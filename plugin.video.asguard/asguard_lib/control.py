
import os
import sys
import threading
import xbmcgui
import six
from kodi_six import xbmc, xbmcaddon, xbmcplugin, xbmcvfs
from six.moves import urllib_parse

try:
    HANDLE = int(sys.argv[1])
except IndexError:
    HANDLE = -1

addonInfo = xbmcaddon.Addon().getAddonInfo
ADDON_VERSION = addonInfo('version')
ADDON_NAME = addonInfo('name')
ADDON_ID = addonInfo('id')
ADDON_ICON = addonInfo('icon')
__settings__ = xbmcaddon.Addon(ADDON_ID)
__language__ = __settings__.getLocalizedString
addonInfo = __settings__.getAddonInfo
PY2 = sys.version_info[0] == 2
PY3 = sys.version_info[0] == 3
TRANSLATEPATH = xbmc.translatePath if PY2 else xbmcvfs.translatePath
LOGINFO = xbmc.LOGNOTICE if PY2 else xbmc.LOGINFO
INPUT_ALPHANUM = xbmcgui.INPUT_ALPHANUM
pathExists = xbmcvfs.exists
dataPath = TRANSLATEPATH(addonInfo('profile'))
ADDON_PATH = __settings__.getAddonInfo('path')
sleep = xbmc.sleep
item = xbmcgui.ListItem
mappingPath = TRANSLATEPATH(xbmcaddon.Addon('script.otaku.mappings').getAddonInfo('path'))
mappingDB = os.path.join(mappingPath, 'resources', 'data', 'anime_mappings.db')
mappingDB_lock = threading.Lock()
progressDialog = xbmcgui.DialogProgress()
dbFile = os.path.join(dataPath, 'debridcache.db')
ALL_EMBEDS = ['doodstream', 'filelions', 'filemoon', 'iga', 'kwik', 'hd-2',
              'mp4upload', 'mycloud', 'streamtape', 'streamwish', 'vidcdn',
              'vidplay', 'hd-1', 'yourupload', 'zto']


def create_multiline_message(line1=None, line2=None, line3=None, *lines):
    """Creates a message from the supplied lines

    :param line1:Line 1
    :type line1:str
    :param line2:Line 2
    :type line2:str
    :param line3: Line3
    :type line3:str
    :param lines:List of additional lines
    :type lines:list[str]
    :return:New message wit the combined lines
    :rtype:str
    """
    result = []
    if line1:
        result.append(line1)
    if line2:
        result.append(line2)
    if line3:
        result.append(line3)
    if lines:
        result.extend(l for l in lines if l)
    return "\n".join(result)

def copy2clip(txt):
    import subprocess
    platform = sys.platform

    if platform == 'win32':
        try:
            cmd = 'echo %s|clip' % txt.strip()
            return subprocess.check_call(cmd, shell=True)
        except:
            pass
    elif platform == 'linux2':
        try:
            from subprocess import PIPE, Popen
            p = Popen(['xsel', '-pi'], stdin=PIPE)
            p.communicate(input=txt)
        except:
            pass

def setGlobalProp(property, value):
    xbmcgui.Window(10000).setProperty(property, str(value))

def enabled_embeds():
    embeds = [embed for embed in ALL_EMBEDS]
    return embeds

def getGlobalProp(property):
    value = xbmcgui.Window(10000).getProperty(property)
    if value.lower in ("true", "false"):
        return value.lower == "true"
    else:
        return value

def refresh():
    return xbmc.executebuiltin('Container.Refresh')


def settingsMenu():
    return xbmcaddon.Addon().openSettings()


def getSetting(key):
    return __settings__.getSetting(key)


def setSetting(id, value):
    return __settings__.setSetting(id=id, value=value)

def lang(x):
    return __language__(x)

def real_debrid_enabled():
    return True if getSetting('rd.auth') != '' and getSetting('realdebrid.enabled') == 'true' else False


def debrid_link_enabled():
    return True if getSetting('dl.auth') != '' and getSetting('dl.enabled') == 'true' else False


def all_debrid_enabled():
    return True if getSetting('alldebrid.apikey') != '' and getSetting('alldebrid.enabled') == 'true' else False


def premiumize_enabled():
    return True if getSetting('premiumize.token') != '' and getSetting('premiumize.enabled') == 'true' else False

def multiselect_dialog(title, _list):
    return xbmcgui.Dialog().multiselect(title, _list)

def colorString(text, color=None):
    if color == 'default' or color == '' or color is None:
        color = 'deepskyblue'

    return '[COLOR %s]%s[/COLOR]' % (color, text)

def select_dialog(title, dialog_list):
    return xbmcgui.Dialog().select(title, dialog_list)

def ok_dialog(title, text):
    return xbmcgui.Dialog().ok(title, text)

def try_release_lock(lock):
    if lock.locked():
        lock.release()

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