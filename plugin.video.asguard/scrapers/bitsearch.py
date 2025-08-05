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

import re
import urllib.parse
from bs4 import BeautifulSoup
import requests
import log_utils
from asguard_lib import scraper_utils, control
from asguard_lib.constants import VIDEO_TYPES, QUALITIES
from asguard_lib.utils2 import i18n
import kodi
from . import scraper

try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)
logger = log_utils.Logger.get_logger()

BASE_URL = 'https://bitsearch.to'
SEARCH_URL = '/search?q=%s&sort=size'
QUALITY_MAP = {'1080p': QUALITIES.HD1080, '720p': QUALITIES.HD720, '480p': QUALITIES.HIGH, '360p': QUALITIES.MEDIUM}

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
        return 'Bitsearch'

    def resolve_link(self, link):
        return link

    def get_sources(self, video):
        hosters = []
        query = self._build_query(video)
        search_url = scraper_utils.urljoin(self.base_url, SEARCH_URL % urllib.parse.quote_plus(query))
        # logger.log(f"Search URL: {search_url}", log_utils.LOGDEBUG)
        html = self._http_get(search_url, require_debrid=True)
        # logger.log(f"Retrieved HTML: {html}", log_utils.LOGDEBUG)
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.find_all('li', class_='card search-result my-2')

        for row in rows:
            try:
                title_tag = row.find('h5', class_='title')
                if not title_tag:
                    continue
                name = title_tag.text.strip()

                stats_div = row.find('div', class_='stats')
                if not stats_div:
                    continue

                # Extract size
                size_tag = stats_div.find_all('div')[1]  # Assuming the secoond div contains the size
                size = size_tag.text.split('Size')[-1].strip() if size_tag else '0 MB'

                # Extract seeders
                seeder_div = stats_div.find_all('div')[2]  # Assuming the third div contains the seeders
                seeders = seeder_div.find('font').text.strip() if seeder_div else '0'


                magnet_link_tag = row.find('a', href=re.compile(r'magnet:'))
                if not magnet_link_tag:
                    continue
                magnet_link = magnet_link_tag['href']

                quality = scraper_utils.get_tor_quality(name)
                info = f"{size} | {seeders} seeders"
                dsize = scraper_utils._size(size)
                name_info = scraper_utils.info_from_name(name, video.trakt_id, video.title, video.year, '', '')

                label = f"{name} | {size} | {seeders} seeders"
                hosters.append({
                    'name': name,
                    'class': self,
                    'label': label,
                    'seeders': seeders,
                    'host': 'magnet',
                    'name_info': name_info,
                    'quality': quality,
                    'language': 'en',
                    'url': magnet_link,
                    'info': info,
                    'multi-part': False,
                    'direct': False,
                    'debridonly': True,
                    'size': dsize
                })
                logger.log(f"Added hoster: {hosters[-1]}", log_utils.LOGDEBUG)
            except Exception as e:
                logger.log(f"Error processing row: {str(e)}", log_utils.LOGWARNING)
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

