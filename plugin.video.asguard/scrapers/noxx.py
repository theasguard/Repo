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
import time
import json
from bs4 import BeautifulSoup
from asguard_lib import scraper_utils
from asguard_lib.constants import VIDEO_TYPES, QUALITIES
from . import scraper
import log_utils
import kodi

logger = log_utils.Logger.get_logger()
BASE_URL = 'https://noxx.to'

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url') or BASE_URL
        self.ddos_guard_cookies = {}

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Noxx'

    def _http_get_with_ddos_guard(self, url, **kwargs):
        """
        Enhanced HTTP get with DDoS-Guard bypass
        """
        logger.log(f'Attempting to access: {url}', log_utils.LOGDEBUG)
        
        # First attempt - might get DDoS-Guard challenge
        html = self._http_get(url, **kwargs)
        
        # Check if we got DDoS-Guard challenge
        if self._is_ddos_guard_challenge(html):
            logger.log('DDoS-Guard challenge detected, attempting bypass', log_utils.LOGDEBUG)
            
            # Try FlareSolverr first (works with DDoS-Guard too)
            if hasattr(self, 'do_flaresolver'):
                flare_result = self.do_flaresolver(url)
                if flare_result and flare_result.get('response'):
                    logger.log('FlareSolverr bypass successful', log_utils.LOGDEBUG)
                    return flare_result['response']
            
            # Fallback to manual DDoS-Guard bypass
            bypassed_html = self._bypass_ddos_guard(url, html)
            if bypassed_html:
                return bypassed_html
                
        return html

    def _is_ddos_guard_challenge(self, html):
        """
        Check if response contains DDoS-Guard challenge
        """
        if not html:
            return False
            
        ddos_guard_indicators = [
            'ddos-guard',
            'DDoS-Guard',
            '__ddg8_',
            'check.ddos-guard.net',
            'js-challenge'
        ]
        
        return any(indicator in html for indicator in ddos_guard_indicators)

    def _bypass_ddos_guard(self, url, challenge_html):
        """
        Attempt to bypass DDoS-Guard protection
        """
        try:
            # Extract challenge information
            soup = BeautifulSoup(challenge_html, 'html.parser')
            
            # Look for challenge script or form
            challenge_script = soup.find('script', src=re.compile(r'check\.ddos-guard\.net'))
            if challenge_script:
                logger.log('Found DDoS-Guard challenge script', log_utils.LOGDEBUG)
                
                # Wait a bit (DDoS-Guard usually has a delay)
                time.sleep(3)
                
                # Make a second request with proper headers and cookies
                headers = {
                    'User-Agent': scraper_utils.get_ua(),
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                    'Accept-Language': 'en-US,en;q=0.5',
                    'Accept-Encoding': 'gzip, deflate',
                    'Referer': url,
                    'Connection': 'keep-alive',
                    'Upgrade-Insecure-Requests': '1'
                }
                
                # Try the request again with the challenge cookies
                second_attempt = self._http_get(url, headers=headers, cache_limit=0)
                
                if second_attempt and not self._is_ddos_guard_challenge(second_attempt):
                    logger.log('DDoS-Guard bypass successful on second attempt', log_utils.LOGDEBUG)
                    return second_attempt
                    
                # Third attempt after longer delay
                time.sleep(5)
                third_attempt = self._http_get(url, headers=headers, cache_limit=0)
                
                if third_attempt and not self._is_ddos_guard_challenge(third_attempt):
                    logger.log('DDoS-Guard bypass successful on third attempt', log_utils.LOGDEBUG)
                    return third_attempt
                    
        except Exception as e:
            logger.log(f'DDoS-Guard bypass error: {e}', log_utils.LOGWARNING)
        
        return None

    def get_sources(self, video):
        sources = []
        source_url = self.get_url(video)
        if not source_url or source_url == scraper_utils.FORCE_NO_MATCH:
            return sources

        url = scraper_utils.urljoin(self.base_url, source_url)
        
        # Use enhanced HTTP get with DDoS-Guard handling
        html = self._http_get_with_ddos_guard(url, cache_limit=1, require_debrid=True)
        logger.log(f'Got HTML length: {len(html) if html else 0}', log_utils.LOGDEBUG)
        
        if not html:
            logger.log('No HTML received, possibly blocked by DDoS-Guard', log_utils.LOGWARNING)
            return sources

        if self._is_ddos_guard_challenge(html):
            logger.log('Still getting DDoS-Guard challenge after bypass attempts', log_utils.LOGWARNING)
            return sources

        soup = BeautifulSoup(html, 'html.parser')
        
        # Look for various link patterns that Noxx might use
        links = []
        
        # Original iframe pattern
        links.extend(soup.find_all('iframe', src=True))
        
        # Button pattern  
        links.extend(soup.find_all('button', value=True))
        
        # Additional patterns for embedded content
        links.extend(soup.find_all('a', href=re.compile(r'(embed|stream|play)', re.I)))
        links.extend(soup.find_all('div', {'data-src': True}))
        
        logger.log(f'Found {len(links)} potential source links', log_utils.LOGDEBUG)

        for link in links:
            stream_url = None
            
            if hasattr(link, 'get') and link.get('src'):
                stream_url = link['src']
            elif hasattr(link, 'get') and link.get('value'):
                stream_url = link['value']
            elif hasattr(link, 'get') and link.get('href'):
                stream_url = link['href']
            elif hasattr(link, 'get') and link.get('data-src'):
                stream_url = link['data-src']
                
            if not stream_url:
                continue
                
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
            sources.append({
                'class': self,                
                'quality': quality,
                'url': stream_url,
                'host': host,
                'multi-part': False,
                'rating': None,
                'views': None,
                'direct': False,
            })
            logger.log('Found source: %s' % sources[-1], log_utils.LOGDEBUG)

        return sources
    
    def search(self, video_type, title, year, season=''):
        """
        Basic search implementation with DDoS-Guard handling
        """
        results = []
        try:
            if video_type == VIDEO_TYPES.MOVIE:
                search_url = f'/search?q={urllib.parse.quote_plus(title)}'
            else:
                search_url = f'/search?q={urllib.parse.quote_plus(title)}'
            
            url = scraper_utils.urljoin(self.base_url, search_url)
            html = self._http_get_with_ddos_guard(url, cache_limit=1)
            
            if html and not self._is_ddos_guard_challenge(html):
                # Parse search results based on Noxx.to's HTML structure
                soup = BeautifulSoup(html, 'html.parser')
                
                # Look for search result links - you may need to adjust these selectors
                result_links = soup.find_all('a', href=re.compile(r'/(movie|tv)/', re.I))
                
                for link in result_links:
                    try:
                        result_title = link.get_text(strip=True)
                        result_url = link.get('href')
                        
                        if result_url and result_title:
                            if not result_url.startswith('http'):
                                result_url = scraper_utils.urljoin(self.base_url, result_url)
                            
                            # Extract year from title if present
                            year_match = re.search(r'\((\d{4})\)', result_title)
                            result_year = year_match.group(1) if year_match else year
                            
                            results.append({
                                'title': result_title,
                                'year': result_year,
                                'url': result_url
                            })
                            
                    except Exception as e:
                        logger.log(f'Error parsing search result: {e}', log_utils.LOGDEBUG)
                        continue
                        
        except Exception as e:
            logger.log(f'Search error: {e}', log_utils.LOGWARNING)
            
        return results

    def get_url(self, video):
        if video.video_type == VIDEO_TYPES.MOVIE:
            return self._movie_url(video)
        elif video.video_type == VIDEO_TYPES.TVSHOW:
            return self._tvshow_url(video)
        elif video.video_type == VIDEO_TYPES.EPISODE:
            return self._episode_url(video)
        return None

    def _movie_url(self, video):
        return '/movie/%s' % (urllib.parse.quote_plus(video.title))

    def _tvshow_url(self, video):
        return '/tv/%s' % (urllib.parse.quote_plus(video.title))

    def _episode_url(self, video):
        return '/tv/%s/%s/%s' % (urllib.parse.quote_plus(video.title), video.season, video.episode)