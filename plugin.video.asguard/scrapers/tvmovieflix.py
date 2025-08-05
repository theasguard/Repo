"""
    Asguard Addon
    Copyright (C) 2025
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
import base64
from bs4 import BeautifulSoup
from asguard_lib import scraper_utils
from asguard_lib.constants import VIDEO_TYPES, QUALITIES
from . import scraper
import log_utils
import kodi

logger = log_utils.Logger.get_logger()
BASE_URL = 'https://tvmovieflix.com'

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url') or BASE_URL
        self.search_path = '/?s=%s'

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE])

    @classmethod
    def get_name(cls):
        return 'TVMovieFlix'

    def get_sources(self, video):
        logger.log(f'[TVMOVIEFLIX] Starting get_sources for video: {video.title} ({video.year})', log_utils.LOGDEBUG)
        sources = []
        
        if video.video_type != VIDEO_TYPES.MOVIE:
            logger.log(f'[TVMOVIEFLIX] Video type {video.video_type} not supported, only movies', log_utils.LOGWARNING)
            return sources

        source_url = self.get_url(video)
        if not source_url or source_url == scraper_utils.FORCE_NO_MATCH:
            logger.log(f'[TVMOVIEFLIX] No source URL found for video: {source_url}', log_utils.LOGWARNING)
            return sources

        url = scraper_utils.urljoin(self.base_url, source_url)
        logger.log(f'[TVMOVIEFLIX] Fetching movie page: {url}', log_utils.LOGDEBUG)
        
        html = self._http_get(url, cache_limit=1, require_debrid=True)
        logger.log(f'[TVMOVIEFLIX] Got HTML length: {len(html) if html else 0}', log_utils.LOGDEBUG)
        
        if not html:
            logger.log('[TVMOVIEFLIX] No HTML received from tvmovieflix', log_utils.LOGWARNING)
            return sources

        # Log a snippet of the HTML to see what we're working with
        html_snippet = html[:500] if html else ""
        logger.log(f'[TVMOVIEFLIX] HTML snippet: {html_snippet}', log_utils.LOGDEBUG)

        # Extract links using multiple methods
        links = []
        
        # Method 1: Look for loadEmbed function calls
        load_embed_links = self._extract_load_embed_links(html)
        links.extend(load_embed_links)
        
        # Method 2: Look for var Servers JavaScript variable
        server_links = self._extract_server_links(html)
        links.extend(server_links)
        
        # Method 3: Look for server onclick buttons  
        onclick_links = self._extract_onclick_server_links(html)
        links.extend(onclick_links)
        
        # Method 4: Look for direct iframe sources as backup
        iframe_links = self._extract_iframe_links(html)
        links.extend(iframe_links)

        # Remove duplicates and filter out unwanted links
        original_count = len(links)
        links = list(set(links))  # Remove duplicates
        links = [link for link in links if link and not any(skip in link.lower() for skip in ['youtube', 'tmdb.org', '.jpg', '.png', '.gif', 'logo.png'])]
        
        logger.log(f'[TVMOVIEFLIX] Total extracted links: {original_count} -> {len(links)} after filtering', log_utils.LOGDEBUG)
        
        # Log all found links for debugging
        for i, link in enumerate(links):
            logger.log(f'[TVMOVIEFLIX] Link {i+1}: {link}', log_utils.LOGDEBUG)

        # Process each link
        for i, link in enumerate(links):
            try:
                # Clean up escaped URLs first
                if '\\/' in link:
                    link = link.replace('\\/', '/')
                    logger.log(f'[TVMOVIEFLIX] Cleaned escaped URL: {link[:50]}...', log_utils.LOGDEBUG)
                
                logger.log(f'[TVMOVIEFLIX] Processing link {i+1}/{len(links)}: {link[:50]}...', log_utils.LOGDEBUG)
                
                # Skip obviously invalid links
                if not link or link in ['about:blank', '#']:
                    logger.log(f'[TVMOVIEFLIX] Skipping invalid link {i+1}', log_utils.LOGDEBUG)
                    continue
                
                # Handle relative URLs
                if link.startswith('//'):
                    link = 'https:' + link
                    logger.log(f'[TVMOVIEFLIX] Converted protocol-relative URL: {link[:50]}...', log_utils.LOGDEBUG)
                elif link.startswith('/'):
                    link = scraper_utils.urljoin(self.base_url, link)
                elif not link.startswith('http'):
                    logger.log(f'[TVMOVIEFLIX] Skipping non-URL link {i+1}: {link[:30]}...', log_utils.LOGDEBUG)
                    continue
                
                # Check if this is a tvmovieflix internal link that needs special handling
                if any(domain in link for domain in ['tvmovieflix.com']):
                    processed_link = self._process_internal_link(link)
                    if processed_link:
                        link = processed_link
                    else:
                        logger.log(f'[TVMOVIEFLIX] Failed to process internal link {i+1}', log_utils.LOGDEBUG)
                        continue
                
                # Extract host and determine quality
                host = urllib.parse.urlparse(link).hostname
                if not host:
                    logger.log(f'[TVMOVIEFLIX] No hostname found in link {i+1}', log_utils.LOGDEBUG)
                    continue
                
                quality = scraper_utils.blog_get_quality(video, link, host)
                
                # Determine if it's a direct link
                direct = self._is_direct_link(link, host)
                
                source = {
                    'class': self,
                    'quality': quality,
                    'url': link,
                    'host': host,
                    'multi-part': False,
                    'rating': None,
                    'views': None,
                    'direct': direct,
                }
                sources.append(source)
                logger.log(f'[TVMOVIEFLIX] Added source {len(sources)}: {source}', log_utils.LOGDEBUG)
                
            except Exception as e:
                logger.log(f'[TVMOVIEFLIX] Error processing link {i+1}: {e}', log_utils.LOGERROR)
                continue

        logger.log(f'[TVMOVIEFLIX] Completed processing, found {len(sources)} sources', log_utils.LOGDEBUG)
        return sources

    def _extract_load_embed_links(self, html):
        """Extract links from loadEmbed function calls"""
        logger.log('[TVMOVIEFLIX] Extracting loadEmbed links', log_utils.LOGDEBUG)
        links = []
        
        try:
            # Look for onclick attributes with loadEmbed calls
            soup = BeautifulSoup(html, 'html.parser')
            elements_with_onclick = soup.find_all(attrs={'onclick': True})
            
            for element in elements_with_onclick:
                onclick = element.get('onclick', '')
                load_embed_matches = re.findall(r'''loadEmbed\(['"]([^'"]+)['"]\)''', onclick, re.DOTALL | re.IGNORECASE)
                links.extend(load_embed_matches)
            
            # Also try direct regex on the HTML
            direct_matches = re.findall(r'''loadEmbed\(['"]([^'"]+)['"]\)''', html, re.DOTALL | re.IGNORECASE)
            links.extend(direct_matches)
            
            logger.log(f'[TVMOVIEFLIX] Found {len(links)} loadEmbed links', log_utils.LOGDEBUG)
            
        except Exception as e:
            logger.log(f'[TVMOVIEFLIX] Error extracting loadEmbed links: {e}', log_utils.LOGERROR)
        
        return links

    def _extract_server_links(self, html):
        """Extract links from var Servers JavaScript variable"""
        logger.log('[TVMOVIEFLIX] Extracting server links', log_utils.LOGDEBUG)
        links = []
        
        try:
            # Look for var Servers = {...}; pattern (more comprehensive)
            server_patterns = [
                r'var\s+Servers\s*=\s*\{([^}]+)\}',
                r'Servers\s*=\s*\{([^}]+)\}',
                r'"Servers"\s*:\s*\{([^}]+)\}'
            ]
            
            for pattern in server_patterns:
                server_matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
                logger.log(f'[TVMOVIEFLIX] Pattern {pattern} found {len(server_matches)} matches', log_utils.LOGDEBUG)
                
                for server_block in server_matches:
                    logger.log(f'[TVMOVIEFLIX] Server block content: {server_block[:200]}...', log_utils.LOGDEBUG)
                    
                    # Extract specific server URLs (excluding metadata like post_id, imdb_id, etc.)
                    server_url_patterns = [
                        r'"mp4"\s*:\s*"([^"]+)"',
                        r'"upcloud"\s*:\s*"([^"]+)"',
                        r'"premium"\s*:\s*"([^"]+)"',
                        r'"embedru"\s*:\s*"([^"]+)"',
                        r'"superembed"\s*:\s*"([^"]+)"',
                        r'"svetacdn"\s*:\s*"([^"]+)"',
                        r'"vidsrc"\s*:\s*"([^"]+)"',
                        r'"openvids"\s*:\s*"([^"]+)"',
                        # Generic pattern for any URL-like value
                        r'"[^"]*"\s*:\s*"(https?://[^"]+)"',
                        r'"[^"]*"\s*:\s*"(//[^"]+)"'
                    ]
                    
                    for url_pattern in server_url_patterns:
                        url_matches = re.findall(url_pattern, server_block, re.IGNORECASE)
                        for url in url_matches:
                            if url and not any(skip in url.lower() for skip in ['youtube', 'tmdb.org', 'jpg', 'png', 'gif']):
                                # Clean up escaped URLs
                                clean_url = url.replace('\\/', '/')
                                links.append(clean_url)
                                logger.log(f'[TVMOVIEFLIX] Found server URL: {clean_url}', log_utils.LOGDEBUG)
            
            logger.log(f'[TVMOVIEFLIX] Total server links found: {len(links)}', log_utils.LOGDEBUG)
            
        except Exception as e:
            logger.log(f'[TVMOVIEFLIX] Error extracting server links: {e}', log_utils.LOGERROR)
        
        return links

    def _extract_onclick_server_links(self, html):
        """Extract server URLs from onclick loadServer() calls combined with Servers variable"""
        logger.log('[TVMOVIEFLIX] Extracting onclick server links', log_utils.LOGDEBUG)
        links = []
        
        try:
            # First, extract the Servers JavaScript object
            servers_data = {}
            server_patterns = [
                r'var\s+Servers\s*=\s*\{([^}]+)\}',
                r'Servers\s*=\s*\{([^}]+)\}'
            ]
            
            for pattern in server_patterns:
                matches = re.findall(pattern, html, re.DOTALL | re.IGNORECASE)
                for match in matches:
                    logger.log(f'[TVMOVIEFLIX] Found Servers object: {match[:100]}...', log_utils.LOGDEBUG)
                    
                    # Parse key-value pairs from the servers object
                    key_value_pattern = r'"([^"]+)"\s*:\s*"([^"]+)"'
                    pairs = re.findall(key_value_pattern, match)
                    
                    for key, value in pairs:
                        if value.startswith(('http', '//')):
                            # Clean up escaped URLs
                            clean_value = value.replace('\\/', '/')
                            servers_data[key] = clean_value
                            logger.log(f'[TVMOVIEFLIX] Server mapping: {key} -> {clean_value}', log_utils.LOGDEBUG)
            
            # Now look for onclick loadServer() calls
            onclick_pattern = r'onclick=["\']loadServer\(([^)]+)\)["\']'
            onclick_matches = re.findall(onclick_pattern, html, re.IGNORECASE)
            
            logger.log(f'[TVMOVIEFLIX] Found {len(onclick_matches)} onclick loadServer calls', log_utils.LOGDEBUG)
            
            for server_name in onclick_matches:
                server_name = server_name.strip()
                logger.log(f'[TVMOVIEFLIX] Processing server: {server_name}', log_utils.LOGDEBUG)
                
                if server_name in servers_data:
                    url = servers_data[server_name]
                    links.append(url)
                    logger.log(f'[TVMOVIEFLIX] Found onclick server URL: {server_name} -> {url}', log_utils.LOGDEBUG)
                else:
                    logger.log(f'[TVMOVIEFLIX] Server {server_name} not found in Servers data', log_utils.LOGDEBUG)
            
            # Also add all server URLs even if not clicked (as backup)
            for key, url in servers_data.items():
                if url not in links and not any(skip in url.lower() for skip in ['youtube', 'tmdb.org', 'jpg', 'png', 'gif']):
                    links.append(url)
                    logger.log(f'[TVMOVIEFLIX] Added backup server URL: {key} -> {url}', log_utils.LOGDEBUG)
            
            logger.log(f'[TVMOVIEFLIX] Total onclick server links: {len(links)}', log_utils.LOGDEBUG)
            
        except Exception as e:
            logger.log(f'[TVMOVIEFLIX] Error extracting onclick server links: {e}', log_utils.LOGERROR)
        
        return links

    def _extract_iframe_links(self, html):
        """Extract direct iframe sources as backup"""
        logger.log('[TVMOVIEFLIX] Extracting iframe links', log_utils.LOGDEBUG)
        links = []
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
            iframes = soup.find_all('iframe', src=True)
            
            for iframe in iframes:
                src = iframe.get('src')
                if src:
                    links.append(src)
            
            logger.log(f'[TVMOVIEFLIX] Found {len(links)} iframe links', log_utils.LOGDEBUG)
            
        except Exception as e:
            logger.log(f'[TVMOVIEFLIX] Error extracting iframe links: {e}', log_utils.LOGERROR)
        
        return links

    def _process_internal_link(self, link):
        """Process internal tvmovieflix links that need special handling"""
        # Clean up escaped URLs first
        if '\\/' in link:
            link = link.replace('\\/', '/')
            logger.log(f'[TVMOVIEFLIX] Cleaned escaped internal link: {link}', log_utils.LOGDEBUG)
            
        logger.log(f'[TVMOVIEFLIX] Processing internal link: {link}', log_utils.LOGDEBUG)
        
        try:
            # Handle /embed.php? links - need base64 decoding
            if '/embed.php?' in link:
                logger.log('[TVMOVIEFLIX] Processing embed.php link', log_utils.LOGDEBUG)
                
                embed_html = self._http_get(link, cache_limit=1)
                if not embed_html:
                    logger.log('[TVMOVIEFLIX] No HTML from embed.php link', log_utils.LOGDEBUG)
                    return None
                
                # Look for base64 encoded link (multiple patterns)
                b64_patterns = [
                    r'["\']([A-Za-z0-9+/=]{50,})["\']',  # Generic base64 pattern
                    r'atob\(["\']([A-Za-z0-9+/=]+)["\']\)',  # atob() function calls
                    r'data-src=["\']([A-Za-z0-9+/=]{50,})["\']',  # data-src attributes
                    r'src=["\']([A-Za-z0-9+/=]{50,})["\']'  # src attributes
                ]
                
                b64_matches = []
                for pattern in b64_patterns:
                    matches = re.findall(pattern, embed_html)
                    b64_matches.extend(matches)
                    if matches:
                        logger.log(f'[TVMOVIEFLIX] Found {len(matches)} base64 matches with pattern: {pattern}', log_utils.LOGDEBUG)
                
                for b64_match in b64_matches:
                    try:
                        decoded = base64.b64decode(b64_match.replace("\/", "/")).decode('utf-8', errors='ignore')
                        if decoded.startswith('http'):
                            logger.log(f'[TVMOVIEFLIX] Successfully decoded embed link: {decoded}', log_utils.LOGDEBUG)
                            return decoded
                    except Exception as decode_error:
                        logger.log(f'[TVMOVIEFLIX] Base64 decode error: {decode_error}', log_utils.LOGDEBUG)
                        continue
                
                logger.log('[TVMOVIEFLIX] No valid base64 decoded link found', log_utils.LOGDEBUG)
                return None
            
            # Handle /player.php? links - need redirection
            elif '/player.php?' in link:
                logger.log('[TVMOVIEFLIX] Processing player.php link', log_utils.LOGDEBUG)
                
                # Try to get the redirect URL
                redirect_url = self._http_get(link, allow_redirect=False, cache_limit=1)
                if redirect_url and redirect_url != link:
                    logger.log(f'[TVMOVIEFLIX] Got redirect from player.php: {redirect_url}', log_utils.LOGDEBUG)
                    return redirect_url
                else:
                    logger.log('[TVMOVIEFLIX] No redirect found for player.php link', log_utils.LOGDEBUG)
                    return None
            
            # For other internal links, return as-is for now
            else:
                logger.log('[TVMOVIEFLIX] Unknown internal link type, returning as-is', log_utils.LOGDEBUG)
                return link
                
        except Exception as e:
            logger.log(f'[TVMOVIEFLIX] Error processing internal link: {e}', log_utils.LOGERROR)
            return None

    def _is_direct_link(self, link, host):
        """Determine if a link is direct based on host and patterns"""
        # Hosts that are typically direct or require minimal processing
        direct_hosts = [
            'google', 'blogspot', 'okru', 'filemoon', 'mixdrop', 'vidcloud', 'embtaku', 
            'streamtape', 'dood', 'mp4upload', 'superembed', 'embedru', 'svetacdn', 
            'vidsrc', 'upload', '2embed', 'openvids'
        ]
        
        # Hosts that are definitely embed/indirect
        embed_hosts = ['youtube', 'tmdb', 'tvmovieflix.com']
        
        if host:
            host_lower = host.lower()
            
            # Check if it's an embed host (definitely indirect)
            if any(h in host_lower for h in embed_hosts):
                return False
                
            # Check if it's a known direct host
            if any(h in host_lower for h in direct_hosts):
                return True
        
        # Check for direct video file extensions
        if any(ext in link.lower() for ext in ['.mp4', '.avi', '.mkv', '.m3u8', '.ts']):
            return True
        
        # Check for embed patterns (usually indirect)
        if any(pattern in link.lower() for pattern in ['/embed/', '/player/', '?embed=']):
            return False
            
        return False

    def search(self, video_type, title, year, season=''):
        """Search implementation for tvmovieflix"""
        logger.log(f'[TVMOVIEFLIX] Starting search: type={video_type}, title={title}, year={year}', log_utils.LOGDEBUG)
        results = []
        
        try:
            # Build search URL
            search_query = urllib.parse.quote_plus(title)
            search_url = self.base_url + self.search_path % search_query
            logger.log(f'[TVMOVIEFLIX] Search URL: {search_url}', log_utils.LOGDEBUG)
            
            html = self._http_get(search_url, cache_limit=1)
            logger.log(f'[TVMOVIEFLIX] Search HTML length: {len(html) if html else 0}', log_utils.LOGDEBUG)
            
            if not html:
                logger.log('[TVMOVIEFLIX] No HTML received from search', log_utils.LOGWARNING)
                return results

            # Parse search results
            soup = BeautifulSoup(html, 'html.parser')
            
            # Look for post divs (pattern from scrubs: div with id="post-.*")
            post_divs = soup.find_all('div', id=re.compile(r'post-.*'))
            logger.log(f'[TVMOVIEFLIX] Found {len(post_divs)} post divs', log_utils.LOGDEBUG)
            
            for post_div in post_divs:
                try:
                    # Look for title link (pattern from scrubs: a with class="title")
                    title_link = post_div.find('a', class_='title')
                    if not title_link:
                        continue
                    
                    result_title = title_link.get_text(strip=True)
                    result_url = title_link.get('href')
                    
                    # Look for year (pattern from scrubs: <span>YYYY</span>)
                    year_span = post_div.find('span', string=re.compile(r'\d{4}'))
                    result_year = year_span.get_text(strip=True) if year_span else year
                    
                    logger.log(f'[TVMOVIEFLIX] Found result: {result_title} ({result_year}) - {result_url}', log_utils.LOGDEBUG)
                    
                    # Check if this matches what we're looking for
                    if self._is_match(result_title, title, result_year, year):
                        result = {
                            'title': result_title,
                            'year': result_year,
                            'url': result_url
                        }
                        results.append(result)
                        logger.log(f'[TVMOVIEFLIX] Added matching result: {result}', log_utils.LOGDEBUG)
                    else:
                        logger.log(f'[TVMOVIEFLIX] Result did not match search criteria', log_utils.LOGDEBUG)
                        
                except Exception as e:
                    logger.log(f'[TVMOVIEFLIX] Error parsing search result: {e}', log_utils.LOGDEBUG)
                    continue
                    
        except Exception as e:
            logger.log(f'[TVMOVIEFLIX] Search error: {e}', log_utils.LOGERROR)
            
        logger.log(f'[TVMOVIEFLIX] Search completed, found {len(results)} results', log_utils.LOGDEBUG)
        return results

    def _is_match(self, result_title, search_title, result_year, search_year):
        """Check if a search result matches the criteria"""
        try:
            # Normalize titles for comparison
            norm_result = scraper_utils.normalize_title(result_title) if hasattr(scraper_utils, 'normalize_title') else result_title.lower()
            norm_search = scraper_utils.normalize_title(search_title) if hasattr(scraper_utils, 'normalize_title') else search_title.lower()
            
            # Check title match
            title_match = norm_search in norm_result or norm_result in norm_search
            
            # Check year match (allow some flexibility)
            year_match = True
            if search_year and result_year:
                try:
                    search_year_int = int(search_year)
                    result_year_int = int(result_year)
                    year_match = abs(search_year_int - result_year_int) <= 1  # Allow 1 year difference
                except ValueError:
                    year_match = search_year == result_year
            
            match = title_match and year_match
            logger.log(f'[TVMOVIEFLIX] Match check: title_match={title_match}, year_match={year_match}, overall={match}', log_utils.LOGDEBUG)
            
            return match
            
        except Exception as e:
            logger.log(f'[TVMOVIEFLIX] Error in match check: {e}', log_utils.LOGERROR)
            return False

    def get_url(self, video):
        """Get URL for the video based on its type"""
        logger.log(f'[TVMOVIEFLIX] Getting URL for video: {video.title} ({video.year})', log_utils.LOGDEBUG)
        
        if video.video_type == VIDEO_TYPES.MOVIE:
            return self._movie_url(video)
        else:
            logger.log(f'[TVMOVIEFLIX] Unsupported video type: {video.video_type}', log_utils.LOGWARNING)
            return None

    def _movie_url(self, video):
        """Get URL for a movie using search results"""
        logger.log(f'[TVMOVIEFLIX] Getting movie URL for: {video.title} ({video.year})', log_utils.LOGDEBUG)
        
        # Use the default get_url mechanism which handles caching and search
        return self._default_get_url(video)

    def resolve_link(self, link):
        """Resolve the final link if needed"""
        return link