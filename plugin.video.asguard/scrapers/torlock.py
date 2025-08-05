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
from urllib.parse import quote_plus, unquote_plus
import kodi
import log_utils  # @UnusedImport
import dom_parser2
from asguard_lib import scraper_utils, control, client
from asguard_lib.constants import FORCE_NO_MATCH, VIDEO_TYPES, QUALITIES, DELIM
from asguard_lib.utils2 import i18n
from . import scraper
import workers

logger = log_utils.Logger.get_logger()
BASE_URL = 'https://www.torlock2.com'
SEARCH_URL = '/all/torrents/%s.html'
_LINKS = re.compile(r'<a\s*href\s*=\s*(/torrent/.+?)>', re.DOTALL | re.I)

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url')
        min_seeders_setting = kodi.get_setting(f'{self.get_name()}-min_seeders')
        try:
            self.min_seeders = int(min_seeders_setting) if min_seeders_setting else 0
        except (ValueError, TypeError):
            self.min_seeders = 0

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Torlock'

    def resolve_link(self, link):
        return link

    def _build_query(self, video):
        query = video.title
        if video.video_type == VIDEO_TYPES.MOVIE:
            query += f' {video.year}'
        elif video.video_type == VIDEO_TYPES.EPISODE:
            query += f' S{int(video.season):02d}'
        query = query.replace(' ', '+').replace('+-', '-')
        return query

    def get_sources(self, video):
        sources = []
        query = self._build_query(video)
        search_url = scraper_utils.urljoin(self.base_url, SEARCH_URL % urllib.parse.quote_plus(query))
        html = self._http_get(search_url, cache_limit=1)
        
        if not html:
            logger.log('TORLOCK: No HTML returned from search', log_utils.LOGWARNING)
            return sources
            
        logger.log(f'TORLOCK Search URL: {search_url}', log_utils.LOGDEBUG)
        
        # Parse the table rows - new structure has TORRENT NAME | TIME AGO | SIZE | SEEDS | PEERS | HEALTH
        rows = client.parseDOM(html, 'tr')
        for row in rows:
            columns = re.findall(r'<td.*?>(.*?)</td>', row, re.DOTALL)
            if len(columns) < 4:  # Need at least name, time, size, seeds
                continue

            try:
                # Extract torrent detail page link from first column
                torrent_link_match = re.search(r'href\s*=\s*["\']([^"\']*torrent[^"\']*)["\']', columns[0], re.I)
                if not torrent_link_match:
                    continue
                    
                torrent_page = torrent_link_match.group(1)
                if not torrent_page.startswith('http'):
                    torrent_page = scraper_utils.urljoin(self.base_url, torrent_page)
                
                # Extract name from the link text
                name_match = re.search(r'>([^<]+)</a>', columns[0])
                if not name_match:
                    continue
                name = scraper_utils.cleanTitle(name_match.group(1))
                
                # Extract size (column 2: SIZE)
                size_text = re.sub(r'<[^>]*>', '', columns[2]).strip()
                if not size_text:
                    continue
                    
                # Extract seeders (column 3: SEEDS) 
                seeders_text = re.sub(r'<[^>]*>', '', columns[3]).strip().replace(',', '')
                try:
                    seeders = int(seeders_text)
                    if self.min_seeders > seeders:
                        continue
                except (ValueError, IndexError):
                    seeders = 0
                
                # Get the torrent detail page to find magnet link
                detail_html = self._http_get(torrent_page, cache_limit=8)
                if not detail_html:
                    continue
                    
                # Look for magnet link in detail page
                magnet_match = re.search(r'href\s*=\s*["\']?(magnet:[^"\'>\s]+)["\']?', detail_html, re.I)
                if not magnet_match:
                    continue
                    
                magnet_url = magnet_match.group(1)
                magnet_url = unquote_plus(magnet_url).replace('&amp;', '&')
                
                # Extract hash from magnet link
                hash_match = re.search(r'btih:([^&]+)', magnet_url, re.I)
                if not hash_match:
                    continue
                hash_value = hash_match.group(1)
                
                quality = scraper_utils.get_tor_quality(name)
                try:
                    dsize, isize = scraper_utils._size(size_text)
                except:
                    dsize, isize = 0, size_text

                sources.append({
                    'class': self,
                    'label': name,
                    'host': 'magnet',
                    'seeders': seeders,
                    'hash': hash_value,
                    'name': name,
                    'quality': quality,
                    'url': magnet_url,
                    'info': isize,
                    'direct': False,
                    'debridonly': True,
                    'size': dsize
                })
                
            except Exception as e:
                logger.log(f'TORLOCK ERROR parsing row: {e}', log_utils.LOGERROR)
                continue
                
        logger.log(f'TORLOCK: Found {len(sources)} sources', log_utils.LOGDEBUG)
        return sources

    @classmethod
    def get_settings(cls):
        settings = super(cls, cls).get_settings()
        settings = scraper_utils.disable_sub_check(settings)
        name = cls.get_name()
        parent_id = f"{name}-enable"
        label_id = kodi.Translations.get_scraper_label_id(name)
        return [
            f'''\t\t<setting id="{parent_id}" type="boolean" label="{label_id}" help="">
\t\t\t<level>0</level>
\t\t\t<default>true</default>
\t\t\t<dependencies>
\t\t\t\t<dependency type="visible">
\t\t\t\t\t<condition on="property" name="InfoBool">true</condition>
\t\t\t\t</dependency>
\t\t\t</dependencies>
\t\t\t<control type="toggle"/>
\t\t</setting>''',
            f'''\t\t<setting id="{name}-base_url" type="string" label="30175" help="">
\t\t\t<level>0</level>
\t\t\t<default>{cls.base_url}</default>
\t\t\t<dependencies>
\t\t\t\t<dependency type="visible">
\t\t\t\t\t<condition operator="is" setting="{parent_id}">true</condition>
\t\t\t\t</dependency>
\t\t\t</dependencies>
\t\t\t<control type="edit" format="string">
\t\t\t\t<heading>{i18n('base_url')}</heading>
\t\t\t</control>
\t\t</setting>''',
            f'''\t\t<setting id="{name}-min_seeders" type="integer" label="40486" help="">
\t\t\t<level>0</level>
\t\t\t<default>0</default>
\t\t\t<constraints>
\t\t\t\t<minimum>0</minimum>
\t\t\t\t<maximum>100</maximum>
\t\t\t</constraints>
\t\t\t<dependencies>
\t\t\t\t<dependency type="visible">
\t\t\t\t\t<condition operator="is" setting="{parent_id}">true</condition>
\t\t\t\t</dependency>
\t\t\t</dependencies>
\t\t\t<control type="slider" format="integer">
\t\t\t\t<popup>false</popup>
\t\t\t</control>
\t\t</setting>'''
        ]
