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
from asguard_lib.constants import FORCE_NO_MATCH, VIDEO_TYPES, QUALITIES
from . import scraper


try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)
    
logger = log_utils.Logger.get_logger()

BASE_URL = 'https://jackettio.elfhosted.com'

class Scraper(scraper.Scraper):
    base_url = BASE_URL
    debrid_resolvers = resolveurl

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting('%s-base_url' % (self.get_name()))
        self.bypass_filter = control.getSetting('Jackettio-bypass_filter') == 'true'
        logger.log('JackettIO: Initializing scraper', log_utils.LOGDEBUG)
        self._set_apikeys()
        
        # Build dynamic configuration with user's API keys
        params = self._build_config_params()
        self.movie_search_url = f'{params}/stream/movie/%s.json'
        self.tv_search_url = f'{params}/stream/series/%s:%s:%s.json'
        logger.log('JackettIO: Scraper initialized successfully', log_utils.LOGDEBUG)

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Jackettio'
    
    def resolve_link(self, link):
        return link

    def _set_apikeys(self):
        self.pm_apikey = kodi.get_setting('premiumize.apikey')
        self.rd_apikey = kodi.get_setting('realdebrid.apikey')
        self.ad_apikey = kodi.get_setting('alldebrid_api_key')
        self.tb_apikey = kodi.get_setting('torbox.apikey')
        self.dl_apikey = kodi.get_setting('debridlink.apikey')
    
    def _build_config_params(self):
        """Build JackettIO configuration parameters with user's debrid API keys"""
        import base64
        
        # Configuration matching JackettIO's expected format
        config = {
            "qualities": [0, 720, 1080, 2160],
            "excludeKeywords": ["cam", "xvid", "ts", "telecine"],
            "maxTorrents": 30,
            "priotizeLanguages": [],
            "priotizePackTorrents": 2,
            "forceCacheNextEpisode": True,
            "sortCached": [["quality", True], ["size", True]],
            "sortUncached": [["seeders", True]],
            "hideUncached": False,
            "indexers": ["eztv", "thepiratebay", "yts"],  # Use only available indexers
            "indexerTimeoutSec": 60,
            "passkey": "",
            "metaLanguage": "",
            "enableMediaFlow": False,
            "mediaflowProxyUrl": "",
            "mediaflowApiPassword": "",
            "mediaflowPublicIp": "",
            "useStremThru": True,
            "stremthruUrl": "http://elfhosted-internal.stremthru",
            "debridId": "realdebrid"  # Default to Real-Debrid
        }
        
        # Add debrid API key based on priority
        debrid_configured = False
        
        if self.rd_apikey:
            config["debridApiKey"] = self.rd_apikey
            config["debridId"] = "realdebrid"
            debrid_configured = True
            logger.log('JackettIO: Using Real-Debrid API key', log_utils.LOGDEBUG)
        elif self.tb_apikey:
            config["debridApiKey"] = self.tb_apikey
            config["debridId"] = "torbox"
            debrid_configured = True
            logger.log('JackettIO: Using TorBox API key', log_utils.LOGDEBUG)
        elif self.ad_apikey:
            config["debridApiKey"] = self.ad_apikey
            config["debridId"] = "alldebrid"
            debrid_configured = True
            logger.log('JackettIO: Using AllDebrid API key', log_utils.LOGDEBUG)
        elif self.pm_apikey:
            config["debridApiKey"] = self.pm_apikey
            config["debridId"] = "premiumize"
            debrid_configured = True
            logger.log('JackettIO: Using Premiumize API key', log_utils.LOGDEBUG)
        elif self.dl_apikey:
            config["debridApiKey"] = self.dl_apikey
            config["debridId"] = "debridlink"
            debrid_configured = True
            logger.log('JackettIO: Using DebridLink API key', log_utils.LOGDEBUG)
        
        if not debrid_configured:
            # Fallback to default TorBox key
            config["debridApiKey"] = kodi.get_setting('torbox.apikey')
            config["debridId"] = "torbox"
            logger.log('JackettIO: No user debrid API keys configured, using default TorBox key', log_utils.LOGWARNING)
        
        # Encode configuration to base64
        config_json = json.dumps(config, separators=(',', ':'))
        params = base64.b64encode(config_json.encode('utf-8')).decode('utf-8')
        
        logger.log('JackettIO: Generated config for debrid service: %s' % config["debridId"], log_utils.LOGDEBUG)
        return params

    def get_sources(self, video):
        sources = []

        try:
            logger.log('JackettIO: Starting get_sources for video type: %s' % video.video_type, log_utils.LOGDEBUG)
            
            # Use centralized IMDB ID retrieval from base class
            imdb_id = self.get_imdb_id(video)
            if not imdb_id:
                logger.log('JackettIO: No IMDB ID found for trakt_id: %s' % video.trakt_id, log_utils.LOGWARNING)
                return sources

            logger.log('JackettIO: Found IMDB ID: %s' % imdb_id, log_utils.LOGDEBUG)

            if video.video_type == VIDEO_TYPES.MOVIE:
                search_url = self.movie_search_url % imdb_id
                logger.log('JackettIO: Searching for movie: %s' % imdb_id, log_utils.LOGDEBUG)
            else:
                search_url = self.tv_search_url % (imdb_id, video.season, video.episode)
                logger.log('JackettIO: Searching for episode: %s S%sE%s' % (imdb_id, video.season, video.episode), log_utils.LOGDEBUG)
            
            logger.log('JackettIO: Search URL template: %s' % search_url, log_utils.LOGDEBUG)

            url = urllib.parse.urljoin(self.base_url, search_url)
            logger.log('JackettIO: Request URL: %s' % url, log_utils.LOGDEBUG)
            
            response = self._http_get(url, cache_limit=1, require_debrid=True)
            if not response or response == FORCE_NO_MATCH:
                logger.log('JackettIO: No response from server for URL: %s' % url, log_utils.LOGWARNING)
                return sources
            
            logger.log('JackettIO: Received response length: %d characters' % len(response), log_utils.LOGDEBUG)

            try:
                data = json.loads(response)
                files = data.get('streams', [])
                logger.log('JackettIO: Found %d streams in response' % len(files), log_utils.LOGDEBUG)
                
                if not files:
                    logger.log('JackettIO: No streams found. Response keys: %s' % list(data.keys()), log_utils.LOGDEBUG)
                    if 'error' in data:
                        logger.log('JackettIO: API error: %s' % data['error'], log_utils.LOGWARNING)
                    
            except json.JSONDecodeError as e:
                logger.log('JackettIO: Failed to parse JSON response: %s' % str(e), log_utils.LOGERROR)
                logger.log('JackettIO: Response content: %s' % response[:500], log_utils.LOGDEBUG)
                return sources

            for file in files:
                try:
                    file_url = file.get('url', '')
                    if not file_url:
                        logger.log('JackettIO: Skipping stream without URL', log_utils.LOGDEBUG)
                        continue
                        
                    logger.log('JackettIO: Processing stream: %s' % file_url[:100], log_utils.LOGDEBUG)
                    name = file.get('title', 'Unknown')
                    
                    # Extract quality from the title
                    quality = scraper_utils.get_tor_quality(name)
                    
                    # Extract size information from the title (JackettIO format includes emojis)
                    info = []
                    size_match = re.search(r'💾\s*([\d.]+)\s*(GB|MB)', name)
                    size = 0
                    if size_match:
                        size_value = float(size_match.group(1))
                        size_unit = size_match.group(2)
                        if size_unit == 'GB':
                            size = size_value * 1024  # Convert GB to MB
                        else:
                            size = size_value
                        info.append('%s%s' % (size_value, size_unit))
                    
                    # Extract seeders info
                    seeders_match = re.search(r'👥\s*(\d+)', name)
                    if seeders_match:
                        seeders = seeders_match.group(1)
                        info.append('%s seeds' % seeders)

                    source_info = ' | '.join(info) if info else 'JackettIO'
                    
                    # Clean up the title for display
                    clean_name = re.sub(r'💾.*$', '', name).strip()
                    clean_name = re.sub(r'👥.*$', '', clean_name).strip()
                    clean_name = re.sub(r'⚙️.*$', '', clean_name).strip()
                    if not clean_name:
                        clean_name = name[:50] + '...' if len(name) > 50 else name
                    
                    source = {
                        'class': self,
                        'host': 'magnet',
                        'label': clean_name,
                        'multi-part': False,
                        'name': clean_name,
                        'quality': quality,
                        'size': size,
                        'language': 'en',
                        'url': file_url,
                        'info': source_info,
                        'direct': False,
                        'debridonly': True
                    }
                    
                    sources.append(source)
                    logger.log('JackettIO: Added source: %s [%s] [%s]' % (clean_name, quality, source_info), log_utils.LOGDEBUG)
                    
                except Exception as e:
                    logger.log('JackettIO: Error processing source: %s' % str(e), log_utils.LOGWARNING)
                    continue

        except Exception as e:
            logger.log('JackettIO: Unexpected error in get_sources: %s' % str(e), log_utils.LOGERROR)

        logger.log('JackettIO: Returning %d sources' % len(sources), log_utils.LOGDEBUG)
        return sources


    def search(self, video_type, title, year, season=''):
        """
        Search method implementation for JackettIO scraper.
        JackettIO requires IMDB IDs, so search functionality is limited.
        """
        logger.log('JackettIO: Search not implemented - requires IMDB ID', log_utils.LOGDEBUG)
        return []

