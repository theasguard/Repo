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
import urllib.error
import urllib.request
import requests
from asguard_lib.utils2 import i18n
import xbmcgui
import kodi
import log_utils
from asguard_lib import scraper_utils, control
from asguard_lib.constants import FORCE_NO_MATCH, VIDEO_TYPES, QUALITIES
from . import scraper

try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)
    
logger = log_utils.Logger.get_logger()


BASE_URL = 'https://aiostreams.elfhosted.com/'

class Scraper(scraper.Scraper):
    base_url = BASE_URL
    debrid_resolvers = resolveurl

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout

        params = 'eyJpdiI6IkdRY1BicWJQZ3QwYVZrQm40eTNPYlE9PSIsImVuY3J5cHRlZCI6InV5dGlOOG1YcUxZdTQydkYxTWtxK3RDNFROWFNNR3o5aW5JL2RPMWUzUzg9IiwidHlwZSI6ImFpb0VuY3J5cHQifQ'
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url')
        self.movie_search_url = f'/stremio/{params}/stream/movie/%s.json'
        self.tv_search_url = f'/stremio/{params}/stream/series/%s:%s:%s.json'
        self.bypass_filter = control.getSetting('Aiostreams-bypass_filter') == 'true'
        self._set_apikeys()

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'AioStreams'
    
    def resolve_link(self, link):
        return link

    def _set_apikeys(self):
        self.pm_apikey = kodi.get_setting('premiumize.apikey')
        self.rd_apikey = kodi.get_setting('realdebrid.apikey')
        self.ad_apikey = kodi.get_setting('alldebrid_api_key')

    def get_sources(self, video):
        sources = []

        try:
            # Use centralized IMDB ID retrieval from base class
            imdb_id = self.get_imdb_id(video)
            if not imdb_id:
                logger.log('AioStreams: No IMDB ID found for trakt_id: %s' % video.trakt_id, log_utils.LOGWARNING)
                return sources

            if video.video_type == VIDEO_TYPES.MOVIE:
                search_url = self.movie_search_url % imdb_id
                logger.log('AioStreams: Searching for movie: %s' % search_url, log_utils.LOGDEBUG)
            elif video.video_type == VIDEO_TYPES.EPISODE:
                search_url = self.tv_search_url % (imdb_id, video.season, video.episode)
                logger.log('AioStreams: Searching for episode: %s' % search_url, log_utils.LOGDEBUG)
            else:
                logger.log('AioStreams: Unsupported video type: %s' % video.video_type, log_utils.LOGWARNING)
                return sources

            url = urllib.parse.urljoin(self.base_url, search_url)
            logger.log('AioStreams: Final URL: %s' % url, log_utils.LOGDEBUG)
            response = self._http_get(url, cache_limit=1, require_debrid=True)
            logger.log('AioStreams: Response received: %s' % response, log_utils.LOGDEBUG)
            
            if not response or response == FORCE_NO_MATCH:
                return sources

            try:
                files = json.loads(response).get('streams', [])
                logger.log('AioStreams: Found %d files' % len(files), log_utils.LOGDEBUG)
            except json.JSONDecodeError as e:
                logger.log('AioStreams: Failed to parse JSON response: %s' % str(e), log_utils.LOGERROR)
                return sources

            for file in files:
                try:
                    hash = file['url']
                    logger.log('AioStreams: Found file URL: %s' % hash, log_utils.LOGDEBUG)
                    name = file['description']
                    
                    # Extract filename using the proper hierarchy
                    name_part = ''
                    
                    # Method 1: behaviorHints.filename (preferred)
                    if 'behaviorHints' in file and 'filename' in file['behaviorHints']:
                        name_part = file['behaviorHints']['filename'].strip()
                        logger.log('AioStreams: Using behaviorHints filename: %s' % name_part, log_utils.LOGDEBUG)
                    # Method 2: streamData.filename (fallback) 
                    elif 'streamData' in file and 'filename' in file['streamData']:
                        name_part = file['streamData']['filename'].strip()
                        logger.log('AioStreams: Using streamData filename: %s' % name_part, log_utils.LOGDEBUG)
                    # Method 3: description field (legacy fallback)
                    else:
                        name_parts = name.split('\n')
                        # Try to find a line that looks like a filename (not size info)
                        for line in name_parts:
                            line = line.strip()
                            if line and '💾' not in line and not line.endswith('Audio'):
                                name_part = line
                                break
                        if not name_part and name_parts:
                            name_part = name_parts[-1].strip()
                        logger.log('AioStreams: Using description fallback: %s' % name_part, log_utils.LOGDEBUG)
                    
                    # Clean the filename
                    name_part = scraper_utils.cleanse_title(name_part)
                    
                    url = hash
                    logger.log('AioStreams: Final processed name: %s' % name_part, log_utils.LOGDEBUG)

                    # Extract quality from filename
                    quality = scraper_utils.get_tor_quality(name_part)
                    
                    # Extract size information - check multiple sources
                    size = 0
                    
                    # Method 1: behaviorHints.videoSize (most accurate)
                    if 'behaviorHints' in file and 'videoSize' in file['behaviorHints']:
                        size = file['behaviorHints']['videoSize'] / (1024 * 1024)  # Convert bytes to MB
                        logger.log('AioStreams: Using behaviorHints size: %s MB' % size, log_utils.LOGDEBUG)
                    # Method 2: streamData.size (fallback)
                    elif 'streamData' in file and 'size' in file['streamData']:
                        size = file['streamData']['size'] / (1024 * 1024)  # Convert bytes to MB
                        logger.log('AioStreams: Using streamData size: %s MB' % size, log_utils.LOGDEBUG)
                    # Method 3: parse from description (legacy)
                    else:
                        size_line = next((line for line in name.split('\n') if '💾' in line), '')
                        size_match = re.search(r'💾\s*([\d.]+)\s*(GiB|MiB|GB|MB)', size_line)
                        if size_match:
                            size_value = float(size_match.group(1))
                            size_unit = size_match.group(2)
                            if size_unit in ['GiB', 'GB']:
                                size = size_value * 1024  # Convert GB to MB
                            else:
                                size = size_value  # MB
                            logger.log('AioStreams: Parsed size from description: %s MB' % size, log_utils.LOGDEBUG)

                    # Create informative label
                    label_parts = [name_part]
                    if size > 0:
                        if size >= 1024:  # Show in GB if > 1GB
                            label_parts.append(f"{size/1024:.1f}GB")
                        else:
                            label_parts.append(f"{size:.1f}MB")
                    label = " | ".join(label_parts)
                    
                    source_item = {
                        'class': self,
                        'host': 'magnet',
                        'label': label,
                        'multi-part': False,
                        'hash': hash,
                        'name': name_part,
                        'quality': quality,
                        'size': size,
                        'language': 'en',
                        'url': url,
                        'direct': False,
                        'debridonly': True
                    }
                    
                    sources.append(source_item)
                    logger.log('AioStreams: Added source: %s' % source_item, log_utils.LOGDEBUG)
                    
                except Exception as e:
                    logger.log('AioStreams: Error processing source: %s' % str(e), log_utils.LOGERROR)
                    continue

        except Exception as e:
            logger.log('AioStreams: Unexpected error in get_sources: %s' % str(e), log_utils.LOGERROR)

        logger.log('AioStreams: Returning %d sources' % len(sources), log_utils.LOGDEBUG)
        return sources

    def search(self, video_type, title, year, season=''):
        """
        Search method implementation for AioStreams scraper.
        AioStreams requires IMDB IDs, so search functionality is limited.
        """
        logger.log('AioStreams: Search not implemented - requires IMDB ID', log_utils.LOGDEBUG)
        return []

    def _http_get(self, url, data=None, retry=True, allow_redirect=True, cache_limit=8, require_debrid=True):
        if require_debrid:
            if Scraper.debrid_resolvers is None:
                # Use resolveurl.relevant_resolvers() instead of choose_source()
                Scraper.debrid_resolvers = [resolver for resolver in resolveurl.relevant_resolvers() if resolver.isUniversal()]
            if not Scraper.debrid_resolvers:
                logger.log('%s requires debrid: %s' % (self.__module__, Scraper.debrid_resolvers), log_utils.LOGDEBUG)
                return ''
        
        try:
            # Use the parent class's cached HTTP get method for consistency and caching
            headers = {'User-Agent': scraper_utils.get_ua()}
            
            return self._cached_http_get(url, self.base_url, self.timeout, 
                                       data=data, headers=headers, 
                                       allow_redirect=allow_redirect, 
                                       cache_limit=cache_limit)
            
        except Exception as e:
            logger.log('AioStreams: HTTP request error for %s: %s' % (url, str(e)), log_utils.LOGWARNING)
            return ''

