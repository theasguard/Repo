import re
import urllib.parse
import kodi
import log_utils
import urllib.request
from bs4 import BeautifulSoup
from asguard_lib import scraper_utils, control
from asguard_lib.utils2 import i18n
from asguard_lib.constants import VIDEO_TYPES, QUALITIES, FORCE_NO_MATCH
from . import scraper
try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)
logger = log_utils.Logger.get_logger()

class Scraper(scraper.Scraper):
    base_url = 'https://cinema.7xtream.com'
    player_url = 'https://7xtream.com/tmdb/movies_7xtream/series.php?tmdb_id=%s&season=%s&episode=%s'
    movie_pattern = '/movieDetail.html?id=%s'
    tv_pattern = 'https://cinema.7xtream.com/SeasonEpisode?/Z1-id=%s'
    
    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return '7xtream'

    def get_sources(self, video):
        from asguard_lib.trakt_api import Trakt_API
        sources = []
        try:
            if video.video_type == VIDEO_TYPES.MOVIE:
                details = Trakt_API().get_movie_details(video.trakt_id)
                tmdb_id = details['ids']['tmdb']
                movie_url = f'https://7xtream.com/movieDetail.html?id={tmdb_id}'
                logger.log('Searching for movie: %s' % movie_url, log_utils.LOGDEBUG)
            else:
                details = Trakt_API().get_show_details(video.trakt_id)
                tmdb_id = details['ids']['tmdb']
                search_url = self.player_url % (tmdb_id, video.season, video.episode)
                logger.log('Sevenxtream Searching for episode: %s' % search_url, log_utils.LOGDEBUG)

                url = search_url
                logger.log('Sevenxtream URL: %s' % url, log_utils.LOGDEBUG)
            if video.video_type == VIDEO_TYPES.MOVIE:
                url = movie_url

            response = self._http_get(url, cache_limit=1, require_debrid=True)
            logger.log('Sevenxtream Response: %s' % response, log_utils.LOGDEBUG)
            if not response or response == FORCE_NO_MATCH:
                return sources
            
            html = response

            soup = BeautifulSoup(html, 'html.parser')
            logger.log(f'Sevenxtream Soup: {soup}', log_utils.LOGDEBUG)
            tabs = soup.find_all('button', {'class': 'tab', 'onclick': True})
            logger.log(f'Tabs: {tabs}', log_utils.LOGDEBUG)
            
            for tab in tabs:
                match = re.search(r'showPlayer\(\d+,\s*"(.*?)"\)', tab['onclick'])
                if match:
                    embed_url = match.group(1).replace('&amp;', '&')
                    host = urllib.parse.urlparse(embed_url).netloc
                    
                    sources.append({
                        'url': embed_url,
                        'host': host,
                        'quality': QUALITIES.HD1080,
                        'direct': False,
                        'class': self,
                        'debridonly': True,
                        'multi-part': False,
                        'rating': None,
                        'views': None,
                    })

        except Exception as e:
            logger.log(f'Error in 7xtream scraper: {str(e)}', log_utils.LOGERROR)
        
        return sources
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
            logger.log('Sevenxtream Request: %s' % req, log_utils.LOGDEBUG)
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