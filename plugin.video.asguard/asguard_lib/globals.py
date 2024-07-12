
import contextlib
import json
import os
import re
import sys
import traceback
import unicodedata
from functools import cached_property
from urllib import parse
from xml.etree import ElementTree
from third_party import pytz

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs
from unidecode import unidecode
try:
    HANDLE = int(sys.argv[1])
except IndexError:
    HANDLE = -1

class GlobalVariables:
    CONTENT_MENU = ""
    CONTENT_FILES = "files"
    CONTENT_MOVIE = "movies"
    CONTENT_SHOW = "tvshows"
    CONTENT_SEASON = "seasons"
    CONTENT_EPISODE = "episodes"
    CONTENT_GENRES = "genres"
    CONTENT_YEARS = "years"
    MEDIA_MENU = ""
    MEDIA_FOLDER = "file"
    MEDIA_MOVIE = "movie"
    MEDIA_SHOW = "tvshow"
    MEDIA_SEASON = "season"
    MEDIA_EPISODE = "episode"

    SEMVER_REGEX = re.compile(r"^((?:\d+\.){2}\d+)")

    def __init__(self):
        self.IS_ADDON_FIRSTRUN = None
        self.ADDON = None
        self.ADDON_DATA_PATH = None
        self.ADDON_ID = None
        self.ADDON_NAME = None
        self.VERSION = None
        self.CLEAN_VERSION = None
        self.USER_AGENT = None
        self.DEFAULT_FANART = None
        self.DEFAULT_ICON = None
        self.DEFAULT_LOGO = None
        self.DEFAULT_POSTER = None
        self.NEXT_PAGE_ICON = None
        self.ADDON_USERDATA_PATH = None
        self.SETTINGS_CACHE = None
        self.RUNTIME_SETTINGS_CACHE = None
        self.LANGUAGE_CACHE = {}
        self.PLAYLIST = None
        self.HOME_WINDOW = None
        self.KODI_DATE_LONG_FORMAT = None
        self.KODI_DATE_SHORT_FORMAT = None
        self.KODI_TIME_FORMAT = None
        self.KODI_TIME_NO_SECONDS_FORMAT = None
        self.KODI_FULL_VERSION = None
        self.KODI_VERSION = None
        self.PLATFORM = self._get_system_platform()
        self.UTC_TIMEZONE = pytz.utc
        self.LOCAL_TIMEZONE = None
        self.URL = None
        self.PLUGIN_HANDLE = 0
        self.IS_SERVICE = True
        self.BASE_URL = None
        self.PATH = None
        self.PARAM_STRING = None
        self.REQUEST_PARAMS = None
        self.FROM_WIDGET = False
        self.PAGE = 1

    def __del__(self):
        self.deinit()

    def deinit(self):
        self.ADDON = None
        del self.ADDON
        self.PLAYLIST = None
        del self.PLAYLIST
        self.HOME_WINDOW = None
        del self.HOME_WINDOW

    def init_globals(self, argv=None, addon_id=None):
        self.IS_ADDON_FIRSTRUN = self.IS_ADDON_FIRSTRUN is None
        self.ADDON = xbmcaddon.Addon()
        self.ADDON_ID = addon_id or self.ADDON.getAddonInfo("id")
        self.ADDON_NAME = self.ADDON.getAddonInfo("name")
        self.VERSION = self.ADDON.getAddonInfo("version")
        self.CLEAN_VERSION = self.SEMVER_REGEX.findall(self.VERSION)[0]
        self.USER_AGENT = f"{self.ADDON_NAME} - {self.CLEAN_VERSION}"
        self._init_kodi()
        self._init_local_timezone()
        self._init_paths()
        self.DEFAULT_FANART = self.ADDON.getAddonInfo("fanart")
        self.DEFAULT_ICON = self.ADDON.getAddonInfo("icon")
        self.DEFAULT_LOGO = f"{self.IMAGES_PATH}icon.png"
        self.DEFAULT_POSTER = f"{self.IMAGES_PATH}fanart.jpg"
        self.NEXT_PAGE_ICON = f"{self.IMAGES_PATH}next.png"
        self.init_request(argv)
        self._init_cache()

    def _init_kodi(self):
        self.PLAYLIST = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
        self.HOME_WINDOW = xbmcgui.Window(10000)
        self.KODI_DATE_LONG_FORMAT = xbmc.getRegion("datelong")
        self.KODI_DATE_SHORT_FORMAT = xbmc.getRegion("dateshort")
        self.KODI_TIME_FORMAT = xbmc.getRegion("time")
        self.KODI_TIME_NO_SECONDS_FORMAT = self.KODI_TIME_FORMAT.replace(":%S", "")
        self.KODI_FULL_VERSION = xbmc.getInfoLabel("System.BuildVersion")
        if version := re.findall(r'(?:(?:((?:\d+\.?){1,3}\S+))?\s+\(((?:\d+\.?){2,3})\))', self.KODI_FULL_VERSION):
            self.KODI_FULL_VERSION = version[0][1]
            if len(version[0][0]) > 1:
                pre_ver = version[0][0][:2]
                full_ver = version[0][1][:2]
                if pre_ver > full_ver:
                    self.KODI_VERSION = int(pre_ver[:2])
                else:
                    self.KODI_VERSION = int(full_ver[:2])
            else:
                self.KODI_VERSION = int(version[0][1][:2])
        else:
            self.KODI_FULL_VERSION = self.KODI_FULL_VERSION.split(' ')[0]
            self.KODI_VERSION = int(self.KODI_FULL_VERSION[:2])

    @staticmethod
    def _get_system_platform():
        """
        get platform on which xbmc run
        """
        platform = "unknown"
        if xbmc.getCondVisibility("system.platform.android"):
            platform = "android"
        elif xbmc.getCondVisibility("system.platform.linux"):
            platform = "linux"
        elif xbmc.getCondVisibility("system.platform.xbox"):
            platform = "xbox"
        elif xbmc.getCondVisibility("system.platform.windows"):
            platform = "xbox" if "Users\\UserMgr" in os.environ.get("TMP") else "windows"
        elif xbmc.getCondVisibility("system.platform.osx"):
            platform = "osx"

        return platform

    def get_language_string(self, localization_id, addon=True):
        """
        Gets a localized string from cache if feasible, if not from localization files
        Will retrieve from addon localizations by default but can be requested from Kodi localizations

        :param localization_id: The id of the localization to retrieve
        :type localization_id: int
        :param addon: True to retrieve from addon, False from Kodi localizations.  Default True
        :type addon bool
        :return: The localized text matching the localization_id from the appropriate localization files.
        :rtype: str
        """
        cache_id = f"A{str(localization_id)}" if addon else f"K{str(localization_id)}"
        text = self.LANGUAGE_CACHE.get(cache_id)
        if not text:
            text = self.ADDON.getLocalizedString(localization_id) if addon else xbmc.getLocalizedString(localization_id)
            self.LANGUAGE_CACHE.update({cache_id: text})

        return text
