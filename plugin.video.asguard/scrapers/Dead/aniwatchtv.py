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
from bs4 import BeautifulSoup
from asguard_lib import scraper_utils
from asguard_lib.constants import VIDEO_TYPES, QUALITIES
from . import scraper
import log_utils
import kodi

logger = log_utils.Logger.get_logger()
BASE_URL = 'https://aniwatchtv.to'

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url') or BASE_URL
        self.domains = ['aniwatchtv.to', 'aniwatch.to', 'zoro.to']

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'AniWatchTV'

    def get_sources(self, video):
        logger.log(f'[ANIWATCHTV] Starting get_sources for video: {video.title} S{video.season}E{video.episode}', log_utils.LOGDEBUG)
        sources = []
        source_url = self.get_url(video)
        
        if not source_url or source_url == scraper_utils.FORCE_NO_MATCH:
            logger.log(f'[ANIWATCHTV] No source URL found for video: {source_url}', log_utils.LOGWARNING)
            return sources

        url = scraper_utils.urljoin(self.base_url, source_url)
        logger.log(f'[ANIWATCHTV] Fetching URL: {url}', log_utils.LOGDEBUG)
        
        html = self._http_get(url, cache_limit=1)
        logger.log(f'[ANIWATCHTV] Got HTML length: {len(html) if html else 0}', log_utils.LOGDEBUG)
        
        if not html:
            logger.log('[ANIWATCHTV] No HTML received from aniwatchtv', log_utils.LOGWARNING)
            return sources

        # Log a snippet of the HTML to see what we're working with
        html_snippet = html[:500] if html else ""
        logger.log(f'[ANIWATCHTV] HTML snippet: {html_snippet}', log_utils.LOGDEBUG)

        try:
            soup = BeautifulSoup(html, 'html.parser')
            
            # Look for episode data-id or episode links
            episode_links = []
            
            # Pattern 1: Look for episode links with data-id attributes
            episode_elements = soup.find_all(['a', 'div'], attrs={'data-id': True})
            for element in episode_elements:
                data_id = element.get('data-id')
                if data_id:
                    episode_links.append(data_id)
                    logger.log(f'[ANIWATCHTV] Found episode data-id: {data_id}', log_utils.LOGDEBUG)
            
            # Pattern 2: Look for direct episode links
            episode_link_elements = soup.find_all('a', href=re.compile(r'/watch/'))
            for link in episode_link_elements:
                href = link.get('href')
                if href:
                    episode_links.append(href)
                    logger.log(f'[ANIWATCHTV] Found episode link: {href}', log_utils.LOGDEBUG)
            
            # Pattern 3: Look for server selection buttons or links
            server_elements = soup.find_all(['button', 'a'], attrs={'data-server': True})
            for server in server_elements:
                server_id = server.get('data-server')
                if server_id:
                    episode_links.append(server_id)
                    logger.log(f'[ANIWATCHTV] Found server data: {server_id}', log_utils.LOGDEBUG)
            
            # Process found links
            for i, link_data in enumerate(episode_links):
                try:
                    logger.log(f'[ANIWATCHTV] Processing link {i+1}/{len(episode_links)}: {link_data}', log_utils.LOGDEBUG)
                    
                    # If it's a data-id, construct the streaming URL
                    if link_data.isdigit():
                        stream_url = f'{self.base_url}/ajax/v2/episode/servers?episodeId={link_data}'
                    elif link_data.startswith('/'):
                        stream_url = scraper_utils.urljoin(self.base_url, link_data)
                    else:
                        stream_url = link_data
                    
                    # Get streaming servers
                    servers = self._get_streaming_servers(stream_url)
                    
                    for server in servers:
                        try:
                            host = urllib.parse.urlparse(server['url']).hostname
                            if not host:
                                continue
                            
                            # Determine quality based on server name or URL
                            quality = self._determine_quality(server.get('name', ''), server['url'])
                            
                            source = {
                                'class': self,
                                'quality': quality,
                                'url': server['url'],
                                'host': host,
                                'multi-part': False,
                                'rating': None,
                                'views': None,
                                'direct': False,
                                'extra': server.get('name', ''),
                            }
                            sources.append(source)
                            logger.log(f'[ANIWATCHTV] Added source: {source}', log_utils.LOGDEBUG)
                            
                        except Exception as e:
                            logger.log(f'[ANIWATCHTV] Error processing server: {e}', log_utils.LOGERROR)
                            continue
                    
                except Exception as e:
                    logger.log(f'[ANIWATCHTV] Error processing link {i+1}: {e}', log_utils.LOGERROR)
                    continue

            # Fallback: Look for direct iframe sources
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
                        
                    quality = scraper_utils.blog_get_quality(video, stream_url, host)
                    
                    source = {
                        'class': self,
                        'quality': quality, 
                        'url': stream_url,
                        'host': host,
                        'multi-part': False,
                        'rating': None,
                        'views': None,
                        'direct': False,
                    }
                    sources.append(source)
                    logger.log(f'[ANIWATCHTV] Found iframe source: {source}', log_utils.LOGDEBUG)
                    
                except Exception as e:
                    logger.log(f'[ANIWATCHTV] Error processing iframe: {e}', log_utils.LOGDEBUG)
                    continue

        except Exception as e:
            logger.log(f'[ANIWATCHTV] Error parsing HTML: {e}', log_utils.LOGERROR)

        logger.log(f'[ANIWATCHTV] Found {len(sources)} total sources', log_utils.LOGDEBUG)
        return sources

    def _get_streaming_servers(self, url):
        """
        Get streaming servers from the episode or server URL
        """
        servers = []
        try:
            logger.log(f'[ANIWATCHTV] Getting streaming servers from: {url}', log_utils.LOGDEBUG)
            
            html = self._http_get(url, cache_limit=0.5)
            if not html:
                return servers
            
            # Try to parse as JSON first (for AJAX endpoints)
            try:
                data = json.loads(html)
                if 'html' in data:
                    # Parse the HTML content from JSON response
                    soup = BeautifulSoup(data['html'], 'html.parser')
                    server_elements = soup.find_all(['a', 'div'], attrs={'data-id': True})
                    
                    for element in server_elements:
                        server_id = element.get('data-id')
                        server_name = element.get_text(strip=True) or element.get('title', '')
                        
                        if server_id:
                            # Construct streaming URL
                            stream_url = f'{self.base_url}/ajax/v2/episode/sources?id={server_id}'
                            servers.append({
                                'name': server_name,
                                'url': stream_url,
                                'id': server_id
                            })
                            
                elif 'servers' in data:
                    # Direct server list in JSON
                    for server in data['servers']:
                        servers.append({
                            'name': server.get('name', ''),
                            'url': server.get('url', ''),
                            'id': server.get('id', '')
                        })
                        
            except json.JSONDecodeError:
                # Parse as HTML
                soup = BeautifulSoup(html, 'html.parser')
                
                # Look for server links
                server_links = soup.find_all('a', href=True)
                for link in server_links:
                    href = link['href']
                    name = link.get_text(strip=True)
                    
                    if href.startswith('/'):
                        href = scraper_utils.urljoin(self.base_url, href)
                    
                    servers.append({
                        'name': name,
                        'url': href,
                        'id': ''
                    })
                
                # Look for embedded players
                iframes = soup.find_all('iframe', src=True)
                for iframe in iframes:
                    src = iframe['src']
                    if src.startswith('/'):
                        src = scraper_utils.urljoin(self.base_url, src)
                    
                    servers.append({
                        'name': 'Embedded Player',
                        'url': src,
                        'id': ''
                    })
            
            logger.log(f'[ANIWATCHTV] Found {len(servers)} streaming servers', log_utils.LOGDEBUG)
            
        except Exception as e:
            logger.log(f'[ANIWATCHTV] Error getting streaming servers: {e}', log_utils.LOGERROR)
        
        return servers

    def _determine_quality(self, server_name, url):
        """
        Determine video quality based on server name or URL
        """
        server_name = server_name.lower()
        url = url.lower()
        
        # Quality indicators in server names
        if any(q in server_name for q in ['1080', '1080p', 'fhd']):
            return QUALITIES.HD1080
        elif any(q in server_name for q in ['720', '720p', 'hd']):
            return QUALITIES.HD720
        elif any(q in server_name for q in ['480', '480p']):
            return QUALITIES.HIGH
        elif any(q in server_name for q in ['360', '360p']):
            return QUALITIES.MEDIUM
        elif any(q in server_name for q in ['240', '240p']):
            return QUALITIES.LOW
        
        # Quality indicators in URLs
        if any(q in url for q in ['1080', 'fhd']):
            return QUALITIES.HD1080
        elif any(q in url for q in ['720', 'hd']):
            return QUALITIES.HD720
        elif any(q in url for q in ['480']):
            return QUALITIES.HIGH
        elif any(q in url for q in ['360']):
            return QUALITIES.MEDIUM
        elif any(q in url for q in ['240']):
            return QUALITIES.LOW
        
        # Default quality
        return QUALITIES.HIGH

    def _clean_title_for_url(self, title):
        """
        Clean title for URL use, following anime naming conventions
        """
        try:
            if hasattr(scraper_utils, 'to_slug'):
                return scraper_utils.to_slug(title)
            else:
                # Fallback manual slug creation for anime titles
                import re
                # Remove special characters but keep some anime-specific ones
                slug = re.sub(r'[^\w\s\-:]', '', title.lower())
                # Replace spaces and colons with hyphens
                slug = re.sub(r'[\s:]+', '-', slug)
                # Remove multiple consecutive hyphens
                slug = re.sub(r'-+', '-', slug)
                slug = slug.strip('-')
                logger.log(f'[ANIWATCHTV] Manual slug creation: {title} -> {slug}', log_utils.LOGDEBUG)
                return slug
        except Exception as e:
            logger.log(f'[ANIWATCHTV] Error in _clean_title_for_url: {e}', log_utils.LOGERROR)
            # Ultimate fallback
            return title.lower().replace(' ', '-').replace("'", "").replace(":", "-")

    def search(self, video_type, title, year, season=''):
        """
        Search implementation for aniwatchtv
        """
        logger.log(f'[ANIWATCHTV] Starting search: type={video_type}, title={title}, year={year}, season={season}', log_utils.LOGDEBUG)
        results = []
        
        try:
            # Clean the title for search
            search_title = title.replace(' ', '+')
            search_url = f'{self.base_url}/search?keyword={urllib.parse.quote_plus(search_title)}'
            
            logger.log(f'[ANIWATCHTV] Search URL: {search_url}', log_utils.LOGDEBUG)
            
            html = self._http_get(search_url, cache_limit=1)
            logger.log(f'[ANIWATCHTV] Search HTML length: {len(html) if html else 0}', log_utils.LOGDEBUG)
            
            if html:
                soup = BeautifulSoup(html, 'html.parser')
                
                # Look for anime results - common patterns for anime sites
                anime_items = soup.find_all(['div', 'article'], class_=re.compile(r'(item|card|anime|result)', re.I))
                
                if not anime_items:
                    # Fallback: look for any links that might be anime results
                    anime_items = soup.find_all('a', href=re.compile(r'/(anime|watch|detail)/', re.I))
                
                logger.log(f'[ANIWATCHTV] Found {len(anime_items)} potential anime items', log_utils.LOGDEBUG)
                
                for item in anime_items[:10]:  # Limit to first 10 results
                    try:
                        # Extract title
                        title_elem = item.find(['h3', 'h4', 'h5', 'a'], class_=re.compile(r'title', re.I))
                        if not title_elem:
                            title_elem = item.find('a')
                        
                        if not title_elem:
                            continue
                            
                        result_title = title_elem.get_text(strip=True)
                        
                        # Extract URL
                        link_elem = item if item.name == 'a' else item.find('a')
                        if not link_elem:
                            continue
                            
                        result_url = link_elem.get('href')
                        if not result_url:
                            continue
                            
                        if result_url.startswith('/'):
                            result_url = result_url
                        elif not result_url.startswith('http'):
                            result_url = '/' + result_url
                        
                        # Extract year if available
                        year_elem = item.find(text=re.compile(r'\b(19|20)\d{2}\b'))
                        result_year = year_elem.strip() if year_elem else year
                        
                        # Check if title matches reasonably well
                        if self._title_matches(title, result_title):
                            result = {
                                'title': result_title,
                                'year': result_year,
                                'url': result_url
                            }
                            results.append(result)
                            logger.log(f'[ANIWATCHTV] Added search result: {result}', log_utils.LOGDEBUG)
                        
                    except Exception as e:
                        logger.log(f'[ANIWATCHTV] Error processing search result: {e}', log_utils.LOGDEBUG)
                        continue
                        
        except Exception as e:
            logger.log(f'[ANIWATCHTV] Search error: {e}', log_utils.LOGERROR)
            
        logger.log(f'[ANIWATCHTV] Search completed, found {len(results)} results', log_utils.LOGDEBUG)
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

    def get_url(self, video):
        """
        Generate URL for the video based on its type
        """
        if video.video_type == VIDEO_TYPES.EPISODE:
            return self._episode_url(video)
        elif video.video_type == VIDEO_TYPES.TVSHOW:
            return self._tvshow_url(video)
        return None

    def _tvshow_url(self, video):
        """
        Generate TV show URL for anime
        """
        clean_title = self._clean_title_for_url(video.title)
        return f'/anime/{clean_title}'

    def _episode_url(self, video):
        """
        Generate episode URL for anime
        """
        clean_title = self._clean_title_for_url(video.title)
        
        # For anime, episodes are usually numbered sequentially
        # Some sites use season-episode format, others use absolute episode numbers
        
        # Try season-episode format first
        if hasattr(video, 'season') and hasattr(video, 'episode'):
            # Format: /watch/anime-title-episode-X or /anime/title/episode-X
            episode_num = int(video.episode)
            
            # Some anime sites use absolute episode numbering
            if hasattr(video, 'season') and int(video.season) > 1:
                # Estimate absolute episode number (rough calculation)
                episode_num = (int(video.season) - 1) * 12 + int(video.episode)
            
            url = f'/watch/{clean_title}-episode-{episode_num}'
            logger.log(f'[ANIWATCHTV] Generated episode URL: {video.title} S{video.season}E{video.episode} -> {url}', log_utils.LOGDEBUG)
            return url
        
        # Fallback to show URL
        return self._tvshow_url(video)

    def resolve_link(self, link):
        """
        Resolve the final streaming link if needed
        """
        try:
            # If it's an AJAX endpoint, get the actual streaming URL
            if '/ajax/' in link and 'sources' in link:
                html = self._http_get(link, cache_limit=0.25)
                if html:
                    try:
                        data = json.loads(html)
                        if 'link' in data:
                            return data['link']
                        elif 'url' in data:
                            return data['url']
                    except json.JSONDecodeError:
                        pass
            
            return link
            
        except Exception as e:
            logger.log(f'[ANIWATCHTV] Error resolving link: {e}', log_utils.LOGERROR)
            return link