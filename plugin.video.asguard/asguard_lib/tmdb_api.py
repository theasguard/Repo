import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import log_utils
import xbmcgui
import logging
import xbmcaddon
import kodi
import time
import threading
from functools import wraps
from asguard_lib import control

addon = xbmcaddon.Addon('plugin.video.asguard')

# Constants
TMDB_API_KEY = kodi.get_setting('tmdb_key')
BEARER_TOKEN = kodi.get_setting('tmdb_bearer_token')
TMDB_API_URL = 'https://api.themoviedb.org/3'
TMDB_SEARCH_URL = 'https://api.themoviedb.org/3/search/movie'
TMDB_SEARCH_TV_URL = 'https://api.themoviedb.org/3/search/tv'
TMDB_TV_DETAILS_URL = 'https://api.themoviedb.org/3/tv/{}'
TMDB_SEASON_DETAILS_URL = 'https://api.themoviedb.org/3/tv/{}/season/{}'
TMDB_EPISODE_GROUPS_URL = 'https://api.themoviedb.org/3/tv/{}/episode_groups'
TMDB_EPISODE_GROUPS_DETAILS_URL = 'https://api.themoviedb.org/3/tv/episode_group/{}'

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = log_utils.Logger.get_logger(__name__)

# Session and caching configuration
_session = None
_cache = {}
_cache_lock = threading.Lock()
_rate_limit_lock = threading.Lock()
_last_request_time = 0
CACHE_DURATION = 300  # 5 minutes
RATE_LIMIT_DELAY = 0.25  # 250ms between requests
REQUEST_TIMEOUT = 10  # 10 second timeout


def _get_session():
    """Get or create a requests session with proper configuration"""
    global _session
    if _session is None:
        _session = requests.Session()
        
        # Configure retry strategy
        try:
            # Try new parameter name (urllib3 >= 1.26.0)
            retry_strategy = Retry(
                total=3,
                status_forcelist=[429, 500, 502, 503, 504],
                allowed_methods=["HEAD", "GET", "OPTIONS"],
                backoff_factor=1
            )
        except TypeError:
            # Fallback to old parameter name (urllib3 < 1.26.0)
            retry_strategy = Retry(
                total=3,
                status_forcelist=[429, 500, 502, 503, 504],
                method_whitelist=["HEAD", "GET", "OPTIONS"],
                backoff_factor=1
            )
        
        # Mount adapter with retry strategy
        adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
        _session.mount("http://", adapter)
        _session.mount("https://", adapter)
        
        # Set default headers
        _session.headers.update({
            'User-Agent': 'Asguard-Kodi-Addon/1.0',
            'Accept': 'application/json'
        })
        
        logger.log('TMDB Session initialized with connection pooling', log_utils.LOGDEBUG)
    
    return _session

def _cache_key(url, params):
    """Generate cache key from URL and parameters"""
    import hashlib
    key_string = f"{url}_{str(sorted(params.items()) if params else '')}"
    return hashlib.md5(key_string.encode()).hexdigest()

def _get_cached_response(cache_key):
    """Get cached response if valid"""
    with _cache_lock:
        if cache_key in _cache:
            cached_data, timestamp = _cache[cache_key]
            if time.time() - timestamp < CACHE_DURATION:
                logger.log(f'Cache hit for key: {cache_key[:8]}...', log_utils.LOGDEBUG)
                return cached_data
            else:
                # Remove expired cache entry
                del _cache[cache_key]
                logger.log(f'Cache expired for key: {cache_key[:8]}...', log_utils.LOGDEBUG)
    return None

def _cache_response(cache_key, data):
    """Cache response data"""
    with _cache_lock:
        _cache[cache_key] = (data, time.time())
        logger.log(f'Cached response for key: {cache_key[:8]}...', log_utils.LOGDEBUG)
        
        # Clean up old cache entries (keep max 100 entries)
        if len(_cache) > 100:
            oldest_key = min(_cache.keys(), key=lambda k: _cache[k][1])
            del _cache[oldest_key]

def _rate_limited_request(url, params=None, timeout=REQUEST_TIMEOUT):
    """Make rate-limited request with caching"""
    global _last_request_time
    
    # Check cache first
    cache_key = _cache_key(url, params)
    cached_response = _get_cached_response(cache_key)
    if cached_response is not None:
        return cached_response
    
    # Rate limiting
    with _rate_limit_lock:
        current_time = time.time()
        time_since_last = current_time - _last_request_time
        if time_since_last < RATE_LIMIT_DELAY:
            sleep_time = RATE_LIMIT_DELAY - time_since_last
            logger.log(f'Rate limiting: sleeping {sleep_time:.3f}s', log_utils.LOGDEBUG)
            time.sleep(sleep_time)
        _last_request_time = time.time()
    
    # Make request
    session = _get_session()
    try:
        logger.log(f'Making TMDB request: {url}', log_utils.LOGDEBUG)
        response = session.get(url, params=params, timeout=timeout)
        response.raise_for_status()
        
        data = response.json()
        _cache_response(cache_key, data)
        return data
        
    except requests.exceptions.Timeout:
        logger.log(f'Request timeout for URL: {url}', log_utils.LOGERROR)
        return {}
    except requests.exceptions.RequestException as e:
        logger.log(f'Request failed: {e}', log_utils.LOGERROR)
        return {}
    except ValueError as e:
        logger.log(f'Error parsing JSON: {e}', log_utils.LOGERROR)
        return {}

def authenticate_tmdb():
    """Authenticate with TMDB API"""
    url = 'https://api.themoviedb.org/3/authentication'
    params = {'api_key': TMDB_API_KEY}
    return _rate_limited_request(url, params)

def search_tmdb(query, page=1, overview=True):
    """
    Search TMDB for movies matching the query.
    
    :param query: The search query string.
    :param page: The page number to retrieve.
    :param overview: Include overview in results.
    :return: A list of search results.
    """
    params = {
        'api_key': TMDB_API_KEY,
        'query': query,
        'page': page,
        'overview': overview
    }
    return _rate_limited_request(TMDB_SEARCH_URL, params)

def search_tmdb_tv(query, page=1):
    """
    Search TMDB for TV shows matching the query.
    
    :param query: The search query string.
    :param page: The page number to retrieve.
    :return: A list of search results.
    """
    params = {
        'api_key': TMDB_API_KEY,
        'query': query,
        'page': page
    }
    return _rate_limited_request(TMDB_SEARCH_TV_URL, params)

def get_tv_details(tmdb_id, overview=True, trakt_id=None):
    """
    Get details of a specific TV show.
    
    :param tmdb_id: The TMDB ID of the TV show.
    :param overview: Include overview in results.
    :param trakt_id: Optional Trakt ID for cross-reference.
    :return: A dictionary with TV show details.
    """
    params = {
        'api_key': TMDB_API_KEY,
        'append_to_response': 'external_ids',
        'overview': overview
    }
    if trakt_id:
        params['trakt_id'] = trakt_id
    
    url = TMDB_TV_DETAILS_URL.format(tmdb_id)
    return _rate_limited_request(url, params)

def get_tv_seasons(tmdb_id):
    """
    Get seasons of a specific TV show.
    
    :param tmdb_id: The TMDB ID of the TV show.
    :return: A list of seasons.
    """
    tv_details = get_tv_details(tmdb_id)
    return tv_details.get('seasons', [])

def get_season_episodes(tmdb_id, season_number, overview=True, trakt_id=None):
    """
    Get episodes of a specific season from TMDB.
    
    :param tmdb_id: The TMDB ID of the TV show.
    :param season_number: The season number.
    :param overview: Include overview in results.
    :param trakt_id: Optional Trakt ID for cross-reference.
    :return: A list of episodes.
    """
    params = {
        'api_key': TMDB_API_KEY,
        'overview': overview
    }
    if trakt_id:
        params['trakt_id'] = trakt_id
    
    url = TMDB_SEASON_DETAILS_URL.format(tmdb_id, season_number)
    result = _rate_limited_request(url, params)
    return result.get('episodes', []) if result else []


def get_all_results(query):
    """
    Retrieve all search results for a given query from TMDB.
    
    :param query: The search query string.
    :return: A list of all search results.
    """
    all_results = []
    page = 1
    while True:
        data = search_tmdb(query, page)
        results = data.get('results', [])
        if not results:
            break
        all_results.extend(results)
        if page >= data.get('total_pages', 1):
            break
        page += 1
    return all_results

def main():
    dialog = xbmcgui.Dialog()
    query = dialog.input("Enter the movie name to search", type=xbmcgui.INPUT_ALPHANUM)
    if not query:
        logger.log("No search query entered.", log_utils.LOGINFO)
        return

    try:
        results = get_all_results(query)
        if not results:
            logger.log("No results found.", log_utils.LOGINFO)
            return
        
        for result in results:
            # Check for both 'title' (movies) and 'name' (TV shows)
            title = result.get('title') or result.get('name', 'N/A')
            release_date = result.get('release_date', 'N/A')
            overview = result.get('overview', 'N/A')
            logger.log(f"Title: {title}\nRelease Date: {release_date}\nOverview: {overview}\n", log_utils.LOGINFO)
    except Exception as e:
        logger.log(f"An error occurred: {e}", log_utils.LOGERROR)

def fetch_tmdb_metadata(imdb_id, trakt_id=None):
    """Fetch TMDB metadata using IMDB ID"""
    url = f'{TMDB_API_URL}/find/{imdb_id}'
    params = {
        'api_key': TMDB_API_KEY,
        'external_source': 'imdb_id'
    }
    if trakt_id:
        params['trakt_id'] = trakt_id
    
    result = _rate_limited_request(url, params)
    return result if result else None

def get_tv_episode_groups(tmdb_id):
    """Get all episode groups for a TV show"""
    url = TMDB_EPISODE_GROUPS_URL.format(tmdb_id)
    params = {'api_key': TMDB_API_KEY}
    
    result = _rate_limited_request(url, params)
    return result.get('results', []) if result else []

def get_episode_group_details(group_id):
    """Get detailed episodes for an episode group"""
    url = TMDB_EPISODE_GROUPS_DETAILS_URL.format(group_id)
    params = {'api_key': TMDB_API_KEY}
    
    return _rate_limited_request(url, params)

def clear_cache():
    """Clear the TMDB API cache"""
    global _cache
    with _cache_lock:
        _cache.clear()
        logger.log('TMDB API cache cleared', log_utils.LOGINFO)

def get_cache_stats():
    """Get cache statistics"""
    with _cache_lock:
        return {
            'entries': len(_cache),
            'max_entries': 100,
            'cache_duration': CACHE_DURATION
        }

def get_tv_details_batch(tmdb_ids, overview=True):
    """
    Get TV details for multiple TMDB IDs efficiently.
    This reduces cascading API calls when the same show is requested multiple times.
    
    :param tmdb_ids: List of TMDB IDs or single TMDB ID
    :param overview: Include overview in results
    :return: Dictionary mapping tmdb_id -> show details
    """
    if isinstance(tmdb_ids, (str, int)):
        tmdb_ids = [tmdb_ids]
    
    results = {}
    uncached_ids = []
    
    # Check cache for each ID first
    for tmdb_id in tmdb_ids:
        params = {
            'api_key': TMDB_API_KEY,
            'append_to_response': 'external_ids',
            'overview': overview
        }
        url = TMDB_TV_DETAILS_URL.format(tmdb_id)
        cache_key = _cache_key(url, params)
        
        cached_response = _get_cached_response(cache_key)
        if cached_response is not None:
            results[str(tmdb_id)] = cached_response
        else:
            uncached_ids.append(tmdb_id)
    
    # Fetch uncached IDs
    for tmdb_id in uncached_ids:
        show_details = get_tv_details(tmdb_id, overview)
        if show_details:
            results[str(tmdb_id)] = show_details
    
    return results

if __name__ == "__main__":
    main()