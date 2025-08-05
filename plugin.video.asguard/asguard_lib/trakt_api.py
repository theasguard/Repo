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
import json
import socket
import ssl
import threading
import time
import gzip
from io import StringIO
from typing import Any, Union
import requests
from six.moves import urllib_parse, urllib_request, urllib_error
import urllib.error
import urllib.parse
import kodi
import log_utils
import utils
from asguard_lib import utils2  # Use relative import
import logging

from asguard_lib.constants import SECTIONS, TEMP_ERRORS, TRAKT_SECTIONS  # Ensure relative import
from asguard_lib.db_utils import DB_Connection  # Ensure relative import

logger = log_utils.Logger.get_logger(__name__)
logging.basicConfig(level=logging.DEBUG)

def __enum(**enums):
    return type('Enum', (), enums)

TEMP_ERRORS = [500, 502, 503, 504, 520, 521, 522, 524]
SECTIONS = __enum(TV='TV', MOVIES='Movies')
TRAKT_SECTIONS = {SECTIONS.TV: 'shows', SECTIONS.MOVIES: 'movies'}
session = requests.Session()
logger.log(f"Trakt API Session: {session}", log_utils.LOGDEBUG)
retry = requests.adapters.Retry(total=None, status=1, status_forcelist=(429, 502, 503, 504))
if kodi.get_setting('use_https') == 'true':
    session.mount('https://api.trakt.tv', requests.adapters.HTTPAdapter(pool_maxsize=100, max_retries=retry))
else:
    session.mount('http://api.trakt.tv', requests.adapters.HTTPAdapter(pool_maxsize=100, max_retries=retry))


class TraktError(Exception):
    pass

class TraktAuthError(Exception):
    pass

class TraktNotFoundError(Exception):
    pass

class TransientTraktError(Exception):
    pass

BASE_URL = 'api.trakt.tv'
V2_API_KEY = '523a3a5e356f78b0e4d3b4eddfc23b704f7576d69cd4229317304cc21e9753a7'
CLIENT_SECRET = '9069c9d421593e61b854990b622eac6883f690a30c62f621baa4f408183485a4'
REDIRECT_URI = 'urn:ietf:wg:oauth:2.0:oob'
RESULTS_LIMIT = 100
HIDDEN_SIZE = 100

class Trakt_API():
    def __init__(self, token=None, use_https=False, list_size=RESULTS_LIMIT, timeout=100, offline=False):
        self.token = token
        self.protocol = 'https://' if use_https else 'http://'
        self.timeout = None if timeout == 0 else timeout
        self.list_size = list_size
        self.offline = offline
        self.__db_connection = DB_Connection()
        self.__worker_id = None
                    # Create a custom opener without authentication handlers
        self.opener = urllib_request.build_opener(
            urllib_request.HTTPHandler(),
            urllib_request.HTTPSHandler(context=ssl.create_default_context())
        )
        # Enable optimized methods (set to True to use new efficient methods)
        self.use_optimized_methods = kodi.get_setting('trakt_use_optimized') == 'true'
        if self.use_optimized_methods:
            logger.log('Trakt API: Using optimized methods like POV', log_utils.LOGDEBUG)

    def get_code(self):
        url = '/oauth/device/code'
        data = {'client_id': V2_API_KEY}
        return self.__call_trakt(url, data=data, auth=False, cached=False)
    
    def get_device_token(self, code):
        url = '/oauth/device/token'
        data = {'client_id': V2_API_KEY, 'client_secret': CLIENT_SECRET, 'code': code}
        return self.__call_trakt(url, data=data, auth=False, cached=False)
    
    def refresh_token(self, refresh_token):
        url = '/oauth/token'
        data = {'client_id': V2_API_KEY, 'client_secret': CLIENT_SECRET, 'redirect_uri': REDIRECT_URI}
        if refresh_token:
            data['refresh_token'] = refresh_token
            data['grant_type'] = 'refresh_token'
        else:
            raise TraktError('Can not refresh trakt token. Trakt reauthorizion required.')
            
        return self.__call_trakt(url, data=data, auth=False, cached=False)
    
    def show_list(self, slug, section, username=None, auth=True, cached=True):
        if not username:
            username = 'me'
            cache_limit = self.__get_cache_limit('lists', 'updated_at', cached)
        else:
            cache_limit = 1  # cache other user's list for one hour

        url = '/users/%s/lists/%s/items' % (utils.to_slug(username), slug)
        params = {'extended': 'full'}
        list_data = self.__call_trakt(url, params=params, auth=auth, cache_limit=cache_limit, cached=cached)
        return [item[item['type']] for item in list_data if item['type'] == TRAKT_SECTIONS[section][:-1]]

    def show_watchlist(self, section, cached=True):
        url = '/users/me/watchlist/%s' % (TRAKT_SECTIONS[section])
        params = {'extended': 'full'}
        cache_limit = self.__get_cache_limit('lists', 'updated_at', cached=cached)
        response = self.__call_trakt(url, params=params, cache_limit=cache_limit)
        return [item[TRAKT_SECTIONS[section][:-1]] for item in response]

    def get_list_header(self, slug, username=None, auth=True):
        if not username:
            username = 'me'
        url = '/users/%s/lists/%s' % (utils.to_slug(username), slug)
        return self.__call_trakt(url, auth=auth)

    def get_lists(self, username=None):
        if not username:
            username = 'me'
            cache_limit = self.__get_cache_limit('lists', 'updated_at', True)
        else:
            cache_limit = 0
        url = '/users/%s/lists' % (utils.to_slug(username))
        return self.__call_trakt(url, cache_limit=cache_limit)

    def get_liked_lists(self, page=None, cached=True):
        url = '/users/likes/lists'
        params = {'limit': self.list_size}
        if page: params['page'] = page
        cache_limit = self.__get_cache_limit('lists', 'liked_at', cached=cached)
        return self.__call_trakt(url, params=params, cache_limit=cache_limit, cached=cached)

    def add_to_list(self, section, slug, items):
        return self.__manage_list('add', section, slug, items)

    def add_to_collection(self, section, item):
        return self.__manage_collection('add', section, item)

    def remove_from_collection(self, section, item):
        return self.__manage_collection('remove', section, item)

    def set_watched(self, section, item, season='', episode='', watched=True):
        url = '/sync/history'
        if not watched: url = url + '/remove'
        data = self.__make_media_list(section, item, season, episode)
        return self.__call_trakt(url, data=data, cache_limit=0)

    def remove_from_list(self, section, slug, items):
        return self.__manage_list('remove', section, slug, items)

    def add_to_watchlist(self, section, items):
        return self.__manage_watchlist('add', section, items)

    def remove_from_watchlist(self, section, items):
        return self.__manage_watchlist('remove', section, items)

    def get_trending(self, section, page=None, filters=None):
        if filters is None: filters = {}
        url = '/{}/trending'.format(TRAKT_SECTIONS[section])
        params = {'extended': 'full', 'limit': self.list_size}
        params.update(filters)
        if page: params['page'] = page
        response = self.__call_trakt(url, params=params)
        return [item[TRAKT_SECTIONS[section][:-1]] for item in response]

    def get_anticipated(self, section, page=None, filters=None):
        if filters is None: filters = {}
        url = '/{}/anticipated'.format(TRAKT_SECTIONS[section])
        params = {'extended': 'full', 'limit': self.list_size}
        params.update(filters)
        if page: params['page'] = page
        response = self.__call_trakt(url, params=params)
        return [item[TRAKT_SECTIONS[section][:-1]] for item in response]

    def get_popular(self, section, page=None, filters=None):
        if filters is None: filters = {}
        url = '/{}/popular'.format(TRAKT_SECTIONS[section])
        params = {'extended': 'full', 'limit': self.list_size}
        params.update(filters)
        if page: params['page'] = page
        return self.__call_trakt(url, params=params)

    def get_recent(self, section, date, page=None):
        url = '/{}/updates/{}'.format(TRAKT_SECTIONS[section], date)
        params = {'extended': 'full', 'limit': self.list_size}
        if page: params['page'] = page
        response = self.__call_trakt(url, params=params)
        return [item[TRAKT_SECTIONS[section][:-1]] for item in response]

    def get_most_played(self, section, period, page=None, filters=None):
        return self.__get_most('played', section, period, page, filters)
    
    def get_most_watched(self, section, period, page=None, filters=None):
        return self.__get_most('watched', section, period, page, filters)
    
    def get_most_collected(self, section, period, page=None, filters=None):
        return self.__get_most('collected', section, period, page, filters)
    
    def __get_most(self, category, section, period, page, filters):
        if filters is None: filters = {}
        url = '/{}/{}/{}'.format(TRAKT_SECTIONS[section], category, period)
        params = {'extended': 'full', 'limit': self.list_size}
        params.update(filters)
        if page: params['page'] = page
        response = self.__call_trakt(url, params=params)
        return [item[TRAKT_SECTIONS[section][:-1]] for item in response]
    
    def get_genres(self, section):
        url = '/genres/%s' % (TRAKT_SECTIONS[section])
        return self.__call_trakt(url, cache_limit=24 * 7)

    def get_recommendations(self, section):
        url = '/recommendations/{}'.format(TRAKT_SECTIONS[section])
        params = {'extended': 'full', 'limit': self.list_size}
        return self.__call_trakt(url, params=params)

    def get_premieres(self, start_date=None, days=None, cached=True):
        url = '/calendars/all/shows/premieres'
        if start_date: url += '/%s' % (start_date)
        if days is not None: url += '/%s' % (days)
        params = {'extended': 'full', 'auth': False}
        return self.__call_trakt(url, params=params, auth=False, cache_limit=24, cached=cached)

    def get_calendar(self, start_date=None, days=None, cached=True):
        url = '/calendars/all/shows'
        if start_date: url += '/%s' % (start_date)
        if days is not None: url += '/%s' % (days)
        params = {'extended': 'full', 'auth': False}
        return self.__call_trakt(url, params=params, auth=False, cache_limit=24, cached=cached)

    def get_my_calendar(self, start_date=None, days=None, cached=True):
        url = '/calendars/my/shows'
        if start_date: url += '/%s' % (start_date)
        if days is not None: url += '/%s' % (days)
        params = {'extended': 'full', 'auth': True}
        return self.__call_trakt(url, params=params, auth=True, cache_limit=24, cached=cached)

    def cache_show_aliases(self, show_id):
        """
        Fetches and caches aliases for a show
        :param show_id: Trakt ID of show item
        :return: list of aliases
        """
        url = f"/shows/{show_id}/aliases"
        try:
            response = self.__call_trakt(url, cache_limit=24 * 7)
            country = getattr(self, 'country', 'us')
            aliases = sorted(
                {
                    i["title"]
                    for i in response
                    if i["country"] in [country, 'us']
                }
            )
            # Cache the aliases
            self.__db_connection.cache_url(url, json.dumps(aliases))
            return aliases
        except Exception as e:
            logger.log(f"Error fetching aliases for show_id {show_id}: {e}", log_utils.LOGERROR)
            return []

    def get_show_aliases(self, show_id):
        """
        Fetches aliases for a show, using cache if available
        :param show_id: Trakt ID of show item
        :return: list of aliases
        """
        url = f"/shows/{show_id}/aliases"
        cached_result = self.__db_connection.get_cached_url(url)
        if cached_result:
            # Ensure cached_result is a string before loading JSON
            if isinstance(cached_result, tuple):
                cached_result = cached_result[0]
            if isinstance(cached_result, (str, bytes, bytearray)):
                try:
                    return json.loads(cached_result)
                except json.JSONDecodeError as e:
                    logger.log(f"Error decoding cached aliases for show_id {show_id}: {e}", log_utils.LOGERROR)
                    return []
            else:
                logger.log(f"Unexpected cached result type: {type(cached_result)}", log_utils.LOGERROR)
                return []
        else:
            return self.cache_show_aliases(show_id)

    def get_next_episode(self, show_id):
        url = '/shows/%s/next_episode' % (show_id)
        params = {'extended': 'full'}
        return self.__call_trakt(url, params=params, cache_limit=24 * 7)

    def get_seasons(self, show_id):
        url = '/shows/%s/seasons' % (show_id)
        params = {'extended': 'full'}
        return self.__call_trakt(url, params=params, cache_limit=24 * 7)

    def get_episodes(self, show_id, season):
        url = '/shows/%s/seasons/%s' % (show_id, season)
        logger.log('Trakt API Seasons URL: %s' % url, log_utils.LOGDEBUG)
        params = {'extended': 'full'}
        return self.__call_trakt(url, params=params, cache_limit=24 * 7)

    def get_show_details(self, show_id):
        url = '/shows/%s' % (show_id)
        params = {'extended': 'full'}
        return self.__call_trakt(url, params=params, cache_limit=24 * 7)

    def get_episode_details(self, show_id, season, episode):
        url = '/shows/%s/seasons/%s/episodes/%s' % (show_id, season, episode)
        logger.log('Trakt API Episode Details URL: %s' % url, log_utils.LOGDEBUG)
        params = {'extended': 'full'}
        return self.__call_trakt(url, params=params, cache_limit=48)

    def get_movie_details(self, show_id):
        url = '/movies/%s' % (show_id)
        params = {'extended': 'full'}
        return self.__call_trakt(url, params=params, cache_limit=48)

    def get_people(self, section, show_id, full=False):
        url = '/%s/%s/people' % (TRAKT_SECTIONS[section], show_id)
        params = {'extended': 'full'} if full else None
        try:
            return self.__call_trakt(url, params=params, cache_limit=24 * 30)
        except TraktNotFoundError:
            return {}

    def search(self, section, query, page=None):
        url = '/search/%s' % (TRAKT_SECTIONS[section][:-1])
        params = {'query': query, 'limit': self.list_size}
        if page:
            params['page'] = page
        params.update({'extended': 'full'})
        
        logger.log('Trakt API Search URL: %s' % url, log_utils.LOGDEBUG)
        logger.log('Trakt API Search Params: %s' % params, log_utils.LOGDEBUG)
        
        response = self.__call_trakt(url, params=params)
        return [item[TRAKT_SECTIONS[section][:-1]] for item in response]

    def get_collection(self, section, full=True, cached=True):
        url = '/users/me/collection/{}'.format(TRAKT_SECTIONS[section])
        params = {'extended': 'full'} if full else None
        media = 'movies' if section == SECTIONS.MOVIES else 'episodes'
        cache_limit = self.__get_cache_limit(media, 'collected_at', cached)
        response = self.__call_trakt(url, params=params, cache_limit=cache_limit, cached=cached)
        result = []
        for item in response:
            element = item[TRAKT_SECTIONS[section][:-1]]
            if section == SECTIONS.TV:
                element['seasons'] = item['seasons']
            result.append(element)
        return result

    def get_watched(self, section, full=False, noseasons=False, cached=True):
        url = '/sync/watched/%s' % (TRAKT_SECTIONS[section])
        params = {'extended': 'full'} if full else {}
        if noseasons and params:
            params['extended'] += ',noseasons'
        elif noseasons:
            params['extended'] = 'noseasons'
        media = 'movies' if section == SECTIONS.MOVIES else 'episodes'
        cache_limit = self.__get_cache_limit(media, 'watched_at', cached)
        return self.__call_trakt(url, params=params, cache_limit=cache_limit, cached=cached)

    def get_history(self, section, full=False, page=None, cached=True):
        url = '/users/me/history/%s' % (TRAKT_SECTIONS[section])
        params = {'limit': self.list_size}
        if full: params.update({'extended': 'full'})
        if page: params['page'] = page
        media = 'movies' if section == SECTIONS.MOVIES else 'episodes'
        cache_limit = self.__get_cache_limit(media, 'watched_at', cached)
        return self.__call_trakt(url, params=params, cache_limit=cache_limit, cached=cached)

    def get_show_progress(self, show_id, full=False, hidden=False, specials=False, cached=True, cache_limit=None):
        if cache_limit is None:
            cache_limit = self.__get_cache_limit('episodes', 'watched_at', cached)
        url = '/shows/%s/progress/watched' % (show_id)
        params = {}
        if full: params['extended'] = 'full'
        if hidden: params['hidden'] = 'true'
        if specials: params['specials'] = 'true'
        return self.__call_trakt(url, params=params, cache_limit=cache_limit, cached=cached)

    def get_hidden_progress(self, cached=True):
        url = '/users/hidden/progress_watched'
        params = {'type': 'show', 'limit': HIDDEN_SIZE, 'page': 1}
        result = []
        while True:
            cache_limit = self.__get_cache_limit('shows', 'hidden_at', cached)
            hidden = self.__call_trakt(url, params=params, cache_limit=cache_limit, cached=cached)
            if not hidden:
                break
            result += hidden
            if len(hidden) < HIDDEN_SIZE:
                break
            params['page'] += 1
        return result
    
    def get_user_profile(self, username=None, cached=True):
        if username is None: username = 'me'
        url = '/users/%s' % (utils.to_slug(username))
        return self.__call_trakt(url, cached=cached)

    def get_bookmarks(self, section=None, full=False):
        url = '/sync/playback'
        if section == SECTIONS.MOVIES:
            url += '/movies'
        elif section == SECTIONS.TV:
            url += '/episodes'
        params = {'extended': 'full'} if full else None
        return self.__call_trakt(url, params=params, cached=False)

    def get_bookmark(self, show_id, season, episode):
        response = self.get_bookmarks()
        for bookmark in response:
            if not season or not episode:
                if bookmark['type'] == 'movie' and int(show_id) == bookmark['movie']['ids']['trakt']:
                    return bookmark['progress']
            else:
                logger.log('Resume: %s, %s, %s, %s' % (bookmark, show_id, season, episode), log_utils.LOGDEBUG)
                if bookmark['type'] == 'episode' and int(show_id) == bookmark['show']['ids']['trakt'] and bookmark['episode']['season'] == int(season) and bookmark['episode']['number'] == int(episode):
                    return bookmark['progress']

    def delete_bookmark(self, bookmark_id):
        url = '/sync/playback/%s' % (bookmark_id)
        return self.__call_trakt(url, method='DELETE', cached=False)
        
    def rate(self, section, item, rating, season='', episode=''):
        url = '/sync/ratings'
        data = self.__make_media_list(section, item, season, episode)

        if rating is None:
            url = url + '/remove'
        else:
            # method only allows ratings one item at a time, so set rating on first item of each in list
            if season and episode:
                data[TRAKT_SECTIONS[section]][0]['seasons'][0]['episodes'][0].update({'rating': int(rating)})
            elif season:
                data[TRAKT_SECTIONS[section]][0]['seasons'][0].update({'rating': int(rating)})
            else:
                data[TRAKT_SECTIONS[section]][0].update({'rating': int(rating)})

        self.__call_trakt(url, data=data, cache_limit=0)

    def get_last_activity(self, media=None, activity=None):
        url = '/sync/last_activities'
        result = self.__call_trakt(url, cache_limit=0.10)
        if media and media in result:
            if activity and activity in result[media]:
                return result[media][activity]
            return result[media]
        return result

    def __get_cache_limit(self, media, activity, cached):
        if cached:
            activity = self.get_last_activity(media, activity)
            cache_limit = (time.time() - utils.iso_2_utc(activity))
            logger.log('Now: %s Last: %s Last TS: %s Cache Limit: %.2fs (%.2fh)' % (time.time(), utils.iso_2_utc(activity), activity, cache_limit, cache_limit / 60 / 60), log_utils.LOGDEBUG)
            cache_limit = cache_limit / 60 / 60
        else:
            cache_limit = 0
        return cache_limit

    def __manage_list(self, action, section, slug, items):
        url = '/users/me/lists/%s/items' % (slug)
        if action == 'remove': url = url + '/remove'
        if not isinstance(items, (list, tuple)): items = [items]
        data = self.__make_media_list_from_list(section, items)
        return self.__call_trakt(url, data=data, cache_limit=0)

    def __manage_watchlist(self, action, section, items):
        url = '/sync/watchlist'
        if action == 'remove':
            url += '/remove'
        if not isinstance(items, (list, tuple)):
            items = [items]
        data = self.__make_media_list_from_list(section, items)
        return self.__call_trakt(url, data=data, cache_limit=0)

    def __manage_collection(self, action, section, item):
        url = '/sync/collection'
        if action == 'remove':
            url += '/remove'
        data = self.__make_media_list(section, item)
        
        # Call the working Trakt API method with error handling
        try:
            result = self.__call_trakt_optimized(url, data=data, cache_limit=0)
        except Exception as e:
            error_msg = str(e)
            logger.log(f'Collection API call failed: {error_msg}', log_utils.LOGERROR)
            
            # Handle specific Trakt API errors with helpful messages
            if 'HTTP Error 420' in error_msg:
                kodi.notify(msg='⏳ Trakt rate limited. Wait and try again.', duration=4000)
            elif 'HTTP Error 401' in error_msg:
                kodi.notify(msg='🔐 Trakt auth failed. Re-authorize required.', duration=4000)
            elif 'HTTP Error 422' in error_msg:
                kodi.notify(msg='⚠️ Invalid data sent to Trakt.', duration=3000)
            elif 'HTTP Error 404' in error_msg:
                kodi.notify(msg='⚠️ Item not found on Trakt.', duration=3000)
            else:
                kodi.notify(msg='❌ Failed to update Trakt collection', duration=3000)
            return None
        
        # Add POV-style user feedback and cache efficiency
        if result:
            try:
                if action == 'add' and 'added' in result:
                    added_count = result['added'].get('movies', 0) + result['added'].get('episodes', 0)
                    if added_count > 0:
                        kodi.notify(msg=f'✅ Added {added_count} item(s) to Trakt collection', duration=3000)
                        # Trigger efficient cache refresh
                        self.__sync_activities_after_change('collection', section)
                    else:
                        kodi.notify(msg='⚠️ Nothing was added to collection', duration=3000)
                        
                elif action == 'remove' and 'deleted' in result:
                    deleted_count = result['deleted'].get('movies', 0) + result['deleted'].get('episodes', 0)
                    if deleted_count > 0:
                        kodi.notify(msg=f'✅ Removed {deleted_count} item(s) from Trakt collection', duration=3000)
                        # Trigger efficient cache refresh and UI update
                        self.__sync_activities_after_change('collection', section)
                        
                    else:
                        kodi.notify(msg='⚠️ Nothing was removed from collection', duration=3000)
                        
            except Exception as e:
                logger.log(f'Collection notification error: {str(e)}', log_utils.LOGDEBUG)
                
        return result

    def __make_media_list(self, section, item, season='', episode=''):
        ids = {'ids': item}
        if section == SECTIONS.MOVIES:
            data = {'movies': [ids]}
        else:
            data = {'shows': [ids]}
            if season:
                data['shows'][0]['seasons'] = [{'number': int(season)}]
                if episode:
                    data['shows'][0]['seasons'][0]['episodes'] = [{'number': int(episode)}]
        return data

    def __make_media_list_from_list(self, section, items):
        data = {TRAKT_SECTIONS[section]: []}
        for item in items:
            ids = {'ids': item}
            data[TRAKT_SECTIONS[section]].append(ids)
        return data

    def __get_db_connection(self):
        worker_id = threading.current_thread().ident
        if not self.__db_connection or self.__worker_id != worker_id:
            self.__db_connection = DB_Connection()
            self.__worker_id = worker_id
        return self.__db_connection

    def __call_trakt(self, url: str, method: str = None, data: Any = None, params: dict = None, auth: bool = True, cache_limit: float = .25, cached: bool = True) -> Union[str, list, dict, Any]:
        res_headers = {}
        if not cached: cache_limit = 0
        if self.offline:
            db_cache_limit = int(time.time()) / 60 / 60
        else:
            if cache_limit > 8:
                db_cache_limit = cache_limit
            else:
                db_cache_limit = 8
        json_data = json.dumps(data).encode('utf-8') if data else None
        logger.log('***Trakt Call: %s, data: %s cache_limit: %s cached: %s' % (url, json_data, cache_limit, cached), log_utils.LOGDEBUG)

        headers = {'Content-Type': 'application/json', 'trakt-api-key': V2_API_KEY, 'trakt-api-version': 2}
        url = '%s%s%s' % (self.protocol, BASE_URL, url)
        if params: 
            url = url + '?' + urllib_parse.urlencode(params)


        db_connection = self.__get_db_connection()
        created, cached_headers, cached_result = db_connection.get_cached_url(url, json_data, db_cache_limit)
        logger.log('DEBUG: cached_result type=%s, value=%s' % (type(cached_result), str(cached_result)[:100] if cached_result else 'NONE'), log_utils.LOGDEBUG)
        if cached_result and (self.offline or (time.time() - created) < (60 * 60 * cache_limit)):
            result = cached_result
            res_headers = dict(cached_headers)
            logger.log('***Using cached result for: %s' % (url), log_utils.LOGDEBUG)
        else:
            auth_retry = False
            while True:
                try:
                    if auth: 
                        headers.update({'Authorization': 'Bearer %s' % (self.token)})
                    logger.log('***Trakt Call: %s, header: %s, data: %s cache_limit: %s cached: %s' % (url, headers, json_data, cache_limit, cached), log_utils.LOGDEBUG)
                    request = urllib_request.Request(url, data=json_data, headers=headers)
                    if method is not None: 
                        request.get_method = lambda: method.upper()


                    response = self.opener.open(request, timeout=self.timeout)
                    result = ''
                    while True:
                        data = response.read()
                        if not data:
                            break
                        result += data.decode('utf-8')
                    logger.log('***Trakt Response: %s' % (result), log_utils.LOGDEBUG)


                    db_connection.cache_url(url, result, json_data, response.info().items())
                    break
                except (ssl.SSLError, socket.timeout) as e:
                    logger.log('Socket Timeout or SSL Error occurred: {}'.format(e), log_utils.LOGWARNING)
                    if cached_result:
                        result = cached_result
                        logger.log('Temporary Trakt Error (%s). Using Cached Page Instead.' % (str(e)), log_utils.LOGWARNING)
                    else:
                        raise TransientTraktError('Temporary Trakt Error: ' + str(e))
                except urllib_error.URLError as e:
                    if isinstance(e, urllib_error.HTTPError):
                        if e.code in TEMP_ERRORS:
                            if cached_result:
                                result = cached_result
                                logger.log('Temporary Trakt Error (%s). Using Cached Page Instead.' % (str(e)), log_utils.LOGWARNING)
                                break
                            else:
                                raise TransientTraktError('Temporary Trakt Error: ' + str(e))
                        elif e.code == 401 or e.code == 405:
                            # token is fine, profile is private
                            if 'X-Private-User' in e.headers and e.headers.get('X-Private-User') == 'true':
                                raise TraktAuthError('Object is No Longer Available (%s)' % (e.code))
                            # auth failure retry or a token request
                            elif auth_retry or url.endswith('/oauth/token'):
                                self.token = None
                                kodi.set_setting('trakt_oauth_token', '')
                                kodi.set_setting('trakt_refresh_token', '')
                                raise TraktAuthError('Trakt Call Authentication Failed (%s)' % (e.code))
                            # first try token fail, try to refresh token
                            else:
                                result = self.refresh_token(kodi.get_setting('trakt_refresh_token'))
                                self.token = result['access_token']
                                kodi.set_setting('trakt_oauth_token', result['access_token'])
                                kodi.set_setting('trakt_refresh_token', result['refresh_token'])
                                auth_retry = True
                        elif e.code == 404:
                            raise TraktNotFoundError('Object Not Found (%s): %s' % (e.code, url))
                        else:
                            raise
                    elif isinstance(e.reason, socket.timeout) or isinstance(e.reason, ssl.SSLError):
                        if cached_result:
                            result = cached_result
                            logger.log('Temporary Trakt Error (%s). Using Cached Page Instead' % (str(e)), log_utils.LOGWARNING)
                            break
                        else:
                            raise TransientTraktError('Temporary Trakt Error: ' + str(e))
                    else:
                        raise TraktError('Trakt Error: ' + str(e))
                except Exception as e:
                    logger.log('Unexpected error: {}'.format(e), log_utils.LOGERROR)
                    raise

        try:
            logger.log('DEBUG: result type=%s, value=%s' % (type(result), str(result)[:100] if result else 'NONE'), log_utils.LOGDEBUG)
            js_data = utils.json_loads_as_str(result)
            logger.log('js_data before sort: %s' % (js_data), log_utils.LOGDEBUG)
            if 'x-sort-by' in res_headers and 'x-sort-how' in res_headers:
                js_data = utils2.sort_list(res_headers['x-sort-by'], res_headers['x-sort-how'], js_data)
        except ValueError:
            js_data = ''
            if result:
                logger.log('Invalid JSON Trakt API Response: %s - |%s|' % (url, js_data), log_utils.LOGERROR)

        return js_data

    def __call_trakt_simple(self, url: str, method: str = None, data: Any = None, params: dict = None, auth: bool = True) -> Union[str, list, dict, Any]:
        """Simplified HTTP handler similar to POV's approach"""
        try:
            import requests
            
            # Use requests session for better performance
            if not hasattr(self, '_session'):
                self._session = requests.Session()
                # Set up retry strategy
                retry_strategy = requests.adapters.Retry(
                    total=3,
                    status_forcelist=[429, 500, 502, 503, 504],
                    allowed_methods=["HEAD", "GET", "OPTIONS", "POST", "PUT", "DELETE"]
                )
                adapter = requests.adapters.HTTPAdapter(max_retries=retry_strategy)
                self._session.mount("http://", adapter)
                self._session.mount("https://", adapter)
            
            headers = {
                'Content-Type': 'application/json',
                'trakt-api-key': V2_API_KEY,
                'trakt-api-version': '2'
            }
            
            if auth and self.token:
                headers['Authorization'] = f'Bearer {self.token}'
            
            full_url = f'{self.protocol}{BASE_URL}{url}'
            method = method or ('POST' if data else 'GET')
            
            logger.log(f'Trakt Simple Call: {method} {full_url}', log_utils.LOGDEBUG)
            
            response = self._session.request(
                method=method,
                url=full_url,
                params=params,
                json=data,
                headers=headers,
                timeout=self.timeout or 30
            )
            
            if response.status_code == 401:
                # Try to refresh token once
                if hasattr(self, '_token_refresh_attempted'):
                    raise TraktAuthError('Authentication failed after token refresh')
                
                self._token_refresh_attempted = True
                refresh_result = self.refresh_token(kodi.get_setting('trakt_refresh_token'))
                if refresh_result and 'access_token' in refresh_result:
                    self.token = refresh_result['access_token']
                    kodi.set_setting('trakt_oauth_token', refresh_result['access_token'])
                    kodi.set_setting('trakt_refresh_token', refresh_result['refresh_token'])
                    
                    # Retry the request with new token
                    headers['Authorization'] = f'Bearer {self.token}'
                    response = self._session.request(
                        method=method,
                        url=full_url,
                        params=params,
                        json=data,
                        headers=headers,
                        timeout=self.timeout or 30
                    )
                else:
                    raise TraktAuthError('Token refresh failed')
            
            # Reset token refresh flag on success
            if hasattr(self, '_token_refresh_attempted'):
                delattr(self, '_token_refresh_attempted')
            
            response.raise_for_status()
            
            try:
                return response.json()
            except ValueError:
                return response.text
                
        except requests.exceptions.RequestException as e:
            logger.log(f'Trakt request error: {str(e)}', log_utils.LOGERROR)
            raise TraktError(f'Trakt request failed: {str(e)}')

    def get_show_play_counts(self, trakt_id):
        url = f'/shows/{trakt_id}/progress/watched'
        return self.__call_trakt(url, params={'extended':'plays'})

    def __sync_activities_after_change(self, changed_type, section):
        """Efficiently sync only what changed, similar to POV's approach"""
        try:
            # Get latest activity timestamp
            activity = self.get_last_activity()
            if not activity:
                return
                
            # Use the new efficient cache clearing methods
            db_connection = self.__get_db_connection()
            
            if changed_type == 'collection':
                media_type = 'movies' if section == SECTIONS.MOVIES else 'episodes'
                # Use new efficient cache clearing
                if hasattr(db_connection, 'clear_collection_cache'):
                    db_connection.clear_collection_cache(media_type)
                else:
                    # Fallback to URL pattern clearing
                    self.__clear_cache_pattern(f'/users/me/collection/{media_type}')
                    self.__clear_cache_pattern(f'/sync/collection')
                    
            elif changed_type == 'watchlist':
                media_type = 'movies' if section == SECTIONS.MOVIES else 'shows'
                # Use new efficient cache clearing
                if hasattr(db_connection, 'clear_watchlist_cache'):
                    db_connection.clear_watchlist_cache(media_type)
                else:
                    # Fallback to URL pattern clearing
                    self.__clear_cache_pattern(f'/users/me/watchlist/{media_type}')
                    self.__clear_cache_pattern(f'/sync/watchlist')
                    
        except Exception as e:
            logger.log(f'Cache sync error: {str(e)}', log_utils.LOGDEBUG)

    def __clear_cache_pattern(self, pattern):
        """Clear cache entries matching a URL pattern"""
        try:
            db_connection = self.__get_db_connection()
            # Clear cache entries that contain the pattern
            sql = 'DELETE FROM url_cache WHERE url LIKE ?'
            db_connection.__execute(sql, (f'%{pattern}%',))
            logger.log(f'Cleared cache entries matching: {pattern}', log_utils.LOGDEBUG)
        except Exception as e:
            logger.log(f'Error clearing cache pattern {pattern}: {str(e)}', log_utils.LOGDEBUG)

    def __call_trakt_optimized(self, url: str, method: str = None, data: Any = None, params: dict = None, auth: bool = True, cache_limit: float = .25, cached: bool = True) -> Union[str, list, dict, Any]:
        """Use optimized HTTP handler when enabled"""
        if self.use_optimized_methods:
            try:
                # Use the new simple HTTP handler for better performance
                return self.__call_trakt_simple(url, method, data, params, auth)
            except Exception as e:
                logger.log(f'Optimized call failed, falling back to original: {str(e)}', log_utils.LOGDEBUG)
                
        # Fall back to original method
        return self.__call_trakt(url, method, data, params, auth, cache_limit, cached)

def trakt_expires(func):
    def wrapper(*args, **kwargs):
        if kodi.get_setting('trakt_refresh_token'):
            expires = float(kodi.get_setting('trakt_expires', '0'))
            if (expires - time.time()) < 28800:  # 8 hours
                self = args[0]  # instance method
                self.refresh_token(kodi.get_setting('trakt_refresh_token'))
        return func(*args, **kwargs)
    return wrapper