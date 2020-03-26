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
import local_lib
import xbmcvfs
import zipfile

local_lib._update_db()
db_connection = local_lib.db_utils.DBCache(local_lib.DB_PATH)

def get_movie_images(tmdb_id):
    return db_connection.get_movie(tmdb_id)

def get_tv_images(tmdb_id):
    return db_connection.get_tvshow(tmdb_id)

def get_person_images(tmdb_id):
    return db_connection.get_person(tmdb_id)
