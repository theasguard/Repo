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
        self.result_limit = kodi.get_setting(f'{self.get_name()}-result_limit')

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Bitsearch'

    def resolve_link(self, link):
        logger.log(f"Resolving link: {link}", log_utils.LOGDEBUG)
        return link

    def get_sources(self, video):
        hosters = []
        query = self._build_query(video)
        search_url = scraper_utils.urljoin(self.base_url, SEARCH_URL % urllib.parse.quote_plus(query))
        logger.log(f"Search URL: {search_url}", log_utils.LOGDEBUG)
        html = self._http_get(search_url, require_debrid=True)
        logger.log(f"Retrieved HTML: {html}", log_utils.LOGDEBUG)
        soup = BeautifulSoup(html, "html.parser")
        rows = soup.find_all('li', class_='card search-result my-2')

        for row in rows:
            try:
                title_tag = row.find('h5', class_='title')
                if not title_tag:
                    continue
                name = title_tag.text.strip()

                size_tag = row.find('div', text=re.compile(r'Size'))
                size = size_tag.text.strip() if size_tag else '0 MB'

                seeders_tag = row.find('div', text=re.compile(r'Seeder'))
                seeders = seeders_tag.find('font').text.strip() if seeders_tag else '0'

                magnet_link_tag = row.find('a', href=re.compile(r'magnet:'))
                if not magnet_link_tag:
                    continue
                magnet_link = magnet_link_tag['href']

                quality = scraper_utils.get_tor_quality(name)
                info = f"{size} | {seeders} seeders"
                dsize = scraper_utils._size(size)
                name_info = scraper_utils.info_from_name(name, video.title, video.year, '', '')

                label = f"{name} | {quality} | {size}"
                hosters.append({
                    'name': name,
                    'class': self,
                    'label': label,
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
            query += f' S{int(video.season):02d}E{int(video.episode):02d}'
        elif video.video_type == VIDEO_TYPES.MOVIE:
            query += f' {video.year}'
        query = re.sub(r'[^A-Za-z0-9\s\.-]+', '', query)
        return query


    def _http_get(self, url, data=None, retry=True, allow_redirect=True, cache_limit=8, require_debrid=True):
        if require_debrid:
            if Scraper.debrid_resolvers is None:
                Scraper.debrid_resolvers = [resolver for resolver in resolveurl.relevant_resolvers() if resolver.isUniversal()]
            if not Scraper.debrid_resolvers:
                logger.log(f'{self.__module__} requires debrid: {Scraper.debrid_resolvers}', log_utils.LOGDEBUG)
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
        settings = super(cls, cls).get_settings()
        name = cls.get_name()
        settings.append(f'         <setting id="{name}-result_limit" label="     {i18n("result_limit")}" type="slider" default="10" range="10,100" option="int" visible="true"/>')
        return settings
