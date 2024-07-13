"""
    tknorris shared module
    Copyright (C) 2024 tknorris, MrBlamo

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
import datetime
import _strptime
import time
import re
import json
import urllib.error as urllib_error
import os
import kodi
import log_utils
import xbmcgui
import xbmcvfs
import xbmc
from six.moves import urllib_request, urllib_parse
import six


logger = log_utils.Logger.get_logger(__name__)

def __enum(**enums):
    return type('Enum', (), enums)

PROGRESS = __enum(OFF=0, WINDOW=1, BACKGROUND=2)
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/58.0.3029.110 Safari/537.3"
CHUNK_SIZE = 8192
DEFAULT_EXT = 'mpg'
INTERVALS = 5
WATCHLIST_SLUG = 'watchlist_slug'

def make_list_item(label, meta, art=None, cast=None):
    if art is None:
        art = {'thumb': '', 'fanart': ''}
    if cast is None:
        cast = []

    # Create a new ListItem with the label
    listitem = xbmcgui.ListItem(label)

    # Set artwork for the list item, using setArt method which is compatible with Kodi 21+
    listitem.setArt({
        'thumb': art['thumb'],
        'fanart': art['fanart'],
        'icon': art['thumb']
    })

    # Set properties for the list item
    listitem.setProperty('isPlayable', 'false')

    # Add empty stream info for video
    listitem.addStreamInfo('video', {})

    # Set cast if available
    if cast:
        listitem.setCast(cast)

    # Set IMDb and TVDB ids as properties if available in meta
    if 'ids' in meta:
        if 'imdb' in meta['ids']:
            listitem.setProperty('imdb_id', str(meta['ids']['imdb']))
        if 'tvdb' in meta['ids']:
            listitem.setProperty('tvdb_id', str(meta['ids']['tvdb']))

    return listitem

def iso_2_utc_tmdb(iso_ts):
    if not iso_ts or iso_ts is None:
        return 0

    # Handle cases where the date might not include the time component
    if len(iso_ts) == 7:  # Format: YYYY-MM
        ts_format = '%Y-%m'
    elif len(iso_ts) == 10:  # Format: YYYY-MM-DD
        ts_format = '%Y-%m-%d'
    elif len(iso_ts) == 19:  # Format: YYYY-MM-DDTHH:MM:SS
        ts_format = '%Y-%m-%dT%H:%M:%S'
    else:
        raise ValueError("Unsupported date format: {}".format(iso_ts))

    try:
        d = datetime.datetime.strptime(iso_ts, ts_format)
    except TypeError:
        d = datetime.datetime(*(time.strptime(iso_ts, ts_format)[0:6]))

    epoch = datetime.datetime.utcfromtimestamp(0)
    delta = d - epoch
    try:
        seconds = delta.total_seconds()  # works only on 2.7+
    except:
        seconds = delta.seconds + delta.days * 24 * 3600  # close enough
    return seconds

def iso_2_utc(iso_ts):
    if not iso_ts or iso_ts is None:
        return 0
    delim = -1
    if not iso_ts.endswith('Z'):
        delim = iso_ts.rfind('+')
        if delim == -1:
            delim = iso_ts.rfind('-')

    if delim > -1:
        ts = iso_ts[:delim]
        sign = iso_ts[delim]
        tz = iso_ts[delim + 1:]
    else:
        ts = iso_ts
        tz = None

    if ts.find('.') > -1:
        ts = ts[:ts.find('.')]

    try:
        d = datetime.datetime.strptime(ts, '%Y-%m-%dT%H:%M:%S')
    except TypeError:
        d = datetime.datetime(*(time.strptime(ts, '%Y-%m-%dT%H:%M:%S')[0:6]))

    dif = datetime.timedelta()
    if tz:
        hours, minutes = tz.split(':')
        hours = int(hours)
        minutes = int(minutes)
        if sign == '-':
            hours = -hours
            minutes = -minutes
        dif = datetime.timedelta(minutes=minutes, hours=hours)
    utc_dt = d - dif
    epoch = datetime.datetime.utcfromtimestamp(0)
    delta = utc_dt - epoch
    try:
        seconds = delta.total_seconds()  # works only on 2.7
    except:
        seconds = delta.seconds + delta.days * 24 * 3600  # close enough
    return seconds

def to_slug(username):
    username = username.strip()
    username = username.lower()
    username = re.sub('[^a-z0-9_]', '-', username)
    username = re.sub('--+', '-', username)
    return username

def json_load_as_str(file_handle):
    return _byteify(json.load(file_handle, object_hook=_byteify), ignore_dicts=True)

def json_loads_as_str(json_text):
    return _byteify(json.loads(json_text, object_hook=_byteify), ignore_dicts=True)

def _byteify(data, ignore_dicts=False):
    if isinstance(data, six.text_type):
        return six.ensure_str(data)
    if isinstance(data, list):
        return [_byteify(item, ignore_dicts=True) for item in data]
    if isinstance(data, dict) and not ignore_dicts:
        return dict([(_byteify(key, ignore_dicts=True), _byteify(value, ignore_dicts=True)) for key, value in six.iteritems(data)])
    return data

def download_media(url, path, file_name, translations, progress=None):
    try:
        if progress is None:
            progress = int(kodi.get_setting('down_progress'))
            
        i18n = translations.i18n
        active = progress != PROGRESS.OFF
        background = progress == PROGRESS.BACKGROUND
        
        # Ensure file_name is a string
        if isinstance(file_name, bytes):
            file_name = file_name.decode('utf-8')
            
        with kodi.ProgressDialog(kodi.get_name(), i18n('downloading').format(file_name), background=background, active=active) as pd:
            try:
                headers = {item.split('=')[0]: urllib_parse.unquote(item.split('=')[1]) for item in (url.split('|')[1]).split('&')}
            except IndexError:
                headers = {}
            if 'User-Agent' not in headers:
                headers['User-Agent'] = BROWSER_UA
            request = urllib_request.Request(url.split('|')[0], headers=headers)
            response = urllib_request.urlopen(request)
            content_length = int(response.info().get('Content-Length', 0))
    
            if not file_name.endswith('.zip'):
                file_name += '.' + get_extension(url, response)
            full_path = os.path.join(path, file_name)
            logger.log('Downloading: {} -> {}'.format(url, full_path), log_utils.LOGDEBUG)
    
            path = kodi.translate_path(xbmcvfs.validatePath(path))
            try:
                os.makedirs(path, exist_ok=True)
            except Exception as e:
                logger.log('Path Create Failed: {} ({})'.format(e, path), log_utils.LOGDEBUG)
    
            if not path.endswith(os.sep):
                path += os.sep
            if not xbmcvfs.exists(path):
                raise Exception(i18n('failed_create_dir'))
            
            with xbmcvfs.File(full_path, 'w') as file_desc:
                total_len = 0
                cancel = False
                while True:
                    data = response.read(CHUNK_SIZE)
                    if not data:
                        break
        
                    if pd.is_canceled():
                        cancel = True
                        break
        
                    file_desc.write(data)
                    total_len += len(data)
                    if content_length > 0:
                        percent = int((total_len * 100) / content_length)
                        pd.update(percent)
    
                if cancel:
                    xbmcvfs.delete(full_path)
                    raise Exception(i18n('download_canceled'))
    
            return full_path
    except Exception as e:
        logger.log('Download Error: {}'.format(str(e)), log_utils.LOGERROR)
        kodi.notify(msg=i18n('download_error').format(str(e), file_name), duration=5000)
        return None
    
def get_extension(url, response):
    filename = url2name(url)
    if 'Content-Disposition' in response.info():
        cd_list = response.info()['Content-Disposition'].split('filename=')
        if len(cd_list) > 1:
            filename = cd_list[-1]
            if filename[0] == '"' or filename[0] == "'":
                filename = filename[1:-1]
    elif response.url != url:
        filename = url2name(response.url)
    ext = os.path.splitext(filename)[1][1:]
    if not ext:
        ext = DEFAULT_EXT
    return ext


def create_legal_filename(title, year):
    filename = title
    if year:
        filename += ' %s' % (year)
    filename = re.sub(r'(?!%s)[^\w\-_\.]', '.', filename)
    filename = re.sub(r'\.+', '.', filename)
    xbmc.makeLegalFilename(filename) if six.PY2 else xbmcvfs.makeLegalFilename(filename)
    return filename


def url2name(url):
    url = url.split('|')[0]
    return os.path.basename(urllib_parse.unquote(urllib_parse.urlsplit(url)[2]))

def auth_trakt(Trakt_API, translations):
    i18n = translations.i18n
    start = time.time()
    use_https = kodi.get_setting('use_https') == 'true'
    trakt_timeout = int(kodi.get_setting('trakt_timeout'))
    trakt_api = Trakt_API(use_https=use_https, timeout=trakt_timeout)
    result = trakt_api.get_code()
    code, expires, interval = result['device_code'], result['expires_in'], result['interval']
    time_left = expires - int(time.time() - start)
    line1 = i18n('verification_url') % (result['verification_url'])
    line2 = i18n('prompt_code') % (result['user_code'])
    with kodi.CountdownDialog(i18n('trakt_acct_auth'), line1=line1, line2=line2, countdown=time_left, interval=interval) as cd:
        result = cd.start(__auth_trakt, [trakt_api, code, i18n])

    try:
        kodi.set_setting('trakt_oauth_token', result['access_token'])
        kodi.set_setting('trakt_refresh_token', result['refresh_token'])
        trakt_api = Trakt_API(result['access_token'], use_https=use_https, timeout=trakt_timeout)
        profile = trakt_api.get_user_profile(cached=False)
        kodi.set_setting('trakt_user', '%s (%s)' % (profile['username'], profile['name']))
        kodi.notify(msg=i18n('trakt_auth_complete'), duration=3000)
    except Exception as e:
        logger.log('Trakt Authorization Failed: %s' % (e), log_utils.LOGDEBUG)


def __auth_trakt(trakt_api, code, i18n):
    try:
        result = trakt_api.get_device_token(code)
        return result
    except urllib_error.URLError as e:
        # authorization is pending; too fast
        if e.code in [400, 429]:
            return
        elif e.code == 418:
            kodi.notify(msg=i18n('user_reject_auth'), duration=3000)
            return True
        elif e.code == 410:
            return
        else:
            raise

def choose_list(Trakt_API, translations, username=None):
    i18n = translations.i18n
    trakt_api = Trakt_API(kodi.get_setting('trakt_oauth_token'), kodi.get_setting('use_https') == 'true', timeout=int(kodi.get_setting('trakt_timeout')))
    lists = trakt_api.get_lists(username)
    if username is None:
        lists.insert(0, {'name': 'watchlist', 'ids': {'slug': WATCHLIST_SLUG}})
    if lists:
        dialog = xbmcgui.Dialog()
        index = dialog.select(i18n('pick_a_list'), [list_data['name'] for list_data in lists])
        if index > -1:
            return (lists[index]['ids']['slug'], lists[index]['name'])
    else:
        kodi.notify(msg=i18n('no_lists_for_user') % (username), duration=5000)

def format_time(seconds):
    minutes, seconds = divmod(seconds, 60)
    if minutes > 60:
        hours, minutes = divmod(minutes, 60)
        return "%02d:%02d:%02d" % (hours, minutes, seconds)
    else:
        return "%02d:%02d" % (minutes, seconds)
    

# def auth_alldebrid(Alldebrid_API, translations):
    # i18n = translations.i18n
    # start = time.time()
    # alldebrid_timeout = int(kodi.get_setting('alldebrid_timeout'))
    # alldebrid_api = Alldebrid_API()
    # result = alldebrid_api.authenticate()
    # code, expires, interval = result['device_code'], result['expires_in'], result['interval']
    # time_left = expires - int(time.time() - start)
    # line1 = i18n('verification_url') % (result['verification_url'])
    # line2 = i18n('prompt_code') % (result['user_code'])
    # with kodi.CountdownDialog(i18n('alldebrid_auth'), line1=line1, line2=line2, countdown=time_left, interval=interval) as cd:
        # result = cd.start(__auth_alldebrid, [alldebrid_api, code, i18n])

    # try:
        # kodi.set_setting('alldebrid_api_key', result['access_token'])
        # alldebrid_api = Alldebrid_API(result['access_token'], timeout=alldebrid_timeout)
        # profile = alldebrid_api.get_user_info(cached=False)
        # kodi.set_setting('alldebrid_user', '%s (%s)' % (profile['username'], profile['name']))
        # kodi.notify(msg=i18n('alldebrid_auth_complete'), duration=3000)
    # except Exception as e:
        # logger.log('AllDebrid Authorization Failed: %s' % (e), log_utils.LOGDEBUG)

# def __auth_alldebrid(alldebrid_api, code, i18n):
    # try:
        # return alldebrid_api.__poll_auth(code)
    # except Exception as e:
        # logger.log('AllDebrid Polling Failed: %s' % (e), log_utils.LOGDEBUG)
        # return None