"""
    Asguard Addon
    Copyright (C) 2017 Mr Blamo.Blamo

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
import datetime
import re
import xbmc
import urllib
import urlparse
import kodi
import log_utils  # @UnusedImport
import time
from asguard_lib import cfscrape
from asguard_lib import cloudflare
import json
import dom_parser2
from asguard_lib.utils2 import i18n
from asguard_lib import scraper_utils
from asguard_lib.constants import FORCE_NO_MATCH
from asguard_lib.constants import QUALITIES
from asguard_lib.constants import VIDEO_TYPES
import scraper

BASE_URL = 'https://cartoonhd.app'

class CartoonHD_Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting('%s-base_url' % (self.get_name()))

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.TVSHOW, VIDEO_TYPES.SEASON, VIDEO_TYPES.EPISODE, VIDEO_TYPES.MOVIE])

    @classmethod
    def get_name(cls):
        return 'CartoonHD'

    def resolve_link(self, link):
        return link

    def format_source_label(self, item):
        if 'resolution' in item:
            return '[%s] (%s) %s' % (item['quality'], item['resolution'], item['host'])
        else:
            return '[%s] %s' % (item['quality'], item['host'])

    def get_sources(self, video):
        source_url = self.get_url(video)
        sources = []
        if source_url:
            url = urlparse.urljoin(self.base_url, source_url)
            html = self._http_get(url, cache_limit=.5)

            gv_qualities = re.findall('googlevideo.com\s*-\s*(\d+)p', html)
            
            pattern = '<IFRAME\s+SRC="([^"]+)'
            gv_index = 0
            for match in re.finditer(pattern, html, re.DOTALL | re.I):
                url = match.group(1)
                host = urlparse.urlsplit(url).hostname.lower()
                resolution = None
                if 'googlevideo' in host:
                    direct = True
                    host = 'CartoonHD'
                    if gv_index < len(gv_qualities):
                        resolution = gv_qualities[gv_index]
                        quality = self._height_get_quality(resolution)
                    else:
                        quality = QUALITIES.HIGH
                    gv_index += 1
                else:
                    direct = False
                    quality = QUALITIES.HIGH

                source = {'multi-part': False, 'url': url, 'host': host, 'class': self, 'quality': self._get_quality(video, host, quality), 'views': None, 'rating': None, 'direct': direct}
                if resolution is not None: source['resolution'] = '%sp' % (resolution)
                sources.append(source)

        return sources

    def get_url(self, video):
        return super(CartoonHD_Scraper, self)._default_get_url(video)

    def search(self, video_type, title, year):
        results = []
        html = self. _http_get(self.base_url, cache_limit=0)
        match = re.search("var\s+token\s*=\s*'([^']+)", html)
        if match:
            token = match.group(1)
            
            search_url = urlparse.urljoin(self.base_url, '/ajax/search.php?q=')
            search_url += urllib.quote_plus(title)
            timestamp = int(time.time() * 1000)
            query = {'q': title, 'limit': '100', 'timestamp': timestamp, 'verifiedCheck': token}
            html = self._http_get(search_url, data=query, cache_limit=.25)
            if video_type in [VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE]:
                media_type = 'TV SHOW'
            else:
                media_type = 'MOVIE'

            if html:
                try:
                    js_data = json.loads(html)
                except ValueError:
                    log_utils.log('No JSON returned: %s: %s' % (search_url, html), xbmc.LOGWARNING)
                else:
                    for item in js_data:
                        if item['meta'].upper().startswith(media_type):
                            result = {'title': item['title'], 'url': item['permalink'].replace(self.base_url, ''), 'year': ''}
                            results.append(result)

        else:
            log_utils.log('Unable to locate CartoonHD token', xbmc.LOGWARNING)
        return results

    def _get_episode_url(self, show_url, video):
        episode_pattern = 'class="link"\s*href="([^"]+/season/%s/episode/%s/*)"' % (video.season, video.episode)
        return super(CartoonHD_Scraper, self)._default_get_episode_url(show_url, video, episode_pattern)

    def _http_get(self, url, data=None, cache_limit=8):
        return self._cached_http_get(url, self.base_url, self.timeout, data=data, cache_limit=cache_limit)