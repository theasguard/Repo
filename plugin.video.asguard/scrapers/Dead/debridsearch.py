"""
    Asguard Addon
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
import logging
import re
import urllib.parse
import requests
from bs4 import BeautifulSoup
import kodi
import log_utils
from asguard_lib import scraper_utils
from asguard_lib.constants import VIDEO_TYPES, QUALITIES
from asguard_lib.utils2 import i18n
from . import scraper

logger = log_utils.Logger.get_logger()

BASE_URL = 'https://www.braflix.ru'
SEARCH_URL = '/search?q=%s'

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting('%s-base_url' % (self.get_name()))
        self.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:102.0) Gecko/20100101 Firefox/102.0'}

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Braflix'

    def resolve_link(self, link):
        return link

    def get_sources(self, video):
        hosters = []
        query = self._build_query(video)
        search_url = scraper_utils.urljoin(self.base_url, SEARCH_URL % urllib.parse.quote_plus(query))
        logger.log('Search URL: %s' % search_url, log_utils.LOGDEBUG)
        html = self._http_get(search_url, require_debrid=True)
        
        soup = BeautifulSoup(html, "html.parser")
        results = soup.find_all('div', class_='result-item')
        
        for result in results:
            try:
                title = result.find('h2').text.strip()
                link = result.find('a', href=True)['href']
                quality = self.get_quality(title)
                info = self.get_info(title)
                
                hosters.append({
                    'name': title,
                    'host': 'braflix',
                    'multi-part': False,
                    'class': self,
                    'url': link,
                    'quality': quality,
                    'info': info,
                    'direct': False,
                    'debridonly': True
                })
            except AttributeError as e:
                logger.log(f'Error parsing result: {e}', log_utils.LOGWARNING)
                continue

        return self._filter_sources(hosters, video)

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

    def _build_query(self, video):
        if video.video_type == VIDEO_TYPES.MOVIE:
            return f"{video.title} {video.year}"
        elif video.video_type == VIDEO_TYPES.TVSHOW:
            return video.title
        elif video.video_type == VIDEO_TYPES.EPISODE:
            return f"{video.title} S{int(video.season):02d}E{int(video.episode):02d}"

    @classmethod
    def get_settings(cls):
        settings = super(cls, cls).get_settings()
        name = cls.get_name()
        settings.append(f'         <setting id="{name}-result_limit" label="     {i18n("result_limit")}" type="slider" default="10" range="10,100" option="int" visible="true"/>')
        return settings

    def get_quality(self, title):
        if '1080p' in title:
            return '1080p'
        elif '720p' in title:
            return '720p'
        elif '480p' in title:
            return '480p'
        else:
            return 'SD'

    def get_info(self, title):
        info = []
        if 'x264' in title:
            info.append('x264')
        if 'x265' in title or 'HEVC' in title:
            info.append('x265')
        if 'HDR' in title:
            info.append('HDR')
        return ', '.join(info)