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
# ORIONSETTINGS
##############################################################################
# Class for handling the Kodi addon settings.
##############################################################################

import re
import threading
import xbmcaddon
from orion.modules.oriontools import *
from orion.modules.orioninterface import *
from orion.modules.orionstream import *
from orion.modules.oriondatabase import *

OrionSettingsLock = threading.Lock()
OrionSettingsCache = None
OrionSettingsSilent = False
OrionSettingsBackupLocal = False
OrionSettingsBackupOnline = False

class OrionSettings:

	##############################################################################
	# CONSTANTS
	##############################################################################

	DatabaseSettings = 'settings'
	DatabaseTemp = 'temp'

	ExtensionManual = 'zip'
	ExtensionAutomatic = 'bck'

	ParameterDefault = 'default'
	ParameterValue = 'value'
	ParameterVisible = 'visible'

	CategoryGeneral = 0
	CategoryAccount = 1
	CategoryFilters = 2

	NotificationsDisabled = 0
	NotificationsEssential = 1
	NotificationsAll = 2

	ScrapingExclusive = 0
	ScrapingSequential = 1
	ScrapingParallel = 2

	ExternalStart = '<!-- ORION FILTERS - %s START -->'
	ExternalEnd = '<!-- ORION FILTERS - %s END -->'

	Addon = None

	##############################################################################
	# INTERNAL
	##############################################################################

	@classmethod
	def _addon(self):
		# NB: Do not use OrionTools.addon() to setSettings().
		# For some reason, Kodi adds a bunch of <setting id="labelXXX" default="true" /> to the profile settings.xml.
		# This can add 1000s of these default settings.
		# On low-end devices, this can make Kodi unusable (especially during boot), since Kodi is constantly busy writing to disk to add these values.
		# Now there are still a few of these settings left, but at least not 1000s.
		if OrionSettings.Addon is None: OrionSettings.Addon = xbmcaddon.Addon(OrionTools.Id)
		return OrionSettings.Addon

	@classmethod
	def _filtersAttribute(self, attribute, type = None):
		if not type is None and not type == 'universal':
			attribute = attribute.replace('filters.', 'filters.' + type + '.')
		return attribute

	##############################################################################
	# LAUNCH
	##############################################################################

	@classmethod
	def launch(self, category = None, section = None, addon = None, app = None, wait = False):
		OrionTools.execute('Addon.OpenSettings(%s)' % (OrionTools.addonId() if addon is None else addon))

		if not app is None:
			category = self.externalCategory(app = app, enabled = category == OrionSettings.CategoryFilters)
		if OrionTools.kodiVersionNew():
			if not category is None: OrionTools.execute('SetFocus(%i)' % (int(category) - 100))
		else:
			if not category is None: OrionTools.execute('SetFocus(%i)' % (int(category) + 100))
			if not section is None: OrionTools.execute('SetFocus(%i)' % (int(section) + 200))

		if wait: OrionInterface.dialogWait()

	@classmethod
	def launchFilters(self, app = None, wait = False):
		self.launch(category = OrionSettings.CategoryFilters, app = app, wait = wait)

	##############################################################################
	# PATH
	##############################################################################

	@classmethod
	def pathAddon(self):
		return OrionTools.pathJoin(OrionTools.addonPath(), 'resources', 'settings.xml')

	@classmethod
	def pathProfile(self):
		return OrionTools.pathJoin(OrionTools.addonProfile(), 'settings.xml')

	@classmethod
	def pathStrings(self):
		return OrionTools.pathJoin(OrionTools.addonPath(), 'resources', 'language', 'English', 'strings.po')

	##############################################################################
	# SILENT
	##############################################################################

	@classmethod
	def silent(self):
		global OrionSettingsSilent
		return OrionSettingsSilent or self.silentDebug()

	@classmethod
	def silentSet(self, silent = True):
		global OrionSettingsSilent
		OrionSettingsSilent = silent

	@classmethod
	def silentDebug(self):
		from orion.modules.orionuser import OrionUser
		return not OrionUser.instance().enabled()

	@classmethod
	def silentAllow(self, type = None):
		from orion.modules.orionapi import OrionApi
		if type in OrionApi.TypesEssential: return True
		if self.silent(): return False
		if type in OrionApi.TypesBlock: return False
		notifications = self.getGeneralNotificationsApi()
		if notifications == OrionSettings.NotificationsDisabled: return False
		elif notifications == OrionSettings.NotificationsAll: return True
		return type == None or not type in OrionApi.TypesNonessential

	##############################################################################
	# DATA
	##############################################################################

	@classmethod
	def data(self):
		try:
			path = OrionTools.pathJoin(self.pathAddon())
			return OrionTools.fileRead(path)
		except:
			OrionTools.error()
			return None

	@classmethod
	def _database(self, path = None, default = False):
		if default: return OrionDatabase.instance(OrionSettings.DatabaseSettings, path = OrionTools.pathJoin(OrionTools.addonPath(), 'resources', OrionSettings.DatabaseSettings))
		else: return OrionDatabase.instance(OrionSettings.DatabaseSettings, default = OrionTools.pathJoin(OrionTools.addonPath(), 'resources'), path = path)

	@classmethod
	def _commit(self):
		self._database()._commit()
		self._backupAutomatic(force = True)

	##############################################################################
	# LOCK
	##############################################################################

	@classmethod
	def _lock(self):
		global OrionSettingsLock
		OrionSettingsLock.acquire()

	@classmethod
	def _unlock(self):
		global OrionSettingsLock
		try: OrionSettingsLock.release()
		except: pass

	#############################################################################
	# CACHE
	##############################################################################

	@classmethod
	def cache(self):
		global OrionSettingsCache
		if OrionSettingsCache == None:
			OrionSettingsCache = {
				'enabled' : OrionTools.toBoolean(self._addon().getSetting('general.settings.cache')),
				'static' : {
					'data' : None,
					'values' : {},
				},
				'dynamic' : {
					'data' : None,
					'values' : {},
				},
			}
		return OrionSettingsCache

	@classmethod
	def cacheClear(self):
		global OrionSettingsCache
		OrionSettingsCache = None

	@classmethod
	def cacheEnabled(self):
		return self.cache()['enabled']

	@classmethod
	def cacheGet(self, id, raw, database = False, obfuscate = False):
		cache = self.cache()
		if raw:
			if cache['static']['data'] is None: cache['static']['data'] = OrionTools.fileRead(self.pathAddon())
			data = cache['static']['data']
			values = cache['static']['values']
			parameter = OrionSettings.ParameterDefault
		else:
			if cache['dynamic']['data'] is None: cache['dynamic']['data'] = OrionTools.fileRead(self.pathProfile())
			data = cache['dynamic']['data']
			values = cache['dynamic']['values']
			parameter = OrionSettings.ParameterValue

		if id in values:
			return values[id]
		elif database:
			result = self._getDatabase(id = id)
			if obfuscate: result = OrionTools.obfuscate(result)
			values[id] = result
			return result
		else:
			result = self.getRaw(id = id, parameter = parameter, data = data)
			if result == None: result = self._addon().getSetting(id)
			if obfuscate: result = OrionTools.obfuscate(result)
			values[id] = result
			return result

	@classmethod
	def cacheSet(self, id, value):
		self.cache()['dynamic']['values'][id] = value

	##############################################################################
	# SET
	##############################################################################

	@classmethod
	def set(self, id, value, commit = True, cached = False, backup = True):
		if value is True or value is False:
			value = OrionTools.toBoolean(value, string = True)
		elif OrionTools.isStructure(value) or value is None:
			database = self._database()
			database.insert('INSERT OR IGNORE INTO %s (id) VALUES(?);' % OrionSettings.DatabaseSettings, parameters = (id,), commit = commit)
			database.update('UPDATE %s SET data = ? WHERE id = ?;' % OrionSettings.DatabaseSettings, parameters = (OrionTools.jsonTo(value), id), commit = commit)
			value = ''
		else:
			value = str(value)
		self._lock()
		self._addon().setSetting(id = id, value = value)
		if cached or self.cacheEnabled(): self.cacheSet(id = id, value = value)
		self._unlock()
		if commit and backup: self._backupAutomatic(force = True)

	##############################################################################
	# GET
	##############################################################################

	@classmethod
	def _getDatabase(self, id, default = False):
		try: return OrionTools.jsonFrom(self._database(default = default).selectValue('SELECT data FROM %s WHERE id = "%s";' % (OrionSettings.DatabaseSettings, id)))
		except: return None

	@classmethod
	def get(self, id, raw = False, obfuscate = False, cached = True, database = False):
		if not raw and cached and self.cacheEnabled():
			return self.cacheGet(id = id, raw = raw, database = database, obfuscate = obfuscate)
		elif raw:
			return self.getRaw(id = id, obfuscate = obfuscate)
		else:
			self._backupAutomatic()
			data = self._addon().getSetting(id)
			if obfuscate: data = OrionTools.obfuscate(data)
			return data

	@classmethod
	def getRaw(self, id, parameter = ParameterDefault, data = None, obfuscate = False):
		try:
			id = OrionTools.unicodeString(id)
			if parameter == OrionSettings.ParameterValue and OrionTools.kodiVersionNew(): expression = 'id\s*=\s*"' + id + '"[^\/]*?>(.*?)<'
			else: expression = 'id\s*=\s*"' + id + '".*?<' + parameter + '[^\/]*?>(.*?)<'
			if data == None: data = self.data()
			match = re.search(expression, data, re.IGNORECASE | re.DOTALL)
			if match:
				data = match.group(1)
				if obfuscate: data = OrionTools.obfuscate(data)
				return data
		except:
			OrionTools.error()
			return None

	@classmethod
	def getString(self, id, raw = False, obfuscate = False, cached = True):
		return self.get(id = id, raw = raw, obfuscate = obfuscate, cached = cached)

	@classmethod
	def getBoolean(self, id, raw = False, obfuscate = False, cached = True):
		return OrionTools.toBoolean(self.get(id = id, raw = raw, obfuscate = obfuscate, cached = cached))

	@classmethod
	def getBool(self, id, raw = False, obfuscate = False, cached = True):
		return self.getBoolean(id = id, raw = raw, obfuscate = obfuscate, cached = cached)

	@classmethod
	def getNumber(self, id, raw = False, obfuscate = False, cached = True):
		return self.getDecimal(id = id, raw = raw, obfuscate = obfuscate, cached = cached)

	@classmethod
	def getDecimal(self, id, raw = False, obfuscate = False, cached = True):
		value = self.get(id = id, raw = raw, obfuscate = obfuscate, cached = cached)
		try: return float(value)
		except: return 0

	@classmethod
	def getFloat(self, id, raw = False, obfuscate = False, cached = True):
		return self.getDecimal(id = id, raw = raw, obfuscate = obfuscate, cached = cached)

	@classmethod
	def getInteger(self, id, raw = False, obfuscate = False, cached = True):
		value = self.get(id = id, raw = raw, obfuscate = obfuscate, cached = cached)
		try: return int(value)
		except: return 0

	@classmethod
	def getInt(self, id, raw = False, obfuscate = False, cached = True):
		return self.getInteger(id = id, raw = raw, obfuscate = obfuscate, cached = cached)

	@classmethod
	def getList(self, id, default = False):
		result = self._getDatabase(id, default = default)
		return [] if result == None or result == '' else result

	@classmethod
	def getObject(self, id, default = False):
		result = self._getDatabase(id, default = default)
		return None if result == None or result == '' else result

	##############################################################################
	# GET CUSTOM
	##############################################################################

	@classmethod
	def getIntegration(self, app):
		try: return self.getString('integration.' + app)
		except: return ''

	@classmethod
	def getGeneralNotificationsApi(self):
		return self.getInteger('general.notifications.api')

	@classmethod
	def getGeneralNotificationsNews(self):
		return self.getBoolean('general.notifications.news')

	@classmethod
	def getGeneralNotificationsUpdates(self):
		return self.getBoolean('general.notifications.updates')

	@classmethod
	def getGeneralNotificationsTickets(self):
		return self.getBoolean('general.notifications.tickets')

	@classmethod
	def getFiltersGlobal(self, app = None, cached = False):
		if app is None or app == 'universal': return True
		elif not OrionTools.isString(app): app = app.id()
		return not self.getBoolean('filters.' + app + '.enabled', cached = cached) # Do not use the cached value, since this setting might have been toggle during the same execution.

	@classmethod
	def getFiltersBoolean(self, attribute, type = None):
		return self.getBoolean(self._filtersAttribute(attribute, type))

	@classmethod
	def getFiltersInteger(self, attribute, type = None):
		return self.getInteger(self._filtersAttribute(attribute, type))

	@classmethod
	def getFiltersString(self, attribute, type = None):
		return self.getString(self._filtersAttribute(attribute, type))

	@classmethod
	def getFiltersObject(self, attribute, type = None, include = False, exclude = False, default = False):
		values = self.getObject(self._filtersAttribute(attribute, type), default = default)
		try:
			if include: values = [key for key, value in OrionTools.iterator(values) if value['enabled']]
		except: pass
		try:
			if exclude: values = [key for key, value in OrionTools.iterator(values) if not value['enabled']]
		except: pass
		return values if values else [] if (include or exclude) else {}

	@classmethod
	def getFiltersCustomApp(self, app):
		try: return self.getBoolean('filters.' + app + '.app', raw = True)
		except: return False

	@classmethod
	def getFiltersCustomEnabled(self, type = None):
		return self.getFiltersBoolean('filters.custom.enabled', type = type)

	@classmethod
	def getFiltersLookup(self, type = None, include = False, exclude = False, default = False):
		result = self.getFiltersObject('filters.lookup.service', type = type, include = include, exclude = exclude)
		if not result and default: result = self.getFiltersObject('filters.lookup.service', type = type, include = include, exclude = exclude, default = default)
		return result

	@classmethod
	def getFiltersAccess(self, stream, type = None, include = False, exclude = False, default = False):
		id = 'filters.access.' + stream
		result = self.getFiltersObject(id, type = type, include = include, exclude = exclude)
		if not result and default: result = self.getFiltersObject(id, type = type, include = include, exclude = exclude, default = default)
		return result

	@classmethod
	def getFiltersAccessTorrent(self, type = None, include = False, exclude = False, default = False):
		return self.getFiltersAccess(stream = OrionStream.TypeTorrent, type = type, include = include, exclude = exclude, default = default)

	@classmethod
	def getFiltersAccessUsenet(self, type = None, include = False, exclude = False, default = False):
		return self.getFiltersAccess(stream = OrionStream.TypeUsenet, type = type, include = include, exclude = exclude, default = default)

	@classmethod
	def getFiltersAccessHoster(self, type = None, include = False, exclude = False, default = False):
		return self.getFiltersAccess(stream = OrionStream.TypeHoster, type = type, include = include, exclude = exclude, default = default)

	@classmethod
	def getFiltersStreamOrigin(self, type = None, include = False, exclude = False):
		return self.getFiltersObject('filters.stream.origin', type = type, include = include, exclude = exclude)

	@classmethod
	def getFiltersStreamSource(self, type = None, include = False, exclude = False):
		return self.getFiltersObject('filters.stream.source', type = type, include = include, exclude = exclude)

	@classmethod
	def getFiltersStreamHoster(self, type = None, include = False, exclude = False):
		return self.getFiltersObject('filters.stream.hoster', type = type, include = include, exclude = exclude)

	@classmethod
	def getFiltersFileLanguages(self, type = None, include = False, exclude = False):
		return self.getFiltersObject('filters.file.languages', type = type, include = include, exclude = exclude)

	@classmethod
	def getFiltersMetaRelease(self, type = None, include = False, exclude = False):
		return self.getFiltersObject('filters.meta.release', type = type, include = include, exclude = exclude)

	@classmethod
	def getFiltersMetaUploader(self, type = None, include = False, exclude = False):
		return self.getFiltersObject('filters.meta.uploader', type = type, include = include, exclude = exclude)

	@classmethod
	def getFiltersMetaEdition(self, type = None, include = False, exclude = False):
		return self.getFiltersObject('filters.meta.edition', type = type, include = include, exclude = exclude)

	@classmethod
	def getFiltersVideoCodec(self, type = None, include = False, exclude = False):
		return self.getFiltersObject('filters.video.codec', type = type, include = include, exclude = exclude)

	@classmethod
	def getFiltersAudioType(self, type = None, include = False, exclude = False):
		return self.getFiltersObject('filters.audio.type', type = type, include = include, exclude = exclude)

	@classmethod
	def getFiltersAudioSystem(self, type = None, include = False, exclude = False):
		return self.getFiltersObject('filters.audio.system', type = type, include = include, exclude = exclude)

	@classmethod
	def getFiltersAudioCodec(self, type = None, include = False, exclude = False):
		return self.getFiltersObject('filters.audio.codec', type = type, include = include, exclude = exclude)

	@classmethod
	def getFiltersAudioLanguages(self, type = None, include = False, exclude = False):
		return self.getFiltersObject('filters.audio.languages', type = type, include = include, exclude = exclude)

	@classmethod
	def getFiltersSubtitleType(self, type = None, include = False, exclude = False):
		return self.getFiltersObject('filters.subtitle.type', type = type, include = include, exclude = exclude)

	@classmethod
	def getFiltersSubtitleLanguages(self, type = None, include = False, exclude = False):
		return self.getFiltersObject('filters.subtitle.languages', type = type, include = include, exclude = exclude)

	##############################################################################
	# SET CUSTOM
	##############################################################################

	@classmethod
	def setIntegration(self, app, value, commit = True):
		return self.set('integration.' + app, value, commit = commit)

	@classmethod
	def setFilters(self, values, wait = False):
		# Do not use threads directly to update settings. Updating the settings in a threads can cause the settings file to become corrupt.
		# This was possibly fixed through the locking mechanism. Launching the thread directly (setFiltersUpdate) should hopefully work now.
		if wait:
			self.setFiltersUpdate(values)
		else:
			# This is still and issues in Kodi 19 with Seren.
			# Sometimes Seren freezes up when scraping Orion and after a while being frozen, Kodi crashes.
			# This does not happen all the time, but the problem is sporadic (happens every 5 - 10 times).
			# When tracking down the point at which Seren/Kodi freezes, it is in Orion's code, in OrionSettings.set(...) -> addon.setSetting(...).
			# This is probably due to a poor locking implementation (or none at all) within Kodi's core code in setSetting(...).
			# The locking in OrionSettings.set(...) will not always work, especially with Seren, since Seren starts two providers (hoster + torrent) in multiple threads.
			# Hence, those two providers will call Orion separately and therefore not share the same lock.
			# The only solution for now seems to update the settings in separate processes instead of threads.

			thread = threading.Thread(target = self._setFiltersThread, args = (values,))
			#thread = threading.Thread(target = self.setFiltersUpdate, args = (values,))

			thread.start()

	@classmethod
	def _setFiltersThread(self, values):
		# Do not pass the values as plugin parameters, since this immediately fills up the log, since Kodi prints the entire command.

		database = self._database()
		database.create('CREATE TABLE IF NOT EXISTS %s (data TEXT);' % OrionSettings.DatabaseTemp)
		database.insert('INSERT INTO %s (data) VALUES(?);' % OrionSettings.DatabaseTemp, parameters = (OrionTools.jsonTo([value.data() for value in values]),))
		OrionTools.executePlugin(execute = True, action = 'settingsFiltersUpdate')

		# There are thread limbo exceptions thrown here sometimes.
		# Wait for executePlugin() to finish.
		# Since this is a thread, simply sleeping and waiting isn't a problem.
		OrionTools.sleep(3)

	@classmethod
	def setFiltersUpdate(self, values = None):
		from orion.modules.orionapp import OrionApp
		try:
			if values is None:
				# Only select the first row, since the _setFiltersThread function can be called multiple times from different threads, therefore inserting multiple rows.
				database = self._database()
				id = database.selectValue('SELECT rowid FROM %s LIMIT 1;' % OrionSettings.DatabaseTemp)
				if id:
					values = database.selectValue('SELECT data FROM %s WHERE rowid = %s;' % (OrionSettings.DatabaseTemp, id))
					database.delete('DELETE FROM %s WHERE rowid = %s;' % (OrionSettings.DatabaseTemp, id))
			if OrionTools.isString(values):
				values = OrionTools.jsonFrom(values)
				values = [OrionStream(value) for value in values]
		except: pass
		if values:
			apps = [None] + [i.id() for i in OrionApp.instances(orion = False)]
			for app in apps:
				self.setFiltersStreamOrigin(values, type = app, commit = False)
				self.setFiltersStreamSource(values, type = app, commit = False)
				self.setFiltersStreamHoster(values, type = app, commit = False)
				self.setFiltersMetaRelease(values, type = app, commit = False)
				self.setFiltersMetaUploader(values, type = app, commit = False)
				self.setFiltersMetaEdition(values, type = app, commit = False)
				self.setFiltersVideoCodec(values, type = app, commit = False)
				self.setFiltersAudioType(values, type = app, commit = False)
				self.setFiltersAudioSystem(values, type = app, commit = False)
				self.setFiltersAudioCodec(values, type = app, commit = False)
			self._commit()

	@classmethod
	def _setFilters(self, values, setting, functionStreams, functionGet, type = None, commit = True):
		if not values: return
		items = {}
		try:
			from orion.modules.orionstream import OrionStream
			for value in values:
				attribute = getattr(value, functionStreams)()
				if not attribute == None:
					items[attribute.lower()] = {'name' : attribute.upper(), 'enabled' : True}
			settings = getattr(self, functionGet)(type = type)
			if settings:
				for key, value in OrionTools.iterator(items):
					if not key in settings:
						settings[key] = value
				items = settings
		except:
			items = values
		if items: count = len([1 for key, value in OrionTools.iterator(items) if value['enabled']])
		else: count = 0

		# Only do this if the data has not changed, since reading is fast (reads from cache), but writing is slow (write to file).
		key = self._filtersAttribute(setting, type)
		if not self.getObject(key) == items:
			self.set(key, items, commit = commit)
			self.set(self._filtersAttribute(setting + '.label', type), str(count) + ' ' + OrionTools.translate(32096), commit = commit)

	@classmethod
	def _setFiltersLanguages(self, values, setting, functionStreams, functionGet, type = None, commit = True):
		if not values: return
		if values: count = len([1 for key, value in OrionTools.iterator(values) if value['enabled']])
		else: count = 0

		# Only do this if the data has not changed, since reading is fast (reads from cache), but writing is slow (write to file).
		key = self._filtersAttribute(setting, type)
		if not self.getObject(key) == values:
			self.set(key, values, commit = commit)
			self.set(self._filtersAttribute(setting + '.label', type), str(count) + ' ' + OrionTools.translate(32096), commit = commit)

	@classmethod
	def setFiltersLimitCount(self, value, type = None, commit = True):
		self.set(self._filtersAttribute('filters.limit.count', type), value, commit = commit)

	@classmethod
	def setFiltersLimitRetry(self, value, type = None, commit = True):
		self.set(self._filtersAttribute('filters.limit.retry', type), value, commit = commit)

	@classmethod
	def setFiltersLookup(self, values, type = None, commit = True):
		if not values: return
		items = {}
		try:
			from orion.modules.orionitem import OrionItem
			for attribute in OrionItem.Lookups:
				attribute = attribute.lower()
				try: value = values[attribute]['enabled']
				except: value = True
				items[attribute] = {'name' : attribute.upper(), 'enabled' : value}
		except:
			items = values
		if items: count = len([1 for key, value in OrionTools.iterator(items) if value['enabled']])
		else: count = 0

		# Only do this if the data has not changed, since reading is fast (reads from cache), but writing is slow (write to file).
		key = self._filtersAttribute('filters.lookup.service', type)
		if not self.getObject(key) == items:
			self.set(self._filtersAttribute('filters.lookup.service', type), items, commit = commit)
			self.set(self._filtersAttribute('filters.lookup.service.label', type), str(count) + ' ' + OrionTools.translate(32096), commit = commit)

	@classmethod
	def setFiltersAccess(self, values, stream, type = None, commit = True):
		if not values: return
		items = {}
		try:
			from orion.modules.orionitem import OrionItem
			for attribute in OrionItem.Accesses:
				attribute = attribute.lower()
				try: value = values[attribute]['enabled']
				except: value = True
				items[attribute] = {'name' : attribute.upper(), 'enabled' : value}
		except:
			items = values
		if items: count = len([1 for key, value in OrionTools.iterator(items) if value['enabled']])
		else: count = 0

		# Only do this if the data has not changed, since reading is fast (reads from cache), but writing is slow (write to file).
		id = 'filters.access.' + stream
		key = self._filtersAttribute(id, type)
		if not self.getObject(key) == items:
			self.set(self._filtersAttribute(id, type), items, commit = commit)
			self.set(self._filtersAttribute(id + '.label', type), str(count) + ' ' + OrionTools.translate(32096), commit = commit)

	@classmethod
	def setFiltersAccessTorrent(self, values, type = None, commit = True):
		return self.setFiltersAccess(values = values, stream = OrionStream.TypeTorrent, type = type, commit = commit)

	@classmethod
	def setFiltersAccessUsenet(self, values, type = None, commit = True):
		return self.setFiltersAccess(values = values, stream = OrionStream.TypeUsenet, type = type, commit = commit)

	@classmethod
	def setFiltersAccessHoster(self, values, type = None, commit = True):
		return self.setFiltersAccess(values = values, stream = OrionStream.TypeHoster, type = type, commit = commit)

	@classmethod
	def setFiltersStreamOrigin(self, values, type = None, commit = True):
		if not values: return
		items = {}
		try:
			from orion.modules.orionstream import OrionStream
			for value in values:
				attribute = value.streamOrigin()
				if not attribute is None and not attribute == '':
					items[attribute.lower()] = {'name' : attribute.upper(), 'type' : value.streamType(), 'enabled' : True}
			settings = self.getFiltersStreamOrigin(type = type)
			if settings:
				for key, value in OrionTools.iterator(items):
					if not key in settings:
						settings[key] = value
				items = settings
		except:
			items = values
		if items: count = len([1 for key, value in OrionTools.iterator(items) if value['enabled']])
		else: count = 0

		# Only do this if the data has not changed, since reading is fast (reads from cache), but writing is slow (write to file).
		key = self._filtersAttribute('filters.stream.origin', type)
		if not self.getObject(key) == items:
			self.set(key, items, commit = commit)
			self.set(self._filtersAttribute('filters.stream.origin.label', type), str(count) + ' ' + OrionTools.translate(32096), commit = commit)

	@classmethod
	def setFiltersStreamSource(self, values, type = None, commit = True):
		if not values: return
		items = {}
		try:
			from orion.modules.orionstream import OrionStream
			for value in values:
				attribute = value.streamSource()
				if not attribute is None and not attribute == '':
					items[attribute.lower()] = {'name' : attribute.upper(), 'type' : value.streamType(), 'enabled' : True}
			settings = self.getFiltersStreamSource(type = type)
			if settings:
				for key, value in OrionTools.iterator(items):
					if not key in settings:
						settings[key] = value
				items = settings
		except:
			items = values
		if items: count = len([1 for key, value in OrionTools.iterator(items) if value['enabled']])
		else: count = 0

		# Only do this if the data has not changed, since reading is fast (reads from cache), but writing is slow (write to file).
		key = self._filtersAttribute('filters.stream.source', type)
		if not self.getObject(key) == items:
			self.set(key, items, commit = commit)
			self.set(self._filtersAttribute('filters.stream.source.label', type), str(count) + ' ' + OrionTools.translate(32096), commit = commit)

	@classmethod
	def setFiltersStreamHoster(self, values, type = None, commit = True):
		if not values: return
		items = {}
		try:
			from orion.modules.orionstream import OrionStream
			for value in values:
				attribute = value.streamHoster()
				if not attribute is None and not attribute == '':
					items[attribute.lower()] = {'name' : attribute.upper(), 'enabled' : True}
			settings = self.getFiltersStreamHoster(type = type)
			if settings:
				for key, value in OrionTools.iterator(items):
					if not key in settings:
						settings[key] = value
				items = settings
		except:
			items = values
		if items: count = len([1 for key, value in OrionTools.iterator(items) if value['enabled']])
		else: count = 0

		# Only do this if the data has not changed, since reading is fast (reads from cache), but writing is slow (write to file).
		key = self._filtersAttribute('filters.stream.hoster', type)
		if not self.getObject(key) == items:
			self.set(self._filtersAttribute('filters.stream.hoster', type), items, commit = commit)
			self.set(self._filtersAttribute('filters.stream.hoster.label', type), str(count) + ' ' + OrionTools.translate(32096), commit = commit)

	@classmethod
	def setFiltersFileLanguages(self, values, type = None, commit = True):
		self._setFiltersLanguages(values, 'filters.file.languages', 'fileLanguages', 'getFiltersFileLanguages', type, commit = commit)

	@classmethod
	def setFiltersMetaRelease(self, values, type = None, commit = True):
		self._setFilters(values, 'filters.meta.release', 'metaRelease', 'getFiltersMetaRelease', type, commit = commit)

	@classmethod
	def setFiltersMetaUploader(self, values, type = None, commit = True):
		self._setFilters(values, 'filters.meta.uploader', 'metaUploader', 'getFiltersMetaUploader', type, commit = commit)

	@classmethod
	def setFiltersMetaEdition(self, values, type = None, commit = True):
		self._setFilters(values, 'filters.meta.edition', 'metaEdition', 'getFiltersMetaEdition', type, commit = commit)

	@classmethod
	def setFiltersVideoCodec(self, values, type = None, commit = True):
		self._setFilters(values, 'filters.video.codec', 'videoCodec', 'getFiltersVideoCodec', type, commit = commit)

	@classmethod
	def setFiltersAudioType(self, values, type = None, commit = True):
		self._setFilters(values, 'filters.audio.type', 'audioType', 'getFiltersAudioType', type, commit = commit)

	@classmethod
	def setFiltersAudioSystem(self, values, type = None, commit = True):
		self._setFilters(values, 'filters.audio.system', 'audioSystem', 'getFiltersAudioSystem', type, commit = commit)

	@classmethod
	def setFiltersAudioCodec(self, values, type = None, commit = True):
		self._setFilters(values, 'filters.audio.codec', 'audioCodec', 'getFiltersAudioCodec', type, commit = commit)

	@classmethod
	def setFiltersAudioLanguages(self, values, type = None, commit = True):
		self._setFiltersLanguages(values, 'filters.audio.languages', 'audioLanguages', 'getFiltersAudioLanguages', type, commit = commit)

	@classmethod
	def setFiltersSubtitleType(self, values, type = None, commit = True):
		self._setFilters(values, 'filters.subtitle.type', 'subtitleType', 'getFiltersSubtitleType', type, commit = commit)

	@classmethod
	def setFiltersSubtitleLanguages(self, values, type = None, commit = True):
		self._setFiltersLanguages(values, 'filters.subtitle.languages', 'subtitleLanguages', 'getFiltersSubtitleLanguages', type, commit = commit)

	##############################################################################
	# CLEAN
	##############################################################################

	# Remove old/unused settings from the profile XML that are not in the new adadon settings XML.
	@classmethod
	def clean(self):
		data = OrionTools.fileRead(self.pathAddon())
		idCurrent = re.findall('<setting\s+id\s*=\s*[\'"](.*?)[\'"]', data, flags = re.IGNORECASE)
		idCurrent = {id : True for id in idCurrent}

		# Exclude integration settings.
		data = OrionTools.fileRead(self.pathProfile())
		idXml = re.findall('<setting\s+id\s*=\s*[\'"]((?!integration\.).*?)[\'"]', data, flags = re.IGNORECASE)

		# Clean XML.
		# Ignore "labelXXX" since these are Kodi strings.po translations for the old settings format.
		# Ignore "integration.XXX", since these are set, but are not in the addon settings.xml.
		# UPDATE: The "labelXXX" problem has been fixed.
		# UPDATE: "integration.XXX" should also be fixed, since those settings were now added to the default settings.xml, but still ignore them, since we might add a new integration, but forget to add an entry to settings.xml.
		for id in idXml:
			#if not(id.startswith('label') or id.startswith('integration.')) and not id in idCurrent:
			if not(id.startswith('integration.')) and not id in idCurrent:
				data = re.sub('([^\S\t\n\r]*<setting\s.*?id\s*=\s*[\'"]%s[\'"].*?(?:\/>|<\/setting>)[^\S\t\n\r]*[\n\r]*)' % id.replace('.', '\.'), '', data, flags = re.IGNORECASE)

		# Clean database.
		database = self._database()
		idDatabase = database.selectValues('SELECT id FROM %s;' % OrionSettings.DatabaseSettings)
		idDatabase = [id for id in idDatabase if not id in idCurrent]
		if idDatabase:
			database.delete('DELETE FROM %s WHERE %s;' % (OrionSettings.DatabaseSettings, ' OR '.join([('id = "%s"' % id) for id in idDatabase])))
			database.compress()

		OrionTools.fileWrite(self.pathProfile(), data)

	@classmethod
	def cleanTemporary(self):
		# Sometimes the process executing setFiltersUpdate() does not finish.
		# Eg: User canceles or restarts Kodi.
		# This makes old temp values remain in the database, overwriting custom source/hoster settings specified by the user, once the user does a scrape.
		# Automatically clear old values from service.py.
		return self._database().delete('DELETE FROM %s;' % OrionSettings.DatabaseTemp)

	##############################################################################
	# BACKUP
	##############################################################################

	@classmethod
	def _backupOutdated(self, settings):
		# Older version of the settings which are incompatible with each other.
		# These keys are from v4 and earlier. The new v5 does not have them anymore.
		return bool(settings) and ('general.advanced.enabled' in settings or 'general.dummy' in settings or 'filters.dummy' in settings)

	@classmethod
	def _backupOnlineCheck(self, notification = True):
		from orion.modules.orionuser import OrionUser
		if OrionUser.instance().subscriptionPackagePremium(): return True

		# This is blocked by the API as well. But save bandwidth by not even making the request.
		if notification: OrionInterface.dialogNotification(title = 32322, message = 33074, icon = OrionInterface.IconWarning)
		return False

	@classmethod
	def _backupExportOnline(self):
		settings = {}
		try:
			path = OrionTools.pathJoin(OrionTools.addonPath(), 'resources', 'settings.xml')
			if OrionTools.fileExists(path):
				# NB: First get the database values. Do not retrieve non-database values with the database parameter.
				ids = self._database().selectValues('SELECT id FROM %s;' % OrionSettings.DatabaseSettings)
				for id in ids:
					settings[id] = self.get(id, database = True)

				data = OrionTools.fileRead(path)
				pattern = re.compile('<setting.*id\s*=\s*"(.*?)"')
				ids = [id for id in re.findall(pattern, data)]

				for id in ids:
					if not id in settings:
						settings[id] = self.get(id)

				settings = {key : value for key, value in OrionTools.iterator(settings) if not key.startswith(('account', 'internal', 'integration'))}
		except:
			OrionTools.error()
		return settings

	@classmethod
	def _backupImportOnline(self, settings):
		try:
			if settings:
				if self._backupOutdated(settings = settings): return None

				for key, value in OrionTools.iterator(settings):
					self.set(key, value, commit = False)
				self._commit()
				return True
		except:
			OrionTools.error()
		return False

	@classmethod
	def backupExportOnline(self):
		if not self._backupOnlineCheck(): return False

		from orion.modules.orionapi import OrionApi
		OrionInterface.loaderShow()
		data = self._backupExportOnline()
		success = OrionApi().addonUpdate(data)
		OrionInterface.loaderHide()
		if success:
			self.set('internal.backup', OrionTools.hash(OrionTools.jsonTo(data)))
			OrionInterface.dialogNotification(title = 32170, message = 33013, icon = OrionInterface.IconSuccess)
			return True
		else:
			OrionInterface.dialogNotification(title = 32170, message = 33015, icon = OrionInterface.IconError)
			return False

	@classmethod
	def backupImportOnline(self, refresh = True):
		if not self._backupOnlineCheck(): return False

		from orion.modules.orionapi import OrionApi
		from orion.modules.orionuser import OrionUser
		OrionInterface.loaderShow()
		api = OrionApi()
		if api.addonRetrieve():
			success = self._backupImportOnline(api.data())
			if success:
				# Get updated user status
				if refresh:
					OrionUser.instance().update()
					self.cacheClear()
				OrionInterface.loaderHide()
				OrionInterface.dialogNotification(title = 32170, message = 33014, icon = OrionInterface.IconSuccess)
				return True
			else:
				OrionInterface.loaderHide()
				OrionInterface.dialogNotification(title = 32170, message = 33084 if success is None else 33016, icon = OrionInterface.IconError)
				return False
		else:
			OrionInterface.loaderHide()
			OrionInterface.dialogNotification(title = 32170, message = 33043, icon = OrionInterface.IconError)
			return False

	@classmethod
	def backupExportAutomaticOnline(self):
		if self._backupOnlineCheck(notification = False) and self._backupSetting(online = True):
			from orion.modules.orionapi import OrionApi
			data = self._backupExportOnline()
			current = OrionTools.hash(OrionTools.jsonTo(data))
			previous = self.getString('internal.backup')
			if not current == previous:
				if OrionApi().addonUpdate(data):
					self.set('internal.backup', current)
					return True
		return False

	@classmethod
	def backupImportAutomaticOnline(self):
		global OrionSettingsBackupOnline
		if not OrionSettingsBackupOnline and self._backupOnlineCheck(notification = False) and self._backupSetting(online = True):
			from orion.modules.orionapi import OrionApi
			OrionSettingsBackupOnline = True
			api = OrionApi()
			return api.addonRetrieve() and self._backupImportOnline(api.data())
		return False

	@classmethod
	def _backupPath(self, clear = False):
		path = OrionTools.pathTemporary('backup')
		OrionTools.directoryDelete(path)
		OrionTools.directoryCreate(path)
		return path

	@classmethod
	def _backupName(self, extension = ExtensionManual):
		# Windows does not support colons in file names.
		return OrionTools.addonName() + ' ' + OrionTools.translate(32170) + ' ' + OrionTools.timeFormat(format = '%Y-%m-%d %H.%M.%S', local = True) + '%s.' + extension

	@classmethod
	def _backupSetting(self, local = False, online = False):
		try: setting = int(self._addon().getSetting(id = 'general.settings.backup'))
		except: setting = 0
		if local and setting in [1, 3]: return True
		elif online and setting in [1, 2]: return True
		else: return False

	@classmethod
	def _backupAutomaticValid(self):
		# Do not convert to bool, but instead check for empty string (default in the XML).
		return not self._addon().getSetting(id = 'account.authentication.valid') == ''

	@classmethod
	def _backupAutomatic(self, force = False):
		success = False
		valid = self._backupAutomaticValid()
		local = self._backupSetting(local = True)
		online = self._backupSetting(online = True)
		if local or online:
			if valid:
				# Do not update the online backup here, since this will create too many requests to the server. Update from the service instead.
				if local: success = self._backupAutomaticExport(force = force)
			else:
				if local: success = self._backupAutomaticImport() and self._backupAutomaticValid()
				if not success and online:
					# NB: Do not import an online backup automatically while the wizard runs.
					# This happens if Orion is installed and launched for the first time.
					# Otherwise the settings are imported during initial wizard setup, although the user has selected in ther wizard to NOT import them.
					if OrionSettings.getBoolean('internal.initial'): success = self.backupImportAutomaticOnline()
				if self._backupAutomaticValid():
					from orion.modules.orionuser import OrionUser
					OrionUser.instance().update()
					self.cacheClear()
		return success

	@classmethod
	def _backupAutomaticExport(self, force = False):
		global OrionSettingsBackupLocal
		if force or not OrionSettingsBackupLocal:
			OrionSettingsBackupLocal = True
			directory = OrionTools.addonProfile()
			fileFrom = OrionTools.pathJoin(directory, 'settings.xml')
			if 'account.authentication.valid' in OrionTools.fileRead(fileFrom):
				fileTo = OrionTools.pathJoin(directory, 'settings.' + OrionSettings.ExtensionAutomatic)
				return OrionTools.fileCopy(fileFrom, fileTo, overwrite = True)
		return False

	@classmethod
	def _backupAutomaticImport(self):
		directory = OrionTools.addonProfile()
		fileTo = OrionTools.pathJoin(directory, 'settings.xml')
		fileFrom = OrionTools.pathJoin(directory, 'settings.' + OrionSettings.ExtensionAutomatic)
		return OrionTools.fileCopy(fileFrom, fileTo, overwrite = True)

	@classmethod
	def backupCheck(self, path):
		return OrionTools.archiveCheck(path)

	@classmethod
	def backupFiles(self, path = None, extension = ExtensionManual):
		directory = OrionTools.addonProfile()
		files = OrionTools.directoryList(directory, files = True, directories = False)
		names = []
		settings = ['settings.xml', (OrionSettings.DatabaseSettings + OrionDatabase.Extension).lower()]
		for i in range(len(files)):
			if files[i].lower() in settings:
				names.append(files[i])
		return [OrionTools.pathJoin(directory, i) for i in names]

	@classmethod
	def backupImport(self, path = None, extension = ExtensionManual):
		try:
			from orion.modules.orionuser import OrionUser

			if path == None: path = OrionInterface.dialogBrowse(title = 32170, type = OrionInterface.BrowseFile, mask = extension)

			directory = self._backupPath(clear = True)
			directoryData = OrionTools.addonProfile()

			OrionTools.archiveExtract(path, directory)

			directories, files = OrionTools.directoryList(directory)
			counter = 0
			for file in files:
				fileFrom = OrionTools.pathJoin(directory, file)
				fileTo = OrionTools.pathJoin(directoryData, file)
				if OrionTools.fileMove(fileFrom, fileTo, overwrite = True):
					counter += 1

			OrionTools.directoryDelete(path = directory, force = True)

			# Get updated user status
			OrionInterface.loaderShow()
			OrionUser.instance().update()
			self.cacheClear()
			OrionInterface.loaderHide()

			if counter > 0:
				OrionInterface.dialogNotification(title = 32170, message = 33014, icon = OrionInterface.IconSuccess)
				return True
			else:
				OrionInterface.dialogNotification(title = 32170, message = 33016, icon = OrionInterface.IconError)
				return False
		except:
			OrionInterface.dialogNotification(title = 32170, message = 33016, icon = OrionInterface.IconError)
			OrionTools.error()
			return False

	@classmethod
	def backupExport(self, path = None, extension = ExtensionManual):
		try:
			if path == None: path = OrionInterface.dialogBrowse(title = 32170, type = OrionInterface.BrowseDirectoryWrite)

			OrionTools.directoryCreate(path)
			name = self._backupName(extension = extension)
			path = OrionTools.pathJoin(path, name)
			counter = 0
			suffix = ''
			while OrionTools.fileExists(path % suffix):
				counter += 1
				suffix = ' [%d]' % counter
			path = path % suffix

			OrionTools.archiveCreate(path, self.backupFiles())
			if self.backupCheck(path):
				OrionInterface.dialogNotification(title = 32170, message = 33013, icon = OrionInterface.IconSuccess)
				return True
			else:
				OrionTools.fileDelete(path)
				OrionInterface.dialogNotification(title = 32170, message = 33015, icon = OrionInterface.IconError)
				return False
		except:
			OrionInterface.dialogNotification(title = 32170, message = 33015, icon = OrionInterface.IconError)
			OrionTools.error()
			return False

	##############################################################################
	# EXTERNAL
	##############################################################################

	@classmethod
	def _externalComment(self, app):
		return app.upper()

	@classmethod
	def _externalStart(self, app):
		return OrionSettings.ExternalStart % self._externalComment(app)

	@classmethod
	def _externalEnd(self, app):
		return OrionSettings.ExternalEnd % self._externalComment(app)

	@classmethod
	def _externalClean(self, data):
		while re.search('(\r?\n){3,}', data): data = re.sub('(\r?\n){3,}', '\n\n', data)
		return data

	@classmethod
	def externalCategory(self, app, enabled = False):
		if app is None or app == 'universal': return OrionSettings.CategoryFilters
		elif not OrionTools.isString(app): app = app.id()

		# If not enabled, default to the universal filters tab.
		if enabled and not self.getBoolean('filters.' + app + '.enabled'): return OrionSettings.CategoryFilters

		data = OrionTools.fileRead(self.pathAddon())
		index = data.find('filters.' + app)
		if not index or index < 0: return OrionSettings.CategoryFilters # If not added to the settings yet, default to the universal filters tab.
		data = data[:index]
		return data.count('<category') - 1

	@classmethod
	def externalLaunch(self, app):
		self.launch(category = self.externalCategory(app = app))

	@classmethod
	def externalInsert(self, app, check = False, settings = None, commit = True):
		from orion.modules.orionapi import OrionApi
		if not OrionApi._keyHidden(key = app.key()) and not OrionTools.addonName().lower() == app.name().lower() and not app.name().lower() == 'web': # Check name as well, in case the key changes.
			appId = app.id()
			if not check or not self.getFiltersCustomApp(appId):
				self.externalRemove(app)
				data = OrionTools.fileRead(self.pathAddon())

				commentStart = self._externalStart('universal')
				commentEnd = self._externalEnd('universal')
				appComment = self._externalComment(appId)

				subset = data[data.find(commentStart) + len(commentStart) : data.find(commentEnd)].strip('\n').strip('\r')

				index = subset.find('filters.custom.app')
				subset = subset[:index] + subset[index:].replace('<default>false</default>', '<default>true</default>', 1)

				index = subset.find('filters.custom.enabled')
				subset = subset[:index] + subset[index:].replace('<default>true</default>', '<default>false</default>', 1)

				subset = subset.replace('&type=universal', '&type=' + appId)
				subset = subset.replace('filters.', 'filters.' + appId + '.')

				appStart = '\n\n' + OrionSettings.ExternalStart % appComment + '\n<category id="filters.' + appId + '" label="' + self.externalLabel(label = app.name()) + '" help="34045">'
				appEnd = '</category>\n' + OrionSettings.ExternalEnd % appComment + '\n'
				subset = appStart + subset + appEnd

				end = '</category>'
				end = data.rfind(end) + len(end)

				endComment = 'END -->'
				if data.find(endComment, end) > 0: end = data.find(endComment, end) + len(endComment)

				data = data[:end] + subset + data[end:]
				OrionTools.fileWrite(self.pathAddon(), self._externalClean(data))

				if not settings:
					database = self._database(path = OrionTools.pathJoin(OrionTools.addonPath(), 'resources', OrionSettings.DatabaseSettings + OrionDatabase.Extension))
					settings = database.select('SELECT id, data FROM  %s;' % OrionSettings.DatabaseSettings)
					settings = [(i[0], OrionTools.jsonFrom(i[1])) for i in settings]
				for setting in settings:
					if setting[0].startswith('filters.'):
						id = self._filtersAttribute(setting[0], appId)
						current = OrionSettings.getObject(id)
						OrionSettings.set(id, current if current else setting[1], commit = False)
				if commit: self._commit()

	@classmethod
	def externalRemove(self, app):
		if not OrionTools.isString(app): app = app.id()
		data = OrionTools.fileRead(self.pathAddon())
		commentStart = self._externalStart(app)
		commentEnd = self._externalEnd(app)
		indexStart = data.find(commentStart)
		if indexStart >= 0:
			indexEnd = data.find(commentEnd)
			if indexStart > 0 and indexEnd > indexStart:
				data = data[:indexStart] + data[indexEnd + len(commentEnd):]
			OrionTools.fileWrite(self.pathAddon(), self._externalClean(data))

	@classmethod
	def externalLabel(self, label):
		try:
			# The new Kodi settings format cannot take a string as a setting's label attribute anymore, only a number for the strings translation file.
			# Insert a new label into strings.po.
			data = OrionTools.fileRead(self.pathStrings())

			subdata = re.search('(\[ORIONSTART\].*\[ORIONEND\])', data, re.IGNORECASE | re.DOTALL)
			if subdata:subdata = subdata.group(1)

			if subdata:
				# Already inserted.
				match = re.search('msgctxt\s*"#(\d+)"\s*msgid\s*"%s"' % label, subdata, re.IGNORECASE | re.DOTALL)
				if match:
					match = match.group(1)
					if match: return match

			# Get last inserted ID.
			id = re.search('.*msgctxt\s*"#(38\d+)"', subdata or data, re.IGNORECASE | re.DOTALL)
			if id:
				id = id.group(1)
				if id: id = int(id)
			if not id: id = 38000
			id += 1

			newdata = subdata.replace('[ORIONSTART]', '').replace('[ORIONEND]', '').strip('\n').strip(' ') if subdata else ''
			newdata += '\n\nmsgctxt "#%i"\nmsgid "%s"\nmsgstr ""\n\n' % (id, label)
			newdata = '\n\n[ORIONSTART]\n\n%s\n\n[ORIONEND]\n\n' % newdata.strip('\n')
			if subdata: data = data.replace(subdata, newdata)
			else: data += newdata

			OrionTools.fileWrite(self.pathStrings(), data)

			return str(id)
		except:
			OrionTools.error()
			return label

	@classmethod
	def externalClean(self):
		# NB: This has to remain here permanently.
		# Re-insert the filters if the XML file is replaced during addon updates or if the default (universal) settings change in a new version.
		from orion.modules.orionapp import OrionApp
		database = self._database(path = OrionTools.pathJoin(OrionTools.addonPath(), 'resources', OrionSettings.DatabaseSettings + OrionDatabase.Extension))
		settings = database.select('SELECT id, data FROM  %s;' % OrionSettings.DatabaseSettings)
		settings = [(i[0], OrionTools.jsonFrom(i[1])) for i in settings]
		for i in OrionApp.instances():
			self.externalRemove(i)
			self.externalInsert(i, check = True, settings = settings, commit = False)
		self._commit()

	##############################################################################
	# ADAPT
	##############################################################################

	@classmethod
	def adapt(self, retries = 1):
		path = OrionTools.pathJoin(OrionTools.addonPath(), 'resources', 'settings.xml')
		pathBase = OrionTools.pathJoin(OrionTools.addonPath(), 'resources', 'settings.base')
		exists = OrionTools.fileExists(path)

		# The XML changed between versions.
		if exists:
			dataBase = OrionTools.fileRead(pathBase)
			dataCurrent = OrionTools.fileRead(path)
			if dataBase and dataCurrent:
				tag = 'UNIVERSAL END'
				dataBase = dataBase[:dataBase.find(tag)]
				dataCurrent = dataCurrent[:dataCurrent.find(tag)]
				dataBase = re.sub('\s', '', dataBase)
				dataCurrent = re.sub('\s', '', dataCurrent)
				if dataBase == dataCurrent:
					OrionTools.log('The settings file exists and has not changed since the previous version. Keeping the current file.')
				else:
					OrionTools.log('The settings file exists, but has changed since the previous version. Making a new copy.')
					exists = False
		else:
			OrionTools.log('The settings file does not exist. Making a new copy.')

		if not exists:
			# Try alternative copy methods (XBMC vs native Python, copy vs file r/w).
			# Some Android devices seem to have problems copying the settings.xml file.
			count = 0
			while count < retries:
				count += 1
				if count > 1 and count < retries: OrionTools.sleep(2)

				# Use XBMC copy functions.
				OrionTools.fileCopy(pathFrom = pathBase, pathTo = path, overwrite = True, native = False, copy = True)
				exists = OrionTools.fileExists(path)
				if exists: break
				OrionTools.log('The XBMC file copy mechanism failed. Retry: ' + str(count))
				OrionTools.sleep(1)

				# Use XBMC file r/w functions.
				OrionTools.fileCopy(pathFrom = pathBase, pathTo = path, overwrite = True, native = False, copy = False)
				exists = OrionTools.fileExists(path)
				if exists: break
				OrionTools.log('The XBMC file read/write mechanism failed. Retry: ' + str(count))
				OrionTools.sleep(1)

				# Use Python copy functions.
				OrionTools.fileCopy(pathFrom = pathBase, pathTo = path, overwrite = True, native = True, copy = True)
				exists = OrionTools.fileExists(path)
				if exists: break
				OrionTools.log('The Python file copy mechanism failed. Retry: ' + str(count))
				OrionTools.sleep(1)

				# Use Python file r/w functions.
				OrionTools.fileCopy(pathFrom = pathBase, pathTo = path, overwrite = True, native = True, copy = False)
				exists = OrionTools.fileExists(path)
				if exists: break
				OrionTools.log('The Python file read/write mechanism failed. Retry: ' + str(count))
				OrionTools.sleep(1)

		return exists

	##############################################################################
	# WIZARD
	##############################################################################

	@classmethod
	def wizard(self):
		from orion.modules.orionuser import OrionUser
		from orion.modules.orionnavigator import OrionNavigator
		from orion.modules.orionintegration import OrionIntegration

		title = 32249
		cancel = 32251
		next = 32250
		skip = 32260

		# Welcome
		choice = OrionInterface.dialogOption(title = title, message = 35001, labelConfirm = cancel, labelDeny = next)
		if choice: return

		# Authentication
		choice = OrionInterface.dialogOption(title = title, message = 35002, labelConfirm = 32252, labelDeny = 32253)
		if choice:
			message = OrionTools.translate(35003) % (OrionInterface.fontBold(str(OrionUser.LinksAnonymous)), OrionInterface.fontBold(str(OrionUser.LinksFree)))
			choice = OrionInterface.dialogOption(title = title, message = message, labelConfirm = cancel, labelDeny = next)
			if choice: return
			OrionUser.anonymous()
		else:
			if not OrionNavigator.settingsAccountLogin(settings = False, refresh = False): return
		OrionInterface.containerRefresh()

		# Limit
		choice = OrionInterface.dialogOption(title = title, message = 35004, labelConfirm = cancel, labelDeny = next)
		if choice: return
		choice = OrionInterface.dialogInput(title = 32254, type = OrionInterface.InputNumeric, verify = (1, 30))
		limit = OrionUser.instance().subscriptionPackageLimitStreams() / float(choice)
		limit = int(OrionTools.roundDown(limit, nearest = 10 if limit >= 100 else 5 if limit >= 50 else None))
		limit = min(5000, max(5, limit))
		self.set('filters.limit.count', limit)
		self.set('filters.limit.count.movie', limit)
		self.set('filters.limit.count.show', limit)

		# Quality
		qualityHigh = OrionInterface.dialogOption(title = title, message = 35005)
		self.set('filters.video.quality.maximum', 0 if qualityHigh else 9)
		qualityLow = OrionInterface.dialogOption(title = title, message = 35006)
		self.set('filters.video.quality.minimum', 0 if qualityLow else 7)
		self.set('filters.video.quality', not(qualityHigh and qualityLow))

		# Type
		typeTorrent = OrionInterface.dialogOption(title = title, message = 35007)
		typeUsenet = OrionInterface.dialogOption(title = title, message = 35008)
		typeHoster = OrionInterface.dialogOption(title = title, message = 35009)
		typeStream = None
		if typeTorrent and typeUsenet and typeHoster: typeStream = 0
		elif typeTorrent and typeUsenet: typeStream = 1
		elif typeTorrent and typeHoster: typeStream = 2
		elif typeUsenet and typeHoster: typeStream = 3
		elif typeTorrent: typeStream = 4
		elif typeUsenet: typeStream = 5
		elif typeHoster: typeStream = 6
		if not typeStream is None: self.set('filters.stream.type', typeStream)

		# Integration
		restart = False
		choice = OrionInterface.dialogOption(title = title, message = 35010, labelConfirm = skip, labelDeny = next)
		if not choice:
			while True:
				addons = OrionIntegration.addons(sort = True) # Refresh to recheck integration.
				items = [i['format'] for i in addons]
				choice = OrionInterface.dialogOptions(title = 32174, items = items)
				if choice < 0: break
				if addons[choice]['native']:
					OrionInterface.dialogNotification(title = 32263, message = 33024, icon = OrionInterface.IconSuccess)
				else:
					OrionIntegration.integrate(addons[choice]['scrapers'] if addons[choice]['scrapers'] else addons[choice]['name'], silent = True)
					if not restart: restart = addons[choice]['restart']

		# Finish
		OrionInterface.dialogConfirm(title = title, message = OrionTools.translate(35011))

		# Restart
		if restart and OrionInterface.dialogOption(title = 32174, message = 33026, labelConfirm = 32261, labelDeny = 32262):
			OrionTools.kodiRefresh()
