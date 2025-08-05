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
import urllib.request
import urllib.error
import json
import kodi
import log_utils
import resolveurl
from asguard_lib.utils2 import i18n
import xbmcgui
from asguard_lib import scraper_utils, control, client
from asguard_lib.constants import FORCE_NO_MATCH, QUALITIES, VIDEO_TYPES
from . import scraper
from . import proxy

try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)

logger = log_utils.Logger.get_logger()
BASE_URL = 'https://torrentgalaxy.hair'
SEARCH_URL = '/fullsearch?q=%s&category=all'
QUALITY_MAP = {'1080p': QUALITIES.HD1080, '720p': QUALITIES.HD720, '480p': QUALITIES.HIGH, '360p': QUALITIES.MEDIUM}

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url') or BASE_URL

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE, VIDEO_TYPES.MOVIE])

    @classmethod
    def get_name(cls):
        return 'TorrentGalaxy'

    def resolve_link(self, link):
        return link

    def _build_query(self, video):
        query = video.title
        if video.video_type == VIDEO_TYPES.EPISODE:
            query += f' S{int(video.season):02d}'
        elif video.video_type == VIDEO_TYPES.MOVIE:
            query += f' {video.year}'
        query = query.replace(' ', '+').replace('+-', '-')
        return query

    def get_sources(self, video):
        sources = []
        query = self._build_query(video)
        # Use the actual API endpoint instead of HTML scraping
        api_url = f'{self.base_url}/api.php?url=/q.php?q={urllib.parse.quote_plus(query)}&cat='
        logger.log(f'TorrentGalaxy API URL: {api_url}', log_utils.LOGDEBUG)
        
        # Get JSON data from API
        json_data = self._http_get(api_url, require_debrid=True, cache_limit=.5)
        if not json_data:
            logger.log('TorrentGalaxy: No API response received', log_utils.LOGWARNING)
            return []
            
        logger.log(f'TorrentGalaxy API response length: {len(json_data)}', log_utils.LOGDEBUG)
        
        try:
            torrents = json.loads(json_data)
            if not isinstance(torrents, list):
                logger.log('TorrentGalaxy: API response is not a list', log_utils.LOGWARNING)
                return []
        except json.JSONDecodeError as e:
            logger.log(f'TorrentGalaxy: JSON parsing error: {str(e)}', log_utils.LOGERROR)
            return []
        
        logger.log(f'TorrentGalaxy: Processing {len(torrents)} torrents from API', log_utils.LOGDEBUG)
        
        for i, torrent in enumerate(torrents):
            try:
                logger.log(f'TorrentGalaxy: Processing torrent {i+1}', log_utils.LOGDEBUG)
                
                # Get title from JSON
                title = torrent.get('name', '')
                if not title:
                    logger.log(f'TorrentGalaxy: Torrent {i+1} - FAILED no title in JSON', log_utils.LOGDEBUG)
                    continue
                
                logger.log(f'TorrentGalaxy: Torrent {i+1} - SUCCESS title: {title}', log_utils.LOGDEBUG)
                
                # Filter out TV episodes from movie searches (and vice versa)
                if not self._is_appropriate_content(video, title):
                    logger.log(f'TorrentGalaxy: Torrent {i+1} - FILTERED OUT content type mismatch: {title}', log_utils.LOGDEBUG)
                    continue
                
                logger.log(f'TorrentGalaxy: Torrent {i+1} - SUCCESS content type filter passed', log_utils.LOGDEBUG)
                
                # Get hash from JSON
                hash = torrent.get('info_hash', '')
                if not hash:
                    logger.log(f'TorrentGalaxy: Torrent {i+1} - FAILED no hash in JSON', log_utils.LOGDEBUG)
                    continue
                
                logger.log(f'TorrentGalaxy: Torrent {i+1} - Got hash: {hash} (length: {len(hash)})', log_utils.LOGDEBUG)
                
                if len(hash) == 32:  # Base32 hash, convert to hex
                    try:
                        hash = scraper_utils.base32_to_hex(hash, 'TorrentGalaxy')
                        logger.log(f'TorrentGalaxy: Torrent {i+1} - Converted base32 to hex: {hash}', log_utils.LOGDEBUG)
                    except Exception as e:
                        logger.log(f'TorrentGalaxy: Torrent {i+1} - FAILED hash conversion: {str(e)}', log_utils.LOGWARNING)
                        continue
                elif len(hash) != 40:
                    logger.log(f'TorrentGalaxy: Torrent {i+1} - FAILED invalid hash length: {len(hash)}', log_utils.LOGDEBUG)
                    continue
                
                logger.log(f'TorrentGalaxy: Torrent {i+1} - SUCCESS hash validation passed', log_utils.LOGDEBUG)
                
                # Build magnet link
                magnet_link = f'magnet:?xt=urn:btih:{hash}&dn={urllib.parse.quote_plus(title)}'
                # Add trackers as defined in the main.js print_trackers() function
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
                for tracker in trackers:
                    magnet_link += f'&tr={urllib.parse.quote_plus(tracker)}'
                
                logger.log(f'TorrentGalaxy: Torrent {i+1} - Built magnet link: {magnet_link[:50]}...', log_utils.LOGDEBUG)
                
                # Get seeders from JSON
                try:
                    seeders = int(torrent.get('seeders', 0))
                except ValueError:
                    seeders = 0
                logger.log(f'TorrentGalaxy: Torrent {i+1} - Seeders: {seeders}', log_utils.LOGDEBUG)
                
                # Clean up title
                name = scraper_utils.clean_title(title)
                logger.log(f'TorrentGalaxy: Torrent {i+1} - Cleaned title: {name}', log_utils.LOGDEBUG)
                
                # Get quality
                quality = scraper_utils.get_tor_quality(name)
                logger.log(f'TorrentGalaxy: Torrent {i+1} - Quality: {quality}', log_utils.LOGDEBUG)
                
                # Build label
                label = f'{name}'
                if seeders > 0:
                    label += f' (S:{seeders})'
                    
                logger.log(f'TorrentGalaxy: Torrent {i+1} - Label: {label}', log_utils.LOGDEBUG)
                
                source_dict = {
                    'class': self,
                    'host': 'torrent',
                    'label': label,
                    'multi-part': False,
                    'hash': hash,
                    'name': name,
                    'quality': quality,
                    'language': 'en',
                    'url': magnet_link,
                    'direct': False,
                    'debridonly': True,
                    'seeders': seeders
                }
                
                sources.append(source_dict)
                logger.log(f'TorrentGalaxy: Torrent {i+1} - ✅ SUCCESSFULLY ADDED SOURCE: {name} ({quality}) S:{seeders}', log_utils.LOGDEBUG)
                
            except Exception as e:
                logger.log(f'TorrentGalaxy: Torrent {i+1} - ❌ EXCEPTION: {str(e)}', log_utils.LOGERROR)
                import traceback
                logger.log(f'TorrentGalaxy: Torrent {i+1} - Traceback: {traceback.format_exc()}', log_utils.LOGDEBUG)
                continue
        
        logger.log(f'TorrentGalaxy: Returning {len(sources)} sources', log_utils.LOGDEBUG)
        return sources



    def _is_appropriate_content(self, video, title):
        """Check if the torrent title matches the video type we're looking for"""
        title_lower = title.lower()
        
        # Episode patterns
        episode_patterns = [
            r's\d{1,2}e\d{1,2}',  # S01E01
            r'season\s*\d+',       # Season 1
            r'\d{1,2}x\d{1,2}',    # 1x01
        ]
        
        has_episode_pattern = any(re.search(pattern, title_lower) for pattern in episode_patterns)
        
        if video.video_type == VIDEO_TYPES.MOVIE:
            # For movies, exclude torrents that look like TV episodes
            if has_episode_pattern:
                logger.log(f'TorrentGalaxy: Excluding TV episode from movie search: {title}', log_utils.LOGDEBUG)
                return False
        elif video.video_type in [VIDEO_TYPES.EPISODE, VIDEO_TYPES.TVSHOW]:
            # For TV content, we want episode patterns
            if not has_episode_pattern:
                # Allow it through, might be a season pack or different naming
                pass
        
        return True
