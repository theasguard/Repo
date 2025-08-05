"""
    Asguard Addon
    Copyright (C) 2016 tknorris

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

import io, re, json, gzip, datetime, time, os, html

import html.entities, urllib.parse, urllib.request, urllib.error, six
import xbmcgui
import hashlib
import xbmcvfs
import _strptime  # @UnusedImport
import xml.etree.ElementTree as ET
import log_utils
import utils
import xbmc, xbmcaddon, xbmcvfs
import kodi
try:
    from . import pyaes
except ImportError:
    import pyaes
from .constants import *  # @UnusedWildImport
from asguard_lib import strings

logger = log_utils.Logger.get_logger()

THEME_LIST = ['4Horsemen', 'Charon', 'Deadly Elegant', 'Death', 'DOA', 'Famine', 'Hades', 'Heinous', 'Pepper Shaker',
              'Pestilence', 'Purgatory', 'Rock Salt', 'Seasoned', 'The Underworld', 'Toxic Death', 'Unsalted', 'War']
THEME = THEME_LIST[int(kodi.get_setting('theme') or 0)]
if kodi.has_addon('script.asguard.themepak'):
    themepak_path = xbmcaddon.Addon('script.asguard.themepak').getAddonInfo('path')
else:
    themepak_path = kodi.get_path()
THEME_PATH = os.path.join(themepak_path, 'art', 'themes', THEME)
translations = kodi.Translations(strings.STRINGS)

SORT_FIELDS = [
    (SORT_LIST[int(kodi.get_setting('sort1_field'))], SORT_SIGNS[kodi.get_setting('sort1_order')]),
    (SORT_LIST[int(kodi.get_setting('sort2_field'))], SORT_SIGNS[kodi.get_setting('sort2_order')]),
    (SORT_LIST[int(kodi.get_setting('sort3_field'))], SORT_SIGNS[kodi.get_setting('sort3_order')]),
    (SORT_LIST[int(kodi.get_setting('sort4_field'))], SORT_SIGNS[kodi.get_setting('sort4_order')]),
    (SORT_LIST[int(kodi.get_setting('sort5_field'))], SORT_SIGNS[kodi.get_setting('sort5_order')]),
    (SORT_LIST[int(kodi.get_setting('sort6_field'))], SORT_SIGNS[kodi.get_setting('sort6_order')])]

def art(name):
    path = os.path.join(THEME_PATH, name)
    if not xbmcvfs.exists(path):
        if name == 'fanart.jpg':
            path = os.path.join(kodi.get_path(), name)
        else:
            path = path.replace('.png', '.jpg')
    return path

def show_id(show):
    queries = {}
    ids = show.get('ids', {})
    for key in ('trakt', 'imdb', 'tvdb', 'tmdb', 'tvrage', 'slug', 'anidb', 'mal'):
        if key in ids and ids[key]:
            queries['id_type'] = key
            queries['show_id'] = ids[key]
            if key == 'imdb':
                queries['imdbnumber'] = ids[key]
            elif key == 'tvdb':
                queries['tvdb'] = ids[key]
            elif key == 'tmdb':
                queries['tmdb'] = ids[key]
            elif key == 'anidb':
                queries['anidb'] = ids[key]
            elif key == 'mal':
                queries['mal'] = ids[key]
            # Note: 'trakt' and 'slug' do not have direct Kodi equivalents
            break
    return queries

def title_key(title):
    if title is None: title = ''
    temp = title.upper()
    if temp.startswith('THE '):
        offset = 4
    elif temp.startswith('A '):
        offset = 2
    elif temp.startswith('AN '):
        offset = 3
    else:
        offset = 0
    return title[offset:]

def _released_key(item):
    if 'released' in item:
        return item['released']
    elif 'first_aired' in item:
        return item['first_aired']
    else:
        return 0

def sort_list(sort_key, sort_direction, list_data):
    logger.log('Sorting List: %s - %s' % (sort_key, sort_direction), log_utils.LOGDEBUG)
    
    # Defensive programming: ensure list_data is actually a list
    if not isinstance(list_data, list):
        logger.log('sort_list: Expected list, got %s. Returning original data.' % type(list_data), log_utils.LOGWARNING)
        return list_data
    
    # Check if list is empty or contains non-dict items
    if not list_data or not isinstance(list_data[0], dict):
        logger.log('sort_list: List is empty or contains non-dict items. Returning original data.', log_utils.LOGDEBUG)
        return list_data
    
    reverse = sort_direction != TRAKT_SORT_DIR.ASCENDING

    def get_item_data(item):
        """Get the show/movie data from the item, handling different data structures."""
        if 'type' in item:
            # Standard list format: item contains type and nested show/movie data
            return item[item['type']]
        elif 'show' in item:
            # Watch history format: item contains show data directly
            return item['show']
        elif 'movie' in item:
            # Watch history format: item contains movie data directly
            return item['movie']
        else:
            # Fallback: return the item itself
            return item

    def get_title(item):
        return title_key(get_item_data(item).get('title', ''))

    def get_released(item):
        return _released_key(get_item_data(item))

    def get_runtime(item):
        return get_item_data(item).get('runtime', 0)

    def get_votes(item):
        return get_item_data(item).get('votes', 0)

    def get_rating(item):
        return get_item_data(item).get('rating', 0)

    def get_plays(item):
        return item.get('plays', 0)

    sort_functions = {
        TRAKT_LIST_SORT.RANK: lambda x: x['rank'],
        TRAKT_LIST_SORT.RECENTLY_ADDED: lambda x: x['listed_at'],
        TRAKT_LIST_SORT.TITLE: get_title,
        TRAKT_LIST_SORT.RELEASE_DATE: get_released,
        TRAKT_LIST_SORT.RUNTIME: get_runtime,
        TRAKT_LIST_SORT.POPULARITY: get_votes,
        TRAKT_LIST_SORT.PERCENTAGE: get_rating,
        TRAKT_LIST_SORT.VOTES: get_votes,
        TRAKT_LIST_SORT.PLAYS: get_plays
    }

    if sort_key in sort_functions:
        sorted_list = sorted(list_data, key=sort_functions[sort_key], reverse=reverse)
        logger.log('Sorted list: %s' % (sorted_list), log_utils.LOGDEBUG)
        return sorted_list
    else:
        logger.log('Unrecognized list sort key: %s - %s' % (sort_key, sort_direction), log_utils.LOGWARNING)
        return list_data
    
def make_seasons_info(progress):
    season_info = {}
    if progress:
        for season in progress['seasons']:
            info = {}
            if 'aired' in season: info['episode'] = info['TotalEpisodes'] = season['aired']
            if 'completed' in season: info['WatchedEpisodes'] = season['completed']
            if 'aired' in season and 'completed' in season:
                info['UnWatchedEpisodes'] = season['aired'] - season['completed']
                info['playcount'] = season['aired'] if season['completed'] == season['aired'] else 0

            if 'number' in season: info['season'] = season['number']
            season_info[str(season['number'])] = info
    return season_info

def make_episodes_watched(episodes, progress):
    try:
        # Ensure progress is a dictionary
        if isinstance(progress, str):
            progress = json.loads(progress)
        
        if 'seasons' not in progress:
            logger.error("Invalid progress data: 'seasons' key not found")
            return episodes

        watched = {}
        for season in progress['seasons']:
            watched[str(season['number'])] = {}
            for ep_status in season['episodes']:
                watched[str(season['number'])][str(ep_status['number'])] = ep_status['completed']

        for episode in episodes:
            season_str = str(episode['season'])
            episode_str = str(episode['number'])
            if season_str in watched and episode_str in watched[season_str]:
                episode['watched'] = watched[season_str][episode_str]
            else:
                episode['watched'] = False

        return episodes
    except (TypeError, ValueError) as e:
        return episodes

def make_episodes_watched_dict(progress):
    """Create a dictionary of watched episodes similar to make_episodes_watched"""
    watched = {}
    try:
        if not progress or 'seasons' not in progress:
            return watched
            
        for season in progress['seasons']:
            season_num = str(season['number'])
            watched.setdefault(season_num, {})
            for ep_status in season['episodes']:
                ep_num = str(ep_status['number'])
                watched[season_num][ep_num] = ep_status['completed']
                
        return watched
    except Exception as e:
        logger.log(f'Error creating watched dict: {e}', log_utils.LOGERROR)
        return watched

def make_trailer(trailer_url):
    match = re.search(r'\?v=(.*)', trailer_url)
    if match:
        return 'plugin://plugin.video.youtube/?action=play_video&videoid=%s' % (match.group(1))

def make_ids(item):
    info = {}
    if 'ids' in item:
        ids = item['ids']
        if 'imdb' in ids: 
            info['code'] = info['imdbnumber'] = info['imdb_id'] = ids['imdb']
        if 'tmdb' in ids: 
            info['tmdb_id'] = ids['tmdb']
        if 'tvdb' in ids: 
            info['tvdb_id'] = ids['tvdb']
        if 'trakt' in ids: 
            info['trakt_id'] = ids['trakt']
        if 'slug' in ids: 
            info['slug'] = ids['slug']
        if 'tvrage' in ids: 
            info['tvrage_id'] = ids['tvrage']
        if 'anidb' in ids: 
            info['anidb_id'] = ids['anidb']
        if 'mal' in ids: 
            info['mal_id'] = ids['mal']
    return info

def make_people(item):
    people = {}
    if 'crew' in item and 'directing' in item['crew']:
        directors = [director['person']['name'] for director in item['crew']['directing'] if director['job'].lower() == 'director']
        if directors:
            people['director'] = directors  # Keep as list for proper infotagger handling
    if 'crew' in item and 'writing' in item['crew']:
        writers = [writer['person']['name'] for writer in item['crew']['writing'] if writer['job'].lower() in ['writer', 'screenplay', 'author']]
        if writers:
            people['writer'] = writers  # Keep as list for proper infotagger handling

    return people

def make_air_date(first_aired):
    utc_air_time = utils.iso_2_utc(first_aired)
    if utc_air_time < 0:
        logger.log(f'Negative UTC time for first_aired: {first_aired}', log_utils.LOGWARNING)
        return '1970-01-01'  # Default date or handle as needed
    try:
        air_date = time.strftime('%Y-%m-%d', time.localtime(utc_air_time))
    except ValueError:  # windows throws a ValueError on negative values to localtime
        d = datetime.datetime.fromtimestamp(0) + datetime.timedelta(seconds=utc_air_time)
        air_date = d.strftime('%Y-%m-%d')
    return str(air_date)

def get_section_params(section):
    section_params = {}
    section_params['section'] = section
    if section == SECTIONS.TV:
        section_params['next_mode'] = MODES.SEASONS
        section_params['folder'] = True
        section_params['video_type'] = VIDEO_TYPES.TVSHOW
        section_params['content_type'] = CONTENT_TYPES.TVSHOWS
        section_params['search_img'] = 'television_search.png'
        section_params['label_plural'] = i18n('tv_shows')
        section_params['label_single'] = i18n('tv_show')
    else:
        section_params['next_mode'] = MODES.GET_SOURCES
        section_params['folder'] = False
        section_params['video_type'] = VIDEO_TYPES.MOVIE
        section_params['content_type'] = CONTENT_TYPES.MOVIES
        section_params['search_img'] = 'movies_search.png'
        section_params['label_plural'] = i18n('movies')
        section_params['label_single'] = i18n('movie')

    return section_params

def filename_from_title(title, video_type, year=None):
    if video_type == VIDEO_TYPES.TVSHOW:
        filename = '%s S%sE%s'
        filename = filename % (title, '%s', '%s')
    else:
        if year: title = '%s.%s' % (title, year)
        filename = title

    filename = re.sub(r'(?!%s)[^\w\-_\.]', '.', filename)
    filename = re.sub(r'\.+', '.', filename)
    filename = re.sub(re.compile(r'(CON|PRN|AUX|NUL|COM\d|LPT\d)\.', re.I), r'\1_', filename)
    xbmc.makeLegalFilename(filename) if six.PY2 else xbmcvfs.makeLegalFilename(filename)
    return filename

def filter_exclusions(hosters):
    exclusions = kodi.get_setting('excl_list')
    exclusions = exclusions.replace(' ', '')
    exclusions = exclusions.lower()
    if not exclusions: return hosters
    filtered_hosters = []
    for hoster in hosters:
        if hoster['host'].lower() in exclusions:
            logger.log('Excluding %s (%s) from %s' % (hoster['url'], hoster['host'], hoster['class'].get_name()), log_utils.LOGDEBUG)
            continue
        filtered_hosters.append(hoster)
    return filtered_hosters

def filter_quality(video_type, hosters):
    qual_filter = 5 - int(kodi.get_setting('%s_quality' % video_type))  # subtract to match Q_ORDER
    if qual_filter == 5:
        return hosters
    else:
        return [hoster for hoster in hosters if hoster['quality'] is not None and Q_ORDER[hoster['quality']] <= qual_filter]

def get_sort_key(item):
    item_sort_key = []
    for field, sign in SORT_FIELDS:
        if field == 'none':
            break
        elif field in SORT_KEYS:
            if field == 'source':
                value = item['class'].get_name()
            if isinstance(field, list):
                value = field[0] if field else None
            else:
                value = item.get(field)
            if isinstance(value, list):
                value = value[0] if value else None

            if isinstance(SORT_KEYS[field], list):
                if value in SORT_KEYS[field]:
                    item_sort_key.append(sign * int(SORT_KEYS[field].index(value)))
                else:
                    item_sort_key.append(sign * -1)
            elif value in SORT_KEYS[field]:
                item_sort_key.append(sign * int(SORT_KEYS[field][value]))
            else:  # assume all unlisted values sort as worst
                item_sort_key.append(sign * -1)

            if isinstance(value, list):
                value = value[0] if value else None
            else:  # assume all unlisted values sort as worst
                item_sort_key.append(sign * -1)
        elif field == 'debrid':
            if field in item:
                item_sort_key.append(sign * bool(item[field]))
            else:
                item_sort_key.append(0)
        else:
            if item.get(field) is None:
                item_sort_key.append(sign * -1)
            else:
                item_sort_key.append(sign * int(item[field]))
    logger.log('item: %s sort_key: %s' % (item, item_sort_key), log_utils.LOGDEBUG)
    return tuple(item_sort_key)

def pick_source(sources, auto_pick=None):
    if auto_pick is None:
        auto_pick = kodi.get_setting('auto_pick') == 'true'

    if len(sources) == 1:
        return sources[0][1]
    elif len(sources) > 1:
        if auto_pick:
            return sources[0][1]
        else:
            result = xbmcgui.Dialog().select(i18n('choose_the_link'), [str(source[0]) if source[0] else 'Unknown' for source in sources])
            if result == -1:
                raise Exception(i18n('no_link_selected'))
            else:
                return sources[result][1]
    else:
        raise Exception(i18n('no_video_link'))

def sort_sources_list(sources):
    if len(sources) > 1:
        try:
            sources.sort(key=lambda x: int(re.sub(r"\D", "", x[0])), reverse=True)
        except:
            logger.log('Sort failed: %s' % sources, log_utils.LOGDEBUG)
            try:
                sources.sort(key=lambda x: re.sub("[^a-zA-Z]", "", x[0].lower()))
            except:
                logger.log('Sort failed: %s' % sources, log_utils.LOGDEBUG)
    return sources

def make_source_sort_string(sort_key):
    sorted_key = sorted(sort_key.items(), key=lambda x: -x[1])
    sort_string = '|'.join([element[0] for element in sorted_key])
    return sort_string

def test_stream(hoster):
    # parse_qsl doesn't work because it splits elements by ';' which can be in a non-quoted UA
    try:
        headers = dict([item.split('=') for item in (hoster['url'].split('|')[1]).split('&')])
        for key in headers:
            headers[key] = urllib.parse.unquote_plus(headers[key])
    except:
        headers = {}
    logger.log('Testing Stream: %s from %s using Headers: %s' % (hoster['url'], hoster['class'].get_name(), headers), log_utils.LOGDEBUG)
    request = urllib.request.Request(hoster['url'].split('|')[0], headers=headers)

    msg = ''
    opener = urllib.request.build_opener(urllib.request.HTTPRedirectHandler)
    urllib.request.install_opener(opener)
    try:
        http_code = urllib.request.urlopen(request, timeout=2).getcode()
    except urllib.error.URLError as e:
        # treat an unhandled url type as success
        if hasattr(e, 'reason') and 'unknown url type' in str(e.reason).lower():
            return True
        else:
            if isinstance(e, urllib.error.HTTPError):
                http_code = e.code
            else:
                http_code = 600
        msg = str(e)
    except Exception as e:
        if 'unknown url type' in str(e).lower():
            return True
        else:
            logger.log('Exception during test_stream: (%s) %s' % (type(e).__name__, e), log_utils.LOGDEBUG)
            http_code = 601
        msg = str(e)

    if int(http_code) >= 400:
        logger.log('Test Stream Failed: Url: %s HTTP Code: %s Msg: %s' % (hoster['url'], http_code, msg), log_utils.LOGDEBUG)

    return int(http_code) < 400

def scraper_enabled(name):
    # return true if setting exists and set to true, or setting doesn't exist (i.e. '')
    return kodi.get_setting('%s-enable' % (name)) in ('true', '')


def make_day(date, use_words=True):
    date = to_datetime(date, '%Y-%m-%d').date()
    today = datetime.date.today()
    day_diff = (date - today).days
    date_format = kodi.get_setting('date_format')
    fallback_format = '%Y-%m-%d'
    try: day = date.strftime(date_format)
    except ValueError: day = date.strftime(fallback_format)
    if use_words:
        if day_diff == -1:
            day = 'YDA'
        elif day_diff == 0:
            day = 'TDA'
        elif day_diff == 1:
            day = 'TOM'
        elif day_diff > 1 and day_diff < 7:
            day = date.strftime('%a')

    return day

def make_time(utc_ts, setting):
    local_time = time.localtime(utc_ts)
    if kodi.get_setting(setting) == '1':
        time_format = '%H:%M'
        time_str = time.strftime(time_format, local_time)
    else:
        time_format = '%I%p' if local_time.tm_min == 0 else '%I:%M%p'
        time_str = time.strftime(time_format, local_time)
        if time_str[0] == '0': time_str = time_str[1:]
    return time_str

def to_datetime(dt_str, date_format):
    # strptime mysteriously fails sometimes with TypeError; this is a hacky workaround
    # note, they aren't 100% equal as time.strptime loses fractional seconds but they are close enough
    try: dt = datetime.datetime.strptime(dt_str, date_format)
    except (TypeError, ImportError): dt = datetime.datetime(*(time.strptime(dt_str, date_format)[0:6]))
    except Exception as e:
        logger.log('Failed dt conversion: (%s) - |%s|%s|' % (e, dt_str, date_format))
        dt = datetime.datetime.fromtimestamp(0)
    return dt

def format_sub_label(sub):
    label = '%s - [%s] - (' % (sub['language'], sub['version'])
    if sub['completed']:
        color = 'green'
    else:
        label += '%s%% Complete, ' % (sub['percent'])
        color = 'yellow'
    if sub['hi']: label += 'HI, '
    if sub['corrected']: label += 'Corrected, '
    if sub['hd']: label += 'HD, '
    if not label.endswith('('):
        label = label[:-2] + ')'
    else:
        label = label[:-4]
    label = '[COLOR %s]%s[/COLOR]' % (color, label)
    return label

def format_source_label(item):
    color = kodi.get_setting('debrid_color') or 'green'
    # BLAMO
    orion = 'orion' in item and kodi.get_setting('show_orion') == 'true'
    if orion: color = kodi.get_setting('orion_color') or 'red'
    # BLAMO
    label = item['class'].format_source_label(item)
    label = '[%s] %s' % (item['class'].get_name(), label)
    if kodi.get_setting('show_debrid') == 'true' and ('debrid' in item or 'torbox' in item) and item['debrid']:
        label = '[COLOR %s]%s[/COLOR]' % (color, label)
    # BLAMO
    elif orion: label = '[COLOR %s]%s[/COLOR]' % (color, label)
    # BLAMO
    if 'debrid' in item and item['debrid']:
        label += ' (%s)' % (', '.join(item['debrid']))

    item['label'] = label
    return label
    
def srt_indicators_enabled():
    return (kodi.get_setting('enable-subtitles') == 'true' and (kodi.get_setting('subtitle-indicator') == 'true'))

def srt_download_enabled():
    return (kodi.get_setting('enable-subtitles') == 'true' and (kodi.get_setting('subtitle-download') == 'true'))

def srt_show_enabled():
    return (kodi.get_setting('enable-subtitles') == 'true' and (kodi.get_setting('subtitle-show') == 'true'))

def format_episode_label(label, season, episode, srts):
    req_hi = kodi.get_setting('subtitle-hi') == 'true'
    req_hd = kodi.get_setting('subtitle-hd') == 'true'
    color = 'red'
    percent = 0
    hi = None
    hd = None
    corrected = None

    for srt in srts:
        if str(season) == srt['season'] and str(episode) == srt['episode']:
            if not req_hi or srt['hi']:
                if not req_hd or srt['hd']:
                    if srt['completed']:
                        color = 'green'
                        if not hi: hi = srt['hi']
                        if not hd: hd = srt['hd']
                        if not corrected: corrected = srt['corrected']
                    elif color != 'green':
                        color = 'yellow'
                        if float(srt['percent']) > percent:
                            if not hi: hi = srt['hi']
                            if not hd: hd = srt['hd']
                            if not corrected: corrected = srt['corrected']
                            percent = srt['percent']

    if color != 'red':
        label += ' [COLOR %s](SRT: ' % (color)
        if color == 'yellow':
            label += ' %s%%, ' % (percent)
        if hi: label += 'HI, '
        if hd: label += 'HD, '
        if corrected: label += 'Corrected, '
        label = label[:-2]
        label += ')[/COLOR]'
    return label

def record_failures(fails, counts=None):
    if counts is None: counts = {}

    cur_failures = get_failures()
    for name in fails:
        if name in counts: del counts[name]
        if cur_failures.get(name, 0) > -1:
            cur_failures[name] = cur_failures.get(name, 0) + 5
    
    for name in counts:
        if counts[name] > 0:
            cur_failures[name] = 0
        elif cur_failures.get(name, 0) > -1:
            cur_failures[name] = cur_failures.get(name, 0) + 1
    store_failures(cur_failures)

def get_failures():
    return json.loads(kodi.get_setting('scraper_failures'))

def store_failures(failures):
    failures = dict((key, value) for key, value in failures.items() if value != 0)
    kodi.set_setting('scraper_failures', json.dumps(failures))

def menu_on(menu):
    return kodi.get_setting('show_%s' % menu) == 'true'

def sort_progress(episodes, sort_order):
    if sort_order == TRAKT_SORT.TITLE:
        return sorted(episodes, key=lambda x: title_key(x['show']['title']))
    elif sort_order == TRAKT_SORT.RECENT_ACTIVITY:
        return sorted(episodes, key=lambda x: utils.iso_2_utc(x['last_watched_at']), reverse=True)
    elif sort_order == TRAKT_SORT.LEAST_COMPLETED:
        return sorted(episodes, key=lambda x: (x['percent_completed'], x['completed']))
    elif sort_order == TRAKT_SORT.MOST_COMPLETED:
        return sorted(episodes, key=lambda x: (x['percent_completed'], x['completed']), reverse=True)
    elif sort_order == TRAKT_SORT.PREVIOUSLY_AIRED:
        return sorted(episodes, key=lambda x: utils.iso_2_utc(x['episode']['first_aired']))
    elif sort_order == TRAKT_SORT.RECENTLY_AIRED:
        return sorted(episodes, key=lambda x: utils.iso_2_utc(x['episode']['first_aired']), reverse=True)
    elif sort_order == TRAKT_SORT.PAST_ACTIVITY:
        return sorted(episodes, key=lambda x: utils.iso_2_utc(x['last_watched_at']))
    else:  # default sort set to activity
        return sorted(episodes, key=lambda x: x['last_watched_at'], reverse=True)

def make_progress_msg(video):
    progress_msg = '%s: %s' % (video.video_type, video.title)
    if video.year: progress_msg += ' (%s)' % (video.year)
    if video.video_type == VIDEO_TYPES.EPISODE:
        progress_msg += ' - S%02dE%02d' % (int(video.season), int(video.episode))
    return progress_msg


def from_playlist():
    pl = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
    if pl.size() > 0:
        li = pl[pl.getposition()]
        plugin_url = 'plugin://%s/' % kodi.get_id()
        if li.getPath().lower().startswith(plugin_url):
            logger.log('Playing Asguard item from playlist |%s|%s|%s|' % (pl.getposition(), li.getPath(), plugin_url), log_utils.LOGDEBUG)
            return True
    
    return False

def reset_base_url():
    xml_path = os.path.join(kodi.get_path(), 'resources', 'settings.xml')
    tree = ET.parse(xml_path)
    for category in tree.getroot().findall('category'):
        if category.get('label').startswith('Scrapers '):
            for setting in category.findall('setting'):
                if re.search('-base_url\d*$', setting.get('id')):
                    logger.log('Resetting: %s -> %s' % (setting.get('id'), setting.get('default')), log_utils.LOGDEBUG)
                    kodi.set_setting(setting.get('id'), setting.get('default'))

def get_and_decrypt(url, password, old_lm=None):
    try:
        plain_text = ''
        new_lm = ''

        # only do the HEAD request if there's an old_lm to compare to
        if old_lm is not None:
            req = urllib.request.Request(url)
            req.get_method = lambda: 'HEAD'
            res = urllib.request.urlopen(req)
            new_lm = res.info().get('Last-Modified')

        if old_lm is None or new_lm != old_lm:
            res = urllib.request.urlopen(url)
            cipher_text = res.read()
            if cipher_text:
                scraper_key = hashlib.sha256(password.encode('utf-8')).digest()
                IV = '\0' * 16
                decrypter = pyaes.Decrypter(pyaes.AESModeOfOperationCBC(scraper_key, IV))
                plain_text = decrypter.feed(cipher_text)
                plain_text += decrypter.feed()
                new_lm = res.info().get('Last-Modified')

        logger.log('url: %s, old_lm: |%s|, new_lm: |%s|, lm_match: %s' % (url, old_lm, new_lm, old_lm == new_lm), log_utils.LOGDEBUG)
                
    except Exception as e:
        logger.log('Failure during getting: %s (%s)' % (url, e), log_utils.LOGWARNING)
    
    return new_lm, plain_text

def get_force_title_list():
    return __get_list('force_title_match')

def get_progress_skip_list():
    return __get_list('progress_skip_cache')

def get_force_progress_list():
    return __get_list('force_include_progress')

def get_min_rewatch_list():
    return __get_list('rewatch_min_list')

def get_max_rewatch_list():
    return __get_list('rewatch_max_list')

def show_requires_source(trakt_id):
    return str(trakt_id) in __get_list('exists_list')

def __get_list(setting):
    filter_str = kodi.get_setting(setting)
    filter_list = filter_str.split('|') if filter_str else []
    return filter_list

def get_next_rewatch_method(trakt_id):
    rewatch_method = get_rewatch_method(trakt_id)
    if rewatch_method == REWATCH_METHODS.LAST_WATCHED:
        return i18n('least_watched_method'), REWATCH_METHODS.LEAST_WATCHED
    elif rewatch_method == REWATCH_METHODS.LEAST_WATCHED:
        return i18n('most_watched_method'), REWATCH_METHODS.MOST_WATCHED
    else:
        return i18n('last_watched_method'), REWATCH_METHODS.LAST_WATCHED
    
def get_rewatch_method(trakt_id):
    if str(trakt_id) in get_min_rewatch_list():
        return REWATCH_METHODS.LEAST_WATCHED
    elif str(trakt_id) in get_max_rewatch_list():
        return REWATCH_METHODS.MOST_WATCHED
    else:
        return REWATCH_METHODS.LAST_WATCHED

def make_plays(history):
    plays = {}
    if 'seasons' in history:
        for season in history['seasons']:
            plays[season['number']] = {}
            for episode in season['episodes']:
                plays[season['number']][episode['number']] = episode['plays']
    logger.log('Plays: %s' % plays, log_utils.LOGDEBUG)
    return plays
    
def get_next_rewatch(trakt_id, plays, progress):
    rewatch_method = get_rewatch_method(trakt_id)
    next_episode = None
    pick_next = False
    if rewatch_method == REWATCH_METHODS.LEAST_WATCHED:
        min_plays = None
        for season in progress['seasons']:
            ep_plays = plays.get(season['number'], {})
            for episode in season['episodes']:
                if min_plays is None or ep_plays.get(episode['number'], 0) < min_plays:
                    next_episode = {'season': season['number'], 'episode': episode['number']}
                    min_plays = ep_plays.get(episode['number'], 0)
                    logger.log('Min Episode: %s - %s' % (min_plays, next_episode), log_utils.LOGDEBUG)
    elif rewatch_method == REWATCH_METHODS.MOST_WATCHED:
        max_plays = None
        for season in progress['seasons']:
            ep_plays = plays.get(season['number'], {})
            for episode in season['episodes']:
                if max_plays is None or pick_next:
                    next_episode = {'season': season['number'], 'episode': episode['number']}
                    if max_plays is None:
                        max_plays = 0
                        first_episode = next_episode
                    pick_next = False
                    logger.log('Max Next Episode: %s' % next_episode, log_utils.LOGDEBUG)
                if ep_plays.get(episode['number'], 0) >= max_plays:
                    pick_next = True
                    max_plays = ep_plays.get(episode['number'], 0)
                    logger.log('Max Episode: %sx%s = %s' % (season['number'], episode['number'], max_plays))
            
            if max_plays == ep_plays.get(episode['number'], 0):
                next_episode = first_episode
    else:
        last_watched_at = progress['last_watched_at']
        first = True
        first_episode = None
        for season in progress['seasons']:
            for episode in season['episodes']:
                if first:
                    first_episode = {'season': season['number'], 'episode': episode['number']}
                    first = False
                    
                if last_watched_at is None or pick_next:
                    return {'season': season['number'], 'episode': episode['number']}
                elif episode['last_watched_at'] == last_watched_at:
                    logger.log('Last Watched: Season: %s - %s' % (season['number'], episode), log_utils.LOGDEBUG)
                    pick_next = True
        
        if next_episode is None:
            next_episode = first_episode
    
    return next_episode

def i18n(string_id):
    return translations.i18n(string_id)

def chunks(l, n):
    """
    Yield successive n-sized chunks from l.
    """
    for i in list(range(0, len(l), n)):
        yield l[i:i + n]

def cleanse_title(text):
    def fixup(m):
        text = m.group(0)
        if not text.endswith(';'):
            text += ';'
        if text[:2] == "&#":
            # character reference
            try:
                if text[:3] == "&#x":
                    return chr(int(text[3:-1], 16))
                else:
                    return chr(int(text[2:-1]))
            except ValueError:
                pass
        else:
            # named entity
            try:
                text = chr(html.entities.name2codepoint[text[1:-1]])
            except KeyError:
                pass

        # replace nbsp with a space
        text = text.replace('\xa0', ' ')
        return text
    if isinstance(text, str):
        try: 
            text = text
        except:
            try: 
                text = text.decode('utf-8', 'ignore')
            except: 
                pass

    return re.sub("&(\w+;|#x?\d+;?)", fixup, text.strip())

def normalize_title(title):
    if title is None:
        title = ''
    title = cleanse_title(title)
    new_title = title.upper()
    new_title = re.sub('[^A-Za-z0-9]', '', new_title)
    if isinstance(new_title, str):
        new_title = new_title
    # logger.log('In title: |%s| Out title: |%s|' % (title,new_title), log_utils.LOGDEBUG)
    return new_title

def crc32(s):
    if s is None:
        return None
    string = s.lower()
    sb = bytearray(string.encode())
    crc = 0xFFFFFFFF
    for b in sb:
        crc = crc ^ (b << 24)
        for i in range(8):
            if (crc & 0x80000000):
                crc = (crc << 1) ^ 0x04C11DB7
            else:
                crc = crc << 1
        crc = crc & 0xFFFFFFFF
    return '%08x' % (crc)

def ungz(compressed):
    buf = io.BytesIO(compressed)
    f = gzip.GzipFile(fileobj=buf)
    html = f.read().decode('utf-8')
#     before = len(compressed) / 1024.0
#     after = len(html) / 1024.0
#     saved = (after - before) / after
#     logger.log('Uncompressing gzip input Before: {before:.2f}KB After: {after:.2f}KB Saved: {saved:.2%}'.format(before=before, after=after, saved=saved))
    return html

def copy2clip(txt):
	from sys import platform
	if platform == "win32":
		try:
			from subprocess import check_call
			cmd = 'echo ' + txt.replace('&', '^&').strip() + '|clip'
			return check_call(cmd, shell=True)
		except: pass
	elif platform == "darwin":
		try:
			from subprocess import check_call
			cmd = 'echo ' + txt.strip() + '|pbcopy'
			return check_call(cmd, shell=True)
		except: pass
	elif platform == "linux":
		try:
			from subprocess import Popen, PIPE
			p = Popen(['xsel', '-pi'], stdin=PIPE)
			p.communicate(input=txt)
		except: pass