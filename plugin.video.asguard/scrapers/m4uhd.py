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
import re
import urllib.parse
from bs4 import BeautifulSoup
from asguard_lib import scraper_utils
from asguard_lib.constants import VIDEO_TYPES, QUALITIES
from . import scraper
import log_utils
import kodi

logger = log_utils.Logger.get_logger()
BASE_URL = 'https://m4uhd.cx'

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url') or BASE_URL
        self.domains = ['m4uhd.tv', 'm4uhd.to']
        self.search_path = '/search/%s.html'
        self.ajax_path = '/ajax'
        # Get initial cookie by visiting the base URL
        self.session_cookies = self._get_session_cookies()

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE])

    @classmethod
    def get_name(cls):
        return 'M4UHD'

    def _get_session_cookies(self):
        """Get session cookies by visiting the base URL"""
        try:
            logger.log('[M4UHD] Getting session cookies', log_utils.LOGDEBUG)
            # Make a request to get cookies
            html = self._http_get(self.base_url, cache_limit=0)
            logger.log(f'[M4UHD] HTML: {html}', log_utils.LOGDEBUG)
            if html:
                logger.log('[M4UHD] Successfully obtained session cookies', log_utils.LOGDEBUG)
                return self._get_cookies()  # Use Asguard's cookie handling
            else:
                logger.log('[M4UHD] Failed to get session cookies', log_utils.LOGWARNING)
                return {}
        except Exception as e:
            logger.log(f'[M4UHD] Error getting session cookies: {e}', log_utils.LOGERROR)
            return {}

    def get_sources(self, video):
        logger.log(f'[M4UHD] Starting get_sources for video: {video.title} ({video.year})', log_utils.LOGDEBUG)
        sources = []
        
        if video.video_type != VIDEO_TYPES.MOVIE:
            logger.log(f'[M4UHD] Video type {video.video_type} not supported, only movies', log_utils.LOGWARNING)
            return sources

        source_url = self.get_url(video)
        if not source_url or source_url == scraper_utils.FORCE_NO_MATCH:
            logger.log(f'[M4UHD] No source URL found for video: {source_url}', log_utils.LOGWARNING)
            return sources

        # Construct full URL
        if not source_url.startswith('http'):
            url = scraper_utils.urljoin(self.base_url, source_url)
        else:
            url = source_url
            
        logger.log(f'[M4UHD] Fetching movie page: {url}', log_utils.LOGDEBUG)
        
        html = self._http_get(url, cache_limit=1, cookies=self.session_cookies)
        logger.log(f'[M4UHD] Got HTML length: {len(html) if html else 0}', log_utils.LOGDEBUG)
        
        if not html:
            logger.log('[M4UHD] No HTML received from m4uhd', log_utils.LOGWARNING)
            return sources

        # Extract CSRF token
        csrf_token = self._extract_csrf_token(html)
        if not csrf_token:
            logger.log('[M4UHD] No CSRF token found', log_utils.LOGWARNING)
            return sources

        logger.log(f'[M4UHD] Found CSRF token: {csrf_token[:20]}...', log_utils.LOGDEBUG)

        # Extract server data IDs
        server_ids = self._extract_server_ids(html)
        logger.log(f'[M4UHD] Found {len(server_ids)} server IDs', log_utils.LOGDEBUG)

        if not server_ids:
            logger.log('[M4UHD] No server IDs found', log_utils.LOGWARNING)
            return sources

        # Process each server ID
        ajax_url = scraper_utils.urljoin(self.base_url, self.ajax_path)
        
        for i, server_id in enumerate(server_ids):
            try:
                logger.log(f'[M4UHD] Processing server {i+1}/{len(server_ids)}: {server_id}', log_utils.LOGDEBUG)
                
                # Make AJAX request to get iframe URL
                iframe_url = self._get_iframe_from_ajax(ajax_url, csrf_token, server_id)
                
                if iframe_url:
                    logger.log(f'[M4UHD] Got iframe URL: {iframe_url}', log_utils.LOGDEBUG)
                    
                    # Extract host and determine quality
                    host = urllib.parse.urlparse(iframe_url).hostname
                    if not host:
                        logger.log(f'[M4UHD] No hostname found in iframe URL', log_utils.LOGDEBUG)
                        continue
                    
                    quality = self._determine_quality(video, iframe_url, host)
                    
                    source = {
                        'class': self,
                        'quality': quality,
                        'url': iframe_url,
                        'host': host,
                        'multi-part': False,
                        'rating': None,
                        'views': None,
                        'direct': False,
                    }
                    sources.append(source)
                    logger.log(f'[M4UHD] Added source {len(sources)}: {source}', log_utils.LOGDEBUG)
                    
            except Exception as e:
                logger.log(f'[M4UHD] Error processing server {i+1}: {e}', log_utils.LOGERROR)
                continue

        logger.log(f'[M4UHD] Found {len(sources)} total sources', log_utils.LOGINFO)
        return sources

    def _extract_csrf_token(self, html):
        """Extract CSRF token from HTML"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            csrf_meta = soup.find('meta', {'name': 'csrf-token'})
            if csrf_meta:
                token = csrf_meta.get('content')
                logger.log(f'[M4UHD] Extracted CSRF token from meta tag', log_utils.LOGDEBUG)
                return token
            
            # Fallback: look for token in script tags
            token_match = re.search(r'csrf[_-]?token["\']?\s*[:=]\s*["\']([^"\']+)["\']', html, re.IGNORECASE)
            if token_match:
                token = token_match.group(1)
                logger.log(f'[M4UHD] Extracted CSRF token from script', log_utils.LOGDEBUG)
                return token
                
            logger.log('[M4UHD] No CSRF token found', log_utils.LOGDEBUG)
            return None
            
        except Exception as e:
            logger.log(f'[M4UHD] Error extracting CSRF token: {e}', log_utils.LOGERROR)
            return None

    def _extract_server_ids(self, html):
        """Extract server data IDs from span elements"""
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Look for span elements with data attribute (from scrubs pattern)
            server_spans = soup.find_all('span', {'data': True})
            server_ids = [span.get('data') for span in server_spans if span.get('data')]
            
            logger.log(f'[M4UHD] Found {len(server_ids)} server IDs from spans', log_utils.LOGDEBUG)
            
            if not server_ids:
                # Alternative patterns to look for server data
                alt_patterns = [
                    r'data-server[=\'"]\s*([^\'"]+)[\'"]',
                    r'data-id[=\'"]\s*([^\'"]+)[\'"]',
                    r'data[=\'"]\s*([^\'"]+)[\'"]'
                ]
                
                for pattern in alt_patterns:
                    matches = re.findall(pattern, html, re.IGNORECASE)
                    if matches:
                        server_ids.extend(matches)
                        logger.log(f'[M4UHD] Found {len(matches)} server IDs with pattern: {pattern}', log_utils.LOGDEBUG)
            
            # Remove duplicates and empty values
            server_ids = list(set([sid for sid in server_ids if sid and sid.strip()]))
            
            logger.log(f'[M4UHD] Total unique server IDs: {len(server_ids)}', log_utils.LOGDEBUG)
            return server_ids
            
        except Exception as e:
            logger.log(f'[M4UHD] Error extracting server IDs: {e}', log_utils.LOGERROR)
            return []

    def _get_iframe_from_ajax(self, ajax_url, csrf_token, server_id):
        """Make AJAX request to get iframe URL"""
        try:
            # Prepare AJAX payload (from scrubs pattern)
            payload = {
                '_token': csrf_token,
                'm4u': server_id
            }
            
            headers = {
                'X-Requested-With': 'XMLHttpRequest',
                'X-CSRF-TOKEN': csrf_token,
                'Content-Type': 'application/x-www-form-urlencoded',
                'Referer': self.base_url
            }
            
            logger.log(f'[M4UHD] Making AJAX request to: {ajax_url}', log_utils.LOGDEBUG)
            
            # Make POST request with payload
            response_html = self._http_get(ajax_url, data=payload, headers=headers, 
                                         cookies=self.session_cookies, cache_limit=0)
            
            if not response_html:
                logger.log('[M4UHD] No response from AJAX request', log_utils.LOGDEBUG)
                return None
                
            logger.log(f'[M4UHD] AJAX response length: {len(response_html)}', log_utils.LOGDEBUG)
            
            # Extract iframe src from response
            soup = BeautifulSoup(response_html, 'html.parser')
            iframe = soup.find('iframe', src=True)
            
            if iframe:
                iframe_src = iframe.get('src')
                logger.log(f'[M4UHD] Found iframe in AJAX response: {iframe_src[:50]}...', log_utils.LOGDEBUG)
                
                # Handle relative URLs
                if iframe_src.startswith('//'):
                    iframe_src = 'https:' + iframe_src
                elif iframe_src.startswith('/'):
                    iframe_src = scraper_utils.urljoin(self.base_url, iframe_src)
                    
                return iframe_src
            else:
                logger.log('[M4UHD] No iframe found in AJAX response', log_utils.LOGDEBUG)
                
                # Log response snippet for debugging
                response_snippet = response_html[:200] if response_html else ""
                logger.log(f'[M4UHD] AJAX response snippet: {response_snippet}', log_utils.LOGDEBUG)
                
                return None
                
        except Exception as e:
            logger.log(f'[M4UHD] Error in AJAX request: {e}', log_utils.LOGERROR)
            return None

    def _determine_quality(self, video, url, host):
        """Determine quality using Asguard's quality system"""
        try:
            # Use Asguard's blog_get_quality if available
            if hasattr(scraper_utils, 'blog_get_quality'):
                quality = scraper_utils.blog_get_quality(video, url, host)
                logger.log(f'[M4UHD] blog_get_quality returned: {quality}', log_utils.LOGDEBUG)
                return quality
            
            # Fallback quality determination
            if hasattr(scraper_utils, 'get_quality'):
                quality = scraper_utils.get_quality(video, host)
                logger.log(f'[M4UHD] get_quality returned: {quality}', log_utils.LOGDEBUG)
                return quality
            
            # Ultimate fallback
            return QUALITIES.HIGH
            
        except Exception as e:
            logger.log(f'[M4UHD] Error determining quality: {e}', log_utils.LOGDEBUG)
            return QUALITIES.HIGH

    def search(self, video_type, title, year, season=''):
        """Search for content on m4uhd.tv"""
        logger.log(f'[M4UHD] Starting search: type={video_type}, title={title}, year={year}', log_utils.LOGDEBUG)
        results = []
        
        try:
            # Clean title for URL (like scrubs geturl function)
            clean_title = self._clean_title_for_url(title)
            search_url = scraper_utils.urljoin(self.base_url, self.search_path % clean_title)
            
            logger.log(f'[M4UHD] Search URL: {search_url}', log_utils.LOGDEBUG)
            
            html = self._http_get(search_url, cache_limit=1, cookies=self.session_cookies)
            if not html:
                logger.log('[M4UHD] No HTML received from search', log_utils.LOGWARNING)
                return results
                
            logger.log(f'[M4UHD] Search HTML length: {len(html)}', log_utils.LOGDEBUG)
            
            # Parse search results
            soup = BeautifulSoup(html, 'html.parser')
            
            # Look for search result items (from scrubs pattern: div.item)
            result_items = soup.find_all('div', class_='item')
            logger.log(f'[M4UHD] Found {len(result_items)} result items', log_utils.LOGDEBUG)
            
            # Expected search term (title + year)
            expected_term = f'{title} ({year})'
            
            for item in result_items:
                try:
                    # Extract title link
                    title_link = item.find('a', href=True, title=True)
                    if not title_link:
                        continue
                        
                    result_url = title_link.get('href')
                    result_title = title_link.get('title')
                    
                    if not result_url or not result_title:
                        continue
                    
                    logger.log(f'[M4UHD] Found result: {result_title} - {result_url}', log_utils.LOGDEBUG)
                    
                    # Check if this matches what we're looking for (exact match like scrubs)
                    normalized_expected = self._normalize_title(expected_term)
                    normalized_result = self._normalize_title(result_title)
                    
                    if normalized_expected == normalized_result:
                        result = {
                            'title': result_title,
                            'year': year,
                            'url': result_url
                        }
                        results.append(result)
                        logger.log(f'[M4UHD] Added exact match result: {result}', log_utils.LOGDEBUG)
                        break  # Found exact match, no need to continue
                        
                except Exception as e:
                    logger.log(f'[M4UHD] Error parsing search result: {e}', log_utils.LOGDEBUG)
                    continue
                    
        except Exception as e:
            logger.log(f'[M4UHD] Search error: {e}', log_utils.LOGERROR)
            
        logger.log(f'[M4UHD] Search completed, found {len(results)} results', log_utils.LOGDEBUG)
        return results

    def _clean_title_for_url(self, title):
        """Clean title for URL use (similar to scrubs cleantitle.geturl)"""
        try:
            # Remove special characters and spaces, replace with hyphens
            clean = re.sub(r'[^\w\s-]', '', title.lower())
            clean = re.sub(r'[-\s]+', '-', clean)
            clean = clean.strip('-')
            logger.log(f'[M4UHD] Cleaned title: {title} -> {clean}', log_utils.LOGDEBUG)
            return clean
        except Exception as e:
            logger.log(f'[M4UHD] Error cleaning title: {e}', log_utils.LOGERROR)
            return title.lower().replace(' ', '-')

    def _normalize_title(self, title):
        """Normalize title for comparison (similar to scrubs cleantitle.get_plus)"""
        try:
            # Convert to lowercase and replace spaces with plus
            normalized = re.sub(r'[^\w\s().-]', '', title.lower())
            normalized = re.sub(r'\s+', '+', normalized.strip())
            return normalized
        except Exception:
            return title.lower()

    def get_url(self, video):
        """Generate URL for the video based on its type"""
        if video.video_type == VIDEO_TYPES.MOVIE:
            return self._movie_url(video)
        return None

    def _movie_url(self, video):
        """Generate movie URL - search first to get the exact URL"""
        search_results = self.search(VIDEO_TYPES.MOVIE, video.title, video.year)
        if search_results:
            return search_results[0]['url']
        return None

    def resolve_link(self, link):
        """Resolve the final link if needed"""
        return link