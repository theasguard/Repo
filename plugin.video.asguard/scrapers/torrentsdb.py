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
import json
import urllib.parse
from asguard_lib import scraper_utils
from asguard_lib.constants import VIDEO_TYPES, QUALITIES
from . import scraper
import log_utils

logger = log_utils.Logger.get_logger()

class Scraper(scraper.Scraper):
    base_url = 'https://torrentsdb.com'
    movie_search_url = '/stream/movie/%s.json'
    tv_search_url = '/stream/series/%s:%s:%s.json'
    
    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.min_seeders = 0

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'TorrentsDB'

    def resolve_link(self, link):
        return link

    def get_sources(self, video):
        sources = []

        try:
            # Use centralized IMDB ID retrieval from base class
            imdb_id = self.get_imdb_id(video)
            if not imdb_id:
                logger.log('TorrentsDB: No IMDB ID found for trakt_id: %s' % video.trakt_id, log_utils.LOGWARNING)
                return sources

            if video.video_type == VIDEO_TYPES.MOVIE:
                search_url = self.base_url + self.movie_search_url % imdb_id
                logger.log('TorrentsDB: Searching for movie: %s' % search_url, log_utils.LOGDEBUG)
            elif video.video_type == VIDEO_TYPES.EPISODE:
                search_url = self.base_url + self.tv_search_url % (imdb_id, video.season, video.episode)
                logger.log('TorrentsDB: Searching for episode: %s' % search_url, log_utils.LOGDEBUG)
            else:
                logger.log('TorrentsDB: Unsupported video type: %s' % video.video_type, log_utils.LOGWARNING)
                return sources

            response = self._http_get(search_url)
            if not response:
                logger.log('TorrentsDB: No response from server', log_utils.LOGWARNING)
                return sources

            try:
                data = json.loads(response)
                files = data.get('streams', [])
                logger.log('TorrentsDB: Found %d streams' % len(files), log_utils.LOGDEBUG)
            except json.JSONDecodeError as e:
                logger.log('TorrentsDB: Failed to parse JSON response: %s' % str(e), log_utils.LOGERROR)
                return sources

            # Regex pattern to match info lines with emoji indicators
            info_pattern = re.compile(r'(📅|👤).*')

            for file in files:
                try:
                    hash_value = file.get('infoHash', '')
                    if not hash_value:
                        continue

                    file_title_raw = file.get('title', '')
                    if not file_title_raw:
                        continue

                    # Split title by newlines and extract info
                    file_title_parts = file_title_raw.split('\n')
                    if not file_title_parts:
                        continue

                    # Extract the main filename (first part)
                    name = scraper_utils.cleanse_title(file_title_parts[0].strip())
                    
                    # Extract info line (contains seeders/size info)
                    file_info = ''
                    for part in file_title_parts:
                        if info_pattern.match(part):
                            file_info = part
                            break

                    # Skip if no name
                    if not name:
                        continue

                    logger.log('TorrentsDB: Processing: %s' % name, log_utils.LOGDEBUG)

                    # Create magnet link
                    magnet_url = 'magnet:?xt=urn:btih:%s&dn=%s' % (hash_value, urllib.parse.quote(name))

                    # Extract seeders from info line
                    seeders = 0
                    if file_info:
                        try:
                            seeder_match = re.search(r'(\d+)', file_info)
                            if seeder_match:
                                seeders = int(seeder_match.group(1))
                                if self.min_seeders > seeders:
                                    logger.log('TorrentsDB: Skipping due to low seeders: %d' % seeders, log_utils.LOGDEBUG)
                                    continue
                        except (ValueError, AttributeError):
                            seeders = 0

                    # Extract quality
                    quality = self._extract_quality(name)

                    # Extract file size from info line
                    size_gb = 0
                    size_label = ''
                    if file_info:
                        try:
                            size_match = re.search(r'((?:\d+\,\d+\.\d+|\d+\.\d+|\d+\,\d+|\d+)\s*(?:GB|GiB|Gb|MB|MiB|Mb))', file_info)
                            if size_match:
                                size_str = size_match.group(0)
                                size_label = size_str
                                # Convert to GB for sorting
                                if 'MB' in size_str.upper() or 'MIB' in size_str.upper():
                                    size_value = float(re.search(r'[\d,\.]+', size_str.replace(',', '')).group())
                                    size_gb = size_value / 1024
                                else:  # GB/GiB
                                    size_value = float(re.search(r'[\d,\.]+', size_str.replace(',', '')).group())
                                    size_gb = size_value
                        except (ValueError, AttributeError):
                            size_gb = 0

                    # Build source info
                    info_parts = []
                    if size_label:
                        info_parts.append(size_label)
                    if seeders > 0:
                        info_parts.append('%d seeders' % seeders)
                    
                    source_info = ' | '.join(info_parts) if info_parts else ''

                    source = {
                        'class': self,
                        'host': 'magnet',
                        'label': name,
                        'multi-part': False,
                        'quality': quality,
                        'url': magnet_url,
                        'info': source_info,
                        'direct': False,
                        'debridonly': True,
                        'size': size_gb
                    }

                    sources.append(source)
                    logger.log('TorrentsDB: Found source: %s [%s seeders, %s]' % (name, seeders, size_label), log_utils.LOGDEBUG)

                except Exception as e:
                    logger.log('TorrentsDB: Error processing stream: %s' % str(e), log_utils.LOGWARNING)
                    continue

        except Exception as e:
            logger.log('TorrentsDB: Unexpected error in get_sources: %s' % str(e), log_utils.LOGERROR)

        logger.log('TorrentsDB: Returning %d sources' % len(sources), log_utils.LOGDEBUG)
        return sources

    def _extract_quality(self, name):
        """Extract quality from torrent name"""
        name_lower = name.lower()
        
        if any(q in name_lower for q in ['2160p', '4k', 'uhd']):
            return QUALITIES.HD4K
        elif any(q in name_lower for q in ['1080p', 'fhd']):
            return QUALITIES.HD1080
        elif any(q in name_lower for q in ['720p', 'hd']):
            return QUALITIES.HD720
        elif any(q in name_lower for q in ['480p']):
            return QUALITIES.HIGH
        elif any(q in name_lower for q in ['360p']):
            return QUALITIES.MEDIUM
        else:
            return QUALITIES.HIGH



    def search(self, video_type, title, year, season=''):
        """
        Search method implementation for TorrentsDB scraper.
        TorrentsDB requires IMDB IDs, so search functionality is limited.
        """
        logger.log('TorrentsDB: Search not implemented - requires IMDB ID', log_utils.LOGDEBUG)
        return [] 