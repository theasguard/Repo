"""
    Asguard Kodi Addon
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

        return link

    def parse_season_from_name(self, name):
        """
        Attempt to parse the season number from the source name.
        :param name: The source name (title of the torrent)
        :return: The season number as an integer, or None if not found.
        """
        # First, try to find explicit season markers (case insensitive)
        patterns = [
            r'Season\s*(\d+)',  # Season 1, Season1, Season 01
            r'S(\d+)',           # S1, S01
            r'S\s*(\d+)',        # S 1, S 01
            r'(\d+)(?:st|nd|rd|th)\s*Season',  # 1st Season, 2nd Season, etc.
        ]
        for pattern in patterns:
            match = re.search(pattern, name, re.IGNORECASE)
            if match:
                return int(match.group(1))
        
        # Then, try to match Roman numerals (only the common ones, up to 12 maybe)
        roman_numerals = {
            ' I ': 1, ' II ': 2, ' III ': 3, ' IV ': 4, ' V ': 5, ' VI ': 6, 
            ' VII ': 7, ' VIII ': 8, ' IX ': 9, ' X ': 10, ' XI ': 11, ' XII ': 12,
            # Also as whole words (with word boundaries)
            r'\bI\b': 1, r'\bII\b': 2, r'\bIII\b': 3, r'\bIV\b': 4, r'\bV\b': 5, r'\bVI\b': 6,
            r'\bVII\b': 7, r'\bVIII\b': 8, r'\bIX\b': 9, r'\bX\b': 10, r'\bXI\b': 11, r'\bXII\b': 12
        }
        for roman, number in roman_numerals.items():
            if re.search(roman, name, re.IGNORECASE):
                return number
        
        # If we haven't found a season, return None
        return None

    def get_sources(self, video):
        """
        Fetches sources for a given video.

        :param video: The video object containing details like title, year, etc.
        :return: A list of sources.
        """
        hosters = []
        query = self._build_query(video)
        search_url = scraper_utils.urljoin(self.base_url, SEARCH_URL)
        # logging.debug("Retrieved show from database: %s", search_url)
        html = self._http_get(search_url, data=urllib.parse.urlencode(query).encode('utf-8'), require_debrid=True)
        # logging.debug("Retrieved html: %s", html)
        soup = BeautifulSoup(html, "html.parser")
        soup_all = soup.find('div', id='content').find_all('div', class_='home_list_entry')
        # logging.debug("Retrieved soup_all: %s", soup_all)


        for entry in soup_all:
            try:
                name = entry.find('div', class_='link').a.text
                magnet = entry.find('a', {'href': re.compile(r'(magnet:)+[^"]*')}).get('href')
                size = entry.find('div', class_='size').text
                torrent = entry.find('a', class_='dllink').get('href')
                # Extract quality from the name
                quality = scraper_utils.get_tor_quality(name)
                logging.debug("Retrieved quality: %s", quality)

                host = scraper_utils.get_direct_hostname(self, name)
                label = f"{name} | {size}"
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
            except AttributeError as e:
                logging.error("Failed to append source: %s", str(e)) 
                continue
        return hosters

    def _is_correct_season(self, name, video):
        """Check if source matches the requested season"""
        season_num = int(video.season)
        patterns = [
            # Match season numbers in various formats
            rf"S{season_num:02d}\b", 
            rf"\b{season_num}\b",
            rf"Season {season_num}\b",
            rf"Season {season_num:02d}\b",
            # Match Roman numerals for seasons I-XII
            rf"\b{self._to_roman(season_num)}\b"
        ]
        return any(re.search(pattern, name, re.IGNORECASE) for pattern in patterns)

    def _to_roman(self, n):
        """Convert integer to Roman numeral (I-XII)"""
        roman_map = {1: 'I', 2: 'II', 3: 'III', 4: 'IV', 5: 'V', 6: 'VI',
                    7: 'VII', 8: 'VIII', 9: 'IX', 10: 'X', 11: 'XI', 12: 'XII'}
        return roman_map.get(n, '')

    def _build_query(self, video):
        """
        Builds the search query for the given video.
        :param video: The video object.
        :return: The search query as a dictionary.
        """
        # Normalize the video title to handle special characters and case sensitivity
        normalized_title = scraper_utils.cleanTitle(video.title)
        query = {'q': f'*{normalized_title}*'}
        logging.debug("Initial query animetosh: %s", query)

        # Construct the query based on the video type
        if video.video_type == VIDEO_TYPES.EPISODE:
            # Include both specific episode formats and season packs
            season_str = f'S{int(video.season):02d}'
            episode_str = f'E{int(video.episode):02d}'
            
            # Add formats: SXXEXX, SXX, and alternative episode formats
            query['q'] += f' {season_str}{episode_str}|{season_str}|"Complete"|"Batch"|"E{int(video.episode):02d}"'
        elif video.video_type == VIDEO_TYPES.MOVIE:
            query['q'] += f' {video.year}'
        elif video.video_type == VIDEO_TYPES.SEASON:
            # Include season range and complete season markers
            season_str = f'S{int(video.season):02d}'
            query['q'] += f' {season_str}|"Complete"|"Batch"'

        # Replace spaces with '+' and handle any special characters
        query['q'] = query['q'].replace(' ', '+').replace('+-', '-')
        query['qx'] = 1
        logging.debug("Final query: %s", query)

        return query

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
            logging.debug("Retrieved req: %s", req)
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return response.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            logger.log(f'HTTP Error: {e.code} - {url}', log_utils.LOGWARNING)
        except urllib.error.URLError as e:
            logger.log(f'URL Error: {e.reason} - {url}', log_utils.LOGWARNING)
        return ''

