"""
    Asguard Kodi Addon
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
import json
import re
import urllib.parse
import kodi
import log_utils
import http.cookiejar
import urllib.request
from asguard_lib import scraper_utils, control
from asguard_lib.utils2 import i18n
from asguard_lib.constants import VIDEO_TYPES, QUALITIES
from . import scraper
from bs4 import SoupStrainer
from bs4 import BeautifulSoup
try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)
logger = log_utils.Logger.get_logger()
BASE_URL = 'https://animepahe.com'
API_URL = 'https://animepahe.com/api'
QUALITY_MAP = {'360p': QUALITIES.MEDIUM, '480p': QUALITIES.HIGH, '720p': QUALITIES.HD720, '1080p': QUALITIES.HD1080}
ALL_EMBEDS = [
    'doodstream', 'filelions', 'filemoon', 'hd-1', 'hd-2', 'iga', 'kwik',
    'megaf', 'moonf', 'mp4upload', 'mp4u', 'mycloud', 'noads', 'noadsalt',
    'swish', 'streamtape', 'streamwish', 'vidcdn', 'vidhide', 'vidplay',
    'vidstream', 'yourupload', 'zto'
]

class Scraper(scraper.Scraper):
    base_url = BASE_URL
    session_cache = {}

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = BASE_URL

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'AnimePahe'

    def resolve_link(self, link):
        return link

    def get_sources(self, video):
        logger.log(f'AnimePahe scraper called for: {video.title}', log_utils.LOGDEBUG)
        sources = []
        session_id = self._get_session_id(video)
        if not session_id:
            logger.log('No session ID found for this video', log_utils.LOGDEBUG)
            return sources

        # Get episode session
        episode_session = self._get_episode_session(session_id, video)
        if not episode_session:
            logger.log('No episode session found for this video', log_utils.LOGDEBUG)
            return sources

        # Get streaming links
        sources = self._get_streaming_links(episode_session, video)
        if not sources:
            logger.log('No sources found for this video', log_utils.LOGDEBUG)
        return sources

    def _get_session_id(self, video):
        """Get the AnimePahe session ID for the show"""
        logger.log(f'Starting show session lookup for: {video.title}', log_utils.LOGDEBUG)
        # Check if we already have it cached
        if video.trakt_id in self.session_cache:
            logger.log(f'Session ID found in cache for {video.title}', log_utils.LOGDEBUG)
            return self.session_cache[video.trakt_id]

        # Search for the show
        query = self._build_query(video)
        logger.log(f'Query: {query}', log_utils.LOGDEBUG)
        params = {'m': 'search', 'q': query}
        url = scraper_utils.urljoin(API_URL, '?' + urllib.parse.urlencode(params))
        logger.log(f'Search URL: {url}', log_utils.LOGDEBUG)
        html = self._http_get(url, require_debrid=False, cache_limit=8)
        logger.log(f'API response: {html[:500]}...', log_utils.LOGDEBUG)
        
        try:
            data = json.loads(html)
            if data.get('data'):
                logger.log(f'Found {len(data["data"])} results', log_utils.LOGDEBUG)
                # Use fuzzy matching for titles
                normalized_title = scraper_utils.normalize_title(video.title)
                for item in data['data']:
                    item_title = scraper_utils.normalize_title(item['title'])
                    # Check for partial match since titles might differ
                    if normalized_title in item_title or item_title in normalized_title:
                        self.session_cache[video.trakt_id] = item['session']
                        logger.log(f'Session ID found for {video.title}: {item["session"]}', log_utils.LOGDEBUG)
                        return item['session']
                logger.log('No session ID found in API response', log_utils.LOGDEBUG)
        except Exception as e:
            logger.log(f'Error getting session ID: {str(e)}', log_utils.LOGERROR)
            logger.log(f'Response content: {html}', log_utils.LOGDEBUG)
        
        return None

    def _get_episode_session(self, session_id, video):
        logger.log(f'Getting episode session for S{video.season}E{video.episode}', log_utils.LOGDEBUG)
        """Get the episode session ID"""
        # Calculate page number based on episode number
        page = 1
        if int(video.episode) > 30:
            page = 1 + (int(video.episode) // 30)
            
        params = {
            'm': 'release',
            'id': session_id,
            'sort': 'episode_asc',
            'page': page
        }
        url = scraper_utils.urljoin(API_URL, '?' + urllib.parse.urlencode(params))
        logger.log(f'Episode URL: {url}', log_utils.LOGDEBUG)
        html = self._http_get(url, require_debrid=False, cache_limit=0.5)
        logger.log(f'Episode API response: {html[:500]}...', log_utils.LOGDEBUG)
        
        try:
            data = json.loads(html)
            if data.get('data'):
                for episode in data['data']:
                    if int(episode['episode']) == int(video.episode):
                        logger.log(f'Episode session found for {video.title}: {episode["session"]}', log_utils.LOGDEBUG)
                        return episode['session']
                logger.log('No episode session found in API response', log_utils.LOGDEBUG)
        except Exception as e:
            logger.log(f'Error getting episode session: {str(e)}', log_utils.LOGERROR)
            logger.log(f'Response content: {html}', log_utils.LOGDEBUG)
        
        return None

    def _get_streaming_links(self, episode_session, video):
        """Get streaming links for the episode"""
        sources = []
        play_url = scraper_utils.urljoin(self.base_url, f'/play/{episode_session}')
        logger.log(f'Play URL: {play_url}', log_utils.LOGDEBUG)
        html = self._http_get(play_url, require_debrid=False, cache_limit=0.5)
        logger.log(f'Play page response length: {len(html)}', log_utils.LOGDEBUG)
        
        # Extract sources from the page using the Otaku method
        mlink = SoupStrainer('div', {'id': 'resolutionMenu'})
        soup = BeautifulSoup(html, "html.parser", parse_only=mlink)
        items = soup.find_all('button')
        
        for item in items:
            stream_url = item.get('data-src')
            if stream_url:
                quality = item.get('data-resolution')
                quality = QUALITY_MAP.get(quality, QUALITIES.HIGH)
                host = urllib.parse.urlparse(stream_url).netloc
                sources.append({
                    'name': f'AnimePahe - {host}',
                    'label': f'AnimePahe - {quality}',
                    'url': stream_url,
                    'quality': quality,
                    'host': host,
                    'class': self,
                    'direct': False,
                    'debridonly': False
                })
        
        if not sources:
            logger.log('No sources found in play page', log_utils.LOGDEBUG)
            
        return sources

    def _build_query(self, video):
        """Build search query for the show"""
        # Clean title and remove season information
        title = re.sub(r'[Ss]eason\s*\d+', '', video.title).strip()
        return title

    def search(self, video_type, title, year, season=''):
        """Search for shows on AnimePahe"""
        results = []
        params = {'m': 'search', 'q': title}
        url = scraper_utils.urljoin(API_URL, '?' + urllib.parse.urlencode(params))
        html = self._http_get(url, require_debrid=False, cache_limit=8)
        
        try:
            data = json.loads(html)
            if data.get('data'):
                for item in data['data']:
                    results.append({
                        'title': item['title'],
                        'year': '',
                        'url': item['session']
                    })
        except Exception as e:
            logger.log(f'Error searching AnimePahe: {str(e)}', log_utils.LOGERROR)
        
        return results

    def _http_get(self, url, data=None, retry=True, allow_redirect=True, cache_limit=8, require_debrid=True):
        if require_debrid:
            if Scraper.debrid_resolvers is None:
                Scraper.debrid_resolvers = [resolver for resolver in resolveurl.relevant_resolvers() if resolver.isUniversal()]
            if not Scraper.debrid_resolvers:
                logger.log('%s requires debrid: %s' % (self.__module__, Scraper.debrid_resolvers), log_utils.LOGDEBUG)
                return ''
        try:
            headers = {
                'User-Agent': scraper_utils.get_ua(),
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': self.base_url
            }
            req = urllib.request.Request(url, data=data, headers=headers)
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                # Check for gzip encoding
                if response.info().get('Content-Encoding') == 'gzip':
                    import gzip
                    with gzip.GzipFile(fileobj=response) as f:
                        content = f.read()
                else:
                    content = response.read()
                    
                return content.decode('utf-8')
        except urllib.error.HTTPError as e:
            logger.log(f'HTTP Error: {e.code} - {url}', log_utils.LOGWARNING)
            # Try to read error response body
            try:
                error_content = e.read().decode('utf-8')
                logger.log(f'Error response: {error_content}', log_utils.LOGDEBUG)
            except:
                pass
        except urllib.error.URLError as e:
            logger.log(f'URL Error: {e.reason} - {url}', log_utils.LOGWARNING)
        except Exception as e:
            logger.log(f'General Error: {str(e)} - {url}', log_utils.LOGWARNING)
        return ''
