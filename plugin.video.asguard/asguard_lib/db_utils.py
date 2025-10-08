"""
    Asguard Addon
    Copyright (C) 2024 MrBlamo, tknorris

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
from abc import abstractmethod
import datetime
import functools
import logging
import pickle
import os
import re
import sqlite3
import time
import csv
import json
import hashlib
import threading
from threading import Semaphore
from contextlib import contextmanager
import requests
import xbmc, xbmcaddon, xbmcvfs, xbmcgui, log_utils, kodi, cache, six
from asguard_lib import control
from .utils2 import i18n

logger = log_utils.Logger.get_logger(__name__)
logging.basicConfig(level=logging.DEBUG)

def enum(**enums):
    return type('Enum', (), enums)

class DatabaseRecoveryError(Exception):
    pass


DB_TYPES = enum(MYSQL='mysql', SQLITE='sqlite')
CSV_MARKERS = enum(REL_URL='***REL_URL***', OTHER_LISTS='***OTHER_LISTS***', SAVED_SEARCHES='***SAVED_SEARCHES***', BOOKMARKS='***BOOKMARKS***')
MAX_TRIES = 5
MYSQL_DATA_SIZE = 512
MYSQL_URL_SIZE = 255
MYSQL_MAX_BLOB_SIZE = 16777215

INCREASED = False
UP_THRESHOLD = 5
DOWN_THRESHOLD = 5
CHECK_THRESHOLD = 50
WRITERS = [0, 1, 5, 25, 50, 100]
try: SPEED = int(kodi.get_setting('machine_speed'))
except: SPEED = 0
if SPEED:
    MAX_WRITERS = WRITERS[SPEED]
else:
    try: MAX_WRITERS = int(kodi.get_setting('sema_value')) or 1
    except: MAX_WRITERS = 1
SQL_SEMA = Semaphore(MAX_WRITERS)
SOURCE_CHUNK = 200

class DB_Connection():
    locks = 0
    writes = 0
    worker_id = None
    _connection_pool = {}  # Add connection pool
    _pool_lock = threading.Lock() 
    
    def __init__(self):
        global OperationalError
        global DatabaseError
        self.dbname = kodi.get_setting('db_name')
        self.username = kodi.get_setting('db_user')
        self.password = kodi.get_setting('db_pass')
        self.address = kodi.get_setting('db_address')
        self.db = None
        self.progress = None
        self._local = threading.local()

        if kodi.get_setting('use_remote_db') == 'true':
            if all((self.address, self.username, self.password, self.dbname)):
                import mysql.connector as db_lib  # @UnresolvedImport @UnusedImport
                from mysql.connector import OperationalError as OperationalError  # @UnresolvedImport
                from mysql.connector import DatabaseError as DatabaseError  # @UnresolvedImport
                logger.log('Loading MySQL as DB engine', log_utils.LOGDEBUG)
                self.db_type = DB_TYPES.MYSQL
            else:
                logger.log('MySQL is enabled but not setup correctly', log_utils.LOGERROR)
                raise ValueError('MySQL enabled but not setup correctly')
        else:
            from sqlite3 import dbapi2 as db_lib  # @Reimport
            from sqlite3 import OperationalError as OperationalError  # @UnusedImport @Reimport
            from sqlite3 import DatabaseError as DatabaseError  # @UnusedImport @Reimport
            logger.log('Loading sqlite3 as DB engine', log_utils.LOGDEBUG)
            self.db_type = DB_TYPES.SQLITE
            db_dir = kodi.translate_path("special://database")
            self.db_path = os.path.join(db_dir, 'asguard_cache.db')
        self.db_lib = db_lib

    def flush_cache(self):
        if self.db_type == DB_TYPES.SQLITE:
            self.__execute('VACUUM')

    def clear_collection_cache(self, media_type):
        """Clear Trakt collection cache for specific media type"""
        try:
            # Clear URL cache entries related to collection
            patterns = [
                f'/users/me/collection/{media_type}%',
                f'/sync/collection%',
                f'%collection%{media_type}%'
            ]
            
            for pattern in patterns:
                sql = 'DELETE FROM url_cache WHERE url LIKE ?'
                self.__execute(sql, (pattern,))
                
            logger.log(f'Cleared {media_type} collection cache', log_utils.LOGDEBUG)
        except Exception as e:
            logger.log(f'Error clearing collection cache: {str(e)}', log_utils.LOGERROR)

    def clear_watchlist_cache(self, media_type):
        """Clear Trakt watchlist cache for specific media type"""
        try:
            # Clear URL cache entries related to watchlist
            patterns = [
                f'/users/me/watchlist/{media_type}%',
                f'/sync/watchlist%',
                f'%watchlist%{media_type}%'
            ]
            
            for pattern in patterns:
                sql = 'DELETE FROM url_cache WHERE url LIKE ?'
                self.__execute(sql, (pattern,))
                
            logger.log(f'Cleared {media_type} watchlist cache', log_utils.LOGDEBUG)
        except Exception as e:
            logger.log(f'Error clearing watchlist cache: {str(e)}', log_utils.LOGERROR)

    def clear_trakt_cache_by_activity(self, activity_type, media_type):
        """Clear specific Trakt cache based on activity type and media type"""
        try:
            cache_patterns = {
                'collection': [
                    f'/users/me/collection/{media_type}%',
                    f'/sync/collection%'
                ],
                'watchlist': [
                    f'/users/me/watchlist/{media_type}%', 
                    f'/sync/watchlist%'
                ],
                'watched': [
                    f'/sync/watched/{media_type}%',
                    f'/users/me/watched/%'
                ],
                'lists': [
                    f'/users/me/lists%',
                    f'/users/likes/lists%'
                ]
            }
            
            patterns = cache_patterns.get(activity_type, [])
            for pattern in patterns:
                sql = 'DELETE FROM url_cache WHERE url LIKE ?'
                self.__execute(sql, (pattern,))
                
            logger.log(f'Cleared {activity_type} cache for {media_type}', log_utils.LOGDEBUG)
        except Exception as e:
            logger.log(f'Error clearing activity cache: {str(e)}', log_utils.LOGERROR)
    
    def prune_cache(self, prune_age=31):
        min_age = time.time() - prune_age * (60 * 60 * 24)
        if self.db_type == DB_TYPES.SQLITE:
            day = {'day': 'DATE(timestamp, "unixepoch")'}
        else:
            day = {'day': 'DATE(FROM_UNIXTIME(timestamp))'}
            
        sql = 'SELECT {day},COUNT(*) FROM url_cache WHERE timestamp < ? GROUP BY {day} ORDER BY {day}'.format(**day)
        rows = self.__execute(sql, (min_age,))
        if rows:
            del_date, count = rows[0]
            logger.log('Pruning url cache of %s rows with date %s' % (count, del_date), log_utils.LOGDEBUG)
            sql = 'DELETE FROM url_cache WHERE {day} = ?'.format(**day)
            self.__execute(sql, (del_date,))
            return len(rows)
        else:
            return False
    
    def get_bookmark(self, trakt_id, season='', episode=''):
        if not trakt_id: return None
        sql = 'SELECT resumepoint FROM bookmark where slug=? and season=? and episode=?'
        bookmark = self.__execute(sql, (trakt_id, season, episode))
        if bookmark:
            return bookmark[0][0]
        else:
            return None

    def get_bookmarks(self):
        sql = 'SELECT * FROM bookmark'
        bookmarks = self.__execute(sql)
        return bookmarks

    def get_cached_genres(self):
        sql = 'SELECT slug, name FROM genres_cache'
        rows = self.__execute(sql)
        return {row[0]: row[1] for row in rows}

    def cache_genres(self, genres):
        sql = 'REPLACE INTO genres_cache (slug, name) VALUES (?, ?)'
        for genre in genres:
            self.__execute(sql, (genre['slug'], genre['name']))

    def bookmark_exists(self, trakt_id, season='', episode=''):
        return self.get_bookmark(trakt_id, season, episode) != None

    def set_bookmark(self, trakt_id, offset, season='', episode=''):
        if not trakt_id: return
        sql = 'REPLACE INTO bookmark (slug, season, episode, resumepoint) VALUES(?, ?, ?,?)'
        self.__execute(sql, (trakt_id, season, episode, offset))

    def clear_bookmark(self, trakt_id, season='', episode=''):
        if not trakt_id: return
        sql = 'DELETE FROM bookmark WHERE slug=? and season=? and episode=?'
        self.__execute(sql, (trakt_id, season, episode))


    def get_trakt_id_by_tmdb(self, tmdb_id):
        control.mappingDB_lock.acquire()
        try:
            conn = sqlite3.connect(control.mappingDB, timeout=60.0)
            conn.row_factory = _dict_factory
            conn.execute("PRAGMA FOREIGN_KEYS = 1")
            cursor = conn.cursor()
            mapping = None
            if tmdb_id:
                db_query = 'SELECT trakt_id FROM anime WHERE themoviedb_id = ?'
                cursor.execute(db_query, (tmdb_id,))
                mapping = cursor.fetchone()
                cursor.close()
        finally:
            control.try_release_lock(control.mappingDB_lock)
            conn.close()
        return mapping['trakt_id'] if mapping else None


    def cache_tmdb_trakt_mapping(self, tmdb_id, trakt_id):
        """Persist a TMDB->Trakt mapping in the MAIN DB (id_mapping table)."""
        if not tmdb_id or not trakt_id:
            return False
        try:
            sql = 'REPLACE INTO id_mapping (themoviedb_id, trakt_id) VALUES (?, ?)'
            self.__execute(sql, (int(tmdb_id), int(trakt_id)))
            return True
        except Exception as e:
            logger.log('Failed to cache tmdb->trakt mapping: %s' % str(e), log_utils.LOGWARNING)
            return False



    def get_cached_tmdb_trakt_mapping(self, tmdb_id):
        """Read a cached TMDB->Trakt mapping from MAIN DB (id_mapping)."""
        if not tmdb_id: return None
        try:
            sql = 'SELECT trakt_id FROM id_mapping WHERE themoviedb_id = ?'
            rows = self.__execute(sql, (tmdb_id,))
            return rows[0][0] if rows else None
        except Exception:
            return None


    def get_trakt_id_by_tmdb_cached(self, tmdb_id):
        """Try anime mapping first, then fallback MAIN DB id_mapping table."""
        tid = self.get_trakt_id_by_tmdb(tmdb_id)
        if tid:
            # also backfill into main DB for future lookups
            try:
                self.cache_tmdb_trakt_mapping(tmdb_id, tid)
            except Exception:
                pass
            return tid
        return self.get_cached_tmdb_trakt_mapping(tmdb_id)
        
    def cache_url(self, url, body, data=None, res_header=None):
        logger.log('Cache URL: URL: %s, Data: %s, Res Header: %s' % (url, data, res_header), log_utils.LOGDEBUG)
        now = time.time()
        if data is None: data = ''
        if res_header is None: res_header = []
        res_header = json.dumps(res_header)
        
        # truncate data if running mysql and greater than col size
        if self.db_type == DB_TYPES.MYSQL and len(url) > MYSQL_URL_SIZE:
            url = url[:MYSQL_URL_SIZE]
        if self.db_type == DB_TYPES.MYSQL and len(data) > MYSQL_DATA_SIZE:
            data = data[:MYSQL_DATA_SIZE]

        if isinstance(body, str):
            body = body.encode('utf-8')

        if self.db_type == DB_TYPES.SQLITE:
            body = memoryview(body)
        sql = 'REPLACE INTO url_cache (url, data, response, res_header, timestamp) VALUES(?, ?, ?, ?, ?)'
        self.__execute(sql, (url, data, body, res_header, now))

    def delete_cached_url(self, url, data=''):
        if data is None: data = ''
        # truncate data if running mysql and greater than col size
        if self.db_type == DB_TYPES.MYSQL and len(data) > MYSQL_DATA_SIZE:
            data = data[:MYSQL_DATA_SIZE]
        sql = 'DELETE FROM url_cache WHERE url = ? and data= ?'
        self.__execute(sql, (url, data))

    def get_cached_url(self, url, data='', cache_limit=8):
        if data is None: data = ''
        # truncate data if running mysql and greater than col size
        if self.db_type == DB_TYPES.MYSQL and len(data) > MYSQL_DATA_SIZE:
            data = data[:MYSQL_DATA_SIZE]
        html = ''
        res_header = []
        created = 0
        now = time.time()
        age = now - created
        limit = 60 * 60 * cache_limit
        sql = 'SELECT timestamp, response, res_header FROM url_cache WHERE url = ? and data=?'
        rows = self.__execute(sql, (url, data))

        if rows:
            created = float(rows[0][0])
            res_header = json.loads(rows[0][2])
            age = now - created
            if age < limit:
                html = rows[0][1]
                if isinstance(html, (memoryview, bytes)):
                    html = html.tobytes().decode('utf-8') if isinstance(html, memoryview) else html.decode('utf-8')
                else:
                    html = str(html)
        logger.log('DB Cache: Url: %s, Data: %s, Cache Hit: %s, created: %s, age: %.2fs (%.2fh), limit: %.2fs (%.2fh)' % (url, data, bool(html), created, age, age / (60 * 60), limit, limit / (60 * 60)), log_utils.LOGDEBUG)
        return created, res_header, html

    def get_all_urls(self, include_response=False, order_matters=False):
        sql = 'SELECT url, data'
        if include_response: sql += ',response'
        sql += ' FROM url_cache'
        if order_matters: sql += ' ORDER BY url, data'
        rows = self.__execute(sql)
        return rows


    def update_show_meta(self, anilist_id, meta_ids, art):
        if isinstance(meta_ids, dict):
            meta_ids = pickle.dumps(meta_ids)
        if isinstance(art, dict):
            art = pickle.dumps(art)
        
        sql = '''
            REPLACE INTO shows_meta (
                anilist_id, meta_ids, art
            ) VALUES (?, ?, ?)
        '''
        
        try:
            self.__execute('PRAGMA foreign_keys=OFF')
            self.__execute(sql, (anilist_id, meta_ids, art))
            self.__execute('PRAGMA foreign_keys=ON')
            self.db.commit()
            logger.log('Updated show metadata for AniList ID: %s' % anilist_id, log_utils.LOGDEBUG)
        except Exception as e:
            logger.log('Failed to update show metadata for AniList ID: %s, Error: %s' % (anilist_id, str(e)), log_utils.LOGERROR)
            import traceback
            traceback.print_exc()

    def cache_function(self, name, args=None, kwargs=None, result=None):
        now = time.time()
        if args is None: args = []
        if kwargs is None: kwargs = {}
        pickle_result = pickle.dumps(result)

        if self.db_type == DB_TYPES.MYSQL and len(pickle_result) > MYSQL_MAX_BLOB_SIZE:
            logger.log('Result too large to cache', log_utils.LOGDEBUG)
            return

        if six.PY2:
            arg_hash = hashlib.md5(name).hexdigest() + hashlib.md5(str(args)).hexdigest() + hashlib.md5(str(kwargs)).hexdigest()
        else:
            arg_hash = hashlib.md5(name.encode('utf8')).hexdigest() + hashlib.md5(str(args).encode('utf8')).hexdigest() + hashlib.md5(str(kwargs).encode('utf8')).hexdigest()

        sql = 'REPLACE INTO function_cache (name, args, result, timestamp) VALUES(?, ?, ?, ?)'

        logger.log('Executing SQL: %s with params: %s' % (sql, (name, arg_hash, pickle_result, now)), log_utils.LOGDEBUG)
        self.__execute(sql, (name, arg_hash, pickle_result, now))
        logger.log('Function Cached: |%s|%s|%s| -> |%s|' % (name, args, kwargs, len(pickle_result)), log_utils.LOGDEBUG)

    def get_cached_function(self, name, args=None, kwargs=None, cache_limit=60 * 60):
        max_age = time.time() - cache_limit
        if args is None: args = []
        if kwargs is None: kwargs = {}
        if six.PY2:
            arg_hash = hashlib.md5(name).hexdigest() + hashlib.md5(str(args)).hexdigest() + hashlib.md5(str(kwargs)).hexdigest()
        else:
            arg_hash = hashlib.md5(name.encode('utf8')).hexdigest() + hashlib.md5(str(args).encode('utf8')).hexdigest() + hashlib.md5(str(kwargs).encode('utf8')).hexdigest()

        sql = 'SELECT result FROM function_cache WHERE name = ? and args = ? and timestamp >= ?'

        logger.log('Executing SQL: %s with params: %s' % (sql, (name, arg_hash, max_age)), log_utils.LOGDEBUG)
        rows = self.__execute(sql, (name, arg_hash, max_age))
        if rows:
            logger.log('Function Cache Hit: |%s|%s|%s| -> |%d|' % (name, args, kwargs, len(rows[0][0])), log_utils.LOGDEBUG)
            return True, pickle.loads(rows[0][0])
        else:
            logger.log('Function Cache Miss: |%s|%s|%s|' % (name, args, kwargs), log_utils.LOGDEBUG)
            return False, None


    def cache_sources(self, sources):
        sql = 'DELETE FROM source_cache'
        self.__execute(sql)
        for i in range(0, len(sources), SOURCE_CHUNK):
            uow = sources[i: i + SOURCE_CHUNK]
            for source in uow:
                if 'class' in source:
                    source['name'] = source['class'].get_name()
                    del source['class']
            pickled_row = pickle.dumps(uow)
            sql = 'INSERT INTO source_cache (source) VALUES (?)'
            self.__execute(sql, (pickled_row,))
    
    def cache_images(self, object_type, trakt_id, art_dict, season='', episode=''):
        now = time.time()
        for key in art_dict:
            if not art_dict[key]:
                art_dict[key] = None
                
        sql = 'REPLACE INTO image_cache (object_type, trakt_id, season, episode, timestamp, banner, fanart, thumb, poster, clearart, clearlogo)\
                values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)'
        self.__execute(sql, (object_type, trakt_id, season, episode, now, art_dict.get('banner'), art_dict.get('fanart'), art_dict.get('thumb'),
                             art_dict.get('poster'), art_dict.get('clearart'), art_dict.get('clearlogo')))
    
    def get_cached_images(self, object_type, trakt_id, season='', episode='', cache_limit=30 * 24):
        art_dict = {}
        sql = 'SELECT timestamp, banner, fanart, thumb, poster, clearart, clearlogo FROM image_cache WHERE object_type= ? and trakt_id = ? and season=? and episode=?'
        rows = self.__execute(sql, (object_type, trakt_id, season, episode))
        if rows:
            created, banner, fanart, thumb, poster, clearart, clearlogo = rows[0]
            if time.time() - float(created) < cache_limit * 60 * 60:
                art_dict = {'banner': banner, 'fanart': fanart, 'thumb': thumb, 'poster': poster, 'clearart': clearart, 'clearlogo': clearlogo}
        return art_dict

    def get_cached_episode_numbers(self, object_type, trakt_id, season='', episode=''):
        # 1. Try exact match first
        sql = '''SELECT season, episode FROM image_cache 
                WHERE object_type=? AND trakt_id=? AND season=? AND episode=?'''
        rows = self.__execute(sql, (object_type, trakt_id, season, episode))
        logger.log('Exact match results: %s' % rows, log_utils.LOGDEBUG)
        
        if not rows:
            # 2. Try latest season/episode for this show
            sql = '''SELECT season, episode FROM image_cache 
                    WHERE object_type=? AND trakt_id=?
                    ORDER BY timestamp DESC LIMIT 1'''
            rows = self.__execute(sql, (object_type, trakt_id))
            logger.log('Latest show results: %s' % rows, log_utils.LOGDEBUG)

        if not rows:
            # 3. Fallback to original values if no cache exists
            logger.log('No cache found, using original values', log_utils.LOGDEBUG)
            return season, episode

        return rows[0][0], rows[0][1]

    def flush_image_cache(self):
        sql = 'DELETE FROM image_cache'
        self.__execute(sql)
        if self.db_type == DB_TYPES.SQLITE:
            self.__execute('VACUUM')
            
        
    def get_cached_sources(self):
        sql = 'SELECT source from source_cache'
        rows = self.__execute(sql)
        sources = []
        for row in rows:
            col = row[0].encode('utf-8') if isinstance(row[0], str) else row[0]
            sources += pickle.loads(col)
        return sources
    
    def add_other_list(self, section, username, slug, name=None):
        sql = 'REPLACE INTO other_lists (section, username, slug, name) VALUES (?, ?, ?, ?)'
        self.__execute(sql, (section, username, slug, name))

    def delete_other_list(self, section, username, slug):
        sql = 'DELETE FROM other_lists WHERE section=? AND username=? and slug=?'
        self.__execute(sql, (section, username, slug))

    def rename_other_list(self, section, username, slug, name):
        sql = 'UPDATE other_lists set name=? WHERE section=? AND username=? AND slug=?'
        self.__execute(sql, (name, section, username, slug))

    def get_other_lists(self, section):
        sql = 'SELECT username, slug, name FROM other_lists WHERE section=?'
        rows = self.__execute(sql, (section,))
        return rows

    def get_all_other_lists(self):
        sql = 'SELECT * FROM other_lists'
        rows = self.__execute(sql)
        return rows

    def set_related_url(self, video_type, title, year, source, rel_url, season='', episode=''):
        if year is None: year = ''
        sql = 'REPLACE INTO rel_url (video_type, title, year, season, episode, source, rel_url) VALUES (?, ?, ?, ?, ?, ?, ?)'
        self.__execute(sql, (video_type, title, year, season, episode, source, rel_url))

    def clear_related_url(self, video_type, title, year, source, season='', episode=''):
        if year is None: year = ''
        sql = 'DELETE FROM rel_url WHERE video_type=? and title=? and year=? and source=?'
        params = [video_type, title, year, source]
        if season:
            sql += ' and season=?'
            params += [season]
        if episode:
            sql += ' and episode=?'
            params += [episode]
        self.__execute(sql, params)

    def clear_scraper_related_urls(self, source):
        sql = 'DELETE FROM rel_url WHERE source=?'
        params = [source]
        self.__execute(sql, params)

    def get_related_url(self, video_type, title, year, source, season='', episode=''):
        if year is None: year = ''
        sql = 'SELECT rel_url FROM rel_url WHERE video_type=? and title=? and year=? and season=? and episode=? and source=?'
        rows = self.__execute(sql, (video_type, title, year, season, episode, source))
        return rows

    def get_all_rel_urls(self):
        sql = 'SELECT * FROM rel_url'
        rows = self.__execute(sql)
        return rows

    def get_searches(self, section, order_matters=False):
        sql = 'SELECT id, query FROM saved_searches WHERE section=?'
        if order_matters: sql += 'ORDER BY added desc'
        rows = self.__execute(sql, (section,))
        return rows

    def get_all_searches(self):
        sql = 'SELECT * FROM saved_searches'
        rows = self.__execute(sql)
        return rows

    def save_search(self, section, query, added=None):
        if added is None: added = time.time()
        sql = 'INSERT INTO saved_searches (section, added, query) VALUES (?, ?, ?)'
        self.__execute(sql, (section, added, query))

    def delete_search(self, search_id):
        sql = 'DELETE FROM saved_searches WHERE id=?'
        self.__execute(sql, (search_id, ))

    def get_setting(self, setting):
        sql = 'SELECT value FROM db_info WHERE setting=?'
        rows = self.__execute(sql, (setting,))
        if rows:
            return rows[0][0]

    def set_setting(self, setting, value):
        sql = 'REPLACE INTO db_info (setting, value) VALUES (?, ?)'
        self.__execute(sql, (setting, value))

    def increment_db_setting(self, setting):
        cur_value = self.get_setting(setting)
        cur_value = int(cur_value) if cur_value else 0
        self.set_setting(setting, str(cur_value + 1))

    def export_from_db(self, full_path):
        temp_path = os.path.join(kodi.translate_path("special://profile/addon_data/plugin.video.asguard"), 'temp_export_%s.csv' % (int(time.time())))
        with open(temp_path, 'w') as f:
            writer = csv.writer(f)
            f.write('***VERSION: %s***\n' % self.get_db_version())
            if self.__table_exists('rel_url'):
                f.write(CSV_MARKERS.REL_URL + '\n')
                for fav in self.get_all_rel_urls():
                    writer.writerow(self.__utf8_encode(fav))
            if self.__table_exists('other_lists'):
                f.write(CSV_MARKERS.OTHER_LISTS + '\n')
                for sub in self.get_all_other_lists():
                    writer.writerow(self.__utf8_encode(sub))
            if self.__table_exists('saved_searches'):
                f.write(CSV_MARKERS.SAVED_SEARCHES + '\n')
                for sub in self.get_all_searches():
                    writer.writerow(self.__utf8_encode(sub))
            if self.__table_exists('bookmark'):
                f.write(CSV_MARKERS.BOOKMARKS + '\n')
                for sub in self.get_bookmarks():
                    writer.writerow(self.__utf8_encode(sub))

        logger.log('Copying export file from: |%s| to |%s|' % (temp_path, full_path), log_utils.LOGDEBUG)
        if not xbmcvfs.copy(temp_path, full_path):
            raise Exception('Export: Copy from |%s| to |%s| failed' % (temp_path, full_path))

        if not xbmcvfs.delete(temp_path):
            raise Exception('Export: Delete of %s failed.' % (temp_path))

    def __utf8_encode(self, items):
        l = []
        for i in items:
            if isinstance(i, str):
                try:
                    l.append(i.encode('utf-8'))
                except UnicodeDecodeError:
                    l.append(i)
            else:
                l.append(i)
        return l
        
    def import_into_db(self, full_path):
        addon_userdata_path = kodi.translate_path("special://profile/addon_data/plugin.video.asguard")
        temp_path = os.path.join(addon_userdata_path, 'temp_import_%s.csv' % (int(time.time())))
        logger.log('Copying import file from: |%s| to |%s|' % (full_path, temp_path), log_utils.LOGDEBUG)
        if not xbmcvfs.copy(full_path, temp_path):
            raise Exception('Import: Copy from |%s| to |%s| failed' % (full_path, temp_path))

        progress = None
        try:
            with open(temp_path, 'r', encoding='latin-1') as f:
                num_lines = sum(1 for _ in f)
            if self.progress:
                progress = self.progress
                try:
                    progress.update(0, 'Importing 0 of %s' % (num_lines))
                except Exception as e:
                    logger.log('Progress dialog update failed: %s' % str(e), log_utils.LOGWARNING)
                    progress = None
            else:
                try:
                    progress = xbmcgui.DialogProgress()
                    progress.create('Asguard', 'Import from %s' % (full_path))
                    progress.update(0, 'Importing 0 of %s' % (num_lines))
                except Exception as e:
                    logger.log('Progress dialog creation failed during import, continuing without progress display: %s' % str(e), log_utils.LOGWARNING)
                    progress = None
            
            with open(temp_path, 'r', encoding='latin-1') as f:
                reader = csv.reader(f)
                mode = ''
                _ = f.readline()  # read header
                i = 0
                for line in reader:
                    line = self.__unicode_encode(line)
                    if progress:
                        try:
                            progress.update(int(i * 100 / num_lines), 'Importing %s of %s' % (i, num_lines))
                            if progress.iscanceled():
                                return
                        except Exception as e:
                            logger.log('Progress dialog update failed during import: %s' % str(e), log_utils.LOGWARNING)
                            progress = None  # Disable further progress updates
                    if line[0] in [CSV_MARKERS.REL_URL, CSV_MARKERS.OTHER_LISTS, CSV_MARKERS.SAVED_SEARCHES, CSV_MARKERS.BOOKMARKS]:
                        mode = line[0]
                        continue
                    elif mode == CSV_MARKERS.REL_URL:
                        self.set_related_url(line[0], line[1], line[2], line[5], line[6], line[3], line[4])
                    elif mode == CSV_MARKERS.OTHER_LISTS:
                        name = None if len(line) != 4 else line[3]
                        self.add_other_list(line[0], line[1], line[2], name)
                    elif mode == CSV_MARKERS.SAVED_SEARCHES:
                        self.save_search(line[1], line[3], line[2])  # column order is different than method order
                    elif mode == CSV_MARKERS.BOOKMARKS:
                        self.set_bookmark(line[0], line[3], line[1], line[2])
                    else:
                        raise Exception('CSV line found while in no mode')
                    i += 1
        except Exception as e:
            logger.log('Import Failed: %s' % e, log_utils.LOGERROR)
            raise
        finally:
            try:
                if not xbmcvfs.delete(temp_path):
                    raise Exception('Import: Delete of %s failed.' % (temp_path))
            except Exception as e:
                logger.log('Error deleting temp file: %s' % e, log_utils.LOGERROR)
            if progress:
                try:
                    progress.close()
                except Exception as e:
                    logger.log('Progress dialog close failed: %s' % str(e), log_utils.LOGWARNING)
            self.progress = None
            if self.db_type == DB_TYPES.SQLITE:
                self.__execute('VACUUM')

    def __unicode_encode(self, items):
        l = []
        for i in items:
            if isinstance(i, bytes):
                try:
                    l.append(i.decode('utf-8'))
                except UnicodeDecodeError:
                    l.append(i)
            else:
                l.append(i)
        return l

        
    def execute_sql(self, sql):
        self.__execute(sql)

    # intended to be a common method for creating a db from scratch
    def init_database(self, db_version):
        try:
            cur_version = kodi.get_version()
            if db_version is not None and cur_version != db_version:
                logger.log('DB Upgrade from %s to %s detected.' % (db_version, cur_version), log_utils.LOGNOTICE)
                # Try to create progress dialog, but handle case where GUI isn't ready
                try:
                    self.progress = xbmcgui.DialogProgress()
                    self.progress.create('Asguard')
                    self.progress.update(0, 'Migrating from %s to %s' % (db_version, cur_version), 'Saving current data.')
                except Exception as e:
                    logger.log('Progress dialog creation failed, continuing without progress display: %s' % str(e), log_utils.LOGWARNING)
                    self.progress = None

                self.__prep_for_reinit()
    
            logger.log('Building Asguard Database', log_utils.LOGDEBUG)
            if self.db_type == DB_TYPES.MYSQL:
                self.__execute(f'''
                    CREATE TABLE IF NOT EXISTS url_cache (
                        url VARBINARY({MYSQL_URL_SIZE}) NOT NULL, 
                        data VARBINARY({MYSQL_DATA_SIZE}) NOT NULL, 
                        response MEDIUMBLOB, 
                        res_header TEXT, 
                        timestamp TEXT, 
                        PRIMARY KEY(url, data)
                    )
                ''')
                self.__execute('''
                    CREATE TABLE IF NOT EXISTS function_cache (
                        name TEXT NOT NULL, 
                        args TEXT NOT NULL,
                        response MEDIUMBLOB, 
                        result BLOB, 
                        timestamp REAL NOT NULL, 
                        PRIMARY KEY(name, args)
                    )
                ''')
                self.__execute('''
                    CREATE TABLE IF NOT EXISTS db_info (
                        setting VARCHAR(255) NOT NULL, 
                        value TEXT, 
                        PRIMARY KEY(setting)
                    )
                ''')
                self.__execute('''
                    CREATE TABLE IF NOT EXISTS rel_url (
                        video_type VARCHAR(15) NOT NULL, 
                        title VARCHAR(255) NOT NULL, 
                        year VARCHAR(4) NOT NULL, 
                        season VARCHAR(5) NOT NULL, 
                        episode VARCHAR(5) NOT NULL, 
                        source VARCHAR(49) NOT NULL, 
                        rel_url VARCHAR(255), 
                        PRIMARY KEY(video_type, title, year, season, episode, source)
                    )
                ''')
                self.__execute('''
                    CREATE TABLE IF NOT EXISTS other_lists (
                        section VARCHAR(10) NOT NULL, 
                        username VARCHAR(68) NOT NULL, 
                        slug VARCHAR(255) NOT NULL, 
                        name VARCHAR(255), 
                        PRIMARY KEY(section, username, slug)
                    )
                ''')
                self.__execute('''
                    CREATE TABLE IF NOT EXISTS saved_searches (
                        id INTEGER NOT NULL AUTO_INCREMENT, 
                        section VARCHAR(10) NOT NULL, 
                        added DOUBLE NOT NULL,
                        query VARCHAR(255) NOT NULL, 
                        PRIMARY KEY(id)
                    )
                ''')
                self.__execute('''
                    CREATE TABLE IF NOT EXISTS bookmark (
                        slug VARCHAR(255) NOT NULL, 
                        season VARCHAR(5) NOT NULL, 
                        episode VARCHAR(5) NOT NULL, 
                        resumepoint DOUBLE NOT NULL, 
                        PRIMARY KEY(slug, season, episode)
                    )
                ''')
                self.__execute('''
                    CREATE TABLE IF NOT EXISTS source_cache (
                        source BLOB NOT NULL
                    )
                ''')
                self.__execute('''
                    CREATE TABLE IF NOT EXISTS image_cache (
                        object_type VARCHAR(15), 
                        trakt_id INTEGER NOT NULL, 
                        season VARCHAR(5) NOT NULL, 
                        episode VARCHAR(5) NOT NULL,
                        timestamp TEXT, 
                        banner VARCHAR(255), 
                        fanart VARCHAR(255), 
                        thumb VARCHAR(255), 
                        poster VARCHAR(255), 
                        clearart VARCHAR(255), 
                        clearlogo VARCHAR(255), 
                        PRIMARY KEY(trakt_id, season, episode)
                    )
                ''')
                self.__execute('''
                    CREATE TABLE IF NOT EXISTS id_mapping (
                        themoviedb_id INTEGER NOT NULL,
                        trakt_id INTEGER,
                        PRIMARY KEY(themoviedb_id)
                    )
                ''')
                self.__execute('''
                    CREATE TABLE IF NOT EXISTS genres_cache (
                        slug VARCHAR(255) NOT NULL, 
                        name VARCHAR(255) NOT NULL, 
                        PRIMARY KEY(slug)
                    )
                ''')
            else:
                self.__create_sqlite_db()
                self.__execute('PRAGMA journal_mode=WAL')
                self.__execute('''
                    CREATE TABLE IF NOT EXISTS url_cache (
                        url VARCHAR(255) NOT NULL, 
                        data VARCHAR(255), 
                        response, 
                        res_header, 
                        timestamp, 
                        PRIMARY KEY(url, data, response)
                    )
                ''')
                self.__execute('''
                    CREATE TABLE IF NOT EXISTS function_cache (
                        name TEXT, 
                        args TEXT, 
                        result BLOB,
                        response,
                        timestamp INTEGER, 
                        PRIMARY KEY(name, args)
                    )
                ''')
                self.__execute('''
                    CREATE TABLE IF NOT EXISTS db_info (
                        setting VARCHAR(255), 
                        value TEXT, 
                        PRIMARY KEY(setting)
                    )
                ''')
                self.__execute('''
                    CREATE TABLE IF NOT EXISTS rel_url (
                        video_type TEXT NOT NULL, 
                        title TEXT NOT NULL, 
                        year TEXT NOT NULL, 
                        season TEXT NOT NULL, 
                        episode TEXT NOT NULL, 
                        source TEXT NOT NULL, 
                        rel_url TEXT, 
                        PRIMARY KEY(video_type, title, year, season, episode, source)
                    )
                ''')
                self.__execute('''
                    CREATE TABLE IF NOT EXISTS other_lists (
                        section TEXT NOT NULL, 
                        username TEXT NOT NULL, 
                        slug TEXT NOT NULL, 
                        name TEXT, 
                        PRIMARY KEY(section, username, slug)
                    )
                ''')
                self.__execute('''
                    CREATE TABLE IF NOT EXISTS saved_searches (
                        id INTEGER PRIMARY KEY, 
                        section TEXT NOT NULL, 
                        added DOUBLE NOT NULL,
                        query TEXT NOT NULL
                    )
                ''')
                self.__execute('''
                    CREATE TABLE IF NOT EXISTS bookmark (
                        slug TEXT NOT NULL, 
                        season TEXT NOT NULL, 
                        episode TEXT NOT NULL, 
                        resumepoint DOUBLE NOT NULL, 
                        PRIMARY KEY(slug, season, episode)
                    )
                ''')
                self.__execute('''
                    CREATE TABLE IF NOT EXISTS source_cache (
                        source TEXT NOT NULL
                    )
                ''')
                self.__execute('''
                    CREATE TABLE IF NOT EXISTS image_cache (
                        object_type TEXT NOT NULL, 
                        trakt_id INTEGER NOT NULL, 
                        season TEXT NOT NULL, 
                        episode TEXT NOT NULL,
                        timestamp, 
                        banner TEXT, 
                        fanart TEXT, 
                        thumb TEXT, 
                        poster TEXT, 
                        clearart TEXT, 
                        clearlogo TEXT, 
                        PRIMARY KEY(object_type, trakt_id, season, episode)
                    )
                ''')
                self.__execute('''
                    CREATE TABLE IF NOT EXISTS id_mapping (
                        themoviedb_id INTEGER PRIMARY KEY,
                        trakt_id INTEGER
                    )
                ''')
                self.__execute('''
                    CREATE TABLE IF NOT EXISTS genres_cache (
                        slug VARCHAR(255) NOT NULL, 
                        name VARCHAR(255) NOT NULL, 
                        PRIMARY KEY(slug)
                    )
                ''')
            # reload the previously saved backup export
            if db_version is not None and cur_version != db_version:
                logger.log('Restoring DB from backup at %s' % (self.mig_path), log_utils.LOGDEBUG)
                self.import_into_db(self.mig_path)
                logger.log('DB restored from %s' % (self.mig_path), log_utils.LOGNOTICE)
    
            sql = 'REPLACE INTO db_info (setting, value) VALUES(?,?)'
            self.__execute(sql, ('version', kodi.get_version()))
        finally:
            if self.progress is not None:
                self.progress.close()

    def __table_exists(self, table):
        if self.db_type == DB_TYPES.MYSQL:
            sql = 'SHOW TABLES LIKE ?'
        else:
            sql = 'select name from sqlite_master where type="table" and name = ?'
        rows = self.__execute(sql, (table,))

        if not rows:
            return False
        else:
            return True

    def reset_db(self):
        if self.db_type == DB_TYPES.SQLITE:
            try:
                # Close our own connection first
                if self.db:
                    self.db.close()
                    self.db = None
            except: 
                pass
            
            # Force close any remaining SQLite connections by attempting to connect and close
            try:
                import gc
                gc.collect()  # Force garbage collection to clean up any unused connections
                
                # Try to connect and immediately close to flush any remaining connections
                temp_conn = self.db_lib.connect(self.db_path)
                temp_conn.close()
            except:
                pass
            
            # Set db to None before attempting file operations
            self.db = None
            self.worker_id = None
            
            # Try a more aggressive approach: rename/move the file instead of deleting
            import time
            import uuid
            success = False
            
            # Generate unique backup name
            backup_name = self.db_path + '.backup.' + str(int(time.time())) + '.' + str(uuid.uuid4())[:8]
            
            try:
                # First, try to rename/move the database file (this usually works even when delete fails)
                if os.path.exists(self.db_path):
                    os.rename(self.db_path, backup_name)
                    logger.log('Moved database file to backup: %s' % backup_name, log_utils.LOGDEBUG)
                    success = True
                
                # Also move WAL and SHM files if they exist
                wal_path = self.db_path + '-wal'
                shm_path = self.db_path + '-shm'
                
                if os.path.exists(wal_path):
                    try:
                        os.rename(wal_path, backup_name + '-wal')
                        logger.log('Moved WAL file to backup', log_utils.LOGDEBUG)
                    except:
                        pass
                
                if os.path.exists(shm_path):
                    try:
                        os.rename(shm_path, backup_name + '-shm')
                        logger.log('Moved SHM file to backup', log_utils.LOGDEBUG)
                    except:
                        pass
                        
            except (OSError, PermissionError) as e:
                logger.log('Failed to rename database file: %s' % e, log_utils.LOGWARNING)
                
                # Last resort: try the original delete approach with retries
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        if os.path.exists(self.db_path):
                            os.remove(self.db_path)
                            logger.log('Successfully removed database file: %s' % self.db_path, log_utils.LOGDEBUG)
                        
                        # Also clean up WAL and SHM files if they exist
                        wal_path = self.db_path + '-wal'
                        shm_path = self.db_path + '-shm'
                        
                        if os.path.exists(wal_path):
                            try:
                                os.remove(wal_path)
                                logger.log('Removed WAL file: %s' % wal_path, log_utils.LOGDEBUG)
                            except:
                                pass
                        
                        if os.path.exists(shm_path):
                            try:
                                os.remove(shm_path)
                                logger.log('Removed SHM file: %s' % shm_path, log_utils.LOGDEBUG)
                            except:
                                pass
                        
                        success = True
                        break  # Success, exit retry loop
                        
                    except (OSError, PermissionError) as retry_e:
                        if attempt < max_retries - 1:
                            logger.log('Delete attempt %d/%d failed (retrying in 2s): %s' % (attempt + 1, max_retries, retry_e), log_utils.LOGWARNING)
                            time.sleep(2)  # Wait before retry
                        else:
                            logger.log('All delete attempts failed: %s' % retry_e, log_utils.LOGERROR)
                            raise Exception('Cannot remove database file - file is locked by other processes. Please close Kodi completely and restart, or manually delete: %s' % self.db_path)
            
            if not success:
                raise Exception('Failed to reset database - file operations failed')
            
            # Now create a fresh database
            self.init_database(None)
            
            # Try to clean up the backup file after a delay (optional cleanup)
            try:
                import threading
                def cleanup_backup():
                    try:
                        time.sleep(10)  # Wait 10 seconds
                        if os.path.exists(backup_name):
                            os.remove(backup_name)
                            logger.log('Cleaned up backup file: %s' % backup_name, log_utils.LOGDEBUG)
                        if os.path.exists(backup_name + '-wal'):
                            os.remove(backup_name + '-wal')
                        if os.path.exists(backup_name + '-shm'):
                            os.remove(backup_name + '-shm')
                    except:
                        pass  # Ignore cleanup failures
                
                cleanup_thread = threading.Thread(target=cleanup_backup)
                cleanup_thread.daemon = True
                cleanup_thread.start()
            except:
                pass  # Ignore cleanup thread creation failures
                
            return True
        else:
            return False

    def get_db_version(self):
        version = None
        try:
            sql = 'SELECT value FROM db_info WHERE setting="version"'
            rows = self.__execute(sql)
        except:
            return None

        if rows:
            version = rows[0][0]

        return version

    def force_close_all_connections(self):
        """Force close database connections - used before recovery operations"""
        try:
            if self.db:
                self.db.close()
            self.db = None
            self.worker_id = None
            
            # Force garbage collection to clean up any orphaned connections
            import gc
            gc.collect()
            
            logger.log('Forced closure of database connections', log_utils.LOGDEBUG)
        except Exception as e:
            logger.log('Error forcing connection closure: %s' % e, log_utils.LOGWARNING)

    def attempt_db_recovery(self):
        header = i18n('recovery_header')
        dialog = None
        
        # Try to create dialog, but handle case where GUI isn't ready
        try:
            dialog = xbmcgui.Dialog()
        except Exception as e:
            logger.log('Dialog creation failed, proceeding with automatic recovery: %s' % str(e), log_utils.LOGWARNING)
        
        # If dialog is available, ask user; otherwise proceed automatically
        should_migrate = True
        if dialog:
            try:
                should_migrate = dialog.yesno(header, i18n('rec_mig_1'), i18n('rec_mig_2'))
            except Exception as e:
                logger.log('Dialog interaction failed, proceeding automatically: %s' % str(e), log_utils.LOGWARNING)
                should_migrate = True
        
        if should_migrate:
            try: 
                # Force close connections before attempting recovery
                self.force_close_all_connections()
                self.init_database('Unknown')
                logger.log('Database recovery completed successfully', log_utils.LOGNOTICE)
            except Exception as e:
                logger.log('DB Migration Failed: %s' % (e), log_utils.LOGWARNING)
                if self.db_type == DB_TYPES.SQLITE:
                    should_reset = True
                    if dialog:
                        try:
                            should_reset = dialog.yesno(header, i18n('rec_reset_1'), i18n('rec_reset_2'), i18n('rec_reset_3'))
                        except Exception as dialog_e:
                            logger.log('Dialog interaction failed, proceeding with automatic reset: %s' % str(dialog_e), log_utils.LOGWARNING)
                            should_reset = True
                    
                    if should_reset:
                        try: 
                            # Force close connections before reset as well
                            self.force_close_all_connections()
                            self.reset_db()
                            try:
                                kodi.notify(msg=i18n('db_reset_success'), duration=5000)
                            except:
                                logger.log('Database reset completed successfully', log_utils.LOGNOTICE)
                        except Exception as e:
                            logger.log('Reset Failed: %s' % (e), log_utils.LOGWARNING)
                            if 'file may be in use' in str(e).lower() or 'cannot access the file' in str(e).lower():
                                try:
                                    kodi.notify(msg='Database reset failed: File is in use. Please close Kodi completely and restart.', duration=8000)
                                except:
                                    logger.log('Database reset failed: File is in use. Please close Kodi completely and restart.', log_utils.LOGERROR)
                            else:
                                try:
                                    kodi.notify(msg=i18n('reset_failed') % str(e), duration=5000)
                                except:
                                    logger.log('Reset failed: %s' % str(e), log_utils.LOGERROR)

    def __execute(self, sql, params=None):
        if params is None:
            params = []

        rows = None
        sql = self.__format(sql)
        is_read = self.__is_read(sql)
        if self.db_type == DB_TYPES.SQLITE and not is_read:
            SQL_SEMA.acquire()
            
        try:
            tries = 1
            while True:
                try:
                    if not is_read: DB_Connection.writes += 1
                    db_con = self.__get_db_connection()
                    cur = db_con.cursor()
                    logger.log('Executing SQL: %s with params: %s' % (sql, params), log_utils.LOGDEBUG)
                    cur.execute(sql, params)
                    if is_read:
                        rows = cur.fetchall()
                    cur.close()
                    db_con.commit()
                    if SPEED == 0:
                        self.__update_writers()
                    return rows
                except OperationalError as e:
                    if tries < MAX_TRIES:
                        tries += 1
                        logger.log('Retrying (%s/%s) SQL: %s Error: %s' % (tries, MAX_TRIES, sql, e), log_utils.LOGWARNING)
                        if 'database is locked' in str(e).lower():
                            DB_Connection.locks += 1
                        self.db = None
                    elif any(s for s in ['no such table', 'no such column'] if s in str(e)):
                        if self.db is not None:
                            db_con.rollback()
                        raise DatabaseRecoveryError(e)
                    else:
                        raise
                except DatabaseError as e:
                    if self.db is not None:
                        db_con.rollback()
                    raise DatabaseRecoveryError(e)
        finally:
            if self.db_type == DB_TYPES.SQLITE and not is_read:
                SQL_SEMA.release()

    def __update_writers(self):
        global MAX_WRITERS
        global INCREASED
        if self.db_type == DB_TYPES.SQLITE and DB_Connection.writes >= CHECK_THRESHOLD:
            lock_percent = DB_Connection.locks * 100 / DB_Connection.writes
            logger.log('Max Writers Update: %s/%s (%s%%) - %s' % (DB_Connection.locks, DB_Connection.writes, lock_percent, MAX_WRITERS))
            DB_Connection.writes = 0
            DB_Connection.locks = 0

            # allow more writers if locks are rare
            if lock_percent <= UP_THRESHOLD and not INCREASED:
                INCREASED = True
                MAX_WRITERS += 1
            # limit to fewer writers if locks are common
            elif MAX_WRITERS > 1 and lock_percent >= DOWN_THRESHOLD:
                MAX_WRITERS -= 1
            # just reset test if between threshholds or already only one writer
            else:
                return

            kodi.set_setting('sema_value', str(MAX_WRITERS))
        
    @contextmanager
    def get_cursor(self):
        """Context manager for thread-safe database operations"""
        db_con = None
        cursor = None
        is_read = False
        try:
            # Get connection and format SQL
            db_con = self.__get_db_connection()
            cursor = db_con.cursor()
            
            # Yield cursor for use in with block
            yield cursor
            
            # Commit if successful
            db_con.commit()
            
        except Exception as e:
            # Rollback on error
            if db_con:
                db_con.rollback()
            raise e
            
        finally:
            # Clean up resources
            if cursor:
                cursor.close()
        


    def __is_read(self, sql):
        fragment = sql[:6].upper()
        return fragment[:6] == 'SELECT' or fragment[:4] == 'SHOW'
    
    # purpose is to save the current db with an export, drop the db, recreate it, then connect to it
    def __prep_for_reinit(self):
        self.mig_path = os.path.join(kodi.translate_path("special://database"), 'mig_export_%s.csv' % (int(time.time())))
        logger.log('Backing up DB to %s' % (self.mig_path), log_utils.LOGDEBUG)
        self.export_from_db(self.mig_path)
        logger.log('Backup export of DB created at %s' % (self.mig_path), log_utils.LOGNOTICE)
        self.__drop_all()
        logger.log('DB Objects Dropped', log_utils.LOGDEBUG)

    def __create_sqlite_db(self):
        if not xbmcvfs.exists(os.path.dirname(self.db_path)):
            try: 
                xbmcvfs.mkdirs(os.path.dirname(self.db_path))
            except: 
                os.makedirs(os.path.dirname(self.db_path))

    def __drop_all(self):
        if self.db_type == DB_TYPES.MYSQL:
            sql = 'show tables'
        else:
            sql = 'select name from sqlite_master where type="table"'
        rows = self.__execute(sql)
        db_objects = [row[0] for row in rows]

        for db_object in db_objects:
            sql = 'DROP TABLE IF EXISTS %s' % (db_object)
            self.__execute(sql)

    def __get_db_connection(self):
        worker_id = threading.current_thread().ident
        # create a connection if we don't have one or it was created in a different worker
        if self.db is None or self.worker_id != worker_id:
            if self.db_type == DB_TYPES.MYSQL:
                self.db = self.db_lib.connect(database=self.dbname, user=self.username, password=self.password, host=self.address, buffered=True)
            else:
                self.db = self.db_lib.connect(self.db_path, isolation_level=None)
                self.db.text_factory = str
            self.worker_id = worker_id
        return self.db
        
    def close_all_connections(self):
        """Clean up all connections in the pool"""
        with self._pool_lock:
            for self.worker_id, self.db in self._connection_pool.items():
                try:
                    self.close()
                except:
                    pass
            self._connection_pool.clear()

    def close(self):
        worker_id = self.worker_id
        self.close_all_connections()
        if self.__get_db_connection().cursor():
            self.__get_db_connection().cursor().close()
        if worker_id is not None:
            worker_id = None
        if self.db:
            self.db.close()
            self.db = None

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        if exc_type:
            import traceback
            logger.log('database error', log_utils.LOGERROR)
            logger.log(f"{''.join(traceback.format_exception(exc_type, exc_val, exc_tb))}", log_utils.LOGERROR)
        if exc_type is OperationalError:
            logger.log('OperationalError', log_utils.LOGERROR)
            logger.log(f"{''.join(traceback.format_exception(exc_type, exc_val, exc_tb))}", log_utils.LOGERROR)
            return True

    # apply formatting changes to make sql work with a particular db driver
    def __format(self, sql):
        if self.db_type == DB_TYPES.MYSQL:
            sql = sql.replace('?', '%s')

        if self.db_type == DB_TYPES.SQLITE:
            if sql[:7] == 'REPLACE':
                sql = 'INSERT OR ' + sql

        return sql


    @abstractmethod
    def set(self, cache_id, data, checksum=None, expiration=None):
        """
        Stores new value in cache location
        :param cache_id: ID of cache to create
        :type cache_id: str
        :param data: value to store in cache
        :type data: Any
        :param checksum: Optional checksum to apply to item
        :type checksum: str,int
        :param expiration: Expiration of cache value in seconds since epoch
        :type expiration: int
        :return: None
        :rtype:
        """
def get_mapping(anilist_id='', mal_id='', kitsu_id='', tmdb_id='', trakt_id=''):
    # Acquire the lock to ensure thread safety
    control.mappingDB_lock.acquire()
    try:
        # Establish a connection to the database
        # Replace this with the appropriate connection method for SALTS
        conn = sqlite3.connect(control.mappingDB, timeout=60.0)
        conn.row_factory = _dict_factory
        conn.execute("PRAGMA FOREIGN_KEYS = 1")
        cursor = conn.cursor()
        
        # Determine the ID type and value
        mapping = {}
        id_type, id_val = '', ''
        if anilist_id:
            id_type, id_val = 'anilist_id', anilist_id
        elif mal_id:
            id_type, id_val = 'mal_id', mal_id
        elif kitsu_id:
            id_type, id_val = 'kitsu_id', kitsu_id
        elif tmdb_id:
            id_type, id_val = 'themoviedb_id', tmdb_id
        elif trakt_id:
            id_type, id_val = 'trakt_id', trakt_id
        
        # Query the database if an ID type and value are provided
        if id_type and id_val:
            db_query = 'SELECT * FROM anime WHERE {0} IN ({1})'.format(id_type, id_val)
            cursor.execute(db_query)
            mapping = cursor.fetchone()
        
        # Close the cursor
        cursor.close()
    finally:
        # Release the lock
        control.try_release_lock(control.mappingDB_lock)
        conn.close()
    
    return mapping

def _dict_factory(cursor, row):
    d = {}
    for idx, col in enumerate(cursor.description):
        d[col[0]] = row[idx]
    return d