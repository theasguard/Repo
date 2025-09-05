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
import time
import json
import base64
from bs4 import BeautifulSoup
from asguard_lib import scraper_utils
from asguard_lib.constants import VIDEO_TYPES, QUALITIES
from . import scraper
import log_utils
import kodi

logger = log_utils.Logger.get_logger()
BASE_URL = 'https://hianime.bz'

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url') or BASE_URL
        self.domains = ['hianime.bz', 'hianime.to', 'aniwatch.to']

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'HiAnime'

    def get_sources(self, video):
        logger.log(f'[HIANIME] Starting get_sources for video: {video.title} S{video.season}E{video.episode}', log_utils.LOGDEBUG)
        sources = []
        source_url = self.get_url(video)
        
        if not source_url or source_url == scraper_utils.FORCE_NO_MATCH:
            logger.log(f'[HIANIME] No source URL found for video: {source_url}', log_utils.LOGWARNING)
            return sources

        url = scraper_utils.urljoin(self.base_url, source_url)
        logger.log(f'[HIANIME] Fetching URL: {url}', log_utils.LOGDEBUG)
        
        html = self._http_get(url, cache_limit=1)
        logger.log(f'[HIANIME] Got HTML length: {len(html) if html else 0}', log_utils.LOGDEBUG)
        
        if not html:
            logger.log('[HIANIME] No HTML received from hianime', log_utils.LOGWARNING)
            return sources

        # Log a snippet of the HTML to see what we're working with
        html_snippet = html[:500] if html else ""
        logger.log(f'[HIANIME] HTML snippet: {html_snippet}', log_utils.LOGDEBUG)

        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Method 1: Look for episode data-id in the watch page
            episode_id = self._extract_episode_id(soup, html)
            if episode_id:
                logger.log(f'[HIANIME] Found episode ID: {episode_id}', log_utils.LOGDEBUG)
                servers = self._get_episode_servers(episode_id)
                
                for server in servers:
                    try:
                        stream_sources = self._get_server_sources(server['id'])
                        for source in stream_sources:
                            sources.append(source)
                            
                    except Exception as e:
                        logger.log(f'[HIANIME] Error processing server {server}: {e}', log_utils.LOGERROR)
                        continue
            
            # Method 2: Look for direct server links in the page
            server_links = self._extract_server_links(soup)
            for server_link in server_links:
                try:
                    stream_sources = self._process_server_link(server_link)
                    sources.extend(stream_sources)
                except Exception as e:
                    logger.log(f'[HIANIME] Error processing server link {server_link}: {e}', log_utils.LOGERROR)
                    continue
            
            # Method 3: Look for embedded players and iframes
            iframes = soup.find_all('iframe', src=True)
            for iframe in iframes:
                try:
                    stream_url = iframe['src']
                    
                    if stream_url.startswith('//'):
                        stream_url = 'https:' + stream_url
                    elif stream_url.startswith('/'):
                        stream_url = scraper_utils.urljoin(self.base_url, stream_url)
                        
                    if not stream_url.startswith('http'):
                        continue
                        
                    host = urllib.parse.urlparse(stream_url).hostname
                    if not host:
                        continue
                        
                    quality = self._determine_quality_from_url(stream_url)
                    
                    source = {
                        'class': self,
                        'quality': quality, 
                        'url': stream_url,
                        'host': host,
                        'multi-part': False,
                        'rating': None,
                        'views': None,
                        'direct': False,
                        'extra': 'Iframe'
                    }
                    sources.append(source)
                    logger.log(f'[HIANIME] Found iframe source: {source}', log_utils.LOGDEBUG)
                    
                except Exception as e:
                    logger.log(f'[HIANIME] Error processing iframe: {e}', log_utils.LOGDEBUG)
                    continue

        except Exception as e:
            logger.log(f'[HIANIME] Error parsing HTML: {e}', log_utils.LOGERROR)

        logger.log(f'[HIANIME] Found {len(sources)} total sources', log_utils.LOGDEBUG)
        return sources

    def _extract_episode_id(self, soup, html):
        """
        Extract episode ID from various possible locations
        """
        episode_id = None
        
        try:
            # Method 1: Look for data-id in episode elements
            episode_elem = soup.find(['div', 'a'], attrs={'data-id': True})
            if episode_elem:
                episode_id = episode_elem.get('data-id')
                logger.log(f'[HIANIME] Found episode ID from data-id: {episode_id}', log_utils.LOGDEBUG)
                return episode_id
            
            # Method 2: Look for episode ID in JavaScript variables
            js_patterns = [
                r'episodeId["\']?\s*[:=]\s*["\']?(\d+)',
                r'episode_id["\']?\s*[:=]\s*["\']?(\d+)',
                r'data-id["\']?\s*[:=]\s*["\']?(\d+)',
                r'id["\']?\s*[:=]\s*["\']?(\d+)'
            ]
            
            for pattern in js_patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    episode_id = match.group(1)
                    logger.log(f'[HIANIME] Found episode ID from JS pattern: {episode_id}', log_utils.LOGDEBUG)
                    return episode_id
            
            # Method 3: Extract from URL patterns in the page
            url_patterns = [
                r'/ajax/v2/episode/servers\?episodeId=(\d+)',
                r'/episode/(\d+)',
                r'episodeId=(\d+)'
            ]
            
            for pattern in url_patterns:
                match = re.search(pattern, html)
                if match:
                    episode_id = match.group(1)
                    logger.log(f'[HIANIME] Found episode ID from URL pattern: {episode_id}', log_utils.LOGDEBUG)
                    return episode_id
                    
        except Exception as e:
            logger.log(f'[HIANIME] Error extracting episode ID: {e}', log_utils.LOGERROR)
        
        return episode_id

    def _get_episode_servers(self, episode_id):
        """
        Get available servers for an episode
        """
        servers = []
        try:
            # Try different server endpoint patterns
            server_urls = [
                f'{self.base_url}/ajax/v2/episode/servers?episodeId={episode_id}',
                f'{self.base_url}/ajax/episode/servers?id={episode_id}',
                f'{self.base_url}/ajax/servers/{episode_id}'
            ]
            
            for server_url in server_urls:
                logger.log(f'[HIANIME] Trying server URL: {server_url}', log_utils.LOGDEBUG)
                
                html = self._http_get(server_url, cache_limit=0.5)
                if not html:
                    continue
                
                try:
                    # Try parsing as JSON
                    data = json.loads(html)
                    if 'html' in data:
                        soup = BeautifulSoup(data['html'], 'html.parser')
                        server_elements = soup.find_all(['a', 'div'], attrs={'data-id': True})
                        
                        for elem in server_elements:
                            server_id = elem.get('data-id')
                            server_name = elem.get_text(strip=True) or elem.get('title', 'Unknown')
                            server_type = elem.get('data-type', 'sub')
                            
                            if server_id:
                                servers.append({
                                    'id': server_id,
                                    'name': server_name,
                                    'type': server_type
                                })
                                
                    elif 'servers' in data:
                        for server in data['servers']:
                            servers.append({
                                'id': server.get('id', ''),
                                'name': server.get('name', 'Unknown'),
                                'type': server.get('type', 'sub')
                            })
                            
                    if servers:
                        break  # Found servers, no need to try other URLs
                        
                except json.JSONDecodeError:
                    # Try parsing as HTML
                    soup = BeautifulSoup(html, 'html.parser')
                    server_elements = soup.find_all(['a', 'div'], attrs={'data-id': True})
                    
                    for elem in server_elements:
                        server_id = elem.get('data-id')
                        server_name = elem.get_text(strip=True) or elem.get('title', 'Unknown')
                        
                        if server_id:
                            servers.append({
                                'id': server_id,
                                'name': server_name,
                                'type': 'sub'
                            })
                    
                    if servers:
                        break
                        
        except Exception as e:
            logger.log(f'[HIANIME] Error getting episode servers: {e}', log_utils.LOGERROR)
        
        logger.log(f'[HIANIME] Found {len(servers)} servers', log_utils.LOGDEBUG)
        return servers

    def _get_server_sources(self, server_id):
        """
        Get streaming sources from a server ID
        """
        sources = []
        try:
            # Try different source endpoint patterns
            source_urls = [
                f'{self.base_url}/ajax/v2/episode/sources?id={server_id}',
                f'{self.base_url}/ajax/episode/sources?id={server_id}',
                f'{self.base_url}/ajax/sources/{server_id}'
            ]
            
            for source_url in source_urls:
                logger.log(f'[HIANIME] Trying source URL: {source_url}', log_utils.LOGDEBUG)
                
                html = self._http_get(source_url, cache_limit=0.25)
                if not html:
                    continue
                
                try:
                    data = json.loads(html)
                    
                    # Extract streaming URL
                    stream_url = None
                    if 'link' in data:
                        stream_url = data['link']
                    elif 'url' in data:
                        stream_url = data['url']
                    elif 'source' in data:
                        stream_url = data['source']
                    
                    if stream_url:
                        # Decode if it's base64 encoded
                        if self._is_base64(stream_url):
                            try:
                                stream_url = base64.b64decode(stream_url).decode('utf-8')
                            except:
                                pass
                        
                        host = urllib.parse.urlparse(stream_url).hostname
                        if host:
                            quality = self._determine_quality_from_url(stream_url)
                            
                            source = {
                                'class': self,
                                'quality': quality,
                                'url': stream_url,
                                'host': host,
                                'multi-part': False,
                                'rating': None,
                                'views': None,
                                'direct': False,
                                'extra': f'Server {server_id}'
                            }
                            sources.append(source)
                            logger.log(f'[HIANIME] Added server source: {source}', log_utils.LOGDEBUG)
                    
                    if sources:
                        break  # Found sources, no need to try other URLs
                        
                except json.JSONDecodeError:
                    logger.log(f'[HIANIME] Failed to parse JSON from {source_url}', log_utils.LOGDEBUG)
                    continue
                    
        except Exception as e:
            logger.log(f'[HIANIME] Error getting server sources: {e}', log_utils.LOGERROR)
        
        return sources

    def _extract_server_links(self, soup):
        """
        Extract server links from the page
        """
        server_links = []
        
        try:
            # Look for server selection elements
            server_elements = soup.find_all(['a', 'button', 'div'], attrs={
                'data-server': True
            })
            
            for elem in server_elements:
                server_id = elem.get('data-server')
                if server_id:
                    server_links.append(server_id)
            
            # Look for links with server patterns
            links = soup.find_all('a', href=re.compile(r'/(server|stream|watch)/', re.I))
            for link in links:
                href = link.get('href')
                if href:
                    server_links.append(href)
                    
        except Exception as e:
            logger.log(f'[HIANIME] Error extracting server links: {e}', log_utils.LOGERROR)
        
        return server_links

    def _process_server_link(self, server_link):
        """
        Process a server link to extract streaming sources
        """
        sources = []
        
        try:
            if server_link.startswith('/'):
                url = scraper_utils.urljoin(self.base_url, server_link)
            else:
                url = server_link
            
            html = self._http_get(url, cache_limit=0.5)
            if html:
                # Look for streaming URLs in the response
                stream_patterns = [
                    r'"(https?://[^"]+\.m3u8[^"]*)"',
                    r'"(https?://[^"]+\.mp4[^"]*)"',
                    r'"file":\s*"([^"]+)"',
                    r'"source":\s*"([^"]+)"',
                    r'"url":\s*"([^"]+)"'
                ]
                
                for pattern in stream_patterns:
                    matches = re.findall(pattern, html)
                    for match in matches:
                        if match.startswith('http'):
                            host = urllib.parse.urlparse(match).hostname
                            if host:
                                quality = self._determine_quality_from_url(match)
                                
                                source = {
                                    'class': self,
                                    'quality': quality,
                                    'url': match,
                                    'host': host,
                                    'multi-part': False,
                                    'rating': None,
                                    'views': None,
                                    'direct': True,
                                    'extra': 'Direct'
                                }
                                sources.append(source)
                                
        except Exception as e:
            logger.log(f'[HIANIME] Error processing server link: {e}', log_utils.LOGERROR)
        
        return sources

    def _is_base64(self, s):
        """
        Check if string is base64 encoded
        """
        try:
            if isinstance(s, str):
                sb_bytes = bytes(s, 'ascii')
            elif isinstance(s, bytes):
                sb_bytes = s
            else:
                raise ValueError("Argument must be string or bytes")
            return base64.b64encode(base64.b64decode(sb_bytes)) == sb_bytes
        except Exception:
            return False

    def _determine_quality_from_url(self, url):
        """
        Determine video quality from URL
        """
        url_lower = url.lower()
        
        if any(q in url_lower for q in ['1080', 'fhd']):
            return QUALITIES.HD1080
        elif any(q in url_lower for q in ['720', 'hd']):
            return QUALITIES.HD720
        elif any(q in url_lower for q in ['480']):
            return QUALITIES.HIGH
        elif any(q in url_lower for q in ['360']):
            return QUALITIES.MEDIUM
        elif any(q in url_lower for q in ['240']):
            return QUALITIES.LOW
        
        # Default quality for anime
        return QUALITIES.HD720

    def _clean_title_for_url(self, title):
        """
        Clean title for URL use, following anime naming conventions
        """
        try:
            if hasattr(scraper_utils, 'to_slug'):
                return scraper_utils.to_slug(title)
            else:
                # Manual slug creation for anime titles
                import re
                # Remove special characters but keep some anime-specific ones
                slug = re.sub(r'[^\w\s\-:]', '', title.lower())
                # Replace spaces and colons with hyphens
                slug = re.sub(r'[\s:]+', '-', slug)
                # Remove multiple consecutive hyphens
                slug = re.sub(r'-+', '-', slug)
                slug = slug.strip('-')
                logger.log(f'[HIANIME] Manual slug creation: {title} -> {slug}', log_utils.LOGDEBUG)
                return slug
        except Exception as e:
            logger.log(f'[HIANIME] Error in _clean_title_for_url: {e}', log_utils.LOGERROR)
            # Ultimate fallback
            return title.lower().replace(' ', '-').replace("'", "").replace(":", "-")

    def search(self, video_type, title, year, season=''):
        """
        Search implementation for hianime
        """
        logger.log(f'[HIANIME] Starting search: type={video_type}, title={title}, year={year}, season={season}', log_utils.LOGDEBUG)
        results = []
        
        try:
            # Clean the title for search
            search_title = title.replace(' ', '+')
            search_url = f'{self.base_url}/search?keyword={urllib.parse.quote_plus(search_title)}'
            
            logger.log(f'[HIANIME] Search URL: {search_url}', log_utils.LOGDEBUG)
            
            html = self._http_get(search_url, cache_limit=1)
            logger.log(f'[HIANIME] Search HTML length: {len(html) if html else 0}', log_utils.LOGDEBUG)
            
            if html:
                soup = BeautifulSoup(html, 'html.parser')
                
                # Look for anime results - HiAnime specific structure
                # Based on the HTML: <div class="flw-item">
                anime_items = soup.find_all('div', class_='flw-item')
                
                logger.log(f'[HIANIME] Found {len(anime_items)} flw-item elements', log_utils.LOGDEBUG)
                
                for item in anime_items[:10]:  # Limit to first 10 results
                    try:
                        # Extract the watch link from film-poster-ahref
                        # <a href="/watch/clevatess-19760" class="film-poster-ahref item-qtip" title="Clevatess" data-id="19760">
                        watch_link = item.find('a', class_='film-poster-ahref')
                        if not watch_link:
                            logger.log(f'[HIANIME] No film-poster-ahref found in item', log_utils.LOGDEBUG)
                            continue
                        
                        result_url = watch_link.get('href')
                        anime_id = watch_link.get('data-id')
                        result_title = watch_link.get('title', '')
                        
                        logger.log(f'[HIANIME] Found watch link: {result_url}, data-id: {anime_id}, title: {result_title}', log_utils.LOGDEBUG)
                        
                        if not result_url or not anime_id:
                            logger.log(f'[HIANIME] Missing URL or anime ID', log_utils.LOGDEBUG)
                            continue
                        
                        # Also try to get title from film-name if not available
                        if not result_title:
                            film_name = item.find('h3', class_='film-name')
                            if film_name:
                                title_link = film_name.find('a')
                                if title_link:
                                    result_title = title_link.get_text(strip=True)
                        
                        # Convert watch URL to detail URL for consistency
                        # /watch/clevatess-19760 -> /detail/clevatess-19760
                        if result_url.startswith('/watch/'):
                            detail_url = result_url.replace('/watch/', '/detail/')
                        else:
                            detail_url = result_url
                        
                        # Extract year if available (not always present in search results)
                        result_year = year  # Default to search year
                        
                        # Skip invalid URLs (social media links, etc.)
                        if any(invalid in result_url.lower() for invalid in ['discord.gg', 'twitter.com', 'reddit.com', 'telegram', 'tinyurl']):
                            logger.log(f'[HIANIME] Skipping invalid URL: {result_url}', log_utils.LOGDEBUG)
                            continue
                        
                        # Check if title matches reasonably well
                        if result_title and self._title_matches(title, result_title):
                            result = {
                                'title': result_title,
                                'year': result_year,
                                'url': detail_url,
                                'anime_id': anime_id
                            }
                            results.append(result)
                            logger.log(f'[HIANIME] Added search result: {result}', log_utils.LOGDEBUG)
                        else:
                            logger.log(f'[HIANIME] Title mismatch: search="{title}" vs result="{result_title}"', log_utils.LOGDEBUG)
                        
                    except Exception as e:
                        logger.log(f'[HIANIME] Error processing search result: {e}', log_utils.LOGERROR)
                        continue
                        
        except Exception as e:
            logger.log(f'[HIANIME] Search error: {e}', log_utils.LOGERROR)
            
        logger.log(f'[HIANIME] Search completed, found {len(results)} results', log_utils.LOGDEBUG)
        return results

    def _title_matches(self, search_title, result_title):
        """
        Check if the result title reasonably matches the search title
        """
        search_lower = search_title.lower()
        result_lower = result_title.lower()
        
        # Exact match
        if search_lower == result_lower:
            return True
        
        # Check if search title is contained in result
        if search_lower in result_lower:
            return True
        
        # Check if result title is contained in search (for longer search titles)
        if result_lower in search_lower:
            return True
        
        # Check word overlap for anime titles
        search_words = set(search_lower.split())
        result_words = set(result_lower.split())
        
        # If more than half the words match, consider it a match
        if len(search_words & result_words) >= len(search_words) * 0.5:
            return True
        
        return False

    def _extract_anime_id_from_url(self, url):
        """
        Extract anime ID from HiAnime URL
        Format: /detail/anime-name-12345 or /watch/anime-name-12345
        """
        try:
            # Look for numeric ID at the end of the URL
            match = re.search(r'-(\d+)(?:\?|$)', url)
            if match:
                return match.group(1)
            
            # Fallback: look for any numeric sequence
            match = re.search(r'(\d+)', url)
            if match:
                return match.group(1)
                
        except Exception as e:
            logger.log(f'[HIANIME] Error extracting anime ID from URL {url}: {e}', log_utils.LOGERROR)
        
        return None

    def _get_episode_list(self, anime_id):
        """
        Get episode list for an anime to find the correct episode ID
        """
        episodes = []
        try:
            # Try different episode list endpoints
            episode_urls = [
                f'{self.base_url}/ajax/v2/episode/list/{anime_id}',
                f'{self.base_url}/ajax/episode/list/{anime_id}',
                f'{self.base_url}/ajax/episodes/{anime_id}'
            ]
            
            for episode_url in episode_urls:
                logger.log(f'[HIANIME] Trying episode list URL: {episode_url}', log_utils.LOGDEBUG)
                
                html = self._http_get(episode_url, cache_limit=1)
                if not html:
                    continue
                
                try:
                    data = json.loads(html)
                    if 'html' in data:
                        soup = BeautifulSoup(data['html'], 'html.parser')
                        episode_elements = soup.find_all(['a', 'div'], attrs={'data-id': True})
                        
                        for elem in episode_elements:
                            episode_id = elem.get('data-id')
                            episode_num = elem.get('data-number') or elem.get_text(strip=True)
                            
                            # Try to extract episode number from text or attributes
                            if not episode_num.isdigit():
                                num_match = re.search(r'(\d+)', episode_num)
                                episode_num = num_match.group(1) if num_match else '1'
                            
                            if episode_id:
                                episodes.append({
                                    'id': episode_id,
                                    'number': int(episode_num),
                                    'title': elem.get('title', f'Episode {episode_num}')
                                })
                                
                    if episodes:
                        break  # Found episodes, no need to try other URLs
                        
                except json.JSONDecodeError:
                    # Try parsing as HTML
                    soup = BeautifulSoup(html, 'html.parser')
                    episode_elements = soup.find_all(['a', 'div'], attrs={'data-id': True})
                    
                    for elem in episode_elements:
                        episode_id = elem.get('data-id')
                        episode_text = elem.get_text(strip=True)
                        
                        # Extract episode number
                        num_match = re.search(r'(\d+)', episode_text)
                        episode_num = int(num_match.group(1)) if num_match else 1
                        
                        if episode_id:
                            episodes.append({
                                'id': episode_id,
                                'number': episode_num,
                                'title': f'Episode {episode_num}'
                            })
                    
                    if episodes:
                        break
                        
        except Exception as e:
            logger.log(f'[HIANIME] Error getting episode list: {e}', log_utils.LOGERROR)
        
        logger.log(f'[HIANIME] Found {len(episodes)} episodes for anime {anime_id}', log_utils.LOGDEBUG)
        return episodes

    def get_url(self, video):
        """
        Generate URL for the video based on its type using the default method
        """
        return self._default_get_url(video)

    def _get_episode_url(self, show_url, video):
        """
        Get episode URL from show URL - required by _default_get_url
        """
        try:
            if not show_url:
                return None
                
            # Extract anime ID from the show URL
            anime_id = self._extract_anime_id_from_url(show_url)
            if not anime_id:
                logger.log(f'[HIANIME] Could not extract anime ID from show URL: {show_url}', log_utils.LOGWARNING)
                return None
            
            logger.log(f'[HIANIME] Extracted anime ID: {anime_id}', log_utils.LOGDEBUG)
            
            # Get episode list to find the correct episode ID
            episodes = self._get_episode_list(anime_id)
            if not episodes:
                logger.log(f'[HIANIME] No episodes found for anime {anime_id}', log_utils.LOGWARNING)
                return None
            
            # Find the episode matching our season/episode
            target_episode = int(video.episode)
            
            # For multi-season anime, calculate absolute episode number
            if hasattr(video, 'season') and int(video.season) > 1:
                # This is a rough calculation - you might need to adjust based on actual episode counts
                target_episode = (int(video.season) - 1) * 12 + int(video.episode)
            
            # Find matching episode
            matching_episode = None
            for ep in episodes:
                if ep['number'] == target_episode:
                    matching_episode = ep
                    break
            
            if not matching_episode:
                # Fallback: use the episode number directly if available
                if target_episode <= len(episodes):
                    matching_episode = episodes[target_episode - 1]
                else:
                    logger.log(f'[HIANIME] Episode {target_episode} not found in {len(episodes)} available episodes', log_utils.LOGWARNING)
                    return None
            
            # Generate the watch URL with the correct format
            # HiAnime format: /watch/anime-name-{anime_id}?ep={episode_id}
            anime_name = show_url.replace('/detail/', '').replace(f'-{anime_id}', '')
            episode_url = f'/watch/{anime_name}-{anime_id}?ep={matching_episode["id"]}'
            
            logger.log(f'[HIANIME] Generated episode URL: {episode_url}', log_utils.LOGDEBUG)
            return episode_url
            
        except Exception as e:
            logger.log(f'[HIANIME] Error generating episode URL: {e}', log_utils.LOGERROR)
            return None

    def resolve_link(self, link):
        """
        Resolve the final streaming link if needed
        """
        try:
            # If it's an AJAX endpoint, get the actual streaming URL
            if '/ajax/' in link and ('sources' in link or 'servers' in link):
                html = self._http_get(link, cache_limit=0.25)
                if html:
                    try:
                        data = json.loads(html)
                        if 'link' in data:
                            stream_url = data['link']
                            # Decode if base64 encoded
                            if self._is_base64(stream_url):
                                try:
                                    stream_url = base64.b64decode(stream_url).decode('utf-8')
                                except:
                                    pass
                            return stream_url
                        elif 'url' in data:
                            return data['url']
                    except json.JSONDecodeError:
                        pass
            
            return link
            
        except Exception as e:
            logger.log(f'[HIANIME] Error resolving link: {e}', log_utils.LOGERROR)
            return link