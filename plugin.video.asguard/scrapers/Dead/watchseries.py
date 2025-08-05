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
from bs4 import BeautifulSoup
from asguard_lib import scraper_utils
from asguard_lib.constants import VIDEO_TYPES, QUALITIES
from . import scraper
import log_utils
import kodi

logger = log_utils.Logger.get_logger()

class Scraper(scraper.Scraper):
    base_url = 'https://watchserieshd.stream'
    search_url = '/?s=%s'
    
    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url') or self.base_url

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'WatchSeries'

    def resolve_link(self, link):
        return link

    def get_sources(self, video):
        sources = []
        
        try:
            # Use centralized IMDB ID retrieval from base class
            imdb_id = self.get_imdb_id(video)
            if not imdb_id:
                logger.log('WatchSeries: No IMDB ID found for trakt_id: %s' % video.trakt_id, log_utils.LOGWARNING)
                # Fall back to search if no IMDB ID
                return self._search_and_get_sources(video)

            # Try to find the content page using search
            content_url = self._find_content_url(video)
            if not content_url:
                logger.log('WatchSeries: Could not find content URL for: %s' % video.title, log_utils.LOGWARNING)
                return sources

            # Get the final episode/movie URL
            if video.video_type == VIDEO_TYPES.EPISODE:
                final_url = self._get_episode_url(content_url, video.season, video.episode)
            else:
                final_url = content_url

            if not final_url:
                logger.log('WatchSeries: Could not get final URL', log_utils.LOGWARNING)
                return sources

            # Extract sources from the content page
            sources = self._extract_sources(final_url, video)

        except Exception as e:
            logger.log('WatchSeries: Unexpected error in get_sources: %s' % str(e), log_utils.LOGERROR)

        logger.log('WatchSeries: Returning %d sources' % len(sources), log_utils.LOGDEBUG)
        return sources

    def _search_and_get_sources(self, video):
        """Fallback method when IMDB ID is not available"""
        sources = []
        
        try:
            search_results = self.search(video.video_type, video.title, video.year)
            if not search_results:
                return sources

            # Use the first matching result
            best_match = search_results[0]
            content_url = best_match.get('url')
            
            if content_url:
                if video.video_type == VIDEO_TYPES.EPISODE:
                    final_url = self._get_episode_url(content_url, video.season, video.episode)
                else:
                    final_url = content_url

                if final_url:
                    sources = self._extract_sources(final_url, video)

        except Exception as e:
            logger.log('WatchSeries: Error in search fallback: %s' % str(e), log_utils.LOGWARNING)

        return sources

    def _find_content_url(self, video):
        """Find the main content page URL by searching"""
        try:
            search_query = urllib.parse.quote_plus(video.title)
            search_url = scraper_utils.urljoin(self.base_url, self.search_url % search_query)
            
            logger.log('WatchSeries: Searching: %s' % search_url, log_utils.LOGDEBUG)
            
            html = self._http_get(search_url, cache_limit=8)
            if not html:
                return None

            soup = BeautifulSoup(html, 'html.parser')
            
            # Look for search result items
            result_items = soup.find_all('div', class_='item')
            
            for item in result_items:
                try:
                    link_elem = item.find('a', href=True)
                    title_elem = item.find('a', title=True)
                    
                    if not link_elem or not title_elem:
                        continue

                    result_url = link_elem['href']
                    result_title = title_elem.get('title', '')
                    
                    # Extract year from title if present
                    year_match = re.search(r'\((\d{4})\)', result_title)
                    result_year = year_match.group(1) if year_match else None
                    
                    # Clean title for comparison
                    clean_result_title = re.sub(r'\s*\(\d{4}\).*', '', result_title).strip()
                    
                    # Check if this matches our search
                    if self._title_match(video.title, clean_result_title) and \
                       self._year_match(video.year, result_year):
                        logger.log('WatchSeries: Found match: %s (%s)' % (clean_result_title, result_year), log_utils.LOGDEBUG)
                        return result_url

                except Exception as e:
                    logger.log('WatchSeries: Error processing search result: %s' % str(e), log_utils.LOGDEBUG)
                    continue

        except Exception as e:
            logger.log('WatchSeries: Error in content search: %s' % str(e), log_utils.LOGWARNING)

        return None

    def _get_episode_url(self, show_url, season, episode):
        """Get the specific episode URL from the show page"""
        try:
            html = self._http_get(show_url, cache_limit=8)
            if not html:
                return None

            soup = BeautifulSoup(html, 'html.parser')
            
            # Look for episode links - common pattern is season-X-episode-Y
            episode_pattern = r'season-%s-episode-%s' % (season, episode)
            
            # Find all links and look for the episode pattern
            links = soup.find_all('a', href=True)
            for link in links:
                href = link['href']
                if re.search(episode_pattern, href, re.I):
                    logger.log('WatchSeries: Found episode URL: %s' % href, log_utils.LOGDEBUG)
                    return href

        except Exception as e:
            logger.log('WatchSeries: Error getting episode URL: %s' % str(e), log_utils.LOGWARNING)

        return None

    def _extract_sources(self, page_url, video):
        """Extract streaming sources from the content page"""
        sources = []
        
        try:
            html = self._http_get(page_url, cache_limit=1)
            if not html:
                return sources

            soup = BeautifulSoup(html, 'html.parser')
            
            # Extract quality info if available
            quality_elem = soup.find('span', class_='quality')
            base_quality = self._extract_quality_from_text(quality_elem.get_text() if quality_elem else '')
            
            # Look for streaming links in data-vs attributes
            # For TV shows
            tv_links = soup.find_all('li', {'data-vs': True})
            # For movies  
            movie_links = soup.find_all('div', {'data-vs': True})
            
            all_links = tv_links + movie_links
            
            logger.log('WatchSeries: Found %d potential source links' % len(all_links), log_utils.LOGDEBUG)

            for link_elem in all_links:
                try:
                    data_vs = link_elem.get('data-vs')
                    if not data_vs:
                        continue

                    # Resolve the data-vs URL to get the actual streaming link
                    resolved_url = self._resolve_data_vs(data_vs)
                    if not resolved_url:
                        continue

                    # Extract host from the resolved URL
                    parsed_url = urllib.parse.urlparse(resolved_url)
                    host = parsed_url.hostname
                    
                    if not host:
                        continue

                    # Skip if this is just a redirect or placeholder
                    if any(skip in host.lower() for skip in ['redirect', 'goto', 'link']):
                        continue

                    # Determine quality
                    quality = base_quality if base_quality != QUALITIES.HIGH else self._extract_quality_from_url(resolved_url)
                    
                    # Check if this is a direct stream
                    direct = self._is_direct_stream(resolved_url)

                    source = {
                        'class': self,
                        'host': host,
                        'label': '%s [%s]' % (host, self._quality_to_text(quality)),
                        'multi-part': False,
                        'quality': quality,
                        'url': resolved_url,
                        'direct': direct,
                        'debridonly': False
                    }

                    sources.append(source)
                    logger.log('WatchSeries: Found source: %s from %s' % (host, resolved_url), log_utils.LOGDEBUG)

                except Exception as e:
                    logger.log('WatchSeries: Error processing source link: %s' % str(e), log_utils.LOGDEBUG)
                    continue

        except Exception as e:
            logger.log('WatchSeries: Error extracting sources: %s' % str(e), log_utils.LOGWARNING)

        return sources

    def _resolve_data_vs(self, data_vs_url):
        """Resolve the data-vs URL to get the actual streaming link"""
        try:
            logger.log('WatchSeries: Resolving data-vs URL: %s' % data_vs_url, log_utils.LOGDEBUG)
            
            response = self._http_get(data_vs_url, cache_limit=1, allow_redirect=True)
            if not response:
                logger.log('WatchSeries: No response from data-vs URL', log_utils.LOGDEBUG)
                return None
            
            logger.log('WatchSeries: Got response length: %d' % len(response), log_utils.LOGDEBUG)
            
            # The response might be a direct redirect URL
            if response.strip().startswith('http'):
                logger.log('WatchSeries: Found direct URL in response', log_utils.LOGDEBUG)
                return response.strip()
                
            # If it's HTML, look for various redirect patterns
            if 'http' in response:
                # Look for various redirect patterns
                url_patterns = [
                    # JavaScript redirects
                    r'window\.location\s*=\s*["\']([^"\']+)["\']',
                    r'location\.href\s*=\s*["\']([^"\']+)["\']',
                    r'document\.location\s*=\s*["\']([^"\']+)["\']',
                    r'window\.open\s*\(\s*["\']([^"\']+)["\']',
                    
                    # Meta refresh
                    r'<meta[^>]+http-equiv[^>]*refresh[^>]+content[^>]*url\s*=\s*["\']?([^"\'>\s]+)',
                    r'<meta[^>]+content[^>]*url\s*=\s*["\']?([^"\'>\s]+)[^>]*http-equiv[^>]*refresh',
                    
                    # iframe src
                    r'<iframe[^>]+src\s*=\s*["\']([^"\']+)["\']',
                    
                    # Video source
                    r'<video[^>]*>.*?<source[^>]+src\s*=\s*["\']([^"\']+)["\']',
                    r'<source[^>]+src\s*=\s*["\']([^"\']+)["\'][^>]*type=["\']video/',
                    
                    # Common streaming patterns
                    r'(?:file|src|url)\s*:\s*["\']([^"\']+\.(?:mp4|m3u8|mkv|avi))["\']',
                    r'["\']([^"\']*(?:\.mp4|\.m3u8|\.mkv|\.avi)[^"\']*)["\']',
                    
                    # Generic URL extraction (be more specific for vidcdn)
                    r'(?:https?://[^"\'\s<>]+\.(?:mp4|m3u8|mkv|avi))',
                ]
                
                for pattern in url_patterns:
                    matches = re.findall(pattern, response, re.I | re.S)
                    for match in matches:
                        # Clean up the URL
                        clean_url = match.strip()
                        if clean_url.startswith('http') and any(ext in clean_url.lower() for ext in ['.mp4', '.m3u8', '.mkv', '.avi', 'stream', 'video']):
                            logger.log('WatchSeries: Found streaming URL: %s' % clean_url, log_utils.LOGDEBUG)
                            return clean_url
                
                # If no direct video URL found, look for any HTTP URL that might be a streaming service
                http_urls = re.findall(r'https?://[^\s"\'<>]+', response)
                for url in http_urls:
                    # Skip obvious non-streaming URLs
                    skip_domains = ['google', 'facebook', 'twitter', 'analytics', 'ads', 'cdn.', 'static.']
                    if not any(skip in url.lower() for skip in skip_domains):
                        # Check if it looks like a streaming URL
                        if any(indicator in url.lower() for indicator in ['stream', 'video', 'play', 'embed', 'player']):
                            logger.log('WatchSeries: Found potential streaming URL: %s' % url, log_utils.LOGDEBUG)
                            return url
            
            logger.log('WatchSeries: No streaming URL found in response', log_utils.LOGDEBUG)

        except Exception as e:
            logger.log('WatchSeries: Error resolving data-vs URL: %s' % str(e), log_utils.LOGWARNING)

        return None

    def _extract_quality_from_text(self, text):
        """Extract quality from text description"""
        if not text:
            return QUALITIES.HIGH
            
        text_lower = text.lower()
        
        if any(q in text_lower for q in ['4k', '2160p', 'uhd']):
            return QUALITIES.HD4K
        elif any(q in text_lower for q in ['1080p', 'fhd']):
            return QUALITIES.HD1080
        elif any(q in text_lower for q in ['720p', 'hd']):
            return QUALITIES.HD720
        elif any(q in text_lower for q in ['480p']):
            return QUALITIES.HIGH
        elif any(q in text_lower for q in ['360p']):
            return QUALITIES.MEDIUM
        else:
            return QUALITIES.HIGH

    def _extract_quality_from_url(self, url):
        """Extract quality from URL patterns"""
        return self._extract_quality_from_text(url)

    def _quality_to_text(self, quality):
        """Convert quality constant to text"""
        quality_map = {
            QUALITIES.HD4K: '4K',
            QUALITIES.HD1080: '1080p',
            QUALITIES.HD720: '720p',
            QUALITIES.HIGH: 'SD',
            QUALITIES.MEDIUM: '360p'
        }
        return quality_map.get(quality, 'SD')

    def _is_direct_stream(self, url):
        """Check if URL is a direct stream"""
        direct_indicators = ['.mp4', '.mkv', '.avi', '.m3u8', '.ts']
        return any(indicator in url.lower() for indicator in direct_indicators)

    def _title_match(self, title1, title2):
        """Check if two titles match"""
        clean1 = scraper_utils.cleanse_title(title1).lower()
        clean2 = scraper_utils.cleanse_title(title2).lower()
        return clean1 == clean2

    def _year_match(self, year1, year2):
        """Check if years match (with some tolerance)"""
        if not year1 or not year2:
            return True
        try:
            y1, y2 = int(year1), int(year2)
            return abs(y1 - y2) <= 1
        except (ValueError, TypeError):
            return True

    def search(self, video_type, title, year, season=''):
        """Search for content on WatchSeries"""
        results = []
        
        try:
            search_query = urllib.parse.quote_plus(title)
            search_url = scraper_utils.urljoin(self.base_url, self.search_url % search_query)
            
            logger.log('WatchSeries: Searching: %s' % search_url, log_utils.LOGDEBUG)
            
            html = self._http_get(search_url, cache_limit=8)
            if not html:
                return results

            soup = BeautifulSoup(html, 'html.parser')
            
            # Parse search results
            result_items = soup.find_all('div', class_='item')
            
            for item in result_items:
                try:
                    link_elem = item.find('a', href=True)
                    title_elem = item.find('a', title=True)
                    
                    if not link_elem or not title_elem:
                        continue

                    result_url = link_elem['href']
                    result_title = title_elem.get('title', '')
                    
                    # Extract year from title
                    year_match = re.search(r'\((\d{4})\)', result_title)
                    result_year = year_match.group(1) if year_match else year
                    
                    # Clean title
                    clean_title = re.sub(r'\s*\(\d{4}\).*', '', result_title).strip()
                    
                    results.append({
                        'title': clean_title,
                        'year': result_year,
                        'url': result_url
                    })

                except Exception as e:
                    logger.log('WatchSeries: Error parsing search result: %s' % str(e), log_utils.LOGDEBUG)
                    continue

        except Exception as e:
            logger.log('WatchSeries: Search error: %s' % str(e), log_utils.LOGWARNING)

        logger.log('WatchSeries: Found %d search results' % len(results), log_utils.LOGDEBUG)
        return results
