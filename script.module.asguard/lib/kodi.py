"""
    tknorris shared module
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
import gettext
import xbmcaddon, xbmc, xbmcgui, xbmcplugin, xbmcvfs, os, sys, re, json, time
import six
from urllib.parse import urlencode, parse_qs
from kodi_six import xbmc, xbmcgui, xbmcplugin, xbmcaddon, xbmcvfs
from six.moves.urllib.parse import urlencode
import CustomProgressDialog
from urllib.parse import urlencode, quote, unquote
from html.parser import HTMLParser

addon = xbmcaddon.Addon()
get_setting = addon.getSetting
show_settings = addon.openSettings
sleep = xbmc.sleep
_log = xbmc.log
dialog = xbmcgui.Dialog()
dp = xbmcgui.DialogProgress()
try:
    _kodiver = float(xbmcaddon.Addon('xbmc.addon').getAddonInfo('version')[:4])
except ValueError:
    pass  # Avoid error while executing unit tests
datafolder = xbmcvfs.translatePath(os.path.join('special://profile/addon_data/', addon.getAddonInfo('id')))
addonfolder = xbmcvfs.translatePath(os.path.join('special://home/addons/', addon.getAddonInfo('id')))
addonicon = xbmcvfs.translatePath(os.path.join(addonfolder, 'icon.png'))
addonfanart = xbmcvfs.translatePath(os.path.join(addonfolder, 'fanart.jpg'))
execute = xbmc.executebuiltin


def execute_jsonrpc(command):
    if not isinstance(command, str):
        command = json.dumps(command)
    response = xbmc.executeJSONRPC(command)
    return json.loads(response)

def get_path():
    return addon.getAddonInfo('path')

def get_profile():
    return addon.getAddonInfo('profile')

def translate_path(path):
    return xbmcvfs.translatePath(path)

def set_setting(id, value):
    if not isinstance(value, six.string_types):
        value = str(value)
    addon.setSetting(id, value)

def supported_video_extensions():
    supported_video_extensions = xbmc.getSupportedMedia('video').split('|')
    unsupported = ['.url', '.zip', '.rar', '.001', '.7z', '.tar.gz', '.tar.bz2',
                   '.tar.xz', '.tgz', '.tbz2', '.gz', '.bz2', '.xz', '.tar', '']
    return [i for i in supported_video_extensions if i not in unsupported]


def accumulate_setting(setting, addend=1):
    cur_value = get_setting(setting)
    cur_value = int(cur_value) if cur_value else 0
    set_setting(setting, cur_value + addend)

def get_version():
    return addon.getAddonInfo('version')

def get_id():
    return addon.getAddonInfo('id')

def get_name():
    return addon.getAddonInfo('name')

def has_addon(addon_id):
    return xbmc.getCondVisibility(f'System.HasAddon({addon_id})') == 1

def get_kodi_version():
    class MetaClass(type):
        def __str__(self):
            return f'|{self.version}| -> |{self.major}|{self.minor}|{self.tag}|{self.tag_version}|{self.revision}|'
        
    class KodiVersion(metaclass=MetaClass):
        version = xbmc.getInfoLabel('System.BuildVersion')
        major, minor, tag, tag_version, revision = 0, 0, '', 0, ''
        
        match = re.search(r'([0-9]+)\.([0-9]+)', version)
        if match:
            major, minor = map(int, match.groups())
        
        match = re.search(r'-([a-zA-Z]+)([0-9]*)', version)
        if match:
            tag, tag_version = match.groups()
            tag_version = int(tag_version) if tag_version else 0
        
        match = re.search(r'\w+:(\w+-\w+)', version)
        if match:
            revision = match.group(1)
        
    return KodiVersion

def getKodiVersion():
    return int(xbmc.getInfoLabel("System.BuildVersion").split(".")[0])


def metadataClean(metadata):
    if metadata == None:
        return metadata
    allowed = ['aired', 'album', 'artist', 'cast',
        'castandrole', 'code', 'country', 'credits', 'dateadded', 'dbid', 'director',
        'duration', 'episode', 'episodeguide', 'genre', 'imdbnumber', 'lastplayed',
        'mediatype', 'mpaa', 'originaltitle', 'overlay', 'path', 'playcount', 'plot',
        'plotoutline', 'premiered', 'rating', 'season', 'set', 'setid', 'setoverview',
        'showlink', 'sortepisode', 'sortseason', 'sorttitle', 'status', 'studio', 'tag',
        'tagline', 'title', 'top250', 'totalepisodes', 'totalteasons', 'tracknumber',
        'trailer', 'tvshowtitle', 'userrating', 'votes', 'watched', 'writer', 'year'
    ]
    return {k: v for k, v in six.iteritems(metadata) if k in allowed}


def get_plugin_url(queries):
    """
    Constructs a plugin URL with the given query parameters.

    Args:
        queries (dict): A dictionary of query parameters.

    Returns:
        str: The constructed plugin URL.
    """
    try:
        query = urlencode(queries)
    except UnicodeEncodeError:
        for k, v in queries.items():
            if isinstance(v, str):
                queries[k] = v.encode('utf-8')
        query = urlencode(queries)

    return f"{sys.argv[0]}?{query}"

def end_of_directory(cache_to_disc=True):
    xbmcplugin.endOfDirectory(int(sys.argv[1]), cacheToDisc=cache_to_disc)

def set_content(content):
    xbmcplugin.setContent(int(sys.argv[1]), content)

def update_listitem(list_item, label):
    if isinstance(label, dict):
        cast2 = label.pop('cast2') if 'cast2' in label.keys() else []
        unique_ids = label.pop('unique_ids') if 'unique_ids' in label.keys() else {}

    if _kodiver > 19.8 and isinstance(label, dict):
        vtag = list_item.getVideoInfoTag()
        if label.get('mediatype'):
            vtag.setMediaType(label['mediatype'])
        if label.get('title'):
            vtag.setTitle(label['title'])
        if label.get('tvshowtitle'):
            vtag.setTvShowTitle(label['tvshowtitle'])
        if label.get('plot'):
            vtag.setPlot(label['plot'])
        if label.get('year'):
            vtag.setYear(int(label['year']))
        if label.get('premiered'):
            vtag.setPremiered(label['premiered'])
        if label.get('status'):
            vtag.setTvShowStatus(label['status'])
        if label.get('duration'):
            vtag.setDuration(label['duration'])
        if label.get('country'):
            vtag.setCountries([label['country']])
        if label.get('genre'):
            vtag.setGenres(label['genre'])
        if label.get('studio'):
            vtag.setStudios(label['studio'])
        if label.get('rating'):
            vtag.setRating(label['rating'])
        if label.get('trailer'):
            vtag.setTrailer(label['trailer'])
        if label.get('season'):
            vtag.setSeason(int(label['season']))
        if label.get('episode'):
            vtag.setEpisode(int(label['episode']))
        if label.get('aired'):
            vtag.setFirstAired(label['aired'])
        if label.get('playcount'):
            vtag.setPlaycount(label['playcount'])
        if cast2:
            cast2 = [xbmc.Actor(p['name'], p['role'], cast2.index(p), p['thumbnail']) for p in cast2]
            vtag.setCast(cast2)
        if unique_ids:
            vtag.setUniqueIDs(unique_ids)
            if 'imdb' in list(unique_ids.keys()):
                vtag.setIMDBNumber(unique_ids['imdb'])
    else:
        list_item.setInfo(type='Video', infoLabels=label)
        if cast2:
            list_item.setCast(cast2)
        if unique_ids:
            list_item.setUniqueIDs(unique_ids)
    return

def create_item(queries, label, thumb='', fanart='', is_folder=None, is_playable=None, total_items=0, menu_items=None, replace_menu=False):
    if not thumb:
        thumb = os.path.join(get_path(), 'icon.png')

    list_item = xbmcgui.ListItem(label)
    list_item.setArt({'icon': thumb, 'thumb': thumb, 'fanart': fanart})
    # if isinstance(label, dict):
    #     update_listitem(list_item, label)
    add_item(queries, list_item, fanart, is_folder, is_playable, total_items, menu_items, replace_menu)

def add_item(queries, list_item, fanart='', is_folder=None, is_playable=None, total_items=0, menu_items=None, replace_menu=False):
    if menu_items is None:
        menu_items = []
    if is_folder is None:
        is_folder = False if is_playable else True

    if is_playable is None:
        playable = 'false' if is_folder else 'true'
    else:
        playable = 'true' if is_playable else 'false'

    liz_url = get_plugin_url(queries)
    if fanart:
        list_item.setProperty('fanart_image', fanart)
    list_item.setInfo('video', {'title': list_item.getLabel()})
    list_item.setProperty('isPlayable', playable)
    list_item.addContextMenuItems(menu_items, replaceItems=replace_menu)
    xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, list_item, isFolder=is_folder, totalItems=total_items)


def parse_query(query):
    q = {'mode': 'main'}
    if query.startswith('?'):
        query = query[1:]
    queries = parse_qs(query)
    for key in queries:
        if len(queries[key]) == 1:
            q[key] = queries[key][0]
        else:
            q[key] = queries[key]
    return q


def notify(header=None, msg='', duration=2000, sound=None):
    if header is None:
        header = get_name()
    if sound is None:
        sound = get_setting('mute_notifications') == 'false'
    icon_path = os.path.join(get_path(), 'icon.png')
    try:
        xbmcgui.Dialog().notification(header, msg, icon_path, duration, sound)
    except:
        builtin = "XBMC.Notification(%s,%s, %s, %s)" % (header, msg, duration, icon_path)
        xbmc.executebuiltin(builtin)


def close_all():
    xbmc.executebuiltin('Dialog.Close(all)')


def get_current_view():
    skinPath = translate_path('special://skin/')
    xml = os.path.join(skinPath, 'addon.xml')
    f = xbmcvfs.File(xml)
    read = f.read()
    f.close()
    try:
        src = re.search('defaultresolution="([^"]+)', read, re.DOTALL).group(1)
    except:
        src = re.search('<res.+?folder="([^"]+)', read, re.DOTALL).group(1)
    src = os.path.join(skinPath, src, 'MyVideoNav.xml')
    f = xbmcvfs.File(src)
    read = f.read()
    f.close()
    match = re.search('<views>([^<]+)', read, re.DOTALL)
    if match:
        views = match.group(1)
        for view in views.split(','):
            if xbmc.getInfoLabel('Control.GetLabel(%s)' % view):
                return view

def set_view(content, set_view=False, set_sort=False):
    if content:
        set_content(content)

    if set_view:
        view = get_setting(f'{content}_view')
        if view and view != '0':
            _log(f'Setting View to {view} ({content})', xbmc.LOGDEBUG)
            xbmc.executebuiltin(f'Container.SetViewMode({view})')

    # set sort methods - probably we don't need all of them
    if set_sort:
        xbmcplugin.addSortMethod(handle=int(sys.argv[1]), sortMethod=xbmcplugin.SORT_METHOD_UNSORTED)
        xbmcplugin.addSortMethod(handle=int(sys.argv[1]), sortMethod=xbmcplugin.SORT_METHOD_VIDEO_SORT_TITLE_IGNORE_THE)
        xbmcplugin.addSortMethod(handle=int(sys.argv[1]), sortMethod=xbmcplugin.SORT_METHOD_VIDEO_YEAR)
        xbmcplugin.addSortMethod(handle=int(sys.argv[1]), sortMethod=xbmcplugin.SORT_METHOD_MPAA_RATING)
        xbmcplugin.addSortMethod(handle=int(sys.argv[1]), sortMethod=xbmcplugin.SORT_METHOD_DATE)
        xbmcplugin.addSortMethod(handle=int(sys.argv[1]), sortMethod=xbmcplugin.SORT_METHOD_VIDEO_RUNTIME)
        xbmcplugin.addSortMethod(handle=int(sys.argv[1]), sortMethod=xbmcplugin.SORT_METHOD_GENRE)

def yesnoDialog(heading=get_name(), line1='', line2='', line3='', nolabel='', yeslabel=''):
    return xbmcgui.Dialog().yesno(heading, line1 + '[CR]' + line2 + '[CR]' + line3, nolabel=nolabel, yeslabel=yeslabel)

def refresh_container():
    xbmc.executebuiltin("Container.Refresh")

def update_container(url):
    xbmc.executebuiltin(f'Container.Update({url})')

def get_keyboard(heading, default=''):
    keyboard = xbmc.Keyboard()
    keyboard.setHeading(heading)
    if default:
        keyboard.setDefault(default)
    keyboard.doModal()
    if keyboard.isConfirmed():
        return keyboard.getText()
    else:
        return None

def ulib(string, enc=False):
    try:
        if enc:
            string = quote(string)
        else:
            string = unquote(string)
        return string
    except:
        return string

def unicodeEscape(string):
    try:
        string = string.encode("unicode-escape").decode()
        return string
    except:
        return string

def convertSize(size):
    import math
    if size == 0:
        return '0 MB'
    size_name = ("B", "KB", "MB", "GB", "TB", "PB", "EB", "ZB", "YB")
    i = int(math.floor(math.log(size, 1024)))
    p = math.pow(1024, i)
    s = round(size / p, 2)
    return f'{s} {size_name[i]}'

def TextBoxes(announce):
    class TextBox:
        WINDOW = 10147
        CONTROL_LABEL = 1
        CONTROL_TEXTBOX = 5

        def __init__(self, *args, **kwargs):
            xbmc.executebuiltin(f"ActivateWindow({self.WINDOW})")
            self.win = xbmcgui.Window(self.WINDOW)
            xbmc.sleep(500)
            self.setControls()

        def setControls(self):
            self.win.getControl(self.CONTROL_LABEL).setLabel('[COLOR red]XXX-O-DUS[/COLOR]')
            try:
                with open(announce) as f:
                    text = f.read()
            except:
                text = announce
            self.win.getControl(self.CONTROL_TEXTBOX).setText(str(text))

    TextBox()
    while xbmc.getCondVisibility('Window.IsVisible(10147)'):
        time.sleep(0.5)

class MLStripper(HTMLParser):
    def __init__(self):
        super().__init__()
        self.fed = []

    def handle_data(self, d):
        self.fed.append(d)

    def get_data(self):
        return ''.join(self.fed)

def strip_tags(html):
    s = MLStripper()
    s.feed(html)
    return s.get_data()

class Translations(object):
    def __init__(self, strings):
        self.strings = strings
        self.addon = xbmcaddon.Addon()
        self.language = xbmc.getLanguage(xbmc.ISO_639_1)
        self.locale_path = os.path.join(self.addon.getAddonInfo('path'), 'resources', 'language', self.language, 'strings.po')
        self.translation = None

        if os.path.exists(self.locale_path):
            try:
                self.translation = gettext.translation('base', localedir=os.path.dirname(self.locale_path), languages=[self.language])
                self.translation.install()
            except Exception as e:
                xbmc.log('%s: Failed to load .po translations: %s' % (self.addon.getAddonInfo('id'), e), xbmc.LOGWARNING)

    def i18n(self, string_id):
        if self.translation:
            try:
                return self.translation.gettext(self.strings[string_id])
            except KeyError:
                xbmc.log('%s: Failed String Lookup in .po: %s' % (self.addon.getAddonInfo('id'), string_id), xbmc.LOGWARNING)
        try:
            return self.addon.getLocalizedString(self.strings[string_id])
        except KeyError as e:
            xbmc.log('%s: Failed String Lookup in strings.py: %s (%s)' % (self.addon.getAddonInfo('id'), string_id, e), xbmc.LOGWARNING)
            return string_id

    def get_scraper_label_id(scraper_name):
        """Maps scraper names to their language string IDs"""
        SCRAPER_IDS = {
            'AioStreams': 40643,
            'DebridCloud': 30398,
            'CouchTuner': 30399,
            'Animetosho': 30400,
            'DDLValley': 30401,
            'EasyNews': 30402,
            'Furk.net': 30403,
            'Local': 30404,
            'Orion': 30405,
            'Premiumize.me': 30406,
            'Premiumize.V2': 30407,
            'RMZ': 30408,
            'scene-rls': 30409,
            'TorrentGalaxy': 30410,
            'LosMovies': 30411,
            'Torrentio': 30412,
            'Bitlord': 30413,
            'Aniwatch': 30414,
            'Binged': 30415,
            'SeriesOnline': 30416,
            'Nyaa': 30418,
            '1337x': 30419,
            'Bitsearch': 30420,
            'Anidex': 30421,
            'Elfhosted': 30422,
            'EZTV': 30423,
            'KAT': 30424,
            'H!anime': 30425,
            'H!anime Alt': 30426,
            'RARBG': 30427,
            'Rutor': 30428,
            'SkyTorrents': 30429,
            'Torrentz2': 30430,
            'Snowfl': 30431,
            'Movie4K': 30432,
            'TorrentDownload': 30433,
            'Gogoanime': 30605,
            'Gogoanime alt': 40606,
            'NunFlix': 40607,
            'Limetorrents': 40608,
            'SolarMovie': 40609,
            'Kickass2': 40611,
            'Dailymotion': 40612,
            'DebridSearch': 40613,
            'IsoHunt2': 40614,
            'YourBittorrent': 40615,
            'BitCQ': 40616,
            'TorrentFunk': 40617,
            'GogoHD': 40621,
            'TorrentFunk': 40622,
            'ReleaseBB': 40624,
            'Vidsrc': 40625,
            'WatchSeriesHD': 40627,
            'Thepiratebay': 40628,
            'Mediafusion': 40629,
            'PFTV': 40630,
            'Jackettio': 40631,
            'Comet': 40632,
            'GloDLS': 40634,
            'AniRena': 40639,
            'AioStreams': 40643,
            'Qbit': 40655,
            'Torlock': 40656,
            'iDope': 40812,
            'CloudTorrents': 40635,
            'WebStreamr': 40915,
            'DoMovies': 40814,
            'BstSrs': 40815,
            'TVMovieFlix': 40816,
            'SFlixWatch': 40817,
            'M4UHD': 40818,
            # Add more mappings as needed
        }
        return SCRAPER_IDS.get(scraper_name, 30000)  # Fallback to default

class WorkingDialog(object):
    def __init__(self):
        xbmc.executebuiltin('ActivateWindow(busydialog)')

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        xbmc.executebuiltin('Dialog.Close(busydialog)')

    def update_progress(self, percent):
        xbmc.executebuiltin(f'Notification(Progress Update, {percent}%, 2000)')

def has_addon(addon_id):
    return xbmc.getCondVisibility('System.HasAddon(%s)' % addon_id) == 1

class ProgressDialog(object):
    def __init__(self, heading, line1='', line2='', line3='', background=False, active=True, timer=0):
        self.line1 = line1
        self.line2 = line2
        self.line3 = line3
        self.begin = time.time()
        self.timer = timer
        self.background = background
        self.heading = heading
        if active and not timer:
            self.pd = self.__create_dialog(line1, line2, line3)
            self.pd.update(0)
        else:
            self.pd = None

    def __create_dialog(self, line1, line2, line3):
        if self.background:
            pd = xbmcgui.DialogProgressBG()
            msg = line1 + line2 + line3
            pd.create(self.heading, msg)
        else:
            if xbmc.getCondVisibility('Window.IsVisible(progressdialog)'):
                pd = CustomProgressDialog.ProgressDialog()
            else:
                pd = xbmcgui.DialogProgress()
            if six.PY2:
                pd.create(self.heading, line1, line2, line3)
            else:
                pd.create(self.heading,
                          line1 + '\n'
                          + line2 + '\n'
                          + line3)
        return pd

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        if self.pd is not None:
            self.pd.close()
            del self.pd

    def is_canceled(self):
        if self.pd is not None and not self.background:
            return self.pd.iscanceled()
        else:
            return False

    def update(self, percent, line1='', line2='', line3=''):
        if not line1:
            line1 = self.line1
        if not line2:
            line2 = self.line2
        if not line3:
            line3 = self.line3
        if self.pd is None and self.timer and (time.time() - self.begin) >= self.timer:
            self.pd = self.__create_dialog(line1, line2, line3)

        if self.pd is not None:
            if self.background:
                msg = line1 + line2 + line3
                self.pd.update(int(percent), self.heading, msg)
            else:
                if six.PY2:
                    self.pd.update(int(percent), line1, line2, line3)
                else:
                    self.pd.update(int(percent),
                                line1 + '\n'
                                + line2 + '\n'
                                + line3)


class CountdownDialog(object):
    __INTERVALS = 5

    def __init__(self, heading, line1='', line2='', line3='', active=True, countdown=60, interval=5):
        self.heading = heading
        self.countdown = countdown
        self.interval = interval
        self.line1 = line1
        self.line2 = line2
        self.line3 = line3
        if active:
            if xbmc.getCondVisibility('Window.IsVisible(progressdialog)'):
                pd = CustomProgressDialog.ProgressDialog()
            else:
                pd = xbmcgui.DialogProgress()
            if not self.line3:
                line3 = 'Expires in: %s seconds' % countdown
            if six.PY2:
                pd.create(self.heading, line1, line2, line3)
            else:
                pd.create(self.heading,
                          line1 + '\n'
                          + line2 + '\n'
                          + line3)
            pd.update(100)
            self.pd = pd
        else:
            self.pd = None

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        if self.pd is not None:
            self.pd.close()
            del self.pd

    def start(self, func, args=None, kwargs=None):
        if args is None:
            args = []
        if kwargs is None:
            kwargs = {}
        result = func(*args, **kwargs)
        if result:
            return result

        if self.pd is not None:
            start = time.time()
            expires = time_left = self.countdown
            interval = self.interval
            while time_left > 0:
                for _ in range(CountdownDialog.__INTERVALS):
                    sleep(int(interval * 1000 / CountdownDialog.__INTERVALS))
                    if self.is_canceled():
                        return
                    time_left = expires - int(time.time() - start)
                    if time_left < 0:
                        time_left = 0
                    progress = int(time_left * 100 / expires)
                    line3 = 'Expires in: %s seconds' % time_left if not self.line3 else ''
                    self.update(progress, line3=line3)

                result = func(*args, **kwargs)
                if result:
                    return result

    def is_canceled(self):
        if self.pd is None:
            return False
        else:
            return self.pd.iscanceled()

    def update(self, percent, line1='', line2='', line3=''):
        if not line1:
            line1 = self.line1
        if not line2:
            line2 = self.line2
        if not line3:
            line3 = self.line3
        if self.pd is not None:
            if six.PY2:
                self.pd.update(percent, line1, line2, line3)
            else:
                self.pd.update(percent,
                               line1 + '\n'
                               + line2 + '\n'
                               + line3)

# Additional functions for Kodi 21+ improvements

def get_addon_info(info):
    return addon.getAddonInfo(info)

def get_addon_setting(setting):
    return addon.getSetting(setting)

def set_addon_setting(setting, value):
    addon.setSetting(setting, value)

def get_addon_profile():
    return xbmcvfs.translatePath(addon.getAddonInfo('profile'))

def get_addon_data_folder():
    return xbmcvfs.translatePath(os.path.join('special://profile/addon_data/', addon.getAddonInfo('id')))

def get_addon_path():
    return xbmcvfs.translatePath(addon.getAddonInfo('path'))

def get_addon_icon():
    return xbmcvfs.translatePath(os.path.join(get_addon_path(), 'icon.png'))

def get_addon_fanart():
    return xbmcvfs.translatePath(os.path.join(get_addon_path(), 'fanart.jpg'))

def log(msg, level=xbmc.LOGDEBUG):
    xbmc.log(f'{addon.getAddonInfo("name")}: {msg}', level)

def show_notification(header, message, icon=None, time=5000, sound=True):
    if icon is None:
        icon = get_addon_icon()
    xbmcgui.Dialog().notification(header, message, icon, time, sound)

def show_busy_dialog():
    xbmc.executebuiltin('ActivateWindow(busydialog)')

def hide_busy_dialog():
    xbmc.executebuiltin('Dialog.Close(busydialog)')

def show_settings_dialog():
    addon.openSettings()

def get_kodi_build_version():
    return xbmc.getInfoLabel('System.BuildVersion')

def get_kodi_platform():
    return xbmc.getInfoLabel('System.Platform')

def get_kodi_language():
    return xbmc.getLanguage()

def get_kodi_region():
    return xbmc.getRegion('locale')

def get_kodi_timezone():
    return xbmc.getRegion('timezone')

def get_kodi_country():
    return xbmc.getRegion('country')

def get_kodi_city():
    return xbmc.getRegion('city')

def get_kodi_currency():
    return xbmc.getRegion('currency')
