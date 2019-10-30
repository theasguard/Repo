"""
    Asguard Addon
    Copyright (C) 2017 Mr Blamo

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
import urllib
import urlparse
import kodi
import log_utils  # @UnusedImport
import dom_parser
from asguard_lib import scraper_utils
from asguard_lib.constants import FORCE_NO_MATCH
from asguard_lib.constants import QUALITIES
from asguard_lib.constants import VIDEO_TYPES
from asguard_lib.utils2 import i18n
import scraper

BASE_URL = 'http://hdflix.net/'
SEARCH_URL = '/newmov.php?menu=%s&query=%s'
XHR = {'X-Requested-With': 'XMLHttpRequest'}

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting('%s-base_url' % (self.get_name()))
        self.username = kodi.get_setting('%s-username' % (self.get_name()))
        self.password = kodi.get_setting('%s-password' % (self.get_name()))

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'HDFlix'

    def get_sources(self, video):
        source_url = self.get_url(video)
        hosters = []
        if source_url and source_url != FORCE_NO_MATCH:
            page_url = urlparse.urljoin(self.base_url, source_url)
            html = self._http_get(page_url, cache_limit=.5)
            hosters += self.__add_sources(dom_parser.parse_dom(html, 'a', {'rel': 'nofollow'}, ret='href'), video)
            
            sources = []
            for match in re.finditer('''\$\.get\('([^']+)'\s*,\s*(\{.*?\})''', html):
                ajax_url, params = match.groups()
                ajax_url = ajax_url + '?' + urllib.urlencode(scraper_utils.parse_params(params))
                ajax_url = urlparse.urljoin(self.base_url, ajax_url)
                headers = {'Referer': page_url}
                headers.update(XHR)
                html = self._http_get(ajax_url, headers=headers, auth=False, cache_limit=.5)
                sources += dom_parser.parse_dom(html, 'source', {'type': '''video[^'"]*'''}, ret='src')
                sources += dom_parser.parse_dom(html, 'iframe', ret='src')
            hosters += self.__add_sources(sources, video, QUALITIES.HD720)
        return hosters

    def __add_sources(self, sources, video, quality=QUALITIES.HIGH):
        hosters = []
        for source in sources:
            if self._get_direct_hostname(source) == 'gvideo':
                host = self._get_direct_hostname(source)
                quality = scraper_utils.gv_get_quality(source)
                stream_url = source + '|User-Agent=%s' % (scraper_utils.get_ua())
                direct = True
            else:
                host = urlparse.urlparse(source).hostname
                quality = scraper_utils.get_quality(video, host, quality)
                stream_url = source
                direct = False
            
            hoster = {'multi-part': False, 'host': host, 'class': self, 'quality': quality, 'views': None, 'rating': None, 'url': stream_url, 'direct': direct}
            hosters.append(hoster)
        return hosters
        
    def _get_episode_url(self, season_url, video):
        episode_pattern = 'href="([^"]*/season/0*%s/episode/0*%s(?!\d)[^"]*)' % (video.season, video.episode)
        title_pattern = 'href="(?P<url>[^"]+)">\s*Episode.*?class="tv_episode_name"[^>]*>\s*(?P<title>[^<]+)'
        return self._default_get_episode_url(season_url, video, episode_pattern, title_pattern)
    
    def search(self, video_type, title, year, season=''):
        results = []
        search_url = urlparse.urljoin(self.base_url, SEARCH_URL)
        if video_type == VIDEO_TYPES.MOVIE:
            search = 'search'
        else:
            search = 'searchshow'
        search_url = search_url % (search, urllib.quote(title))
        html = self._http_get(search_url, cache_limit=8)
        for item in dom_parser.parse_dom(html, 'div', {'class': 'movie'}):
            match_url = dom_parser.parse_dom(item, 'a', {'class': 'poster'}, ret='href')
            match_title = dom_parser.parse_dom(item, 'div', {'class': 'title'})
            match_year = dom_parser.parse_dom(item, 'div', {'class': 'year'})
            if match_url and match_title:
                match_url = match_url[0]
                match_title = match_title[0]
                match_year = match_year[0] if match_year else ''
                if match_title and (not year or not match_year or year == match_year):
                    result = {'title': scraper_utils.cleanse_title(match_title), 'year': match_year, 'url': scraper_utils.pathify_url(match_url)}
                    results.append(result)
        return results

    @classmethod
    def get_settings(cls):
        settings = super(cls, cls).get_settings()
        name = cls.get_name()
        settings.append('         <setting id="%s-username" type="text" label="     %s" default="" visible="eq(-4,true)"/>' % (name, i18n('username')))
        settings.append('         <setting id="%s-password" type="text" label="     %s" option="hidden" default="" visible="eq(-5,true)"/>' % (name, i18n('password')))
        return settings

    def _http_get(self, url, data=None, headers=None, auth=True, method=None, cache_limit=8):
        # return all uncached blank pages if no user or pass
        if not self.username or not self.password:
            return ''

        html = super(self.__class__, self)._http_get(url, data=data, headers=headers, method=method, cache_limit=cache_limit)
        if auth and not dom_parser.parse_dom(html, 'a', {'title': 'My Account'}, ret='href'):
            log_utils.log('Logging in for url (%s)' % (url), log_utils.LOGDEBUG)
            self.__login()
            html = super(self.__class__, self)._http_get(url, data=data, headers=headers, method=method, cache_limit=0)

        return html

    def __login(self):
        url = urlparse.urljoin(self.base_url, '/login')
        data = {'username': self.username, 'password': self.password, 'action': 'login'}
        html = super(self.__class__, self)._http_get(url, data=data, cache_limit=0)
        match = re.search('''window\.location=['"]([^"']+)''', html)
        if match:
            url = urlparse.urljoin(self.base_url, match.group(1))
            html = super(self.__class__, self)._http_get(url, cache_limit=0)
            if not dom_parser.parse_dom(html, 'a', {'title': 'My Account'}, ret='href'):
                raise Exception('hdflix login failed')
