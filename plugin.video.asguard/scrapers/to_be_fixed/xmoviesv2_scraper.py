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
import time
import kodi
import log_utils
import dom_parser
from asguard_lib import cloudflare
from asguard_lib import scraper_utils
from asguard_lib.constants import FORCE_NO_MATCH
from asguard_lib.constants import VIDEO_TYPES
from asguard_lib.constants import QUALITIES
from asguard_lib.constants import Q_ORDER
from asguard_lib.constants import XHR
import scraper

BASE_URL = 'https://xmovies8.cool'
PLAYER_URL = '/ajax/movie/load_player_v2'
EPISODES_URL = '/ajax/movie/load_episodes'

class Scraper(scraper.Scraper):
    base_url = BASE_URL
    
    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting('%s-base_url' % (self.get_name()))

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.SEASON, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'xmoviesv3'

    def get_sources(self, video):
        source_url = self.get_url(video)
        hosters = []
        sources = {}
        if source_url and source_url != FORCE_NO_MATCH:
            page_url = urlparse.urljoin(self.base_url, source_url)
            html = self._http_get(page_url, cache_limit=.5)
        
            headers = {'Referer': page_url, 'Server': 'cloudflare-nginx', 'Accept': 'text/html, */*; q=0.01',
                       'Accept-Language': 'en-US,en;q=0.5', 'Accept-Formating': 'application/json, text/javascript', 'Accept-Encoding': 'gzip, deflate'}
            headers.update(XHR)
            html = self.__get_players(html, page_url)
            players = list(set(re.findall("load_player\(\s*'([^']+)'\s*,\s*'?(\d+)\s*'?", html)))
            player_url = urlparse.urljoin(self.base_url, PLAYER_URL)
            for link_id, height in players:
                params = {'id': link_id, 'quality': height, '_': int(time.time() * 1000)}
                player_url2 = player_url + '?' + urllib.urlencode(params)
                headers = {'Referer': page_url, 'Accept-Encoding': 'gzip, deflate', 'Server': 'cloudflare-nginx', 'Accept-Formating': 'application/json, text/javascript'}
                headers.update(XHR)
                html = self._http_get(player_url2, headers=headers, cache_limit=0)
                js_data = scraper_utils.parse_json(html, player_url)
                if 'link' in js_data and js_data['link']:
                    link_url = js_data['link']
                    if 'player_v2.php' in link_url:
                        headers = {'Referer': page_url}
                        html = self._http_get(link_url, headers=headers, allow_redirect=False, method='HEAD', cache_limit=.25)
                        if html.startswith('http'):
                            if self._get_direct_hostname(html) == 'gvideo':
                                quality = scraper_utils.gv_get_quality(html)
                                sources[html] = {'quality': quality, 'direct': True}
                            else:
                                if height != '0':
                                    quality = scraper_utils.height_get_quality(height)
                                else:
                                    quality = QUALITIES.HIGH
                                sources[html] = {'quality': quality, 'direct': False}
                            if not kodi.get_setting('scraper_url') and Q_ORDER[quality] >= Q_ORDER[QUALITIES.HD720]: break
                    
            for source in sources:
                direct = sources[source]['direct']
                quality = sources[source]['quality']
                if direct:
                    host = self._get_direct_hostname(source)
                else:
                    host = urlparse.urlparse(source).hostname
                stream_url = source + '|User-Agent=%s' % (scraper_utils.get_ua())
                hoster = {'multi-part': False, 'host': host, 'class': self, 'quality': quality, 'views': None, 'rating': None, 'url': stream_url, 'direct': direct}
                hosters.append(hoster)
            
        return hosters

    def __get_players(self, html, page_url):
        url = urlparse.urljoin(self.base_url, EPISODES_URL)
        match = re.search("data\s*:\s*{\s*id:\s*(\d+),\s*episode_id:\s*(\d+),\s*link_id:\s*(\d+),\s*from:\s*'([^']+)", html)
        if match:
            show_id, ep_id, link_id, from_id = match.groups()
            data = {'id': show_id, 'episode_id': ep_id, 'link_id': link_id, 'from': from_id}
            headers = {'Referer': page_url, 'Accept-Formating': 'application/json, text/javascript', 'Server': 'cloudflare-nginx'}
            headers.update(XHR)
            html = self._http_get(url, data=data, headers=headers, cache_limit=1)
        return html
    
    def _get_episode_url(self, season_url, video):
        season_url = urlparse.urljoin(self.base_url, season_url)
        html = self._http_get(season_url, cache_limit=.5)
        html = self.__get_players(html, season_url)
        episode_pattern = 'href="([^"]+)[^>]+class="[^"]*btn-episode[^>]*>%s<' % (video.episode)
        match = re.search(episode_pattern, html)
        if match:
            return scraper_utils.pathify_url(match.group(1))

    def search(self, video_type, title, year, season=''):
        results = []
        search_url = urlparse.urljoin(self.base_url, '/search/%s' % urllib.quote_plus(title))
        html = self._http_get(search_url, cache_limit=8)
        for item in dom_parser.parse_dom(html, 'div', {'class': '[^"]*c-content-product-2[^"]*'}):
            match_title_year = dom_parser.parse_dom(item, 'p', {'class': '[^"]*c-title[^"]*'})
            match_url = dom_parser.parse_dom(item, 'a', ret='href')
            is_season = dom_parser.parse_dom(item, 'div', {'class': '[^"]*c-bg-red[^'"]*"})
            if match_title_year and match_url:
                match_title_year = match_title_year[0]
                match_url = match_url[0]
                if (video_type == VIDEO_TYPES.MOVIE and not is_season) or (video_type == VIDEO_TYPES.SEASON and is_season):
                    match_year = ''
                    if video_type == VIDEO_TYPES.SEASON:
                        match_title = match_title_year
                        if season and not re.search('Season\s+(%s)\s+' % (season), match_title_year, re.I):
                            continue
                    else:
                        match = re.search('(.*?)\s+(\d{4})$', match_title_year)
                        if match:
                            match_title, match_year = match.groups()
                        else:
                            match_title = match_title_year
                            match_year = ''
        
                    match_url = urlparse.urljoin(match_url, 'watching.html')
                    if not year or not match_year or year == match_year:
                        result = {'url': scraper_utils.pathify_url(match_url), 'title': scraper_utils.cleanse_title(match_title), 'year': match_year}
                        results.append(result)
        return results
