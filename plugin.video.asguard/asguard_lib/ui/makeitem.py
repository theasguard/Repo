"""
    Asguard Addon
    Copyright (C) 2025 tknorris

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

import sys, os
import time
import requests
import shutil
import xbmc, xbmcaddon, xbmcgui, xbmcplugin, xbmcvfs
import urllib.request, urllib.parse
import log_utils
import utils
import kodi
from url_dispatcher import URL_Dispatcher
from asguard_lib.db_utils import get_trakt_id_by_tmdb_cached

from asguard_lib.trakt_api import Trakt_API
from asguard_lib import salts_utils, image_scraper, tmdb_api
from asguard_lib.listitem import ListItemInfoTag, set_info_tag

from asguard_lib.constants import *  # @UnusedWildImport
from asguard_lib.utils2 import i18n
from asguard_lib.image_proxy import ImageProxy

try:
    HANDLE = int(sys.argv[1])
except IndexError:
    HANDLE = -1

logger = log_utils.Logger.get_logger()

addon = xbmcaddon.Addon('plugin.video.asguard')
datafolder = xbmcvfs.translatePath(os.path.join('special://profile/addon_data/', addon.getAddonInfo('id')))
addonfolder = xbmcvfs.translatePath(os.path.join('special://home/addons/', addon.getAddonInfo('id')))
addonicon = xbmcvfs.translatePath(os.path.join(addonfolder, 'icon.png'))
addonfanart = xbmcvfs.translatePath(os.path.join(addonfolder, 'fanart.jpg'))
execute = xbmc.executebuiltin
TOKEN = kodi.get_setting('trakt_oauth_token')
logger.log('Trakt OAuth Token: %s' % TOKEN, log_utils.LOGDEBUG)
use_https = kodi.get_setting('use_https') == 'true'
trakt_timeout = int(kodi.get_setting('trakt_timeout'))
list_size = int(kodi.get_setting('list_size'))
OFFLINE = kodi.get_setting('trakt_offline') == 'true'
trakt_api = Trakt_API(TOKEN, use_https, list_size, trakt_timeout, OFFLINE)
proxy = ImageProxy()

url_dispatcher = URL_Dispatcher()


def make_tv_show_item(show):
    logger.log('make_tv_show_item main: {}'.format(show), log_utils.LOGNOTICE)
    name = show.get('name') or show.get('original_name') or ''
    first_air = show.get('first_air_date') or ''
    year = first_air[:4] if first_air else ''
    label = f"{name} ({year})" if year else name
    
    # Create a copy to avoid modifying the original show dict
    show_copy = show.copy()
    
    # Add required fields for salts_utils.make_info()
    show_copy['title'] = name  # Required by make_info()
    if show.get('original_name') and show.get('original_name') != name:
        show_copy['originaltitle'] = show.get('original_name')
    
    # Add year from first_air_date
    if year:
        show_copy['year'] = int(year)
        
    # Add overview if present
    if show.get('overview'):
        show_copy['overview'] = show.get('overview')

    # Provide both a stable cache key ('trakt') and the real TMDB id for image lookups
    tmdb_id = show.get('id')
    trakt_id = get_trakt_id_by_tmdb_cached(tmdb_id)
    ids = {
        'trakt': int(trakt_id) if trakt_id else tmdb_id,  # cache key; prefer real trakt id if available
        'tmdb': tmdb_id
    }
    tvdb_id = (show.get('external_ids') or {}).get('tvdb_id')
    if tvdb_id:
        ids['tvdb'] = int(tvdb_id)

    art = image_scraper.get_images(VIDEO_TYPES.TVSHOW, ids)
    logger.log('make_tv_show_item art: {}'.format(art), log_utils.LOGNOTICE)

    # Add IDs to show_copy for make_info
    show_copy['ids'] = {'tmdb': tmdb_id}
    if trakt_id:
        show_copy['ids']['trakt'] = int(trakt_id)
    
    liz = utils.make_list_item(label, show_copy, art)
    liz.setInfo('video', salts_utils.make_info(show_copy))

    # Fallbacks using TMDB image paths (like episodes use still_path)
    poster_path = show.get('poster_path')
    backdrop_path = show.get('backdrop_path')
    fallback_art = {}
    if poster_path:
        fallback_art['poster'] = f'https://image.tmdb.org/t/p/w500{poster_path}'
        # If no thumb provided, use poster as thumb
        fallback_art['thumb'] = fallback_art['poster']
    if backdrop_path:
        fallback_art['fanart'] = f'https://image.tmdb.org/t/p/w780{backdrop_path}'

    if fallback_art:
        liz.setArt({
            'poster': fallback_art.get('poster') or art.get('poster') or '',
            'fanart': fallback_art.get('fanart') or art.get('fanart') or '',
            'thumb': fallback_art.get('thumb') or art.get('thumb') or '',
            'banner': art['banner']
        })

    queries = {'mode': MODES.TMDB_SEASONS, 'tmdb_id': show['id']}
    liz_url = kodi.get_plugin_url(queries)
    return liz, liz_url


def make_tmdb_season_item(season, show, tmdb_id):
    logger.log('make_tmdb_season_item: {}'.format(season), log_utils.LOGNOTICE)
    logger.log('make_tmdb_season_item: {}'.format(show), log_utils.LOGNOTICE)
    logger.log('make_tmdb_season_item: {}'.format(tmdb_id), log_utils.LOGNOTICE)
    label = '{} {}'.format(i18n('season'), season['season_number'])
    # Provide ids including tmdb (and tvdb if available) so season art can be fetched by scrapers
    tmdb_show_id = int(show.get('id'))
    trakt_id = get_trakt_id_by_tmdb_cached(tmdb_id)
    ids = {
        'trakt': int(trakt_id) if trakt_id else tmdb_id,
        'tmdb': tmdb_id
    }
    tvdb_id = (show.get('external_ids') or {}).get('tvdb_id')
    if tvdb_id:
        ids['tvdb'] = int(tvdb_id)

    art = image_scraper.get_images(VIDEO_TYPES.SEASON, ids, season['season_number'])
    logger.log('make_tmdb_season_item_art: {}'.format(art), log_utils.LOGNOTICE)

    # Build proper meta objects for infotags (make_info expects 'title')
    season_meta = {
        'title': label,
        'overview': season.get('overview', ''),
        'season': season.get('season_number')
    }
    
    # Add IDs to season_meta for make_info
    season_meta['ids'] = {'tmdb': tmdb_id}
    if trakt_id:
        season_meta['ids']['trakt'] = int(trakt_id)
    if tvdb_id:
        season_meta['ids']['tvdb'] = int(tvdb_id)
        
    show_meta = {
        'title': show.get('name') or show.get('original_name') or '',
        'year': (show.get('first_air_date') or '')[:4],
        'overview': show.get('overview', ''),
        'runtime': (show.get('episode_run_time') or [None])[0]
    }

    liz = utils.make_list_item(label, season, art)
    liz.setInfo('video', salts_utils.make_info(season_meta, show_meta))

    # TMDB fallbacks for season/poster and show/backdrop
    season_poster = season.get('poster_path')
    show_backdrop = show.get('backdrop_path')
    fallback = {}
    if season_poster:
        fallback['poster'] = f'https://image.tmdb.org/t/p/w500{season_poster}'
        fallback['thumb'] = fallback['poster']
    if show_backdrop:
        fallback['fanart'] = f'https://image.tmdb.org/t/p/w780{show_backdrop}'

    # Prefer season poster image when available; otherwise use TMDB season poster_path fallback.
    season_poster = fallback.get('poster') or art['poster']
    liz.setArt({
        'icon': fallback.get('thumb') or art['thumb'],
        'thumb': fallback.get('thumb') or art['thumb'],
        'poster': season_poster,
        'fanart': fallback.get('fanart') or art['fanart'],
        'banner': art['banner'],
        'clearlogo': art['clearlogo']
    })
    queries = {'mode': MODES.TMDB_EPISODES, 'tmdb_id': tmdb_id, 'season': season['season_number']}
    liz_url = kodi.get_plugin_url(queries)
    return liz, liz_url

def make_tmdb_episode_item(show, episode, tmdb_id):
    """
    Create a list item for an episode from TMDB data, including context menus for source selection and downloading.
    
    :param show: The show details.
    :param episode: The episode details.
    :return: A tuple containing the list item and its URL.
    """
    logger.log('make_tmdb_episode_item_show: {}'.format(show), log_utils.LOGNOTICE)
    logger.log('make_tmdb_episode_item: {}'.format(episode), log_utils.LOGNOTICE)
    logger.log('make_tmdb_episode_item_tmdb_id: {}'.format(tmdb_id), log_utils.LOGNOTICE)
    trakt_id = get_trakt_id_by_tmdb_cached(tmdb_id)
    ids = {
        'trakt': trakt_id if trakt_id else tmdb_id,
        'tmdb': tmdb_id
    }
    tvdb_id = (show.get('external_ids') or {}).get('tvdb_id') if isinstance(show, dict) else None
    if tvdb_id:
        ids['tvdb'] = tvdb_id
    if episode.get('episode_group'):
        # Custom handling for group items
        label = episode['name']
        # art = image_scraper.get_images(VIDEO_TYPES.SEASON, ids)
        liz = utils.make_list_item(label, episode)
        queries = {
            'mode': MODES.EPISODE_GROUPS,
            'group_id': episode['id'],
            'season': episode.get('season', 0)
        }
        return liz, kodi.get_plugin_url(queries)
        
    episode_title = episode.get('name', 'N/A')  # TMDB uses 'name' for episode title
    season = episode.get('season_number', 'N/A')  # TMDB uses 'season_number'
    episode_number = episode.get('episode_number', 'N/A')
    
    label = '%sx%s %s' % (season, episode_number, episode_title)
    # Provide ids including tmdb (and tvdb if available) so EP/Show art can be fetched
    tmdb_show_id = show.get('id')
    logger.log('make_tmdb_episode_item_tmdb_show_id: {}'.format(tmdb_show_id), log_utils.LOGNOTICE)

        
    # Create episode_meta for make_info
    episode_meta = {
        'title': episode_title,
        'season': season,
        'episode': episode_number,
        'overview': episode.get('overview', ''),
        'ids': {'tmdb': tmdb_id}
    }
    
    # Add trakt/tvdb IDs if available
    if trakt_id:
        episode_meta['ids']['trakt'] = trakt_id
    if tvdb_id:
        episode_meta['ids']['tvdb'] = tvdb_id
        
    # Create show_meta for make_info if show is a dict
    show_meta = None
    if isinstance(show, dict):
        show_meta = {
            'title': show.get('name') or show.get('original_name') or '',
            'year': (show.get('first_air_date') or '')[:4],
            'overview': show.get('overview', '')
        }



    art = image_scraper.get_images(VIDEO_TYPES.EPISODE, ids, season, episode_number)
    
    # Create the list item
    liz = xbmcgui.ListItem(label=label)
    liz.setInfo('video', salts_utils.make_info(episode_meta, show_meta))

    # Fallbacks using TMDB still/poster/backdrop if available
    fallback_art = {}
    still_path = episode.get('still_path')
    if still_path:
        fallback_art['thumb'] = f'https://image.tmdb.org/t/p/w500{still_path}'
    poster_path = show.get('poster_path') if isinstance(show, dict) else None
    backdrop_path = show.get('backdrop_path') if isinstance(show, dict) else None
    # Prefer episode still for poster in episode views so skins that use 'poster' show the still
    if still_path:
        fallback_art['poster'] = fallback_art['thumb']
    elif poster_path:
        fallback_art['poster'] = f'https://image.tmdb.org/t/p/w500{poster_path}'
    if backdrop_path:
        fallback_art['fanart'] = f'https://image.tmdb.org/t/p/w780{backdrop_path}'
    if fallback_art:
        # For episode views, prefer episode still for both thumb and poster
        preferred_thumb = fallback_art.get('thumb') or art['thumb']
        preferred_poster = fallback_art.get('poster') or art['poster']
        liz.setArt({
            'icon': preferred_thumb,
            'poster': preferred_poster,
            'banner': art['banner'],
            'clearlogo': art['clearlogo'],
            'fanart': fallback_art.get('fanart') or art['fanart'],
            'thumb': preferred_thumb
        })
    else:
        liz.setArt({'icon': art['thumb'], 'poster': art['poster'], 'banner': art['banner'], 'clearlogo': art['clearlogo'], 'fanart': art['fanart']})

    # Context menu items
    menu_items = []
    queries = {
        'mode': MODES.GET_SOURCES,
        'video_type': VIDEO_TYPES.EPISODE,
        'title': show['name'],
        'year': show.get('first_air_date', '')[:4],
        'season': season,
        'episode': episode_number,
        'trakt_id': trakt_id
    }
    url = kodi.get_plugin_url(queries)

    # Auto-play setting
    if kodi.get_setting('auto-play') == 'true':
        runstring = 'RunPlugin(%s)' % url
        menu_items.append((i18n('auto-play'), runstring))
    else:
        runstring = 'Container.Update(%s)' % url
        menu_items.append((i18n('select_source'), runstring))

    # Download option
    if kodi.get_setting('show_download') == 'true':
        download_queries = queries.copy()
        download_queries['mode'] = MODES.DOWNLOAD_SOURCE
        download_url = kodi.get_plugin_url(download_queries)
        menu_items.append((i18n('download_source'), 'RunPlugin(%s)' % download_url))

    liz.addContextMenuItems(menu_items, replaceItems=True)

    return liz, url

def make_group_episode_item(show_title, year, trakt_id, tmdb_id, episode, season, ep_watched):
    """Create a list item for group episodes similar to make_episode_item"""
    logger.log('Episode watched: %s' % ep_watched, log_utils.LOGDEBUG)
    ep_num = episode.get('order', 0) + 1
    label = f"{int(season)}x{ep_num} {episode.get('name', 'Episode')}"

    actual_season = episode.get('season_number', 1)
    actual_episode = episode.get('episode_number', 1)
    logger.log('Actual season: %s' % actual_season, log_utils.LOGDEBUG)
    logger.log('Actual episode: %s' % actual_episode, log_utils.LOGDEBUG)
    
    # Create proper show metadata
    show_info = {
        'title': show_title,
        'year': year,
        'ids': {'trakt': trakt_id, 'tmdb': tmdb_id},
        'tvshowtitle': show_title,
        'mediatype': 'tvshow'
    }
    
    # Create episode metadata
    episode_info = {
        'season': actual_season,
        'episode': actual_episode,
        'title': episode.get('name', 'Episode'),
        'overview': episode.get('overview', ''),
        'tvshowtitle': show_title,
        'showtitle': show_title,
        'mediatype': 'episode',
        'watched': 1 if ep_watched else 0  # Set playcount directly in metadata
    }
    logger.log('Episode info: %s' % episode_info, log_utils.LOGDEBUG)
    
    # Combine show and episode info
    meta = salts_utils.make_info(episode_info, show_info)
    
    # Create list item
    li = utils.make_list_item(label, meta)

    # Set unique IDs
    valid_ids = {
        'imdb': meta.get('imdbnumber'),
        'tmdb': meta.get('tmdb_id'),
        'tvdb': meta.get('tvdb_id'),
        'trakt': meta.get('trakt_id'),
        'slug': meta.get('slug'),
        'tvshow.tmdb': str(tmdb_id),  # TV show context
        'tvshow.imdb': meta.get('imdb_id', '')  # TV show context
    }
    li.setUniqueIDs({k: v for k, v in valid_ids.items() if v})
    
    # Set info tag
    set_info_tag(li, meta, 'video', 
                old_method_keys=('size', 'count', 'date', 'duration', 'genre', 'year', 'episode', 'season'))
    
    # Set artwork
    if episode.get('still_path'):
        li.setArt({'thumb': f'https://image.tmdb.org/t/p/w500{episode["still_path"]}'})
    
    # Create URL
    queries = {
        'mode': MODES.GET_SOURCES,
        'video_type': VIDEO_TYPES.EPISODE,
        'title': show_title,
        'year': year,
        'season': season,
        'episode': ep_num,
        'ep_title': episode.get('name', ''),
        'ep_airdate': episode.get('air_date', ''),
        'trakt_id': trakt_id,
        'random': time.time()
    }
    liz_url = kodi.get_plugin_url(queries)
    
    # Create context menu items
    menu_items = []
    
    # Add "Mark as watched/unwatched" option
    if ep_watched:
        watched = False
        label_watched = i18n('mark_as_unwatched')
    else:
        watched = True
        label_watched = i18n('mark_as_watched')
    
    # Create show ID dictionary
    show_id = {'trakt': trakt_id}
    if tmdb_id:
        show_id['tmdb'] = tmdb_id
    
    # Add toggle watched command
    queries = {
        'mode': MODES.TOGGLE_WATCHED,
        'section': SECTIONS.TV,
        'id_type': 'trakt',
        'show_id': trakt_id,
        'season': actual_season,
        'episode': actual_episode,
        'watched': watched
    }
    menu_items.append((label_watched, 'RunPlugin(%s)' % kodi.get_plugin_url(queries)))
    # Add properties for player monitoring
    li.setProperty('trakt_id', str(trakt_id))
    li.setProperty('season', str(actual_season))
    li.setProperty('episode', str(actual_episode))
    li.setProperty('isWatched', '1' if ep_watched else '0')
    li.setInfo('video', {'playcount': 1 if ep_watched else 0})
    
    # Add context menu to list item
    li.addContextMenuItems(menu_items, replaceItems=True)
    
    return li, liz_url