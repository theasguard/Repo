"""
    Asguard Addon
    Copyright (C) 2026 MrBlamo

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

# Standard library imports
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

# Kodi-specific imports
import xbmcaddon

# Local module imports
import kodi, log_utils
from asguard_lib.constants import VIDEO_TYPES
from asguard_lib.db_utils import DB_Connection

logger = log_utils.Logger.get_logger(__name__)

# Import settings and defaults from the main image_scraper
try:
    from .image_scraper import (
        DEFAULT_FANART, PLACE_POSTER, BG_ENABLED, POSTER_ENABLED, 
        BANNER_ENABLED, CLEARART_ENABLED, THUMB_ENABLED,
        fanart_scraper, omdb_scraper, tvmaze_scraper, 
        tvdb_scraper, tmdb_scraper, imdb_scraper
    )
except ImportError:
    # Fallback if running standalone
    DEFAULT_FANART = 'default_fanart.jpg'
    PLACE_POSTER = 'place_poster.png'
    BG_ENABLED = True
    POSTER_ENABLED = True
    BANNER_ENABLED = True
    CLEARART_ENABLED = True
    THUMB_ENABLED = True
    fanart_scraper = None
    omdb_scraper = None
    tvmaze_scraper = None
    tvdb_scraper = None
    tmdb_scraper = None
    imdb_scraper = None

db_connection = DB_Connection()

# Define scraper priority order (higher priority = better quality images)
# This ensures higher quality sources aren't overwritten by lower quality ones
SCRAPER_PRIORITY = {
    'fanarttv': 5,      # FanartTV - highest priority for fanart, clearart, etc.
    'tvdb': 4,          # TVDB - high priority for TV shows
    'tmdb': 3,          # TMDB - good quality, but lower than FanartTV/TVDB
    'tvmaze': 2,        # TVMaze - medium priority
    'omdb': 1,          # OMDB - lowest priority (often has lower quality or in-theater posters)
    'imdb': 1           # IMDB - lowest priority
}

# Define which art types each scraper is best at
SCRAPER_SPECIALTIES = {
    'fanarttv': ['fanart', 'clearart', 'clearlogo', 'banner'],
    'tvdb': ['poster', 'banner', 'thumb'],
    'tmdb': ['fanart', 'poster'],
    'tvmaze': ['thumb', 'poster'],
    'omdb': ['poster'],
    'imdb': ['poster']
}


def merge_scraper_results(results, art_dict, video_type):
    """
    Merge results from multiple scrapers using priority-based system.

    Higher priority scrapers (FanartTV, TVDB) won't be overwritten by lower priority ones (OMDB, IMDB).
    Only missing or lower-priority art types will be updated.

    Args:
        results: Dictionary of scraper results {scraper_name: art_dict}
        art_dict: Current art dictionary to update
        video_type: Type of video (MOVIE, TVSHOW, SEASON, EPISODE)

    Returns:
        Updated art_dict with merged results
    """
    # Sort scrapers by priority (highest first)
    sorted_scrapers = sorted(
        results.keys(),
        key=lambda x: SCRAPER_PRIORITY.get(x, 0),
        reverse=True
    )

    # Track which art types we've already set from high-priority sources
    set_art_types = set()

    # First pass: process high-priority scrapers
    for scraper_name in sorted_scrapers:
        result = results.get(scraper_name, {})
        if not result:
            continue

        # For each art type in the result
        for art_type, art_url in result.items():
            if not art_url:
                continue

            # Skip if this art type is already set from a higher priority scraper
            if art_type in set_art_types:
                continue

            # Check if this scraper is good at this art type
            specialties = SCRAPER_SPECIALTIES.get(scraper_name, [])
            is_specialty = art_type in specialties

            # Only set if:
            # 1. Art type is not yet in art_dict, OR
            # 2. Current value is a placeholder (DEFAULT_FANART or PLACE_POSTER), OR
            # 3. This scraper specializes in this art type
            if (art_type not in art_dict or 
                art_dict[art_type] in [DEFAULT_FANART, PLACE_POSTER, None] or
                is_specialty):
                art_dict[art_type] = art_url
                set_art_types.add(art_type)
                logger.log(f'Set {art_type} from {scraper_name}: {art_url}', log_utils.LOGDEBUG)

    return art_dict


def scrape_images(video_type, video_ids, season='', episode='', cached=True):
    """
    Fetch images from multiple scrapers in parallel for improved performance.

    This version executes multiple scraper calls concurrently instead of sequentially,
    significantly reducing wait time when images are not cached.

    Args:
        video_type: Type of video (MOVIE, TVSHOW, SEASON, EPISODE)
        video_ids: Dictionary containing various IDs (trakt, tmdb, imdb, tvdb, etc.)
        season: Season number (for TV shows)
        episode: Episode number (for episodes)
        cached: Whether to check cache first

    Returns:
        Dictionary containing image URLs for different art types
    """
    art_dict = {
        'banner': None,
        'fanart': DEFAULT_FANART,
        'thumb': None,
        'poster': PLACE_POSTER,
        'clearart': None,
        'clearlogo': None
    }

    trakt_id = video_ids.get('trakt')
    object_type = VIDEO_TYPES.MOVIE if video_type == VIDEO_TYPES.MOVIE else VIDEO_TYPES.TVSHOW

    # Check cache first
    if cached:
        cached_art = db_connection.get_cached_images(object_type, trakt_id, season, episode)
        if cached_art:
            art_dict.update(cached_art)
            return art_dict
    else:
        cached_art = {}

    # If not in cache, fetch from scrapers in parallel
    if not cached_art:
        global fanart_scraper, omdb_scraper, tvmaze_scraper, tvdb_scraper, tmdb_scraper, imdb_scraper

        # Define scraper tasks based on video type
        scraper_tasks = []

        if video_type == VIDEO_TYPES.MOVIE:
            # Movie scraping tasks
            if POSTER_ENABLED:
                scraper_tasks.append(('fanarttv', fanart_scraper.get_movie_images, [video_ids]))

            # TMDB scraper (for fanart and poster if needed)
            scraper_tasks.append(('tmdb', tmdb_scraper.get_movie_images, [video_ids, ['fanart', 'poster']]))

            # OMDB scraper (for poster if needed)
            scraper_tasks.append(('omdb', omdb_scraper.get_images, [video_ids]))

        elif video_type == VIDEO_TYPES.TVSHOW:
            # TV Show scraping tasks
            scraper_tasks.append(('fanarttv', fanart_scraper.get_tvshow_images, [video_ids]))
            scraper_tasks.append(('tvdb', tvdb_scraper.get_tvshow_images, [video_ids, ['fanart', 'poster', 'banner']]))
            scraper_tasks.append(('tmdb', tmdb_scraper.get_tmdbshow_images, [video_ids, ['fanart', 'poster']]))
            # scraper_tasks.append(('omdb', omdb_scraper.get_images, [video_ids]))

        elif video_type == VIDEO_TYPES.SEASON:
            # Season scraping - first get TV show images, then season-specific images
            tvshow_art = scrape_images(VIDEO_TYPES.TVSHOW, video_ids, cached=cached)
            art_dict.update(tvshow_art)

            # Get season images from both scrapers in parallel
            season_tasks = [
                ('fanart_season', fanart_scraper.get_season_images, [video_ids]),
                ('tvdb_season', tvdb_scraper.get_season_images, [video_ids])
            ]

            season_results = _execute_scraper_tasks(season_tasks)

            # Process season results using priority-based merge
            fanart_season_art = season_results.get('fanart_season', {})
            tvdb_season_art = season_results.get('tvdb_season', {})

            # Merge season art with TVDB as fallback (FanartTV has priority)
            for key in tvdb_season_art:
                season_art_dict = fanart_season_art.get(key, {})
                # Merge TVDB results into FanartTV results respecting priorities
                season_art_dict = merge_scraper_results(
                    {'tvdb': tvdb_season_art[key]},
                    season_art_dict,
                    video_type
                )
                fanart_season_art[key] = season_art_dict

            # Cache all season images
            for key in fanart_season_art:
                temp_dict = art_dict.copy()
                temp_dict.update(fanart_season_art[key])
                db_connection.cache_images(object_type, trakt_id, temp_dict, key)

            # Update art_dict with current season
            art_dict.update(fanart_season_art.get(str(season), {}))

            # Cache and return
            db_connection.cache_images(object_type, trakt_id, art_dict, season, episode)
            return art_dict

        elif video_type == VIDEO_TYPES.EPISODE:
            # Episode scraping - first get TV show images
            tvshow_art = scrape_images(VIDEO_TYPES.TVSHOW, video_ids, cached=cached)
            art_dict.update(tvshow_art)

            # Episode-specific scraping tasks
            episode_tasks = [
                ('tvdb_ep', tvdb_scraper.get_episode_images, [video_ids, season, episode]),
                ('tmdb_ep', tmdb_scraper.get_tmdbepisode_images, [video_ids, season, episode, ['fanart', 'poster']]),
                ('tvmaze_ep', tvmaze_scraper.get_episode_images, [video_ids, season, episode])
            ]

            episode_results = _execute_scraper_tasks(episode_tasks)

            # Merge episode results using priority-based system
            art_dict = merge_scraper_results(episode_results, art_dict, video_type)

            # Cache and return
            db_connection.cache_images(object_type, trakt_id, art_dict, season, episode)
            return art_dict

        # Execute scraper tasks for MOVIE and TVSHOW types
        if scraper_tasks:
            results = _execute_scraper_tasks(scraper_tasks)
            logger.log(f'Finished {video_type} scraping |{results}|', log_utils.LOGDEBUG)

            # Merge results using priority-based system
            art_dict = merge_scraper_results(results, art_dict, video_type)

            # Apply fallbacks
            _apply_fallbacks(art_dict, video_type)

            # Cache the final results
            db_connection.cache_images(object_type, trakt_id, art_dict, season, episode)

    return art_dict


def _execute_scraper_tasks(tasks, max_workers=4, timeout=15):
    """
    Execute multiple scraper tasks in parallel.

    Args:
        tasks: List of tuples (name, function, args)
        max_workers: Maximum number of concurrent workers
        timeout: Maximum time to wait for each task

    Returns:
        Dictionary mapping task names to their results
    """
    results = {}

    with ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix='parallel_scraper') as executor:
        # Submit all tasks
        futures = {
            executor.submit(func, *args): name 
            for name, func, args in tasks
        }

        # Collect results as they complete
        for future in as_completed(futures, timeout=timeout):
            task_name = futures[future]
            try:
                result = future.result(timeout=timeout)
                results[task_name] = result
            except Exception as e:
                logger.log(f'Error in {task_name} scraper: {str(e)}', log_utils.LOGWARNING)
                results[task_name] = {}

    return results


def _apply_fallbacks(art_dict, video_type):
    """
    Apply fallback logic for missing images.

    Args:
        art_dict: Dictionary containing image URLs
        video_type: Type of video (MOVIE, TVSHOW, SEASON, EPISODE)
    """
    # Thumb fallback
    if not art_dict.get('thumb'):
        logger.log(f'Doing {video_type} thumb fallback |{art_dict}|', log_utils.LOGDEBUG)
        if video_type == VIDEO_TYPES.MOVIE:
            if art_dict.get('poster') != PLACE_POSTER:
                art_dict['thumb'] = art_dict['poster']
            elif art_dict.get('fanart') != DEFAULT_FANART:
                art_dict['thumb'] = art_dict['fanart']
            else:
                art_dict['thumb'] = art_dict['poster']
        else:
            if art_dict.get('fanart') != DEFAULT_FANART:
                art_dict['thumb'] = art_dict['fanart']
            elif art_dict.get('poster') != PLACE_POSTER:
                art_dict['thumb'] = art_dict['poster']
            else:
                art_dict['thumb'] = art_dict['fanart']

    # Fanart fallback
    elif art_dict.get('fanart') == DEFAULT_FANART:
        logger.log(f'Doing {video_type} fanart fallback |{art_dict}|', log_utils.LOGDEBUG)
        art_dict['fanart'] = art_dict['thumb']


