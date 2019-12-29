"""
    Asguard Addon
    Copyright (C) 2017 Thor

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
import xbmcgui
import hashlib
import kodi
import log_utils  # @UnusedImport
import dom_parser2
from asguard_lib import scraper_utils
from asguard_lib.constants import FORCE_NO_MATCH
from asguard_lib.constants import VIDEO_TYPES
from asguard_lib.constants import QUALITIES
from asguard_lib.constants import DELIM
from asguard_lib.utils2 import i18n
import scraper

logger = log_utils.Logger.get_logger()

BASE_URL3 = 'https://eztv.io'

BASE_UR2 = 'https://yts.lt'
MOVIE_SEARCH_URL = '/api/v2/list_movies.json'
MOVIE_DETAILS_URL = '/api/v2/movie_details.json'

MAGNET_LINK = 'magnet:?xt=urn:btih:%s'
VIDEO_EXT = ['MKV', 'AVI', 'MP4']
QUALITY_MAP = {'1080p': QUALITIES.HD1080, '720p': QUALITIES.HD720, '3D': QUALITIES.HD1080}

class Scraper(scraper.Scraper):
    movie_base_url = BASE_UR2
    tv_base_url = BASE_URL3

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        if kodi.get_setting('%s-use_https' % (self.get_name())) == 'true':
            scheme = 'https'
            prefix = 'www'
        else:
            scheme = 'http'
            prefix = 'http'
        base_url = kodi.get_setting('%s-base_url' % (self.get_name()))
        self.base_url = scheme + '://' + prefix + '.' + base_url
        self.include_trans = kodi.get_setting('%s-include_trans' % (self.get_name())) == 'true'

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'eztv'
        
    def __get_videos(self, content):
        videos = []
        for item in content.itervalues():
            if item['type'].lower() == 'dir':
                videos += self.__get_videos(item['children'])
            else:
                if item['ext'].upper() not in VIDEO_EXT: continue
                label = '(%s) %s' % (scraper_utils.format_size(item['size'], 'B'), item['name'])
                video = {'label': label, 'url': item['url']}
                videos.append(video)
                if self.include_trans and 'transcoded' in item and item['transcoded']:
                    transcode = item['transcoded']
                    if 'size' in transcode:
                        label = '(%s) (Transcode) %s' % (scraper_utils.format_size(transcode['size'], 'B'), item['name'])
                    else:
                        label = '(Transcode) %s' % (item['name'])
                    video = {'label': label, 'url': transcode['url']}
                    videos.append(video)
                    
        return videos

    def get_sources(self, video):
        source_url = self.get_url(video)
        if not source_url or source_url == FORCE_NO_MATCH: return []
        if video.video_type == VIDEO_TYPES.MOVIE:
            return self.__get_movie_sources(source_url)
        else:
            return self.__get_episode_sources(source_url, video)
    
    def __get_movie_id(self, source_url):
        url = scraper_utils.urljoin(self.movie_base_url, source_url)
        html = self._http_get(url, cache_limit=24)
        match = dom_parser2.parse_dom(html, 'div', {'id': 'movie-info'}, req='data-movie-id')
        if match:
            return match[0].attrs['data-movie-id']
          
    def _get_episode_url(self, show_url, video):
        if self.__find_episode(show_url, video):
            return show_url
    
    def __find_episode(self, show_url, video):
        url = scraper_utils.urljoin(self.tv_base_url, show_url)
        html = self._http_get(url, cache_limit=2)
        hashes = []
        for attrs, _magnet in dom_parser2.parse_dom(html, 'a', {'class': 'magnet'}, req=['href', 'title']):
            magnet_link, magnet_title = attrs['href'], attrs['title']
            match = re.search('urn:btih:(.*?)(?:&|$)', magnet_link, re.I)
            if match:
                magnet_title = re.sub(re.compile('\s+magnet\s+link', re.I), '', magnet_title)
                hashes.append((match.group(1), magnet_title))
        
        episode_pattern = 'S%02d\s*E%02d' % (int(video.season), int(video.episode))
        if video.ep_airdate:
            airdate_pattern = '%d{delim}%02d{delim}%02d'.format(delim=DELIM)
            airdate_pattern = airdate_pattern % (video.ep_airdate.year, video.ep_airdate.month, video.ep_airdate.day)
        else:
            airdate_pattern = ''
            
        matches = [link for link in hashes if re.search(episode_pattern, link[1], re.I)]
        if not matches and airdate_pattern:
            matches = [link for link in hashes if re.search(airdate_pattern, link[1])]
        return matches

    def search(self, video_type, title, year, season=''):  # @UnusedVariable
        if video_type == VIDEO_TYPES.MOVIE:
            return self.__movie_search(title, year)
        else:
            return self.__tv_search(title, year)

    def __movie_search(self, title, year):
        results = []
        params = {'query_term': title, 'sort_by': 'seeders', 'order_by': 'desc'}
        search_url = scraper_utils.urljoin(self.movie_base_url, MOVIE_SEARCH_URL)
        js_data = self._json_get(search_url, params=params, cache_limit=1)
        for movie in js_data.get('data', {}).get('movies', []):
            match_url = movie['url'] + '?movie_id=%s' % (movie['id'])
            match_title = movie.get('title_english') or movie.get('title')
            match_year = str(movie['year'])
            if not year or not match_year or year == match_year:
                result = {'title': scraper_utils.cleanse_title(match_title), 'year': match_year, 'url': scraper_utils.pathify_url(match_url)}
                results.append(result)
        
        return results
        
    def __tv_search(self, title, year):
        results = []
        search_url = scraper_utils.urljoin(self.tv_base_url, '/showlist/')
        html = self._http_get(search_url, cache_limit=48)
        match_year = ''
        norm_title = scraper_utils.normalize_title(title)
        for attrs, match_title in dom_parser2.parse_dom(html, 'a', {'class': 'thread_link'}, req='href'):
            match_url = attrs['href']
            if match_title.upper().endswith(', THE'):
                match_title = 'The ' + match_title[:-5]
    
            if norm_title in scraper_utils.normalize_title(match_title) and (not year or not match_year or year == match_year):
                result = {'title': scraper_utils.cleanse_title(match_title), 'year': match_year, 'url': scraper_utils.pathify_url(match_url)}
                results.append(result)
        return results
        
    @classmethod
    def get_settings(cls):
        settings = super(cls, cls).get_settings()
        settings = scraper_utils.disable_sub_check(settings)
        name = cls.get_name()
        settings.append('         <setting id="%s-use_https" type="bool" label="     %s" default="false" visible="eq(-3,true)"/>' % (name, i18n('use_https')))
        settings.append('         <setting id="%s-base_url2" type="text" label="     %s %s" default="%s" visible="eq(-6,true)"/>' % (name, i18n('movies'), i18n('base_url'), cls.movie_base_url))
        settings.append('         <setting id="%s-base_url3" type="text" label="     %s %s" default="%s" visible="eq(-7,true)"/>' % (name, i18n('tv_shows'), i18n('base_url'), cls.tv_base_url))
        settings.append('         <setting id="%s-include_trans" type="bool" label="     %s" default="true" visible="eq(-8,true)"/>' % (name, i18n('include_transcodes')))
        return settings
        
    def _http_get(self, url, data=None, headers=None, allow_redirect=True, cache_limit=8):
        return super(self.__class__, self)._http_get(url, data=data, headers=headers, allow_redirect=allow_redirect, cache_limit=cache_limit)