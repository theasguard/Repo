"""
    Image Cache Module
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
import os
import kodi
import requests
from asguard_lib.image_cache import local_lib
import xbmcvfs
import zipfile

local_lib._update_db()
db_connection = local_lib.db_utils.DBCache(local_lib.DB_PATH)

TMDB_API_KEY = kodi.get_setting('tmdb_key') # Replace with your TMDB API key

def fetch_images_from_tmdb(tmdb_id, media_type):
    url = f'https://api.themoviedb.org/3/{media_type}/{tmdb_id}/images?api_key={TMDB_API_KEY}'
    response = requests.get(url)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Failed to fetch images: {response.status_code}")

def get_movie_images(tmdb_id):
    images = fetch_images_from_tmdb(tmdb_id, 'movie')
    db_connection.update_movie(tmdb_id, images)
    return images

def get_tv_images(tmdb_id):
    images = fetch_images_from_tmdb(tmdb_id, 'tv')
    db_connection.update_tvshow(tmdb_id, images)
    return images

def get_person_images(tmdb_id):
    images = fetch_images_from_tmdb(tmdb_id, 'person')
    db_connection.update_person(tmdb_id, images)
    return images