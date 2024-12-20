"""
    Asguard Addon
    Copyright (C) 2024 MrBlamo

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

import io, urllib.parse, urllib.request, urllib.error

import requests, urllib3, cache
import xbmcaddon
import os, ssl, socket, json, zipfile, time, six

from bs4 import BeautifulSoup
import utils
import log_utils
import kodi
from asguard_lib import utils2, client

from asguard_lib.db_utils import DB_Connection
from asguard_lib.constants import VIDEO_TYPES
import xml.etree.ElementTree as ET
import logging
logger = log_utils.Logger.get_logger(__name__)

# Since the image_cache module is now local, we can directly import it
from . import image_cache

logging.basicConfig(level=logging.DEBUG)
# Add this at the top of the file, after the imports
CACHE_INSTALLED = 'image_cache' in globals()

db_connection = DB_Connection()
PLACE_POSTER = os.path.join(kodi.get_path(), 'resources', 'place_poster.png')
DEFAULT_FANART = utils2.art('fanart.jpg')
OMDB_ENABLED = kodi.get_setting('omdb_enable') == 'true'
TVMAZE_ENABLED = kodi.get_setting('tvmaze_enable') == 'true'
FANARTTV_ENABLED = kodi.get_setting('fanart_enable') == 'true'
BG_ENABLED = kodi.get_setting('bg_enable') == 'true'
POSTER_ENABLED = kodi.get_setting('poster_enable') == 'true'
BANNER_ENABLED = kodi.get_setting('banner_enable') == 'true'
CLEARART_ENABLED = kodi.get_setting('clearart_enable') == 'true'
THUMB_ENABLED = kodi.get_setting('thumb_enable') == 'true'
OMDB_API = kodi.get_setting('omdb_api')
GIF_ENABLED = False

ZIP_CACHE = 24
OBJ_PERSON = 'person'
PROXY_TEMPLATE = 'http://127.0.0.1:{port}{action}'

class Scraper(object):
    protocol = 'http://'
    
    def _clean_art(self, art_dict):
        new_dict = {}
        for key in art_dict:
            if art_dict[key]:
                scheme, netloc, path, params, query, fragment = urllib.parse.urlparse(art_dict[key])
                new_dict[key] = urllib.parse.urlunparse((scheme, netloc, urllib.parse.quote(path), params, query, fragment))
        return new_dict
    
    def _get_url(self, url, params=None, data=None, headers=None, cache_limit=1):
        if headers is None: headers = {}
        if data is not None:
            if isinstance(data, six.string_types):
                data = data
                logger.log('Data: %s' % (data), log_utils.LOGDEBUG)
            else:
                data = urllib.parse.urlencode(data, True)
                logger.log('Data: %s' % (data), log_utils.LOGDEBUG)
        if not url.startswith('http'):
            url = '%s%s%s' % (self.protocol, self.BASE_URL, url)
            logger.log('URL: %s' % (url), log_utils.LOGDEBUG)
        if params: 
            url += '?' + urllib.parse.urlencode(params)
        _created, cached_headers, html = db_connection.get_cached_url(url, data, cache_limit=cache_limit)
        if html:
            logger.log('Using Cached result for: %s' % (url))
            result = html
            res_headers = dict(cached_headers)
            logger.log('Result: %s' % (result), log_utils.LOGDEBUG)
        else:
            try:
                headers['Accept-Encoding'] = 'gzip'
                logger.log('+++Image Scraper Call: %s, header: %s, data: %s cache_limit: %s' % (url, headers, data, cache_limit), log_utils.LOGDEBUG)
                request = urllib.request.Request(url, data=data, headers=headers)
                logger.log('Request: %s' % (request), log_utils.LOGDEBUG)
                response = urllib.request.urlopen(request)
                result = b''
                while True:
                    data = response.read()
                    if not data: break
                    result += data
                res_headers = dict(response.info().items())
                if res_headers.get('content-encoding') == 'gzip':
                    result = utils2.ungz(result)
                db_connection.cache_url(url, result, data, res_header=res_headers)
            except (ssl.SSLError, socket.timeout) as e:
                logger.log('Image Scraper Timeout: %s' % (url))
                return {}
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    logger.log('HTTP Error (%s) during image scraper http get: %s' % (e, url), log_utils.LOGWARNING)
                return {}
            except Exception as e:
                logger.log('Error (%s) during image scraper http get: %s' % (str(e), url), log_utils.LOGWARNING)
                return {}

        try:
            if 'application/json' in res_headers.get('content-type', ''):
                return_data = utils.json_loads_as_str(result)
            else:
                # try/except to handle older responses that might be missing headers
                try: return_data = utils.json_loads_as_str(result)
                except ValueError: return_data = result
        except ValueError:
            return_data = ''
            if result:
                logger.log('Invalid JSON API Response: %s - |%s|' % (url, return_data), log_utils.LOGERROR)

        return return_data
        
class FanartTVScraper(Scraper):
    API_KEY = kodi.get_setting('fanart_key')
    CLIENT_KEY = kodi.get_setting('fanart_person_key')
    BASE_URL = 'http://webservice.fanart.tv/v3'
    LANGS = {'en': 3, '00': 1, '': 2}

    def __init__(self):
        self.headers = {'api-key': self.API_KEY}
        if self.CLIENT_KEY:
            self.headers.update({'client-key': self.CLIENT_KEY})
        
    def get_movie_images(self, ids):
        art_dict = {}
        video_id = ids.get('tmdb') or ids.get('imdb')
        any_art = any((BG_ENABLED, BANNER_ENABLED, POSTER_ENABLED, CLEARART_ENABLED))
        if FANARTTV_ENABLED and self.API_KEY and any_art and video_id:
            url = f'{self.BASE_URL}/movies/{video_id}'
            images = self._get_url(url, headers=self.headers)
            if BG_ENABLED:
                art_dict['fanart'] = self.__get_best_image(images.get('moviebackground', []))

            if THUMB_ENABLED:
                art_dict['thumb'] = self.__get_best_image(images.get('moviethumb', []))

            if BANNER_ENABLED:
                art_dict['banner'] = self.__get_best_image(images.get('moviebanner', []))

            if POSTER_ENABLED:
                art_dict['poster'] = self.__get_best_image(images.get('movieposter', []))

            if CLEARART_ENABLED:
                art_dict['clearlogo'] = self.__get_best_image(images.get('hdmovielogo', []))
                if not art_dict['clearlogo']: art_dict['clearlogo'] = self.__get_best_image(images.get('movielogo', []))
                art_dict['clearart'] = self.__get_best_image(images.get('hdmovieclearart', []))
        
        return self._clean_art(art_dict)
    
    def get_tvshow_images(self, ids):
        art_dict = {}
        video_id = ids.get('tvdb') or ids.get('imdb') or ids.get('trakt')
        any_art = any((BG_ENABLED, BANNER_ENABLED, POSTER_ENABLED, CLEARART_ENABLED, THUMB_ENABLED))
        if FANARTTV_ENABLED and self.API_KEY and 'tvdb' in ids and ids['tvdb'] and video_id and any_art:
            url = f'{self.BASE_URL}/tv/{video_id}'
            images = self._get_url(url, headers=self.headers)
            if BG_ENABLED:
                art_dict['fanart'] = self.__get_best_image(images.get('showbackground', []))

            if THUMB_ENABLED:
                art_dict['thumb'] = self.__get_best_image(images.get('tvthumb', []))

            if BANNER_ENABLED:
                art_dict['banner'] = self.__get_best_image(images.get('tvbanner', []))

            if POSTER_ENABLED:
                art_dict['poster'] = self.__get_best_image(images.get('tvposter', []))

            if CLEARART_ENABLED:
                art_dict['clearlogo'] = self.__get_best_image(images.get('hdtvlogo', []))
                if not art_dict['clearlogo']: art_dict['clearlogo'] = self.__get_best_image(images.get('clearlogo', []))
                art_dict['clearart'] = self.__get_best_image(images.get('hdclearart', []))
                if not art_dict['clearart']: art_dict['clearart'] = self.__get_best_image(images.get('clearart', []))
        
        return self._clean_art(art_dict)
    
    def get_season_images(self, ids):
        season_art = {}
        video_id = ids.get('tvdb') or ids.get('imdb') or ids.get('trakt') or ids.get('tmdb') or ids.get('code')
        any_art = any((BANNER_ENABLED, POSTER_ENABLED, THUMB_ENABLED))
        if FANARTTV_ENABLED and self.API_KEY and 'tvdb' in ids and ids['tvdb'] and video_id and any_art:
            url = f'{self.BASE_URL}/tv/{video_id}'
            images = self._get_url(url, headers=self.headers)
            seasons = set()
            for name in ['seasonposter', 'seasonthumb', 'seasonbanner']:
                seasons |= set([i['season'] for i in images.get(name, [])])

            for season in seasons:
                art_dict = {}
                if POSTER_ENABLED:
                    art_dict['poster'] = self.__get_best_image(images.get('seasonposter', []), season)

                if BANNER_ENABLED:
                    art_dict['banner'] = self.__get_best_image(images.get('seasonbanner', []), season)

                if THUMB_ENABLED:
                    art_dict['thumb'] = self.__get_best_image(images.get('seasonthumb', []), season)
                season_art[season] = self._clean_art(art_dict)
                
        return season_art
    
    def _extract_art(self, images, type_prefix):
        art_dict = {}
        if BG_ENABLED:
            art_dict['fanart'] = self.__get_best_image(images.get(f'{type_prefix}background', []))
        if THUMB_ENABLED:
            art_dict['thumb'] = self.__get_best_image(images.get(f'{type_prefix}thumb', []))
        if BANNER_ENABLED:
            art_dict['banner'] = self.__get_best_image(images.get(f'{type_prefix}banner', []))
        if POSTER_ENABLED:
            art_dict['poster'] = self.__get_best_image(images.get(f'{type_prefix}poster', []))
        if CLEARART_ENABLED:
            art_dict['clearlogo'] = self.__get_best_image(images.get(f'hdtvlogo', []), fallback_key=f'{type_prefix}logo')
            art_dict['clearart'] = self.__get_best_image(images.get(f'hdclearart', []), fallback_key=f'{type_prefix}clearart')
        return art_dict

    def _extract_season_art(self, images):
        season_art = {}
        seasons = set()
        for name in ['seasonposter', 'seasonthumb', 'seasonbanner']:
            seasons |= set([i['season'] for i in images.get(name, [])])
        
        for season in seasons:
            art_dict = {}
            if POSTER_ENABLED:
                art_dict['poster'] = self.__get_best_image(images.get('seasonposter', []), season)
            if BANNER_ENABLED:
                art_dict['banner'] = self.__get_best_image(images.get('seasonbanner', []), season)
            if THUMB_ENABLED:
                art_dict['thumb'] = self.__get_best_image(images.get('seasonthumb', []), season)
            season_art[season] = self._clean_art(art_dict)
        
        return season_art
    
    def __get_best_image(self, images, season=None, fallback_key=None):
        best = None
        images = [image for image in images if image.get('lang') in ('en', '00', '', 'ja')]
        if season is not None:
            images = [image for image in images if image.get('season') == season]
        if not images and fallback_key:
            images = [image for image in images if image.get('lang') in ('en', '00', '')]
        
        images.sort(key=lambda x: (self.LANGS.get(x.get('lang'), 0), int(x['likes'])), reverse=True)
        if images:
            best = images[0]['url']
        return best

    def _get_url(self, url, headers=None):
        req = urllib.request.Request(url, headers=headers or {})
        try:
            with urllib.request.urlopen(req) as response:
                # Decode the byte response to string using utf-8 encoding
                result = response.read().decode('utf-8')
                return json.loads(result)
        except Exception as e:
            logger.log(f'Error during HTTP GET: {e}', log_utils.LOGERROR)
            return {}

    @staticmethod
    def _get_image_size(art):
        if art in ('hdtvlogo', 'hdclearart', 'hdmovielogo', 'hdmovieclearart'):
            return 800
        elif art in ('clearlogo', 'clearart', 'movielogo', 'movieart', 'musiclogo'):
            return 400
        elif art in ('tvbanner', 'seasonbanner', 'moviebanner'):
            return 1000
        elif art in ('showbackground', 'moviebackground'):
            return 1920
        elif art in ('tvposter', 'seasonposter', 'movieposter'):
            return 1426
        elif art in ('tvthumb', 'seasonthumb'):
            return 500
        elif art == 'characterart':
            return 512
        elif art == 'moviethumb':
            return 1000
        return 0


class TMDBScraper(Scraper):
    API_KEY = kodi.get_setting('tmdb_key')
    protocol = 'https://'
    BASE_URL = 'api.themoviedb.org/3'
    headers = {'Content-Type': 'application/json'}
    size = 'original'
    image_base = None

    def _get_url(self, url, params=None, headers=None, cache_limit=None):
        if params:
            url += '?' + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=headers or {})
        try:
            with urllib.request.urlopen(req) as response:
                return json.loads(response.read().decode())
        except Exception as e:
            return {}

    def __get_image_base(self):
        if self.API_KEY:
            if self.image_base is None:
                url = f'{self.protocol}{self.BASE_URL}/configuration'
                params = {'api_key': self.API_KEY}
                js_data = self._get_url(url, params, headers=self.headers, cache_limit=24)
                try: 
                    self.image_base = f"{js_data['images']['base_url']}{self.size}/"
                except KeyError: 
                    self.image_base = None
        else:
            self.image_base = None
        return self.image_base
            
    def get_movie_images(self, ids, need=None):
        if need is None: need = ['fanart', 'poster']
        art_dict = {}
        any_art = any((BG_ENABLED, POSTER_ENABLED))
        if 'tmdb' in ids and ids['tmdb'] and any_art and self.__get_image_base():
            images = image_cache.get_movie_images(ids['tmdb']) if CACHE_INSTALLED else {}
            if not images:
                url = f'{self.protocol}{self.BASE_URL}/movie/{ids["tmdb"]}/images'
                params = {'api_key': self.API_KEY, 'include_image_language': 'en,null'}
                images = self._get_url(url, params, headers=self.headers)
                
            if BG_ENABLED and 'fanart' in need:
                art_dict['fanart'] = self.__get_best_image(images.get('backdrops', []))
            
            if POSTER_ENABLED and 'poster' in need:
                art_dict['poster'] = self.__get_best_image(images.get('posters', []))

        return self._clean_art(art_dict)
    
    def get_tmdbshow_images(self, ids, need=None):
        if need is None: need = ['fanart', 'poster']
        art_dict = {}
        any_art = any((BG_ENABLED, POSTER_ENABLED))
        if 'tmdb' in ids and ids['tmdb'] and any_art and self.__get_image_base():
            images = image_cache.get_tv_images(ids['tmdb']) if CACHE_INSTALLED else {}
            if not images:
                url = f'{self.protocol}{self.BASE_URL}/tv/{ids["tmdb"]}/images'
                params = {'api_key': self.API_KEY, 'include_image_language': 'en,null'}
                images = self._get_url(url, params, headers=self.headers)
                
            if BG_ENABLED and 'fanart' in need:
                art_dict['fanart'] = self.__get_best_image(images.get('backdrops', []))
            
            if POSTER_ENABLED and 'poster' in need:
                art_dict['poster'] = self.__get_best_image(images.get('posters', []))

        return self._clean_art(art_dict)

    def get_person_images(self, ids):
        person_art = {}
        if 'tmdb' in ids and ids['tmdb'] and self.__get_image_base():
            images = image_cache.get_person_images(ids['tmdb']) if CACHE_INSTALLED else {}
            if not images:
                url = f'{self.protocol}{self.BASE_URL}/person/{ids["tmdb"]}/images'
                params = {'api_key': self.API_KEY, 'include_image_language': 'en,null'}
                images = self._get_url(url, params, headers=self.headers, cache_limit=30)
                
            person_art['thumb'] = self.__get_best_image(images.get('profiles', []))
        return self._clean_art(person_art)
            
    def __get_best_image(self, images):
        best = None
        if images:
            images.sort(key=lambda x: x['width'], reverse=True)
            best = images[0]['file_path']
        
        if best:
            best = f"{self.image_base}{best}"
            
        return best
    

class TVDBScraper(Scraper):
    API_KEY = kodi.get_setting('tvdb_key')  # Ensure this setting name matches the one used in settings.xml for the new API key
    protocol = 'https://'
    BASE_URL = 'api.thetvdb.com'
    ZIP_URL = 'thetvdb.com'
    EP_CACHE = {}
    CAST_CACHE = {}
    headers = {'Content-Type': 'application/json'}
    image_base = 'http://thetvdb.com/banners/'
    token = None
    
    def __get_token(self):
        if self.API_KEY:
            if self.token is None:
                url = '/login'
                data = {'apikey': self.API_KEY}
                js_data = self._get_url(url, data=json.dumps(data), headers=self.headers)
                self.token = js_data.get('token')
                self.headers.update({'Authorization': 'Bearer %s' % (self.token)})
        else:
            self.token = None
        
        return self.token
        
    def get_tvshow_images(self, ids, need=None):
        art_dict = {}
        if need is None: need = ['fanart', 'poster', 'banner']
        any_art = any((BG_ENABLED, POSTER_ENABLED, BANNER_ENABLED))
        if 'tvdb' in ids and ids['tvdb'] and self.API_KEY and any_art:
            images = self.__get_images(self.__get_xml(ids['tvdb'], 'banners.xml'))
            if BG_ENABLED and 'fanart' in need:
                art_dict['fanart'] = self.__get_best_image(images.get('fanart', []))
            
            if POSTER_ENABLED and 'poster' in need:
                art_dict['poster'] = self.__get_best_image(images.get('poster', []))
    
            if BANNER_ENABLED and 'banner' in need:
                art_dict['banner'] = self.__get_best_image(images.get('series', []))
            
        return self._clean_art(art_dict)
    
    def get_tvshow_images_v2(self, ids, need=None):
        art_dict = {}
        if need is None: need = ['fanart', 'poster', 'banner']
        any_art = any((BG_ENABLED, POSTER_ENABLED, BANNER_ENABLED))
        if 'tvdb' in ids and ids['tvdb'] and any_art and self.__get_token():
            url = '/series/%s/images/query' % (ids['tvdb'])
            if BG_ENABLED and 'fanart' in need:
                params = {'keyType': 'fanart'}
                images = self._get_url(url, params, headers=self.headers)
                art_dict['fanart'] = self.__get_best_image(images.get('data', []))
            
            if POSTER_ENABLED and 'poster' in need:
                params = {'keyType': 'poster'}
                images = self._get_url(url, params, headers=self.headers)
                art_dict['poster'] = self.__get_best_image(images.get('data', []))
            
            if BANNER_ENABLED and 'banner' in need:
                params = {'keyType': 'series'}
                images = self._get_url(url, params, headers=self.headers)
                art_dict['banner'] = self.__get_best_image(images.get('data', []))
            
        return self._clean_art(art_dict)
    
    def get_season_images(self, ids, need=None):
        season_art = {}
        if need is None: need = ['poster', 'banner']
        any_art = any((BANNER_ENABLED, POSTER_ENABLED))
        if 'tvdb' in ids and ids['tvdb'] and self.API_KEY and any_art:
            images = self.__get_images(self.__get_xml(ids['tvdb'], 'banners.xml'))
            logger.log('images: %s' % images)
            seasons = set([image['subKey'] for image in images.get('season', [])])
            seasons |= set([image['subKey'] for image in images.get('seasonwide', [])])
            
            for season in seasons:
                art_dict = {}
                if POSTER_ENABLED:
                    art_dict['poster'] = self.__get_best_image(images.get('season', []), season)
                
                if BANNER_ENABLED:
                    art_dict['banner'] = self.__get_best_image(images.get('seasonwide', []), season)
                    
                season_art[season] = self._clean_art(art_dict)
                
        return season_art
        
    def get_season_images_v2(self, ids, need=None):
        season_art = {}
        if need is None: need = ['poster', 'banner']
        any_art = any((BANNER_ENABLED, POSTER_ENABLED))
        if 'tvdb' in ids and ids['tvdb'] and any_art and self.__get_token():
            url = '/series/%s/images/query' % (ids['tvdb'])
            images = {}
            seasons = set()
            if POSTER_ENABLED and 'poster' in need:
                params = {'keyType': 'season'}
                images['season'] = self._get_url(url, params, headers=self.headers).get('data', [])
                seasons |= set([i['subKey'] for i in images.get('season', [])])
            
            if BANNER_ENABLED and 'banner' in need:
                params = {'keyType': 'seasonwide'}
                images['seasonwide'] = self._get_url(url, params, headers=self.headers).get('data', [])
                seasons |= set([i['subKey'] for i in images.get('seasonwide', [])])
                
            for season in seasons:
                art_dict = {}
                art_dict['poster'] = self.__get_best_image(images.get('season', []), season)
                art_dict['banner'] = self.__get_best_image(images.get('seasonwide', []), season)
                season_art[season] = self._clean_art(art_dict)
                
        return season_art
    
    def get_episode_images(self, ids, season, episode):
        ep_art = {}
        if 'tvdb' in ids and ids['tvdb'] and self.API_KEY and THUMB_ENABLED:
            tvdb = ids['tvdb']
            season = int(season)
            episode = int(episode)
            try: TVDBScraper.EP_CACHE[tvdb][season]
            except KeyError: self.__build_ep_cache(tvdb, season)

            try: ep_art['thumb'] = self.image_base + TVDBScraper.EP_CACHE[tvdb][season][episode]
            except KeyError: pass
                
        return ep_art
        
    def get_cast(self, tvdb):
        cast = []
        if tvdb in TVDBScraper.CAST_CACHE:
            cast = TVDBScraper.CAST_CACHE[tvdb]
        elif self.API_KEY and self.__zip_is_cached(tvdb):
            xml = self.__get_xml(tvdb, 'actors.xml')
            for actor in ET.fromstring(xml).findall('.//Actor'):
                name = actor.findtext('Name')
                role = actor.findtext('Role')
                thumbnail = actor.findtext('Image')
                if name and role:
                    if thumbnail:
                        thumbnail = self.image_base + thumbnail
                    cast.append({'name': name, 'role': role, 'thumb': thumbnail})
            TVDBScraper.CAST_CACHE[tvdb] = cast

        return cast
    
    def __zip_is_cached(self, tvdb):
        url = 'http://thetvdb.com/api/%s/series/%s/all/en.zip ' % (self.API_KEY, tvdb)
        created, _res_header, _html = db_connection.get_cached_url(url)
        return time.time() - created < ZIP_CACHE * 60 * 60
        
    def __build_ep_cache(self, tvdb, season=None):
        show_dict = TVDBScraper.EP_CACHE.setdefault(tvdb, {})
        xml = self.__get_xml(tvdb, 'en.xml')
        
        # can't use predicates yet because ET 1.3 is Python 2.7
        for item in ET.fromstring(xml).findall('.//Episode'):
            try: item_season = int(item.findtext('SeasonNumber', -1))
            except: continue
            try: item_episode = int(item.findtext('EpisodeNumber', -1))
            except: continue
            thumb = item.findtext('filename')
            if (season is None or int(season) == item_season) and thumb:
                season_dict = show_dict.setdefault(item_season, {})
                season_dict[item_episode] = thumb
    
    def __get_xml(self, tvdb, file_name):
        xml = '<xml/>'
        if self.API_KEY:
            url = 'http://thetvdb.com/api/%s/series/%s/all/en.zip ' % (self.API_KEY, tvdb)
            zip_data = self._get_url(url, cache_limit=ZIP_CACHE)
            if zip_data:
                try:
                    with zipfile.ZipFile(io.BytesIO(zip_data), 'r') as zip_file:
                        xml = zip_file.read(file_name).decode('utf-8')
                except zipfile.BadZipFile:
                    logger.log('TVDB Zip Error: Bad Zip File', log_utils.LOGWARNING)
                except UnicodeDecodeError:
                    logger.log('TVDB Zip Error: Unicode Decode Error', log_utils.LOGWARNING)
        return xml
        
    def __get_images(self, xml):
        images = {}
        for image_ele in ET.fromstring(xml).findall('.//Banner'):
            language = image_ele.findtext('Language')
            if language == 'en' or not language:
                image_type = image_ele.findtext('BannerType')
                if image_type == 'season':
                    image_type = image_ele.findtext('BannerType2')
                    resolution = 0
                else:
                    resolution = image_ele.findtext('BannerType2')
                    
                if image_type:
                    subKey = image_ele.findtext('Season')
                    file_name = image_ele.findtext('BannerPath')
                    try: 
                        average = float(image_ele.findtext('Rating'))
                    except: 
                        average = 0.0
                    try: 
                        count = int(image_ele.findtext('RatingCount'))
                    except: 
                        count = 0
                    image = {'subKey': subKey, 'resolution': resolution, 'ratingsInfo': {'average': average, 'count': count}, 'fileName': file_name}
                    images.setdefault(image_type, []).append(image)
        
        return images
        
    def __get_best_image(self, images, season=None):
        best = None
        if season is not None:
            images = [image for image in images if image['subKey'] == season]
                
        if images:
            images.sort(key=lambda x: (x['resolution'], x['ratingsInfo']['average'], x['ratingsInfo']['count']), reverse=True)
            best = images[0]['fileName']
            
        if best:
            best = self.image_base + best
            
        return best

class TVDBAPI(Scraper):
    def __init__(self):
        self.apiKey = {'apikey': '83914568-d055-4943-a789-4175d6466b05'}
        self.headers = {'User-Agent': 'Asguard'}
        self.baseUrl = 'https://api4.thetvdb.com/v4/'
        self.art = {}
        self.request_response = None
        self.threads = []

    def get_token(self):
        res = client.request(
            self.baseUrl + 'login',
            headers=self.headers,
            post=self.apiKey,
            jpost=True
        )
        data = json.loads(res)
        return data['data'].get('token')

    def get_request(self, url):
        token = cache.get(self.get_token, 24)
        self.headers.update({'Authorization': 'Bearer {0}'.format(token)})
        url = self.baseUrl + url

        response = client.request(url, headers=self.headers)
        if response:
            response = json.loads(response).get('data')
            self.request_response = response
            return response
        else:
            return None

    def get_imdb_id(self, tvdb_id):
        imdb_id = None
        url = 'series/{}/extended'.format(tvdb_id)
        data = self.get_request(url)
        if data:
            imdb_id = [x.get('id') for x in data['remoteIds'] if x.get('type') == 2]
        return imdb_id[0] if imdb_id else None

    def get_seasons(self, tvdb_id):
        url = 'seasons/{}/extended'.format(tvdb_id)
        data = self.get_request(url)
        return data

class TVMazeScraper(Scraper):
    BASE_URL = 'api.tvmaze.com'
    
    def _get_url(self, url, params=None, data=None, headers=None, cache_limit=1):
        if headers is None: headers = {}
        if data is not None:
            if isinstance(data, six.string_types):
                data = data
                logger.log('Data: %s' % (data), log_utils.LOGDEBUG)
            else:
                data = urllib.parse.urlencode(data, True)
                logger.log('Data: %s' % (data), log_utils.LOGDEBUG)
        if not url.startswith('http'):
            url = '%s%s%s' % (self.protocol, self.BASE_URL, url)
            logger.log('URL: %s' % (url), log_utils.LOGDEBUG)
        if params: 
            url += '?' + urllib.parse.urlencode(params)
        _created, cached_headers, html = db_connection.get_cached_url(url, data, cache_limit=cache_limit)
        if html:
            logger.log('Using Cached result for: %s' % (url))
            result = html
            res_headers = dict(cached_headers)
            logger.log('Result: %s' % (result), log_utils.LOGDEBUG)
        else:
            try:
                headers['Accept-Encoding'] = 'gzip'
                logger.log('+++Image Scraper Call: %s, header: %s, data: %s cache_limit: %s' % (url, headers, data, cache_limit), log_utils.LOGDEBUG)
                request = urllib.request.Request(url, data=data, headers=headers)
                logger.log('Request: %s' % (request), log_utils.LOGDEBUG)
                response = urllib.request.urlopen(request)
                result = ''
                while True:
                    data = response.read()
                    if not data: break
                    result += data
                res_headers = dict(response.info().items())
                if res_headers.get('content-encoding') == 'gzip':
                    result = utils2.ungz(result)
                db_connection.cache_url(url, result, data, res_header=res_headers)
            except (ssl.SSLError, socket.timeout) as e:
                logger.log('Image Scraper Timeout: %s' % (url))
                return {}
            except urllib.error.HTTPError as e:
                if e.code != 404:
                    logger.log('HTTP Error (%s) during image scraper http get: %s' % (e, url), log_utils.LOGWARNING)
                return {}
            except Exception as e:
                logger.log('Error (%s) during image scraper http get: %s' % (str(e), url), log_utils.LOGWARNING)
                return {}

        try:
            if 'application/json' in res_headers.get('content-type', ''):
                return_data = utils.json_loads_as_str(result)
            else:
                # try/except to handle older responses that might be missing headers
                try: return_data = utils.json_loads_as_str(result)
                except ValueError: return_data = result
        except ValueError:
            return_data = ''
            if result:
                logger.log('Invalid JSON API Response: %s - |%s|' % (url, return_data), log_utils.LOGERROR)

        return return_data

    def get_episode_images(self, ids, season, episode):
        art_dict = {}
        if not TVMAZE_ENABLED or not THUMB_ENABLED:
            return art_dict
        
        if 'tvdb' in ids and ids['tvdb']:
            key = 'thetvdb'
            video_id = ids['tvdb']
        elif 'imdb' in ids and ids['imdb']:
            key = 'imdb'
            video_id = ids['imdb']
        elif 'tvrage' in ids and ids['tvrage']:
            key = 'tvrage'
            video_id = ids['tvrage']
        elif 'tmdb' in ids and ids['tmdb']:
            key = 'tmdb'
            video_id = ids['tmdb']
        else:
            return art_dict
        
        url = '/lookup/shows'
        params = {key: video_id}
        js_data = self._get_url(url, params, cache_limit=24 * 7)
        if 'id' in js_data and js_data['id']:
            art_dict['poster'] = self.__get_image(js_data)
            url = '/shows/%s/episodes' % (js_data['id'])
            for ep_item in self._get_url(url, cache_limit=24):
                if ep_item['season'] == int(season) and ep_item['number'] == int(episode):
                    art_dict['thumb'] = self.__get_image(ep_item)
                    break
                
        return self._clean_art(art_dict)
    
    def __get_image(self, item):
        image = item.get('image', {})
        image = image.get('original') if image else None
        return image

class IMDBScraper(Scraper):
    BASE_URL = 'https://www.imdb.com'

    def get_movie_images(self, imdb_id):
        art_dict = {}
        url = f'{self.BASE_URL}/title/{imdb_id}/mediaindex'
        images = self._scrape_images(url)
        if images:
            art_dict['poster'] = images.get('poster')
            art_dict['fanart'] = images.get('fanart')
            art_dict['banner'] = images.get('banner')
        return self._clean_art(art_dict)

    def get_tvshow_images(self, imdb_id):
        art_dict = {}

        imdb_id = imdb_id.get('imdb')
        url = f'{self.BASE_URL}/title/{imdb_id}/mediaindex'
        images = self._scrape_images(url)
        if images:
            art_dict['poster'] = images.get('poster')
            art_dict['fanart'] = images.get('fanart')
            art_dict['banner'] = images.get('banner')
        return self._clean_art(art_dict)

    def get_episode_images(self, imdb_id, season, episode):
        art_dict = {}

        imdb_id = imdb_id.get('imdb')
        url = f'{self.BASE_URL}/title/{imdb_id}/episodes?season={season}&episode={episode}'
        images = self._scrape_images(url)
        if images:
            art_dict['thumb'] = images.get('thumb')
            art_dict['banner'] = images.get('banner')
        return self._clean_art(art_dict)

    def _scrape_images(self, url):
        headers = {'User-Agent': 'Mozilla/5.0'}
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req) as response:
                html = response.read()
                soup = BeautifulSoup(html, 'html.parser')
                images = {}
                poster = soup.find('img', {'class': 'poster'})
                if poster:
                    images['poster'] = poster['src']
                fanart = soup.find('img', {'class': 'fanart'})
                if fanart:
                    images['fanart'] = fanart['src']
                thumb = soup.find('img', {'class': 'thumb'})
                if thumb:
                    images['thumb'] = thumb['src']
                banner = soup.find('img', {'class': 'banner'})
                if banner:
                    images['banner'] = banner['src']
                return images
        except Exception as e:
            logger.log(f'Error scraping IMDb images: {e}', log_utils.LOGERROR)
            return {}

class OMDBScraper(Scraper):
    BASE_URL = 'http://www.omdbapi.com/'
    
    def get_images(self, ids):
        art_dict = {}
        omdb_api_key = OMDB_API
        if 'imdb' in ids and ids['imdb'] and OMDB_ENABLED and POSTER_ENABLED:
            url = ''
            params = {'i': ids['imdb'], 'plot': 'short', 'r': 'json'}
            images = self._get_url(url, params)
            if 'Poster' in images and images['Poster'].startswith('http'):
                art_dict['poster'] = images['Poster']
        return self._clean_art(art_dict)

fanart_scraper = FanartTVScraper()
imdb_scraper = IMDBScraper()
tvdbapi_scraper = TVDBAPI()
tvdb_scraper = TVDBScraper()
tmdb_scraper = TMDBScraper()
def get_person_images(video_ids, person, cached=True):
    ids = person['person']['ids']
    person_art = {}
    if 'tmdb' in ids and ids['tmdb']:
        person_art.update(tmdb_scraper.get_person_images(ids))
    elif 'tvdb' in ids and ids['tvdb']:
        return person_art
    else:
        return scrape_person_images(video_ids, person, cached)

def scrape_person_images(video_ids, person, cached=True):
    person_art = {}
    ids = person['person']['ids']
    if cached:
        cached_art = db_connection.get_cached_images(OBJ_PERSON, ids['trakt'])
        if cached_art:
            person_art.update(cached_art)
    else:
        cached_art = {}
    
    if not cached_art:
        logger.log('Getting person images for |%s| in media |%s|' % (person, video_ids), log_utils.LOGDEBUG)
        tried = False
        if not person_art['thumb'] and 'tvdb' in video_ids and video_ids['tvdb']:
            norm_name = utils2.normalize_title(person['person']['name'])
            for member in tvdb_scraper.get_cast(video_ids['tvdb']):
                tried = True
                if norm_name == utils2.normalize_title(member['name']):
                    logger.log('Found %s as |%s| in %s' % (person['person']['name'], norm_name, video_ids))
                    person_art['thumb'] = member['thumb']
                    break
        
        if not person_art['thumb'] and 'tmdb' in ids and ids['tmdb']:
            tried = True
            person_art.update(tmdb_scraper.get_person_images(ids))
        
        # cache the person's art if we tried to get the art
        if tried: db_connection.cache_images(OBJ_PERSON, ids['trakt'], person_art)
            
    return person_art

def clear_cache(video_type, video_ids, season='', episode=''):
    trakt_id = video_ids['trakt']
    port = kodi.get_setting('proxy_port')
    params = {'video_type': video_type, 'trakt_id': trakt_id, 'video_ids': video_ids}
        
    if video_type == VIDEO_TYPES.SEASON or video_type == VIDEO_TYPES.EPISODE:
        params['season'] = season
    
    if video_type == VIDEO_TYPES.EPISODE:
        params['episode'] = episode
        
    url = PROXY_TEMPLATE.format(port=port, action='/clear') + '?' + urllib.parse.urlencode(params)
    try: 
        res = urllib.request.urlopen(url, timeout=30).read()
    except Exception as e: 
        logger.log(f"Failed to clear cache: {str(e)}", log_utils.LOGWARNING)
        res = ''
    return res == 'OK'


def get_images(video_type, video_ids, season='', episode='', cached=True):
    art_dict = {}
    max_retries = 3
    retry_delay = 5  # seconds

    if isinstance(video_ids, int):
        trakt_id = video_ids['trakt']
        video_ids = json.dumps(video_ids)
        image_types = ['poster', 'fanart', 'thumb', 'banner', 'clearart', 'clearlogo', 'seasonbanner', 'seasonposter']
        
        for image_type in image_types:
            params = {'image_type': image_type, 'video_type': video_type, 'trakt_id': trakt_id, 'video_ids': video_ids}
            if video_type == VIDEO_TYPES.SEASON or video_type == VIDEO_TYPES.EPISODE:
                params['season'] = season
            if video_type == VIDEO_TYPES.EPISODE:
                params['episode'] = episode

            for attempt in range(max_retries):
                if video_type == VIDEO_TYPES.MOVIE:
                    if 'tmdb' in video_ids and video_ids['tmdb']:
                        art_dict.update(tmdb_scraper.get_movie_images(video_ids))
                if 'tvdb' in video_ids and video_ids['tvdb']:
                    art_dict.update(fanart_scraper.get_movie_images(video_ids))
                
                if art_dict.get(image_type):
                    break
                else:
                    time.sleep(retry_delay)
        if video_type == VIDEO_TYPES.TVSHOW:
            if 'tmdb' in video_ids and video_ids['tmdb']:
                art_dict.update(tmdb_scraper.get_tmdbshow_images(video_ids))
            if 'tvdb' in video_ids and video_ids['tvdb']:
                art_dict.update(tvdb_scraper.get_tvshow_images(video_ids))
            if 'imdb' in video_ids and video_ids['imdb']:
                art_dict.update(fanart_scraper.get_tvshow_images(video_ids))
        if video_type == VIDEO_TYPES.SEASON:
            if 'tvdb' in video_ids and video_ids['tvdb']:
                art_dict.update(tvdb_scraper.get_season_images(video_ids))
            if 'tvdb' in video_ids and video_ids['tvdb']:
                art_dict.update(tvdb_scraper.get_season_images_v2(video_ids))
            if 'tmdb' in video_ids and video_ids['tmdb']:
                art_dict.update(fanart_scraper.get_season_images(video_ids))
        if video_type == VIDEO_TYPES.EPISODE:
            if 'tmdb' in video_ids and video_ids['tmdb']:
                art_dict.update(tmdb_scraper.__get_best_image(video_ids, season, episode))
            if 'tvdb' in video_ids and video_ids['tvdb']:
                art_dict.update(tvdb_scraper.get_episode_images(video_ids, episode))
            if 'imdb' in video_ids and video_ids['imdb']:
                art_dict.update(imdb_scraper.get_episode_images(video_ids, episode))
        
        return art_dict[image_type]
    else:
        return scrape_images(video_type, video_ids, season, episode, cached)


def scrape_images(video_type, video_ids, season='', episode='', cached=True):
    art_dict = {'banner': None, 'fanart': DEFAULT_FANART, 'thumb': None, 'poster': PLACE_POSTER, 'clearart': None, 'clearlogo': None}
    trakt_id = video_ids['trakt']
    object_type = VIDEO_TYPES.MOVIE if video_type == VIDEO_TYPES.MOVIE else VIDEO_TYPES.TVSHOW
    if cached:
        cached_art = db_connection.get_cached_images(object_type, trakt_id, season, episode)
        if cached_art:
            art_dict.update(cached_art)
    else:
        cached_art = {}
    
    if not cached_art:
        fanart_scraper = FanartTVScraper()
        omdb_scraper = OMDBScraper()
        tvmaze_scraper = TVMazeScraper()
        tvdb_scraper = TVDBScraper()
        tmdb_scraper = TMDBScraper()
        imdb_scraper = IMDBScraper()

        if video_type == VIDEO_TYPES.MOVIE:
            if  POSTER_ENABLED:
                art_dict.update(fanart_scraper.get_movie_images(video_ids))
            # if GIF_ENABLED and POSTER_ENABLED:
            #     art_dict.update(gif_scraper.get_movie_images(video_ids))
             
            need = []
            if art_dict['fanart'] == DEFAULT_FANART: need.append('fanart')
            if art_dict['poster'] == PLACE_POSTER: need.append('poster')
            if need:
                art_dict.update(tmdb_scraper.get_movie_images(video_ids, need))
                
            if art_dict['poster'] == PLACE_POSTER:
                art_dict.update(omdb_scraper.get_images(video_ids))

        elif video_type == VIDEO_TYPES.TVSHOW:
            art_dict.update(fanart_scraper.get_tvshow_images(video_ids))
             
            need = []
            if art_dict['fanart'] == DEFAULT_FANART: need.append('fanart')
            if art_dict['poster'] == PLACE_POSTER: need.append('poster')
            if not art_dict['banner']: need.append('banner')
            if need:
                art_dict.update(tvdb_scraper.get_tvshow_images(video_ids, need))
                
            
            if art_dict['poster'] == PLACE_POSTER:
                art_dict.update(imdb_scraper.get_tvshow_images(video_ids))

        elif video_type == VIDEO_TYPES.SEASON:
            art_dict = scrape_images(VIDEO_TYPES.TVSHOW, video_ids, cached=cached)
            season_art = fanart_scraper.get_season_images(video_ids)
            logger.log('season_art: %s' % season_art)
            tvdb_season_art = tvdb_scraper.get_season_images(video_ids)
            logger.log('tvdb_season_art: %s' % tvdb_season_art)
            
            for key in tvdb_season_art:
                tvdb_poster = tvdb_season_art[key].get('poster')
                tvdb_banner = tvdb_season_art[key].get('banner')

                if tvdb_poster and not season_art.get(key, {}).get('poster'):
                    season_art.setdefault(key, {}).setdefault('poster', tvdb_poster)

                if tvdb_banner and not season_art.get(key, {}).get('banner'):
                    season_art.setdefault(key, {}).setdefault('banner', tvdb_banner)
            
            for key in season_art:
                temp_dict = art_dict.copy()
                temp_dict.update(season_art[key])
                db_connection.cache_images(object_type, trakt_id, temp_dict, key)
            
            art_dict.update(season_art.get(str(season), {}))

        elif video_type == VIDEO_TYPES.EPISODE:
            art_dict = scrape_images(VIDEO_TYPES.TVSHOW, video_ids, cached=cached)
            art_dict.update(tvdb_scraper.get_episode_images(video_ids, season, episode))

            need = []
            if art_dict['fanart'] == DEFAULT_FANART: need.append('fanart')
            if art_dict['poster'] == PLACE_POSTER: need.append('poster')
            if not art_dict['banner']: need.append('banner')
            if need:
                art_dict.update(imdb_scraper.get_episode_images(video_ids, season, episode))

            if not art_dict['thumb'] or art_dict['poster'] == PLACE_POSTER:
                tvmaze_art = tvmaze_scraper.get_episode_images(video_ids, season, episode)
                art_dict['thumb'] = tvmaze_art.get('thumb')
                if art_dict['poster'] == PLACE_POSTER and 'poster' in tvmaze_art:
                    art_dict['poster'] = tvmaze_art['poster']
                    
        if not art_dict['thumb']:
            logger.log('Doing %s thumb fallback |%s|' % (video_type, art_dict))
            if video_type == VIDEO_TYPES.MOVIE:
                if art_dict['poster'] != PLACE_POSTER: art_dict['thumb'] = art_dict['poster']
                elif art_dict['fanart'] != DEFAULT_FANART: art_dict['thumb'] = art_dict['fanart']
                else: art_dict['thumb'] = art_dict['poster']
            else:
                if art_dict['fanart'] != DEFAULT_FANART: art_dict['thumb'] = art_dict['fanart']
                elif art_dict['poster'] != PLACE_POSTER: art_dict['thumb'] = art_dict['poster']
                else: art_dict['thumb'] = art_dict['fanart']
        elif art_dict['fanart'] == DEFAULT_FANART:
            logger.log('Doing %s fanart fallback |%s|' % (video_type, art_dict))
            art_dict['fanart'] = art_dict['thumb']
            
        db_connection.cache_images(object_type, trakt_id, art_dict, season, episode)
    
    return art_dict