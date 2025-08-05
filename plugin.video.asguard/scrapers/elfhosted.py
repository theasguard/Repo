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
import json
import urllib.parse
import urllib.request
import urllib.error
import re
from asguard_lib.utils2 import i18n
import xbmcgui
import kodi
import log_utils

from asguard_lib import scraper_utils, control, db_utils
from asguard_lib.constants import VIDEO_TYPES, QUALITIES
from . import scraper

logger = log_utils.Logger.get_logger()

class Scraper(scraper.Scraper):
    base_url = 'https://webstreamr.hayd.uk'
    
    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url') or self.base_url
        
        # Configuration options from WebStreamr
        self.config = {
            'multi': kodi.get_setting(f'{self.get_name()}-multi') == 'true',
            'en': kodi.get_setting(f'{self.get_name()}-en') == 'true',
            'includeExternalUrls': kodi.get_setting(f'{self.get_name()}-includeExternalUrls') == 'true',
            'mediaFlowProxyUrl': kodi.get_setting(f'{self.get_name()}-mediaFlowProxyUrl') or '',
            'mediaFlowProxyPassword': kodi.get_setting(f'{self.get_name()}-mediaFlowProxyPassword') or ''
        }
        
        # DEBUG: Log all setting values
        logger.log(f'🔧 WebStreamr Settings Debug:', log_utils.LOGDEBUG)
        for key, value in self.config.items():
            raw_value = kodi.get_setting(f'{self.get_name()}-{key}')
            logger.log(f'  {key}: raw="{raw_value}" → parsed={value}', log_utils.LOGDEBUG)
        logger.log(f'  base_url: "{self.base_url}"', log_utils.LOGDEBUG)

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'WebStreamr'

    @classmethod
    def get_settings(cls):
        settings = super(cls, cls).get_settings()
        name = cls.get_name()
        parent_id = f"{name}-enable"
        
        # Language settings
        settings.extend([
            f'''\t\t<setting id="{name}-multi" type="boolean" label="41003" help="">
\t\t\t<level>0</level>
\t\t\t<default>true</default>
\t\t\t<dependencies>
\t\t\t\t<dependency type="visible">
\t\t\t\t\t<condition operator="is" setting="{parent_id}">true</condition>
\t\t\t\t</dependency>
\t\t\t</dependencies>
\t\t\t<control type="toggle"/>
\t\t</setting>''',
            f'''\t\t<setting id="{name}-en" type="boolean" label="41004" help="">
\t\t\t<level>0</level>
\t\t\t<default>true</default>
\t\t\t<dependencies>
\t\t\t\t<dependency type="visible">
\t\t\t\t\t<condition operator="is" setting="{parent_id}">true</condition>
\t\t\t\t</dependency>
\t\t\t</dependencies>
\t\t\t<control type="toggle"/>
\t\t</setting>''',
            f'''\t\t<setting id="{name}-includeExternalUrls" type="boolean" label="41000" help="">
\t\t\t<level>0</level>
\t\t\t<default>true</default>
\t\t\t<dependencies>
\t\t\t\t<dependency type="visible">
\t\t\t\t\t<condition operator="is" setting="{parent_id}">true</condition>
\t\t\t\t</dependency>
\t\t\t</dependencies>
\t\t\t<control type="toggle"/>
\t\t</setting>''',
            f'''\t\t<setting id="{name}-mediaFlowProxyUrl" type="string" label="41001" help="">
\t\t\t<level>0</level>
\t\t\t<default></default>
\t\t\t<dependencies>
\t\t\t\t<dependency type="visible">
\t\t\t\t\t<condition operator="is" setting="{parent_id}">true</condition>
\t\t\t\t</dependency>
\t\t\t</dependencies>
\t\t\t<constraints>
\t\t\t\t<allowempty>true</allowempty>
\t\t\t</constraints>
\t\t\t<control type="edit" format="string">
\t\t\t\t<heading>MediaFlow Proxy URL</heading>
\t\t\t</control>
\t\t</setting>''',
            f'''\t\t<setting id="{name}-mediaFlowProxyPassword" type="string" label="41002" help="">
\t\t\t<level>0</level>
\t\t\t<default></default>
\t\t\t<dependencies>
\t\t\t\t<dependency type="visible">
\t\t\t\t\t<condition operator="is" setting="{parent_id}">true</condition>
\t\t\t\t</dependency>
\t\t\t</dependencies>
\t\t\t<constraints>
\t\t\t\t<allowempty>true</allowempty>
\t\t\t</constraints>
\t\t\t<control type="edit" format="string">
\t\t\t\t<heading>MediaFlow Proxy Password</heading>
\t\t\t</control>
\t\t</setting>'''
        ])
        
        return settings

    def resolve_link(self, link):
        return link

    def get_sources(self, video):
        sources = []
        
        try:
            # Use centralized IMDB ID retrieval from base class
            imdb_id = self.get_imdb_id(video)
            if not imdb_id:
                logger.log('WebStreamr: No IMDB ID found for trakt_id: %s' % video.trakt_id, log_utils.LOGWARNING)
                return sources

            # Determine stream type and build stream ID
            if video.video_type == VIDEO_TYPES.MOVIE:
                stream_type = 'movie'
                stream_id = imdb_id
                logger.log('WebStreamr: Searching for movie: %s' % imdb_id, log_utils.LOGDEBUG)
            else:
                stream_type = 'series'
                stream_id = f"{imdb_id}:{video.season}:{video.episode}"
                logger.log('WebStreamr: Searching for episode: %s S%sE%s' % (imdb_id, video.season, video.episode), log_utils.LOGDEBUG)

            # Build configuration URL
            config_url = self._build_config_url()
            
            # Build stream URL
            stream_url = f"{config_url}/stream/{stream_type}/{stream_id}.json"
            
            logger.log('WebStreamr: Requesting: %s' % stream_url, log_utils.LOGDEBUG)
            
            response = self._http_get(stream_url)
            if not response:
                logger.log('WebStreamr: No response from server', log_utils.LOGWARNING)
                return sources

            try:
                data = json.loads(response)
                streams = data.get('streams', [])
                logger.log('WebStreamr: Found %d streams' % len(streams), log_utils.LOGDEBUG)
            except json.JSONDecodeError as e:
                logger.log('WebStreamr: Failed to parse JSON response: %s' % str(e), log_utils.LOGERROR)
                return sources

            for stream in streams:
                try:
                    stream_url = stream.get('url', '')
                    if not stream_url:
                        continue
                        
                    title = stream.get('title', 'Unknown')
                    
                    # Extract quality from title or use default
                    quality = self._extract_quality(title)
                    
                    # Extract host from URL
                    parsed_url = urllib.parse.urlparse(stream_url)
                    host = parsed_url.hostname or 'Unknown'
                    
                    # Determine if it's a direct stream
                    direct = self._is_direct_stream(stream_url, host)
                    
                    source = {
                        'class': self,
                        'host': host,
                        'label': title,
                        'multi-part': False,
                        'quality': quality,
                        'url': stream_url,
                        'direct': direct,
                        'debridonly': False
                    }
                    
                    sources.append(source)
                    logger.log('WebStreamr: Found source: %s from %s' % (title, host), log_utils.LOGDEBUG)
                    
                except Exception as e:
                    logger.log('WebStreamr: Error processing stream: %s' % str(e), log_utils.LOGWARNING)
                    continue

        except Exception as e:
            logger.log('WebStreamr: Unexpected error in get_sources: %s' % str(e), log_utils.LOGERROR)

        logger.log('WebStreamr: Returning %d sources' % len(sources), log_utils.LOGDEBUG)
        return sources

    def _build_config_url(self):
        """Build the configuration URL with enabled language options"""
        config = {}
        
        # Add language configurations
        if self.config['multi']:
            config['multi'] = 'on'
        if self.config['en']:
            config['en'] = 'on'       
        if self.config['includeExternalUrls']:
            config['includeExternalUrls'] = 'on'
            
        # Add MediaFlow proxy settings if configured
        if self.config['mediaFlowProxyUrl']:
            config['mediaFlowProxyUrl'] = self.config['mediaFlowProxyUrl']
        if self.config['mediaFlowProxyPassword']:
            config['mediaFlowProxyPassword'] = self.config['mediaFlowProxyPassword']
        
        # If no languages selected, default to English
        if not any([self.config['multi'], self.config['en']]):
            config['en'] = 'on'
            
        config_json = json.dumps(config)
        config_encoded = urllib.parse.quote(config_json)
        final_url = f"{self.base_url}/{config_encoded}"
        
        # DEBUG: Log configuration building
        logger.log(f'🌐 WebStreamr Config URL Debug:', log_utils.LOGDEBUG)
        logger.log(f'  Built config: {config}', log_utils.LOGDEBUG)
        logger.log(f'  JSON: {config_json}', log_utils.LOGDEBUG)
        logger.log(f'  Final URL: {final_url}', log_utils.LOGDEBUG)
        
        return final_url

    def _extract_quality(self, title):
        """Extract quality from stream title"""
        title_lower = title.lower()
        
        if any(q in title_lower for q in ['4k', '2160p']):
            return QUALITIES.HD4K
        elif any(q in title_lower for q in ['1080p', 'fhd']):
            return QUALITIES.HD1080
        elif any(q in title_lower for q in ['720p', 'hd']):
            return QUALITIES.HD720
        elif any(q in title_lower for q in ['480p', 'sd']):
            return QUALITIES.HIGH
        elif any(q in title_lower for q in ['360p']):
            return QUALITIES.MEDIUM
        else:
            return QUALITIES.HIGH

    def _is_direct_stream(self, url, host):
        """Determine if the stream is direct based on URL patterns"""
        direct_indicators = [
            '.mp4', '.mkv', '.avi', '.m3u8', '.ts'
        ]
        
        # Check if URL contains direct stream indicators
        url_lower = url.lower()
        if any(indicator in url_lower for indicator in direct_indicators):
            return True
            
        # Known direct streaming hosts
        direct_hosts = [
            'googlevideo.com', 'googleusercontent.com',
            'github.io', 'githubusercontent.com'
        ]
        
        if any(direct_host in host.lower() for direct_host in direct_hosts):
            return True
            
        return False

    def _http_get(self, url, data=None, retry=True, allow_redirect=True, cache_limit=8):
        """HTTP GET request with proper error handling"""
        try:
            headers = {
                'User-Agent': scraper_utils.get_ua(),
                'Accept': 'application/json, text/plain, */*',
                'Accept-Language': 'en-US,en;q=0.9',
            }
            
            if data:
                data = data.encode('utf-8')
                
            req = urllib.request.Request(url, data=data, headers=headers)
            
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                content = response.read()
                if isinstance(content, bytes):
                    content = content.decode('utf-8', errors='ignore')
                return content
                
        except urllib.error.HTTPError as e:
            logger.log('HTTP Error %s: %s' % (e.code, url), log_utils.LOGWARNING)
        except urllib.error.URLError as e:
            logger.log('URL Error: %s - %s' % (e.reason, url), log_utils.LOGWARNING)
        except Exception as e:
            logger.log('Unexpected error: %s - %s' % (str(e), url), log_utils.LOGWARNING)
            
        return ''

    def search(self, video_type, title, year, season=''):
        """Search is not implemented for WebStreamr as it works with IMDB IDs"""
        logger.log('Search not implemented for WebStreamr - requires IMDB ID', log_utils.LOGDEBUG)
        return []
