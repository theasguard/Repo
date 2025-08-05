"""
    Asguard Addon
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
import urllib.parse
import logging
import kodi
import log_utils
from bs4 import BeautifulSoup
from asguard_lib import scraper_utils, control
from asguard_lib.constants import FORCE_NO_MATCH, VIDEO_TYPES
from asguard_lib.utils2 import i18n
from . import scraper
import json

logger = log_utils.Logger.get_logger()

BASE_URL = 'https://idope.hair'
SEARCH_URL = '/fullsearch?q=%s'

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url') or BASE_URL
        min_seeders_setting = kodi.get_setting(f'{self.get_name()}-min_seeders')
        try:
            self.min_seeders = int(min_seeders_setting) if min_seeders_setting else 0
        except (ValueError, TypeError):
            self.min_seeders = 0

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'iDope'

    def get_sources(self, video):
        hosters = []
        query = self._build_query(video)
        api_url = scraper_utils.urljoin(self.base_url, f"/api.php?url=/q.php?q={urllib.parse.quote_plus(query)}")
        
        try:
            json_data = self._http_get(api_url, require_debrid=True, cache_limit=0.25)
        except Exception as http_error:
            logger.log(f'iDope HTTP error: {http_error}', log_utils.LOGWARNING)
            return []

        if not json_data:
            logger.log('iDope: No JSON data received', log_utils.LOGDEBUG)
            return []

        try:
            data = json.loads(json_data)
            logger.log(f'iDope: Parsed {len(data)} torrents from JSON', log_utils.LOGDEBUG)
            for torrent in data:
                try:
                    name = torrent.get('name', '')
                    info_hash = torrent.get('info_hash', '')
                    seeders_str = torrent.get('seeders', '0')
                    leechers_str = torrent.get('leechers', '0')
                    size_str = torrent.get('size', '0')
                    
                    # Convert to integers with error handling
                    try:
                        seeders = int(seeders_str)
                        leechers = int(leechers_str)
                        size = int(size_str)
                    except (ValueError, TypeError):
                        logger.log(f'iDope: Error converting numeric fields for {name}', log_utils.LOGWARNING)
                        continue
                    
                    if self.min_seeders > seeders:
                        continue
                        
                    quality = scraper_utils.get_tor_quality(name)
                    
                    # Construct magnet URI
                    magnet = self._build_magnet_uri(info_hash, name)
                    
                    label = f'{name} {self._format_size(size)}'

                    hosters.append({
                        'class': self, 
                        'host': 'torrent', 
                        'label': label, 
                        'hash': info_hash, 
                        'name': name,
                        'size': size,
                        'multi-part': False,
                        'quality': quality, 
                        'language': 'en', 
                        'url': magnet, 
                        'direct': False, 
                        'debridonly': True
                    })
                except Exception as e:
                    logger.log(f'Error parsing iDope source: {e}', log_utils.LOGWARNING)
                    logger.log(f'Problematic torrent data: {torrent}', log_utils.LOGDEBUG)
        except json.JSONDecodeError as e:
            logger.log(f'Error parsing iDope JSON: {e}', log_utils.LOGWARNING)
        except Exception as e:
            logger.log(f'Unexpected error parsing iDope JSON: {e}', log_utils.LOGWARNING)

        logger.log(f'iDope: Returning {len(hosters)} sources', log_utils.LOGDEBUG)
        return hosters

    def search(self, video_type, title, year, season=''):
        """
        Search for torrents on iDope and return results
        """
        search_results = []
        query = title
        if year:
            query += f' {year}'
        if season and video_type == VIDEO_TYPES.EPISODE:
            query += f' S{int(season):02d}'
        
        search_url = scraper_utils.urljoin(self.base_url, SEARCH_URL % urllib.parse.quote_plus(query))
        logger.log(f'iDope search URL: {search_url}', log_utils.LOGDEBUG)
        
        try:
            html = self._http_get(search_url, cache_limit=0.5)
            if html:
                # Parse search results from HTML
                soup = BeautifulSoup(html, 'html.parser')
                
                # Look for torrent results in the page
                for row in soup.find_all('tr'):
                    try:
                        name_cell = row.find('a', href=True)
                        if name_cell and '/torrent/' in name_cell.get('href', ''):
                            torrent_name = name_cell.get_text(strip=True)
                            torrent_url = name_cell.get('href')
                            
                            # Extract year from torrent name if available
                            year_match = re.search(r'(\d{4})', torrent_name)
                            torrent_year = year_match.group(1) if year_match else ''
                            
                            search_results.append({
                                'title': torrent_name,
                                'year': torrent_year,
                                'url': torrent_url
                            })
                    except Exception as e:
                        logger.log(f'Error parsing search result: {e}', log_utils.LOGDEBUG)
                        continue
        
        except Exception as e:
            logger.log(f'Error during iDope search: {e}', log_utils.LOGWARNING)
        
        logger.log(f'iDope search returned {len(search_results)} results', log_utils.LOGDEBUG)
        return search_results

    def _build_query(self, video):
        query = video.title
        if video.video_type == VIDEO_TYPES.MOVIE:
            query += f' {video.year}'
        elif video.video_type == VIDEO_TYPES.EPISODE:
            query += f' S{int(video.season):02d}'
        return query

    @classmethod
    def get_settings(cls):
        settings = super(cls, cls).get_settings()
        name = cls.get_name()
        parent_id = f"{name}-enable"
        
        settings.extend([
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
        ])
        
        return settings

    def _format_size(self, size_bytes):
        """Format size similar to iDope's print_size function"""
        if size_bytes >= 1125899906842624:
            return f"{round(size_bytes / 1125899906842624, 2)} PiB"
        if size_bytes >= 1099511627776:
            return f"{round(size_bytes / 1099511627776, 2)} TB"
        if size_bytes >= 1073741824:
            return f"{round(size_bytes / 1073741824, 2)} GB"
        if size_bytes >= 1048576:
            return f"{round(size_bytes / 1048576, 2)} MB"
        if size_bytes >= 1024:
            return f"{round(size_bytes / 1024, 2)} KB"
        return f"{size_bytes} B" 

    def _build_magnet_uri(self, info_hash, name):
        """Construct magnet URI from info hash and torrent name"""
        base = f"magnet:?xt=urn:btih:{info_hash}"
        name_encoded = urllib.parse.quote_plus(name)
        trackers = [
            'udp://tracker.coppersurfer.tk:6969/announce',
            'udp://tracker.openbittorrent.com:6969/announce',
            'udp://tracker.opentrackr.org:1337',
            'udp://movies.zsw.ca:6969/announce',
            'udp://tracker.dler.org:6969/announce',
            'udp://opentracker.i2p.rocks:6969/announce',
            'udp://open.stealth.si:80/announce',
            'udp://tracker.0x.tf:6969/announce'
        ]
        
        # Add name parameter
        magnet = f"{base}&dn={name_encoded}"
        
        # Add trackers
        for tracker in trackers:
            encoded_tracker = urllib.parse.quote_plus(tracker)
            magnet += f"&tr={encoded_tracker}"
            
        return magnet 

