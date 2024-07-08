"""
    Asguard Kodi Addon
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
from asguard_lib.constants import QUALITIES, VIDEO_TYPES
from . import scraper

import logging
try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)

logging.basicConfig(level=logging.DEBUG)

logger = log_utils.Logger.get_logger()
BASE_URL = 'https://animetosho.org'
SEARCH_URL = '/search'
QUALITY_MAP = {'1080p': QUALITIES.HD1080, '720p': QUALITIES.HD720, '3D': QUALITIES.HD1080}

class Scraper(scraper.Scraper):
    base_url = BASE_URL
    debrid_resolvers = resolveurl

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url')
        self.result_limit = kodi.get_setting(f'{self.get_name()}-result_limit')

    @classmethod
    def provides(cls):
        """
        Specifies the types of videos this scraper can provide.

        :return: A set of video types.
        """
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Animetosho'

    def resolve_link(self, link):
        logging.debug("Resolving link: %s", link)
        return link

    def get_sources(self, video):
        """
        Fetches sources for a given video.

        :param video: The video object containing details like title, year, etc.
        :return: A list of sources.
        """
        hosters = []
        query = self._build_query(video)
        search_url = scraper_utils.urljoin(self.base_url, SEARCH_URL)
        html = self._http_get(search_url, data=urllib.parse.urlencode(query).encode('utf-8'), require_debrid=True)
        soup = BeautifulSoup(html, "html.parser")
        soup_all = soup.find('div', id='content').find_all('div', class_='home_list_entry')


        for entry in soup_all:
            try:
                name = entry.find('div', class_='link').a.text
                magnet = entry.find('a', {'href': re.compile(r'(magnet:)+[^"]*')}).get('href')
                size = entry.find('div', class_='size').text
                torrent = entry.find('a', class_='dllink').get('href')
                # Extract quality from the name
                quality_match = re.search(r'\b(1080p|720p|480p|360p)\b', name)
                if quality_match:
                    quality = QUALITY_MAP.get(quality_match.group(0), QUALITIES.HD1080)
                else:
                    quality = QUALITIES.HD1080

                host = scraper_utils.get_direct_hostname(self, name)
                label = f"{name} | {quality} | {size}"
                hosters.append({
                    'class': self,
                    'name': name,
                    'multi-part': False,
                    'url': magnet,
                    'size': size,
                    'torrent': torrent,
                    'quality': quality,
                    'host': 'magnet',
                    'label': label,
                    'direct': False,
                    'debridonly': True
                })
                logging.debug("Retrieved sources: %s", hosters[-1])
            except AttributeError as e:
                logging.error("Failed to append source: %s", str(e)) 
                continue

        return self._filter_sources(hosters, video)

    def _build_query(self, video):
        """
        Builds the search query for the given video.

        :param video: The video object.
        :return: The search query as a dictionary.
        """
        query = {'q': video.title}
        if video.video_type == VIDEO_TYPES.EPISODE:
            query['q'] += f' S{int(video.season):02d}E{int(video.episode):02d}'
        elif video.video_type == VIDEO_TYPES.MOVIE:
            query['q'] += f' {video.year}'
        query['q'] = query['q'].replace(' ', '+').replace('+-', '-')
        query['qx'] = 1
        return query

    def _filter_sources(self, hosters, video):
        """
        Filters the sources based on the video type and episode matching.

        :param hosters: List of hosters.
        :param video: The video object.
        :return: Filtered list of sources.
        """
        logging.debug("Retrieved sources: %s", hosters)
        filtered_sources = []
        for source in hosters:
            if video.video_type == VIDEO_TYPES.EPISODE:
                if not self._match_episode(source['name'], video.season, video.episode):
                    continue
            filtered_sources.append(source)
            logging.debug("Retrieved filtered_sources: %s", filtered_sources)
        return filtered_sources

    def _match_episode(self, title, season, episode):
        """
        Matches the episode number in the title with the given season and episode.

        :param title: The title of the source.
        :param season: The season number.
        :param episode: The episode number.
        :return: True if the episode matches, False otherwise.
        """
        regex_ep = re.compile(r'\bS(\d+)E(\d+)\b')
        match = regex_ep.search(title)
        if match:
            # Convert extracted values to integers
            season_num = int(match.group(1))
            episode_num = int(match.group(2))
            
            # Convert expected values to integers
            season = int(season)
            episode = int(episode)
            
            # Perform comparison
            if season_num == season and episode_num == episode:
                return True
        return False

    def _http_get(self, url, data=None, retry=True, allow_redirect=True, cache_limit=8, require_debrid=True):
        """
        Performs an HTTP GET request.

        :param url: The URL to fetch.
        :param data: Data to send in the request.
        :param retry: Whether to retry on failure.
        :param allow_redirect: Whether to allow redirects.
        :param cache_limit: Cache limit for the request.
        :param require_debrid: Whether debrid is required.
        :return: The response text.
        """
        if require_debrid:
            if Scraper.debrid_resolvers is None:
                Scraper.debrid_resolvers = [resolver for resolver in resolveurl.relevant_resolvers() if resolver.isUniversal()]
            if not Scraper.debrid_resolvers:
                logger.log('%s requires debrid: %s' % (self.__module__, Scraper.debrid_resolvers), log_utils.LOGDEBUG)
                return ''
        try:
            headers = {'User-Agent': scraper_utils.get_ua()}
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return response.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            logger.log(f'HTTP Error: {e.code} - {url}', log_utils.LOGWARNING)
        except urllib.error.URLError as e:
            logger.log(f'URL Error: {e.reason} - {url}', log_utils.LOGWARNING)
        return ''

    @classmethod
    def get_settings(cls):
        """
        Returns the settings for the scraper.

        :return: List of settings.
        """
        settings = super(cls, cls).get_settings()
        name = cls.get_name()
        settings.append(f'         <setting id="{name}-result_limit" label="     {i18n("result_limit")}" type="slider" default="10" range="10,100" option="int" visible="true"/>')
        return settings
