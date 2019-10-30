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
import dom_parser
import dom_parser2
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
        self.goog = 'https://www.google.co.uk'

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
        search_url = urlparse.urljoin(self.base_url, '/?s=')
        search_url += urllib.quote(title)
        if video_type == VIDEO_TYPES.EPISODE:
            search_url += '&cat=TV-XviD,TV-Mp4,TV-720p,TV-480p,'
        else:
            search_url += '&cat=Movies-XviD,Movies-720,Movies-480p'
        html = self._http_get(search_url, cache_limit=.25)
        fragment = dom_parser2.parse_dom(html, 'ul', {'class': 'cbp-rfgrid'})
        if not fragment: return results
        
        for item in dom_parser2.parse_dom(fragment, 'li'):
            match = dom_parser2.parse_dom(item, 'a', req=['title', 'href'])
            if not match: continue
            
            match_url = match[0].attrs['href']
            match_title_year = match[0].attrs['title']
            match_title, match_year = scraper_utils.extra_year(match_title_year)
            if not year or not match_year or year == match_year:
                result = {'url': scraper_utils.pathify_url(match_url), 'title': scraper_utils.cleanse_title(match_title), 'year': match_year}
                results.append(result)

        return results

        # tables = dom_parser.parse_dom(html, 'table', {'class': 'posts_table'})
        # if tables:
            # del tables[0]
            # html = ''.join(self.base_url)
            # pattern = "<a[^>]+>(?P<quality>[^<]+).*?href='(?P<url>[^']+)'>(?P<post_title>[^<]+).*?(?P<date>[^>]+)</td></tr>"
            # date_format = '%Y-%m-%d %H:%M:%S'
            # return self._blog_proc_results(html, pattern, date_format, video_type, title, year)
        # else:
            # return []

    def _http_get(self, url, cache_limit=8):
        return super(cls, self)._cached_http_get(url, self.base_url, self.timeout, cache_limit=cache_limit)