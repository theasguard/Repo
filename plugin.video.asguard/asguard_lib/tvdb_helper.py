
"""
Asgard Addon - Integrated TVDB Helper Module

This module provides a shared cache for TVDB IDs using a JSON file to reduce API calls
to TMDB for TVDB ID lookups. It integrates with the existing tvdb_persist module
and uses show data from the default.py file.

Usage example:

        helper = tvdb_helper.TVDBHelper(
        json_url="https://raw.githubusercontent.com/theasguard/Asguard-Updates/refs/heads/main/asg_tvdb.json")
    tvdb_id = helper.enrich_show_tvdb_id(show, tmdb_api, trakt_api=trakt_api)

    from asguard_lib import tvdb_helper

    # Initialize the helper (profile_dir is automatically determined)
    helper = tvdb_helper.TVDBHelper(
        json_url="https://raw.githubusercontent.com/theasguard/Asgard-Updates/main/asg_tvdb.json"
    )

    # Enrich a show with TVDB ID using existing data
    tvdb_id = helper.enrich_show_tvdb_id(show, tmdb_api, trakt_api=trakt_api)
"""
import os
import json
import threading
import time
import xbmcaddon
from datetime import datetime, timezone
from typing import Optional, Dict, Any, Union, List

import kodi
import log_utils
from asguard_lib.tvdb_persist import _coerce_int, enrich_tvdb_id

logger = log_utils.Logger.get_logger(__name__)

# Constants
TVDB_HELPER_ENABLED = 'tvdb_helper_enabled'
TVDB_HELPER_AUTO_UPDATE = 'tvdb_helper_auto_update'
TVDB_HELPER_UPDATE_INTERVAL = 'tvdb_helper_update_interval'  # in days
TVDB_HELPER_FALLBACK_TO_TMDB = 'tvdb_helper_fallback_to_tmdb'
DEFAULT_UPDATE_INTERVAL = 7  # days
JSON_FILENAME = 'asg_tvdb.json'
LOCK_FILENAME = 'asg_tvdb.lock'
addon = xbmcaddon.Addon('plugin.video.asguard')


def get_profile():
    return addon.getAddonInfo('profile')

profile_dir = kodi.translate_path(get_profile())

class TVDBHelper:
    """Helper class for managing TVDB IDs using a shared JSON cache."""

    def __init__(self, json_url: Optional[str] = None):
        """
        Initialize the TVDB Helper.

        Args:
            json_url: Optional URL to download the JSON file from GitHub
        """
        self.profile_dir = profile_dir
        self.json_url = json_url
        self.json_path = os.path.join(profile_dir, JSON_FILENAME)
        self.lock_path = os.path.join(profile_dir, LOCK_FILENAME)
        self._data = None
        self._lock = threading.RLock()
        self._last_check = 0

        # Create profile directory if it doesn't exist
        if not os.path.exists(profile_dir):
            os.makedirs(profile_dir)

        # Load the JSON
        self._load_json()

    def _load_json(self) -> None:
        """Load the JSON from disk or initialize a new structure."""
        with self._lock:
            try:
                if os.path.exists(self.json_path):
                    with open(self.json_path, 'r', encoding='utf-8') as f:
                        self._data = json.load(f)
                    logger.log(f"Loaded TVDB helper JSON from {self.json_path}", log_utils.LOGDEBUG)
                else:
                    self._data = {
                        "version": "1.0",
                        "last_updated": datetime.now(timezone.utc).isoformat(),
                        "entries": {}
                    }
                    # Try to download from GitHub if URL is provided
                    if self.json_url and self._get_setting(TVDB_HELPER_AUTO_UPDATE, 'true') == 'true':
                        self._download_from_github()
                    # Save the initial structure
                    self._save_json()
            except Exception as e:
                logger.log(f"Error loading TVDB helper JSON: {e}", log_utils.LOGERROR)
                # Initialize with empty structure if loading fails
                self._data = {
                    "version": "1.0",
                    "last_updated": datetime.now(timezone.utc).isoformat(),
                    "entries": {}
                }

    def _save_json(self) -> None:
        """Save the current JSON to disk."""
        with self._lock:
            try:
                # Update the last_updated timestamp
                self._data["last_updated"] = datetime.now(timezone.utc).isoformat()

                # Write to a temporary file first to avoid corruption
                temp_path = f"{self.json_path}.tmp"
                with open(temp_path, 'w', encoding='utf-8') as f:
                    json.dump(self._data, f, indent=2, ensure_ascii=False)

                # Rename the temporary file to the final name
                if os.path.exists(self.json_path):
                    os.remove(self.json_path)
                os.rename(temp_path, self.json_path)

                logger.log(f"Saved TVDB helper JSON to {self.json_path}", log_utils.LOGDEBUG)
            except Exception as e:
                logger.log(f"Error saving TVDB helper JSON: {e}", log_utils.LOGERROR)

    def _download_from_github(self) -> bool:
        """
        Download the JSON file from GitHub and merge with local data.

        Returns:
            True if successful, False otherwise
        """
        if not self.json_url:
            return False

        try:
            import requests
            response = requests.get(self.json_url, timeout=10)
            response.raise_for_status()

            remote_data = response.json()

            # Merge remote data with local data
            if "entries" in remote_data:
                with self._lock:
                    # Keep local entries that aren't in remote
                    local_entries = self._data.get("entries", {})
                    remote_entries = remote_data.get("entries", {})

                    # Update with remote entries
                    for key, value in remote_entries.items():
                        if key not in local_entries:
                            local_entries[key] = value

                    self._data["entries"] = local_entries
                    self._data["last_updated"] = datetime.now(timezone.utc).isoformat()

                    logger.log(f"Merged {len(remote_entries)} entries from GitHub", log_utils.LOGDEBUG)
                    return True
        except Exception as e:
            logger.log(f"Error downloading TVDB helper JSON from GitHub: {e}", log_utils.LOGERROR)

        return False

    def _get_setting(self, setting_id: str, default: str = '') -> str:
        """Get an addon setting value."""
        try:
            return kodi.get_setting(setting_id) or default
        except Exception:
            return default

    def _acquire_lock(self, timeout: float = 5.0) -> bool:
        """
        Acquire a file lock to prevent concurrent access.

        Args:
            timeout: Maximum time to wait for the lock

        Returns:
            True if lock acquired, False otherwise
        """
        try:
            if not os.path.exists(self.lock_path):
                with open(self.lock_path, 'x') as f:
                    f.write(str(os.getpid()))
                return True
            return False
        except Exception:
            return False

    def _release_lock(self) -> None:
        """Release the file lock."""
        try:
            if os.path.exists(self.lock_path):
                os.remove(self.lock_path)
        except Exception:
            pass

    def update_json_from_github(self) -> bool:
        """
        Download and merge updates from GitHub.

        Returns:
            True if successful, False otherwise
        """
        if not self.json_url or self._get_setting(TVDB_HELPER_AUTO_UPDATE, 'true') != 'true':
            return False

        # Check if we need to update based on interval
        now = time.time()
        interval_days = int(self._get_setting(TVDB_HELPER_UPDATE_INTERVAL, str(DEFAULT_UPDATE_INTERVAL)))
        interval_seconds = interval_days * 24 * 60 * 60

        if now - self._last_check < interval_seconds:
            return False

        self._last_check = now

        if self._acquire_lock():
            try:
                result = self._download_from_github()
                if result:
                    self._save_json()
                return result
            finally:
                self._release_lock()

        return False

    def enrich_show_tvdb_id(self, show: Dict[str, Any], tmdb_api, trakt_api=None) -> Optional[int]:
        """
        Enrich a show with TVDB ID using the helper cache and existing tvdb_persist functionality.

        This method:
        1. First tries to find the TVDB ID in the JSON cache
        2. If not found, falls back to the tvdb_persist.enrich_tvdb_id function
        3. If a TVDB ID is found, adds it to the JSON cache for future use

        Args:
            show: The show dictionary with at least a title and ids
            tmdb_api: TMDB API instance
            trakt_api: Optional Trakt API instance

        Returns:
            The TVDB ID if found, None otherwise
        """

        if self._get_setting(TVDB_HELPER_ENABLED, 'true') != 'true':
            # If the helper is disabled, just use the original function
            return enrich_tvdb_id(show, tmdb_api, trakt_api=trakt_api)

        try:
            # Extract show information
            ids = show.get('ids') or {}
            title = show.get('title')
            year = show.get('year')

            # Check if we need to update from GitHub
            self.update_json_from_github()

            # Try to find TVDB ID in cache using available IDs
            tvdb_id = None

            # Check if we already have a TVDB ID
            current_tvdb = _coerce_int(ids.get('tvdb'))
            if current_tvdb:
                return current_tvdb

            # Try to find by TMDB ID
            tmdb_id = ids.get('tmdb')
            if tmdb_id:
                tvdb_id = self.get_tvdb_by_tmdb(tmdb_id)
                if tvdb_id:
                    ids['tvdb'] = tvdb_id
                    show['ids'] = ids
                    return tvdb_id

            # Try to find by Trakt ID
            trakt_id = ids.get('trakt')
            if trakt_id:
                tvdb_id = self.get_tvdb_by_trakt(trakt_id)
                if tvdb_id:
                    ids['tvdb'] = tvdb_id
                    show['ids'] = ids
                    return tvdb_id

            # Try to find by title
            if title:
                tvdb_id = self.get_tvdb_by_title(title, year)
                if tvdb_id:
                    ids['tvdb'] = tvdb_id
                    show['ids'] = ids
                    return tvdb_id

            # If not found in cache, try using the original tvdb_persist function
            tvdb_id = enrich_tvdb_id(show, tmdb_api, trakt_api=trakt_api)

            # If found using the original function, add to our cache
            if tvdb_id and self._acquire_lock():
                try:
                    self.add_mapping(
                        title=title,
                        year=year,
                        tmdb_id=tmdb_id,
                        trakt_id=trakt_id,
                        tvdb_id=tvdb_id
                    )
                finally:
                    self._release_lock()

            return tvdb_id
        except Exception as e:
            logger.log(f"Error in enrich_show_tvdb_id: {e}", log_utils.LOGERROR)
            # Fallback to the original function
            return enrich_tvdb_id(show, tmdb_api, trakt_api=trakt_api)

    def get_tvdb_by_tmdb(self, tmdb_id: Union[int, str]) -> Optional[int]:
        """
        Get TVDB ID using TMDB ID.

        Args:
            tmdb_id: The TMDB ID to look up

        Returns:
            The TVDB ID if found, None otherwise
        """
        tmdb_id = _coerce_int(tmdb_id)
        if not tmdb_id:
            return None

        # Look up in cache
        key = f"tmdb_{tmdb_id}"
        with self._lock:
            entry = self._data.get("entries", {}).get(key)
            if entry and "tvdb_id" in entry:
                tvdb_id = _coerce_int(entry["tvdb_id"])
                if tvdb_id:
                    logger.log(f"Found TVDB ID {tvdb_id} for TMDB ID {tmdb_id} in cache", log_utils.LOGDEBUG)
                    return tvdb_id

        return None

    def get_tvdb_by_trakt(self, trakt_id: Union[int, str]) -> Optional[int]:
        """
        Get TVDB ID using Trakt ID.

        Args:
            trakt_id: The Trakt ID to look up

        Returns:
            The TVDB ID if found, None otherwise
        """
        trakt_id = _coerce_int(trakt_id)
        if not trakt_id:
            return None

        # Look up in cache
        key = f"trakt_{trakt_id}"
        with self._lock:
            entry = self._data.get("entries", {}).get(key)
            if entry and "tvdb_id" in entry:
                tvdb_id = _coerce_int(entry["tvdb_id"])
                if tvdb_id:
                    logger.log(f"Found TVDB ID {tvdb_id} for Trakt ID {trakt_id} in cache", log_utils.LOGDEBUG)
                    return tvdb_id

        return None

    def get_tvdb_by_title(self, title: str, year: Optional[int] = None) -> Optional[int]:
        """
        Get TVDB ID using show title.

        Args:
            title: The show title to look up
            year: Optional release year to disambiguate

        Returns:
            The TVDB ID if found, None otherwise
        """
        if not title:
            return None

        # Look up in cache
        with self._lock:
            entries = self._data.get("entries", {})
            # First try exact match
            for key, entry in entries.items():
                if entry.get("title") == title:
                    if year and entry.get("year") and entry.get("year") != year:
                        continue
                    tvdb_id = _coerce_int(entry.get("tvdb_id"))
                    if tvdb_id:
                        logger.log(f"Found TVDB ID {tvdb_id} for title '{title}' in cache", log_utils.LOGDEBUG)
                        return tvdb_id

            # Try case-insensitive match
            title_lower = title.lower()
            for key, entry in entries.items():
                if entry.get("title", "").lower() == title_lower:
                    if year and entry.get("year") and entry.get("year") != year:
                        continue
                    tvdb_id = _coerce_int(entry.get("tvdb_id"))
                    if tvdb_id:
                        logger.log(f"Found TVDB ID {tvdb_id} for title '{title}' (case-insensitive) in cache", log_utils.LOGDEBUG)
                        return tvdb_id

        return None

    def add_mapping(self, 
                   title: Optional[str] = None,
                   year: Optional[int] = None,
                   tmdb_id: Optional[Union[int, str]] = None,
                   trakt_id: Optional[Union[int, str]] = None,
                   tvdb_id: Optional[Union[int, str]] = None) -> bool:
        """
        Add a new mapping to the JSON cache.

        Args:
            title: Show title
            year: Release year
            tmdb_id: TMDB ID
            trakt_id: Trakt ID
            tvdb_id: TVDB ID

        Returns:
            True if successful, False otherwise
        """
        try:
            # Convert IDs to integers
            tmdb_id = _coerce_int(tmdb_id)
            trakt_id = _coerce_int(trakt_id)
            tvdb_id = _coerce_int(tvdb_id)

            # At least one ID is required
            if not any([tmdb_id, trakt_id, tvdb_id]):
                return False

            with self._lock:
                entries = self._data.get("entries", {})

                # Create or update entries for each ID
                if tmdb_id:
                    key = f"tmdb_{tmdb_id}"
                    if key not in entries:
                        entries[key] = {}
                    self._update_entry(entries[key], title, year, tmdb_id, trakt_id, tvdb_id)

                if trakt_id:
                    key = f"trakt_{trakt_id}"
                    if key not in entries:
                        entries[key] = {}
                    self._update_entry(entries[key], title, year, tmdb_id, trakt_id, tvdb_id)

                if tvdb_id:
                    key = f"tvdb_{tvdb_id}"
                    if key not in entries:
                        entries[key] = {}
                    self._update_entry(entries[key], title, year, tmdb_id, trakt_id, tvdb_id)

                self._data["entries"] = entries
                self._save_json()

                logger.log(f"Added mapping: title={title}, tmdb={tmdb_id}, trakt={trakt_id}, tvdb_id={tvdb_id}", log_utils.LOGDEBUG)
                return True
        except Exception as e:
            logger.log(f"Error adding mapping: {e}", log_utils.LOGERROR)
            return False

    def _update_entry(self, entry: Dict[str, Any], 
                     title: Optional[str],
                     year: Optional[int],
                     tmdb_id: Optional[int],
                     trakt_id: Optional[int],
                     tvdb_id: Optional[int]) -> None:
        """
        Update an entry with new information.

        Args:
            entry: The entry to update
            title: Show title
            year: Release year
            tmdb_id: TMDB ID
            trakt_id: Trakt ID
            tvdb_id: TVDB ID
        """
        if title is not None:
            entry["title"] = title
        if year is not None:
            entry["year"] = year
        if tmdb_id is not None:
            entry["tmdb_id"] = tmdb_id
        if trakt_id is not None:
            entry["trakt_id"] = trakt_id
        if tvdb_id is not None:
            entry["tvdb_id"] = tvdb_id

    def add_show_ids_to_cache(self, show: Dict[str, Any]) -> bool:
        """
        Add all available IDs from a show to the TVDB helper cache.

        Args:
            helper: The TVDBHelper instance
            show: The show dictionary with title, year, and ids

        Returns:
            True if successful, False otherwise
        """
        try:
            # Extract show information
            ids = show.get('ids') or {}
            title = show.get('title')
            year = show.get('year')

            # Get the IDs
            tmdb_id = ids.get('tmdb')
            trakt_id = ids.get('trakt')
            tvdb_id = ids.get('tvdb')

            # Add the mapping to the cache
            return self.add_mapping(
                title=title,
                year=year,
                tmdb_id=tmdb_id,
                trakt_id=trakt_id,
                tvdb_id=tvdb_id
            )
        except Exception as e:
            logger.log(f"Error adding show IDs to cache: {e}", log_utils.LOGERROR)
            return False

    def update_cache_with_shows(self, shows: List[Dict[str, Any]]) -> int:
        """
        Update the TVDB helper cache with multiple shows.

        Args:
            helper: The TVDBHelper instance
            shows: List of show dictionaries

        Returns:
            Number of shows successfully added to the cache
        """
        count = 0
        for show in shows:
            if self.add_show_ids_to_cache(show):
                count += 1

        logger.log(f"Added {count} shows to TVDB helper cache", log_utils.LOGINFO)
        return count

    def update_cache_from_trakt(self, trakt_api) -> int:
        """
        Update the TVDB helper cache with shows from Trakt.

        Args:
            helper: The TVDBHelper instance
            trakt_api: The Trakt API instance

        Returns:
            Number of shows successfully added to the cache
        """
        try:
            # Get all shows from Trakt
            shows = trakt_api.get_all_shows() or []
            return self.update_cache_with_shows(shows)
        except Exception as e:
            logger.log(f"Error updating cache from Trakt: {e}", log_utils.LOGERROR)
            return 0

    def update_cache_from_tmdb(self, tmdb_api, shows: List[Dict[str, Any]]) -> int:
        """
        Update the TVDB helper cache with TVDB IDs from TMDB for existing shows.

        Args:
            helper: The TVDBHelper instance
            tmdb_api: The TMDB API instance
            shows: List of show dictionaries

        Returns:
            Number of shows successfully updated with TVDB IDs
        """
        count = 0
        for show in shows:
            try:
                # Debug: Check if show is a dictionary
                if not isinstance(show, dict):
                    logger.log(f"Error: show is not a dictionary: {type(show)} - {show}", log_utils.LOGERROR)
                    continue
                    
                ids = show.get('ids') or {}
                tmdb_id = ids.get('tmdb')
                
                # Debug: Check if ids is a dictionary
                if not isinstance(ids, dict):
                    logger.log(f"Error: ids is not a dictionary: {type(ids)} - {ids}", log_utils.LOGERROR)
                    continue

                if tmdb_id and not ids.get('tvdb'):
                    # Get TVDB ID from TMDB
                    from asguard_lib.tvdb_persist import _fetch_tvdb_from_tmdb
                    tvdb_id = _fetch_tvdb_from_tmdb(tmdb_api, tmdb_id)

                    if tvdb_id:
                        # Update the show with the TVDB ID
                        ids['tvdb'] = tvdb_id
                        show['ids'] = ids

                        # Add to cache
                        if self.add_mapping(
                            title=show.get('title'),
                            year=show.get('year'),
                            tmdb_id=tmdb_id,
                            trakt_id=ids.get('trakt'),
                            tvdb_id=tvdb_id
                        ):
                            count += 1
            except Exception as e:
                logger.log(f"Error updating show from TMDB: {e}", log_utils.LOGERROR)
                import traceback
                logger.log(f"Traceback: {traceback.format_exc()}", log_utils.LOGERROR)

        logger.log(f"Updated {count} shows with TVDB IDs from TMDB", log_utils.LOGINFO)
        return count
