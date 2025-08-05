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
from asguard_lib.constants import FORCE_NO_MATCH, VIDEO_TYPES, QUALITIES
from . import scraper


try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)
    
logger = log_utils.Logger.get_logger()

class Scraper(scraper.Scraper):
    base_url = 'https://comet.elfhosted.com'
    movie_search_url = '/eyJtYXhSZXN1bHRzUGVyUmVzb2x1dGlvbiI6MCwibWF4U2l6ZSI6MCwiY2FjaGVkT25seSI6ZmFsc2UsInJlbW92ZVRyYXNoIjp0cnVlLCJyZXN1bHRGb3JtYXQiOlsiYWxsIl0sImRlYnJpZFNlcnZpY2UiOiJ0b3Jib3giLCJkZWJyaWRBcGlLZXkiOiJlODAwZWUyYi1kMmRmLTQ0MDYtOTk2MS1hNjdhMjRjNWM0MGUiLCJkZWJyaWRTdHJlYW1Qcm94eVBhc3N3b3JkIjoiIiwibGFuZ3VhZ2VzIjp7InJlcXVpcmVkIjpbXSwiZXhjbHVkZSI6W10sInByZWZlcnJlZCI6W119LCJyZXNvbHV0aW9ucyI6e30sIm9wdGlvbnMiOnsicmVtb3ZlX3JhbmtzX3VuZGVyIjotMTAwMDAwMDAwMDAsImFsbG93X2VuZ2xpc2hfaW5fbGFuZ3VhZ2VzIjpmYWxzZSwicmVtb3ZlX3Vua25vd25fbGFuZ3VhZ2VzIjpmYWxzZX19/stream/movie/%s.json'
    tv_search_url = '/eyJtYXhSZXN1bHRzUGVyUmVzb2x1dGlvbiI6MCwibWF4U2l6ZSI6MCwiY2FjaGVkT25seSI6ZmFsc2UsInJlbW92ZVRyYXNoIjp0cnVlLCJyZXN1bHRGb3JtYXQiOlsiYWxsIl0sImRlYnJpZFNlcnZpY2UiOiJ0b3Jib3giLCJkZWJyaWRBcGlLZXkiOiJlODAwZWUyYi1kMmRmLTQ0MDYtOTk2MS1hNjdhMjRjNWM0MGUiLCJkZWJyaWRTdHJlYW1Qcm94eVBhc3N3b3JkIjoiIiwibGFuZ3VhZ2VzIjp7InJlcXVpcmVkIjpbXSwiZXhjbHVkZSI6W10sInByZWZlcnJlZCI6W119LCJyZXNvbHV0aW9ucyI6e30sIm9wdGlvbnMiOnsicmVtb3ZlX3JhbmtzX3VuZGVyIjotMTAwMDAwMDAwMDAsImFsbG93X2VuZ2xpc2hfaW5fbGFuZ3VhZ2VzIjpmYWxzZSwicmVtb3ZlX3Vua25vd25fbGFuZ3VhZ2VzIjpmYWxzZX19/stream/series/%s:%s:%s.json'
    debrid_resolvers = resolveurl

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.bypass_filter = control.getSetting('Comet-bypass_filter') == 'true'
        self._set_apikeys()

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Comet'
    
    def resolve_link(self, link):
        logging.debug("Resolving link: %s", link)
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
                logger.log('Comet: No IMDB ID found for trakt_id: %s' % video.trakt_id, log_utils.LOGWARNING)
                return sources

            if video.video_type == VIDEO_TYPES.MOVIE:
                search_url = self.movie_search_url % imdb_id
                logger.log('Comet: Searching for movie: %s' % imdb_id, log_utils.LOGDEBUG)
            else:
                search_url = self.tv_search_url % (imdb_id, video.season, video.episode)
                logger.log('Comet: Searching for episode: %s S%sE%s' % (imdb_id, video.season, video.episode), log_utils.LOGDEBUG)

            url = urllib.parse.urljoin(self.base_url, search_url)
            response = self._http_get(url, cache_limit=1, require_debrid=True)
            if not response or response == FORCE_NO_MATCH:
                logger.log('Comet: No response from server', log_utils.LOGWARNING)
                return sources

            try:
                files = json.loads(response).get('streams', [])
                logger.log('Comet: Found %d files' % len(files), log_utils.LOGDEBUG)
            except json.JSONDecodeError as e:
                logger.log('Comet: Failed to parse JSON response: %s' % str(e), log_utils.LOGERROR)
                return sources

            for file in files:
                try:
                    file_url = file.get('url', '')
                    if not file_url:
                        continue
                        
                    logger.log('Comet: Found file: %s' % file_url, log_utils.LOGDEBUG)
                    name = file.get('description', 'Unknown')
                    
                    # Extract quality
                    quality = scraper_utils.get_tor_quality(name)
                    
                    # Extract size information
                    info = []
                    size_match = re.search(r'💾\s*([\d.]+)\s*(GB|MB)', name)
                    size = 0
                    if size_match:
                        size_value = float(size_match.group(1))
                        size_unit = size_match.group(2)
                        if size_unit == 'GB':
                            size = size_value * 1024  # Convert GB to MB
                        else:
                            size = size_value
                        info.append('%s%s' % (size_value, size_unit))

                    source_info = ' | '.join(info)
                    label = '%s | %s | %sMB' % (name, quality, size) if size > 0 else '%s | %s' % (name, quality)
                    
                    source = {
                        'class': self,
                        'host': 'magnet',
                        'label': label,
                        'multi-part': False,
                        'name': name,
                        'quality': quality,
                        'size': size,
                        'language': 'en',
                        'url': file_url,
                        'info': source_info,
                        'direct': False,
                        'debridonly': True
                    }
                    
                    sources.append(source)
                    logger.log('Comet: Found source: %s [%s]' % (name, source_info), log_utils.LOGDEBUG)
                    
                except Exception as e:
                    logger.log('Comet: Error processing source: %s' % str(e), log_utils.LOGWARNING)
                    continue

        except Exception as e:
            logger.log('Comet: Unexpected error in get_sources: %s' % str(e), log_utils.LOGERROR)

        logger.log('Comet: Returning %d sources' % len(sources), log_utils.LOGDEBUG)
        return sources



    def search(self, video_type, title, year, season=''):
        """
        Search method implementation for Comet scraper.
        Comet requires IMDB IDs, so search functionality is limited.
        """
        logger.log('Comet: Search not implemented - requires IMDB ID', log_utils.LOGDEBUG)
        return []
