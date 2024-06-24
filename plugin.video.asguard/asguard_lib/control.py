
import os
import sys
import threading
import xbmcgui
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
progressDialog = xbmcgui.DialogProgress()


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

