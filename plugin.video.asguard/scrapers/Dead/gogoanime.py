"""
    SALTS Addon
    Copyright (C) 2024 MrBlamo

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
import urllib.parse
import urllib.request
import urllib.error
import kodi
import log_utils
from bs4 import BeautifulSoup
from asguard_lib import scraper_utils, control
from asguard_lib.constants import QUALITIES, VIDEO_TYPES
from asguard_lib.utils2 import i18n
from . import scraper

logger = log_utils.Logger.get_logger()
BASE_URL = 'https://anitaku.to'
SEARCH_URL = '/search.html?keyword='

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url')

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Gogoanime'

    def resolve_link(self, link):
        return link

    def get_sources(self, video):
        hosters = []
        query = self._build_query(video)
        search_url = scraper_utils.urljoin(self.base_url, SEARCH_URL, urllib.parse.quote_plus(query))
        logger.log('Search URL: %s' % search_url, log_utils.LOGDEBUG)
        
        html = self._http_get(search_url)
        soup = BeautifulSoup(html, 'html.parser')
        results = soup.find_all('div', {'class': 'list_search_ajax'})
        
        for result in results:
            result_title = result.find('a').text.strip()
            if video.title.lower() not in result_title.lower():
                continue
                
            slug = result.find('a').get('href').split('/')[-1]
            episode_urls = self._get_episode_urls(slug, video)
            
            for server, url in episode_urls:
                host = urllib.parse.urlparse(url).hostname
                quality = scraper_utils.get_quality(video, url, host)
                
                hoster = {
                    'class': self,
                    'name': f'GogoAnime ({server})',
                    'url': url,
                    'quality': quality,
                    'host': host,
                    'direct': False,
                    'debridonly': False
                }
                hosters.append(hoster)
        
        return hosters

    def _get_episode_urls(self, slug, video):
        urls = []
        url = f"{self.base_url}/category/{slug}"
        html = self._http_get(url)
        soup = BeautifulSoup(html, 'html.parser')
        
        # Match episode using regex pattern like watchepisodes
        episode_pattern = re.compile(f'-episode-{video.episode}(?:$|\\D)')
        
        for server in soup.select('.anime_muti_link > ul > li'):
            server_name = server.get('class')[0]
            link = server.a.get('data-video')
            
            if link and episode_pattern.search(link):
                if link.startswith('//'):
                    link = 'https:' + link
                urls.append((server_name, link))
        
        return urls

    def _build_query(self, video):
        if video.video_type == VIDEO_TYPES.EPISODE:
            query = f'{video.title}'
            logger.log('Query: %s' % query, log_utils.LOGDEBUG)
        if video.video_type == VIDEO_TYPES.MOVIE:
            query = f'{video.title} {video.year}'
        return query
