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
BASE_URL = 'https://ww6.solarmovie.to'
SEARCH_URL = '/search.html?q='

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
        return 'SolarMovie'

    def get_sources(self, video):
        hosters = []
        query = self._build_query(video)
        search_url = scraper_utils.urljoin(self.base_url, SEARCH_URL + urllib.parse.quote_plus(query))
        logger.log('Search URL: %s' % search_url, log_utils.LOGDEBUG)
        html = self._http_get(search_url, allow_redirect=True)
        logger.log('HTML: %s' % html, log_utils.LOGDEBUG)
        if not html:
            return hosters

        soup = BeautifulSoup(html, 'html.parser')
        results = soup.select('div.card.bg-transparent.border-0 a.poster')
        for result in results:
            title = result.get('title')
            url = result.get('href')
            if video.title.lower() in title.lower():
                episode_url = self._get_episode_url(url, video)
                if episode_url:
                    hosters.append({
                        'class': self,
                        'name': title,
                        'multi-part': False,
                        'url': episode_url,
                        'quality': QUALITIES.HD720,
                        'host': 'http',
                        'direct': False,
                        'debridonly': False
                    })

        return hosters

    def _build_query(self, video):
        query = video.title
        if video.video_type == VIDEO_TYPES.EPISODE:
            query += f' S{int(video.season):02d}'
        elif video.video_type == VIDEO_TYPES.MOVIE:
            query += f' {video.year}'
        return query

    def _get_episode_url(self, show_url, video):
        html = self._http_get(show_url)
        if not html:
            return None

        soup = BeautifulSoup(html, 'html.parser')
        episodes = soup.select('button.list-group-item.episode')
        for episode in episodes:
            ep_title = episode.get('title')
            if video.ep_title.lower() in ep_title.lower():
                return episode.get('href')
        return None

    @classmethod
    def get_settings(cls):
        settings = super(cls, cls).get_settings()
        name = cls.get_name()
        settings.append(f'         <setting id="{name}-result_limit" label="     {i18n("result_limit")}" type="slider" default="10" range="10,100" option="int" visible="true"/>')
        return settings