"""
    Image Cache Module
    Copyright (C) 2024 tknorris

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
import os
import kodi
import requests
from asguard_lib import image_scraper, control
from asguard_lib.image_cache import local_lib
import xbmcvfs
import zipfile
import log_utils
import logging

logger = log_utils.Logger.get_logger(__name__)

logging.basicConfig(level=logging.DEBUG)

local_lib._update_db()
db_connection = local_lib.db_utils.DBCache(local_lib.DB_PATH)

TMDB_API_KEY = kodi.get_setting('tmdb_key')

def fetch_images_from_tmdb(tmdb_id, media_type):
    # Convert tmdb_id and media_type to the format expected by image_scraper.get_images
    video_ids = {'tmdb': tmdb_id}
    video_type = 'movie' if media_type == 'movie' else 'tvshow'  
    
    # Call the function with proper parameters
    return image_scraper.get_images(video_type, video_ids, cached=False)

def get_movie_images(tmdb_id):
    try:
        images = fetch_images_from_tmdb(tmdb_id, 'movie')
        db_connection.update_movie(tmdb_id, images)
        return images
    except Exception as e:
        logger.log(f"Error fetching movie images: {e}", log_utils.LOGERROR)
        return {}

def get_tv_images(tmdb_id):
    try:
        images = fetch_images_from_tmdb(tmdb_id, 'tv')
        db_connection.update_tvshow(tmdb_id, images)
        return images
    except Exception as e:
        logger.log(f"Error fetching TV show images: {e}", log_utils.LOGERROR)
        return {}

def get_person_images(tmdb_id):
    try:
        images = fetch_images_from_tmdb(tmdb_id, 'person')
        db_connection.update_person(tmdb_id, images)
        return images
    except Exception as e:
        logger.log(f"Error fetching person images: {e}", log_utils.LOGERROR)
        return {}