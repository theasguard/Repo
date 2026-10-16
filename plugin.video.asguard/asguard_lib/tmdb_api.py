import requests, json, time, threading
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import log_utils
import xbmcgui
import simplecache
import xbmcaddon
import kodi
from functools import wraps
from asguard_lib import control
from asguard_lib.db_utils import DB_Connection

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
TMDB_API_V4_URL = 'https://api.themoviedb.org/4'
ANIME_KEYWORD_ID = 210024  # TMDB keyword ID for anime content

# Configure logging
logger = log_utils.Logger.get_logger(__name__)

db_connection = DB_Connection()

# Session and caching configuration
_session = None
_simple_cache = simplecache.SimpleCache()
_rate_limit_lock = threading.Lock()
_last_request_time = 0
CACHE_DURATION = 28800  # 8 Hours
RATE_LIMIT_DELAY = 0.15  # 150ms between requests
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
                allowed_methods=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"],
                backoff_factor=0.3
            )
        except TypeError:
            # Fallback to old parameter name (urllib3 < 1.26.0)
            retry_strategy = Retry(
                total=3,
                status_forcelist=[429, 500, 502, 503, 504],
                method_whitelist=["HEAD", "GET", "PUT", "DELETE", "OPTIONS", "TRACE", "POST"],
                backoff_factor=0.3
            )

        # Mount adapter with retry strategy
        adapter = HTTPAdapter(pool_connections=5, pool_maxsize=15, max_retries=retry_strategy)
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
    key_string = f"tmdb_api_{url}_{str(sorted(params.items()) if params else '')}"
    return hashlib.md5(key_string.encode()).hexdigest()

def _get_cached_response(cache_key):
    """Get cached response if valid"""
    cached_data = _simple_cache.get(cache_key)
    if cached_data is not None:
        logger.log(f'Cache hit for key: {cache_key[:8]}...', log_utils.LOGDEBUG)
        return cached_data
    logger.log(f'Cache miss for key: {cache_key[:8]}...', log_utils.LOGDEBUG)
    return None

def _cache_response(cache_key, data):
    """Cache response data"""
    import datetime
    expiration = datetime.timedelta(seconds=CACHE_DURATION)
    _simple_cache.set(cache_key, data, expiration=expiration)
    logger.log(f'Cached response for key: {cache_key[:8]}...', log_utils.LOGDEBUG)

def _rate_limited_request(url, params=None, timeout=REQUEST_TIMEOUT):
    """Make rate-limited request with caching (memory + DB)"""
    global _last_request_time

    # Build keys
    cache_key = _cache_key(url, params)
    params_data = json.dumps(params, sort_keys=True) if params else ''

    # 1) In-memory cache first
    cached_response = _get_cached_response(cache_key)
    if cached_response is not None:
        return cached_response

    # 2) DB cache
    try:
        cache_limit_hours = max(0.001, CACHE_DURATION / 3600.0)
        _created, _res_headers, html = db_connection.get_cached_url(url, data=params_data, cache_limit=cache_limit_hours)
        if html:
            try:
                data = html if isinstance(html, dict) else (json.loads(html) if isinstance(html, str) else {})
            except Exception:
                data = {}
            if data:
                _cache_response(cache_key, data)
                return data
    except Exception as e:
        logger.log(f'TMDB DB cache read error: {e}', log_utils.LOGDEBUG)

    # 3) Rate limiting then network
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
        # Write-through: memory + DB
        _cache_response(cache_key, data)
        try:
            db_connection.cache_url(url, json.dumps(data), data=params_data, res_header=list(response.headers.items()))
        except Exception as e:
            logger.log(f'TMDB DB cache write error: {e}', log_utils.LOGDEBUG)
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

def search_tmdb_tv(query, page=1, include_adult=False):
    """
    Search TMDB for TV shows matching the query.

    :param query: The search query string.
    :param page: The page number to retrieve.
    :param include_adult: Whether to include adult content in results.
    :return: A list of search results.
    """
    params = {
        'api_key': TMDB_API_KEY,
        'query': query,
        'page': page,
        'include_adult': include_adult,
        'language': 'en-US'
    }
    return _rate_limited_request(TMDB_SEARCH_TV_URL, params)

def search_tmdb_tv_multi_page(query, max_pages=3, include_adult=False):
    """
    Search TMDB for TV shows across multiple pages to get more results.

    :param query: The search query string.
    :param max_pages: Maximum number of pages to retrieve (default: 3).
    :param include_adult: Whether to include adult content in results.
    :return: A combined list of search results from all pages.
    """
    all_results = []

    for page in range(1, max_pages + 1):
        try:
            results = search_tmdb_tv(query, page, include_adult)
            if not results or 'results' not in results or not results['results']:
                break

            all_results.extend(results['results'])

            # If we've reached the last page, stop
            if page >= results.get('total_pages', 1):
                break

        except Exception as e:
            logger.log(f"Error fetching page {page} of search results: {e}", log_utils.LOGERROR)
            break

    return all_results

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
    result = _rate_limited_request(url, params)

    # If we have external IDs, try to get/save the Trakt ID mapping
    if result and 'external_ids' in result:
        ext_ids = result.get('external_ids', {})
        logger.log(f'External IDs: {ext_ids}', log_utils.LOGDEBUG)
        imdb_id = ext_ids.get('imdb_id')

        # If we have an IMDB ID but no Trakt ID passed in, try to find the Trakt ID
        if imdb_id and not trakt_id:
            # First check if we already have a mapping
            trakt_id = db_connection.get_trakt_id_by_tmdb_cached(tmdb_id)

            # If no mapping exists, we could try to fetch it from Trakt API
            # but for now we'll just cache any we find through other means
            if not trakt_id and 'trakt_id' in ext_ids:
                found_trakt_id = ext_ids.get('trakt_id')
                if found_trakt_id:
                    try:
                        db_connection.cache_tmdb_trakt_mapping(tmdb_id, found_trakt_id)
                        logger.log(f'Cached Trakt ID {found_trakt_id} for TMDB ID {tmdb_id} from external IDs', 
                            log_utils.LOGDEBUG)
                    except Exception as e:
                        logger.log(f'Failed to cache Trakt ID from external IDs: {e}', log_utils.LOGWARNING)

    return result

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
    _simple_cache.clear()
    logger.log('TMDB API cache cleared', log_utils.LOGINFO)

def get_cache_stats():
    """Get cache statistics"""
    # SimpleCache doesn't provide direct access to entry count
    # We return what information is available
    return {
        'cache_duration': CACHE_DURATION,
        'cache_type': 'SimpleCache (disk-based, persistent)'
    }

def cleanup():
    """Cleanup function to properly close the session and release resources"""
    global _session
    if _session is not None:
        try:
            _session.close()
            logger.log('TMDB Session closed properly', log_utils.LOGDEBUG)
        except Exception as e:
            logger.log(f'Error closing TMDB Session: {e}', log_utils.LOGERROR)
        finally:
            _session = None

def __del__():
    """Destructor to ensure cleanup is called when the module is unloaded"""
    cleanup()

def get_tv_details_batch(tmdb_ids, overview=True):
    """
    Get TV details for multiple TMDB IDs efficiently.
    This reduces cascading API calls when the same show is requested multiple times.

    :param tmdb_ids: List of TMDB IDs or single TMDB ID
    :param overview: Include overview in results
    :return: Dictionary mapping tmdb_id -> show details
    """
    if isinstance(tmdb_ids, (str, int)):
        tmdb_ids = [tmdb_id]

    results = {}
    uncached_ids = []

    if not tmdb_ids:
        return results

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

# ============ Anime Functions ============

def get_anime_movies_popular(page=1):
    """
    Get popular anime movies from TMDB.

    :param page: Page number to retrieve (default: 1)
    :return: Dictionary with anime movie results
    """
    params = {
        'api_key': TMDB_API_KEY,
        'page': page,
        'with_keywords': ANIME_KEYWORD_ID,
        'sort_by': 'popularity.desc',
        'language': 'en-US'
    }
    url = f'{TMDB_API_URL}/discover/movie'
    return _rate_limited_request(url, params)

def get_anime_movies_latest_releases(page=1):
    """
    Get latest anime movie releases from TMDB.

    :param page: Page number to retrieve (default: 1)
    :return: Dictionary with latest anime movie results
    """
    import datetime
    current_date = datetime.date.today()
    previous_date = current_date - datetime.timedelta(days=181)

    params = {
        'api_key': TMDB_API_KEY,
        'page': page,
        'with_keywords': ANIME_KEYWORD_ID,
        'sort_by': 'primary_release_date.desc',
        'release_date.gte': previous_date.strftime('%Y-%m-%d'),
        'release_date.lte': current_date.strftime('%Y-%m-%d'),
        'with_release_type': '4|5',
        'language': 'en-US'
    }
    url = f'{TMDB_API_URL}/discover/movie'
    return _rate_limited_request(url, params)

def get_anime_movies_by_genre(genre_id, page=1):
    """
    Get anime movies filtered by genre.

    :param genre_id: TMDB genre ID
    :param page: Page number to retrieve (default: 1)
    :return: Dictionary with anime movie results
    """
    params = {
        'api_key': TMDB_API_KEY,
        'page': page,
        'with_keywords': ANIME_KEYWORD_ID,
        'with_genres': genre_id,
        'sort_by': 'popularity.desc',
        'language': 'en-US'
    }
    url = f'{TMDB_API_URL}/discover/movie'
    return _rate_limited_request(url, params)

def get_anime_movies_by_year(year, page=1):
    """
    Get anime movies filtered by year.

    :param year: Year to filter by
    :param page: Page number to retrieve (default: 1)
    :return: Dictionary with anime movie results
    """
    params = {
        'api_key': TMDB_API_KEY,
        'page': page,
        'with_keywords': ANIME_KEYWORD_ID,
        'sort_by': 'popularity.desc',
        'primary_release_year': year,
        'certification_country': 'US',
        'language': 'en-US'
    }
    url = f'{TMDB_API_URL}/discover/movie'
    return _rate_limited_request(url, params)

def get_anime_tv_popular(page=1):
    """
    Get popular anime TV shows from TMDB.

    :param page: Page number to retrieve (default: 1)
    :return: Dictionary with anime TV show results
    """
    params = {
        'api_key': TMDB_API_KEY,
        'page': page,
        'with_keywords': ANIME_KEYWORD_ID,
        'sort_by': 'popularity.desc',
        'language': 'en-US'
    }
    url = f'{TMDB_API_URL}/discover/tv'
    return _rate_limited_request(url, params)

def get_anime_tv_premieres(page=1):
    """
    Get recent anime TV show premieres from TMDB.

    :param page: Page number to retrieve (default: 1)
    :return: Dictionary with anime TV show results
    """
    import datetime
    current_date = datetime.date.today()
    previous_date = current_date - datetime.timedelta(days=181)

    params = {
        'api_key': TMDB_API_KEY,
        'page': page,
        'with_keywords': ANIME_KEYWORD_ID,
        'sort_by': 'first_air_date.desc',
        'first_air_date.gte': previous_date.strftime('%Y-%m-%d'),
        'first_air_date.lte': current_date.strftime('%Y-%m-%d'),
        'language': 'en-US'
    }
    url = f'{TMDB_API_URL}/discover/tv'
    return _rate_limited_request(url, params)

def get_anime_tv_by_genre(genre_id, page=1):
    """
    Get anime TV shows filtered by genre.

    :param genre_id: TMDB genre ID
    :param page: Page number to retrieve (default: 1)
    :return: Dictionary with anime TV show results
    """
    params = {
        'api_key': TMDB_API_KEY,
        'page': page,
        'with_keywords': ANIME_KEYWORD_ID,
        'with_genres': genre_id,
        'sort_by': 'popularity.desc',
        'include_null_first_air_dates': False,
        'language': 'en-US'
    }
    url = f'{TMDB_API_URL}/discover/tv'
    return _rate_limited_request(url, params)

def get_anime_tv_by_year(year, page=1):
    """
    Get anime TV shows filtered by year.

    :param year: Year to filter by
    :param page: Page number to retrieve (default: 1)
    :return: Dictionary with anime TV show results
    """
    params = {
        'api_key': TMDB_API_KEY,
        'page': page,
        'with_keywords': ANIME_KEYWORD_ID,
        'sort_by': 'popularity.desc',
        'include_null_first_air_dates': False,
        'first_air_date_year': year,
        'language': 'en-US'
    }
    url = f'{TMDB_API_URL}/discover/tv'
    return _rate_limited_request(url, params)

# ============ List Management Functions (TMDB API v4) ============

def _get_v4_headers():
    """Get headers for TMDB API v4 requests with bearer token"""
    if not BEARER_TOKEN:
        logger.log('No TMDB bearer token configured', log_utils.LOGWARNING)
        return None
    return {
        'Authorization': f'Bearer {BEARER_TOKEN}',
        'Content-Type': 'application/json;charset=utf-8'
    }

def _make_v4_request(url, method='GET', params=None, data=None):
    """
    Make a request to TMDB API v4 with proper authentication.

    :param url: Full URL for the request
    :param method: HTTP method (GET, POST, PUT, DELETE)
    :param params: Query parameters
    :param data: Request body data (for POST/PUT/DELETE)
    :return: Response data or None on error
    """
    headers = _get_v4_headers()
    if not headers:
        return None

    session = _get_session()
    try:
        if method == 'GET':
            response = session.get(url, params=params, headers=headers, timeout=REQUEST_TIMEOUT)
        elif method == 'POST':
            response = session.post(url, params=params, json=data, headers=headers, timeout=REQUEST_TIMEOUT)
        elif method == 'PUT':
            response = session.put(url, params=params, json=data, headers=headers, timeout=REQUEST_TIMEOUT)
        elif method == 'DELETE':
            response = session.delete(url, params=params, json=data, headers=headers, timeout=REQUEST_TIMEOUT)
        else:
            logger.log(f'Unsupported HTTP method: {method}', log_utils.LOGERROR)
            return None

        response.raise_for_status()
        return response.json()

    except requests.exceptions.RequestException as e:
        logger.log(f'TMDB API v4 request failed: {e}', log_utils.LOGERROR)
        return None
    except ValueError as e:
        logger.log(f'Error parsing JSON response: {e}', log_utils.LOGERROR)
        return None

def get_user_watchlist(mediatype='movie', page=1):
    """
    Get user's watchlist from TMDB.

    :param mediatype: Media type ('movie' or 'tv')
    :param page: Page number to retrieve (default: 1)
    :return: Dictionary with watchlist items
    """
    account_id = kodi.get_setting('tmdb_account_id')
    if not account_id:
        logger.log('No TMDB account ID configured', log_utils.LOGWARNING)
        return None

    url = f'{TMDB_API_V4_URL}/account/{account_id}/watchlist/{mediatype}'
    params = {
        'page': page,
        'language': 'en-US',
        'sort_by': 'created_at.desc'
    }
    return _make_v4_request(url, 'GET', params=params)

def get_user_favorites(mediatype='movie', page=1):
    """
    Get user's favorites from TMDB.

    :param mediatype: Media type ('movie' or 'tv')
    :param page: Page number to retrieve (default: 1)
    :return: Dictionary with favorite items
    """
    account_id = kodi.get_setting('tmdb_account_id')
    if not account_id:
        logger.log('No TMDB account ID configured', log_utils.LOGWARNING)
        return None

    url = f'{TMDB_API_V4_URL}/account/{account_id}/favorite/{mediatype}'
    params = {
        'page': page,
        'language': 'en-US',
        'sort_by': 'created_at.desc'
    }
    return _make_v4_request(url, 'GET', params=params)

def add_to_watchlist(media_type, media_id, watchlist=True):
    """
    Add or remove an item from the user's watchlist.

    :param media_type: Media type ('movie' or 'tv')
    :param media_id: TMDB ID of the media
    :param watchlist: True to add, False to remove
    :return: Success status
    """
    account_id = kodi.get_setting('tmdb_account_id')
    if not account_id:
        logger.log('No TMDB account ID configured', log_utils.LOGWARNING)
        return False

    url = f'{TMDB_API_V4_URL}/account/{account_id}/watchlist'
    data = {
        'media_type': media_type,
        'media_id': int(media_id),
        'watchlist': watchlist
    }
    result = _make_v4_request(url, 'POST', data=data)
    return result is not None

def add_to_favorites(media_type, media_id, favorite=True):
    """
    Add or remove an item from the user's favorites.

    :param media_type: Media type ('movie' or 'tv')
    :param media_id: TMDB ID of the media
    :param favorite: True to add, False to remove
    :return: Success status
    """
    account_id = kodi.get_setting('tmdb_account_id')
    if not account_id:
        logger.log('No TMDB account ID configured', log_utils.LOGWARNING)
        return False

    url = f'{TMDB_API_V4_URL}/account/{account_id}/favorite'
    data = {
        'media_type': media_type,
        'media_id': int(media_id),
        'favorite': favorite
    }
    result = _make_v4_request(url, 'POST', data=data)
    return result is not None

def get_user_lists(page=1):
    """
    Get user's custom lists from TMDB.

    :param page: Page number to retrieve (default: 1)
    :return: Dictionary with user lists
    """
    account_id = kodi.get_setting('tmdb_account_id')
    if not account_id:
        logger.log('No TMDB account ID configured', log_utils.LOGWARNING)
        return None

    url = f'{TMDB_API_V4_URL}/account/{account_id}/lists'
    params = {'page': page}
    return _make_v4_request(url, 'GET', params=params)

def get_list_details(list_id):
    """
    Get details of a specific TMDB list.

    :param list_id: TMDB list ID
    :return: Dictionary with list details
    """
    url = f'{TMDB_API_V4_URL}/list/{list_id}'
    return _make_v4_request(url, 'GET')

def create_list(list_name, description='', public=True):
    """
    Create a new TMDB list.

    :param list_name: Name of the list
    :param description: Description of the list
    :param public: Whether the list is public
    :return: List ID if successful, None otherwise
    """
    url = f'{TMDB_API_V4_URL}/list'
    data = {
        'name': list_name,
        'description': description,
        'public': public,
        'iso_639_1': 'en',
        'iso_3166_1': 'US'
    }
    result = _make_v4_request(url, 'POST', data=data)
    return result.get('list_id') if result else None

def add_items_to_list(list_id, items):
    """
    Add items to a TMDB list.

    :param list_id: TMDB list ID
    :param items: List of items to add (each item should have 'media_type' and 'media_id')
    :return: Success status
    """
    url = f'{TMDB_API_V4_URL}/list/{list_id}/items'
    data = {'items': items}
    result = _make_v4_request(url, 'POST', data=data)
    return result is not None

def remove_items_from_list(list_id, items):
    """
    Remove items from a TMDB list.

    :param list_id: TMDB list ID
    :param items: List of items to remove (each item should have 'media_type' and 'media_id')
    :return: Success status
    """
    url = f'{TMDB_API_V4_URL}/list/{list_id}/items'
    data = {'items': items}
    result = _make_v4_request(url, 'DELETE', data=data)
    return result is not None

def update_list(list_id, name=None, description=None, public=None):
    """
    Update a TMDB list.

    :param list_id: TMDB list ID
    :param name: New name (optional)
    :param description: New description (optional)
    :param public: New public status (optional)
    :return: Success status
    """
    url = f'{TMDB_API_V4_URL}/list/{list_id}'
    data = {}
    if name is not None:
        data['name'] = name
    if description is not None:
        data['description'] = description
    if public is not None:
        data['public'] = public

    result = _make_v4_request(url, 'PUT', data=data)
    return result is not None

def clear_list(list_id):
    """
    Clear all items from a TMDB list.

    :param list_id: TMDB list ID
    :return: Success status
    """
    url = f'{TMDB_API_V4_URL}/list/{list_id}/clear'
    result = _make_v4_request(url, 'POST')
    return result is not None

def delete_list(list_id):
    """
    Delete a TMDB list.

    :param list_id: TMDB list ID
    :return: Success status
    """
    url = f'{TMDB_API_V4_URL}/list/{list_id}'
    result = _make_v4_request(url, 'DELETE')
    return result is not None

def check_item_status(list_id, media_type, media_id):
    """
    Check if an item is in a TMDB list.

    :param list_id: TMDB list ID
    :param media_type: Media type ('movie' or 'tv')
    :param media_id: TMDB ID of the media
    :return: Item status or None on error
    """
    url = f'{TMDB_API_V4_URL}/list/{list_id}/item_status'
    params = {
        'media_type': media_type,
        'media_id': int(media_id)
    }
    return _make_v4_request(url, 'GET', params=params)

if __name__ == "__main__":
    main()
