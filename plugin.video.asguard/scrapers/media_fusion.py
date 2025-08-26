"""
    Asguard Addon
    Copyright (C) 2024
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
import json
import urllib.parse
import requests
from asguard_lib.utils2 import i18n
import xbmcgui
import kodi
import log_utils
from asguard_lib import scraper_utils, control
from asguard_lib.constants import VIDEO_TYPES, QUALITIES
from . import scraper


try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)
    
logger = log_utils.Logger.get_logger()

class Scraper(scraper.Scraper):
    base_url = 'https://mediafusion.elfhosted.com'
    movie_search_url = '/stream/movie/%s.json'
    tv_search_url = '/stream/series/%s:%s:%s.json'
    debrid_resolvers = resolveurl

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.min_seeders = 0
        self.bypass_filter = control.getSetting('Mediafusion-bypass_filter') == 'true'
        self._set_apikeys()

    def _headers(self):
        headers = {'encoded_user_data': 'eyJlbmFibGVfY2F0YWxvZ3MiOiBmYWxzZSwgIm1heF9zdHJlYW1zX3Blcl9yZXNvbHV0aW9uIjogOTksICJ0b3JyZW50X3NvcnRpbmdfcHJpb3JpdHkiOiBbXSwgImNlcnRpZmljYXRpb25fZmlsdGVyIjogWyJEaXNhYmxlIl0sICJudWRpdHlfZmlsdGVyIjogWyJEaXNhYmxlIl19'}
        return headers

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Mediafusion'
    
    def resolve_link(self, link):
        return link

    def _set_apikeys(self):
        self.pm_apikey = kodi.get_setting('premiumize.apikey')
        self.rd_apikey = kodi.get_setting('realdebrid.apikey')
        self.ad_apikey = kodi.get_setting('alldebrid_api_key')

    def get_sources(self, video):
        sources = []
        
        try:
            # Use centralized IMDB ID retrieval from base class
            imdb_id = self.get_imdb_id(video)
            if not imdb_id:
                logger.log('MediaFusion: No IMDB ID found for trakt_id: %s' % video.trakt_id, log_utils.LOGWARNING)
                return sources
            
            if video.video_type == VIDEO_TYPES.MOVIE:
                search_url = self.movie_search_url % imdb_id
                logger.log('MediaFusion: Searching for movie: %s' % search_url, log_utils.LOGDEBUG)
            elif video.video_type == VIDEO_TYPES.EPISODE:
                search_url = self.tv_search_url % (imdb_id, video.season, video.episode)
                logger.log('MediaFusion: Searching for episode: %s' % search_url, log_utils.LOGDEBUG)
            else:
                logger.log('MediaFusion: Unsupported video type: %s' % video.video_type, log_utils.LOGWARNING)
                return sources

            url = urllib.parse.urljoin(self.base_url, search_url)
            response = self._http_get(url, cache_limit=1, require_debrid=True)
            logger.log('MediaFusion Response: %s' % response, log_utils.LOGDEBUG)
            
            if not response:
                return sources

            try:
                files = json.loads(response).get('streams', [])
                logger.log('MediaFusion: Found %d files' % len(files), log_utils.LOGDEBUG)
            except json.JSONDecodeError as e:
                logger.log('MediaFusion: Failed to parse JSON response: %s' % str(e), log_utils.LOGERROR)
                return sources

            for file in files:
                try:
                    # Extract hash from either infoHash or URL
                    if 'infoHash' in file:
                        hash = file['infoHash']
                    elif 'url' in file:
                        hash_match = re.search(r'\b\w{40}\b', file['url'])
                        hash = hash_match.group() if hash_match else ''
                    else:
                        continue
                        
                    logger.log('MediaFusion: Found file hash: %s' % hash, log_utils.LOGDEBUG)
                    
                    # Try multiple ways to get the filename and description
                    name = ''
                    description = ''
                    
                    # Method 1: behaviorHints.filename (newer format)
                    if 'behaviorHints' in file and 'filename' in file['behaviorHints']:
                        name = file['behaviorHints']['filename'].split('\n')[0]
                        description = file.get('description', '')
                    # Method 2: description field (current format)  
                    elif 'description' in file:
                        description = file['description']
                        name = description.split('\n')[0].split('/')[0]
                    # Method 3: title field (fallback)
                    elif 'title' in file:
                        name = file['title'].split('\n')[0]
                        description = name
                    else:
                        continue
                        
                    logger.log('MediaFusion: Found name: %s' % name, log_utils.LOGDEBUG)
                    
                    # Create magnet URL
                    name_part = re.sub(r'[^\w\-_\.]', ' ', name)  # Clean name for magnet
                    url = 'magnet:?xt=urn:btih:%s&dn=%s' % (hash, urllib.parse.quote(name_part))
                    logger.log('MediaFusion: Created magnet: %s' % url, log_utils.LOGDEBUG)
                    
                    # Extract seeders - try multiple patterns
                    seeders = 0
                    if 'seeds' in file:
                        seeders = int(file.get('seeds', 0))
                    else:
                        # Look for seeders in description with emoji or text
                        seeder_patterns = [
                            r'👤\s*(\d+)',  # Emoji format
                            r'Seeders?:?\s*(\d+)',  # Text format
                            r'Seeds?:?\s*(\d+)'     # Alternative text format
                        ]
                        for pattern in seeder_patterns:
                            seeder_match = re.search(pattern, description, re.IGNORECASE)
                            if seeder_match:
                                seeders = int(seeder_match.group(1))
                                break
                    
                    if self.min_seeders > seeders:
                        continue

                    # Extract quality from filename
                    quality = scraper_utils.get_tor_quality(name)
                    
                    # Extract size information
                    size = 0
                    size_patterns = [
                        r'💾\s*([\d.]+)\s*(GB|MB)',  # Emoji format
                        r'((?:\d+\,\d+\.\d+|\d+\.\d+|\d+\,\d+|\d+)\s*(?:GB|GiB|Gb|MB|MiB|Mb))',  # General format
                        r'Size:?\s*([\d.]+)\s*(GB|MB)'  # Text format
                    ]
                    
                    for pattern in size_patterns:
                        size_match = re.search(pattern, description, re.IGNORECASE)
                        if size_match:
                            size_value = float(size_match.group(1))
                            size_unit = size_match.group(2).upper()
                            if size_unit.startswith('G'):
                                size = size_value * 1024  # Convert GB to MB
                            else:
                                size = size_value
                            break
                    
                    # Create label with available information
                    label_parts = [name_part]
                    if size > 0:
                        label_parts.append(f"{size:.1f}MB")
                    if seeders > 0:
                        label_parts.append(f"{seeders} seeders")
                    label = " | ".join(label_parts)
                    
                    source_item = {
                        'class': self,
                        'host': 'magnet',
                        'label': label,
                        'multi-part': False,
                        'seeders': seeders,
                        'hash': hash,
                        'name': name,
                        'quality': quality,
                        'size': size,
                        'language': 'en',
                        'url': url,
                        'direct': False,
                        'debridonly': True
                    }
                    
                    sources.append(source_item)
                    logger.log('MediaFusion: Added source: %s' % source_item, log_utils.LOGDEBUG)
                    
                except Exception as e:
                    logger.log('MediaFusion: Error processing source: %s' % str(e), log_utils.LOGERROR)
                    continue

        except Exception as e:
            logger.log('MediaFusion: Unexpected error in get_sources: %s' % str(e), log_utils.LOGERROR)

        logger.log('MediaFusion: Returning %d sources' % len(sources), log_utils.LOGDEBUG)
        return sources

    def search(self, video_type, title, year, season=''):
        """
        Search method implementation for MediaFusion scraper.
        MediaFusion requires IMDB IDs, so search functionality is limited.
        """
        logger.log('MediaFusion: Search not implemented - requires IMDB ID', log_utils.LOGDEBUG)
        return []

