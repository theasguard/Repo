"""
    Asguard Kodi Addon
    Copyright (C) 2024 MrBlamo

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

import logging
import re
import urllib.parse, urllib.request, urllib.error
from bs4 import BeautifulSoup, SoupStrainer
import kodi
import log_utils
from asguard_lib import scraper_utils, control
from asguard_lib.constants import FORCE_NO_MATCH, VIDEO_TYPES, QUALITIES
from asguard_lib.utils2 import i18n
from asguard_lib.cloudflare_bypass import get_html_with_cf_bypass, CFBypass
from . import scraper
import concurrent.futures

try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)

logging.basicConfig(level=logging.DEBUG)
logger = log_utils.Logger.get_logger()
BASE_URL = "https://en.torrentfunk-official.live"

class Scraper(scraper.Scraper):
    base_url = BASE_URL
    debrid_resolvers = resolveurl

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url') or BASE_URL
        self.result_limit = kodi.get_setting(f'{self.get_name()}-result_limit')
        self.min_seeders = 0
        self.cf_bypass = CFBypass(timeout=timeout)
        self.use_cf_bypass = True

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'TorrentFunk'

    def resolve_link(self, link):
        return link

    def get_sources(self, video):
        hosters = []
        
        content_url = self._build_content_url(video)
        
        if not content_url or content_url == FORCE_NO_MATCH:
            logger.log('TorrentFunk: No valid content URL could be built', log_utils.LOGWARNING)
            return hosters

        logger.log(f'TorrentFunk Content URL: {content_url}', log_utils.LOGNOTICE)      
        
        # Try enhanced CF bypass first if enabled, then fallback to standard method
        html = self._get_html_with_bypass(content_url, require_debrid=True)

        if not html:
            logger.log('TorrentFunk: No HTML response received - check network/URL', log_utils.LOGWARNING)
            return hosters

        # Parse the HTML for the content page
        soup = BeautifulSoup(html, "html.parser")
        
        # Enhanced debug logging 
        logger.log(f'TorrentFunk HTML length: {len(html)} chars', log_utils.LOGNOTICE)
        
        # Check for key elements that should be present
        modal_count = len(soup.find_all('div', class_='modal'))
        table_count = len(soup.find_all('table'))
        magnet_count = len(soup.find_all('a', href=re.compile(r'^magnet:', re.I)))
        
        logger.log(f'TorrentFunk HTML analysis: {modal_count} modals, {table_count} tables, {magnet_count} magnet links', log_utils.LOGNOTICE)
        
        # Check specifically for our expected structure
        modal_download = soup.find('div', class_='modal modal-download')
        if modal_download:
            modal_table = modal_download.find('table', class_='table')
            if modal_table:
                tbody = modal_table.find('tbody')
                if tbody:
                    rows = tbody.find_all('tr')
                    logger.log(f'TorrentFunk: Found expected structure with {len(rows)} torrent rows', log_utils.LOGNOTICE)
                else:
                    logger.log('TorrentFunk: No tbody found in modal table', log_utils.LOGWARNING)
            else:
                logger.log('TorrentFunk: No table found in modal', log_utils.LOGWARNING)
        else:
            logger.log('TorrentFunk: No modal-download found', log_utils.LOGWARNING)
        
        # Try to parse torrent information from the content page
        hosters = self._parse_content_page(soup, video)

        logger.log(f'TorrentFunk FINAL RESULT: {len(hosters)} sources extracted', log_utils.LOGNOTICE)
        if hosters:
            for i, hoster in enumerate(hosters[:3]):  # Log first 3 sources
                logger.log(f'TorrentFunk Source {i+1}: {hoster["name"][:50]}... | {hoster["quality"]} | {hoster["size"]}', log_utils.LOGNOTICE)
        
        return hosters

    def _get_html_with_bypass(self, url, require_debrid=False, max_retries=1):
        """
        Enhanced HTTP method with Cloudflare bypass capabilities
        Optimized to fail fast on consistent blocking (403 errors)
        """
        # Check debrid requirement first
        if require_debrid:
            if Scraper.debrid_resolvers is None:
                try:
                    Scraper.debrid_resolvers = [resolver for resolver in resolveurl.resolve(url) if resolver.isUniversal()]
                except:
                    Scraper.debrid_resolvers = []
            if not Scraper.debrid_resolvers:
                logger.log(f'TorrentFunk requires debrid but none available: {Scraper.debrid_resolvers}', log_utils.LOGDEBUG)
                return ''
        
        # Method 1: Quick standard method test first
        logger.log('TorrentFunk: Quick standard test first', log_utils.LOGDEBUG)
        try:
            html = self._http_get(url, require_debrid=require_debrid)
            if html and len(html) > 1000:
                logger.log('TorrentFunk: Standard HTTP method successful', log_utils.LOGDEBUG)
                return html
        except urllib.error.HTTPError as e:
            if e.code == 403:
                logger.log('TorrentFunk: HTTP 403 detected - site is blocking access', log_utils.LOGWARNING)
                logger.log('TorrentFunk: Trying alternative domains/URLs', log_utils.LOGDEBUG)
                # Try alternative approach before giving up
                return self._try_alternative_urls(url, require_debrid)
            else:
                logger.log(f'TorrentFunk: Standard HTTP failed with {e.code}, trying CF bypass', log_utils.LOGDEBUG)
        except Exception as e:
            logger.log(f'TorrentFunk: Standard HTTP method failed: {e}', log_utils.LOGDEBUG)
        
        # Method 2: Try simplified CF bypass only if not blocked
        if self.use_cf_bypass:
            logger.log('TorrentFunk: Trying simplified CF bypass', log_utils.LOGDEBUG)
            try:
                html = get_html_with_cf_bypass(url, max_retries=1)  # Reduced retries
                if html and len(html) > 1000:
                    logger.log('TorrentFunk: Simplified CF bypass successful', log_utils.LOGDEBUG)
                    return html
            except Exception as e:
                logger.log(f'TorrentFunk: Simplified CF bypass failed: {e}', log_utils.LOGDEBUG)
        
        logger.log('TorrentFunk: All bypass methods failed', log_utils.LOGWARNING)
        return ''

    def _try_alternative_urls(self, original_url, require_debrid=False):
        """Try alternative URLs when main domain is blocked"""
        
        # Alternative TorrentFunk domains/mirrors
        alternative_domains = [
            'torrentfunk.com',
            'torrentfunk-official.live', 
            'torrentfunk.live',
            'eztv-official.live',
            'eztv.ag'
        ]
        
        # Extract path from original URL
        parsed = urllib.parse.urlparse(original_url)
        path = parsed.path
        
        for domain in alternative_domains:
            try:
                alt_url = f"https://{domain}{path}"
                logger.log(f'TorrentFunk: Trying alternative URL: {alt_url}', log_utils.LOGDEBUG)
                
                html = self._http_get(alt_url, require_debrid=require_debrid)
                if html and len(html) > 1000:
                    logger.log(f'TorrentFunk: Alternative URL successful: {domain}', log_utils.LOGNOTICE)
                    # Update base_url for future requests
                    self.base_url = f"https://{domain}"
                    return html
                    
            except Exception as e:
                logger.log(f'TorrentFunk: Alternative URL {domain} failed: {e}', log_utils.LOGDEBUG)
                continue
        
        logger.log('TorrentFunk: All alternative URLs failed', log_utils.LOGWARNING)
        return ''

    def _build_content_url(self, video):
        """Build the direct content URL based on video type and title"""
        try:
            # Format the title for URL (lowercase, spaces to dashes, remove special chars)
            formatted_title = self._format_title_for_url(video.title)
            
            if video.video_type == VIDEO_TYPES.MOVIE:
                # Format: /movies/title-year
                url_path = f"/movies/{formatted_title}-{video.year}"
            elif video.video_type == VIDEO_TYPES.EPISODE:
                # For specific episodes, we need both season and episode numbers
                # Format: /episodes/title-year-season-X-episode-Y
                if hasattr(video, 'season') and hasattr(video, 'episode') and video.season and video.episode:
                    season_num = int(video.season)
                    episode_num = int(video.episode)
                    year = video.year if video.year else ''
                    url_path = f"/episodes/{formatted_title}-{year}-season-{season_num}-episode-{episode_num}"
                else:
                    logger.log('TorrentFunk: Episode request missing season or episode number', log_utils.LOGWARNING)
                    return None
            elif video.video_type == VIDEO_TYPES.TVSHOW:
                # For TV shows, use season-specific URL if season is available
                if hasattr(video, 'season') and video.season:
                    season_num = int(video.season)
                    url_path = f"/seasons/{formatted_title}-{video.year}-season-{season_num}"
                else:
                    # Fallback to general series page
                    url_path = f"/series/{formatted_title}-{video.year}"
            else:
                logger.log(f'TorrentFunk: Unsupported video type: {video.video_type}', log_utils.LOGWARNING)
                return None
                
            content_url = scraper_utils.urljoin(self.base_url, url_path)
            return content_url
            
        except Exception as e:
            logger.log(f'TorrentFunk Error building content URL: {e}', log_utils.LOGWARNING)
            return None

    def _format_title_for_url(self, title):
        """Format title for URL path (similar to how the site formats titles)"""
        # Convert to lowercase
        formatted = title.lower()
        
        # Remove common punctuation and special characters
        formatted = re.sub(r'[^\w\s-]', '', formatted)
        
        # Replace spaces with dashes
        formatted = re.sub(r'\s+', '-', formatted)
        
        # Remove multiple consecutive dashes
        formatted = re.sub(r'-+', '-', formatted)
        
        # Remove leading/trailing dashes
        formatted = formatted.strip('-')
        
        return formatted

    def _parse_content_page(self, soup, video):
        """Parse torrent information from the content page"""
        hosters = []
        
        try:
            # Method 1: Look for the modal torrent table structure (primary method for this site)
            hosters = self._parse_modal_torrent_table(soup, video)
            
            # Method 2: Look for torrent links or magnet links directly (fallback)
            if not hosters:
                magnet_links = soup.find_all('a', href=re.compile(r'^magnet:', re.I))
                for magnet_link in magnet_links:
                    try:
                        hoster = self._create_hoster_from_magnet(magnet_link, video, soup)
                        if hoster:
                            hosters.append(hoster)
                    except Exception as e:
                        logger.log(f'TorrentFunk Error processing magnet link: {e}', log_utils.LOGDEBUG)
                        continue
            
            # Method 3: Look for torrent download sections or tables (fallback)
            if not hosters:
                hosters = self._parse_torrent_sections(soup, video)
            
            # Method 4: Look for embedded torrent information (fallback)
            if not hosters:
                hosters = self._parse_embedded_torrents(soup, video)
                
        except Exception as e:
            logger.log(f'TorrentFunk Error parsing content page: {e}', log_utils.LOGWARNING)
        
        return hosters

    def _parse_modal_torrent_table(self, soup, video):
        """Parse the modal torrent table structure specifically"""
        hosters = []
        
        try:
            # Check for modal container first
            modal = soup.find('div', class_='modal modal-download')
            if modal:
                logger.log('TorrentFunk: Found modal container', log_utils.LOGNOTICE)
                # Look for table within the modal
                torrent_table = modal.find('table', class_='table')
            else:
                logger.log('TorrentFunk: No modal found, looking for table directly', log_utils.LOGNOTICE)
                # Look for the torrent table directly
                torrent_table = soup.find('table', class_='table')
            
            if not torrent_table:
                logger.log('TorrentFunk: No torrent table found', log_utils.LOGWARNING)
                return hosters
            
            # Find all torrent rows in the tbody
            torrent_rows = torrent_table.find('tbody')
            if not torrent_rows:
                logger.log('TorrentFunk: No tbody found in torrent table', log_utils.LOGWARNING)
                return hosters
            
            rows = torrent_rows.find_all('tr')
            logger.log(f'TorrentFunk: Found {len(rows)} torrent rows', log_utils.LOGNOTICE)
            
            success_count = 0
            for i, row in enumerate(rows):
                try:
                    hoster = self._extract_torrent_from_table_row(row, video)
                    if hoster:
                        hosters.append(hoster)
                        success_count += 1
                        if success_count <= 3:  # Log first 3 successful extractions
                            logger.log(f'TorrentFunk: Row {i+1} extracted: {hoster["name"][:50]}...', log_utils.LOGNOTICE)
                except Exception as e:
                    logger.log(f'TorrentFunk Error processing torrent row {i+1}: {e}', log_utils.LOGWARNING)
                    continue
            
            logger.log(f'TorrentFunk: Successfully extracted {success_count}/{len(rows)} torrents', log_utils.LOGNOTICE)
            
        except Exception as e:
            logger.log(f'TorrentFunk Error parsing modal torrent table: {e}', log_utils.LOGWARNING)
        
        return hosters

    def _extract_torrent_from_table_row(self, row, video):
        """Extract torrent information from a table row"""
        try:
            cells = row.find_all('td')
            if len(cells) < 5:
                logger.log(f'TorrentFunk: Row has insufficient columns ({len(cells)})', log_utils.LOGDEBUG)
                return None
            
            # Column structure: Quality, Name, Size, Download, Magnet
            quality_cell = cells[0]
            name_cell = cells[1] 
            size_cell = cells[2]
            download_cell = cells[3]
            magnet_cell = cells[4]
            
            # Extract quality
            quality_text = quality_cell.get_text(strip=True)
            
            # Extract title - prefer the title attribute, fallback to text content
            title = name_cell.get('title', '').strip()
            if not title:
                title = name_cell.get_text(strip=True)
            
            if not title:
                logger.log('TorrentFunk: No title found for torrent', log_utils.LOGDEBUG)
                return None
            
            # Extract size
            size = size_cell.get_text(strip=True)
            if not size:
                size = 'N/A'
            
            # Extract magnet link - try magnet cell first, then download cell
            magnet_link = None
            
            # Check magnet cell first
            magnet_a = magnet_cell.find('a', href=re.compile(r'^magnet:', re.I))
            if magnet_a:
                magnet_link = magnet_a.get('href')
            
            # Fallback to download cell
            if not magnet_link:
                download_a = download_cell.find('a', href=re.compile(r'^magnet:', re.I))
                if download_a:
                    magnet_link = download_a.get('href')
            
            if not magnet_link:
                logger.log(f'TorrentFunk: No magnet link found for {title}', log_utils.LOGWARNING)
                return None
            
            # Try to extract seeders/leechers from data attributes or nearby elements
            seeders = 0
            leechers = 0
            
            # Look for data attributes on the magnet link
            if magnet_a:
                torrent_id = magnet_a.get('data-torrent-id')
                if torrent_id:
                    # Could potentially use this to fetch more detailed info, but for now we'll use defaults
                    pass
            
            # Since we don't have explicit seeder/leecher info in this structure,
            # we'll set reasonable defaults (this data might be loaded via JS)
            seeders = 1  # Assume at least 1 seeder since it's available
            leechers = 0
            
            # Check minimum seeders requirement
            if self.min_seeders > seeders:
                logger.log(f'TorrentFunk Seeders ({seeders}) less than minimum required ({self.min_seeders})', log_utils.LOGDEBUG)
                return None

            # Determine quality from title and quality cell
            if quality_text:
                # Use the quality from the table if available
                if '1080p' in quality_text:
                    quality = QUALITIES.HD1080
                elif '720p' in quality_text:
                    quality = QUALITIES.HD720  
                elif '480p' in quality_text:
                    quality = QUALITIES.HIGH
                else:
                    # Fallback to scraper_utils quality detection
                    quality = scraper_utils.get_tor_quality(title)
            else:
                quality = scraper_utils.get_tor_quality(title)
            
            # Create label
            label = f"{title} | {size} | {seeders} ↑ | {leechers} ↓"
            
            return {
                'name': title,
                'label': label,
                'multi-part': False,
                'class': self,
                'url': magnet_link,
                'size': size,
                'seeders': seeders,
                'quality': quality,
                'host': 'magnet',
                'direct': False,
                'debridonly': True
            }
            
        except Exception as e:
            logger.log(f'TorrentFunk Error extracting torrent from table row: {e}', log_utils.LOGDEBUG)
            return None

    def _create_hoster_from_magnet(self, magnet_link, video, soup):
        """Create a hoster entry from a magnet link"""
        try:
            magnet_href = magnet_link.get('href', '')
            if not magnet_href.startswith('magnet:'):
                return None
            
            # Try to find title from the magnet link's context or the link text
            title = self._extract_title_from_context(magnet_link, soup)
            if not title:
                # Extract from magnet URI
                title = self._extract_title_from_magnet(magnet_href)
            
            # Try to find size and seeders from nearby elements
            size, seeders, leechers = self._extract_torrent_stats(magnet_link, soup)
            
            # Check minimum seeders requirement
            if self.min_seeders > seeders:
                logger.log(f'TorrentFunk Seeders ({seeders}) less than minimum required ({self.min_seeders})', log_utils.LOGDEBUG)
                return None

            # Determine quality from title
            quality = scraper_utils.get_tor_quality(title)
            
            # Create label
            label = f"{title} | {size} | {seeders} ↑ | {leechers} ↓"
            
            return {
                'name': title,
                'label': label,
                'multi-part': False,
                'class': self,
                'url': magnet_href,
                'size': size,
                'seeders': seeders,
                'quality': quality,
                'host': 'magnet',
                'direct': False,
                'debridonly': True
            }
            
        except Exception as e:
            logger.log(f'TorrentFunk Error creating hoster from magnet: {e}', log_utils.LOGDEBUG)
            return None

    def _parse_torrent_sections(self, soup, video):
        """Parse torrent sections or tables"""
        hosters = []
        
        # Look for common torrent table or section structures
        torrent_containers = []
        
        # Try different selectors for torrent containers - updated for TorrentFunk structure
        selectors = [
            'table.table tbody tr',  # Primary structure for TorrentFunk
            'div.modal-download table tbody tr',  # Modal structure for TorrentFunk
            'table.torrent-table tr',
            'div.torrent-list div.torrent-item',
            'div.download-section',
            'ul.torrent-list li',
            'div[class*="torrent"]',
            'tr[class*="torrent"]'
        ]
        
        for selector in selectors:
            containers = soup.select(selector)
            if containers:
                torrent_containers = containers
                logger.log(f'TorrentFunk found torrent containers using selector: {selector} ({len(containers)} items)', log_utils.LOGDEBUG)
                break
        
        for container in torrent_containers:
            try:
                hoster = self._extract_torrent_info(container, video)
                if hoster:
                    hosters.append(hoster)
            except Exception as e:
                logger.log(f'TorrentFunk Error parsing torrent container: {e}', log_utils.LOGDEBUG)
                continue
                
        return hosters

    def _parse_embedded_torrents(self, soup, video):
        """Parse embedded torrent information from scripts or data attributes"""
        hosters = []
        
        # Look for JavaScript variables or JSON data that might contain torrent info
        script_tags = soup.find_all('script')
        for script in script_tags:
            if script.string:
                # Look for patterns that might indicate torrent data
                script_content = script.string
                
                # Look for magnet links in JavaScript
                magnet_matches = re.findall(r'magnet:\?[^"\']+', script_content)
                for magnet in magnet_matches:
                    try:
                        title = self._extract_title_from_magnet(magnet)
                        quality = scraper_utils.get_tor_quality(title)
                        
                        hoster = {
                            'name': title,
                            'label': f"{title} | N/A | 0 ↑ | 0 ↓",
                            'multi-part': False,
                            'class': self,
                            'url': magnet,
                            'size': 'N/A',
                            'seeders': 0,
                            'quality': quality,
                            'host': 'magnet',
                            'direct': False,
                            'debridonly': True
                        }
                        hosters.append(hoster)
                    except Exception as e:
                        logger.log(f'TorrentFunk Error processing embedded magnet: {e}', log_utils.LOGDEBUG)
                        continue
        
        return hosters

    def _extract_title_from_context(self, magnet_link, soup):
        """Extract title from the context around a magnet link"""
        # Look for title in parent elements or nearby text
        parent = magnet_link.parent
        if parent:
            # Check for title in parent text
            parent_text = parent.get_text(strip=True)
            if parent_text and len(parent_text) > 3:
                return parent_text
        
        # Look for title in link text
        link_text = magnet_link.get_text(strip=True)
        if link_text and len(link_text) > 3 and 'magnet' not in link_text.lower():
            return link_text
            
        return None

    def _extract_title_from_magnet(self, magnet_uri):
        """Extract title from magnet URI"""
        try:
            # Parse the magnet URI to extract the display name (dn parameter)
            parsed = urllib.parse.urlparse(magnet_uri)
            params = urllib.parse.parse_qs(parsed.query)
            
            if 'dn' in params:
                title = urllib.parse.unquote_plus(params['dn'][0])
                return title
            
            # Fallback: use hash as title
            if 'xt' in params:
                xt = params['xt'][0]
                if 'btih:' in xt:
                    hash_part = xt.split('btih:')[1][:20]  # First 20 chars of hash
                    return f"Torrent_{hash_part}"
                    
        except Exception as e:
            logger.log(f'TorrentFunk Error extracting title from magnet: {e}', log_utils.LOGDEBUG)
        
        return "Unknown Torrent"

    def _extract_torrent_stats(self, element, soup):
        """Extract size, seeders, and leechers from element context"""
        size = 'N/A'
        seeders = 0
        leechers = 0
        
        # Look in the element and its siblings/parents for stats
        contexts = [element, element.parent] if element.parent else [element]
        
        for context in contexts:
            if not context:
                continue
                
            text = context.get_text()
            
            # Extract size
            size_match = re.search(r'(\d+(?:\.\d+)?\s*(?:GB|MB|KB|TB))', text, re.I)
            if size_match:
                size = size_match.group(1)
            
            # Extract seeders
            seed_match = re.search(r'(?:seed|↑)[:\s]*(\d+)', text, re.I)
            if seed_match:
                try:
                    seeders = int(seed_match.group(1))
                except ValueError:
                    pass
            
            # Extract leechers
            leech_match = re.search(r'(?:leech|↓)[:\s]*(\d+)', text, re.I)
            if leech_match:
                try:
                    leechers = int(leech_match.group(1))
                except ValueError:
                    pass
        
        return size, seeders, leechers

    def _extract_torrent_info(self, element, video):
        """Extract torrent information from a DOM element (reused from previous version)"""
        try:
            # Extract title - try multiple approaches
            title = self._extract_title(element)
            if not title:
                return None
                
            # Extract magnet link
            magnet = self._extract_magnet_link(element)
            if not magnet:
                return None
                
            # Extract size
            size = self._extract_size(element)
            
            # Extract seeders and leechers
            seeders, leechers = self._extract_seeds_leechers(element)
            
            # Check minimum seeders requirement
            if self.min_seeders > seeders:
                logger.log(f'TorrentFunk Seeders ({seeders}) less than minimum required ({self.min_seeders})', log_utils.LOGDEBUG)
                return None

            # Determine quality from title
            quality = scraper_utils.get_tor_quality(title)
            
            # Create label
            label = f"{title} | {size} | {seeders} ↑ | {leechers} ↓"
            
            return {
                'name': title,
                'label': label,
                'multi-part': False,
                'class': self,
                'url': magnet,
                'size': size,
                'seeders': seeders,
                'quality': quality,
                'host': 'magnet',
                'direct': False,
                'debridonly': True
            }
            
        except Exception as e:
            logger.log(f'TorrentFunk Error extracting torrent info: {e}', log_utils.LOGDEBUG)
            return None

    def _extract_title(self, element):
        """Extract title from various possible locations"""
        # Check if this is a table row structure (TorrentFunk format)
        cells = element.find_all('td')
        if len(cells) >= 2:
            # TorrentFunk uses second cell for title with title attribute
            name_cell = cells[1]
            title = name_cell.get('title', '').strip()
            if title and len(title) > 3:
                return title
            # Fallback to cell text
            title = name_cell.get_text(strip=True)
            if title and len(title) > 3:
                return title
        
        # Original selectors for other structures
        title_selectors = [
            'h2.card-title',
            'h3.card-title', 
            '.title',
            '.name',
            'a[href*="torrent"]',
            'a[href*="magnet"]',
            '.torrent-name',
            '.result-title'
        ]
        
        for selector in title_selectors:
            title_elem = element.select_one(selector)
            if title_elem:
                title = title_elem.get_text(strip=True)
                if title and len(title) > 3:  # Basic validation
                    return title
                    
        # Fallback: look for any link that might contain the title
        links = element.find_all('a', href=True)
        for link in links:
            if 'torrent' in link.get('href', '').lower() or 'magnet' in link.get('href', '').lower():
                title = link.get_text(strip=True)
                if title and len(title) > 3:
                    return title
                    
        return None

    def _extract_magnet_link(self, element):
        """Extract magnet link from various possible locations"""
        # Check if this is a table row structure (TorrentFunk format)
        cells = element.find_all('td')
        if len(cells) >= 5:
            # TorrentFunk uses 4th and 5th cells for download/magnet links
            download_cell = cells[3]
            magnet_cell = cells[4]
            
            # Check magnet cell first
            magnet_a = magnet_cell.find('a', href=re.compile(r'^magnet:', re.I))
            if magnet_a:
                return magnet_a.get('href')
            
            # Fallback to download cell
            download_a = download_cell.find('a', href=re.compile(r'^magnet:', re.I))
            if download_a:
                return download_a.get('href')
        
        # Look for direct magnet links (original logic)
        magnet_links = element.find_all('a', href=re.compile(r'^magnet:', re.I))
        if magnet_links:
            return magnet_links[0]['href']
            
        # Look for buttons or links with magnet text
        magnet_selectors = [
            'a[class*="magnet"]',
            'a[title*="magnet"]',
            'a:contains("Magnet")',
            'button[class*="magnet"]'
        ]
        
        for selector in magnet_selectors:
            try:
                magnet_elem = element.select_one(selector)
                if magnet_elem and magnet_elem.get('href'):
                    href = magnet_elem['href']
                    if href.startswith('magnet:'):
                        return href
            except Exception:
                continue
                
        # Look for any link containing 'magnet' in the href
        all_links = element.find_all('a', href=True)
        for link in all_links:
            href = link.get('href', '')
            if href.startswith('magnet:'):
                return href
                
        return None

    def _extract_size(self, element):
        """Extract file size from various possible locations"""
        # Check if this is a table row structure (TorrentFunk format)
        cells = element.find_all('td')
        if len(cells) >= 3:
            # TorrentFunk uses third cell for size
            size_cell = cells[2]
            size = size_cell.get_text(strip=True)
            if size and size != 'N/A':
                return size
        
        # Original size extraction logic
        size_patterns = [
            r'(\d+(?:\.\d+)?\s*(?:GB|MB|KB|TB))',
            r'Size:\s*(\d+(?:\.\d+)?\s*(?:GB|MB|KB|TB))',
            r'(\d+(?:\.\d+)?\s*(?:G|M|K|T)B)',
        ]
        
        text = element.get_text()
        for pattern in size_patterns:
            match = re.search(pattern, text, re.I)
            if match:
                return match.group(1)
                
        # Look for specific size elements
        size_selectors = ['.size', '.file-size', '[class*="size"]']
        for selector in size_selectors:
            size_elem = element.select_one(selector)
            if size_elem:
                size_text = size_elem.get_text(strip=True)
                if re.search(r'\d+(?:\.\d+)?\s*(?:GB|MB|KB|TB)', size_text, re.I):
                    return size_text
                    
        return 'N/A'

    def _extract_seeds_leechers(self, element):
        """Extract seeders and leechers counts"""
        seeders = 0
        leechers = 0
        
        # Look for elements with specific classes
        seeders_elem = element.select_one('.text-success, .seeders, [class*="seed"]')
        if seeders_elem:
            try:
                seeders_text = seeders_elem.get_text(strip=True).replace(',', '')
                seeders = int(re.search(r'\d+', seeders_text).group()) if re.search(r'\d+', seeders_text) else 0
            except (ValueError, AttributeError):
                pass
                
        leechers_elem = element.select_one('.text-error, .text-danger, .leechers, [class*="leech"]')
        if leechers_elem:
            try:
                leechers_text = leechers_elem.get_text(strip=True).replace(',', '')
                leechers = int(re.search(r'\d+', leechers_text).group()) if re.search(r'\d+', leechers_text) else 0
            except (ValueError, AttributeError):
                pass
                
        # Fallback: look for patterns in text
        if seeders == 0 or leechers == 0:
            text = element.get_text()
            seed_match = re.search(r'(?:seed|↑)[:\s]*(\d+)', text, re.I)
            leech_match = re.search(r'(?:leech|↓)[:\s]*(\d+)', text, re.I)
            
            if seed_match:
                try:
                    seeders = int(seed_match.group(1))
                except ValueError:
                    pass
                    
            if leech_match:
                try:
                    leechers = int(leech_match.group(1))
                except ValueError:
                    pass
                    
        return seeders, leechers
