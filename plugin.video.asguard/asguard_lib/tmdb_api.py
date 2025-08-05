import requests
import xbmcgui
import logging
import xbmcaddon
import kodi
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
logger = logging.getLogger(__name__)


def authenticate_tmdb():
    url = 'https://api.themoviedb.org/3/authentication'
    params = {'api_key': TMDB_API_KEY}
    response = requests.get(url, params=params)
    return response.json()

def search_tmdb(query, page=1, overview=True):
    """
    Search TMDB for movies matching the query.
    
    :param query: The search query string.
    :param page: The page number to retrieve.
    :return: A list of search results.
    """
    params = {
        'api_key': TMDB_API_KEY,
        'query': query,
        'page': page,
        'overview': overview
    }
    try:
        response = requests.get(TMDB_SEARCH_URL, params=params)
        response.raise_for_status()  # Raise an exception for HTTP errors
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Request failed: {e}")
        return {}
    except ValueError as e:
        logger.error(f"Error parsing JSON: {e}")
        return {}

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
    try:
        response = requests.get(TMDB_SEARCH_TV_URL, params=params)
        response.raise_for_status()  # Raise an exception for HTTP errors
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Request failed: {e}")
        return {}
    except ValueError as e:
        logger.error(f"Error parsing JSON: {e}")
        return {}

def get_tv_details(tmdb_id, overview=True, trakt_id=None):
    """
    Get details of a specific TV show.
    
    :param tmdb_id: The TMDB ID of the TV show.
    :return: A dictionary with TV show details.
    """
    params = {
        'api_key': TMDB_API_KEY,
        'append_to_response': 'external_ids',
        'overview': overview
    }
    if trakt_id:
        params['trakt_id'] = trakt_id
    try:
        response = requests.get(TMDB_TV_DETAILS_URL.format(tmdb_id), params=params)
        response.raise_for_status()  # Raise an exception for HTTP errors
        return response.json()
    except requests.RequestException as e:
        logger.error(f"Request failed: {e}")
        return {}
    except ValueError as e:
        logger.error(f"Error parsing JSON: {e}")
        return {}

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
    :return: A list of episodes.
    """
    params = {
        'api_key': TMDB_API_KEY,
        'overview': overview
    }
    if trakt_id:
        params['trakt_id'] = trakt_id
    try:
        response = requests.get(TMDB_SEASON_DETAILS_URL.format(tmdb_id, season_number), params=params)
        response.raise_for_status()  # Raise an exception for HTTP errors
        return response.json().get('episodes', [])
    except requests.RequestException as e:
        logger.error(f"Request failed: {e}")
        return []
    except ValueError as e:
        logger.error(f"Error parsing JSON: {e}")
        return []


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
        logger.info("No search query entered.")
        return

    try:
        results = get_all_results(query)
        if not results:
            logger.info("No results found.")
            return
        
        for result in results:
            # Check for both 'title' (movies) and 'name' (TV shows)
            title = result.get('title') or result.get('name', 'N/A')
            release_date = result.get('release_date', 'N/A')
            overview = result.get('overview', 'N/A')
            logger.info(f"Title: {title}\nRelease Date: {release_date}\nOverview: {overview}\n")
    except Exception as e:
        logging.error(f"An error occurred: {e}")

def fetch_tmdb_metadata(imdb_id, trakt_id=None):
    url = f'{TMDB_API_URL}/find/{imdb_id}'
    params = {
        'api_key': TMDB_API_KEY,
        'external_source': 'imdb_id'
    }
    if trakt_id:
        params['trakt_id'] = trakt_id
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response.json()
    return None

def get_tv_episode_groups(tmdb_id):
    """Get all episode groups for a TV show"""
    url = TMDB_EPISODE_GROUPS_URL.format(tmdb_id)
    params = {'api_key': TMDB_API_KEY}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json().get('results', [])
    except Exception as e:
        logger.error(f"Error getting episode groups: {e}")
        return []

def get_episode_group_details(group_id):
    """Get detailed episodes for an episode group"""
    url = TMDB_EPISODE_GROUPS_DETAILS_URL.format(group_id)
    params = {'api_key': TMDB_API_KEY}
    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.error(f"Error getting group details: {e}")
        return None

if __name__ == "__main__":
    main()