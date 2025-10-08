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

def get_movie_images(tmdb_id):
    return db_connection.get_movie(tmdb_id)

def get_tv_images(tmdb_id):
    return db_connection.get_tvshow(tmdb_id)

def get_person_images(tmdb_id):
    return db_connection.get_person(tmdb_id)

def get_season_images(tmdb_id, season):
    return db_connection.get_season(tmdb_id, season)
    
def get_episode_images(tmdb_id, season, episode):
    return db_connection.get_episode(tmdb_id, season, episode)