from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
import six
from urllib3.util import Retry
import urllib.request
from bs4 import BeautifulSoup
from asguard_lib.db_utils import DB_Connection
import requests
import json
import kodi, log_utils, utils
import xbmcgui
import xbmcaddon


logger = log_utils.Logger.get_logger(__name__)
# Get the TMDb API key from Kodi add-on settings
addon = xbmcaddon.Addon()

db_connection = DB_Connection()
TMDB_API_KEY = addon.getSetting('tmdb_key')
# TMDb API endpoint
TMDB_API_URL = 'https://api.themoviedb.org/3'
UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'


class SessionManager:
    _instance = None
    _session = None
    _executor = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
            cls._initialized = True
        return cls._instance
    
    def _initialize(self):
        """Initialize shared session and thread pool"""
        cls = SessionManager
        
        # Create shared session with connection pooling
        cls._session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[429, 500, 502, 503, 504],
        )
        
        # Mount adapter with connection pooling
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=30,
            pool_maxsize=30,
            pool_block=False
        )
        
        cls._session.mount('http://', adapter)
        cls._session.mount('https://', adapter)
        
        # Create shared thread pool with reduced workers
        cls._executor = ThreadPoolExecutor(max_workers=20)
    
    @classmethod
    def get_session(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance._session
    
    @classmethod
    def get_executor(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance._executor
    
    @classmethod
    def close(cls):
        """Clean up resources"""
        if cls._instance:
            if cls._instance._executor:
                cls._instance._executor.shutdown(wait=False)
            if cls._instance._session:
                cls._instance._session.close()
            cls._instance = None
            cls._initialized = False

class Scraper(object):
    protocol = 'http://'
    def __init__(self):
        self.session = self._create_session()
        self.executor = self._create_executor()
        self.protocol = 'http://'
    
    def _create_session(self):
        """No longer needed - using shared session"""
        return SessionManager.get_session()
    
    def _create_executor(self):
        """No longer needed - using shared executor"""
        return SessionManager.get_executor()
    
    def _clean_art(self, art_dict):
        new_dict = {}
        for key in art_dict:
            if art_dict[key]:
                scheme, netloc, path, params, query, fragment = urllib.parse.urlparse(art_dict[key])
                new_dict[key] = urllib.parse.urlunparse((scheme, netloc, urllib.parse.quote(path), params, query, fragment))
        return new_dict
    

    
    def _get_url(self, url, params=None, data=None, headers=None, cache_limit=1, is_binary=False):
        """Get URL with improved performance using requests library"""
        if headers is None: 
            headers = {}
        
        # Prepare data if needed
        if data is not None:
            if isinstance(data, six.string_types):
                data = data
                logger.log('String image Data: %s' % (data), log_utils.LOGDEBUG)
            else:
                data = urllib.parse.urlencode(data, True)
                logger.log('Urlencode image Data: %s' % (data), log_utils.LOGDEBUG)
        
        # Build full URL if needed
        if not url.startswith('http'):
            url = '%s%s%s' % (self.protocol, self.BASE_URL, url)
            logger.log('Image Scrape URL: %s' % (url), log_utils.LOGDEBUG)
        
        # Add query parameters
        if params: 
            url += '?' + urllib.parse.urlencode(params)
            logger.log('Image Scrape URL with params: %s' % (url), log_utils.LOGDEBUG)
        # Check if this is a binary file request (ZIP, images, etc.)
        if url.lower().endswith('.zip') or any(ext in url.lower() for ext in ['.jpg', '.jpeg', '.png', '.gif']):
            is_binary = True
        # Check cache first
        _created, cached_headers, html = db_connection.get_cached_url(url, data, cache_limit=cache_limit, is_binary=is_binary)
        if html:
            logger.log('Using Cached result for: %s' % (url))
            result = html
            res_headers = dict(cached_headers)
            logger.log('Result: %s' % (result), log_utils.LOGDEBUG)
        else:
            try:
                # Set default headers
                headers.setdefault('Accept-Encoding', 'gzip')
                headers.setdefault('Connection', 'keep-alive')
                headers.setdefault('User-Agent', UA)
                
                logger.log('+++Image Scraper Call: %s, header: %s, data: %s cache_limit: %s' % 
                          (url, headers, data, cache_limit), log_utils.LOGDEBUG)
                
                # Use requests session with timeout
                response = self.session.get(
                    url, 
                    data=data, 
                    headers=headers, 
                    timeout=(3.05, 6)  # (connect timeout, read timeout)
                )
                response.raise_for_status()  # Raise exception for 4XX/5XX status codes
                
                # Get response content and headers
                result = response.content
                res_headers = dict(response.headers)
                
                # Cache the result
                db_connection.cache_url(url, result, data, res_header=res_headers)
                
            except requests.exceptions.Timeout:
                logger.log('Image Scraper Timeout: %s' % (url))
                return {}
            except requests.exceptions.HTTPError as e:
                if e.response.status_code != 404:
                    logger.log('HTTP Error (%s) during image scraper http get: %s' % (e, url), log_utils.LOGWARNING)
                return {}
            except Exception as e:
                logger.log('Error (%s) during image scraper http get: %s' % (str(e), url), log_utils.LOGWARNING)
                return {}
        
        try:
            # Process response based on content type
            content_type = res_headers.get('content-type', '').lower()
            if 'application/json' in content_type:
                return_data = utils.json_loads_as_str(result)
            else:
                # Try to parse as JSON, fallback to raw result
                try:
                    return_data = utils.json_loads_as_str(result)
                except ValueError:
                    return_data = result
        except ValueError:
            return_data = ''
            if result:
                logger.log('Invalid JSON API Response: %s - |%s|' % (url, return_data), log_utils.LOGERROR)
        
        return return_data
    
    def get_multiple_urls(self, url_list, params=None, headers=None, cache_limit=1):
        """
        Fetch multiple URLs concurrently using ThreadPoolExecutor
        
        Args:
            url_list: List of URLs to fetch
            params: Optional query parameters for all URLs
            headers: Optional headers for all URLs
            cache_limit: Cache duration in hours
            
        Returns:
            Dictionary mapping URLs to their responses
        """
        results = {}
        
        # Create a list of futures for each URL
        futures = {
            self.executor.submit(
                self._get_url, 
                url, 
                params, 
                None,  # No data for GET requests
                headers, 
                cache_limit
            ): url for url in url_list
        }
        
        # Process completed futures as they complete
        for future in as_completed(futures):
            url = futures[future]
            try:
                results[url] = future.result()
            except Exception as e:
                logger.log('Error fetching %s: %s' % (url, str(e)), log_utils.LOGWARNING)
                results[url] = {}
        
        return results
class IMDBScraper(Scraper):
    BASE_URL = 'https://www.imdb.com'
    UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'

    def _fetch(self, url):
        headers = {'User-Agent': self.UA, 'Accept-Language': 'en-US,en;q=0.9'}
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read()

    def _extract_poster(self, html_bytes):
        try:
            soup = BeautifulSoup(html_bytes, 'html.parser')
            meta = soup.find('meta', property='og:image')
            if meta and meta.get('content'):
                return meta['content']
            for script in soup.find_all('script', type='application/ld+json'):
                try:
                    data = json.loads(script.string or '')
                except Exception:
                    continue
                image = data.get('image')
                if isinstance(image, str):
                    return image
                if isinstance(image, dict):
                    url = image.get('url')
                    if url:
                        return url
                if isinstance(image, list) and image:
                    if isinstance(image[0], str):
                        return image[0]
                    if isinstance(image[0], dict) and image[0].get('url'):
                        return image[0]['url']
        except Exception as e:
            logger.log(f'IMDb poster parse error: {e}', log_utils.LOGDEBUG)
        return None

    def _extract_img_from_container(self, container):
        img = container.find('img')
        if not img:
            return None
        for attr in ('srcset', 'data-srcset'):
            srcset = img.get(attr)
            if srcset:
                try:
                    parts = [p.strip().split(' ')[0] for p in srcset.split(',') if p.strip()]
                    if parts:
                        return parts[-1]
                except Exception:
                    pass
        for attr in ('src', 'data-src', 'loadlate'):
            if img.get(attr):
                return img[attr]
        return None

    def get_movie_images(self, imdb_id):
        art = {}
        if isinstance(imdb_id, dict):
            imdb_id = imdb_id.get('imdb')
        if not imdb_id:
            return art
        try:
            html = self._fetch(f'{self.BASE_URL}/title/{imdb_id}/')
            poster = self._extract_poster(html)
            if poster:
                art['poster'] = poster
        except Exception as e:
            logger.log(f'IMDb movie fetch error: {e}', log_utils.LOGWARNING)
        return self._clean_art(art)

    def get_tvshow_images(self, ids):
        art = {}
        imdb_id = ids.get('imdb') if isinstance(ids, dict) else ids
        if not imdb_id:
            return art
        try:
            html = self._fetch(f'{self.BASE_URL}/title/{imdb_id}/')
            poster = self._extract_poster(html)
            if poster:
                art['poster'] = poster
        except Exception as e:
            logger.log(f'IMDb tvshow fetch error: {e}', log_utils.LOGWARNING)
        return self._clean_art(art)

    def get_episode_images(self, ids, season, episode):
        art = {}
        imdb_id = ids.get('imdb') if isinstance(ids, dict) else ids
        if not imdb_id:
            return art
        try:
            html = self._fetch(f'{self.BASE_URL}/title/{imdb_id}/episodes?season={season}')
            soup = BeautifulSoup(html, 'html.parser')
            candidate = None
            for container in soup.find_all(['div', 'li', 'section']):
                epnum = container.get('data-episode-number')
                if epnum and str(epnum).strip() == str(int(episode)):
                    candidate = container
                    break
                badge = container.find(attrs={'data-testid': 'episode-item-episode-number'})
                if badge and badge.get_text(strip=True).isdigit() and int(badge.get_text(strip=True)) == int(episode):
                    candidate = container
                    break
                meta_num = container.find('meta', itemprop='episodeNumber')
                if meta_num and meta_num.get('content') and int(meta_num['content']) == int(episode):
                    candidate = container
                    break
            if candidate:
                img_url = self._extract_img_from_container(candidate)
                if img_url:
                    art['thumb'] = img_url
        except Exception as e:
            logger.log(f'IMDb episode fetch/parse error: {e}', log_utils.LOGWARNING)
        return self._clean_art(art)

class IMDbDetails:
    def __init__(self):
        self.api_key = TMDB_API_KEY
        self._movie_genres = None
        self._tv_genres = None

    def _get_movie_genres(self):
        """Fetch movie genres from TMDb and cache them"""
        if self._movie_genres is None:
            url = f'{TMDB_API_URL}/genre/movie/list?api_key={self.api_key}'
            response = requests.get(url)
            if response.status_code == 200:
                data = json.loads(response.text)
                self._movie_genres = {genre['id']: genre['name'] for genre in data['genres']}
            else:
                self._movie_genres = {}
        return self._movie_genres

    def _get_tv_genres(self):
        """Fetch TV show genres from TMDb and cache them"""
        if self._tv_genres is None:
            url = f'{TMDB_API_URL}/genre/tv/list?api_key={self.api_key}'
            response = requests.get(url)
            if response.status_code == 200:
                data = json.loads(response.text)
                self._tv_genres = {genre['id']: genre['name'] for genre in data['genres']}
            else:
                self._tv_genres = {}
        return self._tv_genres

    def get_movie_details(self, imdb_id):
        url = f'{TMDB_API_URL}/find/{imdb_id}?api_key={self.api_key}&external_source=imdb_id'
        response = requests.get(url)
        if response.status_code == 200:
            data = json.loads(response.text)
            if data['movie_results']:
                movie = data['movie_results'][0]
                return {
                    'title': movie['title'],
                    'year': movie['release_date'].split('-')[0],
                    'imdb_id': imdb_id,
                    'genre': ', '.join([self._get_movie_genres().get(gid, str(gid)) for gid in movie.get('genre_ids', [])]),
                    'plot': movie['overview'],
                    'poster': f"https://image.tmdb.org/t/p/w500{movie['poster_path']}",
                    'rating': movie['vote_average'],
                    'director': 'N/A',  # TMDb does not provide director info in this endpoint
                    'cast': 'N/A'  # TMDb does not provide cast info in this endpoint
                }
        return None

    def get_tv_show_details(self, imdb_id):
        url = f'{TMDB_API_URL}/find/{imdb_id}?api_key={self.api_key}&external_source=imdb_id'
        response = requests.get(url)
        if response.status_code == 200:
            data = json.loads(response.text)
            if data['tv_results']:
                show = data['tv_results'][0]
                return {
                    'title': show['name'],
                    'year': show['first_air_date'].split('-')[0],
                    'imdb_id': imdb_id,
                    'genre': ', '.join([self._get_tv_genres().get(gid, str(gid)) for gid in show.get('genre_ids', [])]),
                    'plot': show['overview'],
                    'poster': f"https://image.tmdb.org/t/p/w500{show['poster_path']}",
                    'rating': show['vote_average'],
                    'creator': 'N/A',  # TMDb does not provide creator info in this endpoint
                    'cast': 'N/A'  # TMDb does not provide cast info in this endpoint
                }
        return None

    def get_episode_details(self, imdb_id, season, episode):
        # First, get the TV show ID from the IMDb ID
        url = f'{TMDB_API_URL}/find/{imdb_id}?api_key={self.api_key}&external_source=imdb_id'
        response = requests.get(url)
        if response.status_code == 200:
            data = json.loads(response.text)
            if data['tv_results']:
                show_id = data['tv_results'][0]['id']
                # Now, get the episode details using the show ID, season, and episode number
                url = f'{TMDB_API_URL}/tv/{show_id}/season/{season}/episode/{episode}?api_key={self.api_key}'
                response = requests.get(url)
                if response.status_code == 200:
                    data = json.loads(response.text)
                    return {
                        'title': data['name'],
                        'season': season,
                        'episode': episode,
                        'imdb_id': imdb_id,
                        'air_date': data['air_date'],
                        'plot': data['overview'],
                        'rating': data['vote_average'],
                        'director': 'N/A',  # TMDb does not provide director info in this endpoint
                        'cast': ', '.join([cast['name'] for cast in data['guest_stars']])
                    }
        return None

# Example usage
imdb_details = IMDbDetails()
movie_details = imdb_details.get_movie_details('tt0111161')  # Replace with your movie IMDb ID
tv_show_details = imdb_details.get_tv_show_details('tt0903747')  # Replace with your TV show IMDb ID
episode_details = imdb_details.get_episode_details('tt0903747', 1, 1)  # Replace with your TV show IMDb ID, season, and episode

# Print the results
print('Movie Details:')
print(json.dumps(movie_details, indent=4))
print('TV Show Details:')
print(json.dumps(tv_show_details, indent=4))
print('Episode Details:')
print(json.dumps(episode_details, indent=4))