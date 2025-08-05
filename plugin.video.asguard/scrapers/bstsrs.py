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
BASE_URL = 'https://bstsrs.in'

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url') or BASE_URL
        self.domains = ['bstsrs.in', 'bstsrs.one']

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'BstSrs'

    def get_sources(self, video):
        logger.log(f'[BSTSRS] Starting get_sources for video: {video.title} S{video.season}E{video.episode}', log_utils.LOGDEBUG)
        sources = []
        source_url = self.get_url(video)
        
        if not source_url or source_url == scraper_utils.FORCE_NO_MATCH:
            logger.log(f'[BSTSRS] No source URL found for video: {source_url}', log_utils.LOGWARNING)
            return sources

        url = scraper_utils.urljoin(self.base_url, source_url)
        logger.log(f'[BSTSRS] Fetching URL: {url}', log_utils.LOGDEBUG)
        
        html = self._http_get(url, cache_limit=1, require_debrid=True)
        logger.log(f'[BSTSRS] Got HTML length: {len(html) if html else 0}', log_utils.LOGDEBUG)
        
        if not html:
            logger.log('[BSTSRS] No HTML received from bstsrs', log_utils.LOGWARNING)
            return sources

        # Log a snippet of the HTML to see what we're working with
        html_snippet = html[:500] if html else ""
        logger.log(f'[BSTSRS] HTML snippet: {html_snippet}', log_utils.LOGDEBUG)

        # Check if we have the correct show page by looking for IMDB link
        imdb_id = self.get_imdb_id(video)
        if hasattr(video, 'imdb_id') and imdb_id:
            if f'imdb.com/title/{imdb_id}/' not in html:
                logger.log(f'[BSTSRS] IMDB ID {imdb_id} not found on page, may be wrong show', log_utils.LOGWARNING)
            else:
                logger.log(f'[BSTSRS] IMDB ID {imdb_id} confirmed on page', log_utils.LOGDEBUG)

        # Look for encrypted links using the pattern from scrubs bstsrs_one.py
        links = re.findall(r"window\.open\(dbneg\('(.+?)'\)", html)
        logger.log(f'[BSTSRS] Found {len(links)} encrypted links with dbneg pattern', log_utils.LOGDEBUG)
        
        # Also try other potential patterns
        alt_patterns = [
            r"dbneg\('(.+?)'\)",
            r"window\.open\('(.+?)'\)",
            r"href=['\"](.+?)['\"].*?stream",
        ]
        
        for i, pattern in enumerate(alt_patterns):
            alt_links = re.findall(pattern, html, re.IGNORECASE)
            if alt_links:
                logger.log(f'[BSTSRS] Found {len(alt_links)} links with alternative pattern {i+1}: {pattern}', log_utils.LOGDEBUG)
                links.extend(alt_links)

        for i, encrypted_link in enumerate(links):
            try:
                logger.log(f'[BSTSRS] Processing encrypted link {i+1}/{len(links)}: {encrypted_link[:50]}...', log_utils.LOGDEBUG)
                
                # Decode the encrypted link
                decoded_link = self._decode_link(encrypted_link)
                if not decoded_link:
                    logger.log(f'[BSTSRS] Failed to decode link {i+1}', log_utils.LOGDEBUG)
                    continue
                    
                logger.log(f'[BSTSRS] Successfully decoded link {i+1}: {decoded_link}', log_utils.LOGDEBUG)
                
                # Extract host from the decoded link
                host = urllib.parse.urlparse(decoded_link).hostname
                if not host:
                    logger.log(f'[BSTSRS] No hostname found in decoded link {i+1}', log_utils.LOGDEBUG)
                    continue
                
                # Determine quality
                quality = scraper_utils.blog_get_quality(video, decoded_link, host)
                
                source = {
                    'class': self,
                    'quality': quality,
                    'url': decoded_link,
                    'host': host,
                    'multi-part': False,
                    'rating': None,
                    'views': None,
                    'direct': False,
                }
                sources.append(source)
                logger.log(f'[BSTSRS] Added source {len(sources)}: {source}', log_utils.LOGDEBUG)
                
            except Exception as e:
                logger.log(f'[BSTSRS] Error processing encrypted link {i+1}: {e}', log_utils.LOGERROR)
                continue

        # Also look for direct iframe sources as backup
        soup = BeautifulSoup(html, 'html.parser')
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
                logger.log('Found iframe source: %s' % source, log_utils.LOGDEBUG)
                
            except Exception as e:
                logger.log(f'Error processing iframe: {e}', log_utils.LOGDEBUG)
                continue

        return sources

    def _decode_link(self, encrypted_link):
        """
        Decode the encrypted link using the decryption logic from scrubs addon.
        Uses both the hex alphabet replacement and complex decipher methods.
        """
        logger.log(f'[BSTSRS] Starting decryption for link: {encrypted_link[:50]}...', log_utils.LOGDEBUG)
        
        try:
            # First try the simple decode method (hex alphabet replacement)
            decoded_simple = self._simple_decode(encrypted_link)
            logger.log(f'[BSTSRS] Simple decode result: {decoded_simple[:100] if decoded_simple else "None"}...', log_utils.LOGDEBUG)
            
            if decoded_simple and (decoded_simple.startswith('http') or '://' in decoded_simple):
                logger.log(f'[BSTSRS] Simple decode successful: {decoded_simple}', log_utils.LOGDEBUG)
                return decoded_simple
            
            # If simple decode doesn't work, try the complex decipher method
            logger.log('[BSTSRS] Attempting complex decipher method', log_utils.LOGDEBUG)
            decoded_complex = self._decipher(encrypted_link)
            logger.log(f'[BSTSRS] Complex decipher result: {decoded_complex[:100] if decoded_complex else "None"}...', log_utils.LOGDEBUG)
            
            if decoded_complex and (decoded_complex.startswith('http') or '://' in decoded_complex):
                logger.log(f'[BSTSRS] Complex decipher successful: {decoded_complex}', log_utils.LOGDEBUG)
                return decoded_complex
            
            # Try applying simple decode to the complex result
            if decoded_complex:
                final_decode = self._simple_decode(decoded_complex)
                logger.log(f'[BSTSRS] Final decode attempt: {final_decode[:100] if final_decode else "None"}...', log_utils.LOGDEBUG)
                if final_decode and (final_decode.startswith('http') or '://' in final_decode):
                    logger.log(f'[BSTSRS] Final decode successful: {final_decode}', log_utils.LOGDEBUG)
                    return final_decode
            
            logger.log(f'[BSTSRS] All decryption methods failed for: {encrypted_link[:50]}...', log_utils.LOGWARNING)
            return None
            
        except Exception as e:
            logger.log(f'[BSTSRS] Error in _decode_link: {str(e)}', log_utils.LOGERROR)
            return None

    def _simple_decode(self, uri):
        """
        Simple decode using hex alphabet replacement (from scrubs decryption.decode)
        """
        ALPHABET = {
            '47ab07f9': 'A', '47ab07fa': 'B', '47ab07fb': 'C', '47ab07fc': 'D', '47ab07fd': 'E',
            '47ab07fe': 'F', '47ab07ff': 'G', '47ab0800': 'H', '47ab0801': 'I', '47ab0802': 'J',
            '47ab0803': 'K', '47ab0804': 'L', '47ab0805': 'M', '47ab0806': 'N', '47ab0807': 'O',
            '47ab0808': 'P', '47ab0809': 'Q', '47ab080a': 'R', '47ab080b': 'S', '47ab080c': 'T',
            '47ab080d': 'U', '47ab080e': 'V', '47ab080f': 'W', '47ab0810': 'X', '47ab0811': 'Y',
            '47ab0812': 'Z',
            '47ab0819': 'a', '47ab081a': 'b', '47ab081b': 'c', '47ab081c': 'd', '47ab081d': 'e',
            '47ab081e': 'f', '47ab081f': 'g', '47ab0820': 'h', '47ab0821': 'i', '47ab0822': 'j',
            '47ab0823': 'k', '47ab0824': 'l', '47ab0825': 'm', '47ab0826': 'n', '47ab0827': 'o',
            '47ab0828': 'p', '47ab0829': 'q', '47ab082a': 'r', '47ab082b': 's', '47ab082c': 't',
            '47ab082d': 'u', '47ab082e': 'v', '47ab082f': 'w', '47ab0830': 'x', '47ab0831': 'y',
            '47ab0832': 'z',
            '47ab07e8': '0', '47ab07e9': '1', '47ab07ea': '2', '47ab07eb': '3', '47ab07ec': '4',
            '47ab07ed': '5', '47ab07ee': '6', '47ab07ef': '7', '47ab07f0': '8', '47ab07f1': '9',
            '47ab07f2': ':', '47ab07e7': '/', '47ab07e6': '.', '47ab0817': '_', '47ab07e5': '-'
        }
        
        try:
            original_uri = uri
            replacements_made = 0
            
            for key in ALPHABET.keys():
                if key in uri:
                    uri = uri.replace(key, ALPHABET[key])
                    replacements_made += 1
            
            logger.log(f'[BSTSRS] Simple decode made {replacements_made} replacements', log_utils.LOGDEBUG)
            
            # Handle dash replacement (from scrubs logic)
            result = uri.replace('---', '-$DASH$-').replace('-', '').replace('$DASH$', '-')
            
            if result != original_uri:
                logger.log(f'[BSTSRS] Simple decode transformation: {original_uri[:50]}... -> {result[:50]}...', log_utils.LOGDEBUG)
            
            return result
            
        except Exception as e:
            logger.log(f'[BSTSRS] Error in _simple_decode: {str(e)}', log_utils.LOGERROR)
            return uri

    def _decipher(self, encrypted_url):
        """
        Complex decipher method (from scrubs decryption.decipher)
        """
        CHARACTER_MAP = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
        
        try:
            if len(encrypted_url) < 9:
                logger.log(f'[BSTSRS] Encrypted URL too short for decipher: {len(encrypted_url)}', log_utils.LOGDEBUG)
                return None
                
            s1, s2 = encrypted_url[:9], encrypted_url[9:].strip('=')
            logger.log(f'[BSTSRS] Decipher s1: {s1}, s2 length: {len(s2)}', log_utils.LOGDEBUG)
            
            crypto = 0
            decrypted = ""
            
            for index, character in enumerate(s2, 1):
                crypto <<= 6
                if character in CHARACTER_MAP:
                    crypto |= CHARACTER_MAP.index(character)
                if index and not (index % 4):
                    decrypted += chr((0xff0000 & crypto) >> 16) + chr((0xff00 & crypto) >> 8) + chr(0xff & crypto)
                    crypto = 0
                    
            if index % 4 and not (index % 2):
                crypto >>= 4
                decrypted += chr(crypto)
            if index % 4 and not (index % 3):
                decrypted += chr((65280 & crypto) >> 8) + chr(255 & crypto)
                
            decrypted = urllib.parse.unquote(decrypted)
            logger.log(f'[BSTSRS] After base64-like decode: {decrypted[:50]}...', log_utils.LOGDEBUG)
            
            # RC4-like decryption
            mapper = {byte_index: byte_index for byte_index in range(0x100)}
            xcrypto = 0
            
            for byte_index in range(0x100):
                xcrypto = (xcrypto + mapper.get(byte_index) + ord(s1[byte_index % len(s1)])) % 0x100
                mapper[byte_index], mapper[xcrypto] = mapper[xcrypto], mapper[byte_index]
                
            xcryptoz, xcryptoy = 0, 0
            cipher = ""
            
            for character in decrypted:
                xcryptoy = (xcryptoy + 1) % 0x100
                xcryptoz = (xcryptoz + mapper.get(xcryptoy)) % 0x100
                mapper[xcryptoy], mapper[xcryptoz] = mapper[xcryptoz], mapper[xcryptoy]
                cipher += chr(ord(character) ^ mapper[(mapper[xcryptoy] + mapper[xcryptoz]) % 0x100])
                
            logger.log(f'[BSTSRS] Final decipher result: {cipher[:50]}...', log_utils.LOGDEBUG)
            return cipher
            
        except Exception as e:
            logger.log(f'[BSTSRS] Error in _decipher: {str(e)}', log_utils.LOGERROR)
            return None

    def _clean_title_for_url(self, title):
        """
        Clean title for URL use, fallback if scraper_utils.to_slug doesn't exist
        """
        try:
            if hasattr(scraper_utils, 'to_slug'):
                return scraper_utils.to_slug(title)
            else:
                # Fallback manual slug creation
                import re
                # Convert to lowercase and replace spaces/special chars with hyphens
                slug = re.sub(r'[^\w\s-]', '', title.lower())
                slug = re.sub(r'[-\s]+', '-', slug)
                slug = slug.strip('-')
                logger.log(f'[BSTSRS] Manual slug creation: {title} -> {slug}', log_utils.LOGDEBUG)
                return slug
        except Exception as e:
            logger.log(f'[BSTSRS] Error in _clean_title_for_url: {e}', log_utils.LOGERROR)
            # Ultimate fallback - just return original title with basic cleanup
            return title.lower().replace(' ', '-').replace("'", "")

    def search(self, video_type, title, year, season=''):
        """
        Search implementation for bstsrs
        """
        logger.log(f'[BSTSRS] Starting search: type={video_type}, title={title}, year={year}, season={season}', log_utils.LOGDEBUG)
        results = []
        try:
            # Clean the title for URL formatting
            clean_title = self._clean_title_for_url(title)
            logger.log(f'[BSTSRS] Clean title: {title} -> {clean_title}', log_utils.LOGDEBUG)
            
            if video_type == VIDEO_TYPES.TVSHOW:
                # For TV shows, we'll search and return the show page
                search_url = f'/show/{clean_title}'
            else:
                # For episodes, include season info if available
                if season:
                    search_url = f'/show/{clean_title}/season/{season}'
                else:
                    search_url = f'/show/{clean_title}'
            
            url = scraper_utils.urljoin(self.base_url, search_url)
            logger.log(f'[BSTSRS] Search URL: {url}', log_utils.LOGDEBUG)
            
            html = self._http_get(url, cache_limit=1)
            logger.log(f'[BSTSRS] Search HTML length: {len(html) if html else 0}', log_utils.LOGDEBUG)
            
            if html:
                # Log a snippet of the search HTML
                html_snippet = html[:300] if html else ""
                logger.log(f'[BSTSRS] Search HTML snippet: {html_snippet}', log_utils.LOGDEBUG)
                
                # Check if the page exists and contains the expected content
                soup = BeautifulSoup(html, 'html.parser')
                
                # Look for show title or episode listings to confirm it's a valid result
                title_elements = soup.find_all(['h1', 'h2', 'h3'], string=re.compile(title, re.I))
                logger.log(f'[BSTSRS] Found {len(title_elements)} title elements matching search', log_utils.LOGDEBUG)
                
                # Also check for any presence of the show name in the page
                if title.lower() in html.lower() or clean_title in html.lower():
                    logger.log(f'[BSTSRS] Title found in page content', log_utils.LOGDEBUG)
                    result = {
                        'title': title,
                        'year': year,
                        'url': search_url
                    }
                    results.append(result)
                    logger.log(f'[BSTSRS] Added search result: {result}', log_utils.LOGDEBUG)
                else:
                    logger.log(f'[BSTSRS] Title not found in page content', log_utils.LOGDEBUG)
                        
        except Exception as e:
            logger.log(f'[BSTSRS] Search error: {e}', log_utils.LOGERROR)
            
        logger.log(f'[BSTSRS] Search completed, found {len(results)} results', log_utils.LOGDEBUG)
        return results

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
        Generate TV show URL
        """
        clean_title = self._clean_title_for_url(video.title)
        
        # Handle special cases like the original scraper
        if video.title == 'House':
            clean_title = self._clean_title_for_url('House M.D.')
            
        return f'/show/{clean_title}'

    def _episode_url(self, video):
        """
        Generate episode URL following bstsrs URL pattern
        """
        original_title = video.title
        clean_title = self._clean_title_for_url(video.title)
        
        # Handle special cases
        if video.title == 'House':
            clean_title = self._clean_title_for_url('House M.D.')
            logger.log(f'[BSTSRS] Applied House -> House M.D. title mapping', log_utils.LOGDEBUG)
        
        # Format season and episode with leading zeros
        season_episode = f's{int(video.season):02d}e{int(video.episode):02d}'
        
        # Build URL: /show/{title-sXXeXX}/season/{season}/episode/{episode}
        url = f'/show/{clean_title}-{season_episode}/season/{int(video.season)}/episode/{int(video.episode)}'
        
        logger.log(f'[BSTSRS] Generated episode URL: {original_title} -> {url}', log_utils.LOGDEBUG)
        return url

    def resolve_link(self, link):
        """
        Resolve the final link if needed
        """
        return link