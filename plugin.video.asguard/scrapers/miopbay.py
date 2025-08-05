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
import requests
from asguard_lib.utils2 import i18n
import xbmcgui
import kodi
import log_utils
from asguard_lib import scraper_utils, control
from asguard_lib.constants import VIDEO_TYPES, QUALITIES
from . import scraper


try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)
    
logger = log_utils.Logger.get_logger()

class Scraper(scraper.Scraper):
    base_url = 'https://thepiratebay-plus.strem.fun'
    movie_search_url = '/stream/movie/%s.json'
    tv_search_url = '/stream/series/%s:%s:%s.json'
    debrid_resolvers = resolveurl

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.min_seeders = 0
        self.bypass_filter = control.getSetting('Thepiratebay-bypass_filter') == 'true'
        self._set_apikeys()

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Thepiratebay'
    
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
                logger.log('Thepiratebay: No IMDB ID found for trakt_id: %s' % video.trakt_id, log_utils.LOGWARNING)
                return sources

            if video.video_type == VIDEO_TYPES.MOVIE:
                search_url = self.movie_search_url % imdb_id
                logger.log('Thepiratebay: Searching for movie: %s' % search_url, log_utils.LOGDEBUG)
            elif video.video_type == VIDEO_TYPES.EPISODE:
                search_url = self.tv_search_url % (imdb_id, video.season, video.episode)
                logger.log('Thepiratebay: Searching for episode: %s' % search_url, log_utils.LOGDEBUG)
            else:
                logger.log('Thepiratebay: Unsupported video type: %s' % video.video_type, log_utils.LOGWARNING)
                return sources

            url = urllib.parse.urljoin(self.base_url, search_url)
            response = self._http_get(url, cache_limit=1, require_debrid=True)
            logger.log('Thepiratebay Response: %s' % response, log_utils.LOGDEBUG)
            if not response:
                return sources

            try:
                files = json.loads(response).get('streams', [])
                logger.log('Thepiratebay: Found %d files' % len(files), log_utils.LOGDEBUG)
            except json.JSONDecodeError as e:
                logger.log('Thepiratebay: Failed to parse JSON response: %s' % str(e), log_utils.LOGERROR)
                return sources

            for file in files:
                try:
                    hash = file['infoHash']
                    logger.log('Thepiratebay: Found file hash: %s' % hash, log_utils.LOGDEBUG)
                    name = file['title']
                    
                    # Clean name for magnet URL
                    name_clean = urllib.parse.quote(name)
                    url = 'magnet:?xt=urn:btih:%s&dn=%s' % (hash, name_clean)
                    logger.log('Thepiratebay: Created magnet: %s' % url, log_utils.LOGDEBUG)
                    
                    seeders = int(file.get('seeds', 0))
                    if self.min_seeders > seeders:
                        continue

                    # Extract quality from filename
                    quality = scraper_utils.get_tor_quality(name)
                    
                    # Extract size information
                    size = 0
                    size_match = re.search(r'💾\s*([\d.]+)\s*(GB|MB)', name)
                    if size_match:
                        size_value = float(size_match.group(1))
                        size_unit = size_match.group(2)
                        if size_unit == 'GB':
                            size = size_value * 1024  # Convert GB to MB
                        else:
                            size = size_value

                    # Create informative label
                    label_parts = [name, quality]
                    if size > 0:
                        label_parts.append(f"{size:.1f}MB")
                    if seeders > 0:
                        label_parts.append(f"{seeders} seeders")
                    label = " | ".join(label_parts)
                    
                    source_item = {
                        'class': self,
                        'host': 'magnet',
                        'label': label,
                        'multi-part': False,
                        'seeders': seeders,
                        'hash': hash,
                        'name': name,
                        'quality': quality,
                        'size': size,
                        'language': 'en',
                        'url': url,
                        'direct': False,
                        'debridonly': True
                    }
                    
                    sources.append(source_item)
                    logger.log('Thepiratebay: Added source: %s' % source_item, log_utils.LOGDEBUG)
                    
                except Exception as e:
                    logger.log('Thepiratebay: Error processing source: %s' % str(e), log_utils.LOGERROR)
                    continue

        except Exception as e:
            logger.log('Thepiratebay: Unexpected error in get_sources: %s' % str(e), log_utils.LOGERROR)

        logger.log('Thepiratebay: Returning %d sources' % len(sources), log_utils.LOGDEBUG)
        return sources

    def search(self, video_type, title, year, season=''):
        """
        Search method implementation for Thepiratebay scraper.
        Thepiratebay requires IMDB IDs, so search functionality is limited.
        """
        logger.log('Thepiratebay: Search not implemented - requires IMDB ID', log_utils.LOGDEBUG)
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
            logger.log('Thepiratebay: HTTP request error for %s: %s' % (url, str(e)), log_utils.LOGWARNING)
            return ''
