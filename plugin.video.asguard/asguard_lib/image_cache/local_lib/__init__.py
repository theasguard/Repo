"""
    Image Cache Module for Asguard Addon
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

import log_utils
import os
import zipfile
import xbmcvfs
import kodi
import utils
# Absolute imports
from asguard_lib.image_cache.local_lib import strings
from asguard_lib.image_cache.local_lib import db_utils
import xbmcaddon

logger = log_utils.Logger.get_logger()

addon = xbmcaddon.Addon('plugin.video.asguard')

def get_profile():
    return addon.getAddonInfo('profile')

def get_version():
    return addon.getAddonInfo('version')

CACHE_NAME = 'tmdb_cache'
DB_NAME = CACHE_NAME + '.db'
ZIP_NAME = CACHE_NAME + '.zip'
DB_FOLDER = kodi.translate_path(get_profile())
DB_PATH = os.path.join(DB_FOLDER, DB_NAME)
ZIP_SOURCE = os.path.join('https://github.com/theasguard/Asguard-Updates/raw/main/', ZIP_NAME)

def _update_db():
    db_ver = None
    if xbmcvfs.exists(DB_PATH):
        db_connection = db_utils.DBCache(DB_PATH)
        db_ver = db_connection.get_setting('db_version')
        db_connection.close()
    
    if db_ver != get_version():
        try:
            # Attempt to download the media
            logger.log(f"Downloading from {ZIP_SOURCE} to {DB_FOLDER} as {ZIP_NAME}", log_utils.LOGDEBUG)
            try:
                zip_path = utils.download_media(ZIP_SOURCE, DB_FOLDER, ZIP_NAME, kodi.Translations(strings.STRINGS), utils.PROGRESS.WINDOW)
            except TypeError:
                zip_path = utils.download_media(ZIP_SOURCE, DB_FOLDER, ZIP_NAME, kodi.Translations(strings.STRINGS))
            
            if not zip_path:
                raise Exception("Failed to download the zip file.")
            
            # Extract the downloaded zip file
            logger.log(f"Extracting {zip_path} to {DB_FOLDER}", log_utils.LOGDEBUG)
            with zipfile.ZipFile(zip_path, 'r') as zip_file:
                zip_file.extract(DB_NAME, DB_FOLDER)
            
            # Update the database version
            db_connection = db_utils.DBCache(DB_PATH)
            db_connection.set_setting('db_version', get_version())
        except Exception as e:
            logger.log(f"Error updating database: {e}", log_utils.LOGDEBUG)
        finally:
            # Clean up the zip file if it exists
            if xbmcvfs.exists(zip_path):
                xbmcvfs.delete(zip_path)