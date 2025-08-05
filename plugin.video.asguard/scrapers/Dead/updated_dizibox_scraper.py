"""
Updated Dizibox scraper for Asguard Kodi addon
Based on analysis of current site structure (dizibox.so)
Copyright (C) 2025 MrBlamo

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.
"""
import re
import urllib.parse
import gzip
import ssl
import urllib.request
import urllib.error
from io import BytesIO

import dom_parser
import kodi
import log_utils
from asguard_lib import scraper_utils
from asguard_lib.constants import FORCE_NO_MATCH
from asguard_lib.constants import VIDEO_TYPES
from . import scraper

logger = log_utils.Logger.get_logger()

BASE_URL = 'https://www.dizibox.so'

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting('%s-base_url' % (self.get_name()))

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Dizibox'

    def resolve_link(self, link):
        return link

    def format_source_label(self, item):
        label = '[%s] %s' % (item['quality'], item['host'])
        return label

    def _http_get(self, url, params=None, data=None, multipart_data=None, headers=None, cookies=None, 
                  allow_redirect=True, method=None, require_debrid=False, read_error=False, cache_limit=8):
        """
        Enhanced HTTP get with SSL context handling for Dizibox
        """
        logger.log('Dizibox HTTP GET: %s' % url, log_utils.LOGDEBUG)
        
        # First try the parent method
        html = super()._http_get(url, params, data, multipart_data, headers, cookies, 
                               allow_redirect, method, require_debrid, read_error, cache_limit)
        
        # If parent method failed and this is a dizibox.so URL, try with SSL bypass
        if not html and 'dizibox.so' in url:
            logger.log('Parent HTTP method failed, trying SSL bypass', log_utils.LOGDEBUG)
            html = self._http_get_ssl_bypass(url, headers, cookies)
        
        return html
    
    def _http_get_ssl_bypass(self, url, headers=None, cookies=None):
        """
        HTTP get with SSL certificate bypass for Dizibox site issues
        """
        
        try:
            logger.log('Attempting SSL bypass for: %s' % url, log_utils.LOGDEBUG)
            
            # Create SSL context that bypasses certificate verification
            ssl_context = ssl.create_default_context()
            ssl_context.check_hostname = False
            ssl_context.verify_mode = ssl.CERT_NONE
            
            # Prepare headers with proper user agent
            if headers is None:
                headers = {}
            
            request_headers = {
                'User-Agent': scraper_utils.get_ua(),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Connection': 'keep-alive',
                'Referer': self.base_url
            }
            request_headers.update(headers)
            
            # Create and send request
            request = urllib.request.Request(url, headers=request_headers)
            
            with urllib.request.urlopen(request, timeout=self.timeout, context=ssl_context) as response:
                raw_content = response.read()
                
                # Handle GZIP compression
                if response.headers.get('Content-Encoding') == 'gzip':
                    try:
                        html = gzip.decompress(raw_content).decode('utf-8', errors='ignore')
                        logger.log('SSL bypass + GZIP decompression successful: %d chars' % len(html), log_utils.LOGDEBUG)
                    except:
                        html = raw_content.decode('utf-8', errors='ignore')
                        logger.log('SSL bypass successful (no GZIP): %d chars' % len(html), log_utils.LOGDEBUG)
                else:
                    html = raw_content.decode('utf-8', errors='ignore')
                    logger.log('SSL bypass successful: %d chars' % len(html), log_utils.LOGDEBUG)
                
                return html
                
        except Exception as e:
            logger.log('SSL bypass failed: %s' % str(e), log_utils.LOGWARNING)
            return ''



    def get_sources(self, video):
        source_url = self.get_url(video)
        hosters = []
        if source_url and source_url != FORCE_NO_MATCH:
            page_url = urllib.parse.urljoin(self.base_url, source_url)
            html = self._http_get(page_url, cache_limit=.25)
            
            if not html:
                logger.log('No HTML content received for: %s' % page_url, log_utils.LOGWARNING)
                return hosters
            
            logger.log('Processing page for sources: %s (length: %d)' % (page_url, len(html)), log_utils.LOGDEBUG)
            
            # Updated pattern for current site - look for Turkish subtitle options
            # Pattern 1: Look for "Altyazısız" or "Türkçe Altyazılı" options
            subtitle_patterns = [
                r'''<option[^>]+value\s*=\s*["']([^"']+)[^>]*>(?:Altyazısız|Türkçe\s*Altyazılı)<''',
                r'''<option[^>]+value\s*=\s*["']([^"']+)[^>]*>\s*(?:TR|Turkish|Türkçe)[^<]*<''',
                r'''<a[^>]+href\s*=\s*["']([^"']+)[^>]*>\s*(?:Altyazısız|Türkçe)[^<]*<'''
            ]
            
            option_url = None
            for pattern in subtitle_patterns:
                match = re.search(pattern, html, re.IGNORECASE)
                if match:
                    option_url = urllib.parse.urljoin(self.base_url, match.group(1))
                    logger.log('Found subtitle option URL: %s' % option_url, log_utils.LOGDEBUG)
                    break
            
            if option_url:
                html = self._http_get(option_url, cache_limit=.25)
                if not html:
                    logger.log('No HTML content from subtitle option URL', log_utils.LOGWARNING)
                    return hosters
            
            # Look for video player containers - updated patterns
            player_containers = [
                {'class': 'object-wrapper'},  # Original pattern
                {'class': 'player-container'},  # Alternative pattern
                {'class': 'video-container'},   # Alternative pattern
                {'id': 'player'},               # Alternative pattern
            ]
            
            iframe_url = None
            for container_attrs in player_containers:
                fragments = dom_parser.parse_dom(html, 'div', container_attrs)
                if not fragments:
                    fragments = dom_parser.parse_dom(html, 'span', container_attrs)
                
                if fragments:
                    iframe_urls = dom_parser.parse_dom(fragments[0], 'iframe', ret='src')
                    if iframe_urls:
                        iframe_url = iframe_urls[0]
                        logger.log('Found iframe URL: %s' % iframe_url, log_utils.LOGDEBUG)
                        break
            
            if iframe_url:
                html = self._http_get(iframe_url, cache_limit=.25)
                if html:
                    logger.log('Processing iframe content (length: %d)' % len(html), log_utils.LOGDEBUG)
                    hosters = self._extract_sources_from_player(html)
            else:
                logger.log('No iframe found, trying direct source extraction', log_utils.LOGDEBUG)
                hosters = self._extract_sources_from_player(html)
    
        logger.log('Total sources found: %d' % len(hosters), log_utils.LOGDEBUG)
        return hosters

    def _extract_sources_from_player(self, html):
        """Extract video sources from player HTML"""
        hosters = []
        seen_urls = {}
        
        # Enhanced patterns for various player implementations
        source_patterns = [
            # Original pattern
            r'"?file"?\s*:\s*"([^"]+)"\s*,\s*"?label"?\s*:\s*"(\d+)p?[^"]*"',
            # Alternative patterns for different players
            r'"?src"?\s*:\s*"([^"]+)"\s*,\s*"?quality"?\s*:\s*"(\d+)p?"',
            r'"?url"?\s*:\s*"([^"]+)"\s*,\s*"?height"?\s*:\s*"?(\d+)"?',
            r'"?source"?\s*:\s*"([^"]+)"\s*,\s*"?res"?\s*:\s*"(\d+)p?"',
            # M3U8 playlist patterns
            r'"?file"?\s*:\s*"([^"]+\.m3u8[^"]*)"',
            # Direct video file patterns
            r'"?file"?\s*:\s*"([^"]+\.(?:mp4|avi|mkv|webm)[^"]*)"',
        ]
        
        for pattern in source_patterns:
            matches = re.finditer(pattern, html, re.IGNORECASE)
            for match in matches:
                if len(match.groups()) >= 2:
                    stream_url, height = match.groups()[:2]
                elif len(match.groups()) == 1:
                    stream_url = match.group(1)
                    height = '720'  # Default quality
                else:
                    continue
                
                if stream_url and stream_url not in seen_urls:
                    seen_urls[stream_url] = True
                    
                    # Clean up URL
                    stream_url = stream_url.replace('\\/', '/')
                    
                    # Add user agent for direct streams
                    if not stream_url.startswith('http'):
                        continue
                        
                    stream_url += '|User-Agent=%s' % (scraper_utils.get_ua())
                    
                    # Determine quality and host
                    host = self._get_direct_hostname(stream_url)
                    if host == 'gvideo':
                        quality = scraper_utils.gv_get_quality(stream_url)
                    else:
                        quality = scraper_utils.height_get_quality(height)
                    
                    hoster = {
                        'class': self,
                        'multi-part': False, 
                        'host': host, 
                        'quality': quality, 
                        'views': None, 
                        'rating': None, 
                        'url': stream_url, 
                        'direct': True
                    }
                    hosters.append(hoster)
                    logger.log('Added source: %s [%s]' % (host, quality), log_utils.LOGDEBUG)
        
        return hosters

    def get_url(self, video):
        return self._default_get_url(video)

    def _get_episode_url(self, show_url, video):
        show_url = urllib.parse.urljoin(self.base_url, show_url)
        html = self._http_get(show_url, cache_limit=24)
        
        if not html:
            logger.log('No HTML content for show URL: %s' % show_url, log_utils.LOGWARNING)
            return None
        
        # Updated patterns for current site structure
        season_patterns = [
            # Original pattern
            r'''href=['"]([^'"]+)[^>]+>\s*%s\.\s*Sezon<''' % video.season,
            # Alternative patterns
            r'''href=['"]([^'"]+sezon-%s[^'"]*)[^>]*>\s*(?:Season\s*%s|%s\.\s*Sezon)''' % (video.season, video.season, video.season),
            r'''href=['"]([^'"]+)[^>]*>\s*(?:S%02d|Season\s*%s)''' % (int(video.season), video.season),
        ]
        
        season_url = None
        for pattern in season_patterns:
            match = re.search(pattern, html, re.IGNORECASE)
            if match:
                season_url = urllib.parse.urljoin(self.base_url, match.group(1))
                logger.log('Found season URL: %s' % season_url, log_utils.LOGDEBUG)
                break
        
        if season_url:
            # Get the season page HTML
            season_html = self._http_get(season_url, cache_limit=24)
            if not season_html:
                return None
                
            # Enhanced episode pattern with Turkish support - try each pattern
            episode_patterns = [
                # Original pattern
                r'''href=['"]([^'"]+-%s-sezon-%s-[^\;"]*bolum[^'"]*)''' % (video.season, video.episode),
                # Alternative patterns
                r'''href=['"]([^'"]+)[^>]*>\s*(?:%s\.\s*Bölüm|Episode\s*%s|E%02d)''' % (video.episode, video.episode, int(video.episode)),
                r'''href=['"]([^'"]+sezon-%s[^'"]*bolum-%s[^'"]*)[^>]*''' % (video.season, video.episode),
                r'''href=['"]([^'"]+)[^>]*>\s*S%02dE%02d''' % (int(video.season), int(video.episode)),
            ]
            
            # Try each pattern until we find a match
            for episode_pattern in episode_patterns:
                result = self._default_get_episode_url(season_html, video, episode_pattern)
                if result:
                    return result
        
        return None

    def search(self, video_type, title, year, season=''):
        html = self._http_get(self.base_url, cache_limit=8)
        results = []
        seen_urls = {}
        
        if not html:
            logger.log('No HTML content received from base URL', log_utils.LOGWARNING)
            return results
        
        norm_title = scraper_utils.normalize_title(title)
        logger.log('Searching for: "%s" (normalized: "%s")' % (title, norm_title), log_utils.LOGDEBUG)
        
        # Updated search patterns for current site structure
        search_containers = [
            # New alphabetical category lists
            {'class': 'alphabetical-category-list'},
            # Original category lists (fallback)
            {'class': 'category-list'},
            # Alternative containers
            {'class': 'series-list'},
            {'class': 'show-list'},
        ]
        
        all_links = []
        for container_attrs in search_containers:
            fragments = dom_parser.parse_dom(html, 'ul', container_attrs)
            if fragments:
                logger.log('Found %d containers with %s' % (len(fragments), container_attrs), log_utils.LOGDEBUG)
                for fragment in fragments:
                    # Extract all links from this fragment (fragment is a DomMatch object)
                    fragment_content = fragment.content if hasattr(fragment, 'content') else str(fragment)
                    links = re.finditer(r'''href=["']([^'"]+)[^>]+>([^<]+)''', fragment_content)
                    for match in links:
                        url, match_title = match.groups()
                        all_links.append((url.strip(), match_title.strip()))
        
        # If no structured containers found, try global link search
        if not all_links:
            logger.log('No structured containers found, trying global search', log_utils.LOGDEBUG)
            global_links = re.finditer(r'''<a[^>]+href=["']([^'"]+diziler/[^'"]+)["'][^>]*>([^<]+)</a>''', html, re.IGNORECASE)
            all_links = [(match.group(1).strip(), match.group(2).strip()) for match in global_links]
        
        logger.log('Found %d total links to process' % len(all_links), log_utils.LOGDEBUG)
        
        for url, match_title in all_links:
            if url not in seen_urls and url.strip() and match_title.strip():
                seen_urls[url] = True
                
                # Clean up title (remove icons and extra text)
                clean_title = re.sub(r'^\s*\w+\s+', '', match_title)  # Remove icon text
                clean_title = clean_title.strip()
                
                # Normalize for comparison
                norm_match_title = scraper_utils.normalize_title(clean_title)
                
                # Enhanced matching logic
                title_match = (
                    norm_title in norm_match_title or 
                    norm_match_title in norm_title or
                    self._fuzzy_title_match(norm_title, norm_match_title)
                )
                
                if title_match:
                    # Extract year from URL or title if available
                    year_match = re.search(r'(\d{4})', url + ' ' + clean_title)
                    found_year = year_match.group(1) if year_match else ''
                    
                    result = {
                        'url': scraper_utils.pathify_url(url), 
                        'title': clean_title, 
                        'year': found_year
                    }
                    results.append(result)
                    logger.log('Match found: "%s" -> %s' % (clean_title, url), log_utils.LOGDEBUG)
        
        logger.log('Search completed. Found %d results for "%s"' % (len(results), title), log_utils.LOGDEBUG)
        return results

    def _fuzzy_title_match(self, title1, title2):
        """Simple fuzzy matching for titles"""
        if not title1 or not title2:
            return False
        
        # Remove common words and characters
        common_words = ['the', 'a', 'an', 'and', 'or', 'of', 'in', 'on', 'at', 'to', 'for', 'with']
        
        def clean_for_fuzzy(text):
            text = re.sub(r'[^\w\s]', '', text.lower())
            words = text.split()
            return ' '.join([w for w in words if w not in common_words and len(w) > 2])
        
        clean1 = clean_for_fuzzy(title1)
        clean2 = clean_for_fuzzy(title2)
        
        # Simple word overlap check
        words1 = set(clean1.split())
        words2 = set(clean2.split())
        
        if not words1 or not words2:
            return False
        
        overlap = len(words1.intersection(words2))
        min_words = min(len(words1), len(words2))
        
        # Consider it a match if more than 50% of words overlap
        return overlap / min_words > 0.5