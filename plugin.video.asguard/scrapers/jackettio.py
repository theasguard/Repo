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
    base_url = 'https://jackettio.elfhosted.com'
    movie_search_url = 'eyJtYXhUb3JyZW50cyI6MzAsInByaW90aXplUGFja1RvcnJlbnRzIjoyLCJleGNsdWRlS2V5d29yZHMiOltdLCJkZWJyaWRJZCI6InRvcmJveCIsImhpZGVVbmNhY2hlZCI6ZmFsc2UsInNvcnRDYWNoZWQiOltbInF1YWxpdHkiLHRydWVdLFsic2l6ZSIsdHJ1ZV1dLCJzb3J0VW5jYWNoZWQiOltbInNlZWRlcnMiLHRydWVdXSwiZm9yY2VDYWNoZU5leHRFcGlzb2RlIjpmYWxzZSwicHJpb3RpemVMYW5ndWFnZXMiOltdLCJpbmRleGVyVGltZW91dFNlYyI6NjAsIm1ldGFMYW5ndWFnZSI6IiIsImVuYWJsZU1lZGlhRmxvdyI6ZmFsc2UsIm1lZGlhZmxvd1Byb3h5VXJsIjoiIiwibWVkaWFmbG93QXBpUGFzc3dvcmQiOiIiLCJtZWRpYWZsb3dQdWJsaWNJcCI6IiIsInVzZVN0cmVtVGhydSI6dHJ1ZSwic3RyZW10aHJ1VXJsIjoiaHR0cDovL2VsZmhvc3RlZC1pbnRlcm5hbC5zdHJlbXRocnUiLCJxdWFsaXRpZXMiOlswLDcyMCwxMDgwLDIxNjBdLCJpbmRleGVycyI6WyJlenR2IiwidGhlcGlyYXRlYmF5IiwidGhlcmFyYmciLCJ5dHMiXSwiZGVicmlkQXBpS2V5IjoiZTgwMGVlMmItZDJkZi00NDA2LTk5NjEtYTY3YTI0YzVjNDBlIn0=/stream/movie/%s.json'
    tv_search_url = 'eyJtYXhUb3JyZW50cyI6MzAsInByaW90aXplUGFja1RvcnJlbnRzIjoyLCJleGNsdWRlS2V5d29yZHMiOltdLCJkZWJyaWRJZCI6InRvcmJveCIsImhpZGVVbmNhY2hlZCI6ZmFsc2UsInNvcnRDYWNoZWQiOltbInF1YWxpdHkiLHRydWVdLFsic2l6ZSIsdHJ1ZV1dLCJzb3J0VW5jYWNoZWQiOltbInNlZWRlcnMiLHRydWVdXSwiZm9yY2VDYWNoZU5leHRFcGlzb2RlIjpmYWxzZSwicHJpb3RpemVMYW5ndWFnZXMiOltdLCJpbmRleGVyVGltZW91dFNlYyI6NjAsIm1ldGFMYW5ndWFnZSI6IiIsImVuYWJsZU1lZGlhRmxvdyI6ZmFsc2UsIm1lZGlhZmxvd1Byb3h5VXJsIjoiIiwibWVkaWFmbG93QXBpUGFzc3dvcmQiOiIiLCJtZWRpYWZsb3dQdWJsaWNJcCI6IiIsInVzZVN0cmVtVGhydSI6dHJ1ZSwic3RyZW10aHJ1VXJsIjoiaHR0cDovL2VsZmhvc3RlZC1pbnRlcm5hbC5zdHJlbXRocnUiLCJxdWFsaXRpZXMiOlswLDcyMCwxMDgwLDIxNjBdLCJpbmRleGVycyI6WyJlenR2IiwidGhlcGlyYXRlYmF5IiwidGhlcmFyYmciLCJ5dHMiXSwiZGVicmlkQXBpS2V5IjoiZTgwMGVlMmItZDJkZi00NDA2LTk5NjEtYTY3YTI0YzVjNDBlIn0=/stream/series/%s:%s:%s.json'
    debrid_resolvers = resolveurl

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.bypass_filter = control.getSetting('Jackettio-bypass_filter') == 'true'
        self._set_apikeys()

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Jackettio'
    
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
                logger.log('Jackettio: No IMDB ID found for trakt_id: %s' % video.trakt_id, log_utils.LOGWARNING)
                return sources

            if video.video_type == VIDEO_TYPES.MOVIE:
                search_url = self.movie_search_url % imdb_id
                logger.log('Jackettio: Searching for movie: %s' % imdb_id, log_utils.LOGDEBUG)
            else:
                search_url = self.tv_search_url % (imdb_id, video.season, video.episode)
                logger.log('Jackettio: Searching for episode: %s S%sE%s' % (imdb_id, video.season, video.episode), log_utils.LOGDEBUG)

            url = urllib.parse.urljoin(self.base_url, search_url)
            response = self._http_get(url, cache_limit=1, require_debrid=True)
            if not response or response == FORCE_NO_MATCH:
                logger.log('Jackettio: No response from server', log_utils.LOGWARNING)
                return sources

            try:
                files = json.loads(response).get('streams', [])
                logger.log('Jackettio: Found %d files' % len(files), log_utils.LOGDEBUG)
            except json.JSONDecodeError as e:
                logger.log('Jackettio: Failed to parse JSON response: %s' % str(e), log_utils.LOGERROR)
                return sources

            for file in files:
                try:
                    file_url = file.get('url', '')
                    if not file_url:
                        continue
                        
                    logger.log('Jackettio: Found file: %s' % file_url, log_utils.LOGDEBUG)
                    name = file.get('title', 'Unknown')
                    
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
                    label = '%s | %sMB' % (name, size) if size > 0 else name
                    
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
                    logger.log('Jackettio: Found source: %s [%s]' % (name, source_info), log_utils.LOGDEBUG)
                    
                except Exception as e:
                    logger.log('Jackettio: Error processing source: %s' % str(e), log_utils.LOGWARNING)
                    continue

        except Exception as e:
            logger.log('Jackettio: Unexpected error in get_sources: %s' % str(e), log_utils.LOGERROR)

        logger.log('Jackettio: Returning %d sources' % len(sources), log_utils.LOGDEBUG)
        return sources


    def search(self, video_type, title, year, season=''):
        """
        Search method implementation for Jackettio scraper.
        Jackettio requires IMDB IDs, so search functionality is limited.
        """
        logger.log('Jackettio: Search not implemented - requires IMDB ID', log_utils.LOGDEBUG)
        return []

