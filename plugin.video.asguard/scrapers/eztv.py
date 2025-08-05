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
import urllib.request
import urllib.error
import json
import kodi
import log_utils
import resolveurl
from asguard_lib.utils2 import i18n
import xbmcgui
from bs4 import BeautifulSoup
from asguard_lib import scraper_utils, control, client
from asguard_lib.constants import FORCE_NO_MATCH, QUALITIES, VIDEO_TYPES
from . import scraper

logger = log_utils.Logger.get_logger()
BASE_URL = 'https://eztvx.to'
SEARCH_URL = '/search/%s'
QUALITY_MAP = {'1080p': QUALITIES.HD1080, '720p': QUALITIES.HD720, '3D': QUALITIES.HD1080}

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url') or BASE_URL
        self.result_limit = kodi.get_setting(f'{self.get_name()}-result_limit')

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'EZTV'

    def resolve_link(self, link):
        return link

    def _build_query(self, video):
        query = video.title
        if video.video_type == VIDEO_TYPES.EPISODE:
            query += f' S{int(video.season):02d}'
        elif video.video_type == VIDEO_TYPES.MOVIE:
            query += f' {video.year}'
        query = query.replace(' ', '+').replace('+-', '-')
        return query

    def get_sources(self, video):
        sources = []
        query = self._build_query(video)
        search_url = scraper_utils.urljoin(self.base_url, SEARCH_URL % query)
        logger.log(f'EZTV Search URL: {search_url}', log_utils.LOGDEBUG)
        
        # Try multiple methods to get the links
        html = self._get_search_html(search_url)
        if not html:
            logger.log('EZTV: No HTML content received', log_utils.LOGWARNING)
            return []
            
        logger.log(f'EZTV Search HTML length: {len(html)}', log_utils.LOGDEBUG)
        
        try:
            soup = BeautifulSoup(html, 'html.parser')
        except Exception as e:
            logger.log(f'EZTV: BeautifulSoup parsing error: {str(e)}', log_utils.LOGERROR)
            return []
        
        # Debug: Log some basic info about the HTML
        all_tables = soup.find_all('table')
        logger.log(f'EZTV: Found {len(all_tables)} total tables in HTML', log_utils.LOGDEBUG)
        
        # Try multiple table detection methods
        torrent_table = None
        
        # Method 1: Look for specific table classes that EZTV might use
        table_selectors = [
            'table.forum_header_border',  # Original expectation
            'table[class*="forum"]',      # Any table with "forum" in class
            'table[class*="torrent"]',    # Any table with "torrent" in class
            'table[class*="listing"]',    # Any table with "listing" in class
            'table[class*="episodes"]',   # Any table with "episodes" in class
            '.table-striped',             # Bootstrap-style table
            '.table',                     # Generic table class
            'tbody'                       # Sometimes tbody is the main container
                ]
        
        for selector in table_selectors:
             try:
                 found_elements = soup.select(selector)
                 logger.log(f'EZTV: Selector {selector} found {len(found_elements)} elements', log_utils.LOGDEBUG)
                 
                 if found_elements:
                     # For forum_header_border, we need to find the table that contains torrent data
                     # Look for the table that has both header rows and torrent rows (name="hover")
                     if selector == 'table.forum_header_border':
                         for i, table in enumerate(found_elements):
                             rows = table.find_all('tr')
                             hover_rows = [r for r in rows if r.get('name') == 'hover']
                             logger.log(f'EZTV: Table {i+1} has {len(rows)} total rows, {len(hover_rows)} hover rows', log_utils.LOGDEBUG)
                             
                             # Look for the table with actual torrent data (has hover rows)
                             if hover_rows:
                                 torrent_table = table
                                 logger.log(f'EZTV: Selected table {i+1} with torrent data using selector: {selector}', log_utils.LOGDEBUG)
                                 break
                         if torrent_table:
                             break
                     else:
                         torrent_table = found_elements[0] if selector != 'tbody' else found_elements[0].parent
                         logger.log(f'EZTV: Found table using selector: {selector}', log_utils.LOGDEBUG)
                         break
             except Exception as e:
                 logger.log(f'EZTV: Error with selector {selector}: {str(e)}', log_utils.LOGDEBUG)
                 continue
        
        # Method 2: If no specific table found, look for the largest table
        if not torrent_table and all_tables:
            # Find the table with the most rows (likely the main content table)
            largest_table = max(all_tables, key=lambda t: len(t.find_all('tr')))
            if len(largest_table.find_all('tr')) > 1:  # Must have at least header + 1 row
                torrent_table = largest_table
                logger.log(f'EZTV: Using largest table with {len(largest_table.find_all("tr"))} rows', log_utils.LOGDEBUG)
        
        # Method 3: Look for any container with torrent-like content
        if not torrent_table:
            # Look for divs or other containers that might hold torrent info
            for container_selector in ['.episodes', '.torrent-list', '.listing', '[class*="episode"]']:
                containers = soup.select(container_selector)
                if containers:
                    logger.log(f'EZTV: Found non-table container: {container_selector}', log_utils.LOGDEBUG)
                    # Convert div-based layout to table-like processing
                    return self._parse_non_table_layout(containers[0])
        
        if not torrent_table:
            logger.log('EZTV: No torrent table found after all methods', log_utils.LOGWARNING)
            # Debug: Save first 2000 chars of HTML to help diagnose
            html_sample = html[:2000] if len(html) > 2000 else html
            logger.log(f'EZTV: HTML sample: {html_sample}', log_utils.LOGDEBUG)
            return []
        
        rows = torrent_table.find_all('tr')
        
        # Filter out header rows and empty rows
        torrent_rows = []
        for row in rows:
            # Skip header rows (those with th elements or specific header classes)
            if row.find('th') or 'section_post_header' in str(row.get('class', [])):
                continue
            # Look for actual torrent rows - they should have name="hover" or multiple td elements
            if row.get('name') == 'hover' or len(row.find_all('td')) >= 4:
                torrent_rows.append(row)
        
        logger.log(f'EZTV: Found {len(torrent_rows)} torrent rows in selected table (from {len(rows)} total rows)', log_utils.LOGDEBUG)
        
        # Additional debugging: log info about first few rows
        for i, row in enumerate(torrent_rows[:3]):
            cols = row.find_all(['td', 'th'])
            logger.log(f'EZTV: Torrent row {i+1}: {len(cols)} columns, classes: {row.get("class")}, name: {row.get("name")}', log_utils.LOGDEBUG)
        
        for row in torrent_rows:
            try:
                columns = row.find_all('td')
                if len(columns) < 4:
                    logger.log(f'EZTV: Skipping row with only {len(columns)} columns', log_utils.LOGDEBUG)
                    continue
                
                # Look for magnet link - try multiple methods
                magnet_link = self._extract_magnet_link(row, columns)
                if not magnet_link:
                    # Debug: log the row HTML to see what we're missing
                    row_html = str(row)[:500]  # First 500 chars
                    logger.log(f'EZTV: No magnet found. Row HTML sample: {row_html}', log_utils.LOGDEBUG)
                    continue
                    
                # Extract title
                title = self._extract_title(row, columns)
                if not title:
                    continue
                
                # Extract seeders if available
                seeders = self._extract_seeders(columns)
                
                # Clean up the magnet URL
                url = urllib.parse.unquote_plus(client.replaceHTMLCodes(magnet_link)).split('&tr')[0]
                
                # Extract hash from magnet URL
                hash_match = re.search(r'btih:([a-fA-F0-9]{32,40})', url, re.I)
                if not hash_match:
                    logger.log(f'EZTV: No valid hash found in URL: {url}', log_utils.LOGDEBUG)
                    continue
                
                hash = hash_match.group(1)
                if len(hash) == 32:  # Base32 hash, convert to hex
                    try:
                        hash = scraper_utils.base32_to_hex(hash, 'EZTV')
                        url = re.sub(r'btih:[a-fA-F0-9]{32}', f'btih:{hash}', url)
                    except Exception as e:
                        logger.log(f'EZTV: Error converting hash: {str(e)}', log_utils.LOGWARNING)
                        continue
                elif len(hash) != 40:
                    logger.log(f'EZTV: Invalid hash length: {len(hash)}', log_utils.LOGDEBUG)
                    continue
                
                # Clean up title
                name = title.replace('[eztv]', '').replace(' Torrent: Magnet Link', '').strip()
                name = scraper_utils.clean_title(name)
                
                # Get quality
                quality = scraper_utils.get_tor_quality(name)
                
                label = f'{name}'
                if seeders > 0:
                    label += f' (S:{seeders})'
                
                sources.append({
                    'class': self,
                    'host': 'torrent',
                    'label': label,
                    'multi-part': False,
                    'hash': hash,
                    'name': name,
                    'quality': quality,
                    'language': 'en',
                    'url': url,
                    'direct': False,
                    'debridonly': True,
                    'seeders': seeders
                })
                
                logger.log(f'EZTV: Added source - {name} ({quality})', log_utils.LOGDEBUG)
                
            except Exception as e:
                logger.log(f'Error processing EZTV source: {str(e)}', log_utils.LOGERROR)
                continue
        
        logger.log(f'EZTV: Returning {len(sources)} sources', log_utils.LOGDEBUG)
        return sources

    def _get_search_html(self, search_url):
        """Try multiple methods to get the search results with visible links"""
        
        # Method 1: POST with def_wlinks layout
        try:
            post_data = urllib.parse.urlencode({'layout': 'def_wlinks'}).encode('utf-8')
            html = self._http_get(search_url, data=post_data, require_debrid=True, cache_limit=.5)
            if html and 'magnet:' in html:
                logger.log('EZTV: Got links with def_wlinks method', log_utils.LOGDEBUG)
                return html
        except Exception as e:
            logger.log(f'EZTV: def_wlinks method failed: {str(e)}', log_utils.LOGDEBUG)
        
        # Method 2: Try with different layout parameters
        for layout in ['def_nodef_wlinks', 'def_no_wlinks', 'simple', 'full']:
            try:
                post_data = urllib.parse.urlencode({'layout': layout}).encode('utf-8')
                html = self._http_get(search_url, data=post_data, require_debrid=True, cache_limit=.5)
                if html and 'magnet:' in html:
                    logger.log(f'EZTV: Got links with {layout} method', log_utils.LOGDEBUG)
                    return html
            except Exception as e:
                logger.log(f'EZTV: {layout} method failed: {str(e)}', log_utils.LOGDEBUG)
        
        # Method 3: Try regular GET request
        try:
            html = self._http_get(search_url, require_debrid=True, cache_limit=.5)
            if html:
                logger.log('EZTV: Got HTML with regular GET', log_utils.LOGDEBUG)
                return html
        except Exception as e:
            logger.log(f'EZTV: Regular GET failed: {str(e)}', log_utils.LOGDEBUG)
        
        # Method 4: Try with show parameter
        try:
            url_with_param = f"{search_url}?show=1"
            html = self._http_get(url_with_param, require_debrid=True, cache_limit=.5)
            if html and 'magnet:' in html:
                logger.log('EZTV: Got links with show parameter', log_utils.LOGDEBUG)
                return html
        except Exception as e:
            logger.log(f'EZTV: Show parameter method failed: {str(e)}', log_utils.LOGDEBUG)
        
        return ''
    
    def _extract_magnet_link(self, row, columns):
        """Extract magnet link from table row using multiple methods"""
        
        # Debug: log column count and sample content
        logger.log(f'EZTV: Checking row with {len(columns)} columns for magnet links', log_utils.LOGDEBUG)
        
        # Method 1: EZTV specific - look in 3rd column (index 2) for magnet link
        if len(columns) >= 3:
            download_column = columns[2]  # Download column is typically 3rd
            
            # Debug: log what's in the download column
            column_html = str(download_column)[:200]
            logger.log(f'EZTV: Download column HTML: {column_html}', log_utils.LOGDEBUG)
            
            magnet_links = download_column.find_all('a', href=re.compile(r'^magnet:', re.I))
            if magnet_links:
                logger.log(f'EZTV: Found magnet link in download column: {magnet_links[0]["href"][:50]}...', log_utils.LOGDEBUG)
                return magnet_links[0]['href']
            else:
                logger.log('EZTV: No direct magnet links found in download column', log_utils.LOGDEBUG)
        
        # Method 2: Look for direct magnet links in all columns
        for i, column in enumerate(columns):
            magnet_links = column.find_all('a', href=re.compile(r'^magnet:', re.I))
            if magnet_links:
                logger.log(f'EZTV: Found magnet link in column {i}: {magnet_links[0]["href"][:50]}...', log_utils.LOGDEBUG)
                return magnet_links[0]['href']
        
        # Method 3: Look for magnet links with class="magnet"
        for i, column in enumerate(columns):
            magnet_links = column.find_all('a', class_='magnet')
            logger.log(f'EZTV: Column {i} has {len(magnet_links)} links with class "magnet"', log_utils.LOGDEBUG)
            
            if magnet_links:
                for j, link in enumerate(magnet_links):
                    href = link.get('href')
                    logger.log(f'EZTV: Magnet link {j} href: {href}', log_utils.LOGDEBUG)
                    if href and href.startswith('magnet:'):
                        logger.log(f'EZTV: Found magnet link by class: {href[:50]}...', log_utils.LOGDEBUG)
                        return href
                    elif href:
                        logger.log(f'EZTV: Link with magnet class but no magnet href: {href}', log_utils.LOGDEBUG)
        
        # Method 4: Look for magnet links in onclick or other attributes
        for column in columns:
            for link in column.find_all('a'):
                for attr in ['onclick', 'data-magnet', 'data-url']:
                    if link.get(attr) and 'magnet:' in str(link.get(attr)):
                        magnet_match = re.search(r'magnet:[^"\'\s]+', str(link.get(attr)))
                        if magnet_match:
                            return magnet_match.group(0)
        
        # Method 5: Look for magnet links in the HTML content using regex
        row_html = str(row)
        magnet_matches = re.findall(r'magnet:\?[^"\'\s<>]+', row_html, re.I)
        if magnet_matches:
            logger.log(f'EZTV: Found magnet link by regex: {magnet_matches[0][:50]}...', log_utils.LOGDEBUG)
            return magnet_matches[0]
        
        logger.log('EZTV: No magnet link found in row', log_utils.LOGDEBUG)
        return None
    
    def _extract_title(self, row, columns):
        """Extract title from table row"""
        
        # EZTV specific - look in 2nd column (index 1) for episode name
        if len(columns) >= 2:
            title_column = columns[1]  # Episode Name column is typically 2nd
            
            # Look for links with title attribute (preferred)
            for link in title_column.find_all('a'):
                title = link.get('title')
                if title and not title.lower().startswith(('magnet', 'download', 'info')):
                    logger.log(f'EZTV: Found title in title attribute: {title}', log_utils.LOGDEBUG)
                    return title
            
            # Look for links with class="epinfo" (EZTV specific)
            epinfo_links = title_column.find_all('a', class_='epinfo')
            if epinfo_links:
                title = epinfo_links[0].get('title') or epinfo_links[0].get_text(strip=True)
                if title:
                    logger.log(f'EZTV: Found title in epinfo link: {title}', log_utils.LOGDEBUG)
                    return title
        
        # Fallback: Look for title in all columns
        for i, column in enumerate(columns):
            # Try links with title attribute
            for link in column.find_all('a'):
                title = link.get('title')
                if title and not title.lower().startswith(('magnet', 'download', 'info')):
                    logger.log(f'EZTV: Found title in column {i} title attribute: {title}', log_utils.LOGDEBUG)
                    return title
            
            # Try class-based selection
            title_elem = column.find(['a', 'span'], class_=re.compile(r'(title|name|epinfo)', re.I))
            if title_elem:
                title = title_elem.get('title') or title_elem.get_text(strip=True)
                if title and not title.lower().startswith(('magnet', 'download', 'info')):
                    logger.log(f'EZTV: Found title in column {i} by class: {title}', log_utils.LOGDEBUG)
                    return title
        
        # Last resort: get text from links in title-like columns
        for i in [1, 2, 3]:
            if len(columns) > i:
                links = columns[i].find_all('a')
                for link in links:
                    text = link.get_text(strip=True)
                    if text and len(text) > 10 and not text.lower().startswith(('magnet', 'download', 'info')):
                        logger.log(f'EZTV: Found title in column {i} link text: {text}', log_utils.LOGDEBUG)
                        return text
        
        logger.log('EZTV: No title found in row', log_utils.LOGDEBUG)
        return None
    
    def _extract_seeders(self, columns):
        """Extract seeder count from table columns"""
        try:
            # EZTV specific - look in last column for green colored text (seeders)
            if len(columns) >= 1:
                last_column = columns[-1]  # Seeders are typically in the last column
                
                # Look for font with color="green" (EZTV specific)
                green_fonts = last_column.find_all('font', color='green')
                if green_fonts:
                    seeder_text = green_fonts[0].get_text(strip=True)
                    numbers = re.findall(r'\d+', seeder_text.replace(',', ''))
                    if numbers:
                        seeders = int(numbers[0])
                        logger.log(f'EZTV: Found {seeders} seeders in green font', log_utils.LOGDEBUG)
                        return seeders
                
                # Fallback: look for any numbers in last column
                text = last_column.get_text(strip=True)
                numbers = re.findall(r'\d+', text.replace(',', ''))
                if numbers:
                    seeders = int(numbers[0])
                    logger.log(f'EZTV: Found {seeders} seeders in last column text', log_utils.LOGDEBUG)
                    return seeders
            
            # General fallback: Look for numbers in the last few columns
            for i in range(max(0, len(columns)-3), len(columns)):
                if i < len(columns):
                    text = columns[i].get_text(strip=True)
                    # Look for numbers that could be seeders
                    numbers = re.findall(r'\d+', text.replace(',', ''))
                    if numbers:
                        seeders = int(numbers[0])
                        logger.log(f'EZTV: Found {seeders} seeders in column {i}', log_utils.LOGDEBUG)
                        return seeders
            
            return 0
        except Exception as e:
            logger.log(f'EZTV: Error extracting seeders: {str(e)}', log_utils.LOGDEBUG)
            return 0
    
    def _parse_non_table_layout(self, container):
        """Parse div-based or other non-table layout for torrent information"""
        sources = []
        logger.log('EZTV: Attempting to parse non-table layout', log_utils.LOGDEBUG)
        
        try:
            # Look for div elements that might contain torrent info
            torrent_items = container.find_all(['div', 'li', 'article'], class_=re.compile(r'(episode|torrent|item|entry)', re.I))
            
            if not torrent_items:
                # Try broader search
                torrent_items = container.find_all(['div', 'li', 'article'])
            
            logger.log(f'EZTV: Found {len(torrent_items)} potential torrent items in non-table layout', log_utils.LOGDEBUG)
            
            for item in torrent_items:
                try:
                    # Look for magnet links
                    magnet_link = None
                    for link in item.find_all('a', href=re.compile(r'^magnet:', re.I)):
                        magnet_link = link['href']
                        break
                    
                    if not magnet_link:
                        # Look in onclick or other attributes
                        for element in item.find_all(['a', 'button', 'span']):
                            for attr in ['onclick', 'data-magnet', 'data-url', 'href']:
                                if element.get(attr) and 'magnet:' in str(element.get(attr)):
                                    magnet_match = re.search(r'magnet:[^"\'\s]+', str(element.get(attr)))
                                    if magnet_match:
                                        magnet_link = magnet_match.group(0)
                                        break
                            if magnet_link:
                                break
                    
                    if not magnet_link:
                        continue
                    
                    # Extract title
                    title = None
                    # Try different ways to get the title
                    title_selectors = [
                        '.title', '.name', '.episode-title', 'h1', 'h2', 'h3', 'h4',
                        '[class*="title"]', '[class*="name"]', 'a[title]'
                    ]
                    
                    for selector in title_selectors:
                        title_elem = item.select_one(selector)
                        if title_elem:
                            title = title_elem.get('title') or title_elem.get_text(strip=True)
                            if title and not title.lower().startswith(('magnet', 'download')):
                                break
                    
                    if not title:
                        # Fallback: get text from first link or heading
                        for elem in item.find_all(['a', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6']):
                            text = elem.get_text(strip=True)
                            if text and not text.lower().startswith(('magnet', 'download', 'link')):
                                title = text
                                break
                    
                    if not title:
                        continue
                    
                    # Process the magnet link
                    url = urllib.parse.unquote_plus(client.replaceHTMLCodes(magnet_link)).split('&tr')[0]
                    
                    # Extract hash
                    hash_match = re.search(r'btih:([a-fA-F0-9]{32,40})', url, re.I)
                    if not hash_match:
                        continue
                    
                    hash = hash_match.group(1)
                    if len(hash) == 32:  # Base32 hash, convert to hex
                        try:
                            hash = scraper_utils.base32_to_hex(hash, 'EZTV')
                            url = re.sub(r'btih:[a-fA-F0-9]{32}', f'btih:{hash}', url)
                        except Exception as e:
                            logger.log(f'EZTV: Error converting hash: {str(e)}', log_utils.LOGWARNING)
                            continue
                    elif len(hash) != 40:
                        continue
                    
                    # Clean up title
                    name = title.replace('[eztv]', '').replace(' Torrent: Magnet Link', '').strip()
                    name = scraper_utils.clean_title(name)
                    
                    # Get quality
                    quality = scraper_utils.get_tor_quality(name)
                    
                    # Try to extract seeders
                    seeders = 0
                    seeder_text = item.get_text()
                    seeder_matches = re.findall(r'(\d+)\s*(?:seed|s\.)', seeder_text, re.I)
                    if seeder_matches:
                        seeders = int(seeder_matches[0])
                    
                    label = f'{name}'
                    if seeders > 0:
                        label += f' (S:{seeders})'
                    
                    sources.append({
                        'class': self,
                        'host': 'torrent',
                        'label': label,
                        'multi-part': False,
                        'hash': hash,
                        'name': name,
                        'quality': quality,
                        'language': 'en',
                        'url': url,
                        'direct': False,
                        'debridonly': True,
                        'seeders': seeders
                    })
                    
                    logger.log(f'EZTV: Added non-table source - {name} ({quality})', log_utils.LOGDEBUG)
                    
                except Exception as e:
                    logger.log(f'EZTV: Error processing non-table item: {str(e)}', log_utils.LOGERROR)
                    continue
            
        except Exception as e:
            logger.log(f'EZTV: Error in non-table parsing: {str(e)}', log_utils.LOGERROR)
        
        return sources

    def _http_get(self, url, data=None, retry=True, allow_redirect=True, cache_limit=8, require_debrid=True):
        if require_debrid:
            if Scraper.debrid_resolvers is None:
                Scraper.debrid_resolvers = [resolver for resolver in resolveurl.relevant_resolvers() if resolver.isUniversal()]
            if not Scraper.debrid_resolvers:
                logger.log('%s requires debrid: %s' % (self.__module__, Scraper.debrid_resolvers), log_utils.LOGDEBUG)
                return ''
        try:
            import gzip
            import zlib
            
            headers = {
                'User-Agent': scraper_utils.get_ua(),
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
                'Accept-Language': 'en-US,en;q=0.5',
                'Accept-Encoding': 'gzip, deflate',
                'Referer': self.base_url
            }
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                content = response.read()
                
                # Handle compressed content
                content_encoding = response.getheader('Content-Encoding', '').lower()
                if content_encoding == 'gzip':
                    try:
                        content = gzip.decompress(content)
                        logger.log('EZTV: Decompressed gzip content', log_utils.LOGDEBUG)
                    except Exception as e:
                        logger.log(f'EZTV: Failed to decompress gzip: {str(e)}', log_utils.LOGWARNING)
                elif content_encoding == 'deflate':
                    try:
                        content = zlib.decompress(content)
                        logger.log('EZTV: Decompressed deflate content', log_utils.LOGDEBUG)
                    except Exception as e:
                        logger.log(f'EZTV: Failed to decompress deflate: {str(e)}', log_utils.LOGWARNING)
                
                # Decode to string
                try:
                    return content.decode('utf-8')
                except UnicodeDecodeError:
                    try:
                        return content.decode('latin-1')
                    except UnicodeDecodeError:
                        return content.decode('utf-8', errors='ignore')
                        
        except urllib.error.HTTPError as e:
            logger.log(f'HTTP Error: {e.code} - {url}', log_utils.LOGWARNING)
        except urllib.error.URLError as e:
            logger.log(f'URL Error: {e.reason} - {url}', log_utils.LOGWARNING)
        except Exception as e:
            logger.log(f'Unexpected error: {str(e)} - {url}', log_utils.LOGWARNING)
        return ''