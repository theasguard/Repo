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
import base64
import logging
import re
import json
import urllib.parse
from bs4 import BeautifulSoup
import requests
from asguard_lib.utils2 import i18n
import xbmcgui
import kodi
from typing import Optional, Tuple, Dict, List
import log_utils
from asguard_lib import scraper_utils, control
from asguard_lib.constants import HOST_Q, VIDEO_TYPES, QUALITIES
from . import scraper

try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)
    
logger = log_utils.Logger.get_logger()

class Scraper(scraper.Scraper):
    base_url = 'https://vidsrc.xyz'
    movie_search_url = '/embed/movie/%s'
    tv_search_url = '/embed/tv/%s/%s/%s'
    debrid_resolvers = resolveurl

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Vidsrc'
    
    def resolve_link(self, link):
        if link.startswith('//'):
            link = 'https:' + link
        return link

    def _link(self, data):
        links = data['links']
        for link in links:
            if link.lower().startswith('http'):
                return link
        return links[0]

    @classmethod
    def _hosts(self):
        hosts = []
        for key, value in HOST_Q.items():
            hosts.extend(value)
        hosts = [i.lower() for i in hosts]
        return hosts

    def _domain(self, data):
        elements = urllib.parse.urlparse(self._link(data))
        domain = elements.netloc or elements.path
        domain = domain.split('@')[-1].split(':')[0]
        result = re.search('(?:www\.)?([\w\-]*\.[\w\-]{2,3}(?:\.[\w\-]{2,3})?)$', domain)
        if result: domain = result.group(1)
        return domain.lower()

    @staticmethod
    def decode_base64_url_safe(s: str) -> bytearray:
        standardized_input = s.replace('_', '/').replace('-', '+')
        binary_data = base64.b64decode(standardized_input)
        return bytearray(binary_data)

    def get_sources(self, video):
        from asguard_lib.trakt_api import Trakt_API
        sources = []
        trakt_id = video.trakt_id

        try:
            if video.video_type == VIDEO_TYPES.MOVIE:
                details = Trakt_API().get_movie_details(trakt_id)
                tmdb_id = details['ids']['tmdb']
                search_url = self.movie_search_url % (tmdb_id)
            else:
                details = Trakt_API().get_show_details(trakt_id)
                tmdb_id = details['ids']['tmdb']
                search_url = self.tv_search_url % (tmdb_id, video.season, video.episode)

            url = urllib.parse.urljoin(self.base_url, search_url)
            response = self._http_get(url, cache_limit=1)
            if not response:
                return sources

            soup = BeautifulSoup(response, 'html.parser')
            iframe = soup.find('iframe', src=True)
            if iframe:
                embed_url = iframe['src']
                if embed_url.startswith('//'):
                    embed_url = 'https:' + embed_url
                host = urllib.parse.urlparse(embed_url).hostname
                quality = scraper_utils.blog_get_quality(video, embed_url, host)
                sources.append({
                    'quality': quality,
                    'url': embed_url,
                    'host': host,
                    'multi-part': False,
                    'class': self,
                    'rating': None,
                    'views': None,
                    'direct': False,
                })
                logger.log('Found source: %s' % sources[-1], log_utils.LOGDEBUG)
            else:
                logger.log('No iframe found in the response', log_utils.LOGWARNING)

        except AttributeError as e:
            logger.log('AttributeError: %s' % str(e), log_utils.LOGERROR)

        return sources


