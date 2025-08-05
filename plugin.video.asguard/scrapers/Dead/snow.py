"""
    Asguard Addon - Snow Scraper
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
import logging
import re
import time
import random
import urllib.parse
import urllib.request
import urllib.error
import base64
from bs4 import BeautifulSoup

import kodi
import log_utils
from asguard_lib import scraper_utils
from asguard_lib.constants import VIDEO_TYPES, QUALITIES, FORCE_NO_MATCH
from asguard_lib.utils2 import i18n
from . import scraper

try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)

logger = log_utils.Logger.get_logger()

BASE_URL = 'https://snowfl.com'
QUALITY_MAP = {'2160': QUALITIES.HD4K, '1080': QUALITIES.HD1080, '720': QUALITIES.HD720, '480': QUALITIES.HIGH}

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url') or BASE_URL
        self.result_limit = int(kodi.get_setting(f'{self.get_name()}-result_limit') or 10)
        self.min_seeders = int(kodi.get_setting(f'{self.get_name()}-min_seeders') or 0)

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Snow'

    def resolve_link(self, link):
        return link

    def get_sources(self, video):
        """Get torrent sources from snowfl.com"""
        hosters = []
        
        # Build search query
        search_query = self._build_search_query(video)
        if not search_query or search_query == FORCE_NO_MATCH:
            logger.log('Snow: No valid search query could be built', log_utils.LOGDEBUG)
            return hosters

        logger.log(f'Snow: Search query: {search_query}', log_utils.LOGDEBUG)
        
        try:
            # Get the main page first to extract required parameters
            api_params = self._extract_api_params()
            if not api_params:
                logger.log('Snow: Failed to extract API parameters', log_utils.LOGWARNING)
                return hosters
            
            # Search for torrents using the API
            results = self._search_torrents(search_query, api_params)
            if not results:
                logger.log('Snow: No search results returned', log_utils.LOGDEBUG)
                return hosters
            
            # Process results and create hosters
            hosters = self._process_search_results(results, video)
            
        except Exception as e:
            logger.log(f'Snow: Error during search: {e}', log_utils.LOGWARNING)
            return hosters
        
        logger.log(f'Snow: Returning {len(hosters)} sources', log_utils.LOGDEBUG)
        return hosters

    def _build_search_query(self, video):
        """Build search query based on video type"""
        if video.video_type == VIDEO_TYPES.MOVIE:
            search_query = f"{video.title} {video.year}"
        elif video.video_type == VIDEO_TYPES.EPISODE:
            search_query = f"{video.title} S{int(video.season):02d}E{int(video.episode):02d}"
        else:  # TVSHOW
            search_query = f"{video.title} S{int(video.season):02d}"
        
        # Clean up the query
        search_query = re.sub(r'[^\w\s-]', '', search_query)
        search_query = re.sub(r'\s+', ' ', search_query).strip()
        
        return search_query

    def _extract_api_params(self):
        """Extract API parameters from the main page"""
        try:
            logger.log('Snow: Extracting API parameters', log_utils.LOGDEBUG)
            
            # Get main page
            html = self._http_get(self.base_url, require_debrid=True)
            if not html:
                logger.log('Snow: Failed to get main page', log_utils.LOGWARNING)
                return None
            
            logger.log(f'Snow: Main page HTML length: {len(html)}', log_utils.LOGDEBUG)
            
            # Extract b.min.js file path with version parameter
            js_pattern = r'src="(b\.min\.js[^"]*)"'
            js_match = re.search(js_pattern, html)
            if not js_match:
                logger.log('Snow: Could not find b.min.js reference', log_utils.LOGWARNING)
                logger.log('Snow: Searching for alternative JS patterns', log_utils.LOGDEBUG)
                # Try alternative patterns
                alt_patterns = [
                    r'src="(b\.min\.js[^"]*)"',
                    r'<script[^>]*src="([^"]*b\.min\.js[^"]*)"',
                    r'"([^"]*b\.min\.js[^"]*)"'
                ]
                for pattern in alt_patterns:
                    alt_match = re.search(pattern, html, re.I)
                    if alt_match:
                        js_path = alt_match.group(1)
                        logger.log(f'Snow: Found JS with alternative pattern: {js_path}', log_utils.LOGDEBUG)
                        break
                else:
                    return None
            else:
                js_path = js_match.group(1)
            
            logger.log(f'Snow: Found JS path: {js_path}', log_utils.LOGNOTICE)
            
            # Extract the API code from the version parameter in the JS path
            # The API code is the 'v=' parameter value
            version_pattern = r'v=([^&"\']+)'
            version_match = re.search(version_pattern, js_path)
            
            if not version_match:
                logger.log('Snow: Could not extract version parameter from JS path', log_utils.LOGWARNING)
                return None
            
            api_code = version_match.group(1)
            logger.log(f'Snow: Successfully extracted API code from JS version: {api_code[:20]}...{api_code[-20:]}', log_utils.LOGNOTICE)
            
            return {
                'code': api_code,
                'timestamp': str(int(time.time() * 1000))
            }
            
        except Exception as e:
            logger.log(f'Snow: Error extracting API params: {e}', log_utils.LOGWARNING)
            return None

    def _search_torrents(self, query, api_params, max_pages=3):
        """Search for torrents using the extracted API parameters"""
        all_results = []
        
        try:
            encoded_query = urllib.parse.quote_plus(query)
            logger.log(f'Snow: Encoded query: {encoded_query}', log_utils.LOGDEBUG)
            
            for page in range(1, max_pages + 1):
                logger.log(f'Snow: Searching page {page} for: {query}', log_utils.LOGNOTICE)
                
                # Generate random string for the request
                rand_str = self._generate_random_string()
                logger.log(f'Snow: Random string: {rand_str}', log_utils.LOGDEBUG)
                
                # Build API URL - based on the pattern seen in original code
                api_url = f"{self.base_url}/{api_params['code']}/{encoded_query}/{rand_str}/{page}/NONE/NONE/1"
                logger.log(f'Snow: API URL: {api_url}', log_utils.LOGDEBUG)
                
                # Add timestamp parameter
                params = {'_': api_params['timestamp']}
                logger.log(f'Snow: Request params: {params}', log_utils.LOGDEBUG)
                
                # Make the API request
                response_text = self._http_get(api_url, params=params, require_debrid=True)
                if not response_text:
                    logger.log(f'Snow: No response from API for page {page}', log_utils.LOGWARNING)
                    continue
                
                logger.log(f'Snow: Response length: {len(response_text)}', log_utils.LOGDEBUG)
                logger.log(f'Snow: Response preview: {response_text[:200]}...', log_utils.LOGDEBUG)
                
                try:
                    # Parse JSON response
                    results = json.loads(response_text)
                    logger.log(f'Snow: JSON parsed successfully, type: {type(results)}', log_utils.LOGDEBUG)
                    
                    if not isinstance(results, list):
                        logger.log(f'Snow: Unexpected response format on page {page}: {type(results)}', log_utils.LOGWARNING)
                        logger.log(f'Snow: Response content: {str(results)[:300]}', log_utils.LOGDEBUG)
                        continue
                    
                    if not results:
                        logger.log(f'Snow: Empty results list on page {page}', log_utils.LOGNOTICE)
                        break  # No more results
                    
                    all_results.extend(results)
                    logger.log(f'Snow: Found {len(results)} results on page {page}', log_utils.LOGNOTICE)
                    
                    # Log sample of first result for debugging
                    if results and len(results) > 0:
                        sample_result = results[0]
                        logger.log(f'Snow: Sample result keys: {list(sample_result.keys()) if isinstance(sample_result, dict) else "Not a dict"}', log_utils.LOGDEBUG)
                    
                    # Stop if we have enough results
                    if len(all_results) >= self.result_limit:
                        logger.log(f'Snow: Reached result limit ({self.result_limit})', log_utils.LOGDEBUG)
                        break
                        
                except json.JSONDecodeError as e:
                    logger.log(f'Snow: Failed to parse JSON response on page {page}: {e}', log_utils.LOGWARNING)
                    logger.log(f'Snow: Raw response: {response_text[:500]}', log_utils.LOGDEBUG)
                    continue
            
            logger.log(f'Snow: Total results collected: {len(all_results)}', log_utils.LOGNOTICE)
            
        except Exception as e:
            logger.log(f'Snow: Error during torrent search: {e}', log_utils.LOGWARNING)
            import traceback
            logger.log(f'Snow: Traceback: {traceback.format_exc()}', log_utils.LOGDEBUG)
        
        return all_results

    def _process_search_results(self, results, video):
        """Process search results and create hoster objects"""
        hosters = []
        
        for result in results[:self.result_limit]:
            try:
                # Handle direct magnet links
                if 'magnet' in result and result['magnet']:
                    hoster = self._create_hoster_from_result(result, video, result['magnet'])
                    if hoster:
                        hosters.append(hoster)
                
                # Handle results that need additional processing for magnet links
                elif 'url' in result and 'site' in result:
                    # Try to get the actual magnet/torrent link
                    magnet_link = self._get_magnet_link(result)
                    if magnet_link:
                        hoster = self._create_hoster_from_result(result, video, magnet_link)
                        if hoster:
                            hosters.append(hoster)
                
            except Exception as e:
                logger.log(f'Snow: Error processing result: {e}', log_utils.LOGDEBUG)
                continue
        
        return hosters

    def _create_hoster_from_result(self, result, video, magnet_link):
        """Create a hoster object from a search result"""
        try:
            name = result.get('name', 'Unknown')
            size_str = result.get('size', '0')
            seeders = int(result.get('seeder', 0))
            leechers = int(result.get('leecher', 0))
            
            # Check minimum seeders requirement
            if seeders < self.min_seeders:
                logger.log(f'Snow: Skipping {name} - insufficient seeders ({seeders})', log_utils.LOGDEBUG)
                return None
            
            # Parse size
            try:
                size = self._parse_size(size_str)
            except:
                size = 0
            
            # Check size limit
            max_size = float(kodi.get_setting("size_limit") or 10)
            if size > max_size:
                logger.log(f'Snow: Skipping {name} - too large ({size}GB)', log_utils.LOGDEBUG)
                return None
            
            # Determine quality
            quality = scraper_utils.get_tor_quality(name)
            
            hoster = {
                'multi-part': False,
                'host': 'magnet',
                'class': self,
                'quality': quality,
                'views': None,
                'rating': None,
                'url': magnet_link,
                'size': scraper_utils.format_size(int(size * 1024)) if size else '',
                'extra': f'S:{seeders} L:{leechers}',
                'direct': False,
                'debridonly': True
            }
            
            logger.log(f'Snow: Created hoster for {name} ({quality}, {size}GB)', log_utils.LOGDEBUG)
            return hoster
            
        except Exception as e:
            logger.log(f'Snow: Error creating hoster: {e}', log_utils.LOGDEBUG)
            return None

    def _get_magnet_link(self, result):
        """Get magnet link for results that don't have direct magnet"""
        try:
            site = result.get('site', '')
            url = result.get('url', '')
            
            if not site or not url:
                return None
            
            # Encode URL for API call
            encoded_url = base64.b64encode(urllib.parse.quote_plus(url).encode()).decode().replace('\n', '')
            
            # Make API call to get magnet link
            api_url = f"{self.base_url}/OIcObqNfqpHTDvLKWQDNRlzQPbtqRcoKhtlled/{site}/{encoded_url}"
            
            response_text = self._http_get(api_url, require_debrid=True)
            if not response_text:
                return None
            
            response_data = json.loads(response_text)
            return response_data.get('url')
            
        except Exception as e:
            logger.log(f'Snow: Error getting magnet link: {e}', log_utils.LOGDEBUG)
            return None

    def _parse_size(self, size_str):
        """Parse size string to GB float"""
        if not size_str:
            return 0
        
        size_str = size_str.replace(',', '').strip()
        
        # Extract number and unit
        match = re.search(r'([\d.]+)\s*(GB|MB|KB|TB)?', size_str, re.I)
        if not match:
            return 0
        
        size_num = float(match.group(1))
        unit = (match.group(2) or 'MB').upper()
        
        # Convert to GB
        if unit == 'TB':
            return size_num * 1024
        elif unit == 'GB':
            return size_num
        elif unit == 'MB':
            return size_num / 1024
        elif unit == 'KB':
            return size_num / (1024 * 1024)
        
        return size_num

    def _generate_random_string(self, length=8):
        """Generate random string for API requests"""
        chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOP1234567890"
        return ''.join(random.choice(chars) for _ in range(length))

    def _http_get(self, url, data=None, params=None, require_debrid=True):
        """Enhanced HTTP GET with parameter support"""
        if require_debrid:
            if Scraper.debrid_resolvers is None:
                try:
                    Scraper.debrid_resolvers = [resolver for resolver in resolveurl.relevant_resolvers() if resolver.isUniversal()]
                except:
                    Scraper.debrid_resolvers = []
            if not Scraper.debrid_resolvers:
                logger.log(f'Snow requires debrid: {Scraper.debrid_resolvers}', log_utils.LOGDEBUG)
                return ''
        
        try:
            # Add parameters to URL if provided
            if params:
                url_parts = list(urllib.parse.urlparse(url))
                query_dict = urllib.parse.parse_qs(url_parts[4])
                query_dict.update(params)
                url_parts[4] = urllib.parse.urlencode(query_dict, doseq=True)
                url = urllib.parse.urlunparse(url_parts)
            
            logger.log(f'Snow: Making request to: {url}', log_utils.LOGDEBUG)
            
            headers = {
                'User-Agent': scraper_utils.get_ua(),
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'Accept-Language': 'en-US,en;q=0.5',
                'X-Requested-With': 'XMLHttpRequest',
                'Connection': 'keep-alive',
                'Referer': self.base_url + '/',
            }
            
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                content = response.read().decode('utf-8')
                logger.log(f'Snow: Request successful, content length: {len(content)}', log_utils.LOGDEBUG)
                return content
            
        except urllib.error.HTTPError as e:
            logger.log(f'Snow: HTTP Error {e.code}: {url}', log_utils.LOGWARNING)
            if hasattr(e, 'read'):
                error_content = e.read().decode('utf-8', errors='ignore')
                logger.log(f'Snow: Error response: {error_content[:300]}', log_utils.LOGDEBUG)
        except urllib.error.URLError as e:
            logger.log(f'Snow: URL Error: {e.reason} - {url}', log_utils.LOGWARNING)
        except Exception as e:
            logger.log(f'Snow: Request error: {e} - {url}', log_utils.LOGWARNING)
            import traceback
            logger.log(f'Snow: Request traceback: {traceback.format_exc()}', log_utils.LOGDEBUG)
        
        return ''

    @classmethod
    def get_settings(cls):
        settings = super(cls, cls).get_settings()
        name = cls.get_name()
        settings.append(f'         <setting id="{name}-result_limit" label="     {i18n("result_limit")}" type="slider" default="10" range="10,100" option="int" visible="true"/>')
        settings.append(f'         <setting id="{name}-min_seeders" label="     {i18n("min_seeders")}" type="slider" default="0" range="0,50" option="int" visible="true"/>')
        return settings 