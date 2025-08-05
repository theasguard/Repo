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
import logging
import kodi
import log_utils
from bs4 import BeautifulSoup
from asguard_lib.utils2 import i18n
from asguard_lib import scraper_utils, control
from asguard_lib.constants import QUALITIES, VIDEO_TYPES
from . import scraper
try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)
logger = log_utils.Logger.get_logger()
BASE_URL = 'https://cloudtorrents.com'
SEARCH_URL = '/search?query='

class Scraper(scraper.Scraper):
    base_url = BASE_URL
    debrid_resolvers = resolveurl

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url')

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'CloudTorrents'

    def resolve_link(self, link):
        return link

    def get_sources(self, video):
        hosters = []
        query = self._build_query(video)
        search_url = scraper_utils.urljoin(self.base_url, SEARCH_URL + query)
        html = self._http_get(search_url)
        soup = BeautifulSoup(html, "html.parser")
        results = soup.find('table', class_='bordered-table striped-table')
        
        # Check if results were found
        if not results:
            logger.log("No results found in the table", log_utils.LOGWARNING)
            return hosters
            
        tbody = results.find('tbody')

        # Check if tbody exists
        if not tbody:
            logger.log("No tbody found in results", log_utils.LOGWARNING)
            return hosters

        for result in tbody.find_all('tr'):
            try:
                # Find the torrent title div
                title_div = result.find('div', class_='torrent-title')
                if not title_div:
                    logger.log("No torrent-title div found in row", log_utils.LOGDEBUG)
                    continue
                    
                # Extract the name from the <b> tag inside the <a> tag
                name_tag = title_div.find('a').find('b')
                if not name_tag:
                    logger.log("No name tag found in title div", log_utils.LOGDEBUG)
                    continue
                    
                name = name_tag.get_text(strip=True)
                
                # Extract the magnet link
                magnet_tag = result.find('a', class_='magnet-link')
                if not magnet_tag:
                    logger.log("No magnet link found in row", log_utils.LOGDEBUG)
                    continue
                    
                magnet = magnet_tag['href']
                
                # Extract the size
                size_td = result.find('td', {'data-title': 'Size'})
                size = size_td.get_text(strip=True) if size_td else 'Unknown size'
                
                # Determine quality based on the name
                quality = scraper_utils.get_tor_quality(name)
                label = f"{name} | {size}"

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
            except (AttributeError, TypeError) as e:
                logger.log(f"Failed to append source: {str(e)}", log_utils.LOGWARNING)
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

