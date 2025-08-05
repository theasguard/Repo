"""
    Asguard Addon SALTS Fork
    Copyright (C) 2025 MrBlamo

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
from bs4 import BeautifulSoup
import requests
import log_utils
import json
from asguard_lib import scraper_utils, control
from asguard_lib.constants import VIDEO_TYPES, QUALITIES, FORCE_NO_MATCH
from asguard_lib.utils2 import i18n
import kodi
from . import scraper

try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)
logger = log_utils.Logger.get_logger()

BASE_URL = 'https://rivestream.org'
SEARCH_URL = ''
QUALITY_MAP = {'1080p': QUALITIES.HD1080, '720p': QUALITIES.HD720, '480p': QUALITIES.HIGH, '360p': QUALITIES.MEDIUM}

class Scraper(scraper.Scraper):
    base_url = BASE_URL
    movie_search_url = '/detail?type=movie&id=%s'
    tv_search_url = '/watch?type=tv&id=%s&season=%s&episode=%s'

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url') or BASE_URL

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Rivestream'

    def get_sources(self, video):
        from asguard_lib.trakt_api import Trakt_API
        sources = []
        trakt_id = video.trakt_id
        try:
            if video.video_type == VIDEO_TYPES.MOVIE:
                details = Trakt_API().get_movie_details(trakt_id)
                tmdb_id = details['ids']['tmdb']
                path = self.movie_search_url % tmdb_id
            else:
                details = Trakt_API().get_show_details(trakt_id)
                tmdb_id = details['ids']['tmdb']
                path = self.tv_search_url % (tmdb_id, video.season, video.episode)

            # Construct full URL
            url = urllib.parse.urljoin(self.base_url, path)
            logger.log(f"Fetching URL: {url}", log_utils.LOGDEBUG)
            
            response = self._http_get(url, cache_limit=1)
            if not response or response == FORCE_NO_MATCH:
                logger.log(f"Empty response for URL: {url}", log_utils.LOGWARNING)
                return sources

            soup = BeautifulSoup(response, 'html.parser')
            logger.log(f"Rivestream Soup: {soup}", log_utils.LOGDEBUG)
            
            # Look for primary embed container
            iframe = soup.find('iframe', {'id': 'embed-container'})
            logger.log(f"Rivestream Iframe: {iframe}", log_utils.LOGDEBUG)
            if iframe:
                embed_url = iframe['src']
                if embed_url.startswith('//'):
                    embed_url = 'https:' + embed_url
                
                host = urllib.parse.urlparse(embed_url).netloc
                
                sources.append({
                    'class': self,
                    'quality': QUALITIES.HD1080,
                    'url': embed_url,
                    'host': host,
                    'direct': False,
                    'multi-part': False,
                    'debridonly': False
                })

            # Look for alternative server links
            server_list = soup.find('div', class_='server-list')
            if server_list:
                for server in server_list.find_all('a', href=True):
                    server_url = server['href']
                    if not server_url.startswith('http'):
                        server_url = urllib.parse.urljoin(self.base_url, server_url)
                        host = urllib.parse.urlparse(server_url).netloc

                    sources.append({
                        'class': self,
                        'quality': QUALITIES.HD720,
                        'url': server_url,
                        'host': host,
                        'direct': False,
                        'multi-part': False,
                        'debridonly': False
                    })

        except Exception as e:
            logger.log(f'Error scraping Rivestream: {str(e)}', log_utils.LOGERROR)
        
        return sources

    def _http_get(self, url, data=None, retry=True, allow_redirect=True, cache_limit=8, require_debrid=True):
        if require_debrid:
            if Scraper.debrid_resolvers is None:
                Scraper.debrid_resolvers = [resolver for resolver in resolveurl.relevant_resolvers(url) if resolver.isUniversal()]
            if not Scraper.debrid_resolvers:
                logger.log('%s requires debrid: %s' % (self.__module__, Scraper.debrid_resolvers), log_utils.LOGDEBUG)
                return ''
        try:
            headers = {'User-Agent': scraper_utils.get_ua()}
            req = urllib.request.Request(url, data=data, headers=headers)
            logger.log('Rivestream Request: %s' % req, log_utils.LOGDEBUG)
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return response.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            logger.log(f'HTTP Error: {e.code} - {url}', log_utils.LOGWARNING)
        except urllib.error.URLError as e:
            logger.log(f'URL Error: {e.reason} - {url}', log_utils.LOGWARNING)
        return ''

    def _get_quality(self, url):
        for quality in self.QUALITY_MAP:
            if quality in url.lower():
                return self.QUALITY_MAP[quality]
        return QUALITIES.HIGH

    def resolve_link(self, link):
        if link.startswith('//'):
            link = 'https:' + link
        return link