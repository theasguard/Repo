# -*- coding: utf-8 -*-

'''
    Asgard Add-on
    Copyright (C) 2025 MrBlamo

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
'''

import urllib.parse, urllib.request
import requests
import cache
import kodi
import log_utils
import utils
import xbmcaddon
import json


logger = log_utils.Logger.get_logger()

ADDON = xbmcaddon.Addon()
ANILIST_API = 'https://graphql.anilist.co'