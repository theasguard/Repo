
"""
    Asguard Addon - MDBList API
    Copyright (C) 2025 MrBlamo, tknorris

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
import json
import time
import threading
import requests
import kodi
import log_utils
import utils
from asguard_lib.db_utils import DB_Connection
from urllib3.util.retry import Retry
from typing import Any, Union, Dict, List, Optional

logger = log_utils.Logger.get_logger(__name__)

# MDBList API Configuration
BASE_URL = "https://api.mdblist.com"
TIMEOUT = 5.05
RESULTS_LIMIT = 100

# Modern retry configuration
retry_strategy = Retry(
    total=None,
    backoff_factor=1,
    status_forcelist=[429, 502, 503, 504],
    allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"],
    raise_on_status=False
)

# Create session with retry strategy
session = requests.Session()
session.mount('https://api.mdblist.com', requests.adapters.HTTPAdapter(pool_maxsize=100, max_retries=retry_strategy))

class MDBListError(Exception):
    """Base exception for MDBList errors"""
    pass

class MDBListAuthError(Exception):
    """Exception for MDBList authentication errors"""
    pass

class MDBListNotFoundError(Exception):
    """Exception for MDBList not found errors"""
    pass

class TransientMDBListError(Exception):
    """Exception for transient MDBList errors"""
    pass

class MDBList_API:
    """MDBList API client with caching similar to Trakt API"""

    def __init__(self, token=None, timeout=TIMEOUT, offline=False):
        """
        Initialize MDBList API client

        Args:
            token: MDBList API token
            timeout: Request timeout in seconds
            offline: Whether to operate in offline mode (use cache only)
        """
        self.token = token or kodi.get_setting('mdblist_token')
        self.timeout = None if timeout == 0 else timeout
        self.offline = offline
        self.__db_connection = DB_Connection()
        self.__worker_id = None

        logger.log(f"MDBList API initialized with token: {'***' if self.token else 'None'}", log_utils.LOGDEBUG)

    def __get_db_connection(self):
        """Get database connection, creating new one if needed for current thread"""
        worker_id = threading.current_thread().ident
        if not self.__db_connection or self.__worker_id != worker_id:
            self.__db_connection = DB_Connection()
            self.__worker_id = worker_id
        return self.__db_connection

    def __get_cache_limit(self, cache_limit):
        """
        Get cache limit in hours

        Args:
            cache_limit: Cache limit in hours

        Returns:
            Cache limit in hours
        """
        if self.offline:
            return int(time.time()) / 60 / 60
        else:
            if cache_limit > 8:
                return cache_limit
            else:
                return 8

    def __call_mdblist(self, path: str, method: str = None, data: Any = None, params: dict = None, cache_limit: float = 1.0, cached: bool = True) -> Union[str, list, dict, Any]:
        """
        Make API call to MDBList with caching

        Args:
            path: API endpoint path
            method: HTTP method (GET, POST, DELETE, etc.)
            data: Request body data
            params: Query parameters
            cache_limit: Cache limit in hours
            cached: Whether to use cache

        Returns:
            Response data as JSON or text
        """
        if not cached:
            cache_limit = 0

        if self.offline:
            db_cache_limit = int(time.time()) / 60 / 60
        else:
            db_cache_limit = self.__get_cache_limit(cache_limit)

        json_data = json.dumps(data) if data else None
        url = f"{BASE_URL}/{path}"

        # Add API key to params
        if params is None:
            params = {}
        params['apikey'] = self.token

        logger.log(f"MDBList Call: {path}, data: {json_data}, cache_limit: {cache_limit}, cached: {cached}", log_utils.LOGDEBUG)

        db_connection = self.__get_db_connection()
        created, cached_headers, cached_result = db_connection.get_cached_url(url, json_data, db_cache_limit)

        # Use cached result if available and not expired
        if cached_result and (self.offline or (time.time() - created) < (60 * 60 * cache_limit)):
            result = cached_result
            logger.log(f"Using cached result for: {url}", log_utils.LOGDEBUG)
        else:
            try:
                req_method = (method or 'get').upper()
                r = session.request(req_method, url, params=params, json=data, timeout=self.timeout)

                status = r.status_code
                if status >= 400:
                    if status == 401:
                        raise MDBListAuthError(f"MDBList authentication failed (HTTP {status})")
                    elif status == 404:
                        raise MDBListNotFoundError(f"MDBList resource not found (HTTP {status}): {url}")
                    elif status in [500, 502, 503, 504]:
                        if cached_result:
                            result = cached_result
                            logger.log(f"Temporary MDBList Error (HTTP {status}). Using Cached Page Instead.", log_utils.LOGWARNING)
                            return result
                        else:
                            raise TransientMDBListError(f"Temporary MDBList Error: HTTP {status}")
                    else:
                        raise MDBListError(f"MDBList Error: HTTP {status}")

                result = r.text
                logger.log(f"MDBList Response: {result}", log_utils.LOGDEBUG)
                db_connection.cache_url(url, result, json_data, list(r.headers.items()))
            except requests.exceptions.RequestException as e:
                if cached_result:
                    result = cached_result
                    logger.log(f"MDBList Request Error: {str(e)}. Using Cached Page Instead.", log_utils.LOGWARNING)
                else:
                    raise MDBListError(f"MDBList Request Error: {str(e)}")

        # Try to parse as JSON if possible
        try:
            return json.loads(result)
        except (json.JSONDecodeError, ValueError):
            return result

    # User Lists Methods
    def get_user_lists(self, list_type='my'):
        """
        Get user lists

        Args:
            list_type: 'my' for user's own lists, 'external' for external lists

        Returns:
            List of user lists
        """
        path = 'lists/user' if list_type == 'my' else 'external/lists/user'
        return self.__call_mdblist(path, cache_limit=1.0)

    def get_list_contents(self, list_id, list_type='my', unified=True):
        """
        Get contents of a list

        Args:
            list_id: List ID
            list_type: 'my' or 'external'
            unified: Whether to return unified format

        Returns:
            List items
        """
        path = f"lists/{list_id}/items"
        if unified:
            path += '?unified=true'
        return self.__call_mdblist(path, cache_limit=1.0)

    def search_lists(self, query):
        """
        Search for lists

        Args:
            query: Search query

        Returns:
            List of matching lists
        """
        path = f"lists/search?query={query}"
        return self.__call_mdblist(path, cache_limit=1.0)

    def get_top_lists(self):
        """
        Get top lists

        Returns:
            List of top lists
        """
        path = 'lists/top'
        return self.__call_mdblist(path, cache_limit=1.0)

    # Collection and Watchlist Methods
    def get_collection(self, mediatype='all', limit=5000):
        """
        Get user collection

        Args:
            mediatype: 'movies', 'shows', or 'all'
            limit: Maximum items to fetch

        Returns:
            Collection items
        """
        path = 'sync/collection'
        params = {'limit': limit}
        result = self.__call_mdblist(path, params=params, cache_limit=1.0)

        # If result has pagination, fetch all pages
        if result and 'pagination' in result and result['pagination']['has_more']:
            items = {'movies': [], 'shows': []}
            items['movies'] = result.get('movies', [])
            items['shows'] = result.get('shows', [])

            while result['pagination']['has_more']:
                offset = result['pagination']['offset'] + result['pagination']['limit']
                params['offset'] = offset
                result = self.__call_mdblist(path, params=params, cache_limit=0)
                items['movies'].extend(result.get('movies', []))
                items['shows'].extend(result.get('shows', []))

            result = items

        return result

    def get_watchlist(self, mediatype='all', limit=1000):
        """
        Get user watchlist

        Args:
            mediatype: 'movies', 'shows', or 'all'
            limit: Maximum items to fetch

        Returns:
            Watchlist items
        """
        path = 'watchlist/items'
        params = {'limit': limit}
        result = self.__call_mdblist(path, params=params, cache_limit=1.0)

        # If result has pagination, fetch all pages
        if result and 'pagination' in result and result['pagination']['has_more']:
            items = {'movies': [], 'shows': []}
            items['movies'] = result.get('movies', [])
            items['shows'] = result.get('shows', [])

            while result['pagination']['has_more']:
                offset = result['pagination']['offset'] + result['pagination']['limit']
                params['offset'] = offset
                result = self.__call_mdblist(path, params=params, cache_limit=0)
                items['movies'].extend(result.get('movies', []))
                items['shows'].extend(result.get('shows', []))

            result = items

        return result

    def add_to_collection(self, mediatype, items):
        """
        Add items to collection

        Args:
            mediatype: 'movies' or 'shows'
            items: List of items to add

        Returns:
            API response
        """
        data = {mediatype: items}
        result = self.__call_mdblist('sync/collection', method='post', data=data, cache_limit=0)

        # Clear collection cache after successful update
        if result and result.get('updated', {}).get(mediatype, 0) > 0:
            self.__clear_collection_cache(mediatype)

        return result

    def remove_from_collection(self, mediatype, items):
        """
        Remove items from collection

        Args:
            mediatype: 'movies' or 'shows'
            items: List of items to remove

        Returns:
            API response
        """
        data = {mediatype: items}
        result = self.__call_mdblist('sync/collection/remove', method='post', data=data, cache_limit=0)

        # Clear collection cache after successful update
        if result and result.get('removed', {}).get(mediatype, 0) > 0:
            self.__clear_collection_cache(mediatype)

        return result

    def add_to_watchlist(self, list_id, items):
        """
        Add items to watchlist or list

        Args:
            list_id: List ID ('watchlist' for watchlist)
            items: List of items to add

        Returns:
            API response
        """
        path = 'watchlist/items/add' if list_id == 'watchlist' else f'lists/{list_id}/items/add'
        result = self.__call_mdblist(path, method='post', data=items, cache_limit=0)

        # Clear watchlist cache after successful update
        if result and result.get('added', {}).get('movies', 0) + result.get('added', {}).get('shows', 0) > 0:
            self.__clear_watchlist_cache()

        return result

    def remove_from_watchlist(self, list_id, items):
        """
        Remove items from watchlist or list

        Args:
            list_id: List ID ('watchlist' for watchlist)
            items: List of items to remove

        Returns:
            API response
        """
        path = 'watchlist/items/remove' if list_id == 'watchlist' else f'lists/{list_id}/items/remove'
        result = self.__call_mdblist(path, method='post', data=items, cache_limit=0)

        # Clear watchlist cache after successful update
        if result and result.get('removed', {}).get('movies', 0) + result.get('removed', {}).get('shows', 0) > 0:
            self.__clear_watchlist_cache()

        return result

    # Watched Status Methods
    def get_watched(self, limit=5000):
        """
        Get watched items

        Args:
            limit: Maximum items to fetch

        Returns:
            Watched items
        """
        path = 'sync/watched'
        params = {'limit': limit}
        result = self.__call_mdblist(path, params=params, cache_limit=1.0)

        # If result has pagination, fetch all pages
        if result and 'pagination' in result and result['pagination']['has_more']:
            items = {'movies': [], 'episodes': []}
            items['movies'] = result.get('movies', [])
            items['episodes'] = result.get('episodes', [])

            while result['pagination']['has_more']:
                offset = result['pagination']['offset'] + result['pagination']['limit']
                params['offset'] = offset
                result = self.__call_mdblist(path, params=params, cache_limit=0)
                items['movies'].extend(result.get('movies', []))
                items['episodes'].extend(result.get('episodes', []))

            result = items

        return result

    def mark_watched(self, mediatype, media_id, season=None, episode=None, id_type='tmdb'):
        """
        Mark item as watched

        Args:
            mediatype: 'movies', 'shows', 'season', or 'episode'
            media_id: Media ID
            season: Season number (for shows/seasons/episodes)
            episode: Episode number (for episodes)
            id_type: ID type ('tmdb', 'imdb', 'tvdb')

        Returns:
            API response
        """
        if mediatype == 'movies':
            data = {'movies': [{'ids': {id_type: media_id}}]}
        elif mediatype == 'shows':
            data = {'shows': [{'ids': {id_type: media_id}}]}
        elif mediatype == 'season':
            data = {'shows': [{'ids': {id_type: media_id}, 'seasons': [{'number': int(season)}]}]}
        elif mediatype == 'episode':
            data = {'shows': [{'ids': {id_type: media_id}, 'seasons': [{'number': int(season), 'episodes': [{'number': int(episode)}]}]}]}

        result = self.__call_mdblist('sync/watched', method='post', data=data, cache_limit=0)

        # Clear watched cache after successful update
        if result and result.get('updated', {}).get('movies', 0) + result.get('updated', {}).get('episodes', 0) > 0:
            self.__clear_watched_cache()

        return result

    def mark_unwatched(self, mediatype, media_id, season=None, episode=None, id_type='tmdb'):
        """
        Mark item as unwatched

        Args:
            mediatype: 'movies', 'shows', 'season', or 'episode'
            media_id: Media ID
            season: Season number (for shows/seasons/episodes)
            episode: Episode number (for episodes)
            id_type: ID type ('tmdb', 'imdb', 'tvdb')

        Returns:
            API response
        """
        if mediatype == 'movies':
            data = {'movies': [{'ids': {id_type: media_id}}]}
        elif mediatype == 'shows':
            data = {'shows': [{'ids': {id_type: media_id}}]}
        elif mediatype == 'season':
            data = {'shows': [{'ids': {id_type: media_id}, 'seasons': [{'number': int(season)}]}]}
        elif mediatype == 'episode':
            data = {'shows': [{'ids': {id_type: media_id}, 'seasons': [{'number': int(season), 'episodes': [{'number': int(episode)}]}]}]}

        result = self.__call_mdblist('sync/watched/remove', method='post', data=data, cache_limit=0)

        # Clear watched cache after successful update
        if result and result.get('removed', {}).get('movies', 0) + result.get('removed', {}).get('episodes', 0) > 0:
            self.__clear_watched_cache()

        return result

    # Progress/Scrobble Methods
    def get_playback_progress(self):
        """
        Get playback progress for all items

        Returns:
            Playback progress data
        """
        path = 'sync/playback'
        return self.__call_mdblist(path, cache_limit=1.0)

    def update_progress(self, mediatype, media_id, percent, season=None, episode=None, resume_id=None):
        """
        Update playback progress

        Args:
            mediatype: 'movie' or 'show'
            media_id: Media ID
            percent: Progress percentage (0-100)
            season: Season number (for shows)
            episode: Episode number (for shows)
            resume_id: Resume ID (for clearing progress)

        Returns:
            API response
        """
        if resume_id:
            # Clear progress
            data = {'id': resume_id}
            path = 'scrobble/clear'
        else:
            # Update progress
            if mediatype == 'movie':
                data = {'movie': {'ids': {'tmdb': media_id}}, 'progress': float(percent)}
            elif mediatype == 'show':
                data = {'show': {'ids': {'tmdb': media_id}, 'season': {'number': int(season), 'episode': {'number': int(episode)}}}, 'progress': float(percent)}
            path = 'scrobble/pause'

        result = self.__call_mdblist(path, method='post', data=data, cache_limit=0)

        # Clear progress cache after successful update
        if result:
            self.__clear_progress_cache()

        return result

    def clear_progress(self, resume_id):
        """
        Clear playback progress

        Args:
            resume_id: Resume ID to clear

        Returns:
            API response
        """
        return self.update_progress(None, None, 0, resume_id=resume_id)

    # Activity Methods
    def get_activity(self):
        """
        Get last activity timestamps

        Returns:
            Activity timestamps
        """
        path = 'sync/last_activities'
        return self.__call_mdblist(path, cache_limit=0.1)

    def sync_activities(self, force_update=False):
        """
        Sync activities and update cache as needed

        Args:
            force_update: Force full sync regardless of activity timestamps

        Returns:
            Sync status ('success', 'not needed', 'failed', 'no account')
        """
        if not self.token:
            return 'no account'

        if force_update:
            self.__clear_all_cache()

        latest = self.get_activity()
        if latest is None:
            self.__clear_all_cache()
            return 'failed'

        cached = self.__get_cached_activity()
        if cached is None:
            cached = self.__get_default_activities()

        # Compare timestamps and update cache as needed
        success = 'not needed'

        if self.__compare_timestamps(latest.get('watched_at'), cached.get('watched_at')):
            success = 'success'
            self.__sync_watched()

        if self.__compare_timestamps(latest.get('paused_at'), cached.get('paused_at')):
            success = 'success'
            self.__sync_progress()

        if self.__compare_timestamps(latest.get('watchlisted_at'), cached.get('watchlisted_at')):
            success = 'success'
            self.__clear_watchlist_cache()

        if self.__compare_timestamps(latest.get('collected_at'), cached.get('collected_at')):
            success = 'success'
            self.__clear_collection_cache('all')

        if self.__compare_timestamps(latest.get('dropped_at'), cached.get('dropped_at')):
            success = 'success'
            self.__clear_dropped_cache()

        if self.__compare_timestamps(latest.get('list_updated_at'), cached.get('list_updated_at')):
            success = 'success'
            self.__clear_lists_cache()

        # Update cached activity
        self.__set_cached_activity(latest)

        return success

    # Hidden/Dropped Methods
    def get_hidden_items(self, list_type='dropped'):
        """
        Get hidden/dropped items

        Args:
            list_type: Type of hidden list ('dropped')

        Returns:
            Hidden items
        """
        path = f'sync/{list_type}'
        result = self.__call_mdblist(path, cache_limit=1.0)

        # If result has pagination, fetch all pages
        if result and 'pagination' in result and result['pagination']['has_more']:
            items = result.get('shows', [])

            while result['pagination']['has_more']:
                offset = result['pagination']['offset'] + result['pagination']['limit']
                result = self.__call_mdblist(path, params={'offset': offset}, cache_limit=0)
                items.extend(result.get('shows', []))

            result = {'shows': items}

        return result

    def hide_item(self, mediatype, media_id, id_type='tmdb'):
        """
        Hide item

        Args:
            mediatype: 'movies' or 'shows'
            media_id: Media ID
            id_type: ID type ('tmdb', 'imdb', 'tvdb')

        Returns:
            API response
        """
        data = {mediatype: [{'ids': {id_type: media_id}}]}
        result = self.__call_mdblist('sync/dropped', method='post', data=data, cache_limit=0)

        # Clear dropped cache after successful update
        if result:
            self.__clear_dropped_cache()

        return result

    def unhide_item(self, mediatype, media_id, id_type='tmdb'):
        """
        Unhide item

        Args:
            mediatype: 'movies' or 'shows'
            media_id: Media ID
            id_type: ID type ('tmdb', 'imdb', 'tvdb')

        Returns:
            API response
        """
        data = {mediatype: [{'ids': {id_type: media_id}}]}
        result = self.__call_mdblist('sync/dropped/remove', method='post', data=data, cache_limit=0)

        # Clear dropped cache after successful update
        if result:
            self.__clear_dropped_cache()

        return result

    # Cache Management Methods
    def __clear_all_cache(self):
        """Clear all MDBList cache"""
        try:
            db_connection = self.__get_db_connection()
            patterns = [
                'api.mdblist.com/lists%',
                'api.mdblist.com/sync%',
                'api.mdblist.com/watchlist%',
                'api.mdblist.com/scrobble%',
            ]

            for pattern in patterns:
                sql = 'DELETE FROM url_cache WHERE url LIKE ?'
                db_connection.__execute(sql, (f'%{pattern}%',))

            logger.log('Cleared all MDBList cache', log_utils.LOGDEBUG)
        except Exception as e:
            logger.log(f'Error clearing all MDBList cache: {str(e)}', log_utils.LOGERROR)

    def __clear_collection_cache(self, mediatype):
        """Clear collection cache for specific media type"""
        try:
            db_connection = self.__get_db_connection()
            patterns = [
                'api.mdblist.com/sync/collection%',
            ]

            for pattern in patterns:
                sql = 'DELETE FROM url_cache WHERE url LIKE ?'
                db_connection.__execute(sql, (f'%{pattern}%',))

            logger.log(f'Cleared {mediatype} collection cache', log_utils.LOGDEBUG)
        except Exception as e:
            logger.log(f'Error clearing collection cache: {str(e)}', log_utils.LOGERROR)

    def __clear_watchlist_cache(self):
        """Clear watchlist cache"""
        try:
            db_connection = self.__get_db_connection()
            patterns = [
                'api.mdblist.com/watchlist%',
            ]

            for pattern in patterns:
                sql = 'DELETE FROM url_cache WHERE url LIKE ?'
                db_connection.__execute(sql, (f'%{pattern}%',))

            logger.log('Cleared watchlist cache', log_utils.LOGDEBUG)
        except Exception as e:
            logger.log(f'Error clearing watchlist cache: {str(e)}', log_utils.LOGERROR)

    def __clear_watched_cache(self):
        """Clear watched cache"""
        try:
            db_connection = self.__get_db_connection()
            patterns = [
                'api.mdblist.com/sync/watched%',
            ]

            for pattern in patterns:
                sql = 'DELETE FROM url_cache WHERE url LIKE ?'
                db_connection.__execute(sql, (f'%{pattern}%',))

            logger.log('Cleared watched cache', log_utils.LOGDEBUG)
        except Exception as e:
            logger.log(f'Error clearing watched cache: {str(e)}', log_utils.LOGERROR)

    def __clear_progress_cache(self):
        """Clear progress cache"""
        try:
            db_connection = self.__get_db_connection()
            patterns = [
                'api.mdblist.com/sync/playback%',
                'api.mdblist.com/scrobble%',
            ]

            for pattern in patterns:
                sql = 'DELETE FROM url_cache WHERE url LIKE ?'
                db_connection.__execute(sql, (f'%{pattern}%',))

            logger.log('Cleared progress cache', log_utils.LOGDEBUG)
        except Exception as e:
            logger.log(f'Error clearing progress cache: {str(e)}', log_utils.LOGERROR)

    def __clear_dropped_cache(self):
        """Clear dropped/hidden cache"""
        try:
            db_connection = self.__get_db_connection()
            patterns = [
                'api.mdblist.com/sync/dropped%',
            ]

            for pattern in patterns:
                sql = 'DELETE FROM url_cache WHERE url LIKE ?'
                db_connection.__execute(sql, (f'%{pattern}%',))

            logger.log('Cleared dropped cache', log_utils.LOGDEBUG)
        except Exception as e:
            logger.log(f'Error clearing dropped cache: {str(e)}', log_utils.LOGERROR)

    def __clear_lists_cache(self):
        """Clear lists cache"""
        try:
            db_connection = self.__get_db_connection()
            patterns = [
                'api.mdblist.com/lists%',
                'api.mdblist.com/external/lists%',
            ]

            for pattern in patterns:
                sql = 'DELETE FROM url_cache WHERE url LIKE ?'
                db_connection.__execute(sql, (f'%{pattern}%',))

            logger.log('Cleared lists cache', log_utils.LOGDEBUG)
        except Exception as e:
            logger.log(f'Error clearing lists cache: {str(e)}', log_utils.LOGERROR)

    def __get_cached_activity(self):
        """Get cached activity data"""
        try:
            db_connection = self.__get_db_connection()
            url = f"{BASE_URL}/sync/last_activities"
            created, _, cached_result = db_connection.get_cached_url(url, '', 8760)  # 1 year cache limit

            if cached_result:
                try:
                    return json.loads(cached_result)
                except json.JSONDecodeError:
                    return None
            return None
        except Exception as e:
            logger.log(f'Error getting cached activity: {str(e)}', log_utils.LOGERROR)
            return None

    def __set_cached_activity(self, activity):
        """Set cached activity data"""
        try:
            db_connection = self.__get_db_connection()
            url = f"{BASE_URL}/sync/last_activities"
            json_data = json.dumps(activity)
            db_connection.cache_url(url, json_data, '', [])
        except Exception as e:
            logger.log(f'Error setting cached activity: {str(e)}', log_utils.LOGERROR)

    def __get_default_activities(self):
        """Get default activity timestamps"""
        return {
            'watchlisted_at': '2022-05-24T02:09:00Z',
            'watched_at': '2022-05-24T02:09:00Z',
            'season_watched_at': '2022-05-24T02:09:00Z',
            'episode_watched_at': '2022-05-24T02:09:00Z',
            'rated_at': '2022-05-24T02:09:00Z',
            'collected_at': '2022-05-24T02:09:00Z',
            'dropped_at': '2022-05-24T02:09:00Z',
            'paused_at': '2022-05-24T02:09:00Z',
            'episode_paused_at': '2022-05-24T02:09:00Z',
            'list_updated_at': '2022-05-24T02:09:00Z'
        }

    def __compare_timestamps(self, latest, cached, res_format='%Y-%m-%dT%H:%M:%SZ'):
        """
        Compare timestamps to determine if update is needed

        Args:
            latest: Latest timestamp
            cached: Cached timestamp
            res_format: Timestamp format

        Returns:
            True if latest is newer than cached, False otherwise
        """
        if latest is None and cached is None:
            return False

        try:
            latest_ts = utils.iso_2_utc(latest)
            cached_ts = utils.iso_2_utc(cached)
            return latest_ts > cached_ts
        except Exception as e:
            logger.log(f'Error comparing timestamps: {str(e)}', log_utils.LOGERROR)
            return True

    def __sync_watched(self):
        """Sync watched status"""
        try:
            watched_info = self.get_watched()
            # Process and cache watched status
            # This would be implemented based on specific requirements
            logger.log('Synced watched status', log_utils.LOGDEBUG)
        except Exception as e:
            logger.log(f'Error syncing watched status: {str(e)}', log_utils.LOGERROR)

    def __sync_progress(self):
        """Sync playback progress"""
        try:
            progress_info = self.get_playback_progress()
            # Process and cache progress
            # This would be implemented based on specific requirements
            logger.log('Synced playback progress', log_utils.LOGDEBUG)
        except Exception as e:
            logger.log(f'Error syncing playback progress: {str(e)}', log_utils.LOGERROR)

# Create a singleton instance for easy access
_mdblist_api_instance = None

def get_mdblist_api():
    """
    Get singleton instance of MDBList API

    Returns:
        MDBList_API instance
    """
    global _mdblist_api_instance
    if _mdblist_api_instance is None:
        _mdblist_api_instance = MDBList_API()
    return _mdblist_api_instance
