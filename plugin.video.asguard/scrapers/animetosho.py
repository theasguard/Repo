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
import json
import itertools
import urllib.parse
import urllib.request
import urllib.error
import kodi
from bs4 import BeautifulSoup
from asguard_lib.utils2 import i18n
import xbmcgui
import log_utils
from asguard_lib import scraper_utils, control
from asguard_lib.constants import VIDEO_TYPES
from . import scraper

import logging

logging.basicConfig(level=logging.DEBUG)

logger = log_utils.Logger.get_logger()
BASE_URL = 'https://animetosho.org'
SEARCH_URL = '/search'

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url')
        self.result_limit = kodi.get_setting(f'{self.get_name()}-result_limit')

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Animetosho'

    def resolve_link(self, link):
        logging.debug("Resolving link: %s", link)
        return link

    def get_sources(self, video):
        sources = []
        query = self._build_query(video)
        search_url = scraper_utils.urljoin(self.base_url, SEARCH_URL)
        logging.debug("Retrieved show from database: %s", search_url)
        html = self._http_get(search_url, data=urllib.parse.urlencode(query).encode('utf-8'))
        logging.debug("Retrieved html: %s", html)
        soup = BeautifulSoup(html, "html.parser")
        soup_all = soup.find('div', id='content').find_all('div', class_='home_list_entry')
        logging.debug("Retrieved soup_all: %s", soup_all)
        host = scraper_utils.is_host_valid(soup_all, domains=['magnet'])

        for entry in soup_all:
            try:
                name = entry.find('div', class_='link').a.text
                logging.debug("Retrieved name: %s", name)
                magnet = entry.find('a', {'href': re.compile(r'(magnet:)+[^"]*')}).get('href')
                logging.debug("Retrieved magnet: %s", magnet)
                size = entry.find('div', class_='size').text
                logging.debug("Retrieved size: %s", size)
                torrent = entry.find('a', class_='dllink').get('href')
                logging.debug("Retrieved torrent: %s", torrent)
                sources.append({
                    'name': name,
                    'magnet': magnet,
                    'size': size,
                    'torrent': torrent,
                    'quality': scraper_utils.get_tquality(name),
                    'host': host,
                    'debridonly': True
                })
                logging.debug("Retrieved sources: %s", sources)
            except AttributeError as e:
                logger.log(f'Error parsing entry: {e}', log_utils.LOGWARNING)
                continue

        return self._filter_sources(sources, video)

    def _build_query(self, video):
        query = {'q': video.title}
        logging.debug("Retrieved query: %s", query)
        if video.video_type == VIDEO_TYPES.EPISODE:
            query['q'] += f' S{int(video.season):02d}E{int(video.episode):02d}'
            logging.debug("Retrieved query: %s", query)
        elif video.video_type == VIDEO_TYPES.MOVIE:
            query['q'] += f' {video.year}'
            logging.debug("Retrieved query: %s", query)
        query['qx'] = 1
        logging.debug("Retrieved query: %s", query)
        return query

    def _filter_sources(self, sources, video):
        logging.debug("Retrieved sources: %s", sources)
        filtered_sources = []
        for source in sources:
            if video.video_type == VIDEO_TYPES.EPISODE:
                if not self._match_episode(source['name'], video.season, video.episode):
                    continue
            filtered_sources.append(source)
        return filtered_sources

    def _match_episode(self, title, season, episode):
        regex_ep = re.compile(r'\bS(\d+)E(\d+)\b')
        match = regex_ep.search(title)
        logging.debug("Retrieved match: %s", match)
        if match:
            return int(match.group(1)) == season and int(match.group(2)) == episode
        logging.debug("Retrieved match: %s", match)
        return False

    def _http_get(self, url, data=None, retry=True, allow_redirect=True, cache_limit=8):
        try:
            headers = {'User-Agent': scraper_utils.get_ua()}
            req = urllib.request.Request(url, data=data, headers=headers)
            logging.debug("Retrieved req: %s", req)
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return response.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            logger.log(f'HTTP Error: {e.code} - {url}', log_utils.LOGWARNING)
        except urllib.error.URLError as e:
            logger.log(f'URL Error: {e.reason} - {url}', log_utils.LOGWARNING)
        return ''

    @classmethod
    def get_settings(cls):
        settings = super(cls, cls).get_settings()
        name = cls.get_name()
        settings.append(f'         <setting id="{name}-result_limit" label="     {i18n("result_limit")}" type="slider" default="10" range="10,100" option="int" visible="true"/>')
        return settings