"""
    SALTS XBMC Addon
    Copyright (C) 2014 tknorris

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
import kodi
import re
import urlparse
import urllib
import hashlib
import random
import string
import base64
import dom_parser
from asguard_lib import scraper_utils
from asguard_lib.constants import FORCE_NO_MATCH
from asguard_lib.constants import QUALITIES
from asguard_lib.constants import VIDEO_TYPES
import xml.etree.ElementTree as ET
import scraper

BASE_URL = 'https://yesmovies.ag'
QP_URL = '/ajax/v2_movie_quick_play/%s/%s/%s.html'
SL_URL = '/ajax/v3_movie_get_episodes/%s/%s/%s/%s.html'
PLAYLIST_URL1 = '/ajax/movie_load_embed/%s.html'
PLAYLIST_URL2 = '/ajax/v4_episode_get_sources/%s/%s.html'
PLAYLIST_URL3 = '/ajax/get_sources/%s/%s.html'
SEARCH_KEY = ''
XHR = {'X-Requested-With': 'XMLHttpRequest'}
COOKIE1 = base64.b64decode('eHdoMzhpZjM5dWN4')
COOKIE2 = base64.b64decode('OHFoZm05b3lxMXV4')
KEY = base64.b64decode('Y3RpdzR6bHJuMDl0YXU3a3F2YzE1M3Vv')

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
        return 'YesMovies'

    def get_sources(self, video):
        source_url = self.get_url(video)
        hosters = []
        if source_url and source_url != FORCE_NO_MATCH:
            links = []
            page_url = urlparse.urljoin(self.base_url, source_url)
            _movie_id, _sl_url, html = self.__get_source_page(video.video_type, source_url)
            
            for match in re.finditer('''load_episode\(\s*(\d+)\s*,\s*(\d+)(.*?)</a>''', html, re.DOTALL):
                param1, param2, fragment = match.groups()
                if video.video_type == VIDEO_TYPES.EPISODE:
                    match = re.search('title="([^"]+)', fragment)
                    if match:
                        if not self.__episode_match(video, match.group(1)):
                            continue
                    else:
                        continue
                links.append((param1, param2))
                
            for param1, param2 in links:
                if int(param1) < 100:
                    link_type = param1
                    link_id = param2
                else:
                    link_type = param2
                    link_id = param1
                    
                sources = []
                if link_type in ['12', '13', '14', '15']:
                    url = urlparse.urljoin(self.base_url, PLAYLIST_URL1 % (link_id))
                    sources = self.__get_link_from_json(url)
                elif kodi.get_setting('scraper_url'):
                    token = self.__get_token()
                    cookie = {'%s%s%s' % (COOKIE1, link_id, COOKIE2): token}
                    url_hash = hashlib.md5(link_id + token + KEY).hexdigest()
                    url = urlparse.urljoin(self.base_url, PLAYLIST_URL3 % (link_id, url_hash))
                    sources = self.__get_links_from_json2(url, page_url, cookie)
                    if not sources:
                        url = urlparse.urljoin(self.base_url, PLAYLIST_URL2 % (link_id, url_hash))
                        sources = self.__get_links_from_xml(url, video, page_url, cookie)
            
                for source in sources:
                    if not source.lower().startswith('http'): continue
                    if sources[source]['direct']:
                        host = self._get_direct_hostname(source)
                        if host != 'gvideo':
                            stream_url = source + '|User-Agent=%s&Referer=%s' % (scraper_utils.get_ua(), urllib.quote(page_url))
                        else:
                            stream_url = source
                    else:
                        host = urlparse.urlparse(source).hostname
                        stream_url = source
                    hoster = {'multi-part': False, 'host': host, 'class': self, 'quality': sources[source]['quality'], 'views': None, 'rating': None, 'url': stream_url, 'direct': sources[source]['direct']}
                    hosters.append(hoster)
                
        return hosters

    def __get_token(self):
        return ''.join(random.sample(string.digits + string.ascii_lowercase, 6))
    
    def __get_link_from_json(self, url):
        sources = {}
        html = self._http_get(url, cache_limit=.5)
        js_result = scraper_utils.parse_json(html, url)
        if 'embed_url' in js_result:
            sources[js_result['embed_url']] = {'quality': QUALITIES.HIGH, 'direct': False}
        return sources
    
    def __get_links_from_json2(self, url, page_url, cookies):
        sources = {}
        headers = {'Referer': page_url}
        html = self._http_get(url, cookies=cookies, headers=headers, cache_limit=.5)
        js_data = scraper_utils.parse_json(html, url)
        playlist = js_data.get('playlist', [])
        if playlist:
            for source in playlist[0].get('sources', []):
                stream_url = source['file']
                if self._get_direct_hostname(stream_url) == 'gvideo':
                    quality = scraper_utils.gv_get_quality(stream_url)
                else:
                    quality = scraper_utils.height_get_quality(source.get('label', ''))
                sources[stream_url] = {'quality': quality, 'direct': True}
                log_utils.log('Adding stream: %s Quality: %s' % (stream_url, quality), log_utils.LOGDEBUG)
        return sources
    
    def __get_links_from_xml(self, url, video, page_url, cookies):
        sources = {}
        try:
            headers = {'Referer': page_url}
            xml = self._http_get(url, cookies=cookies, headers=headers, cache_limit=.5)
            root = ET.fromstring(xml)
            for item in root.findall('.//item'):
                title = item.find('title').text
                if title and title.upper() == 'OOPS!': continue
                for source in item.findall('{http://rss.jwpcdn.com/}source'):
                    stream_url = source.get('file')
                    label = source.get('label')
                    if self._get_direct_hostname(stream_url) == 'gvideo':
                        quality = scraper_utils.gv_get_quality(stream_url)
                    elif label:
                        quality = scraper_utils.height_get_quality(label)
                    elif title:
                        quality = scraper_utils.blog_get_quality(video, title, '')
                    else:
                        quality = scraper_utils.blog_get_quality(video, stream_url, '')
                    sources[stream_url] = {'quality': quality, 'direct': True}
                    log_utils.log('Adding stream: %s Quality: %s' % (stream_url, quality), log_utils.LOGDEBUG)
        except Exception as e:
            log_utils.log('Exception during YesMovies XML Parse: %s' % (e), log_utils.LOGWARNING)

        return sources
    
    def __get_source_page(self, video_type, page_url):
        html = ''
        sl_url = ''
        movie_id = ''
        match = re.search('/movie/(.*?)-(\d+)\.html', page_url)
        if match:
            slug, movie_id = match.groups()
            vid_type = 'movie' if video_type == VIDEO_TYPES.MOVIE else 'series'
            qp_url = QP_URL % (slug, movie_id, vid_type)
            qp_url = urlparse.urljoin(self.base_url, qp_url)
            headers = {'Referer': urlparse.urljoin(self.base_url, page_url)}
            headers.update(XHR)
            html = self._http_get(qp_url, headers=headers, cache_limit=8)
            source_url = dom_parser.parse_dom(html, 'a', {'title': 'View all episodes'}, ret='href')
            if source_url:
                match = re.search('-(\d+)/(\d+)-(\d+)/', source_url[0])
                if match:
                    show_id, episode_id, server_id = match.groups()
                    sl_url = SL_URL % (show_id, server_id, episode_id, vid_type)
                    sl_url = urlparse.urljoin(self.base_url, sl_url)
                    html = self._http_get(sl_url, headers=headers, cache_limit=8)
        return movie_id, sl_url, html
        
    def _get_episode_url(self, season_url, video):
        _movie_id, _sl_url, html = self.__get_source_page(video.video_type, season_url)
        titles = dom_parser.parse_dom(html, 'a', {'href': '#player-area'}, ret='title')
        if any([self.__episode_match(video, title) for title in titles]):
            return season_url
    
    def __episode_match(self, video, label):
        episode_pattern = 'Episode\s+0*%s(?!\d)' % (video.episode)
        if re.search(episode_pattern, label, re.I):
            return True
        
        if video.ep_title:
            match = re.search('Episode\s+\d+: (.*)', label)
            if match:
                label = match.group(1)
                
            if scraper_utils.normalize_title(video.ep_title) in scraper_utils.normalize_title(label):
                return True
        
        return False
        
    def search(self, video_type, title, year, season=''):
        results = []
        search_url = urlparse.urljoin(self.base_url, '/ajax/movie_suggest_search.html')
        title = re.sub('[^A-Za-z0-9 ]', '', title)
        search_token = hashlib.md5(title + SEARCH_KEY).hexdigest()
        data = {'keyword': title, 'hash': search_token}
        headers = {'Referer': self.base_url}
        headers.update(XHR)
        html = self._http_get(search_url, data=data, headers=headers, cache_limit=8)
        js_data = scraper_utils.parse_json(html, search_url)
        html = js_data.get('content', '')
        html = html.replace('\"', '"')
        titles = dom_parser.parse_dom(html, 'a', {'class': 'ss-title'})
        urls = dom_parser.parse_dom(html, 'a', {'class': 'ss-title'}, ret='href')
        match_year = ''
        for match_title, match_url in zip(titles, urls):
            is_season = re.search('Season\s+(\d+)', match_title, re.I)
            if (video_type == VIDEO_TYPES.MOVIE and not is_season) or (video_type == VIDEO_TYPES.SEASON and is_season):
                if video_type == VIDEO_TYPES.SEASON:
                    if season and int(season) != int(is_season.group(1)): continue
                    
                if not year or not match_year or year == match_year:
                    result = {'title': scraper_utils.cleanse_title(match_title), 'year': match_year, 'url': scraper_utils.pathify_url(match_url)}
                    results.append(result)
    
        return results