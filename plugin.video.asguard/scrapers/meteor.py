
"""
    Asguard Addon
    Copyright (C) 2024
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
import logging
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

BASE_URL = 'https://meteorfortheweebs.midnightignite.me'

class Scraper(scraper.Scraper):
    base_url = BASE_URL
    movie_search_url = '/stream/movie/%s.json'
    tv_search_url = '/stream/series/%s:%s:%s.json'
    debrid_resolvers = resolveurl

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url')
        self.movie_search_url = '/stream/movie/%s.json'
        self.timeout = timeout
        self.min_seeders = 0
        self._set_apikeys()

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Meteor'

    def resolve_link(self, link):
        return link

    def _set_apikeys(self):
        self.pm_apikey = kodi.get_setting('premiumize.apikey')
        self.rd_apikey = kodi.get_setting('realdebrid.apikey')
        self.ad_apikey = kodi.get_setting('alldebrid_api_key')

    def _get_config_params(self):
        """
        Build configuration parameters for Meteor API
        """
        config = {
            "debridService": "torrent",
            "debridApiKey": "",
            "cachedOnly": False,
            "removeTrash": False,
            "removeSamples": False,
            "removeAdult": False,
            "exclude3D": False,
            "enableSeaDex": False,
            "minSeeders": 0,
            "maxResults": 0,
            "maxResultsPerRes": 0,
            "maxSize": 0,
            "resolutions": [],
            "languages": {
                "preferred": ["en", "multi"],
                "required": [],
                "exclude": []
            },
            "resultFormat": ["title", "quality", "size", "audio"],
            "sortOrder": ["pack", "title", "quality", "size", "seeders", "resolution"]
        }

        # Apply user settings if available
        min_seeders = 0
        if min_seeders:
            try:
                config["minSeeders"] = int(min_seeders)
            except ValueError:
                pass

        # Encode config to base64
        config_json = json.dumps(config)
        config_b64 = base64.b64encode(config_json.encode()).decode()
        return config_b64

    def get_intelligent_name(self, file_data, video_type):
        """
        Intelligently choose the best name based on content type and context
        """
        behavior_hints = file_data.get('behaviorHints', {})
        filename = behavior_hints.get('filename', '')
        description = file_data.get('description', '')

        # Parse description lines
        description_lines = description.split('\n')
        first_line = description_lines[0] if description_lines else ''

        # Detect if this is a season pack or individual episode
        is_season_pack = self._is_season_pack(filename, first_line)
        logger.log('Meteor: Season pack detection - is_season_pack: %s, filename: %s' % (is_season_pack, filename), log_utils.LOGDEBUG)

        if video_type == VIDEO_TYPES.EPISODE:
            if is_season_pack:
                # For season packs, show pack info
                pack_name = self._clean_pack_name(filename or first_line)
                logger.log('Meteor: Cleaned pack_name: %s' % pack_name, log_utils.LOGDEBUG)
                return pack_name
            else:
                # For individual episodes, use filename if available
                logger.log('Meteor: Processing as individual episode', log_utils.LOGDEBUG)
                if filename:
                    result = self._clean_episode_name(filename)
                    logger.log('Meteor: Using filename: %s' % result, log_utils.LOGDEBUG)
                    return result
                else:
                    result = self._clean_pack_name(first_line)
                    logger.log('Meteor: Using cleaned description: %s' % result, log_utils.LOGDEBUG)
                    return result
        else:
            # For movies, use the most descriptive name available
            if filename:
                return self._clean_episode_name(filename)
            else:
                return self._clean_pack_name(first_line)

    def _is_season_pack(self, filename, description):
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
        ]

        combined_text = f"{filename} {description}".lower()
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
            r'\([^)]*(?:1080p|720p|480p|2160p|4K)[^)]*\)',  # Resolution-based quality info
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
        Extract metadata from Meteor API response
        """
        behavior_hints = file_data.get('behaviorHints', {})
        filename = behavior_hints.get('filename', '')
        description = file_data.get('description', '')

        metadata = {
            'seeders': 0,
            'size': 0,
            'size_gb': 0,
            'source': 'Meteor',
            'quality_info': []
        }

        # Extract size from behaviorHints or description
        video_size = behavior_hints.get('videoSize', 0)
        if video_size:
            metadata['size'] = video_size / (1024 * 1024)  # Convert to MB
            metadata['size_gb'] = video_size / (1024 * 1024 * 1024)
        else:
            # Try to extract from description
            size_match = re.search(r'💾\s*([\d.]+)\s*(GB|MB)', description)
            if size_match:
                size_value = float(size_match.group(1))
                size_unit = size_match.group(2)
                if size_unit == 'GB':
                    metadata['size'] = size_value * 1024  # MB for compatibility
                    metadata['size_gb'] = size_value
                else:
                    metadata['size'] = size_value
                    metadata['size_gb'] = size_value / 1024

        # Enhanced quality detection
        combined_text = f"{filename} {description}".upper()
        quality_info = []

        # Source type  
        if 'REMUX' in combined_text:
            quality_info.append('REMUX')
        elif 'BLURAY' in combined_text or 'BD' in combined_text:
            quality_info.append('BluRay')
        elif 'WEB' in combined_text:
            quality_info.append('WEB')
        elif 'DVDRIP' in combined_text:
            quality_info.append('DVDRip')

        # Codec
        if 'X265' in combined_text or 'HEVC' in combined_text:
            quality_info.append('x265')
        elif 'X264' in combined_text:
            quality_info.append('x264')

        # Resolution
        if '2160P' in combined_text or '4K' in combined_text:
            quality_info.append('4K')
        elif '1080P' in combined_text:
            quality_info.append('1080p')
        elif '720P' in combined_text:
            quality_info.append('720p')
        elif '480P' in combined_text:
            quality_info.append('480p')

        metadata['quality_info'] = quality_info
        return metadata

    def get_sources(self, video):
        sources = []

        try:
            # Use centralized IMDB ID retrieval from base class
            imdb_id = self.get_imdb_id(video)
            if not imdb_id:
                logger.log('Meteor: No IMDB ID found for trakt_id: %s' % video.trakt_id, log_utils.LOGWARNING)
                return sources

            # Get configuration parameters
            config_params = self._get_config_params()

            if video.video_type == VIDEO_TYPES.MOVIE:
                search_url = 'stream/movie/%s.json' % imdb_id
                logger.log('Meteor: Searching for movie: %s' % search_url, log_utils.LOGDEBUG)
            elif video.video_type == VIDEO_TYPES.EPISODE:
                search_url = 'stream/series/%s:%s:%s.json' % (imdb_id, video.season, video.episode)
                logger.log('Meteor: Searching for episode S%sE%s: %s' % (video.season, video.episode, search_url), log_utils.LOGDEBUG)
            else:
                logger.log('Meteor: Unsupported video type: %s' % video.video_type, log_utils.LOGWARNING)
                return sources

            # Construct URL with base64-encoded config
            url = '%s/%s/%s' % (self.base_url, config_params, search_url)
            logger.log('Meteor: Fetching from URL: %s' % url, log_utils.LOGDEBUG)
            response = self._http_get(url, cache_limit=1, require_debrid=True)
            if not response or response == FORCE_NO_MATCH:
                logger.log('Meteor: No response or forced no match', log_utils.LOGDEBUG)
                return sources

            try:
                data = json.loads(response)
                files = data.get('streams', [])
                logger.log('Meteor: Found %d streams from API' % len(files), log_utils.LOGDEBUG)
            except json.JSONDecodeError as e:
                logger.log('Meteor: Failed to parse JSON response: %s' % str(e), log_utils.LOGERROR)
                return sources

            for file_data in files:
                try:
                    hash_value = file_data.get('infoHash')
                    if not hash_value:
                        continue

                    # Get intelligent name based on content type
                    display_name = self.get_intelligent_name(file_data, video.video_type)
                    logger.log('Meteor: Generated display_name: %s' % display_name, log_utils.LOGDEBUG)

                    # Extract enhanced metadata
                    metadata = self.extract_enhanced_metadata(file_data)

                    # Check minimum seeders requirement
                    if self.min_seeders > metadata['seeders']:
                        logger.log('Meteor: Skipping source with %d seeders (min: %d)' % (metadata['seeders'], self.min_seeders), log_utils.LOGDEBUG)
                        continue

                    # Create magnet URL with proper encoding
                    magnet_url = 'magnet:?xt=urn:btih:%s&dn=%s' % (hash_value, urllib.parse.quote(display_name))

                    # Get quality using existing method
                    quality = scraper_utils.get_tor_quality(file_data.get('description', ''))

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
                    logger.log('Meteor: Added source: %s [%s] [%d seeders]' % (display_name, quality, metadata['seeders']), log_utils.LOGDEBUG)

                except Exception as e:
                    logger.log('Meteor: Error processing stream: %s' % str(e), log_utils.LOGWARNING)
                    continue

        except Exception as e:
            logger.log('Meteor: Unexpected error in get_sources: %s' % str(e), log_utils.LOGERROR)

        logger.log('Meteor: Returning %d sources' % len(sources), log_utils.LOGDEBUG)
        return sources

    def search(self, video_type, title, year, season=''):
        """
        Search method for Meteor scraper.
        Meteor works best with IMDB IDs through get_sources.
        """
        logger.log('Meteor: Text search not optimal - use get_sources with IMDB ID for best results', log_utils.LOGDEBUG)
        return []
