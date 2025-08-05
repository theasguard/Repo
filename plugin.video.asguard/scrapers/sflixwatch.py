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
import json
from bs4 import BeautifulSoup
from asguard_lib import scraper_utils
from asguard_lib.constants import VIDEO_TYPES, QUALITIES
from . import scraper
import log_utils
import kodi

logger = log_utils.Logger.get_logger()
BASE_URL = 'https://sflixz.watch'

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url') or BASE_URL
        self.domains = ['sflixz.watch']
        # Custom hoster domains from scrubs version
        self.custom_hoster_domains = ['//cdnvid.art/', '//videofast.art/']

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'SFlixWatch'

    def get_sources(self, video):
        logger.log(f'[SFLIXWATCH] Starting get_sources for video: {video.title}', log_utils.LOGDEBUG)
        sources = []
        source_url = self.get_url(video)
        
        if not source_url or source_url == scraper_utils.FORCE_NO_MATCH:
            logger.log(f'[SFLIXWATCH] No source URL found for video: {source_url}', log_utils.LOGWARNING)
            return sources

        url = scraper_utils.urljoin(self.base_url, source_url)
        logger.log(f'[SFLIXWATCH] Fetching URL: {url}', log_utils.LOGDEBUG)
        
        html = self._http_get(url, cache_limit=1, require_debrid=False)
        logger.log(f'[SFLIXWATCH] Got HTML length: {len(html) if html else 0}', log_utils.LOGDEBUG)
        
        if not html:
            logger.log('[SFLIXWATCH] No HTML received from sflixz.watch', log_utils.LOGWARNING)
            return sources

        # Log a snippet of the HTML to see what we're working with
        html_snippet = html[:500] if html else ""
        logger.log(f'[SFLIXWATCH] HTML snippet: {html_snippet}', log_utils.LOGDEBUG)

        # Check if we have the correct page by looking for IMDB link or title
        imdb_id = self.get_imdb_id(video)
        if hasattr(video, 'imdb_id') and imdb_id:
            if f'imdb.com/title/{imdb_id}/' not in html:
                logger.log(f'[SFLIXWATCH] IMDB ID {imdb_id} not found on page, may be wrong content', log_utils.LOGWARNING)
            else:
                logger.log(f'[SFLIXWATCH] IMDB ID {imdb_id} confirmed on page', log_utils.LOGDEBUG)

        # Verify year match for movies
        if video.video_type == VIDEO_TYPES.MOVIE:
            try:
                year_match = re.search(r'/year/(\d{4})/', html)
                if year_match:
                    page_year = year_match.group(1)
                    if not self._year_match(page_year, video.year):
                        logger.log(f'[SFLIXWATCH] Year mismatch: expected {video.year}, found {page_year}', log_utils.LOGWARNING)
                        return sources
                    else:
                        logger.log(f'[SFLIXWATCH] Year confirmed: {page_year}', log_utils.LOGDEBUG)
            except Exception as e:
                logger.log(f'[SFLIXWATCH] Error checking year: {e}', log_utils.LOGDEBUG)

        # Find the player URL pattern from scrubs version
        servers_url_match = re.search(r'const pl_url = \'(.+?)\';', html)
        if not servers_url_match:
            logger.log('[SFLIXWATCH] Could not find pl_url pattern', log_utils.LOGWARNING)
            return sources
            
        servers_url = servers_url_match.group(1)
        logger.log(f'[SFLIXWATCH] Found servers URL: {servers_url}', log_utils.LOGDEBUG)
        
        # Get the servers page
        servers_html = self._http_get(servers_url, cache_limit=1)
        if not servers_html:
            logger.log('[SFLIXWATCH] Failed to get servers HTML', log_utils.LOGWARNING)
            return sources
            
        logger.log(f'[SFLIXWATCH] Got servers HTML length: {len(servers_html)}', log_utils.LOGDEBUG)

        # Parse server URLs using BeautifulSoup
        soup = BeautifulSoup(servers_html, 'html.parser')
        server_divs = soup.find_all('div', {'data-id': True})
        logger.log(f'[SFLIXWATCH] Found {len(server_divs)} server divs', log_utils.LOGDEBUG)
        
        for i, server_div in enumerate(server_divs):
            try:
                server_url = server_div.get('data-id')
                if not server_url:
                    continue
                    
                logger.log(f'[SFLIXWATCH] Processing server {i+1}/{len(server_divs)}: {server_url[:50]}...', log_utils.LOGDEBUG)
                
                # Check if it's a custom hoster domain (needs special handling)
                if any(domain in server_url for domain in self.custom_hoster_domains):
                    logger.log(f'[SFLIXWATCH] Custom hoster domain detected: {server_url}', log_utils.LOGDEBUG)
                    
                    # Get the server page to extract iframe
                    server_html = self._http_get(server_url, cache_limit=1)
                    if server_html:
                        server_soup = BeautifulSoup(server_html, 'html.parser')
                        iframe = server_soup.find('iframe', src=True)
                        if iframe:
                            server_link = iframe['src']
                            logger.log(f'[SFLIXWATCH] Extracted iframe link: {server_link}', log_utils.LOGDEBUG)
                            
                            # Add this as a source
                            host = urllib.parse.urlparse(server_link).hostname
                            if host:
                                quality = self._determine_quality(video, server_link, host)
                                source = {
                                    'class': self,
                                    'quality': quality,
                                    'url': server_link,
                                    'host': host,
                                    'multi-part': False,
                                    'rating': None,
                                    'views': None,
                                    'direct': False,
                                }
                                sources.append(source)
                                logger.log(f'[SFLIXWATCH] Added custom hoster source: {source}', log_utils.LOGDEBUG)
                else:
                    # Regular server URL - add directly
                    host = urllib.parse.urlparse(server_url).hostname
                    if host:
                        quality = self._determine_quality(video, server_url, host)
                        source = {
                            'class': self,
                            'quality': quality,
                            'url': server_url,
                            'host': host,
                            'multi-part': False,
                            'rating': None,
                            'views': None,
                            'direct': False,
                        }
                        sources.append(source)
                        logger.log(f'[SFLIXWATCH] Added regular source: {source}', log_utils.LOGDEBUG)
                        
            except Exception as e:
                logger.log(f'[SFLIXWATCH] Error processing server {i+1}: {e}', log_utils.LOGERROR)
                continue

        logger.log(f'[SFLIXWATCH] Found {len(sources)} total sources', log_utils.LOGINFO)
        return sources

    def _determine_quality(self, video, url, host):
        """
        Determine quality using Asguard's quality system which considers both URL patterns and host capabilities
        """
        try:
            logger.log(f'[SFLIXWATCH] Determining quality for: {url} (host: {host})', log_utils.LOGDEBUG)
            
            # Use Asguard's blog_get_quality which considers both URL content and host quality
            if hasattr(scraper_utils, 'blog_get_quality'):
                quality = scraper_utils.blog_get_quality(video, url, host)
                logger.log(f'[SFLIXWATCH] blog_get_quality returned: {quality}', log_utils.LOGDEBUG)
                return quality
            
            # Fallback: Use Asguard's get_quality with manual URL parsing
            logger.log('[SFLIXWATCH] blog_get_quality not available, using fallback', log_utils.LOGDEBUG)
            
            # Parse URL for quality indicators (like blog_get_quality does)
            url_upper = url.upper()
            # Remove video title and year to clean the URL for quality detection
            if hasattr(video, 'title') and video.title:
                url_upper = url_upper.replace(video.title.upper(), '')
            if hasattr(video, 'year') and video.year:
                url_upper = url_upper.replace(str(video.year), '')
            
            logger.log(f'[SFLIXWATCH] Cleaned URL for quality detection: {url_upper}', log_utils.LOGDEBUG)
            
            # Determine post quality from URL content
            post_quality = None
            
            # Check for 4K indicators
            if any(q in url_upper for q in ['4K']):
                post_quality = QUALITIES.HD4K
                logger.log('[SFLIXWATCH] Found 4K quality indicators', log_utils.LOGDEBUG)
            # Check for 1080p indicators  
            elif any(q in url_upper for q in ['1080']):
                post_quality = QUALITIES.HD1080
                logger.log('[SFLIXWATCH] Found 1080p quality indicators', log_utils.LOGDEBUG)
            # Check for 720p indicators
            elif any(q in url_upper for q in ['720', 'HDTS', ' HD ']):
                post_quality = QUALITIES.HD720
                logger.log('[SFLIXWATCH] Found 720p quality indicators', log_utils.LOGDEBUG)
            # Check for high quality indicators
            elif any(q in url_upper for q in ['HDRIP', 'DVDRIP', 'BRRIP', 'BDRIP', '480P', 'HDTV']):
                post_quality = QUALITIES.HIGH
                logger.log('[SFLIXWATCH] Found HIGH quality indicators', log_utils.LOGDEBUG)
            # Check for medium quality indicators
            elif any(q in url_upper for q in ['-XVID', '-MP4', 'MEDIUM']):
                post_quality = QUALITIES.MEDIUM
                logger.log('[SFLIXWATCH] Found MEDIUM quality indicators', log_utils.LOGDEBUG)
            # Check for low quality indicators
            elif any(q in url_upper for q in [' CAM ', ' TS ', ' R6 ', 'CAMRIP']):
                post_quality = QUALITIES.LOW
                logger.log('[SFLIXWATCH] Found LOW quality indicators', log_utils.LOGDEBUG)
            
            # Use Asguard's get_quality to factor in host quality
            if hasattr(scraper_utils, 'get_quality'):
                final_quality = scraper_utils.get_quality(video, host, post_quality)
                logger.log(f'[SFLIXWATCH] get_quality returned: {final_quality} (post_quality: {post_quality}, host: {host})', log_utils.LOGDEBUG)
                return final_quality
            
            # Ultimate fallback
            logger.log('[SFLIXWATCH] Using ultimate fallback quality determination', log_utils.LOGDEBUG)
            return post_quality if post_quality else QUALITIES.HIGH
                
        except Exception as e:
            logger.log(f'[SFLIXWATCH] Error determining quality: {e}', log_utils.LOGERROR)
            return QUALITIES.HIGH

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
            logger.log(f'[SFLIXWATCH] Match check: title_match={title_match}, year_match={year_match}, overall={match}', log_utils.LOGDEBUG)
            
            return match
            
        except Exception as e:
            logger.log(f'[SFLIXWATCH] Error in _is_match: {e}', log_utils.LOGDEBUG)
            return False

    def _year_match(self, page_year, search_year):
        """Check if years match with some flexibility"""
        try:
            if not search_year or not page_year:
                return True
            page_year_int = int(page_year)
            search_year_int = int(search_year)
            return abs(page_year_int - search_year_int) <= 1  # Allow 1 year difference
        except ValueError:
            return page_year == search_year

    def search(self, video_type, title, year, season=''):
        """
        Search for content on sflixz.watch
        """
        logger.log(f'[SFLIXWATCH] Starting search: type={video_type}, title={title}, year={year}, season={season}', log_utils.LOGDEBUG)
        results = []
        
        try:
            # Build search URL like scrubs version
            search_query = urllib.parse.quote_plus(title)
            search_url = f'/search?keyword={search_query}'
            url = scraper_utils.urljoin(self.base_url, search_url)
            
            logger.log(f'[SFLIXWATCH] Search URL: {url}', log_utils.LOGDEBUG)
            
            html = self._http_get(url, cache_limit=1)
            if not html:
                logger.log('[SFLIXWATCH] No HTML received from search', log_utils.LOGWARNING)
                return results
                
            logger.log(f'[SFLIXWATCH] Search HTML length: {len(html)}', log_utils.LOGDEBUG)
            
            # Parse search results
            soup = BeautifulSoup(html, 'html.parser')
            
            # Look for result containers (based on scrubs parsing)
            result_containers = soup.find_all('div', class_='inner')
            logger.log(f'[SFLIXWATCH] Found {len(result_containers)} result containers', log_utils.LOGDEBUG)
            
            for container in result_containers:
                try:
                    # Extract title link
                    title_link = container.find('a', class_='title')
                    if not title_link:
                        continue
                        
                    result_url = title_link.get('href')
                    result_title = title_link.get_text(strip=True)
                    
                    if not result_url or not result_title:
                        continue
                    
                    # Extract metadata (year, etc.)
                    metadata_div = container.find('div', class_='metadata')
                    result_year = year  # default
                    
                    if metadata_div:
                        # Look for year in metadata
                        year_match = re.search(r'>(\d{4})<', str(metadata_div))
                        if year_match:
                            result_year = year_match.group(1)
                    
                    # Filter by content type
                    if video_type == VIDEO_TYPES.MOVIE and '/movie/' not in result_url:
                        continue
                    elif video_type in [VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE] and '/series/' not in result_url:
                        continue
                    
                    # Check title and year match
                    if self._is_match(result_title, title, result_year, year):
                        result = {
                            'title': result_title,
                            'year': result_year,
                            'url': result_url
                        }
                        results.append(result)
                        logger.log(f'[SFLIXWATCH] Added search result: {result}', log_utils.LOGDEBUG)
                        
                except Exception as e:
                    logger.log(f'[SFLIXWATCH] Error parsing search result: {e}', log_utils.LOGDEBUG)
                    continue
                    
        except Exception as e:
            logger.log(f'[SFLIXWATCH] Search error: {e}', log_utils.LOGERROR)
            
        logger.log(f'[SFLIXWATCH] Search completed, found {len(results)} results', log_utils.LOGDEBUG)
        return results

    def get_url(self, video):
        """
        Generate URL for the video based on its type
        """
        if video.video_type == VIDEO_TYPES.MOVIE:
            return self._movie_url(video)
        elif video.video_type == VIDEO_TYPES.TVSHOW:
            return self._tvshow_url(video)
        elif video.video_type == VIDEO_TYPES.EPISODE:
            return self._episode_url(video)
        return None

    def _movie_url(self, video):
        """
        Generate movie URL - will need to search first to get the exact URL with ID
        """
        search_results = self.search(VIDEO_TYPES.MOVIE, video.title, video.year)
        if search_results:
            return search_results[0]['url']
        return None

    def _tvshow_url(self, video):
        """
        Generate TV show URL
        """
        search_results = self.search(VIDEO_TYPES.TVSHOW, video.title, video.year)
        if search_results:
            return search_results[0]['url']
        return None

    def _episode_url(self, video):
        """
        Generate episode URL
        """
        # First get the show URL
        show_results = self.search(VIDEO_TYPES.TVSHOW, video.title, video.year)
        if show_results:
            show_url = show_results[0]['url']
            # Append season/episode info like scrubs version
            return f"{show_url}/{video.season}-{video.episode}/"
        return None

    def resolve_link(self, link):
        """
        Resolve the final link if needed
        """
        return link