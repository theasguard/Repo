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
import kodi
import threading
import json
import os
import requests
import log_utils
from contextlib import contextmanager
from threading import Semaphore
logger = log_utils.Logger.get_logger(__name__)

def __enum(**enums):
    return type('Enum', (), enums)

class DatabaseRecoveryError(Exception):
    pass

DB_TYPES = __enum(MYSQL='mysql', SQLITE='sqlite')
CSV_MARKERS = __enum(REL_URL='***REL_URL***', OTHER_LISTS='***OTHER_LISTS***', SAVED_SEARCHES='***SAVED_SEARCHES***', BOOKMARKS='***BOOKMARKS***')
MAX_TRIES = 5
MYSQL_DATA_SIZE = 512
MYSQL_URL_SIZE = 255
MYSQL_MAX_BLOB_SIZE = 16777215

INCREASED = False
UP_THRESHOLD = 0
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
class DBCache(object):
    worker_id = None
    locks = 0
    writes = 0
    _connection_pool = {}  # Add connection pool
    _pool_lock = threading.Lock() 
    TMDB_API_KEY = kodi.get_setting('tmdb_key')


    def __init__(self, db_path=None):
        global OperationalError
        global DatabaseError
        self.db_path = os.path.join(os.path.expanduser('~'), 'tmdb_cache.db') if db_path is None else db_path
        self.dbname = kodi.get_setting('db_name')
        self.username = kodi.get_setting('db_user')
        self.password = kodi.get_setting('db_pass')
        self.address = kodi.get_setting('db_address')
        self.db = None
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
        self.db_lib = db_lib


        self.__create_db()
        self.__execute('CREATE TABLE IF NOT EXISTS api_cache (tmdb_id INTEGER NOT NULL, object_type CHAR(1) NOT NULL, data VARCHAR(255), PRIMARY KEY(tmdb_id, object_type))')
        self.__execute('CREATE TABLE IF NOT EXISTS db_info (setting VARCHAR(255), value TEXT, PRIMARY KEY(setting))')
        
    def __create_db(self):
        db_dir = os.path.dirname(self.db_path)
        if not os.path.exists(db_dir):
            os.makedirs(db_dir)
        if not os.path.exists(self.db_path):
            open(self.db_path, 'w').close()
            
    def update_movie(self, tmdb_id, js_data):
        self.__update_object(tmdb_id, 'M', js_data)
    
    def get_movie(self, tmdb_id):
        return self.__get_object(tmdb_id, 'M')
        
    def get_tvshow(self, tmdb_id):
        return self.__get_object(tmdb_id, 'T')

    def get_season(self, tmdb_id, season):
        return self.__get_object(tmdb_id, 'S')
        
    def get_episode(self, tmdb_id, season, episode):
        return self.__get_object(tmdb_id, 'E')

    def update_season(self, tmdb_id, season, js_data):
        self.__update_object(tmdb_id, 'S', js_data)

    def update_episode(self, tmdb_id, js_data):
        self.__update_object(tmdb_id, 'E', js_data)

    def get_person(self, tmdb_id):
        return self.__get_object(tmdb_id, 'P')
        
    def __get_object(self, tmdb_id, object_type):
        sql = 'SELECT data from api_cache where tmdb_id = ? and object_type=?'
        rows = self.__execute(sql, (tmdb_id, object_type))
        if rows:
            return json.loads(rows[0][0])
        else:
            return {}
        
    def update_tvshow(self, tmdb_id, js_data):
        self.__update_object(tmdb_id, 'T', js_data)
    
    def update_person(self, tmdb_id, js_data):
        self.__update_object(tmdb_id, 'P', js_data)
    
    def __update_object(self, tmdb_id, object_type, js_data):
        self.__execute('REPLACE INTO api_cache (tmdb_id, object_type, data) values (?, ?, ?)', (tmdb_id, object_type, json.dumps(js_data)))

    def get_setting(self, setting):
        sql = 'SELECT value FROM db_info WHERE setting = ?'
        rows = self.__execute(sql, (setting,))
        if rows:
            return rows[0][0]

    def set_setting(self, setting, value):
        sql = 'REPLACE INTO db_info (setting, value) VALUES (?, ?)'
        self.__execute(sql, (setting, value))

    def execute(self, sql, params=None):
        return self.__execute(sql, params)
    

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
            for worker_id, self.db in self._connection_pool.items():
                try:
                    self.db.close()
                except:
                    pass
            self._connection_pool.clear()

    def close(self):
        self.close_all_connections()
        if self.db:
            self.db.close()
            self.db = None

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_all_connections()
        if exc_type:
            import traceback
            logger.log('database error', log_utils.LOGERROR)
            logger.log(f"{''.join(traceback.format_exception(exc_type, exc_val, exc_tb))}", log_utils.LOGERROR)
        if exc_type is OperationalError:
            return True

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
                    if not is_read: DBCache.writes += 1
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
                            DBCache.locks += 1
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
        if self.db_type == DB_TYPES.SQLITE and DBCache.writes >= CHECK_THRESHOLD:
            lock_percent = DBCache.locks * 100 / DBCache.writes
            logger.log('Max Writers Update: %s/%s (%s%%) - %s' % (DBCache.locks, DBCache.writes, lock_percent, MAX_WRITERS))
            DBCache.writes = 0
            DBCache.locks = 0

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

            kodi.set_setting('sema_value1', str(MAX_WRITERS))

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
        


    # apply formatting changes to make sql work with a particular db driver
    def __format(self, sql):
        if self.db_type == DB_TYPES.MYSQL:
            sql = sql.replace('?', '%s')

        if self.db_type == DB_TYPES.SQLITE:
            if sql[:7] == 'REPLACE':
                sql = 'INSERT OR ' + sql

        return sql

    def __is_read(self, sql):
        fragment = sql[:6].upper()
        return fragment[:6] == 'SELECT' or fragment[:4] == 'SHOW'

    def fetch_and_store_movie(self, tmdb_id):
        url = f'https://api.themoviedb.org/3/movie/{tmdb_id}?api_key={self.TMDB_API_KEY}'
        response = requests.get(url)
        if response.status_code == 200:
            self.update_movie(tmdb_id, response.json())
        else:
            raise Exception(f"Failed to fetch movie data: {response.status_code}")

    def fetch_and_store_tvshow(self, tmdb_id):
        url = f'https://api.themoviedb.org/3/tv/{tmdb_id}?api_key={self.TMDB_API_KEY}'
        response = requests.get(url)
        if response.status_code == 200:
            self.update_tvshow(tmdb_id, response.json())
        else:
            raise Exception(f"Failed to fetch TV show data: {response.status_code}")

    def fetch_and_store_person(self, tmdb_id):
        url = f'https://api.themoviedb.org/3/person/{tmdb_id}?api_key={self.TMDB_API_KEY}'
        response = requests.get(url)
        if response.status_code == 200:
            self.update_person(tmdb_id, response.json())
        else:
            raise Exception(f"Failed to fetch person data: {response.status_code}")

    def fetch_and_store_episode(self, tmdb_id, season_number):
        url = f'https://api.themoviedb.org/3/tv/{tmdb_id}/season/{season_number}?api_key={self.TMDB_API_KEY}'
        response = requests.get(url)
        if response.status_code == 200:
            self.update_episode(tmdb_id, response.json())
        else:
            raise Exception(f"Failed to fetch person data: {response.status_code}")

    def fetch_and_store_episode(self, tmdb_id, season_number, episode_number):
        url = f'https://api.themoviedb.org/3/tv/{tmdb_id}/season/{season_number}/episode/{episode_number}?api_key={self.TMDB_API_KEY}'
        response = requests.get(url)
        if response.status_code == 200:
            self.update_episode(tmdb_id, response.json())
        else:
            raise Exception(f"Failed to fetch person data: {response.status_code}")