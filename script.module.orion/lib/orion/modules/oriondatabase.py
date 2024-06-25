# -*- coding: utf-8 -*-

"""
	Orion
    https://orionoid.com

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

##############################################################################
# ORIONDATABASE
##############################################################################
# Class for handling SQLite databases.
##############################################################################

from threading import Lock
from orion.modules.oriontools import *
try: from sqlite3 import dbapi2 as database
except: from pysqlite2 import dbapi2 as database

class OrionDatabase(object):

	Initialized = False
	Instances = {}

	Lock = Lock()
	Locks = {}

	##############################################################################
	# CONSTANTS
	##############################################################################

	Timeout = 20
	Extension = '.db'

	##############################################################################
	# CONSTRUCTOR
	##############################################################################

	def __init__(self, name = None, default = None, path = None, connect = True):
		try:
			if name is None: name = OrionTools.hash(path)

			if not name in OrionDatabase.Locks: OrionDatabase.Locks[name] = Lock()
			self.mLock = OrionDatabase.Locks[name]

			if path is None:
				if not name.endswith(OrionDatabase.Extension): name += OrionDatabase.Extension
				self.mPath = OrionTools.pathJoin(OrionTools.pathResolve(OrionTools.addonProfile()), name)
				if default and not OrionTools.fileExists(self.mPath):
					OrionTools.fileCopy(OrionTools.pathJoin(default, name), self.mPath)
			else:
				if not path.endswith(OrionDatabase.Extension): path += OrionDatabase.Extension
				self.mPath = path

			if connect: self._connect()
		except:
			OrionTools.error()

	def __del__(self):
		self._close()

	@classmethod
	def instance(self, name, default = None, path = None, create = None):
		self.instancesInitialize()

		id = name + '_' + (default if default else '') + '_' + (path if path else '')
		id = OrionTools.hashInternal(id)

		if not id in OrionDatabase.Instances:
			# Use a lock here, otherwise there can be sporadic errors:
			#	(oriondatabase.py, 176, _execute): ProgrammingError, line 176, in _execute, if parameters == None: self.mDatabase.execute(query), sqlite3.ProgrammingError: Recursive use of cursors not allowed.
			# This error was observed by a user with CocoScrapers when both torrent and hoster scraping is enabled.
			# Maybe this happens if both torrent and hoster scrapers finish at exactly the same time.
			# Then this function could be called at the same time from 2 different threads, nad both create a NEW self.mLock in the constructor.
			# This means the 2 threads will use different locks in _execute(), making the locks essentially useless, and causing the error above when the cursor is used at the same time from 2 different threads.
			# UPDATE: still happens, even with the lock here. Made other updates to _connect().
			OrionDatabase.Lock.acquire()

			if not id in OrionDatabase.Instances:
				OrionDatabase.Instances[id] = OrionDatabase(name = name, default = default, path = path)
				if not create is None: OrionDatabase.Instances[id].create(create)

			OrionDatabase.Lock.release()

		return OrionDatabase.Instances[id]

	@classmethod
	def instancesInitialize(self):
		# Python only deletes instances if there are no more references to them.
		# The database instances have to be manually deleted to ensure that the connections are closed.
		# Do not close connections from the Orion() destructor, since some connections might still be running in a thread when the destructor is executed.
		if not OrionDatabase.Initialized:
			import atexit
			OrionDatabase.Initialized = True
			atexit.register(self.instancesClear)

	@classmethod
	def instancesClear(self):
		try:
			OrionDatabase.Lock.acquire()
			for instance in OrionTools.iteratorValues(OrionDatabase.Instances):
				instance._close()
			OrionDatabase.Instances = {}
			OrionDatabase.Locks = {}
			OrionDatabase.Custom = {}
		finally:
			OrionDatabase.Lock.release()

	##############################################################################
	# INTERNAL
	##############################################################################

	def _lock(self):
		self.mLock.acquire()

	def _unlock(self):
		try: self.mLock.release()
		except: pass

	def _connect(self):
		try:
			# When the addon is launched for the first time after installation, an error occurs, since the addon userdata directory does not exist yet and the database file is written to that directory.
			# If the directory does not exist yet, create it.
			OrionTools.directoryCreate(OrionTools.directoryName(self.mPath))

			# SQLite does not allow database objects to be used from multiple threads. Explicitly allow multi-threading.
			self._lock()
			try: self.mConnection = database.connect(self.mPath, check_same_thread = False, timeout = OrionDatabase.Timeout)
			except: self.mConnection = database.connect(self.mPath, timeout = OrionDatabase.Timeout)
			self.mDatabase = self.mConnection.cursor()
			self._unlock()

			return True
		except:
			self._close()
			return False
		finally:
			self._unlock()

	def _close(self):
		try:
			self._lock()
			try: self.mDatabase.close()
			except: pass
			try: self.mConnection.close()
			except: pass
			self.mConnection = None
			self.mDatabase = None
		except:
			pass
		finally:
			self._unlock()

	def _list(self, items):
		if not type(items) in [list, tuple]: items = [items]
		return items

	def _null(self):
		return 'NULL'

	def _commit(self, lock = True, unlock = True):
		try:
			if lock: self._lock()
			self.mConnection.commit()
			return True
		except:
			return False
		finally:
			if unlock: self._unlock()

	def _execute(self, query, parameters = None, commit = True, compress = False, lock = True, unlock = True):
		try:
			if lock: self._lock()

			if parameters is None: self.mDatabase.execute(query)
			else: self.mDatabase.execute(query, parameters)

			if commit: self._commit(lock = False, unlock = False)
			if compress: self.compress(commit = True, lock = False, unlock = False)

			return True
		except:
			OrionTools.error()
			return False
		finally:
			if unlock: self._unlock()

	# query must contain %s for table name.
	# tables can be None, table name, or list of tables names.
	# If tables is None, will retrieve all tables in the database.
	def _executeAll(self, query, tables = None, parameters = None, commit = True, lock = True, unlock = True):
		try:
			if lock: self._lock()
			result = True
			if tables is None: tables = self.tables()
			tables = self._list(tables, lock = False, unlock = False)

			for table in tables:
				result = result and self._execute(query % table, parameters = parameters, commit = False, compress = False, lock = False, unlock = False)

			if commit: self._commit(lock = False, unlock = False)
			if compress: self.compress(commit = True, lock = False, unlock = False)

			return result
		finally:
			if unlock: self._unlock()

	##############################################################################
	# COMPRESS
	##############################################################################

	def compress(self, commit = True, lock = True, unlock = True):
		return self._execute('VACUUM', commit = commit, lock = lock, unlock = unlock)

	##############################################################################
	# GENERAL
	##############################################################################

	def tables(self, lock = True, unlock = True):
		return self.selectValues('SELECT name FROM sqlite_master WHERE type IS "table"', lock = lock, unlock = unlock)

	def create(self, query, parameters = None, commit = True, lock = True, unlock = True):
		result = self._execute(query, parameters = parameters, commit = commit, lock = lock, unlock = unlock)
		return result

	def createAll(self, query, tables, parameters = None, commit = True, lock = True, unlock = True):
		result = self._executeAll(query, tables = tables, parameters = parameters, commit = commit, lock = lock, unlock = unlock)
		return result

	# Retrieves a list of rows.
	# Each row is a tuple with all the return values.
	# Eg: [(row1value1, row1value2), (row2value1, row2value2)]
	def select(self, query, parameters = None, lock = True, unlock = True):
		try:
			self._execute(query, parameters = parameters, commit = False, lock = lock, unlock = False)
			return self.mDatabase.fetchall()
		finally:
			if unlock: self._unlock()

	# Retrieves a single row.
	# Each row is a tuple with all the return values.
	# Eg: (row1value1, row1value2)
	def selectSingle(self, query, parameters = None, lock = True, unlock = True):
		try:
			self._execute(query, parameters = parameters, commit = False, lock = lock, unlock = False)
			return self.mDatabase.fetchone()
		finally:
			if unlock: self._unlock()

	# Retrieves a list of single values from rows.
	# Eg: [row1value1, row1value2]
	def selectValues(self, query, parameters = None, lock = True, unlock = True):
		try:
			result = self.select(query, parameters = parameters, lock = lock, unlock = unlock)
			return [i[0] for i in result]
		except: return []

	# Retrieves a signle value from a single row.
	# Eg: row1value1
	def selectValue(self, query, parameters = None, lock = True, unlock = True):
		try: return self.selectSingle(query, parameters = parameters, lock = lock, unlock = unlock)[0]
		except: return None

	# Checks if the value exists, such as an ID.
	def exists(self, query, parameters = None, lock = True, unlock = True):
		return len(self.select(query, parameters = parameters, lock = lock, unlock = unlock)) > 0

	def insert(self, query, parameters = None, commit = True, lock = True, unlock = True):
		return self._execute(query, parameters = parameters, commit = commit, lock = lock, unlock = unlock)
		return result

	def update(self, query, parameters = None, commit = True, lock = True, unlock = True):
		return self._execute(query, parameters = parameters, commit = commit, lock = lock, unlock = unlock)

	# Deletes specific row in table.
	# If table is none, assumes it was already set in the query
	def delete(self, query, parameters = None, table = None, commit = True, lock = True, unlock = True):
		if not table is None: query = query % table
		return self._execute(query, parameters = parameters, commit = commit, lock = lock, unlock = unlock)

	# Deletes all rows in table.
	# tables can be None, table name, or list of tables names.
	# If tables is None, deletes all rows in all tables.
	def deleteAll(self, tables = None, parameters = None, commit = True, lock = True, unlock = True):
		return self._executeAll('DELETE FROM %s;', tables, parameters = parameters, commit = commit, lock = lock, unlock = unlock)

	# Drops single table.
	def drop(self, table, parameters = None, commit = True, lock = True, unlock = True):
		return self._execute('DROP TABLE IF EXISTS %s;' % table, parameters = parameters, commit = commit, lock = lock, unlock = unlock)

	# Drops all tables.
	def dropAll(self, parameters = None, commit = True, lock = True, unlock = True):
		return self._executeAll('DROP TABLE IF EXISTS %s;', parameters = parameters, commit = commit, lock = lock, unlock = unlock)
