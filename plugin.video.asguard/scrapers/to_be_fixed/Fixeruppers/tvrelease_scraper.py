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
import urllib
import urlparse
import kodi
import log_utils  # @UnusedImport
import requests
import dom_parser
import dom_parser2
from asguard_lib import cfscrape
from asguard_lib.utils2 import i18n
from asguard_lib import scraper_utils
from asguard_lib.constants import FORCE_NO_MATCH
from asguard_lib.constants import QUALITIES
from asguard_lib.constants import VIDEO_TYPES
import scraper

logger = log_utils.Logger.get_logger()

BASE_URL = 'http://tv-release.pw'
QUALITY_MAP = {'SD-XVID': QUALITIES.MEDIUM, 'DVD9': QUALITIES.HIGH, 'SD-X264': QUALITIES.HIGH,
               'HD-720P': QUALITIES.HD720, 'HD-1080P': QUALITIES.HD1080, '720P': QUALITIES.HD720, 'XVID': QUALITIES.MEDIUM,
               'X264': QUALITIES.HIGH, '1080P': QUALITIES.HD1080}

class TVReleaseNet_Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting('%s-base_url' % (self.get_name()))
        self.search_link = '/?s='

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'TVRelease'

    def resolve_link(self, link):
        return link

    def format_source_label(self, item):
        return '[%s] %s' % (item['quality'], item['host'])

    def get_sources(self, video):
        scraper = cfscrape.create_scraper()
        source_url = self.get_url(video)
        hosters = []
        if source_url and source_url != FORCE_NO_MATCH:
            url = urlparse.urljoin(self.base_url, source_url)
            html = self._http_get(url, cache_limit=.5)

            q_str = ''
            quality = None
            match = re.search('>Category.*?td_col">([^<]+)', html)
            if match:
                quality = QUALITY_MAP.get(match.group(1).upper(), None)
            else:
                match = re.search('>Release.*?td_col">([^<]+)', html)
                if match:
                    q_str = match.group(1).upper()
                
            pattern = "td_cols.+?href='(.+?)"
            for match in re.finditer(pattern, html):
                url = match.group(1)
                if re.search('\.rar(\.|$)', url):
                    continue

                hoster = {'multi-part': False, 'class': self, 'views': None, 'url': url, 'rating': None, 'direct': False}
                hoster['host'] = urlparse.urlsplit(url).hostname
                if quality is None:
                    hoster['quality'] = scraper_utils.blog_get_quality(video, q_str, hoster['host'])
                else:
                    hoster['quality'] = scraper_utils.get_quality(video, hoster['host'], quality)
                hosters.append(hoster)

        return hosters

    def get_url(self, video):
        return self._blog_get_url(video, delim=' ')

    @classmethod
    def get_settings(cls):
        settings = super(cls, cls).get_settings()
        settings = scraper_utils.disable_sub_check(settings)
        name = cls.get_name()
        settings.append('         <setting id="%s-filter" type="slider" range="0,180" option="int" label="     %s" default="30" visible="eq(-4,true)"/>' % (name, i18n('filter_results_days')))
        settings.append('         <setting id="%s-select" type="enum" label="     %s" lvalues="30636|30637" default="0" visible="eq(-5,true)"/>' % (name, i18n('auto_select')))
        return settings

    def search(self, video_type, title, year, season=''):
        scrape = title.lower().replace(' ','+').replace(':', '')
        search_url = urlparse.urljoin(self.base_url, '?s=%s')
        search_url += urllib.quote(title)
        if video_type == VIDEO_TYPES.EPISODE:
            search_url += '&cat=TV-XviD,TV-Mp4,TV-720p,TV-480p,'
        else:
            search_url += '&cat=Movies-XviD,Movies-720,Movies-480p'
        html = requests.get(search_url)
        tables = dom_parser.parse_dom(html, 'table', {'class': 'posts_table'})
        if tables:
            html = ''.join(tables)
            pattern = "<a[^>]+>(?P<quality>[^<]+).*?href='(?P<url>[^']+)'>(?P<post_title>[^<]+).*?(?P<date>[^>]+)</td></tr>"
            date_format = '%Y-%m-%d %H:%M:%S'
            return self._blog_proc_results(html, pattern, date_format, video_type, title, year)
        else:
            return []
