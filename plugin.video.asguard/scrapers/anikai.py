import re
import urllib.parse
import kodi
import log_utils
import urllib.request
from bs4 import BeautifulSoup
import base64
import json
from asguard_lib import scraper_utils, control
from asguard_lib.utils2 import i18n
from asguard_lib.constants import VIDEO_TYPES, QUALITIES, FORCE_NO_MATCH
from . import scraper
try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)
import difflib
logger = log_utils.Logger.get_logger()

BASE_URL = 'https://animekai.bz'
SEARCH_URL = '/browser?keyword=%s'

class Scraper(scraper.Scraper):
    base_url = BASE_URL
    
    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url') or BASE_URL

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Anikai'

    def get_sources(self, video):
        sources = []
        query = self._build_query(video)
        search_url = scraper_utils.urljoin(self.base_url, SEARCH_URL % urllib.parse.quote_plus(query))
        # logger.log(f'Anikai Search URL: {search_url}', log_utils.LOGDEBUG)
        html = self._http_get(search_url, require_debrid=True)
        
        if not html or html == FORCE_NO_MATCH:
            return sources

        soup = BeautifulSoup(html, 'html.parser')
        # logger.log(f'Anikai Soup: {soup}', log_utils.LOGDEBUG)
        items = soup.find_all('div', class_='aitem')
        # logger.log(f'Anikai Items: {items}', log_utils.LOGDEBUG)

        def normalize_title(title):
            """Improved normalization with word boundary handling"""
            return re.sub(r'\W+', '', title.lower()).strip()
        
        search_title = normalize_title(video.title)
        # logger.log(f'Normalized Search Title: {search_title}', log_utils.LOGDEBUG)

        # Create a list of all potential matches for ranking
        potential_matches = []
        
        for item in items:
            title_elem = item.find('a', class_='title')
            if not title_elem:
                continue
            
            item_title = normalize_title(title_elem.get('title', ''))
            # logger.log(f'Normalized Item Title: {item_title}', log_utils.LOGDEBUG)

            # Calculate sequence match ratio
            seq_ratio = difflib.SequenceMatcher(None, search_title, item_title).ratio()
            # Calculate partial ratio for substring matches
            partial_ratio = difflib.SequenceMatcher(None, search_title, item_title).quick_ratio()
            
            # Use the highest of the two ratios
            match_ratio = max(seq_ratio, partial_ratio)
            # logger.log(f'Title Match Ratio: {match_ratio:.2f}', log_utils.LOGDEBUG)

            potential_matches.append((match_ratio, item))

        # Sort matches by highest ratio first
        potential_matches.sort(key=lambda x: x[0], reverse=True)
        # logger.log(f'Sorted Matches: {[(r, i.find("a", class_="title")["title"]) for r,i in potential_matches]}', 
        #            log_utils.LOGDEBUG)

        # Process only the top 3 matches to avoid false positives
        for match_ratio, item in potential_matches[:3]:
            if match_ratio < 0.5:  # Lowered threshold to account for longer titles
                continue
            
            # Get anime detail page URL
            detail_path = item.find('a', class_='poster')['href']
            # logger.log(f'Anikai Detail Path: {detail_path}', log_utils.LOGDEBUG)
            detail_url = scraper_utils.urljoin(self.base_url, detail_path)
            # logger.log(f'Anikai Detail URL: {detail_url}', log_utils.LOGDEBUG)

            episode_url = f"{detail_url}#ep={video.episode}"
            # logger.log(f'Anikai Episode URL: {episode_url}', log_utils.LOGDEBUG)
            
            # Fetch video player page
            player_html = self._http_get(episode_url, require_debrid=True)
            player_soup = BeautifulSoup(player_html, 'html.parser')
            # logger.log(f'Anikai Player Soup: {player_soup}', log_utils.LOGDEBUG)
            
            # Attempt multiple extraction methods
            sources = []
            
            # Method 1: Decode window.__$ payload
            if script := player_soup.find('script', text=re.compile(r'window\.__\$=')):
                match = re.search(r"window\.__\$='([^']+)", script.text)
                if match:
                    try:
                        encoded = match.group(1).replace('-', '+').replace('_', '/')
                        decoded = base64.b64decode(encoded).decode('utf-8')
                        if video_data := json.loads(decoded):
                            if embed_url := video_data.get('sources', [{}])[0].get('file'):
                                host = urllib.parse.urlparse(embed_url).netloc
                                sources.append({
                                    'url': embed_url,
                                    'host': host,
                                    'quality': QUALITIES.HD1080,
                                    'direct': False,
                                    'class': self,
                                    'debridonly': False,
                                    'multi-part': False
                                })
                    except Exception as e:
                        logger.log(f'Script payload decoding error: {str(e)}', log_utils.LOGERROR)

            # Method 2: data-meta attribute (existing method)
            if not sources and (main_entity := player_soup.find('div', itemprop='mainEntity')):
                if meta_data := main_entity.get('data-meta', ''):
                    try:
                        decoded_meta = base64.b64decode(meta_data).decode('utf-8')
                        if video_data := json.loads(decoded_meta):
                            if embed_url := video_data.get('sources', [{}])[0].get('file'):
                                host = urllib.parse.urlparse(embed_url).netloc
                                sources.append({
                                    'url': embed_url,
                                    'host': host,
                                    'quality': QUALITIES.HD1080,
                                    'direct': False,
                                    'class': self,
                                    'debridonly': False,
                                    'multi-part': False
                                })
                    except Exception as e:
                        logger.log(f'Meta data parsing error: {str(e)}', log_utils.LOGERROR)

            # Method 3: Fallback to iframe
            if not sources and (iframe := player_soup.find('iframe', src=True)):
                embed_url = iframe['src']
                host = urllib.parse.urlparse(embed_url).netloc
                sources.append({
                    'url': embed_url,
                    'host': host,
                    'quality': QUALITIES.HD1080,
                    'direct': False,
                    'class': self,
                    'debridonly': False,
                    'multi-part': False
                })

        return sources

    def _build_query(self, video):
        query = video.title
        if video.video_type == VIDEO_TYPES.EPISODE:
            query = f'{video.title}'
            logger.log(f'Anikai Episode query: {query}', log_utils.LOGDEBUG)
        elif video.video_type == VIDEO_TYPES.SEASON:
            # Use quotes to search for the entire season and include common batch terms
            query = f'"{video.title} Season {int(video.season):02d}"|"Complete"|"Batch"|"S{int(video.season):02d}"'
        elif video.video_type == VIDEO_TYPES.MOVIE:
            query += f' {video.year}'
        query = query.replace(' ', '+').replace('+-', '-')
        logger.log(f'Anikai Final query: {query}', log_utils.LOGDEBUG)
        return query 

    def _http_get(self, url, data=None, retry=True, allow_redirect=True, cache_limit=8, require_debrid=True):
        if require_debrid:
            if Scraper.debrid_resolvers is None:
                Scraper.debrid_resolvers = [resolver for resolver in resolveurl.choose_source(url) if resolver.isUniversal()]
            if not Scraper.debrid_resolvers:
                logger.log('%s requires debrid: %s' % (self.__module__, Scraper.debrid_resolvers), log_utils.LOGDEBUG)
                return ''
        try:
            headers = {'User-Agent': scraper_utils.get_ua()}
            req = urllib.request.Request(url, data=data, headers=headers)
            logger.log('Anikai Request: %s' % req, log_utils.LOGDEBUG)
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return response.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            logger.log(f'HTTP Error: {e.code} - {url}', log_utils.LOGWARNING)
        except urllib.error.URLError as e:
            logger.log(f'URL Error: {e.reason} - {url}', log_utils.LOGWARNING)
        return ''

    def _parse_quality(self, text):
        text = text.lower()
        if '4k' in text:
            return QUALITIES.HD4K
        elif '1080' in text or 'fhd' in text:
            return QUALITIES.HD1080
        elif '720' in text or 'hd' in text:
            return QUALITIES.HD720
        return QUALITIES.HIGH

    def resolve_link(self, link):
        try:
            # Clean URL parameters
            link = re.sub(r'\?.*', '', link)
            
            # Recursive resolution with depth limit
            return self._resolve_recursive(link, depth=0)
        except Exception as e:
            logger.log(f'Resolution error: {str(e)}', log_utils.LOGERROR)
            return link

    def _resolve_recursive(self, link, depth=0, max_depth=3):
        if depth >= max_depth:
            return link
            
        response = self._http_get(link, require_debrid=False)
        if not response:
            return link
            
        soup = BeautifulSoup(response, 'html.parser')
        
        # Check for video sources
        if script := soup.find('script', text=re.compile(r'var\s+video\s*=')):
            match = re.search(r"var\s+video\s*=\s*'([^']+)", script.text)
            if match:
                return match.group(1)
                
        # Check for iframes
        if iframe := soup.find('iframe', src=True):
            return self._resolve_recursive(iframe['src'], depth+1, max_depth)
            
        # Check for m3u8 playlists
        if m3u8_link := soup.find('a', href=re.compile(r'\.m3u8')):
            return m3u8_link['href']
            
        return link