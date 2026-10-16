
"""
    Asguard Addon
    Copyright (C) 2026
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

import re
import json
import urllib.parse
import base64
import requests
from asguard_lib.utils2 import i18n
import xbmcgui
import kodi
import log_utils
from asguard_lib import scraper_utils
from asguard_lib.constants import FORCE_NO_MATCH, VIDEO_TYPES, QUALITIES
from . import scraper


try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)

logger = log_utils.Logger.get_logger()
logger.disable()
BASE_URL = 'https://torii.nexioapp.org'

# Default configuration for Torii API
DEFAULT_CONFIG = {
    "useEnglishTitles": True,
    "showSeasonalSeries": True,
    "showAiringSeries": True,
    "showTrendingSeries": True,
    "showTopSeries": True,
    "showTrendingMovies": True,
    "showTopMovies": True,
    "showSearchCatalog": True,
    "hideUncached": False,
    "resolutions": ["8K", "4K", "2K", "1080p", "720p", "480p", "SD"],
    "enableP2P": True,
    "language": ["ENG", "RUS", "JPN"]
}

class Scraper(scraper.Scraper):
    base_url = BASE_URL
    movie_search_url = '/%s/stream/movie/%s.json'
    tv_search_url = '/%s/stream/series/%s:%s:%s.json'
    debrid_resolvers = resolveurl

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url') or BASE_URL
        self.movie_search_url = '/%s/stream/movie/%s.json'
        self.tv_search_url = '/%s/stream/series/%s:%s:%s.json'
        self.timeout = timeout
        self.min_seeders = 0
        self._set_apikeys()
        self._config = DEFAULT_CONFIG

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Torii'

    def resolve_link(self, link):
        return link

    def _set_apikeys(self):
        self.pm_apikey = kodi.get_setting('premiumize.apikey')
        self.rd_apikey = kodi.get_setting('realdebrid.apikey')
        self.ad_apikey = kodi.get_setting('alldebrid_api_key')

    def _get_config_string(self):
        """Encode the configuration to base64 for the API URL"""
        config_json = json.dumps({"NexioTorii": json.dumps(self._config)})
        logger.log('Torii: Config JSON: %s' % config_json, log_utils.LOGDEBUG)
        config_b64 = base64.b64encode(config_json.encode()).decode()
        # Return the base64 config without additional URL encoding
        return config_b64

    def get_intelligent_name(self, file_data, video_type):
        """
        Intelligently choose the best name based on content type and context
        """
        description = file_data.get('description', '')
        name = file_data.get('name', '')

        # Parse description to extract filename
        filename_match = re.search(r'📄\s*\[([^\]]+)\]\s*(.+?)(?:\n|$)', description)
        if filename_match:
            filename = filename_match.group(2)
        else:
            filename = description.split('\n')[0] if description else ''

        # Detect if this is a season pack or individual episode
        is_season_pack = self._is_season_pack(filename or description)
        logger.log('Torii: Season pack detection - is_season_pack: %s, filename: %s' % (is_season_pack, filename), log_utils.LOGDEBUG)

        if video_type == VIDEO_TYPES.EPISODE:
            if is_season_pack:
                # For season packs, show pack info
                pack_name = self._clean_pack_name(filename or name)
                logger.log('Torii: Cleaned pack_name: %s' % pack_name, log_utils.LOGDEBUG)
                return pack_name
            else:
                # For individual episodes, use filename if available
                logger.log('Torii: Processing as individual episode', log_utils.LOGDEBUG)
                if filename:
                    result = self._clean_episode_name(filename)
                    logger.log('Torii: Using filename: %s' % result, log_utils.LOGDEBUG)
                    return result
                else:
                    result = self._clean_pack_name(name)
                    logger.log('Torii: Using cleaned name: %s' % result, log_utils.LOGDEBUG)
                    return result
        else:
            # For movies, use the most descriptive name available
            if filename:
                return self._clean_episode_name(filename)
            else:
                return self._clean_pack_name(name)

    def _is_season_pack(self, text):
        """
        Detect if this is a season pack vs individual episode
        """
        pack_indicators = [
            r'season\s+\d+-\d+',  # Season 1-8
            r's\d+-s\d+',        # S01-S08
            r'complete',          # Complete series
            r'seasons?\s+\d+',    # Season 1, Seasons 1
            r'\[S\d+-S\d+\]',     # [S01-S08]
            r'S\d{2}-S\d{2}',     # S01-S08
            r'\[BATCH\]',         # [BATCH]
            r'\(Batch\)',         # (Batch)
        ]

        combined_text = f"{text}".lower()
        return any(re.search(pattern, combined_text, re.IGNORECASE) for pattern in pack_indicators)

    def _clean_pack_name(self, pack_name):
        """
        Clean the pack/collection name for display by removing quality/encoding info
        """
        clean_name = pack_name

        # Remove [tags] at the end (release groups, etc.)
        clean_name = re.sub(r'\[.*?\]', '', clean_name)

        # Remove quality/encoding information in parentheses
        quality_patterns = [
            r'\([^)]*(?:1080p|720p|480p|2160p|4K|8K)[^)]*\)',  # Resolution-based quality info
            r'\([^)]*(?:BluRay|HDTV|WEB-?DL|WEBRip|DVDRip)[^)]*\)',  # Source-based quality info
            r'\([^)]*(?:x265|x264|HEVC|AVC|XVID)[^)]*\)',  # Codec-based quality info
            r'\([^)]*(?:AAC|AC3|DTS|TrueHD|FLAC)[^)]*\)',  # Audio-based quality info
        ]

        for pattern in quality_patterns:
            clean_name = re.sub(pattern, '', clean_name, flags=re.IGNORECASE)

        # Remove group tags like -GROUP at the end
        clean_name = re.sub(r'-[A-Z0-9]+$', '', clean_name, flags=re.IGNORECASE)

        # Clean up multiple spaces and trim
        clean_name = re.sub(r'\s+', ' ', clean_name).strip()

        # If we've cleaned too much and it's empty, return original
        if not clean_name or len(clean_name) < 5:
            return pack_name

        return clean_name

    def _clean_episode_name(self, episode_name):
        """
        Clean individual episode name for display
        """
        if not episode_name:
            return 'Unknown'

        # Remove file extension
        clean_name = re.sub(r'\.(mkv|mp4|avi)$', '', episode_name, flags=re.IGNORECASE)

        # Replace dots and underscores with spaces
        clean_name = re.sub(r'(?<!\d)\.(?!\d)', ' ', clean_name)
        clean_name = re.sub(r'_', ' ', clean_name)

        # Clean up multiple spaces
        clean_name = re.sub(r'\s+', ' ', clean_name).strip()

        return clean_name

    def extract_enhanced_metadata(self, file_data):
        """
        Extract metadata from Torii API response
        """
        description = file_data.get('description', '')
        name = file_data.get('name', '')

        metadata = {
            'seeders': 0,
            'size': 0,
            'size_gb': 0,
            'source': 'Torii',
            'quality_info': []
        }

        # Extract seeders from description
        seeders_match = re.search(r'👥\s*(\d+)', description)
        if seeders_match:
            metadata['seeders'] = int(seeders_match.group(1))

        # Extract size from description
        size_match = re.search(r'💾\s*([\d.]+)\s*(GB|MB|GiB|MiB)', description)
        if size_match:
            size_value = float(size_match.group(1))
            size_unit = size_match.group(2).upper()
            if size_unit in ['GB', 'GIB']:
                metadata['size_gb'] = size_value
                metadata['size'] = size_value * 1024**3
            elif size_unit in ['MB', 'MIB']:
                metadata['size_gb'] = size_value / 1024
                metadata['size'] = size_value * 1024**2

        # Extract quality from name
        quality_match = re.search(r'(1080p|720p|480p|2160p|4K|8K|SD)', name)
        if quality_match:
            metadata['quality'] = quality_match.group(1)

        # Extract language
        lang_match = re.search(r'🎙\s*(\w+)', name)
        if lang_match:
            metadata['language'] = lang_match.group(1)

        # Check if batch
        metadata['is_batch'] = file_data.get('_isBatch', False)

        return metadata

    def _get_api_url(self, video_type, title, year, season, episode):
        """Build the API URL for the request"""
        config_str = self._get_config_string()

        if video_type == VIDEO_TYPES.MOVIE:
            # For movies: /{config}/stream/movie/{imdb_id}.json
            url = self.base_url + self.movie_search_url % (config_str, title)
        else:
            # For TV shows: /{config}/stream/series/{imdb_id}:{season}:{episode}.json
            url = self.base_url + self.tv_search_url % (config_str, title, season, episode)

        return url

    def get_sources(self, video):
        sources = []

        try:
            # Use centralized IMDB ID retrieval from base class
            imdb_id = self.get_imdb_id(video)
            if not imdb_id:
                logger.log('Torii: No IMDB ID found for trakt_id: %s' % video.trakt_id, log_utils.LOGWARNING)
                return sources

            config_str = self._get_config_string()
            # Properly URL encode the config string with curly braces to match the working URL format
            encoded_config = urllib.parse.quote('{%s}' % config_str, safe='')

            if video.video_type == VIDEO_TYPES.MOVIE:
                search_url = '%s%s/stream/movie/%s.json' % (self.base_url, encoded_config, imdb_id)
                logger.log('Torii: Searching for movie: %s' % search_url, log_utils.LOGDEBUG)
            elif video.video_type == VIDEO_TYPES.EPISODE:
                search_url = '%s%s/stream/series/%s:%s:%s.json' % (self.base_url, encoded_config, imdb_id, video.season, video.episode)
                logger.log('Torii: Searching for episode S%sE%s: %s' % (video.season, video.episode, search_url))
            else:
                logger.log('Torii: Unsupported video type: %s' % video.video_type, log_utils.LOGWARNING)
                return sources

            logger.log('Torii: Fetching from URL: %s' % search_url, log_utils.LOGDEBUG)
            response = self._http_get(search_url, cache_limit=1, require_debrid=True)
            if not response or response == FORCE_NO_MATCH:
                logger.log('Torii: No response or forced no match', log_utils.LOGDEBUG)
                return sources

            try:
                data = json.loads(response)
                files = data.get('streams', [])
                logger.log('Torii: Found %d streams from API' % len(files), log_utils.LOGDEBUG)
            except json.JSONDecodeError as e:
                logger.log('Torii: Failed to parse JSON response: %s' % str(e), log_utils.LOGERROR)
                return sources

            for file_data in files:
                try:
                    hash_value = file_data.get('infoHash')
                    if not hash_value:
                        continue

                    # Get intelligent name based on content type
                    display_name = self.get_intelligent_name(file_data, video.video_type)
                    logger.log('Torii: Generated display_name: %s' % display_name, log_utils.LOGDEBUG)

                    # Extract enhanced metadata
                    metadata = self.extract_enhanced_metadata(file_data)

                    # Check minimum seeders requirement
                    if self.min_seeders > metadata['seeders']:
                        logger.log('Torii: Skipping source with %d seeders (min: %d)' % (metadata['seeders'], self.min_seeders), log_utils.LOGDEBUG)
                        continue

                    # Create magnet URL with proper encoding
                    magnet_url = 'magnet:?xt=urn:btih:%s&dn=%s' % (hash_value, urllib.parse.quote(display_name))

                    # Get quality using existing method
                    quality = scraper_utils.get_tor_quality(display_name)

                    # Create enhanced label
                    quality_str = ', '.join(metadata['quality_info'][:2])  # Max 2 quality tags
                    size_str = f"{metadata['size_gb']:.1f}GB" if metadata['size_gb'] > 0 else "Unknown"

                    label_parts = [display_name]
                    if quality_str:
                        label_parts.append(quality_str)
                    label_parts.append(f"{size_str}")
                    if metadata.get('source'):
                        label_parts.append(f"{metadata['source']}")

                    label = ' | '.join(label_parts)

                    source = {
                        'class': self,
                        'host': 'magnet',
                        'label': label,
                        'multi-part': False,
                        'seeders': metadata['seeders'],
                        'hash': hash_value,
                        'name': display_name,
                        'quality': quality,
                        'size': metadata['size'],
                        'language': 'en',
                        'url': magnet_url,
                        'direct': False,
                        'debridonly': True
                    }

                    sources.append(source)
                    logger.log('Torii: Added source: %s [%s] [%d seeders]' % (display_name, quality, metadata['seeders']), log_utils.LOGDEBUG)

                except Exception as e:
                    logger.log('Torii: Error processing stream: %s' % str(e), log_utils.LOGWARNING)
                    continue

        except Exception as e:
            logger.log('Torii: Unexpected error in get_sources: %s' % str(e), log_utils.LOGERROR)

        logger.log('Torii: Returning %d sources' % len(sources), log_utils.LOGDEBUG)
        return sources

    def _get_debrid_provider(self):
        """Determine which debrid provider to use"""
        if self.rd_apikey:
            return 'realdebrid'
        elif self.pm_apikey:
            return 'premiumize'
        elif self.ad_apikey:
            return 'alldebrid'
        return None
