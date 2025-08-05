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
import kodi
import urllib.parse
import urllib.request
import urllib.error
import logging
from bs4 import BeautifulSoup
from asguard_lib import scraper_utils, control
from asguard_lib.constants import QUALITIES, VIDEO_TYPES
from asguard_lib.utils2 import i18n
from . import scraper

logger = logging.getLogger(__name__)
BASE_URL = 'https://glodls.to'
SEARCH_URL = '/search_results.php?search='

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url')

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'GloDLS'
    
    def resolve_link(self, link):
        return link

    def get_sources(self, video):
        hosters = []
        query = self._build_query(video)
        search_url = scraper_utils.urljoin(self.base_url, SEARCH_URL + query)
        html = self._http_get(search_url, require_debrid=True)
        soup = BeautifulSoup(html, "html.parser")
        results = soup.find_all('tr', class_='t-row')


        for result in results:
            try:
                # Extract the name from the <b> tag within the <a> tag
                name_tag = result.find('a', title=True)
                name = name_tag.text if name_tag else 'Unknown Title'

                # Extract the magnet link
                magnet_tag = result.find('a', href=re.compile(r'magnet:\?xt=urn:btih:'))
                magnet = magnet_tag['href'] if magnet_tag else None

                # Extract the size
                size_tag = result.find_all('td', class_='ttable_col1')[-1]
                size = size_tag.text if size_tag else 'Unknown Size'

                # Determine quality based on the name
                quality = scraper_utils.get_tor_quality(name)
                label = f"{name} | {size}"

                if magnet:
                    hosters.append({
                        'class': self,
                        'name': name,
                        'multi-part': False,
                        'url': magnet,
                        'size': size,
                        'quality': quality,
                        'host': 'magnet',
                        'label': label,
                        'direct': False,
                        'debridonly': True

                    })
            except AttributeError as e:
                logger.error("Failed to append source: %s", str(e))
                continue

        return hosters

    def _build_query(self, video):
        query = video.title
        if video.video_type == VIDEO_TYPES.EPISODE:
            query += f' S{int(video.season):02d}'
        elif video.video_type == VIDEO_TYPES.MOVIE:
            query += f' {video.year}'
        query = query.replace(' ', '+').replace('+-', '-')
        return query
    