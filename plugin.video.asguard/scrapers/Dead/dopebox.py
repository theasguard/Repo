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
import requests
import json
import log_utils
import kodi
import dom_parser2
from asguard_lib import scraper_utils
from asguard_lib.constants import FORCE_NO_MATCH
from asguard_lib.constants import QUALITIES
from asguard_lib.constants import VIDEO_TYPES
from asguard_lib.utils2 import i18n
from . import scraper

try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)

logger = log_utils.Logger.get_logger()

BASE_URL = 'https://dopebox.to'
BACKUP_DOMAINS = ['sflix.se', 'sflix.to', 'theflixer.tv', 'f2movies.to']

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting('%s-base_url' % (self.get_name())) or BASE_URL
        self.session = requests.Session()
        
    def _http_get_with_retry(self, url, **kwargs):
        """Enhanced HTTP get with anti-blocking and compression handling"""
        import time
        import gzip
        import requests
        
        logger.log('DopeBox: Attempting to access: %s' % url, log_utils.LOGDEBUG)
        
        # Enhanced headers - DISABLE compression to avoid issues
        headers = kwargs.get('headers', {})
        headers.update({
            'User-Agent': scraper_utils.get_ua(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'identity',  # Request uncompressed content to avoid decompression issues
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'DNT': '1',
            'Pragma': 'no-cache',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
            'Referer': self.base_url
        })
        
        # Use direct requests instead of parent method to handle compression properly
        session = getattr(self, 'session', None) or requests.Session()
        
        for attempt in range(3):
            try:
                logger.log('DopeBox: Attempt %d for %s' % (attempt + 1, url), log_utils.LOGDEBUG)
                
                response = session.get(url, headers=headers, timeout=15, stream=False)
                
                logger.log('DopeBox: Response status: %d, headers: %s' % (
                    response.status_code, dict(response.headers)), log_utils.LOGDEBUG)
                
                if response.status_code == 200:
                    # Check what compression was used
                    content_encoding = response.headers.get('Content-Encoding', '').lower()
                    logger.log('DopeBox: Content-Encoding: %s' % content_encoding, log_utils.LOGDEBUG)
                    
                    # Skip automatic decompression and handle manually
                    raw_content = response.content
                    logger.log('DopeBox: Raw content length: %d bytes' % len(raw_content), log_utils.LOGDEBUG)
                    
                    content = None
                    
                    # Try different decompression methods based on encoding
                    if 'br' in content_encoding:
                        try:
                            import brotli
                            content = brotli.decompress(raw_content).decode('utf-8', errors='ignore')
                            logger.log('DopeBox: Manual Brotli decompression successful (%d bytes)' % len(content), log_utils.LOGDEBUG)
                        except ImportError:
                            logger.log('DopeBox: Brotli module not available - trying parent scraper method', log_utils.LOGDEBUG)
                            # Immediately try parent scraper method for Brotli content
                            try:
                                content = super(Scraper, self)._http_get(url, cache_limit=0, **kwargs)
                                if content and len(content) > 500 and '<' in content:
                                    logger.log('DopeBox: Parent method handled Brotli successfully (%d bytes)' % len(content), log_utils.LOGDEBUG)
                                    return content
                                else:
                                    logger.log('DopeBox: Parent method failed for Brotli content', log_utils.LOGDEBUG)
                            except Exception as parent_e:
                                logger.log('DopeBox: Parent method failed: %s' % str(parent_e), log_utils.LOGDEBUG)
                        except Exception as e:
                            logger.log('DopeBox: Brotli decompression failed: %s' % str(e), log_utils.LOGDEBUG)
                    
                    elif 'gzip' in content_encoding:
                        try:
                            content = gzip.decompress(raw_content).decode('utf-8', errors='ignore')
                            logger.log('DopeBox: Manual gzip decompression successful (%d bytes)' % len(content), log_utils.LOGDEBUG)
                        except Exception as e:
                            logger.log('DopeBox: Gzip decompression failed: %s' % str(e), log_utils.LOGDEBUG)
                    
                    elif 'deflate' in content_encoding:
                        try:
                            import zlib
                            content = zlib.decompress(raw_content).decode('utf-8', errors='ignore')
                            logger.log('DopeBox: Manual deflate decompression successful (%d bytes)' % len(content), log_utils.LOGDEBUG)
                        except Exception as e:
                            logger.log('DopeBox: Deflate decompression failed: %s' % str(e), log_utils.LOGDEBUG)
                    
                    else:
                        # No compression or unknown compression
                        try:
                            content = raw_content.decode('utf-8', errors='ignore')
                            logger.log('DopeBox: Raw bytes to string conversion (%d bytes)' % len(content), log_utils.LOGDEBUG)
                        except Exception as e:
                            logger.log('DopeBox: Raw bytes decoding failed: %s' % str(e), log_utils.LOGDEBUG)
                    
                    # Verify we got valid HTML content
                    if content and len(content) > 100:
                        # Check for actual HTML tags, not just < and >
                        if '<html' in content.lower() or '<body' in content.lower() or '<div' in content.lower():
                            logger.log('DopeBox: Valid HTML content received (%d chars)' % len(content), log_utils.LOGDEBUG)
                            return content
                        else:
                            logger.log('DopeBox: Content does not appear to be HTML. Preview: %s' % content[:200], log_utils.LOGDEBUG)
                    else:
                        logger.log('DopeBox: No valid content after decompression attempts', log_utils.LOGDEBUG)
                        
                elif response.status_code == 403:
                    logger.log('DopeBox: Access forbidden (403) - possible blocking', log_utils.LOGDEBUG)
                elif response.status_code == 503:
                    logger.log('DopeBox: Service unavailable (503) - possible rate limiting', log_utils.LOGDEBUG)
                else:
                    logger.log('DopeBox: HTTP error: %d' % response.status_code, log_utils.LOGDEBUG)
                    
            except Exception as e:
                logger.log('DopeBox: Request attempt %d failed: %s' % (attempt + 1, str(e)), log_utils.LOGDEBUG)
            
            if attempt < 2:  # Not the last attempt
                time.sleep(2 * (attempt + 1))  # Increasing delay
        
        # Try backup domains as last resort
        logger.log('DopeBox: All direct attempts failed, trying backup domains', log_utils.LOGDEBUG)
        original_hostname = urllib.parse.urlparse(self.base_url).hostname
        
        for backup_domain in BACKUP_DOMAINS[:2]:  # Try first 2 backup domains
            try:
                backup_url = url.replace(original_hostname, backup_domain)
                logger.log('DopeBox: Trying backup domain: %s' % backup_url, log_utils.LOGDEBUG)
                
                response = session.get(backup_url, headers=headers, timeout=15)
                
                if response.status_code == 200:
                    content = response.text
                    if content and '<' in content and '>' in content:
                        logger.log('DopeBox: Backup domain %s successful' % backup_domain, log_utils.LOGDEBUG)
                        # Update base_url to working domain
                        self.base_url = 'https://' + backup_domain
                        return content
                        
            except Exception as e:
                logger.log('DopeBox: Backup domain %s failed: %s' % (backup_domain, str(e)), log_utils.LOGDEBUG)
                continue
        
        # Final fallback - try parent scraper's HTTP method
        logger.log('DopeBox: Trying parent scraper HTTP method as final fallback', log_utils.LOGDEBUG)
        try:
            result = super(Scraper, self)._http_get(url, cache_limit=0, **kwargs)
            if result and len(result) > 500 and '<' in result and '>' in result:
                logger.log('DopeBox: Parent HTTP method successful (%d bytes)' % len(result), log_utils.LOGDEBUG)
                return result
            else:
                logger.log('DopeBox: Parent HTTP method failed or returned invalid content', log_utils.LOGDEBUG)
        except Exception as e:
            logger.log('DopeBox: Parent HTTP method failed: %s' % str(e), log_utils.LOGDEBUG)
        
        logger.log('DopeBox: All attempts failed - no content retrieved', log_utils.LOGWARNING)
        return None

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'DopeBox'

    def get_sources(self, video):
        hosters = []
        source_url = self.get_url(video)
        
        if not source_url or source_url == FORCE_NO_MATCH:
            return hosters

        url = scraper_utils.urljoin(self.base_url, source_url)
        logger.log('DopeBox: Getting sources for: %s' % url, log_utils.LOGDEBUG)
        html = self._http_get_with_retry(url)
            
        if not html or html == FORCE_NO_MATCH:
            return hosters

        try:
            # Extract item ID from the page - try multiple methods
            item_id = None
            
            # Method 1: data-id attribute
            item_id_match = dom_parser2.parse_dom(html, 'div', req='data-id')
            if item_id_match:
                item_id = item_id_match[0].attrs['data-id']
                logger.log('DopeBox: Found item ID via data-id: %s' % item_id, log_utils.LOGDEBUG)
            
            # Method 2: Extract from URL patterns in HTML 
            if not item_id:
                id_match = re.search(r'/ajax/movie/episodes/(\d+)', html)
                if not id_match:
                    id_match = re.search(r'/ajax/v2/tv/seasons/(\d+)', html)
                if not id_match:
                    id_match = re.search(r'data-id="(\d+)"', html)
                if not id_match:
                    # Extract from current URL if it has an ID
                    id_match = re.search(r'-(\d+)$', source_url)
                    
                if id_match:
                    item_id = id_match.group(1)
                    logger.log('DopeBox: Found item ID via regex: %s' % item_id, log_utils.LOGDEBUG)
            
            if not item_id:
                logger.log('DopeBox: Could not find item ID - trying alternative parsing', log_utils.LOGDEBUG)
                # Try to find streaming links directly in the HTML
                direct_links = re.findall(r'(https?://[^\s"\'<>]+(?:mp4|m3u8|mkv))', html)
                if direct_links:
                    logger.log('DopeBox: Found %d direct streaming links' % len(direct_links), log_utils.LOGDEBUG)
                    for link in direct_links[:5]:  # Limit to first 5
                        host = urllib.parse.urlparse(link).hostname
                        if host:
                            quality = scraper_utils.get_quality(video, link, host)
                            hoster = {
                                'class': self,
                                'multi-part': False,
                                'host': host,
                                'quality': quality,
                                'views': None,
                                'rating': None,
                                'url': link,
                                'direct': True
                            }
                            hosters.append(hoster)
                    return hosters
                else:
                    return hosters
                
            logger.log('DopeBox: Using item ID: %s' % item_id, log_utils.LOGDEBUG)

            if video.video_type == VIDEO_TYPES.MOVIE:
                hosters.extend(self._get_movie_sources(item_id, video))
            elif video.video_type == VIDEO_TYPES.EPISODE:
                hosters.extend(self._get_episode_sources(item_id, video))

        except Exception as e:
            logger.log('DopeBox: Error getting sources: %s' % str(e), log_utils.LOGWARNING)

        return hosters

    def _get_movie_sources(self, item_id, video):
        """Get sources for movies"""
        hosters = []
        
        try:
            servers_url = scraper_utils.urljoin(self.base_url, '/ajax/movie/episodes/%s' % item_id)
            servers_html = self._http_get_with_retry(servers_url)
            
            if not servers_html:
                return hosters
                
            # Extract server IDs
            server_ids = []
            server_id_matches = dom_parser2.parse_dom(servers_html, 'a', req='data-id')
            if server_id_matches:
                server_ids.extend([match.attrs['data-id'] for match in server_id_matches])
            else:
                # Try alternative attribute
                server_id_matches = dom_parser2.parse_dom(servers_html, 'a', req='data-linkid')
                if server_id_matches:
                    server_ids.extend([match.attrs['data-linkid'] for match in server_id_matches])
            
            logger.log('DopeBox: Found %d movie servers' % len(server_ids), log_utils.LOGDEBUG)
            
            # Get links from each server
            for server_id in server_ids:
                try:
                    stream_url = self._get_stream_url_from_server(server_id)
                    
                    if stream_url:
                        host = urllib.parse.urlparse(stream_url).hostname
                        if host:
                            quality = scraper_utils.get_quality(video, stream_url, host)
                            hoster = {
                                'class': self,
                                'multi-part': False,
                                'host': host,
                                'quality': quality,
                                'views': None,
                                'rating': None,
                                'url': stream_url,
                                'direct': False,
                                'debridonly': False
                            }
                            hosters.append(hoster)
                            logger.log('DopeBox: Found movie source: %s from %s' % (stream_url, host), log_utils.LOGDEBUG)
                            
                except Exception as e:
                    logger.log('DopeBox: Error getting movie link: %s' % str(e), log_utils.LOGDEBUG)
                    continue
                    
        except Exception as e:
            logger.log('DopeBox: Error getting movie sources: %s' % str(e), log_utils.LOGWARNING)
            
        return hosters

    def _get_episode_sources(self, item_id, video):
        """Get sources for TV episodes"""
        hosters = []
        
        try:
            # First get seasons
            seasons_url = scraper_utils.urljoin(self.base_url, '/ajax/v2/tv/seasons/%s' % item_id)
            seasons_html = self._http_get_with_retry(seasons_url)
            
            if not seasons_html:
                return hosters
            
            # Find the season we need
            season_links = dom_parser2.parse_dom(seasons_html, 'a', req='data-id')
            season_titles = dom_parser2.parse_dom(seasons_html, 'a')
            
            season_id = None
            check_season = 'Season %s' % video.season
            
            for i, season_title in enumerate(season_titles):
                if len(season_links) > i and check_season == season_title.content.strip():
                    season_id = season_links[i].attrs['data-id']
                    break
                    
            if not season_id:
                logger.log('DopeBox: Could not find season %s' % video.season, log_utils.LOGDEBUG)
                return hosters
                
            logger.log('DopeBox: Found season ID: %s' % season_id, log_utils.LOGDEBUG)
            
            # Get episodes for this season
            episodes_url = scraper_utils.urljoin(self.base_url, '/ajax/v2/season/episodes/%s' % season_id)
            episodes_html = self._http_get_with_retry(episodes_url)
            
            if not episodes_html:
                return hosters
                
            # Find the episode we need
            episode_ids = dom_parser2.parse_dom(episodes_html, 'div', req='data-id')
            episode_titles = dom_parser2.parse_dom(episodes_html, 'img', req='title')
            
            episode_id = None
            check_episode = 'Episode %s:' % video.episode
            
            for i, episode_title in enumerate(episode_titles):
                if len(episode_ids) > i and check_episode in episode_title.attrs['title']:
                    episode_id = episode_ids[i].attrs['data-id']
                    break
                    
            if not episode_id:
                logger.log('DopeBox: Could not find episode %s' % video.episode, log_utils.LOGDEBUG)
                return hosters
                
            logger.log('DopeBox: Found episode ID: %s' % episode_id, log_utils.LOGDEBUG)
            
            # Get servers for this episode
            servers_url = scraper_utils.urljoin(self.base_url, '/ajax/v2/episode/servers/%s' % episode_id)
            servers_html = self._http_get_with_retry(servers_url)
            
            if not servers_html:
                return hosters
                
            # Extract server IDs
            server_ids = []
            server_id_matches = dom_parser2.parse_dom(servers_html, 'a', req='data-id')
            if server_id_matches:
                server_ids.extend([match.attrs['data-id'] for match in server_id_matches])
            else:
                # Try alternative attribute
                server_id_matches = dom_parser2.parse_dom(servers_html, 'a', req='data-linkid')
                if server_id_matches:
                    server_ids.extend([match.attrs['data-linkid'] for match in server_id_matches])
            
            logger.log('DopeBox: Found %d episode servers' % len(server_ids), log_utils.LOGDEBUG)
            
            # Get links from each server
            for server_id in server_ids:
                try:
                    stream_url = self._get_stream_url_from_server(server_id)
                    
                    if stream_url:
                        host = urllib.parse.urlparse(stream_url).hostname
                        if host:
                            quality = scraper_utils.get_quality(video, stream_url, host)
                            hoster = {
                                'class': self,
                                'multi-part': False,
                                'host': host,
                                'quality': quality,
                                'views': None,
                                'rating': None,
                                'url': stream_url,
                                'direct': False,
                                'debridonly': False
                            }
                            hosters.append(hoster)
                            logger.log('DopeBox: Found episode source: %s from %s' % (stream_url, host), log_utils.LOGDEBUG)
                            
                except Exception as e:
                    logger.log('DopeBox: Error getting episode link: %s' % str(e), log_utils.LOGDEBUG)
                    continue
                    
        except Exception as e:
            logger.log('DopeBox: Error getting episode sources: %s' % str(e), log_utils.LOGWARNING)
            
        return hosters

    def _get_stream_url_from_server(self, server_id):
        """Get stream URL from server ID with proper headers and fallback endpoints"""
        try:
            # Try the original get_link endpoint first
            link_url = scraper_utils.urljoin(self.base_url, '/ajax/get_link/%s' % server_id)
            
            headers = {
                'Host': urllib.parse.urlparse(self.base_url).hostname,
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'X-Requested-With': 'XMLHttpRequest',
                'User-Agent': scraper_utils.get_ua(),
                'Referer': self.base_url,
                'Accept-Encoding': 'gzip, deflate, br',
                'Accept-Language': 'en-US,en;q=0.9'
            }
            
            response = self._http_get_with_retry(link_url, headers=headers)
            logger.log('DopeBox: Link response for %s: %s bytes' % (server_id, len(response) if response else 0), log_utils.LOGDEBUG)
            
            if response:
                try:
                    json_data = json.loads(response)
                    if 'link' in json_data:
                        return json_data['link']
                    elif 'url' in json_data:
                        return json_data['url']
                except (ValueError, TypeError):
                    # Not JSON, might be HTML - check if it's a 404 page
                    if '404' in response and 'page doesn\'t exist' in response:
                        logger.log('DopeBox: 404 error for server %s' % server_id, log_utils.LOGDEBUG)
                    else:
                        logger.log('DopeBox: Non-JSON response: %s' % response[:200], log_utils.LOGDEBUG)
            
            # Try alternative endpoint patterns if first fails
            alt_endpoints = [
                f'/ajax/sources/{server_id}',
                f'/ajax/embed-{server_id}',
                f'/ajax/v2/sources/{server_id}',
                f'/ajax/v2/episode/sources/{server_id}',
                f'/ajax/episode/info?id={server_id}'
            ]
            
            for endpoint in alt_endpoints:
                try:
                    alt_url = scraper_utils.urljoin(self.base_url, endpoint)
                    alt_response = self._http_get_with_retry(alt_url, headers=headers)
                    
                    if alt_response:
                        try:
                            alt_data = json.loads(alt_response)
                            if 'link' in alt_data:
                                logger.log('DopeBox: Found working endpoint: %s' % endpoint, log_utils.LOGDEBUG)
                                return alt_data['link']
                            elif 'url' in alt_data:
                                return alt_data['url']
                        except (ValueError, TypeError):
                            continue
                except:
                    continue
                    
        except Exception as e:
            logger.log('DopeBox: Stream URL request failed: %s' % str(e), log_utils.LOGDEBUG)
            
        return None

    def search(self, video_type, title, year, season=''):
        results = []
            
        try:
            # Try search first since direct URLs need IDs which we get from search
            logger.log('DopeBox: Using search approach for "%s"' % title, log_utils.LOGDEBUG)
            
            # Clean and encode title properly for DopeBox search
            clean_title = scraper_utils.cleanse_title(title).lower()
            # Replace spaces with + and encode special characters
            encoded_title = urllib.parse.quote_plus(clean_title)
            search_url = scraper_utils.urljoin(self.base_url, '/search/%s' % encoded_title)
            
            logger.log('DopeBox: Searching for "%s" at %s' % (title, search_url), log_utils.LOGDEBUG)
            
            # Use enhanced anti-blocking HTTP method
            html = self._http_get_with_retry(search_url)
            if not html:
                logger.log('DopeBox: No HTML received for search', log_utils.LOGDEBUG)
                return results
            
            logger.log('DopeBox: Received %d bytes of search results' % len(html), log_utils.LOGDEBUG)
            
            # Clean HTML to handle encoding issues
            try:
                # Remove null characters and clean encoding
                clean_html = html.replace('\x00', '').encode('utf-8', 'ignore').decode('utf-8', 'ignore')
                html = clean_html
            except Exception as e:
                logger.log('DopeBox: HTML cleaning failed: %s' % str(e), log_utils.LOGDEBUG)
            
            # Parse DopeBox search results - based on actual structure from search page
            logger.log('DopeBox: Parsing search results with DopeBox-specific structure', log_utils.LOGDEBUG)
            
            # Parse DopeBox search results based on actual structure
            # Pattern from real search: "## Title" followed by "Watch now" link
            search_results = []
            
            # Method 1: Find direct links with full URLs (if they exist in HTML)
            tv_links = re.findall(r'href="(/tv/watch-[^"]*-online-hd-\d+)"', html)
            movie_links = re.findall(r'href="(/movie/watch-[^"]*-online-hd-\d+)"', html)
            
            if tv_links or movie_links:
                search_results.extend([(link, 'tv', None) for link in tv_links])
                search_results.extend([(link, 'movie', None) for link in movie_links])
                logger.log('DopeBox: Found %d direct links (%d TV, %d movies)' % (
                    len(search_results), len(tv_links), len(movie_links)), log_utils.LOGDEBUG)
            
            # Method 2: Parse the actual search structure - titles with watch links
            if not search_results:
                logger.log('DopeBox: No direct links found, parsing search structure', log_utils.LOGDEBUG)
                
                # Find all title patterns: ## Title
                title_matches = re.finditer(r'##\s*([^#\n]+?)(?=\s*(?:Watch now|\n|$))', html, re.MULTILINE)
                titles_found = []
                
                for match in title_matches:
                    found_title = match.group(1).strip()
                    if found_title and len(found_title) > 1:
                        titles_found.append(found_title)
                
                logger.log('DopeBox: Found %d titles: %s' % (len(titles_found), titles_found[:5]), log_utils.LOGDEBUG)
                
                # Find year/type patterns: 2006 **TV** or 2024 **Movie**
                year_type_pattern = r'(\d{4})\s*\*\*\s*(TV|Movie)\s*\*\*'
                year_type_matches = re.findall(year_type_pattern, html)
                logger.log('DopeBox: Found %d year/type pairs: %s' % (len(year_type_matches), year_type_matches[:5]), log_utils.LOGDEBUG)
                
                # Try to match titles with years/types
                for i, found_title in enumerate(titles_found):
                    # Get corresponding year/type if available
                    result_year = year
                    result_type = 'tv'  # default
                    
                    if i < len(year_type_matches):
                        result_year, type_str = year_type_matches[i]
                        result_type = 'tv' if type_str.lower() == 'tv' else 'movie'
                    
                    # Create a constructed URL (we'll have to guess the ID)
                    clean_title = found_title.lower().replace(' ', '-').replace(':', '')
                    constructed_url = '/%s/watch-%s-online-hd' % (result_type, clean_title)
                    
                    search_results.append((constructed_url, result_type, found_title))
                
                logger.log('DopeBox: Constructed %d results from search structure' % len(search_results), log_utils.LOGDEBUG)
            
            items = search_results
            found_structure = 'search-structure' if search_results else None
            
            if found_structure:
                logger.log('DopeBox: Found %d items using %s structure' % (len(items), found_structure), log_utils.LOGDEBUG)
            else:
                logger.log('DopeBox: No search results found - showing HTML preview', log_utils.LOGDEBUG)
                # Show cleaned HTML for debugging
                safe_html = html[:800].replace('\n', ' ').replace('\r', '')
                logger.log('DopeBox: HTML preview: %s' % safe_html, log_utils.LOGDEBUG)
            
            for i, item in enumerate(items):
                try:
                    logger.log('DopeBox: Processing item %d with structure %s' % (i+1, found_structure), log_utils.LOGDEBUG)
                    
                    # Item is now a tuple: (url, type, title) where title can be None
                    result_url, item_type, extracted_title = item
                    
                    # Get title - either extracted or from URL
                    if extracted_title:
                        result_title = extracted_title
                    else:
                        # Extract title from URL as fallback
                        if '-online-hd-' in result_url:
                            # Pattern: /tv/watch-dexter-online-hd-39448 -> dexter
                            title_match = re.search(r'/(?:tv|movie)/watch-([^-]+(?:-[^-]+)*)-online-hd', result_url)
                        else:
                            # Pattern: /tv/watch-dexter-online-hd -> dexter (no ID)
                            title_match = re.search(r'/(?:tv|movie)/watch-([^-]+(?:-[^-]+)*)-online-hd', result_url)
                        
                        if title_match:
                            result_title = title_match.group(1).replace('-', ' ').title()
                        else:
                            result_title = None
                    
                    # Use provided year as fallback
                    result_year = year
                    
                    # Determine if this is a movie or TV show
                    is_movie = item_type == 'movie' or result_url.startswith('/movie/')
                    is_tvshow = item_type == 'tv' or result_url.startswith('/tv/')
                    
                    logger.log('DopeBox: Extracted - URL: %s, Title: %s, Type: %s' % (
                        result_url, result_title or 'Unknown', 'Movie' if is_movie else 'TV Show'), log_utils.LOGDEBUG)
                    
                    if result_url and result_title:
                        # Check if this matches our search and video type
                        title_match_check = scraper_utils.normalize_title(title) in scraper_utils.normalize_title(result_title)
                        
                        # Also check type compatibility
                        type_match = False
                        if video_type == VIDEO_TYPES.MOVIE and is_movie:
                            type_match = True
                        elif video_type in [VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE] and is_tvshow:
                            type_match = True
                        
                        logger.log('DopeBox: Match check - Title: %s, Type: %s' % (title_match_check, type_match), log_utils.LOGDEBUG)
                        
                        if title_match_check and type_match:
                            # For constructed URLs without IDs, we need to test if they exist
                            if not re.search(r'-\d+$', result_url):
                                # URL doesn't have ID, try to get the real URL by testing
                                logger.log('DopeBox: Testing constructed URL: %s' % result_url, log_utils.LOGDEBUG)
                                test_url = scraper_utils.urljoin(self.base_url, result_url)
                                test_html = self._http_get_with_retry(test_url)
                                
                                if test_html and len(test_html) > 1000:
                                    # Found the page, try to extract real ID
                                    id_match = re.search(r'data-id="(\d+)"', test_html)
                                    if id_match:
                                        item_id = id_match.group(1)
                                        result_url = result_url + '-' + item_id
                                        logger.log('DopeBox: Found real URL with ID: %s' % result_url, log_utils.LOGDEBUG)
                                    else:
                                        logger.log('DopeBox: Could not find ID for constructed URL', log_utils.LOGDEBUG)
                                else:
                                    logger.log('DopeBox: Constructed URL test failed', log_utils.LOGDEBUG)
                                    continue
                            
                            # Create result entry
                            result = {
                                'url': scraper_utils.pathify_url(result_url),
                                'title': scraper_utils.cleanse_title(result_title),
                                'year': result_year
                            }
                            results.append(result)
                            logger.log('DopeBox: Found search result: %s (%s) - %s' % (result_title, result_year, 'Movie' if is_movie else 'TV Show'), log_utils.LOGDEBUG)
                        else:
                            logger.log('DopeBox: Skipping non-matching result: %s (title_match: %s, type_match: %s)' % (result_title, title_match_check, type_match), log_utils.LOGDEBUG)
                    else:
                        logger.log('DopeBox: Could not extract title from item: %s' % str(item), log_utils.LOGDEBUG)
                        
                except Exception as e:
                    logger.log('DopeBox: Error processing search result: %s' % str(e), log_utils.LOGDEBUG)
                    continue
                    
        except Exception as e:
            logger.log('DopeBox: Search error: %s' % str(e), log_utils.LOGWARNING)
            
        return results

    def get_url(self, video):
        """Get URL for video based on type"""
        return self._default_get_url(video)

    def _get_episode_url(self, show_url, video):
        """Get episode URL from show page - DopeBox uses AJAX so we return show URL"""
        # For DopeBox, episodes are accessed via AJAX from the show page
        # So we just return the show URL and handle episode selection in get_sources
        return show_url
