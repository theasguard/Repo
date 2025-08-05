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
import kodi
import log_utils
from bs4 import BeautifulSoup
from asguard_lib import scraper_utils
from asguard_lib.constants import FORCE_NO_MATCH, VIDEO_TYPES, QUALITIES
from asguard_lib.utils2 import i18n
from . import scraper

logger = log_utils.Logger.get_logger()

BASE_URL = 'https://swatchseries.is'
BACKUP_URLS = [
    'https://swatchseries.is',
    'https://watchseries.is', 
    'https://ww1.swatchseries.is',
    'https://ww2.swatchseries.is',
    'https://swatchseries.to',
    'https://watchseries.to'
]
SEARCH_URL = '/search/%s'

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url') or BASE_URL
        logger.log(f'WatchSeries using base URL: {self.base_url}', log_utils.LOGDEBUG)

    def _try_backup_urls(self, path, headers=None):
        """
        Try multiple backup URLs if the main one fails
        """
        # First try the configured base URL
        urls_to_try = [self.base_url] + [url for url in BACKUP_URLS if url != self.base_url]
        
        for base_url in urls_to_try:
            try:
                full_url = scraper_utils.urljoin(base_url, path)
                logger.log(f'Trying URL: {full_url}', log_utils.LOGDEBUG)
                
                html = self._http_get(full_url, headers=headers, cache_limit=1)
                if html and len(html) > 1000:  # Got substantial content
                    logger.log(f'Success with URL: {base_url}', log_utils.LOGDEBUG)
                    # Update the base URL for future requests
                    self.base_url = base_url
                    return html
                    
            except Exception as e:
                logger.log(f'Failed with {base_url}: {e}', log_utils.LOGDEBUG)
                continue
        
        return None

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'WatchSeries'

    def get_sources(self, video):
        """
        Extract streaming sources from episode/movie page
        """
        hosters = []
        source_url = self.get_url(video)
        if not source_url or source_url == FORCE_NO_MATCH:
            return hosters

        page_url = scraper_utils.urljoin(self.base_url, source_url)
        logger.log(f'WatchSeries source URL: {page_url}', log_utils.LOGDEBUG)
        
        # Store page URL for movie ID extraction
        self._current_page_url = page_url

        try:
            # Add headers to bypass anti-bot protection
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Referer': self.base_url
            }
            
            html = self._http_get(page_url, headers=headers, cache_limit=0.5)
            if not html:
                return hosters

            logger.log(f'WatchSeries page HTML length: {len(html)}', log_utils.LOGDEBUG)
            logger.log(f'WatchSeries page HTML sample: {html[:8000]}', log_utils.LOGDEBUG)
            
            # Analyze the HTML structure for debugging
            self._analyze_html_structure(html)
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # sWatchSeries specific extraction - look for AJAX endpoints and embedded data
            hosters.extend(self._extract_swatchseries_sources(soup, page_url, headers))
            
            # If no sources found, try generic extraction
            if not hosters:
                hosters.extend(self._extract_generic_sources(soup, page_url))
            
            # If still no sources, try alternative extraction
            if not hosters:
                hosters.extend(self._extract_sources_alternative(soup, video))
            
        except Exception as e:
            logger.log(f'Error getting WatchSeries sources: {e}', log_utils.LOGWARNING)
        
        # Remove duplicate sources based on URL
        unique_hosters = []
        seen_urls = set()
        
        for hoster in hosters:
            url = hoster.get('url', '')
            if url and url not in seen_urls:
                seen_urls.add(url)
                unique_hosters.append(hoster)
        
        logger.log(f'WatchSeries found {len(unique_hosters)} unique sources (filtered from {len(hosters)} total)', log_utils.LOGDEBUG)
        
        # Debug: Log all found sources
        if unique_hosters:
            logger.log('=== Found Sources ===', log_utils.LOGDEBUG)
            for i, hoster in enumerate(unique_hosters):
                host = hoster.get('host', 'Unknown')
                url = hoster.get('url', 'No URL')
                logger.log(f'Source {i+1}: {host} -> {url}', log_utils.LOGDEBUG)
            logger.log('=== End Sources ===', log_utils.LOGDEBUG)
        else:
            logger.log('No sources found - checking what was processed:', log_utils.LOGDEBUG)
        
        return unique_hosters

    def _analyze_html_structure(self, html):
        """
        Analyze HTML structure for debugging source extraction
        """
        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Log key structural elements
            logger.log('=== HTML Structure Analysis ===', log_utils.LOGDEBUG)
            
            # Look for movie ID in the HTML for AJAX calls
            movie_id_patterns = [
                r'data-id["\']?\s*[:=]\s*["\']?(\d+)["\']?',
                r'movie\.id\s*[:=]\s*["\']?(\d+)["\']?',
                r'var\s+movie_id\s*=\s*["\']?(\d+)["\']?',
                r'/movie/watch-[^/]*-(\d+)',  # Updated pattern
                r'/watch-[^/]*-(\d+)'
            ]
            
            found_movie_id = None
            logger.log(f'Searching for movie ID in HTML (length: {len(html)})', log_utils.LOGDEBUG)
            
            for pattern in movie_id_patterns:
                matches = re.findall(pattern, html, re.I)  # Find all matches
                if matches:
                    found_movie_id = matches[0]  # Take first match
                    logger.log(f'Found movie ID in HTML via pattern {pattern}: {found_movie_id} (total matches: {len(matches)})', log_utils.LOGDEBUG)
                    break
                else:
                    logger.log(f'Pattern {pattern} found no matches', log_utils.LOGDEBUG)
            
            # Also check the current page URL for movie ID
            if not found_movie_id and hasattr(self, '_current_page_url'):
                current_url = getattr(self, '_current_page_url', '')
                logger.log(f'Checking current page URL for movie ID: {current_url}', log_utils.LOGDEBUG)
                for pattern in movie_id_patterns:
                    match = re.search(pattern, current_url, re.I)
                    if match:
                        found_movie_id = match.group(1)
                        logger.log(f'Found movie ID in current URL via pattern {pattern}: {found_movie_id}', log_utils.LOGDEBUG)
                        break
            
            # Look for content-episodes div (where servers get loaded)
            content_episodes = soup.select('#content-episodes')
            if content_episodes:
                logger.log(f'Found #content-episodes div: {len(content_episodes[0].get_text().strip())} chars of content', log_utils.LOGDEBUG)
                if content_episodes[0].get_text().strip():
                    logger.log(f'Content-episodes sample: {content_episodes[0].get_text()[:200]}...', log_utils.LOGDEBUG)
            
            # Look for sWatchSeries specific server structure first
            server_selectors = [
                '.server-select', '.server-select .nav', '.server-select .nav .nav-item',
                '.server-select .nav .nav-item a', '.nav-item a[data-linkid]'
            ]
            
            for selector in server_selectors:
                elements = soup.select(selector)
                if elements:
                    logger.log(f'Found {selector}: {len(elements)} elements', log_utils.LOGDEBUG)
                    # Log first few elements for debugging
                    for i, elem in enumerate(elements[:3]):
                        if elem.name == 'a':
                            href = elem.get('href', 'No href')
                            title = elem.get('title', 'No title')
                            linkid = elem.get('data-linkid', 'No linkid')
                            text = elem.get_text(strip=True)
                            logger.log(f'  Element {i}: href="{href}", title="{title}", linkid="{linkid}", text="{text}"', log_utils.LOGDEBUG)
            
            # Look for common video player containers
            player_selectors = [
                '#player', '.player', '#video-player', '.video-player',
                '#embed', '.embed', '#iframe-container', '.iframe-container',
                '.server-list', '.servers', '.links', '.streaming-links'
            ]
            
            for selector in player_selectors:
                elements = soup.select(selector)
                if elements:
                    logger.log(f'Found {selector}: {len(elements)} elements', log_utils.LOGDEBUG)
            
            # Look for iframes
            iframes = soup.find_all('iframe')
            logger.log(f'Total iframes found: {len(iframes)}', log_utils.LOGDEBUG)
            for i, iframe in enumerate(iframes[:3]):  # First 3 iframes
                src = iframe.get('src', 'No src')
                logger.log(f'Iframe {i}: {src}', log_utils.LOGDEBUG)
            
            # Look for data attributes
            data_attrs = ['data-src', 'data-url', 'data-embed', 'data-link']
            for attr in data_attrs:
                elements = soup.find_all(attrs={attr: True})
                if elements:
                    logger.log(f'Elements with {attr}: {len(elements)}', log_utils.LOGDEBUG)
            
            # Look for script tags that might contain streaming data
            scripts = soup.find_all('script')
            logger.log(f'Total script tags: {len(scripts)}', log_utils.LOGDEBUG)
            
            # Look for common streaming domains in the HTML
            streaming_domains = ['streamtape', 'doodstream', 'mixdrop', 'upstream', 'fembed', 'vtube', 'filelions']
            for domain in streaming_domains:
                if domain in html.lower():
                    logger.log(f'Found streaming domain in HTML: {domain}', log_utils.LOGDEBUG)
            
            logger.log('=== End HTML Analysis ===', log_utils.LOGDEBUG)
            
        except Exception as e:
            logger.log(f'Error analyzing HTML structure: {e}', log_utils.LOGDEBUG)

    def _extract_swatchseries_sources(self, soup, page_url, headers):
        """
        Extract sources specific to sWatchSeries structure
        """
        hosters = []
        
        try:
            # Method 1: Look for dynamically loaded server list via AJAX
            # Extract movie/show ID from the page URL
            movie_id = None
            url_parts = page_url.split('/')
            for i, part in enumerate(url_parts):
                if part.startswith('watch-') and '-' in part:
                    # Look for ID at the end of the URL or as separate part
                    if i + 1 < len(url_parts) and url_parts[i + 1].isdigit():
                        movie_id = url_parts[i + 1]
                    else:
                        # ID might be at end of the watch- part
                        parts = part.split('-')
                        for p in reversed(parts):
                            if p.isdigit():
                                movie_id = p
                                break
                    break
            
            # Also try extracting from data attributes or JavaScript
            if not movie_id:
                # Look for movie ID in HTML data attributes or JavaScript
                id_patterns = [
                    r'data-id["\']?\s*[:=]\s*["\']?(\d+)["\']?',
                    r'movie\.id\s*[:=]\s*["\']?(\d+)["\']?',
                    r'var\s+movie_id\s*=\s*["\']?(\d+)["\']?',
                    r'/movie/watch-[^/]*-(\d+)',  # Fixed pattern for /movie/watch-title-ID
                    r'/watch-[^/]*-(\d+)',
                    r'href=["\'][^"\']*-(\d+)["\']'  # Any href ending with -ID

                ]
                
                html_text = str(soup) + " " + page_url  # Include the page URL in search
                for pattern in id_patterns:
                    match = re.search(pattern, html_text, re.I)
                    if match:
                        movie_id = match.group(1)
                        logger.log(f'Found movie ID via pattern {pattern}: {movie_id}', log_utils.LOGDEBUG)
                        break
            
            logger.log(f'Extracted movie ID: {movie_id}', log_utils.LOGDEBUG)
            
            # Try to load server list via AJAX if we have movie ID
            if movie_id:
                ajax_endpoints = [
                    f'/ajax/episode/list/{movie_id}',
                    f'/ajax/season/list/{movie_id}',
                    f'/ajax/server/list/{movie_id}',
                    f'/ajax/sources/{movie_id}'
                ]
                
                for endpoint in ajax_endpoints:
                    try:
                        ajax_url = scraper_utils.urljoin(self.base_url, endpoint)
                        logger.log(f'Trying AJAX endpoint: {ajax_url}', log_utils.LOGDEBUG)
                        
                        ajax_html = self._http_get(ajax_url, headers=headers, cache_limit=0)
                        if ajax_html and len(ajax_html) > 100:
                            logger.log(f'Got AJAX response from {endpoint}, length: {len(ajax_html)}', log_utils.LOGDEBUG)
                            logger.log(f'AJAX response sample: {ajax_html[:500]}', log_utils.LOGDEBUG)
                            
                            # Parse the AJAX response for server links
                            ajax_soup = BeautifulSoup(ajax_html, 'html.parser')
                            ajax_server_links = ajax_soup.select('.nav-item a[data-linkid]')
                            
                            if not ajax_server_links:
                                # Try alternative selectors for AJAX content
                                ajax_server_links = ajax_soup.select('a[data-linkid]')
                            
                            if not ajax_server_links:
                                # Try any links with href containing watch-
                                ajax_server_links = ajax_soup.select('a[href*="watch-"]')
                            
                            if ajax_server_links:
                                logger.log(f'Found {len(ajax_server_links)} server links in AJAX response', log_utils.LOGDEBUG)
                                server_links = ajax_server_links
                                break
                        
                    except Exception as e:
                        logger.log(f'AJAX endpoint {endpoint} failed: {e}', log_utils.LOGDEBUG)
                        continue
            
            # Fallback: Look for server list in the main HTML
            if 'server_links' not in locals() or not server_links:
                server_links = soup.select('.server-select .nav .nav-item a')
                logger.log(f'Primary selector found: {len(server_links)} server links', log_utils.LOGDEBUG)
                
                # Try alternative selectors if primary didn't work
                if not server_links:
                    alt_selectors = [
                        '.server-select a',
                        '.nav-item a[data-linkid]',
                        'a[data-linkid]',
                        '.nav a[href*="watch-"]'
                    ]
                    
                    for selector in alt_selectors:
                        server_links = soup.select(selector)
                        if server_links:
                            logger.log(f'Alternative selector "{selector}" found: {len(server_links)} server links', log_utils.LOGDEBUG)
                            break
            
            if server_links:
                logger.log(f'Total sWatchSeries server links found: {len(server_links)}', log_utils.LOGDEBUG)
                
                for server_link in server_links:
                    try:
                        # Extract server details
                        server_url = server_link.get('href', '').strip()
                        server_name = server_link.get('title', '').strip()
                        data_linkid = server_link.get('data-linkid', '').strip()
                        
                        # Also try getting name from span text
                        if not server_name:
                            span_elem = server_link.find('span')
                            if span_elem:
                                server_name = span_elem.get_text(strip=True)
                        
                        if not server_name:
                            server_name = server_link.get_text(strip=True).replace('▶', '').strip()
                        
                        logger.log(f'Processing server: {server_name} -> {server_url} (linkid: {data_linkid})', log_utils.LOGDEBUG)
                        
                        if server_url and server_name:
                            # Make server URL absolute
                            if not server_url.startswith('http'):
                                server_url = scraper_utils.urljoin(self.base_url, server_url)
                            
                            # Method 1a: Try to get the actual streaming URL by following the server link
                            try:
                                logger.log(f'Fetching server page: {server_url}', log_utils.LOGDEBUG)
                                server_html = self._http_get(server_url, headers=headers, cache_limit=0)
                                
                                if server_html:
                                    # Parse the server page for actual streaming URLs
                                    server_sources = self._parse_server_page(server_html, server_name, headers)
                                    hosters.extend(server_sources)
                                    
                                    # If we found sources, continue to next server
                                    if server_sources:
                                        continue
                            except Exception as e:
                                logger.log(f'Error fetching server page {server_url}: {e}', log_utils.LOGDEBUG)
                            
                            # Method 1b: If data-linkid exists, try AJAX call
                            if data_linkid:
                                try:
                                    # Common AJAX patterns for sWatchSeries
                                    ajax_patterns = [
                                        f'/ajax/episode/list/{data_linkid}',
                                        f'/ajax/server/{data_linkid}',
                                        f'/ajax/link/{data_linkid}',
                                        f'/ajax/embed/{data_linkid}'
                                    ]
                                    
                                    for ajax_pattern in ajax_patterns:
                                        ajax_url = scraper_utils.urljoin(self.base_url, ajax_pattern)
                                        logger.log(f'Trying AJAX with linkid: {ajax_url}', log_utils.LOGDEBUG)
                                        
                                        ajax_html = self._http_get(ajax_url, headers=headers, cache_limit=0)
                                        if ajax_html and len(ajax_html) > 50:
                                            ajax_sources = self._parse_ajax_response(ajax_html)
                                            if ajax_sources:
                                                hosters.extend(ajax_sources)
                                                break
                                except Exception as e:
                                    logger.log(f'Error with AJAX linkid {data_linkid}: {e}', log_utils.LOGDEBUG)
                            
                            # Method 1c: Fallback - add the server link itself as a source
                            if not any(h.get('url') == server_url for h in hosters):
                                logger.log(f'Adding server link as fallback source: {server_name}', log_utils.LOGDEBUG)
                                hoster = {
                                    'multi-part': False,
                                    'host': server_name.lower(),
                                    'class': self,
                                    'quality': QUALITIES.HD720,
                                    'views': None,
                                    'rating': None,
                                    'url': server_url,
                                    'direct': False
                                }
                                hosters.append(hoster)
                        
                    except Exception as e:
                        logger.log(f'Error processing server link: {e}', log_utils.LOGDEBUG)
                        continue
            
            # Method 2: Look for alternative server structures if main method didn't work
            if not hosters:
                # Be more specific - only look for links that have watch/stream patterns and avoid navigation
                potential_server_links = soup.find_all('a', href=True)
                for link in potential_server_links:
                    href = link.get('href', '').strip()
                    text = link.get_text(strip=True)
                    title = link.get('title', '').strip()
                    
                    # Skip navigation links explicitly
                    if any(skip in href.lower() for skip in ['/genre/', '/country/', '/search', '/movie/', '/tv-show/', '/top-', '/year/']):
                        continue
                    
                    # Only consider links that look like watch/server links
                    if any(pattern in href.lower() for pattern in ['/watch-', '/server/', '/embed/', '/stream/']):
                        server_name = title or text.replace('▶', '').strip()
                        if server_name and len(server_name) > 2 and len(server_name) < 20:  # Reasonable server name length
                            if not href.startswith('http'):
                                href = scraper_utils.urljoin(self.base_url, href)
                            
                            logger.log(f'Found potential server link: {server_name} -> {href}', log_utils.LOGDEBUG)
                            hoster = {
                                'multi-part': False,
                                'host': server_name.lower(),
                                'class': self,
                                'quality': QUALITIES.HD720,
                                'views': None,
                                'rating': None,
                                'url': href,
                                'direct': False
                            }
                            hosters.append(hoster)
            
            # Method 3: Look for AJAX endpoints and streaming URLs in JavaScript
            if not hosters:
                scripts = soup.find_all('script')
                for script in scripts:
                    script_text = script.get_text() if script.string else ''
                    
                    if script_text:
                        # Extract potential streaming sources from obfuscated JavaScript
                        hosters.extend(self._extract_js_sources(script_text, headers))
                    
                    # Look for AJAX URLs that might contain streaming data
                    ajax_matches = re.findall(r'["\']([^"\']*(?:ajax|load|stream|server|episode)[^"\']*)["\']', script_text, re.I)
                    for ajax_url in ajax_matches:
                        if ajax_url.startswith('/') and len(ajax_url) > 5:
                            try:
                                full_ajax_url = scraper_utils.urljoin(self.base_url, ajax_url)
                                logger.log(f'Trying AJAX URL: {full_ajax_url}', log_utils.LOGDEBUG)
                                
                                ajax_html = self._http_get(full_ajax_url, headers=headers, cache_limit=0)
                                if ajax_html:
                                    ajax_sources = self._parse_ajax_response(ajax_html)
                                    hosters.extend(ajax_sources)
                                    
                            except Exception as e:
                                logger.log(f'Error fetching AJAX URL {ajax_url}: {e}', log_utils.LOGDEBUG)
                                continue
            
            # Method 2: Look for embedded iframe sources
            iframes = soup.find_all('iframe', src=True)
            for iframe in iframes:
                iframe_src = iframe.get('src', '').strip()
                if iframe_src and iframe_src.startswith('http'):
                    host = self._extract_host_from_url(iframe_src)
                    # Filter out tracking and non-streaming URLs
                    excluded_hosts = [
                        'swatchseries', 'watchseries', 'sysmeasuring', 'google-analytics', 
                        'googletagmanager', 'facebook', 'twitter', 'jsdelivr', 'cloudflare',
                        'gstatic', 'googleapis', 'doubleclick', 'adsystem', 'googlesyndication'
                    ]
                    if host and not any(excluded in host for excluded in excluded_hosts):
                        logger.log(f'Found iframe source: {host}', log_utils.LOGDEBUG)
                        hoster = {
                            'multi-part': False,
                            'host': host,
                            'class': self,
                            'quality': QUALITIES.HD720,  # Default quality
                            'views': None,
                            'rating': None,
                            'url': iframe_src,
                            'direct': False
                        }
                        hosters.append(hoster)
            
            # Method 3: Look for data attributes containing streaming info
            elements_with_data = soup.find_all(attrs={'data-src': True})
            elements_with_data.extend(soup.find_all(attrs={'data-url': True}))
            elements_with_data.extend(soup.find_all(attrs={'data-embed': True}))
            
            for elem in elements_with_data:
                for attr in ['data-src', 'data-url', 'data-embed']:
                    data_url = elem.get(attr, '').strip()
                    if data_url and ('http' in data_url or data_url.startswith('/')):
                        if not data_url.startswith('http'):
                            data_url = scraper_utils.urljoin(self.base_url, data_url)
                        
                        host = self._extract_host_from_url(data_url)
                        # Filter out tracking and non-streaming URLs
                        excluded_hosts = [
                            'swatchseries', 'watchseries', 'sysmeasuring', 'google-analytics', 
                            'googletagmanager', 'facebook', 'twitter', 'jsdelivr', 'cloudflare',
                            'gstatic', 'googleapis', 'doubleclick', 'adsystem', 'googlesyndication'
                        ]
                        if host and not any(excluded in host for excluded in excluded_hosts):
                            # Additional check: skip homepage/root URLs
                            if not (data_url.endswith('/') and len(data_url.split('/')) <= 4):
                                logger.log(f'Found data attribute source: {host}', log_utils.LOGDEBUG)
                                hoster = {
                                    'multi-part': False,
                                    'host': host,
                                    'class': self,
                                    'quality': QUALITIES.HD720,
                                    'views': None,
                                    'rating': None,
                                    'url': data_url,
                                    'direct': False
                                }
                                hosters.append(hoster)
            
            # Method 4: Look for buttons or links with streaming-related classes
            streaming_elements = soup.find_all(['a', 'button', 'div'], class_=re.compile(r'(play|stream|server|episode|watch)', re.I))
            for elem in streaming_elements:
                href = elem.get('href', '').strip()
                onclick = elem.get('onclick', '').strip()
                
                # Extract URLs from href or onclick
                urls_to_check = []
                if href and href.startswith('http'):
                    urls_to_check.append(href)
                
                if onclick:
                    # Extract URLs from onclick JavaScript
                    url_matches = re.findall(r'["\']([^"\']*https?://[^"\']+)["\']', onclick)
                    urls_to_check.extend(url_matches)
                
                for url in urls_to_check:
                    host = self._extract_host_from_url(url)
                    if host and host not in ['swatchseries', 'watchseries']:
                        logger.log(f'Found streaming element source: {host}', log_utils.LOGDEBUG)
                        hoster = {
                            'multi-part': False,
                            'host': host,
                            'class': self,
                            'quality': QUALITIES.HD720,
                            'views': None,
                            'rating': None,
                            'url': url,
                            'direct': False
                        }
                        hosters.append(hoster)
            
        except Exception as e:
            logger.log(f'Error in sWatchSeries specific extraction: {e}', log_utils.LOGDEBUG)
        
        return hosters

    def _parse_server_page(self, server_html, server_name, headers):
        """
        Parse a server page to extract actual streaming URLs
        """
        hosters = []
        
        try:
            soup = BeautifulSoup(server_html, 'html.parser')
            logger.log(f'Parsing server page for {server_name}, HTML length: {len(server_html)}', log_utils.LOGDEBUG)
            
            # Method 1: Look for iframes with streaming sources
            iframes = soup.find_all('iframe', src=True)
            for iframe in iframes:
                iframe_src = iframe.get('src', '').strip()
                if iframe_src and iframe_src.startswith('http'):
                    # Skip self-referential iframes
                    if self.base_url not in iframe_src:
                        host = self._extract_host_from_url(iframe_src)
                        if host and host not in ['swatchseries', 'watchseries']:
                            logger.log(f'Found iframe streaming source: {host}', log_utils.LOGDEBUG)
                            hoster = {
                                'multi-part': False,
                                'host': host,
                                'class': self,
                                'quality': QUALITIES.HD720,
                                'views': None,
                                'rating': None,
                                'url': iframe_src,
                                'direct': False
                            }
                            hosters.append(hoster)
            
            # Method 2: Look for embedded video players
            video_elements = soup.find_all(['video', 'embed', 'object'])
            for elem in video_elements:
                src = elem.get('src') or elem.get('data-src') or elem.get('data')
                if src and src.startswith('http'):
                    host = self._extract_host_from_url(src)
                    if host and host not in ['swatchseries', 'watchseries']:
                        logger.log(f'Found video element source: {host}', log_utils.LOGDEBUG)
                        hoster = {
                            'multi-part': False,
                            'host': host,
                            'class': self,
                            'quality': QUALITIES.HD720,
                            'views': None,
                            'rating': None,
                            'url': src,
                            'direct': False
                        }
                        hosters.append(hoster)
            
            # Method 3: Look for JavaScript redirects or embedded URLs
            scripts = soup.find_all('script')
            for script in scripts:
                script_text = script.get_text() if script.string else ''
                if script_text:
                    # Look for common patterns
                    url_patterns = [
                        r'(?:src|url|link|embed)\s*[:=]\s*["\']([^"\']*https?://[^"\']+)["\']',
                        r'window\.location\s*=\s*["\']([^"\']*https?://[^"\']+)["\']',
                        r'(?:player|video)\.src\s*=\s*["\']([^"\']+)["\']'
                    ]
                    
                    for pattern in url_patterns:
                        matches = re.findall(pattern, script_text, re.I)
                        for match in matches:
                            if match.startswith('http') and self.base_url not in match:
                                host = self._extract_host_from_url(match)
                                if host and host not in ['swatchseries', 'watchseries']:
                                    logger.log(f'Found JS embedded source: {host}', log_utils.LOGDEBUG)
                                    hoster = {
                                        'multi-part': False,
                                        'host': host,
                                        'class': self,
                                        'quality': QUALITIES.HD720,
                                        'views': None,
                                        'rating': None,
                                        'url': match,
                                        'direct': False
                                    }
                                    hosters.append(hoster)
            
            # Method 4: Look for direct links to streaming sites
            all_links = soup.find_all('a', href=True)
            for link in all_links:
                href = link.get('href', '').strip()
                if href.startswith('http') and self.base_url not in href:
                    host = self._extract_host_from_url(href)
                    # Check if this looks like a streaming host
                    streaming_indicators = ['stream', 'video', 'embed', 'player', 'watch']
                    if (host and host not in ['swatchseries', 'watchseries'] and 
                        any(indicator in href.lower() for indicator in streaming_indicators)):
                        
                        logger.log(f'Found direct streaming link: {host}', log_utils.LOGDEBUG)
                        hoster = {
                            'multi-part': False,
                            'host': host,
                            'class': self,
                            'quality': QUALITIES.HD720,
                            'views': None,
                            'rating': None,
                            'url': href,
                            'direct': False
                        }
                        hosters.append(hoster)
            
        except Exception as e:
            logger.log(f'Error parsing server page: {e}', log_utils.LOGDEBUG)
        
        logger.log(f'Server page {server_name} extracted {len(hosters)} sources', log_utils.LOGDEBUG)
        return hosters

    def _extract_js_sources(self, script_text, headers):
        """
        Extract streaming sources from obfuscated JavaScript
        """
        hosters = []
        
        try:
            # Method 1: Look for direct HTTP URLs in the JavaScript
            url_patterns = [
                r'https?://[^\s"\'<>()]+',  # Direct HTTP URLs
                r'["\']https?://[^"\']+["\']',  # Quoted HTTP URLs
                r'src\s*[:=]\s*["\']([^"\']+)["\']',  # src= patterns
                r'url\s*[:=]\s*["\']([^"\']+)["\']',  # url= patterns
                r'link\s*[:=]\s*["\']([^"\']+)["\']',  # link= patterns
                r'embed\s*[:=]\s*["\']([^"\']+)["\']',  # embed= patterns
            ]
            
            for pattern in url_patterns:
                matches = re.findall(pattern, script_text, re.I)
                for match in matches:
                    # Clean up the match (remove quotes if present)
                    url = match.strip('\'"')
                    
                    if url.startswith('http') and len(url) > 10:
                        host = self._extract_host_from_url(url)
                        if host and host not in ['swatchseries', 'watchseries', 'google', 'facebook', 'twitter']:
                            # Skip common non-streaming domains
                            if not any(skip in host for skip in ['gstatic', 'googleapis', 'cloudflare', 'jquery', 'bootstrap']):
                                logger.log(f'Found JS source: {host}', log_utils.LOGDEBUG)
                                hoster = {
                                    'multi-part': False,
                                    'host': host,
                                    'class': self,
                                    'quality': QUALITIES.HD720,
                                    'views': None,
                                    'rating': None,
                                    'url': url,
                                    'direct': False
                                }
                                hosters.append(hoster)
            
            # Method 2: Look for base64 encoded data that might contain URLs
            b64_patterns = [
                r'atob\s*\(\s*["\']([A-Za-z0-9+/=]+)["\']',  # atob() calls
                r'Base64\.decode\s*\(\s*["\']([A-Za-z0-9+/=]+)["\']',  # Base64.decode calls
                r'["\']([A-Za-z0-9+/=]{20,})["\']'  # Long base64-looking strings
            ]
            
            for pattern in b64_patterns:
                matches = re.findall(pattern, script_text)
                for match in matches:
                    try:
                        import base64
                        decoded = base64.b64decode(match).decode('utf-8', errors='ignore')
                        # Look for URLs in the decoded string
                        decoded_urls = re.findall(r'https?://[^\s"\'<>()]+', decoded)
                        for url in decoded_urls:
                            host = self._extract_host_from_url(url)
                            if host and host not in ['swatchseries', 'watchseries']:
                                logger.log(f'Found decoded JS source: {host}', log_utils.LOGDEBUG)
                                hoster = {
                                    'multi-part': False,
                                    'host': host,
                                    'class': self,
                                    'quality': QUALITIES.HD720,
                                    'views': None,
                                    'rating': None,
                                    'url': url,
                                    'direct': False
                                }
                                hosters.append(hoster)
                    except Exception:
                        continue
            
            # Method 3: Look for common streaming site patterns
            streaming_patterns = [
                r'streamtape\.com[^"\']*',
                r'doodstream\.com[^"\']*',
                r'fembed\.com[^"\']*',
                r'mixdrop\.co[^"\']*',
                r'upstream\.to[^"\']*',
                r'videovard\.to[^"\']*',
                r'streamlare\.com[^"\']*',
                r'filelions\.com[^"\']*',
                r'vtube\.to[^"\']*',
                r'voe\.sx[^"\']*'
            ]
            
            for pattern in streaming_patterns:
                matches = re.findall(pattern, script_text, re.I)
                for match in matches:
                    if not match.startswith('http'):
                        url = 'https://' + match
                    else:
                        url = match
                    
                    host = self._extract_host_from_url(url)
                    if host:
                        logger.log(f'Found streaming pattern source: {host}', log_utils.LOGDEBUG)
                        hoster = {
                            'multi-part': False,
                            'host': host,
                            'class': self,
                            'quality': QUALITIES.HD720,
                            'views': None,
                            'rating': None,
                            'url': url,
                            'direct': False
                        }
                        hosters.append(hoster)
            
            # Method 4: Look for AJAX endpoints that might load streaming data
            ajax_patterns = [
                r'/ajax/[^"\']*',
                r'/api/[^"\']*',
                r'/load[^"\']*',
                r'/get[^"\']*stream[^"\']*',
                r'/embed[^"\']*'
            ]
            
            for pattern in ajax_patterns:
                matches = re.findall(pattern, script_text, re.I)
                for match in matches:
                    if len(match) > 8:  # Reasonable length
                        try:
                            ajax_url = scraper_utils.urljoin(self.base_url, match)
                            logger.log(f'Trying JS AJAX endpoint: {ajax_url}', log_utils.LOGDEBUG)
                            
                            ajax_response = self._http_get(ajax_url, headers=headers, cache_limit=0)
                            if ajax_response:
                                ajax_sources = self._parse_ajax_response(ajax_response)
                                hosters.extend(ajax_sources)
                        except Exception as e:
                            logger.log(f'Error fetching JS AJAX {match}: {e}', log_utils.LOGDEBUG)
                            continue
            
        except Exception as e:
            logger.log(f'Error extracting JS sources: {e}', log_utils.LOGDEBUG)
        
        return hosters

    def _parse_ajax_response(self, ajax_html):
        """
        Parse AJAX response for streaming links - enhanced for sWatchSeries
        """
        hosters = []
        
        try:
            # Try parsing as JSON first
            import json
            try:
                data = json.loads(ajax_html)
                logger.log(f'AJAX response parsed as JSON: {type(data)}', log_utils.LOGDEBUG)
                
                if isinstance(data, dict):
                    # Look for common keys that might contain streaming URLs or HTML
                    for key in ['html', 'content', 'data', 'result', 'response']:
                        if key in data and isinstance(data[key], str):
                            # If it's HTML content, parse it
                            if '<' in data[key]:
                                logger.log(f'Found HTML content in JSON key "{key}"', log_utils.LOGDEBUG)
                                html_content = data[key]
                                soup = BeautifulSoup(html_content, 'html.parser')
                                
                                # Look for server links in the HTML content
                                server_links = soup.select('.nav-item a[data-linkid]')
                                if not server_links:
                                    server_links = soup.select('a[data-linkid]')
                                if not server_links:
                                    server_links = soup.select('a[href*="watch-"]')
                                
                                for link in server_links:
                                    server_url = link.get('href', '').strip()
                                    server_name = link.get('title', '').strip()
                                    data_linkid = link.get('data-linkid', '').strip()
                                    
                                    if not server_name:
                                        span_elem = link.find('span')
                                        if span_elem:
                                            server_name = span_elem.get_text(strip=True)
                                    
                                    if not server_name:
                                        server_name = link.get_text(strip=True).replace('▶', '').strip()
                                    
                                    if server_url and server_name:
                                        if not server_url.startswith('http'):
                                            server_url = scraper_utils.urljoin(self.base_url, server_url)
                                        
                                        logger.log(f'Found server from AJAX HTML: {server_name} -> {server_url}', log_utils.LOGDEBUG)
                                        hoster = {
                                            'multi-part': False,
                                            'host': server_name.lower(),
                                            'class': self,
                                            'quality': QUALITIES.HD720,
                                            'views': None,
                                            'rating': None,
                                            'url': server_url,
                                            'direct': False
                                        }
                                        hosters.append(hoster)
                            else:
                                # Direct URL
                                url = data[key].strip()
                                if url.startswith('http'):
                                    host = self._extract_host_from_url(url)
                                    if host:
                                        hoster = {
                                            'multi-part': False,
                                            'host': host,
                                            'class': self,
                                            'quality': QUALITIES.HD720,
                                            'views': None,
                                            'rating': None,
                                            'url': url,
                                            'direct': False
                                        }
                                        hosters.append(hoster)
                    
                    # Also look for direct streaming URLs in JSON
                    for key in ['url', 'link', 'embed', 'src', 'stream']:
                        if key in data and isinstance(data[key], str):
                            url = data[key].strip()
                            if url.startswith('http'):
                                host = self._extract_host_from_url(url)
                                if host:
                                    hoster = {
                                        'multi-part': False,
                                        'host': host,
                                        'class': self,
                                        'quality': QUALITIES.HD720,
                                        'views': None,
                                        'rating': None,
                                        'url': url,
                                        'direct': False
                                    }
                                    hosters.append(hoster)
                    
            except json.JSONDecodeError:
                logger.log('AJAX response is not JSON, trying HTML parsing', log_utils.LOGDEBUG)
            
            # If not JSON or no hosters found, parse as HTML
            if not hosters:
                soup = BeautifulSoup(ajax_html, 'html.parser')
                
                # Look for server links first (sWatchSeries specific)
                server_links = soup.select('.nav-item a[data-linkid]')
                if not server_links:
                    server_links = soup.select('a[data-linkid]')
                if not server_links:
                    server_links = soup.select('a[href*="watch-"]')
                
                logger.log(f'Found {len(server_links)} server links in AJAX HTML', log_utils.LOGDEBUG)
                
                for link in server_links:
                    server_url = link.get('href', '').strip()
                    server_name = link.get('title', '').strip()
                    data_linkid = link.get('data-linkid', '').strip()
                    
                    if not server_name:
                        span_elem = link.find('span')
                        if span_elem:
                            server_name = span_elem.get_text(strip=True)
                    
                    if not server_name:
                        server_name = link.get_text(strip=True).replace('▶', '').strip()
                    
                    if server_url and server_name:
                        if not server_url.startswith('http'):
                            server_url = scraper_utils.urljoin(self.base_url, server_url)
                        
                        logger.log(f'Found server from AJAX: {server_name} -> {server_url} (linkid: {data_linkid})', log_utils.LOGDEBUG)
                        hoster = {
                            'multi-part': False,
                            'host': server_name.lower(),
                            'class': self,
                            'quality': QUALITIES.HD720,
                            'views': None,
                            'rating': None,
                            'url': server_url,
                            'direct': False
                        }
                        hosters.append(hoster)
                
                # Fallback: look for any links with streaming URLs
                if not hosters:
                    links = soup.find_all('a', href=True)
                    iframes = soup.find_all('iframe', src=True)
                    
                    for elem in links + iframes:
                        url = elem.get('href') or elem.get('src', '')
                        if url and url.startswith('http'):
                            host = self._extract_host_from_url(url)
                            if host and host not in ['swatchseries', 'watchseries']:
                                hoster = {
                                    'multi-part': False,
                                    'host': host,
                                    'class': self,
                                    'quality': QUALITIES.HD720,
                                    'views': None,
                                    'rating': None,
                                    'url': url,
                                    'direct': False
                                }
                                hosters.append(hoster)
            
        except Exception as e:
            logger.log(f'Error parsing AJAX response: {e}', log_utils.LOGDEBUG)
        
        logger.log(f'AJAX response parsing returned {len(hosters)} sources', log_utils.LOGDEBUG)
        return hosters

    def _extract_generic_sources(self, soup, page_url):
        """
        Generic source extraction for common patterns
        """
        hosters = []
        
        try:
            # Look for streaming links in various containers
            link_containers = []
            
            # Check for common link containers
            for selector in ['#linktable', '.server-list', '.streaming-links', '.episode-links', '.servers', '.links']:
                container = soup.select_one(selector)
                if container:
                    link_containers.append(container)
            
            # If no specific containers found, look for generic link patterns
            if not link_containers:
                link_containers = soup.find_all(['div', 'table'], class_=re.compile(r'(link|server|stream)', re.I))
            
            for container in link_containers:
                # Look for links within the container
                links = container.find_all('a', href=True)
                
                for link in links:
                    try:
                        stream_url = link.get('href', '').strip()
                        if not stream_url or stream_url.startswith('#'):
                            continue
                        
                        # Extract host name
                        host_elem = link.find_parent('tr') or link.find_parent('div')
                        if host_elem:
                            host_text = host_elem.get_text(strip=True)
                            # Clean up host name
                            host = re.sub(r'(click|here|to|play|watch|stream)', '', host_text, flags=re.I).strip()
                            host = re.sub(r'[^\w\s.-]', '', host).strip()
                            if not host:
                                host = self._extract_host_from_url(stream_url)
                        else:
                            host = self._extract_host_from_url(stream_url)
                        
                        if not host:
                            continue
                        
                        # Determine quality
                        quality_text = link.get_text() + ' ' + (host_elem.get_text() if host_elem else '')
                        quality = self._determine_quality(quality_text, video={})
                        
                        # Make sure URL is absolute
                        if not stream_url.startswith('http'):
                            stream_url = scraper_utils.urljoin(self.base_url, stream_url)
                        
                        hoster = {
                            'multi-part': False,
                            'host': host,
                            'class': self,
                            'quality': quality,
                            'views': None,
                            'rating': None,
                            'url': stream_url,
                            'direct': False
                        }
                        hosters.append(hoster)
                        
                    except Exception as e:
                        logger.log(f'Error parsing link: {e}', log_utils.LOGDEBUG)
                        continue
            
        except Exception as e:
            logger.log(f'Error in generic source extraction: {e}', log_utils.LOGDEBUG)
        
        return hosters

    def _extract_sources_alternative(self, soup, video):
        """
        Alternative method to extract sources if primary method fails
        """
        hosters = []
        
        # Look for all links that might be streaming sources
        all_links = soup.find_all('a', href=True)
        
        for link in all_links:
            href = link.get('href', '').strip()
            link_text = link.get_text(strip=True).lower()
            
            # Skip navigation and non-streaming links
            if any(skip in link_text for skip in ['home', 'contact', 'about', 'dmca', 'register', 'login', 'genre']):
                continue
            
            if any(skip in href.lower() for skip in ['/genre/', '/country/', '/search', '#', 'javascript:']):
                continue
            
            # Look for streaming-related keywords
            if any(keyword in link_text for keyword in ['watch', 'stream', 'play', 'server', 'link']):
                host = self._extract_host_from_url(href)
                if host and host not in ['swatchseries', 'watchseries']:
                    quality = self._determine_quality(link_text, video)
                    
                    if not href.startswith('http'):
                        href = scraper_utils.urljoin(self.base_url, href)
                    
                    hoster = {
                        'multi-part': False,
                        'host': host,
                        'class': self,
                        'quality': quality,
                        'views': None,
                        'rating': None,
                        'url': href,
                        'direct': False
                    }
                    hosters.append(hoster)
        
        return hosters

    def _extract_host_from_url(self, url):
        """
        Extract hostname from URL
        """
        try:
            parsed = urllib.parse.urlparse(url)
            host = parsed.netloc.lower()
            # Remove www. prefix
            if host.startswith('www.'):
                host = host[4:]
            return host
        except:
            return 'Unknown'

    def _determine_quality(self, text, video):
        """
        Determine video quality from text
        """
        text = text.lower()
        if any(q in text for q in ['4k', '2160p', 'uhd']):
            return QUALITIES.HD8K
        elif any(q in text for q in ['1080p', 'fhd', 'full hd']):
            return QUALITIES.HD1080
        elif any(q in text for q in ['720p', 'hd']):
            return QUALITIES.HD720
        elif any(q in text for q in ['480p', 'sd']):
            return QUALITIES.HIGH
        elif 'cam' in text:
            return QUALITIES.LOW
        else:
            return scraper_utils.get_quality(video, text, QUALITIES.HIGH)

    def resolve_link(self, link):
        """
        Resolve intermediate links to actual streaming URLs
        """
        if link.startswith('http') and self.base_url not in link:
            return link
        
        try:
            html = self._http_get(link, cache_limit=0)
            if not html:
                return link
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Look for redirect links or embedded players
            for selector in ['a[href*="http"]', 'iframe[src*="http"]', 'embed[src*="http"]']:
                elem = soup.select_one(selector)
                if elem:
                    url = elem.get('href') or elem.get('src')
                    if url and self.base_url not in url:
                        return url
            
            # Look for JavaScript redirects
            scripts = soup.find_all('script')
            for script in scripts:
                script_text = script.get_text()
                if script_text:
                    # Look for window.location or similar redirects
                    redirect_match = re.search(r'(?:window\.location|location\.href)\s*=\s*["\']([^"\']+)["\']', script_text)
                    if redirect_match:
                        redirect_url = redirect_match.group(1)
                        if redirect_url.startswith('http') and self.base_url not in redirect_url:
                            return redirect_url
        
        except Exception as e:
            logger.log(f'Error resolving WatchSeries link: {e}', log_utils.LOGDEBUG)
        
        return link

    def search(self, video_type, title, year, season=''):
        """
        Search for TV shows on sWatchSeries
        """
        results = []
        
        try:
            # Construct search query
            search_term = title
            if year:
                search_term += f' {year}'
            
            search_url = scraper_utils.urljoin(self.base_url, SEARCH_URL % urllib.parse.quote(search_term.lower().replace(' ', '-')))
            logger.log(f'WatchSeries search URL: {search_url}', log_utils.LOGDEBUG)
            
            # Add headers to appear more like a real browser
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'DNT': '1',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
            }
            
            try:
                html = self._http_get(search_url, headers=headers, cache_limit=1)
            except Exception as e:
                logger.log(f'Primary URL failed: {e}', log_utils.LOGDEBUG)
                if '410' in str(e) or '404' in str(e) or 'Gone' in str(e):
                    logger.log('Got 410/404 error, trying backup URLs', log_utils.LOGDEBUG)
                    search_path = SEARCH_URL % urllib.parse.quote(search_term.lower().replace(' ', '-'))
                    html = self._try_backup_urls(search_path, headers=headers)
                else:
                    html = None
            
            if not html:
                return results
            
            logger.log(f'WatchSeries HTML length: {len(html)}', log_utils.LOGDEBUG)
            
            # Check if we got a redirect/landing page instead of search results
            if len(html) < 10000 and 'chronos' in html:
                logger.log('Detected redirect page, trying to extract redirect URL', log_utils.LOGDEBUG)
                
                # Try to extract redirect from JavaScript
                redirect_match = re.search(r"window\.location\.href\s*=\s*data\.location", html)
                if redirect_match:
                    # Try to get the actual search page by following redirects
                    logger.log('Trying to bypass redirect page', log_utils.LOGDEBUG)
                    
                    # Try different approaches
                    # Method 1: Try the search URL with different format
                    alt_search_path = f"/search?keyword={urllib.parse.quote_plus(search_term)}"
                    logger.log(f'Trying alternative search format', log_utils.LOGDEBUG)
                    
                    alt_html = self._try_backup_urls(alt_search_path, headers=headers)
                    if alt_html and len(alt_html) > len(html):
                        html = alt_html
                        logger.log(f'Got better HTML with length: {len(html)}', log_utils.LOGDEBUG)
                    
                    # Method 2: Try without hyphens
                    if len(html) < 10000:
                        simple_search_path = f"/search/{urllib.parse.quote_plus(search_term)}"
                        logger.log(f'Trying simple search format', log_utils.LOGDEBUG)
                        
                        simple_html = self._try_backup_urls(simple_search_path, headers=headers)
                        if simple_html and len(simple_html) > len(html):
                            html = simple_html
                            logger.log(f'Got better HTML with length: {len(html)}', log_utils.LOGDEBUG)
                    
                    # Method 3: Try visiting working domain main page first
                    if len(html) < 10000:
                        logger.log('Trying to visit working main site first', log_utils.LOGDEBUG)
                        main_html = self._try_backup_urls('/', headers=headers)
                        if main_html:
                            # Now try search again with the working base URL
                            search_path = SEARCH_URL % urllib.parse.quote(search_term.lower().replace(' ', '-'))
                            retry_html = self._http_get(scraper_utils.urljoin(self.base_url, search_path), headers=headers, cache_limit=0)
                            if retry_html and len(retry_html) > len(html):
                                html = retry_html
                                logger.log(f'Got better HTML after visiting main site: {len(html)}', log_utils.LOGDEBUG)
            
            # If still getting short HTML, log it for debugging
            if len(html) < 10000:
                logger.log(f'Still getting short HTML, sample: {html[:1000]}...', log_utils.LOGDEBUG)
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Look for search results - sWatchSeries specific structure
            show_containers = []
            
            # Method 1: Look for sWatchSeries specific structure (.flw-item)
            flw_containers = soup.select('.flw-item')
            if flw_containers:
                show_containers = flw_containers
                logger.log(f'Found sWatchSeries containers (.flw-item): {len(flw_containers)}', log_utils.LOGDEBUG)
            
            # Method 2: Fallback to other common containers
            if not show_containers:
                for selector in ['.movie-item', '.show-item', '.result-item', '.card', '.item', '.post', '.entry']:
                    containers = soup.select(selector)
                    if containers:
                        show_containers = containers
                        logger.log(f'Found containers with selector: {selector}', log_utils.LOGDEBUG)
                        break
            
            # Method 3: Look for h2 or h3 headers with links (common pattern)
            if not show_containers:
                header_containers = soup.find_all(['h2', 'h3', 'h4'], string=re.compile(r'.+'))
                for header in header_containers:
                    parent = header.find_parent(['div', 'article', 'section'])
                    if parent and parent.find('a', href=True):
                        show_containers.append(parent)
                if show_containers:
                    logger.log(f'Found containers via headers: {len(show_containers)}', log_utils.LOGDEBUG)
            
            # Method 4: Look for divs containing links with movie/show patterns
            if not show_containers:
                potential_containers = soup.find_all('div')
                for div in potential_containers:
                    div_text = div.get_text().lower()
                    if any(pattern in div_text for pattern in ['movie', 'tv', 'eps', 'season', '20']):  # year pattern
                        links = div.find_all('a', href=True)
                        if links:
                            show_containers.append(div)
                if show_containers:
                    logger.log(f'Found containers via content analysis: {len(show_containers)}', log_utils.LOGDEBUG)
            
            # Method 5: If still no containers, look for any div with class containing common patterns
            if not show_containers:
                show_containers = soup.find_all(['div', 'article'], class_=re.compile(r'(movie|show|item|card|post|entry)', re.I))
                if show_containers:
                    logger.log(f'Found containers via regex patterns: {len(show_containers)}', log_utils.LOGDEBUG)
            
            logger.log(f'Total containers found: {len(show_containers)}', log_utils.LOGDEBUG)
            
            for container in show_containers:
                try:
                    logger.log(f'Processing container: {container.get_text()[:100]}...', log_utils.LOGDEBUG)
                    
                    # sWatchSeries specific parsing
                    if 'flw-item' in container.get('class', []):
                        # sWatchSeries structure: .film-name a contains title and URL
                        title_link = container.select_one('.film-name a')
                        if title_link:
                            match_url = title_link.get('href', '').strip()
                            match_title = title_link.get_text(strip=True)
                            
                            # Extract year from .fdi-item (first span in .fd-infor)
                            fdi_items = container.select('.fdi-item')
                            match_year = ''
                            if fdi_items:
                                year_text = fdi_items[0].get_text(strip=True)
                                if year_text.isdigit() and len(year_text) == 4:
                                    match_year = year_text
                            
                            # Extract type from .fdi-type
                            type_elem = container.select_one('.fdi-type')
                            content_type = type_elem.get_text(strip=True).lower() if type_elem else ''
                            
                            logger.log(f'sWatchSeries match: {match_title} ({match_year}) [{content_type}] -> {match_url}', log_utils.LOGDEBUG)
                            
                            # Filter by video type
                            if video_type == VIDEO_TYPES.MOVIE and content_type != 'movie':
                                continue
                            elif video_type == VIDEO_TYPES.TVSHOW and content_type == 'movie':
                                continue
                            
                            # Filter by year
                            if year and match_year and year != match_year:
                                continue
                            
                            if match_url and match_title:
                                # Make URL absolute
                                if not match_url.startswith('http'):
                                    match_url = scraper_utils.urljoin(self.base_url, match_url)
                                
                                result = {
                                    'url': scraper_utils.pathify_url(match_url),
                                    'title': scraper_utils.cleanse_title(match_title),
                                    'year': match_year
                                }
                                results.append(result)
                                continue
                    
                    # Generic parsing for other structures
                    # Find title link - try multiple approaches
                    title_link = container.find('a', href=True)
                    if not title_link:
                        # Try finding link in child elements
                        title_link = container.find('h2') or container.find('h3') or container.find('h4')
                        if title_link:
                            title_link = title_link.find('a', href=True)
                    
                    if not title_link:
                        # Try any link in the container
                        all_links = container.find_all('a', href=True)
                        for link in all_links:
                            link_text = link.get_text(strip=True)
                            href = link.get('href', '').strip()
                            # Skip obvious navigation links
                            if not any(skip in href.lower() for skip in ['/genre/', '/country/', '#', 'javascript:']):
                                if link_text and len(link_text) > 5:  # Reasonable title length
                                    title_link = link
                                    break
                    
                    if not title_link:
                        logger.log('No title link found in container', log_utils.LOGDEBUG)
                        continue
                    
                    match_url = title_link.get('href', '').strip()
                    match_title = title_link.get_text(strip=True)
                    
                    logger.log(f'Found potential match: {match_title} -> {match_url}', log_utils.LOGDEBUG)
                    
                    if not match_url or not match_title:
                        logger.log('Empty URL or title', log_utils.LOGDEBUG)
                        continue
                    
                    # Extract year if present
                    year_match = re.search(r'\((\d{4})\)', match_title)
                    match_year = year_match.group(1) if year_match else ''
                    
                    # Clean up title
                    clean_title = re.sub(r'\(\d{4}\)', '', match_title).strip()
                    
                    # Filter by video type and year
                    container_text = container.get_text().lower()
                    is_movie = any(indicator in container_text for indicator in ['movie', 'film', 'm '])
                    is_tv_show = any(indicator in container_text for indicator in ['tv', 'ss ', 'eps ', 'season', 'episode'])
                    
                    if video_type == VIDEO_TYPES.MOVIE:
                        # For movies, skip TV shows
                        if is_tv_show and not is_movie:
                            continue
                    elif video_type == VIDEO_TYPES.TVSHOW:
                        # For TV shows, skip movies
                        if is_movie and not is_tv_show:
                            continue
                    
                    if year and match_year and year != match_year:
                        continue
                    
                    # Make URL absolute
                    if not match_url.startswith('http'):
                        match_url = scraper_utils.urljoin(self.base_url, match_url)
                    
                    result = {
                        'url': scraper_utils.pathify_url(match_url),
                        'title': scraper_utils.cleanse_title(clean_title),
                        'year': match_year
                    }
                    results.append(result)
                    
                except Exception as e:
                    logger.log(f'Error parsing search result: {e}', log_utils.LOGDEBUG)
                    continue
            
            # If no results found with containers, try alternative search
            if not results:
                logger.log('No results from container method, trying alternative search', log_utils.LOGDEBUG)
                results = self._search_alternative(soup, title, year, video_type)
            
            # If still no results, do a broad link analysis for debugging
            if not results:
                logger.log('No results from alternative search, analyzing all links for debugging', log_utils.LOGDEBUG)
                all_links = soup.find_all('a', href=True)
                logger.log(f'Total links found on page: {len(all_links)}', log_utils.LOGDEBUG)
                
                # Log sample of links for debugging
                for i, link in enumerate(all_links[:10]):  # First 10 links
                    href = link.get('href', '')
                    text = link.get_text(strip=True)
                    logger.log(f'Link {i}: {text} -> {href}', log_utils.LOGDEBUG)
        
        except Exception as e:
            logger.log(f'Error searching WatchSeries: {e}', log_utils.LOGWARNING)
        
        logger.log(f'WatchSeries search returned {len(results)} results', log_utils.LOGDEBUG)
        return results

    def _search_alternative(self, soup, title, year, video_type):
        """
        Alternative search method if primary method fails
        """
        results = []
        
        # Look for all links that might be show pages
        all_links = soup.find_all('a', href=True)
        
        for link in all_links:
            href = link.get('href', '').strip()
            link_text = link.get_text(strip=True)
            
            # Skip navigation links
            if any(skip in href.lower() for skip in ['/genre/', '/country/', '/search', '#', 'javascript:']):
                continue
            
            # Check if link text contains the search title
            if title.lower() in link_text.lower():
                # Extract year if present
                year_match = re.search(r'\((\d{4})\)', link_text)
                match_year = year_match.group(1) if year_match else ''
                
                # Clean up title
                clean_title = re.sub(r'\(\d{4}\)', '', link_text).strip()
                
                if year and match_year and year != match_year:
                    continue
                
                if not href.startswith('http'):
                    href = scraper_utils.urljoin(self.base_url, href)
                
                result = {
                    'url': scraper_utils.pathify_url(href),
                    'title': scraper_utils.cleanse_title(clean_title),
                    'year': match_year
                }
                results.append(result)
        
        return results

    def _get_episode_url(self, show_url, video):
        """
        Get the URL for a specific episode or movie
        """
        try:
            # For movies, just return the show_url directly
            if video.video_type == VIDEO_TYPES.MOVIE:
                return scraper_utils.pathify_url(show_url)
            
            show_url = scraper_utils.urljoin(self.base_url, show_url)
            html = self._http_get(show_url, cache_limit=2)
            
            if not html:
                return None
            
            soup = BeautifulSoup(html, 'html.parser')
            
            # Look for episode links with various patterns
            episode_patterns = [
                rf's0*{video.season}[_\-\s]*e0*{video.episode}(?!\d)',
                rf'season[_\-\s]*0*{video.season}[_\-\s]*episode[_\-\s]*0*{video.episode}(?!\d)',
                rf'{video.season}x0*{video.episode}(?!\d)',
                rf's{video.season:02d}e{video.episode:02d}'
            ]
            
            for pattern in episode_patterns:
                # Look in href attributes
                episode_links = soup.find_all('a', href=re.compile(pattern, re.I))
                if episode_links:
                    episode_url = episode_links[0].get('href')
                    return scraper_utils.pathify_url(episode_url)
                
                # Look in text content
                episode_elements = soup.find_all(text=re.compile(pattern, re.I))
                for elem in episode_elements:
                    parent = elem.parent if elem.parent else elem
                    episode_link = parent.find('a', href=True) if hasattr(parent, 'find') else None
                    if episode_link:
                        episode_url = episode_link.get('href')
                        return scraper_utils.pathify_url(episode_url)
            
            # If no specific episode found, return the show URL (some sites list episodes on show page)
            return scraper_utils.pathify_url(show_url)
            
        except Exception as e:
            logger.log(f'Error getting episode URL: {e}', log_utils.LOGWARNING)
            return None

    @classmethod
    def get_settings(cls):
        """
        Generate settings for the scraper
        """
        settings = super(cls, cls).get_settings()
        return settings 