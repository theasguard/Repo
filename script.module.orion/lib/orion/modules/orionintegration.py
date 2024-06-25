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
# ORIONINTEGRATION
##############################################################################
# Class for integrating Orion into other addons.
##############################################################################

import re
from orion.modules.oriontools import *
from orion.modules.orionsettings import *
from orion.modules.orioninterface import *

class OrionIntegration:

	ExtensionBackup = '.orion'
	PathLength = 50

	AddonGaia = 'Gaia'
	AddonSeren = 'Seren'
	AddonIncursion = 'Incursion'
	AddonPlacenta = 'Placenta'
	AddonCovenant = 'Covenant'
	AddonMagicality = 'Magicality'
	AddonTheOath = 'TheOath'
	AddonApocalypse720 = 'Apocalypse 720'
	AddonNoLivesMatter = 'No Lives Matter'
	AddonYoda = 'Yoda'
	AddonBodie = 'Bodie'
	AddonNymeria = 'Nymeria'
	AddonVenom = 'Venom'
	AddonScrubs = 'Scrubs'
	AddonMedusa = 'Medusa'
	AddonMercury = 'Mercury'
	AddonDeceit = 'Deceit'
	AddonFen = 'Fen'
	AddonNightwing = 'Nightwing'
	AddonPov = 'POV'
	AddonUmbrella = 'Umbrella'
	AddonKingPin = 'KingPin'
	AddonEzra = 'Ezra'
	AddonGenesis = 'Genesis'
	AddonExodus = 'Exodus'
	AddonExodusRedux = 'Exodus Redux'
	AddonNeptuneRising = 'Neptune Rising'
	AddonDeathStreams = 'Death Streams'
	AddonBoomMovies = 'Boom Movies'
	AddonContinuum = 'Continuum'
	AddonMarauder = 'Marauder'
	AddonPatriot = 'Patriot'
	AddonAsguard = 'Asguard'
	AddonAsgard = 'Asgard'
	AddonTheCrew = 'The Crew'
	AddonChainsGenocide = 'Chains Genocide'
	AddonKodiVerse = 'KodiVerse'
	AddonOpenScrapers = 'Open Scrapers'
	AddonLambdaScrapers = 'Lambda Scrapers'
	AddonFenomScrapers = 'Fenom Scrapers'
	AddonNightwingScrapers = 'Nightwing Scrapers'
	AddonCocoScrapers = 'Coco Scrapers'
	AddonUmbrellaScrapers = 'Umbrella Scrapers'
	AddonKingPinScrapers = 'KingPin Scrapers'
	AddonEzScrapers = 'Ez Scrapers'
	AddonUniversalScrapers = 'Universal Scrapers'
	AddonUniversalDebrid = 'Universal Debrid'
	AddonNanScrapers = 'NaN Scrapers'
	AddonEncrypticScrapers = 'Encryptic Scrapers'
	AddonElementum = 'Elementum'
	AddonQuasar = 'Quasar'
	Addons = [AddonGaia, AddonSeren, AddonIncursion, AddonPlacenta, AddonCovenant, AddonMagicality, AddonTheOath, AddonApocalypse720, AddonNoLivesMatter, AddonYoda, AddonBodie, AddonNymeria, AddonVenom, AddonScrubs, AddonMedusa, AddonMercury, AddonDeceit, AddonFen, AddonNightwing, AddonPov, AddonUmbrella, AddonKingPin, AddonEzra, AddonGenesis, AddonExodus, AddonExodusRedux, AddonNeptuneRising, AddonDeathStreams, AddonBoomMovies, AddonContinuum, AddonMarauder, AddonPatriot, AddonAsguard, AddonAsgard, AddonTheCrew, AddonChainsGenocide, AddonKodiVerse, AddonOpenScrapers, AddonLambdaScrapers, AddonFenomScrapers, AddonNightwingScrapers, AddonUmbrellaScrapers, AddonCocoScrapers, AddonKingPinScrapers, AddonEzScrapers, AddonUniversalScrapers, AddonUniversalDebrid, AddonNanScrapers, AddonEncrypticScrapers, AddonElementum, AddonQuasar]

	LanguageXml = 'xml'
	LanguagePython = 'python'

	CommentXmlStart = '<!-- [ORION/] -->'
	CommentXmlEnd = '<!-- [/ORION] -->'
	CommentPythonStart = '# [ORION/]'
	CommentPythonEnd = '# [/ORION]'

	##############################################################################
	# CONSTRUCTOR
	##############################################################################

	def __init__(self, silent = False):
		self.mSilent = silent

	##############################################################################
	# GENERAL
	##############################################################################

	@classmethod
	def id(self, addon, check = False):
		if addon == None: return addon
		addon = addon.lower().replace(' ', '')
		if check:
			addons = [i.lower().replace(' ', '') for i in OrionIntegration.Addons]
			if not addon in addons: return None
		return addon

	@classmethod
	def _comment(self, data, language = LanguagePython, indentation = ''):
		commentStart = ''
		commentEnd = ''
		if language == OrionIntegration.LanguageXml:
			commentStart = OrionIntegration.CommentXmlStart
			commentEnd = OrionIntegration.CommentXmlEnd
		elif language == OrionIntegration.LanguagePython:
			commentStart = OrionIntegration.CommentPythonStart
			commentEnd = OrionIntegration.CommentPythonEnd
		data = data.replace('\n', '\n' + indentation)
		return '\n\n' + indentation + commentStart + '\n' + indentation + data + '\n' + indentation + commentEnd + '\n'

	@classmethod
	def _expression(self, language = LanguagePython, full = True):
		commentStart = ''
		commentEnd = ''
		if language == OrionIntegration.LanguageXml:
			commentStart = OrionIntegration.CommentXmlStart
			commentEnd = OrionIntegration.CommentXmlEnd
		elif language == OrionIntegration.LanguagePython:
			commentStart = OrionIntegration.CommentPythonStart
			commentEnd = OrionIntegration.CommentPythonEnd
		if full: return '\n[\t ]*' + ((commentStart + '.*' + commentEnd).replace('\n', '').replace('[', '\[').replace(']', '\]').replace('/', '\/')) + '[\t ]*\n'
		else: return commentStart.replace('\n', '').replace('[', '\[').replace(']', '\]').replace('/', '\/')

	def _path(self, file):
		return OrionTools.pathJoin(OrionTools.addonPath(), 'lib', 'orion', 'integration', self.id, file)

	def _content(self, file):
		return OrionTools.fileRead(self._path(file)).strip()

	def _version(self, idPlugin, idModule = None):
		try:
			version = OrionTools.addonVersion(idPlugin)
			if idModule: version += '-' + OrionTools.addonVersion(idModule)
			return version
		except: pass
		return None

	##############################################################################
	# BACKUP
	##############################################################################

	def _backupContains(self, path):
		return OrionTools.fileContains(path, self._expression(OrionIntegration.LanguageXml, False)) or OrionTools.fileContains(path, self._expression(OrionIntegration.LanguagePython, False))

	def _backupCreate(self):
		for i in self.files:
			if not self._backupContains(i):
				OrionTools.fileCopy(i, i + OrionIntegration.ExtensionBackup, overwrite = True)

	def _backupRestore(self):
		for i in self.files:
			j = i + OrionIntegration.ExtensionBackup
			if OrionTools.fileExists(j):
				OrionTools.fileMove(j, i, overwrite = True)

	##############################################################################
	# INIRIALIZE
	##############################################################################

	@classmethod
	def initialize(self, addon, silent = False):
		integration = OrionIntegration(silent = silent)
		try:
			if addon == OrionIntegration.AddonGaia: integration._gaiaInitialize()
			elif addon == OrionIntegration.AddonSeren: integration._serenInitialize()
			elif addon == OrionIntegration.AddonIncursion: integration._incursionInitialize()
			elif addon == OrionIntegration.AddonPlacenta: integration._placentaInitialize()
			elif addon == OrionIntegration.AddonCovenant: integration._covenantInitialize()
			elif addon == OrionIntegration.AddonMagicality: integration._magicalityInitialize()
			elif addon == OrionIntegration.AddonTheOath: integration._theOathInitialize()
			elif addon == OrionIntegration.AddonApocalypse720: integration._apocalypse720Initialize()
			elif addon == OrionIntegration.AddonNoLivesMatter: integration._noLivesMatterInitialize()
			elif addon == OrionIntegration.AddonYoda: integration._yodaInitialize()
			elif addon == OrionIntegration.AddonBodie: integration._bodieInitialize()
			elif addon == OrionIntegration.AddonNymeria: integration._nymeriaInitialize()
			elif addon == OrionIntegration.AddonFen: integration._fenInitialize()
			elif addon == OrionIntegration.AddonNightwing: integration._nightwingInitialize()
			elif addon == OrionIntegration.AddonPov: integration._povInitialize()
			elif addon == OrionIntegration.AddonUmbrella: integration._umbrellaInitialize()
			elif addon == OrionIntegration.AddonKingPin: integration._kingPinInitialize()
			elif addon == OrionIntegration.AddonEzra: integration._ezraInitialize()
			elif addon == OrionIntegration.AddonVenom: integration._venomInitialize()
			elif addon == OrionIntegration.AddonScrubs: integration._scrubsInitialize()
			elif addon == OrionIntegration.AddonMedusa: integration._medusaInitialize()
			elif addon == OrionIntegration.AddonMercury: integration._mercuryInitialize()
			elif addon == OrionIntegration.AddonDeceit: integration._deceitInitialize()
			elif addon == OrionIntegration.AddonGenesis: integration._genesisInitialize()
			elif addon == OrionIntegration.AddonExodus: integration._exodusInitialize()
			elif addon == OrionIntegration.AddonExodusRedux: integration._exodusReduxInitialize()
			elif addon == OrionIntegration.AddonNeptuneRising: integration._neptuneRisingInitialize()
			elif addon == OrionIntegration.AddonDeathStreams: integration._deathStreamsInitialize()
			elif addon == OrionIntegration.AddonBoomMovies: integration._boomMoviesInitialize()
			elif addon == OrionIntegration.AddonContinuum: integration._continuumInitialize()
			elif addon == OrionIntegration.AddonMarauder: integration._marauderInitialize()
			elif addon == OrionIntegration.AddonPatriot: integration._patriotInitialize()
			elif addon == OrionIntegration.AddonAsguard: integration._asguardInitialize()
			elif addon == OrionIntegration.AddonAsgard: integration._asgardInitialize()
			elif addon == OrionIntegration.AddonTheCrew: integration._theCrewInitialize()
			elif addon == OrionIntegration.AddonChainsGenocide: integration._chainsGenocideInitialize()
			elif addon == OrionIntegration.AddonKodiVerse: integration._kodiVerseInitialize()
			elif addon == OrionIntegration.AddonOpenScrapers: integration._openScrapersInitialize()
			elif addon == OrionIntegration.AddonLambdaScrapers: integration._lambdaScrapersInitialize()
			elif addon == OrionIntegration.AddonFenomScrapers: integration._fenomScrapersInitialize()
			elif addon == OrionIntegration.AddonNightwingScrapers: integration._nightwingScrapersInitialize()
			elif addon == OrionIntegration.AddonCocoScrapers: integration._cocoScrapersInitialize()
			elif addon == OrionIntegration.AddonUmbrellaScrapers: integration._umbrellaScrapersInitialize()
			elif addon == OrionIntegration.AddonKingPinScrapers: integration._kingPinScrapersInitialize()
			elif addon == OrionIntegration.AddonEzScrapers: integration._ezScrapersInitialize()
			elif addon == OrionIntegration.AddonUniversalScrapers: integration._universalScrapersInitialize()
			elif addon == OrionIntegration.AddonUniversalDebrid: integration._universalDebridInitialize()
			elif addon == OrionIntegration.AddonNanScrapers: integration._nanScrapersInitialize()
			elif addon == OrionIntegration.AddonEncrypticScrapers: integration._encrypticScrapersInitialize()
			elif addon == OrionIntegration.AddonElementum: integration._elementumInitialize()
			elif addon == OrionIntegration.AddonQuasar: integration._quasarInitialize()
		except:
			OrionTools.error()
		return integration

	##############################################################################
	# CHECK
	##############################################################################

	@classmethod
	def check(self, silent = False):
		for addon in OrionIntegration.Addons:
			try:
				integration = self.initialize(addon, silent = silent)
				setting = OrionSettings.getIntegration(integration.id)
				try: native = integration.native
				except: native = False
				if ((not setting == '' and not setting == '0') or native) and not setting == integration.version:
					integration._integrate(addon)
					OrionSettings.setIntegration(integration.id, integration.version)
			except: pass

	##############################################################################
	# ADDONS
	##############################################################################

	@classmethod
	def addons(self, sort = False):
		result = []
		formatNative = OrionInterface.font(32259, color = OrionInterface.ColorGood)
		formatIntegrated = OrionInterface.font(32256, color = OrionInterface.ColorMedium)
		formatNotIntegrated = OrionInterface.font(32257, color = OrionInterface.ColorPoor)
		formatNotInstalled = OrionInterface.font(32258, color = OrionInterface.ColorBad)
		formatNotEnabled = OrionInterface.font(32281, color = OrionInterface.ColorBad)
		for addon in OrionIntegration.Addons:
			try:
				integration = self.initialize(addon)
				idAddon = None
				try: idAddon = integration.idPlugin
				except: idAddon = integration.idModule
				try: settings = integration.idSettings
				except: settings = idAddon
				try: version = OrionTools.addonVersion(idAddon)
				except: version = None
				try: native = integration.native
				except: native = False
				try: restart = not native and integration.restart
				except: restart = True
				try:
					scrapers = integration.scrapers
					scrapersId = self.initialize(scrapers).id
				except:
					scrapers = None
					scrapersId = None
				installed = OrionTools.addonInstalled(idAddon)
				enabled = OrionTools.addonEnabled(idAddon)
				integrated = OrionSettings.getIntegration(integration.id)
				integrated = native or not integrated == '' or (enabled and scrapersId and OrionSettings.getIntegration(scrapersId))
				action = 'integration' + addon.title().replace(' ', '')
				format = '%s: %s' % (OrionInterface.font(addon, bold = True), formatNotInstalled if not installed else formatNotEnabled if not enabled else formatNative if native else formatIntegrated if integrated else formatNotIntegrated)
				result.append({'id' : integration.id, 'name' : addon, 'addon' : idAddon, 'version' : version, 'settings' : settings, 'installed' : installed, 'enabled' : enabled, 'integrated' : integrated, 'native' : native, 'restart' : restart, 'scrapers' : scrapers, 'action' : action, 'format' : format})
			except:
				OrionTools.error()
		if sort: result = sorted(result, key = lambda i: i['name'])
		return result

	##############################################################################
	# CLEAN
	##############################################################################

	def _clean(self, language = None):
		if language == None:
			self._clean(language = OrionIntegration.LanguageXml)
			self._clean(language = OrionIntegration.LanguagePython)
		else:
			expression = self._expression(language, True)
			for i in self.files:
				OrionTools.fileClean(i, expression)
			if not self.deletes == None:
				for i in self.deletes:
					if OrionTools.fileExists(i):
						OrionTools.fileDelete(i)
					elif OrionTools.directoryExists(i):
						OrionTools.directoryDelete(i)

	@classmethod
	def clean(self, addon):
		integration = self.initialize(addon)
		if not OrionTools.addonInstalled(integration.idPlugin):
			OrionInterface.dialogNotification(title = 32175, message = 33027, icon = OrionInterface.IconError)
		elif not OrionTools.addonEnabled(integration.idPlugin):
			OrionInterface.dialogNotification(title = 32175, message = 33010, icon = OrionInterface.IconError)
		elif OrionInterface.dialogOption(title = 32174, message = OrionTools.translate(33021) % addon):
			integration._backupRestore()
			integration._clean()
			if integration._deintegrate(addon):
				OrionSettings.setIntegration(integration.id, '')
				OrionInterface.dialogNotification(title = 32177, message = 33019, icon = OrionInterface.IconSuccess)
				return True
		return False

	##############################################################################
	# INTEGRATE
	##############################################################################

	@classmethod
	def integrate(self, addon, silent = False):
		integration = self.initialize(addon)
		if not OrionTools.addonInstalled(integration.idPlugin):
			OrionInterface.dialogNotification(title = 32175, message = 33027, icon = OrionInterface.IconError)
		elif not OrionTools.addonEnabled(integration.idPlugin):
			OrionInterface.dialogNotification(title = 32175, message = 33010, icon = OrionInterface.IconError)
		elif silent or OrionInterface.dialogOption(title = 32174, message = OrionTools.translate(33020) % (addon, addon)):
			if integration._integrate(addon):
				try: reintegrate = integration.reintegrate or silent
				except: reintegrate = True
				try: restart = integration.restart
				except: restart = True
				if reintegrate and not addon == OrionIntegration.AddonSeren and (silent or OrionInterface.dialogOption(title = 32174, message = OrionTools.translate(33022) % (addon, addon))):
					OrionSettings.setIntegration(integration.id, integration.version)
				else:
					OrionSettings.setIntegration(integration.id, 0)
				if not silent and restart:
					message = (OrionTools.translate(33025) % addon) + OrionInterface.fontNewline() + OrionInterface.font(33026, bold = True)
					if OrionInterface.dialogOption(title = 32174, message = message, labelConfirm = 32261, labelDeny = 32262):
						OrionTools.kodiRefresh()
				return True
		return False

	def _integrate(self, addon):
		self._backupRestore()
		self._clean()
		self._backupCreate()
		result = False
		if addon == OrionIntegration.AddonGaia: result = True
		elif addon == OrionIntegration.AddonSeren: result = self._serenIntegrate()
		elif addon == OrionIntegration.AddonIncursion: result = self._incursionIntegrate()
		elif addon == OrionIntegration.AddonPlacenta: result = self._placentaIntegrate()
		elif addon == OrionIntegration.AddonCovenant: result = self._covenantIntegrate()
		elif addon == OrionIntegration.AddonMagicality: result = self._magicalityIntegrate()
		elif addon == OrionIntegration.AddonTheOath: result = True
		elif addon == OrionIntegration.AddonApocalypse720: result = True
		elif addon == OrionIntegration.AddonNoLivesMatter: result = True
		elif addon == OrionIntegration.AddonYoda: result = self._yodaIntegrate()
		elif addon == OrionIntegration.AddonDeathStreams: result = self._deathStreamsIntegrate()
		elif addon == OrionIntegration.AddonBoomMovies: result = self._boomMoviesIntegrate()
		elif addon == OrionIntegration.AddonContinuum: result = self._continuumIntegrate()
		elif addon == OrionIntegration.AddonMarauder: result = True
		elif addon == OrionIntegration.AddonPatriot: result = True
		elif addon == OrionIntegration.AddonAsguard: result = True
		elif addon == OrionIntegration.AddonAsgard: result = self._asgardIntegrate()
		elif addon == OrionIntegration.AddonTheCrew: result = True
		elif addon == OrionIntegration.AddonChainsGenocide: result = self._chainsGenocideIntegrate()
		elif addon == OrionIntegration.AddonKodiVerse: result = self._kodiVerseIntegrate()
		elif addon == OrionIntegration.AddonScrubs: result = self._scrubsIntegrate()
		elif addon == OrionIntegration.AddonPov: result = self._povIntegrate()
		elif addon == OrionIntegration.AddonGenesis: result = self._genesisIntegrate()
		elif addon == OrionIntegration.AddonExodus: result = self._exodusIntegrate()
		elif addon == OrionIntegration.AddonOpenScrapers: result = self._openScrapersIntegrate()
		elif addon == OrionIntegration.AddonLambdaScrapers: result = self._lambdaScrapersIntegrate()
		elif addon == OrionIntegration.AddonFenomScrapers: result = self._fenomScrapersIntegrate()
		elif addon == OrionIntegration.AddonNightwingScrapers: result = self._nightwingScrapersIntegrate()
		elif addon == OrionIntegration.AddonCocoScrapers: result = self._cocoScrapersIntegrate()
		elif addon == OrionIntegration.AddonUmbrellaScrapers: result = self._umbrellaScrapersIntegrate()
		elif addon == OrionIntegration.AddonKingPinScrapers: result = self._kingPinScrapersIntegrate()
		elif addon == OrionIntegration.AddonEzScrapers: result = self._ezScrapersIntegrate()
		elif addon == OrionIntegration.AddonUniversalScrapers: result = self._universalScrapersIntegrate()
		elif addon == OrionIntegration.AddonUniversalDebrid: result = self._universalDebridIntegrate()
		elif addon == OrionIntegration.AddonNanScrapers: result = self._nanScrapersIntegrate()
		elif addon == OrionIntegration.AddonEncrypticScrapers: result = True
		elif addon == OrionIntegration.AddonElementum: result = self._elementumIntegrate()
		elif addon == OrionIntegration.AddonQuasar: result = self._quasarIntegrate()
		return result

	def _integrateSuccess(self):
		if not self.mSilent: OrionInterface.dialogNotification(title = 32176, message = 33018, icon = OrionInterface.IconSuccess)
		return True

	def _integrateFailure(self, message = None, path = None):
		self._clean()
		self._backupRestore()
		if message is None: message = OrionTools.translate(32324)
		original = path
		if path is None: path = ''
		else: path = OrionInterface.fontNewline().join([path[i - OrionIntegration.PathLength : i] for i in range(OrionIntegration.PathLength, len(path) + OrionIntegration.PathLength, OrionIntegration.PathLength)])
		OrionInterface.dialogNotification(title = 32175, message = 33017, icon = OrionInterface.IconError)
		OrionInterface.dialogConfirm(title = 32174, message = OrionInterface.fontBold(32175) + OrionInterface.fontNewline() + message + OrionInterface.fontNewline() + path)
		OrionTools.log('INTEGRATION FAILURE: ' + message + (' (' + original + ')' if original else ''))
		return False

	##############################################################################
	# DEINTEGRATE
	##############################################################################

	def _deintegrate(self, addon):
		result = True
		if addon == OrionIntegration.AddonSeren: result = self._serenDeintegrate()
		return result

	##############################################################################
	# LAUNCH
	##############################################################################

	@classmethod
	def launch(self, addon):
		integration = self.initialize(addon)
		if not OrionTools.addonInstalled(integration.idPlugin):
			OrionInterface.dialogNotification(title = 32282, message = 33027, icon = OrionInterface.IconError)
		elif not OrionTools.addonEnabled(integration.idPlugin):
			OrionInterface.dialogNotification(title = 32282, message = 33010, icon = OrionInterface.IconError)
		else:
			OrionTools.addonLaunch(integration.idPlugin)
			return True
		return False

	##############################################################################
	# SETTINGS
	##############################################################################

	@classmethod
	def settings(self, addon):
		integration = self.initialize(addon)
		try: addon = integration.idSettings
		except:
			try: addon = integration.idPlugin
			except:
				try: addon = integration.idModule
				except: addon = None
		if not addon or not OrionTools.addonInstalled(addon):
			OrionInterface.dialogNotification(title = 32282, message = 33027, icon = OrionInterface.IconError)
		elif not OrionTools.addonEnabled(addon):
			OrionInterface.dialogNotification(title = 32282, message = 33010, icon = OrionInterface.IconError)
		else:
			OrionSettings.launch(addon = addon)
			return True
		return False

	##############################################################################
	# EXECUTE
	##############################################################################

	@classmethod
	def execute(self, addon, integrate = True):
		integration = self.initialize(addon)

		try: native = integration.native
		except: native = False
		try: scrapers = integration.scrapers
		except: scrapers = None

		if native:
			OrionInterface.dialogNotification(title = 32263, message = 33024, icon = OrionInterface.IconSuccess)
			integrate = False
		elif not scrapers is None:
			if OrionInterface.dialogOption(title = 32174, message = OrionTools.translate(33023) % (addon, scrapers, scrapers)):
				addon = scrapers
			else:
				return None

		items = []
		if integrate:
			items.append(OrionInterface.fontBold(32178) + ': ' + OrionTools.translate(32179))
			items.append(OrionInterface.fontBold(32006) + ': ' + OrionTools.translate(32180))
		items.append(OrionInterface.fontBold(32181) + ': ' + OrionTools.translate(32182))
		items.append(OrionInterface.fontBold(32005) + ': ' + OrionTools.translate(32280))
		choice = OrionInterface.dialogOptions(title = 32174, items = items)

		if integrate:
			if choice == 0:
				result = self.integrate(addon)
				OrionInterface.containerRefresh()
				return result
			elif choice == 1:
				result = self.clean(addon)
				OrionInterface.containerRefresh()
				return result
			elif choice == 2:
				return self.launch(addon)
			elif choice == 3:
				return self.settings(addon)
		else:
			if choice == 0:
				return self.launch(addon)
			elif choice == 1:
				return self.settings(addon)

	@classmethod
	def executeGaia(self):
		return self.execute(OrionIntegration.AddonGaia)

	@classmethod
	def executeSeren(self):
		return self.execute(OrionIntegration.AddonSeren)

	@classmethod
	def executeIncursion(self):
		return self.execute(OrionIntegration.AddonIncursion)

	@classmethod
	def executePlacenta(self):
		return self.execute(OrionIntegration.AddonPlacenta)

	@classmethod
	def executeCovenant(self):
		return self.execute(OrionIntegration.AddonCovenant)

	@classmethod
	def executeMagicality(self):
		return self.execute(OrionIntegration.AddonMagicality)

	@classmethod
	def executeTheOath(self):
		return self.execute(OrionIntegration.AddonTheOath)

	@classmethod
	def executeApocalypse720(self):
		return self.execute(OrionIntegration.AddonApocalypse720)

	@classmethod
	def executeNoLivesMatter(self):
		return self.execute(OrionIntegration.AddonNoLivesMatter)

	@classmethod
	def executeYoda(self):
		return self.execute(OrionIntegration.AddonYoda)

	@classmethod
	def executeBodie(self):
		return self.execute(OrionIntegration.AddonBodie)

	@classmethod
	def executeNymeria(self):
		return self.execute(OrionIntegration.AddonNymeria)

	@classmethod
	def executeVenom(self):
		return self.execute(OrionIntegration.AddonVenom)

	@classmethod
	def executeScrubs(self):
		return self.execute(OrionIntegration.AddonScrubs)

	@classmethod
	def executeMedusa(self):
		return self.execute(OrionIntegration.AddonMedusa)

	@classmethod
	def executeMercury(self):
		return self.execute(OrionIntegration.AddonMercury)

	@classmethod
	def executeDeceit(self):
		return self.execute(OrionIntegration.AddonDeceit)

	@classmethod
	def executeFen(self):
		return self.execute(OrionIntegration.AddonFen)

	@classmethod
	def executeNightwing(self):
		return self.execute(OrionIntegration.AddonNightwing)

	@classmethod
	def executePov(self):
		return self.execute(OrionIntegration.AddonPov)

	@classmethod
	def executeUmbrella(self):
		return self.execute(OrionIntegration.AddonUmbrella)

	@classmethod
	def executeKingPin(self):
		return self.execute(OrionIntegration.AddonKingPin)

	@classmethod
	def executeEzra(self):
		return self.execute(OrionIntegration.AddonEzra)

	@classmethod
	def executeGenesis(self):
		return self.execute(OrionIntegration.AddonGenesis)

	@classmethod
	def executeExodus(self):
		return self.execute(OrionIntegration.AddonExodus)

	@classmethod
	def executeExodusRedux(self):
		return self.execute(OrionIntegration.AddonExodusRedux)

	@classmethod
	def executeNeptuneRising(self):
		return self.execute(OrionIntegration.AddonNeptuneRising)

	@classmethod
	def executeDeathStreams(self):
		return self.execute(OrionIntegration.AddonDeathStreams)

	@classmethod
	def executeBoomMovies(self):
		return self.execute(OrionIntegration.AddonBoomMovies)

	@classmethod
	def executeContinuum(self):
		return self.execute(OrionIntegration.AddonContinuum)

	@classmethod
	def executeMarauder(self):
		return self.execute(OrionIntegration.AddonMarauder)

	@classmethod
	def executePatriot(self):
		return self.execute(OrionIntegration.AddonPatriot)

	@classmethod
	def executeAsguard(self):
		return self.execute(OrionIntegration.AddonAsguard)

	@classmethod
	def executeAsgard(self):
		return self.execute(OrionIntegration.AddonAsgard)

	@classmethod
	def executeTheCrew(self):
		return self.execute(OrionIntegration.AddonTheCrew)

	@classmethod
	def executeChainsGenocide(self):
		return self.execute(OrionIntegration.AddonChainsGenocide)

	@classmethod
	def executeKodiVerse(self):
		return self.execute(OrionIntegration.AddonKodiVerse)

	@classmethod
	def executeOpenScrapers(self):
		return self.execute(OrionIntegration.AddonOpenScrapers)

	@classmethod
	def executeLambdaScrapers(self):
		return self.execute(OrionIntegration.AddonLambdaScrapers)

	@classmethod
	def executeFenomScrapers(self):
		return self.execute(OrionIntegration.AddonFenomScrapers)

	@classmethod
	def executeNightwingScrapers(self):
		return self.execute(OrionIntegration.AddonNightwingScrapers)

	@classmethod
	def executeCocoScrapers(self):
		return self.execute(OrionIntegration.AddonCocoScrapers)

	@classmethod
	def executeUmbrellaScrapers(self):
		return self.execute(OrionIntegration.AddonUmbrellaScrapers)

	@classmethod
	def executeKingPinScrapers(self):
		return self.execute(OrionIntegration.AddonKingPinScrapers)

	@classmethod
	def executeEzScrapers(self):
		return self.execute(OrionIntegration.AddonEzScrapers)

	@classmethod
	def executeUniversalScrapers(self):
		return self.execute(OrionIntegration.AddonUniversalScrapers)

	@classmethod
	def executeUniversalDebrid(self):
		return self.execute(OrionIntegration.AddonUniversalDebrid)

	@classmethod
	def executeNanScrapers(self):
		return self.execute(OrionIntegration.AddonNanScrapers)

	@classmethod
	def executeEncrypticScrapers(self):
		return self.execute(OrionIntegration.AddonEncrypticScrapers)

	@classmethod
	def executeElementum(self):
		return self.execute(OrionIntegration.AddonElementum)

	@classmethod
	def executeQuasar(self):
		return self.execute(OrionIntegration.AddonQuasar)

	##############################################################################
	# GAIA
	##############################################################################

	def _gaiaInitialize(self):
		self.name = OrionIntegration.AddonGaia
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.gaia'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		self.native = True
		self.files = []
		self.deletes = []

	##############################################################################
	# SEREN
	##############################################################################

	def _serenInitialize(self):
		self.name = OrionIntegration.AddonSeren
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.seren'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		self.reintegrate = False
		self.restart = False
		self.link = OrionSettings.getString('internal.providers', raw = True)
		self.files = []
		self.deletes = []

		self._serenCheck()

	def _serenIntegrate(self):
		OrionTools.executePlugin(addon = self.idPlugin, action = 'externalProviderInstall', parameters = {'url' : self.link}, execute = True)
		self._serenWait()
		return self._integrateSuccess() if self._serenCheck() else self._integrateFailure('Seren provider installation failure')

	def _serenDeintegrate(self):
		OrionTools.executePlugin(addon = self.idPlugin, action = 'externalProviderUninstall', parameters = {'url' : 'Orion'}, execute = True)
		self._serenWait()
		return not self._serenCheck()

	def _serenCheck(self):
		# Manually check if the integrated provider folder exists.
		path = OrionTools.pathJoin(OrionTools.addonProfile(self.idPlugin), 'providers', 'Orion')
		integrated = OrionTools.directoryExists(path)
		current = OrionSettings.getIntegration(self.id)
		if not integrated == current: OrionSettings.setIntegration(self.id, 0 if integrated else '')
		return integrated

	def _serenWait(self):
		OrionInterface.loaderShow()
		for i in range(250): # In case something is wrong, do not wait forever.
			visible = OrionInterface.dialogVisible()
			if not visible:
				for i in range(4): # Wait 2 seconds to make sure the process is finished, because Seren shows multiple dialogs and there is a short time in between where no dialog is showing.
					OrionTools.sleep(0.5)
					visible = OrionInterface.dialogVisible()
					if visible: break
				if not visible: break
			OrionTools.sleep(0.5)
		OrionInterface.loaderHide()

	##############################################################################
	# INCURSION
	##############################################################################

	def _incursionInitialize(self):
		self.name = OrionIntegration.AddonIncursion
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.incursion'
		self.idModule = 'script.module.incursion'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin, self.idModule)

		self.pathPlugin = OrionTools.addonPath(self.idPlugin)
		self.pathModule = OrionTools.addonPath(self.idModule)

		self.pathSettings = OrionTools.pathJoin(self.pathPlugin, 'resources', 'settings.xml')
		self.pathAddon = OrionTools.pathJoin(self.pathModule, 'addon.xml')
		self.pathSources = OrionTools.pathJoin(self.pathModule, 'lib', 'resources', 'lib', 'sources', '__init__.py')
		self.pathOrion = OrionTools.pathJoin(self.pathModule, 'lib', 'resources', 'lib', 'sources', 'orion')
		self.pathOrionoid = OrionTools.pathJoin(self.pathOrion, 'orionoid.py')
		self.pathInit = OrionTools.pathJoin(self.pathOrion, '__init__.py')

		self.files = []
		self.files.append(self.pathSettings)
		self.files.append(self.pathAddon)
		self.files.append(self.pathSources)

		self.deletes = []
		self.deletes.append(self.pathOrion)

	def _incursionIntegrate(self):
		# settings.xml
		data = self._comment(self._content('settings.xml'), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathSettings, '<\s*category\s+label\s*=\s*[\'"]32345[\'"]\s*>', data):
			return self._integrateFailure('Incursion settings integration failure', self.pathSettings)

		# addon.xml
		data = self._comment(self._content('addon.xml') % (OrionTools.addonId(), OrionTools.addonVersion()), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathAddon, '<import\s+addon\s*=\s*[\'"]script\.module\.beautifulsoup4[\'"]\s*\/>', data):
			return self._integrateFailure('Incursion addon metadata integration failure', self.pathAddon)

		# __init__.py
		data = self._comment(self._content('sources.py'), OrionIntegration.LanguagePython, '                    ')
		if not OrionTools.fileInsert(self.pathSources, '\.load_module\(module_name\)', data, validate = True):
			return self._integrateFailure('Incursion sources integration failure', self.pathSources)

		# orionoid.py
		if not OrionTools.directoryExists(self.pathOrion) and not OrionTools.directoryCreate(self.pathOrion):
			return self._integrateFailure('Incursion directory creation error', self.pathOrion)
		if not OrionTools.fileCopy(self._path('orionoid.py'), self.pathOrionoid, overwrite = True):
			return self._integrateFailure('Incursion provider integration failure', self.pathOrionoid)
		if not OrionTools.fileCopy(self._path('module.py'), self.pathInit, overwrite = True):
			return self._integrateFailure('Incursion module integration failure', self.pathInit)

		return self._integrateSuccess()

	##############################################################################
	# PLACENTA
	##############################################################################

	def _placentaInitialize(self):
		self.name = OrionIntegration.AddonPlacenta
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.placenta'
		self.idModule = 'script.module.placenta'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin, self.idModule)

		self.pathPlugin = OrionTools.addonPath(self.idPlugin)
		self.pathModule = OrionTools.addonPath(self.idModule)

		self.pathSettings = OrionTools.pathJoin(self.pathPlugin, 'resources', 'settings.xml')
		self.pathAddon = OrionTools.pathJoin(self.pathModule, 'addon.xml')
		self.pathSources = OrionTools.pathJoin(self.pathModule, 'lib', 'resources', 'lib', 'sources', '__init__.py')
		self.pathOrion = OrionTools.pathJoin(self.pathModule, 'lib', 'resources', 'lib', 'sources', 'orion')
		self.pathOrionoid = OrionTools.pathJoin(self.pathOrion, 'orionoid.py')
		self.pathInit = OrionTools.pathJoin(self.pathOrion, '__init__.py')

		self.files = []
		self.files.append(self.pathSettings)
		self.files.append(self.pathAddon)
		self.files.append(self.pathSources)

		self.deletes = []
		self.deletes.append(self.pathOrion)

	def _placentaIntegrate(self):
		# settings.xml
		data = self._comment(self._content('settings.xml'), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathSettings, '<\s*category\s+label\s*=\s*[\'"]32345[\'"]\s*>', data):
			return self._integrateFailure('Placenta settings integration failure', self.pathSettings)

		# addon.xml
		data = self._comment(self._content('addon.xml') % (OrionTools.addonId(), OrionTools.addonVersion()), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathAddon, '<import\s+addon\s*=\s*[\'"]script\.module\.beautifulsoup4[\'"]\s*\/>', data):
			return self._integrateFailure('Placenta addon metadata integration failure', self.pathAddon)

		# __init__.py
		data = self._comment(self._content('sources.py'), OrionIntegration.LanguagePython, '                    ')
		if not OrionTools.fileInsert(self.pathSources, '\.load_module\(module_name\)', data, validate = True):
			return self._integrateFailure('Placenta sources integration failure', self.pathSources)

		# orionoid.py
		if not OrionTools.directoryExists(self.pathOrion) and not OrionTools.directoryCreate(self.pathOrion):
			return self._integrateFailure('Placenta directory creation error', self.pathOrion)
		if not OrionTools.fileCopy(self._path('orionoid.py'), self.pathOrionoid, overwrite = True):
			return self._integrateFailure('Placenta provider integration failure', self.pathOrionoid)
		if not OrionTools.fileCopy(self._path('module.py'), self.pathInit, overwrite = True):
			return self._integrateFailure('Placenta module integration failure', self.pathInit)

		return self._integrateSuccess()

	##############################################################################
	# COVENANT
	##############################################################################

	def _covenantInitialize(self):
		self.name = OrionIntegration.AddonCovenant
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.covenant'
		self.idModule = 'script.module.covenant'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin, self.idModule)

		self.pathPlugin = OrionTools.addonPath(self.idPlugin)
		self.pathModule = OrionTools.addonPath(self.idModule)

		self.pathSettings = OrionTools.pathJoin(self.pathPlugin, 'resources', 'settings.xml')
		self.pathAddon = OrionTools.pathJoin(self.pathModule, 'addon.xml')
		self.pathSources = OrionTools.pathJoin(self.pathModule, 'lib', 'resources', 'lib', 'sources', '__init__.py')
		self.pathOrion = OrionTools.pathJoin(self.pathModule, 'lib', 'resources', 'lib', 'sources', 'orion')
		self.pathOrionoid = OrionTools.pathJoin(self.pathOrion, 'orionoid.py')
		self.pathInit = OrionTools.pathJoin(self.pathOrion, '__init__.py')

		self.files = []
		self.files.append(self.pathSettings)
		self.files.append(self.pathAddon)
		self.files.append(self.pathSources)

		self.deletes = []
		self.deletes.append(self.pathOrion)

	def _covenantIntegrate(self):
		# settings.xml
		data = self._comment(self._content('settings.xml'), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathSettings, '<\s*category\s+label\s*=\s*[\'"]32345[\'"]\s*>', data):
			return self._integrateFailure('Covenant settings integration failure', self.pathSettings)

		# addon.xml
		data = self._comment(self._content('addon.xml') % (OrionTools.addonId(), OrionTools.addonVersion()), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathAddon, '<import\s+addon\s*=\s*[\'"]xbmc\.python[\'"].*?\/>', data):
			return self._integrateFailure('Covenant addon metadata integration failure', self.pathAddon)

		# __init__.py
		data = self._comment(self._content('sources.py'), OrionIntegration.LanguagePython, '                    ')
		if not OrionTools.fileInsert(self.pathSources, '\.load_module\(module_name\)', data, validate = True):
			return self._integrateFailure('Covenant sources integration failure', self.pathSources)

		# orionoid.py
		if not OrionTools.directoryExists(self.pathOrion) and not OrionTools.directoryCreate(self.pathOrion):
			return self._integrateFailure('Covenant directory creation error', self.pathOrion)
		if not OrionTools.fileCopy(self._path('orionoid.py'), self.pathOrionoid, overwrite = True):
			return self._integrateFailure('Covenant provider integration failure', self.pathOrionoid)
		if not OrionTools.fileCopy(self._path('module.py'), self.pathInit, overwrite = True):
			return self._integrateFailure('Covenant module integration failure', self.pathInit)

		return self._integrateSuccess()

	##############################################################################
	# MAGICALITY
	##############################################################################

	def _magicalityInitialize(self):
		self.name = OrionIntegration.AddonMagicality
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.magicality'
		self.idModule = 'script.module.magicality'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin, self.idModule)

		self.pathPlugin = OrionTools.addonPath(self.idPlugin)
		self.pathModule = OrionTools.addonPath(self.idModule)

		self.pathSettings = OrionTools.pathJoin(self.pathPlugin, 'resources', 'settings.xml')
		self.pathAddon = OrionTools.pathJoin(self.pathModule, 'addon.xml')
		self.pathSources = OrionTools.pathJoin(self.pathModule, 'lib', 'resources', 'lib', 'sources', '__init__.py')
		self.pathOrion = OrionTools.pathJoin(self.pathModule, 'lib', 'resources', 'lib', 'sources', 'orion')
		self.pathOrionoid = OrionTools.pathJoin(self.pathOrion, 'orionoid.py')
		self.pathInit = OrionTools.pathJoin(self.pathOrion, '__init__.py')

		self.files = []
		self.files.append(self.pathSettings)
		self.files.append(self.pathAddon)
		self.files.append(self.pathSources)

		self.deletes = []
		self.deletes.append(self.pathOrion)

	def _magicalityIntegrate(self):
		# settings.xml
		data = self._comment(self._content('settings.xml'), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathSettings, '<\s*category\s+label\s*=\s*[\'"]32345[\'"]\s*>', data):
			return self._integrateFailure('Magicality settings integration failure', self.pathSettings)

		# addon.xml
		data = self._comment(self._content('addon.xml') % (OrionTools.addonId(), OrionTools.addonVersion()), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathAddon, '<import\s+addon\s*=\s*[\'"]xbmc\.python[\'"].*?\/>', data):
			return self._integrateFailure('Magicality addon metadata integration failure', self.pathAddon)

		# __init__.py
		data = self._comment(self._content('sources.py'), OrionIntegration.LanguagePython, '                    ')
		if not OrionTools.fileInsert(self.pathSources, '\.load_module\(module_name\)', data, validate = True):
			return self._integrateFailure('Magicality sources integration failure', self.pathSources)

		# orionoid.py
		if not OrionTools.directoryExists(self.pathOrion) and not OrionTools.directoryCreate(self.pathOrion):
			return self._integrateFailure('Magicality directory creation error', self.pathOrion)
		if not OrionTools.fileCopy(self._path('orionoid.py'), self.pathOrionoid, overwrite = True):
			return self._integrateFailure('Magicality provider integration failure', self.pathOrionoid)
		if not OrionTools.fileCopy(self._path('module.py'), self.pathInit, overwrite = True):
			return self._integrateFailure('Magicality module integration failure', self.pathInit)

		return self._integrateSuccess()

	##############################################################################
	# THEOATH
	##############################################################################

	def _theOathInitialize(self):
		self.name = OrionIntegration.AddonTheOath
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.theoath'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		self.native = True
		self.files = []
		self.deletes = []

	##############################################################################
	# APOCALYPSE720
	##############################################################################

	def _apocalypse720Initialize(self):
		self.name = OrionIntegration.AddonApocalypse720
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.apocalypse720'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		self.native = True
		self.files = []
		self.deletes = []

	##############################################################################
	# NOLIVESMATTER
	##############################################################################

	def _noLivesMatterInitialize(self):
		self.name = OrionIntegration.AddonNoLivesMatter
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.nlm'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		self.native = True
		self.files = []
		self.deletes = []

	##############################################################################
	# YODA
	##############################################################################

	def _yodaInitialize(self):
		self.name = OrionIntegration.AddonYoda
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.yoda'
		self.idModule = 'script.module.yoda'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin, self.idModule)

		self.pathPlugin = OrionTools.addonPath(self.idPlugin)
		self.pathModule = OrionTools.addonPath(self.idModule)

		self.pathSettings = OrionTools.pathJoin(self.pathPlugin, 'resources', 'settings.xml')
		self.pathAddon = OrionTools.pathJoin(self.pathModule, 'addon.xml')
		self.pathSources = OrionTools.pathJoin(self.pathModule, 'lib', 'resources', 'lib', 'sources', '__init__.py')
		self.pathOrion = OrionTools.pathJoin(self.pathModule, 'lib', 'resources', 'lib', 'sources', 'orion')
		self.pathOrionoid = OrionTools.pathJoin(self.pathOrion, 'orionoid.py')
		self.pathInit = OrionTools.pathJoin(self.pathOrion, '__init__.py')

		self.files = []
		self.files.append(self.pathSettings)
		self.files.append(self.pathAddon)
		self.files.append(self.pathSources)

		self.deletes = []
		self.deletes.append(self.pathOrion)

	def _yodaIntegrate(self):
		# settings.xml
		data = self._comment(self._content('settings.xml'), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathSettings, '<\s*category\s+label\s*=\s*[\'"]32345[\'"]\s*>', data):
			return self._integrateFailure('Yoda settings integration failure', self.pathSettings)

		# addon.xml
		data = self._comment(self._content('addon.xml') % (OrionTools.addonId(), OrionTools.addonVersion()), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathAddon, '<import\s+addon\s*=\s*[\'"]xbmc\.python[\'"].*?\/>', data):
			return self._integrateFailure('Yoda addon metadata integration failure', self.pathAddon)

		# __init__.py
		data = self._comment(self._content('sources.py'), OrionIntegration.LanguagePython, '                    ')
		if not OrionTools.fileInsert(self.pathSources, '\.load_module\(module_name\)', data, validate = True):
			return self._integrateFailure('Yoda sources integration failure', self.pathSources)

		# orionoid.py
		if not OrionTools.directoryExists(self.pathOrion) and not OrionTools.directoryCreate(self.pathOrion):
			return self._integrateFailure('Yoda directory creation error', self.pathOrion)
		if not OrionTools.fileCopy(self._path('orionoid.py'), self.pathOrionoid, overwrite = True):
			return self._integrateFailure('Yoda provider integration failure', self.pathOrionoid)
		if not OrionTools.fileCopy(self._path('module.py'), self.pathInit, overwrite = True):
			return self._integrateFailure('Yoda module integration failure', self.pathInit)

		return self._integrateSuccess()

	##############################################################################
	# BODIE
	##############################################################################

	def _bodieInitialize(self):
		self.name = OrionIntegration.AddonBodie
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.bodiekodi'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		self.scrapers = OrionIntegration.AddonLambdaScrapers
		self.files = []
		self.deletes = []

	##############################################################################
	# NYMERIA
	##############################################################################

	def _nymeriaInitialize(self):
		self.name = OrionIntegration.AddonNymeria
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.nymeria'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		self.scrapers = OrionIntegration.AddonUniversalScrapers
		self.files = []
		self.deletes = []

	##############################################################################
	# FEN
	##############################################################################

	def _fenInitialize(self):
		self.name = OrionIntegration.AddonFen
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.fen'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		#self.scrapers = OrionIntegration.AddonFenomScrapers
		self.scrapers = OrionIntegration.AddonCocoScrapers
		self.files = []
		self.deletes = []

	##############################################################################
	# NIGHTWING
	##############################################################################

	def _nightwingInitialize(self):
		self.name = OrionIntegration.AddonNightwing
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.nightwing'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		self.scrapers = OrionIntegration.AddonNightwingScrapers
		self.files = []
		self.deletes = []

	##############################################################################
	# UMBRELLA
	##############################################################################

	def _umbrellaInitialize(self):
		self.name = OrionIntegration.AddonUmbrella
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.umbrella'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		#self.scrapers = OrionIntegration.AddonUmbrellaScrapers
		self.scrapers = OrionIntegration.AddonCocoScrapers
		self.files = []
		self.deletes = []

	##############################################################################
	# KINGPIN
	##############################################################################

	def _kingPinInitialize(self):
		self.name = OrionIntegration.AddonKingPin
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.kingpin'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		self.scrapers = OrionIntegration.AddonKingPinScrapers
		self.files = []
		self.deletes = []

	##############################################################################
	# EZRA
	##############################################################################

	def _ezraInitialize(self):
		self.name = OrionIntegration.AddonEzra
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.ezra'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		self.scrapers = OrionIntegration.AddonEzScrapers
		self.files = []
		self.deletes = []

	##############################################################################
	# VENOM
	##############################################################################

	def _venomInitialize(self):
		self.name = OrionIntegration.AddonVenom
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.venom'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		self.scrapers = OrionIntegration.AddonFenomScrapers
		self.files = []
		self.deletes = []

	##############################################################################
	# POV SCRAPERS
	##############################################################################

	def _povInitialize(self):
		self.name = OrionIntegration.AddonPov
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.pov'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		self.versionNumber = int(re.sub('[^0-9]', '', self.version)) if self.version else None

		self.pathPlugin = OrionTools.addonPath(self.idPlugin)

		self.pathSettings = OrionTools.pathJoin(self.pathPlugin, 'resources', 'settings.xml')
		self.pathAddon = OrionTools.pathJoin(self.pathPlugin, 'addon.xml')

		self.pathScrapers = OrionTools.pathJoin(self.pathPlugin, 'resources', 'lib', 'fenom', 'sourcesdir')
		self.pathOrionoid = OrionTools.pathJoin(self.pathScrapers, 'orionoid.py')
		self.pathOrionHoster = OrionTools.pathJoin(self.pathScrapers, 'hosters', 'orionhoster.py')
		self.pathOrionTorrent = OrionTools.pathJoin(self.pathScrapers, 'torrents', 'oriontorrent.py')

		self.files = []
		self.files.append(self.pathSettings)
		self.files.append(self.pathAddon)

		self.deletes = []
		self.deletes.append(self.pathOrionoid)
		self.deletes.append(self.pathOrionHoster)
		self.deletes.append(self.pathOrionTorrent)

	def _povIntegrate(self):
		# settings.xml

		# Currently it seems that hosters are not supported in POV.
		# It does not use any resolver addon, and the hoster ssupport over debrid does not seem to work yet.
		# The hoster settings (eg: pm.hoster.enabled) are all disabled and hidden.
		# This can be reenabled in the future once POV hass proper hosster support.
		#data = self._comment(self._content('settings1.xml'), OrionIntegration.LanguageXml, '\t\t')
		#if not OrionTools.fileInsert(self.pathSettings, '<category\s*label\s*=\s*[\'"]Sources[\'"]>.*?\/>.*?\n(?=\s*<\/category>)', data, flags = re.S):
		#	return self._integrateFailure('POV hoster settings integration failure', self.pathSettings)

		data = self._comment(self._content('settings2.xml'), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathSettings, '<category\s*label\s*=\s*[\'"]Sources[\'"]>.*?<setting.*?\s*label\s*=\s*[\'"]Torrents[\'"].*?\/>', data, flags = re.S):
			return self._integrateFailure('POV torrent settings integration failure', self.pathSettings)

		# addon.xml
		data = self._comment(self._content('addon.xml') % (OrionTools.addonId(), OrionTools.addonVersion()), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathAddon, '<requires.*?(\r?\n?)\s*<\/requires>', data, flags = OrionTools.RegexDotAll, group = 1):
			return self._integrateFailure('POV addon metadata integration failure', self.pathAddon)

		# orionoid.py
		if not OrionTools.fileCopy(self._path('orionoid.py'), self.pathOrionoid, overwrite = True):
			return self._integrateFailure('POV provider integration failure', self.pathOrionoid)
		if not OrionTools.fileCopy(self._path('orionhoster.py'), self.pathOrionHoster, overwrite = True):
			return self._integrateFailure('POV hoster provider integration failure', self.pathOrionHoster)
		if not OrionTools.fileCopy(self._path('oriontorrent.py'), self.pathOrionTorrent, overwrite = True):
			return self._integrateFailure('POV torrent provider integration failure', self.pathOrionTorrent)

		return self._integrateSuccess()

	##############################################################################
	# SCRUBS
	##############################################################################

	def _scrubsInitialize(self):
		self.name = OrionIntegration.AddonScrubs
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.scrubsv2'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)

		self.pathPlugin = OrionTools.addonPath(self.idPlugin)

		self.pathSettings = OrionTools.pathJoin(self.pathPlugin, 'resources', 'settings.xml')
		self.pathAddon = OrionTools.pathJoin(self.pathPlugin, 'addon.xml')
		self.pathSources = OrionTools.pathJoin(self.pathPlugin, 'resources', 'lib', 'sources', '__init__.py')
		self.pathOrionoid = OrionTools.pathJoin(self.pathPlugin, 'resources', 'lib', 'sources', 'working', 'orionoid.py')

		self.files = []
		self.files.append(self.pathSettings)
		self.files.append(self.pathAddon)
		self.files.append(self.pathSources)

		self.deletes = []
		self.deletes.append(self.pathOrionoid)

	def _scrubsIntegrate(self):
		# settings.xml
		data = self._comment(self._content('settings.xml'), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathSettings, '<\s*setting\s*.*?\s*label\s*=\s*"Enable\s*All.*?<setting type="sep".*?\/>', data, flags = re.S | re.I):
			return self._integrateFailure('Scrubs settings integration failure', self.pathSettings)

		# addon.xml
		data = self._comment(self._content('addon.xml') % (OrionTools.addonId(), OrionTools.addonVersion()), OrionIntegration.LanguageXml, '        ')
		if not OrionTools.fileInsert(self.pathAddon, '.*<import\s+.*?\/>', data, flags = re.S | re.I):
			return self._integrateFailure('Scrubs addon metadata integration failure', self.pathAddon)

		# __init__.py
		data = self._comment(self._content('sources1.py'), OrionIntegration.LanguagePython, '                ')
		if not OrionTools.fileInsert(self.pathSources, '\.load_module\(module_name\)', data, validate = True):
			return self._integrateFailure('Scrubs sources integration failure', self.pathSources)
		data = self._comment(self._content('sources2.py'), OrionIntegration.LanguagePython, '    ')
		if not OrionTools.fileInsert(self.pathSources, 'return\s*sourceDict', data, validate = True, replace = True):
			return self._integrateFailure('Scrubs sources integration failure', self.pathSources)

		# orionoid.py
		if not OrionTools.fileCopy(self._path('orionoid.py'), self.pathOrionoid, overwrite = True):
			return self._integrateFailure('Scrubs provider integration failure', self.pathOrionoid)

		return self._integrateSuccess()

	##############################################################################
	# MEDUSA
	##############################################################################

	def _medusaInitialize(self):
		self.name = OrionIntegration.AddonMedusa
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.Medusa'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		self.scrapers = OrionIntegration.AddonUniversalScrapers
		self.files = []
		self.deletes = []

	##############################################################################
	# MERCURY
	##############################################################################

	def _mercuryInitialize(self):
		self.name = OrionIntegration.AddonMercury
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.Mercury'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		self.scrapers = OrionIntegration.AddonUniversalScrapers
		self.files = []
		self.deletes = []

	##############################################################################
	# DECEIT
	##############################################################################

	def _deceitInitialize(self):
		self.name = OrionIntegration.AddonDeceit
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.deceit'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		self.scrapers = OrionIntegration.AddonUniversalScrapers
		self.files = []
		self.deletes = []

	##############################################################################
	# GENISIS
	##############################################################################

	def _genesisInitialize(self):
		self.name = OrionIntegration.AddonGenesis
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.genesis'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)

		self.pathPlugin = OrionTools.addonPath(self.idPlugin)

		self.pathSettings = OrionTools.pathJoin(self.pathPlugin, 'resources', 'settings.xml')
		self.pathAddon = OrionTools.pathJoin(self.pathPlugin, 'addon.xml')
		self.pathSources = OrionTools.pathJoin(self.pathPlugin, 'resources', 'lib', 'sources', '__init__.py')
		self.pathOrion = OrionTools.pathJoin(self.pathPlugin, 'resources', 'lib', 'sources', 'orion')
		self.pathOrionoid = OrionTools.pathJoin(self.pathOrion, 'orionoid.py')
		self.pathInit = OrionTools.pathJoin(self.pathOrion, '__init__.py')

		self.files = []
		self.files.append(self.pathSettings)
		self.files.append(self.pathAddon)
		self.files.append(self.pathSources)

		self.deletes = []
		self.deletes.append(self.pathOrion)

	def _genesisIntegrate(self):
		# settings.xml
		data = self._comment(self._content('settings.xml'), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathSettings, '<\s*category\s*label\s*=\s*"Hosts"\s*>.*?<\s*\/\s*category\s*>', data, flags = re.S):
			return self._integrateFailure('Genesis settings integration failure', self.pathSettings)

		# addon.xml
		data = self._comment(self._content('addon.xml') % (OrionTools.addonId(), OrionTools.addonVersion()), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathAddon, '<import\s+addon\s*=\s*[\'"]xbmc\.python[\'"].*?\/>', data):
			return self._integrateFailure('Genesis addon metadata integration failure', self.pathAddon)

		# __init__.py
		data = self._comment(self._content('sources.py'), OrionIntegration.LanguagePython, '                    ')
		if not OrionTools.fileInsert(self.pathSources, '\.load_module\(module_name\)', data, validate = True):
			return self._integrateFailure('Genesis sources integration failure', self.pathSources)

		# orionoid.py
		if not OrionTools.directoryExists(self.pathOrion) and not OrionTools.directoryCreate(self.pathOrion):
			return self._integrateFailure('Genesis directory creation error', self.pathOrion)
		if not OrionTools.fileCopy(self._path('orionoid.py'), self.pathOrionoid, overwrite = True):
			return self._integrateFailure('Genesis provider integration failure', self.pathOrionoid)
		if not OrionTools.fileCopy(self._path('module.py'), self.pathInit, overwrite = True):
			return self._integrateFailure('Genesis module integration failure', self.pathInit)

		return self._integrateSuccess()

	##############################################################################
	# EXODUS
	##############################################################################

	def _exodusInitialize(self):
		self.name = OrionIntegration.AddonExodus
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.exodus'

		# KodiBae has created a new fork of Exodus with the same ID as older versions, but has a different name.
		# The new fork supports Orion nativley.
		# https://github.com/kodibae/repository.kodibae/tree/master/plugin.video.exodus
		try: native = 'vpn' in OrionTools.addonName(self.idPlugin).lower()
		except: native = False

		if native:
			self.idSettings = self.idPlugin
			self.version = self._version(self.idPlugin)
			self.native = True
			self.files = []
			self.deletes = []
		else:
			self.idModule = 'script.module.exoscrapers'
			self.idSettings = self.idModule
			self.version = self._version(self.idPlugin, self.idModule)

			self.pathPlugin = OrionTools.addonPath(self.idPlugin)
			self.pathModule = OrionTools.addonPath(self.idModule)

			self.pathSettings = OrionTools.pathJoin(self.pathModule, 'resources', 'settings.xml')
			self.pathAddon = OrionTools.pathJoin(self.pathModule, 'addon.xml')
			self.pathScrapers = OrionTools.pathJoin(self.pathModule, 'lib', 'exoscrapers', '__init__.py')
			self.pathSources = OrionTools.pathJoin(self.pathModule, 'lib', 'exoscrapers', 'sources_exoscrapers', '__init__.py')
			self.pathOrion = OrionTools.pathJoin(self.pathModule, 'lib', 'exoscrapers', 'sources_exoscrapers', 'orion')
			self.pathOrionoid = OrionTools.pathJoin(self.pathOrion, 'orionoid.py')
			self.pathInit = OrionTools.pathJoin(self.pathOrion, '__init__.py')

			self.files = []
			self.files.append(self.pathSettings)
			self.files.append(self.pathAddon)
			self.files.append(self.pathSources)

			self.deletes = []
			self.deletes.append(self.pathOrion)

	def _exodusIntegrate(self):
		# settings.xml
		data = self._comment(self._content('settings.xml'), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathSettings, '<\/category>', data):
			return self._integrateFailure('Exodus settings integration failure', self.pathSettings)

		# addon.xml
		data = self._comment(self._content('addon.xml') % (OrionTools.addonId(), OrionTools.addonVersion()), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathAddon, '<import\s+addon\s*=\s*[\'"]xbmc\.python[\'"].*?\/>', data):
			return self._integrateFailure('Exodus addon metadata integration failure', self.pathAddon)

		# __init__.py
		data = self._comment(self._content('scrapers.py'), OrionIntegration.LanguagePython, '    ')
		if not OrionTools.fileInsert(self.pathScrapers, 'return sourceDict', data, validate = True):
			return self._integrateFailure('Yoda scrapers integration failure', self.pathScrapers)

		# __init__.py
		data = self._comment(self._content('sources.py'), OrionIntegration.LanguagePython)
		if not OrionTools.fileInsert(self.pathSources, 'all_providers\s*=\s*\[\]', data, validate = True):
			return self._integrateFailure('Exodus sources integration failure', self.pathSources)

		# orionoid.py
		if not OrionTools.directoryExists(self.pathOrion) and not OrionTools.directoryCreate(self.pathOrion):
			return self._integrateFailure('Exodus directory creation error', self.pathOrion)
		if not OrionTools.fileCopy(self._path('orionoid.py'), self.pathOrionoid, overwrite = True):
			return self._integrateFailure('Exodus provider integration failure', self.pathOrionoid)
		if not OrionTools.fileCopy(self._path('module.py'), self.pathInit, overwrite = True):
			return self._integrateFailure('Exodus module integration failure', self.pathInit)

		return self._integrateSuccess()

	##############################################################################
	# EXODUS REDUX
	##############################################################################

	def _exodusReduxInitialize(self):
		self.name = OrionIntegration.AddonExodusRedux
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.exodusredux'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		self.scrapers = OrionIntegration.AddonOpenScrapers
		self.files = []
		self.deletes = []

	##############################################################################
	# NEPTUNE RISING
	##############################################################################

	def _neptuneRisingInitialize(self):
		self.name = OrionIntegration.AddonNeptuneRising
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.neptune'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		self.scrapers = OrionIntegration.AddonUniversalScrapers
		self.files = []
		self.deletes = []

	##############################################################################
	# DEATH STREAMS
	##############################################################################

	def _deathStreamsInitialize(self):
		self.name = OrionIntegration.AddonDeathStreams
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.blamo'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)

		self.pathPlugin = OrionTools.addonPath(self.idPlugin)

		self.pathAddon = OrionTools.pathJoin(self.pathPlugin, 'addon.xml')
		self.pathOrionoid = OrionTools.pathJoin(self.pathPlugin, 'scrapers', 'orionoid.py')

		self.files = []
		self.files.append(self.pathAddon)

		self.deletes = []
		self.deletes.append(self.pathOrionoid)

	def _deathStreamsIntegrate(self):
		# addon.xml
		data = self._comment(self._content('addon.xml') % (OrionTools.addonId(), OrionTools.addonVersion()), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathAddon, '<import\s+addon\s*=\s*[\'"]script\.module\.dateutil[\'"]\s*\/>', data):
			return self._integrateFailure('Death Streams addon metadata integration failure', self.pathAddon)

		# orionoid.py
		if not OrionTools.fileCopy(self._path('orionoid.py'), self.pathOrionoid, overwrite = True):
			return self._integrateFailure('Death Streams provider integration failure', self.pathOrionoid)

		return self._integrateSuccess()

	##############################################################################
	# BOOM MOVIES
	##############################################################################

	def _boomMoviesInitialize(self):
		self.name = OrionIntegration.AddonBoomMovies
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.BoomMovies'
		self.idModule = 'script.module.BoomMovies'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin, self.idModule)

		self.pathPlugin = OrionTools.addonPath(self.idPlugin)
		self.pathModule = OrionTools.addonPath(self.idModule)

		self.pathSettings = OrionTools.pathJoin(self.pathPlugin, 'resources', 'settings.xml')
		self.pathAddon = OrionTools.pathJoin(self.pathModule, 'addon.xml')
		self.pathSources = OrionTools.pathJoin(self.pathModule, 'lib', 'resources', 'lib', 'sources', '__init__.py')
		self.pathOrion = OrionTools.pathJoin(self.pathModule, 'lib', 'resources', 'lib', 'sources', 'orion')
		self.pathOrionoid = OrionTools.pathJoin(self.pathOrion, 'orionoid.py')
		self.pathInit = OrionTools.pathJoin(self.pathOrion, '__init__.py')

		self.files = []
		self.files.append(self.pathSettings)
		self.files.append(self.pathAddon)
		self.files.append(self.pathSources)

		self.deletes = []
		self.deletes.append(self.pathOrion)

	def _boomMoviesIntegrate(self):
		# settings.xml
		data = self._comment(self._content('settings.xml'), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathSettings, '<\s*category\s+label\s*=\s*[\'"]32345[\'"]\s*>', data):
			return self._integrateFailure('BoomMovies settings integration failure', self.pathSettings)

		# addon.xml
		data = self._comment(self._content('addon.xml') % (OrionTools.addonId(), OrionTools.addonVersion()), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathAddon, '<import\s+addon\s*=\s*[\'"]xbmc\.python[\'"].*?\/>', data):
			return self._integrateFailure('BoomMovies addon metadata integration failure', self.pathAddon)

		# __init__.py
		data = self._comment(self._content('sources1.py'), OrionIntegration.LanguagePython, '                    ')
		if not OrionTools.fileInsert(self.pathSources, '\.load_module\(module_name\)', data, validate = True):
			return self._integrateFailure('BoomMovies sources integration failure', self.pathSources)
		data = self._comment(self._content('sources2.py'), OrionIntegration.LanguagePython, '        ')
		if not OrionTools.fileInsert(self.pathSources, 'return\s*sourceDict', data, validate = True, replace = True):
			return self._integrateFailure('BoomMovies sources integration failure', self.pathSources)

		# orionoid.py
		if not OrionTools.directoryExists(self.pathOrion) and not OrionTools.directoryCreate(self.pathOrion):
			return self._integrateFailure('BoomMovies directory creation error', self.pathOrion)
		if not OrionTools.fileCopy(self._path('orionoid.py'), self.pathOrionoid, overwrite = True):
			return self._integrateFailure('BoomMovies provider integration failure', self.pathOrionoid)
		if not OrionTools.fileCopy(self._path('module.py'), self.pathInit, overwrite = True):
			return self._integrateFailure('BoomMovies module integration failure', self.pathInit)

		return self._integrateSuccess()

	##############################################################################
	# CONTINUUM
	##############################################################################

	def _continuumInitialize(self):
		self.name = OrionIntegration.AddonContinuum
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.cmovies'
		self.idModule = 'script.module.cmovies'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin, self.idModule)

		self.pathPlugin = OrionTools.addonPath(self.idPlugin)
		self.pathModule = OrionTools.addonPath(self.idModule)

		self.pathSettings = OrionTools.pathJoin(self.pathPlugin, 'resources', 'settings.xml')
		self.pathAddon = OrionTools.pathJoin(self.pathModule, 'addon.xml')
		self.pathSources = OrionTools.pathJoin(self.pathModule, 'lib', 'resources', 'lib', 'sources', '__init__.py')
		self.pathOrion = OrionTools.pathJoin(self.pathModule, 'lib', 'resources', 'lib', 'sources', 'orion')
		self.pathOrionoid = OrionTools.pathJoin(self.pathOrion, 'orionoid.py')
		self.pathInit = OrionTools.pathJoin(self.pathOrion, '__init__.py')

		self.files = []
		self.files.append(self.pathSettings)
		self.files.append(self.pathAddon)
		self.files.append(self.pathSources)

		self.deletes = []
		self.deletes.append(self.pathOrion)

	def _continuumIntegrate(self):
		# settings.xml
		data = self._comment(self._content('settings.xml'), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathSettings, '<\s*category\s+label\s*=\s*[\'"]32345[\'"]\s*>', data):
			return self._integrateFailure('Continuum settings integration failure', self.pathSettings)

		# addon.xml
		data = self._comment(self._content('addon.xml') % (OrionTools.addonId(), OrionTools.addonVersion()), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathAddon, '<import\s+addon\s*=\s*[\'"]xbmc\.python[\'"].*?\/>', data):
			return self._integrateFailure('Continuum addon metadata integration failure', self.pathAddon)

		# __init__.py
		data = self._comment(self._content('sources.py'), OrionIntegration.LanguagePython, '                    ')
		if not OrionTools.fileInsert(self.pathSources, '\.load_module\(module_name\)', data, validate = True):
			return self._integrateFailure('Continuum sources integration failure', self.pathSources)

		# orionoid.py
		if not OrionTools.directoryExists(self.pathOrion) and not OrionTools.directoryCreate(self.pathOrion):
			return self._integrateFailure('Continuum directory creation error', self.pathOrion)
		if not OrionTools.fileCopy(self._path('orionoid.py'), self.pathOrionoid, overwrite = True):
			return self._integrateFailure('Continuum provider integration failure', self.pathOrionoid)
		if not OrionTools.fileCopy(self._path('module.py'), self.pathInit, overwrite = True):
			return self._integrateFailure('Continuum module integration failure', self.pathInit)

		return self._integrateSuccess()

	##############################################################################
	# MARAUDER
	##############################################################################

	def _marauderInitialize(self):
		self.name = OrionIntegration.AddonMarauder
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.marauder'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		self.native = True
		self.files = []
		self.deletes = []

	##############################################################################
	# PATRIOT
	##############################################################################

	def _patriotInitialize(self):
		self.name = OrionIntegration.AddonPatriot
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.patriot'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		self.native = True
		self.files = []
		self.deletes = []

	##############################################################################
	# ASGUARD
	##############################################################################

	def _asguardInitialize(self):
		self.name = OrionIntegration.AddonAsguard
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.asguard'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		self.native = True
		self.files = []
		self.deletes = []

	##############################################################################
	# ASGARD
	##############################################################################

	def _asgardInitialize(self):
		self.name = OrionIntegration.AddonAsgard
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.asgard'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)

		self.pathPlugin = OrionTools.addonPath(self.idPlugin)

		self.pathAddon = OrionTools.pathJoin(self.pathPlugin, 'addon.xml')
		self.pathSettings = OrionTools.pathJoin(self.pathPlugin, 'resources', 'settings.xml')
		self.pathOrionoid = OrionTools.pathJoin(self.pathPlugin, 'resources', 'sources', 'Orion.py') # Use "Orion", since the name is displayed in the GUI stream list.

		self.files = []
		self.files.append(self.pathAddon)
		self.files.append(self.pathSettings)

		self.deletes = []
		self.deletes.append(self.pathOrionoid)

	def _asgardIntegrate(self):
		# settings.xml
		data = self._comment(self._content('settings1.xml'), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathSettings, 'label\s*=\s*"32256".*?>', data, flags = re.S):
			return self._integrateFailure('Asgard main settings integration failure', self.pathSettings)
		data = self._comment(self._content('settings2.xml'), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathSettings, 'label\s*=\s*"32251".*?(?:movie\s*sources\s*\-\->|id\s*=\s*"fav_movie".*?\/>)', data, flags = re.S | re.I):
			return self._integrateFailure('Asgard movie settings integration failure', self.pathSettings)
		data = self._comment(self._content('settings3.xml'), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathSettings, 'label\s*=\s*".*?tv\s*sources.*?".*?(?:tv\s*sources\-\->|id\s*=\s*"fav=tv".*?\/>)', data, flags = re.S | re.I):
			return self._integrateFailure('Asgard show settings integration failure', self.pathSettings)

		# addon.xml
		data = self._comment(self._content('addon.xml') % (OrionTools.addonId(), OrionTools.addonVersion()), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathAddon, '<requires.*?(\r?\n?)\s*<\/requires>', data, flags = OrionTools.RegexDotAll, group = 1):
			return self._integrateFailure('Asgard addon metadata integration failure', self.pathAddon)

		# Orion.py
		if not OrionTools.fileCopy(self._path('Orion.py'), self.pathOrionoid, overwrite = True):
			return self._integrateFailure('Asgard provider integration failure', self.pathOrionoid)

		return self._integrateSuccess()

	##############################################################################
	# THECREW
	##############################################################################

	def _theCrewInitialize(self):
		self.name = OrionIntegration.AddonTheCrew
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.thecrew'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		self.native = True
		self.files = []
		self.deletes = []

	##############################################################################
	# CHAINSGENOCIDE
	##############################################################################

	def _chainsGenocideInitialize(self):
		self.name = OrionIntegration.AddonChainsGenocide
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.chainsgenocide'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)

		self.pathPlugin = OrionTools.addonPath(self.idPlugin)

		self.pathSettings = OrionTools.pathJoin(self.pathPlugin, 'resources', 'settings.xml')
		self.pathAddon = OrionTools.pathJoin(self.pathPlugin, 'addon.xml')

		self.pathScrapers = OrionTools.pathJoin(self.pathPlugin, 'resources', 'lib', 'jacksparrow', 'sourcesdir')
		self.pathOrionoid = OrionTools.pathJoin(self.pathScrapers, 'orionoid.py')
		self.pathOrionHoster = OrionTools.pathJoin(self.pathScrapers, 'hosters', 'orionhoster.py')
		self.pathOrionTorrent = OrionTools.pathJoin(self.pathScrapers, 'torrents', 'oriontorrent.py')

		self.files = []
		self.files.append(self.pathSettings)
		self.files.append(self.pathAddon)

		self.deletes = []
		self.deletes.append(self.pathOrionoid)
		self.deletes.append(self.pathOrionHoster)
		self.deletes.append(self.pathOrionTorrent)

	def _chainsGenocideIntegrate(self):
		# settings.xml
		data = self._comment(self._content('settings.xml'), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathSettings, '"32345".*?(\r?\n?)\s*<\/category>', data, flags = OrionTools.RegexDotAll, group = 1):
			return self._integrateFailure('Chains Genocide settings integration failure', self.pathSettings)

		# addon.xml
		data = self._comment(self._content('addon.xml') % (OrionTools.addonId(), OrionTools.addonVersion()), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathAddon, '<requires.*?(\r?\n?)\s*<\/requires>', data, flags = OrionTools.RegexDotAll, group = 1):
			return self._integrateFailure('Chains Genocide addon metadata integration failure', self.pathAddon)

		# orionoid.py
		if not OrionTools.fileCopy(self._path('orionoid.py'), self.pathOrionoid, overwrite = True):
			return self._integrateFailure('Chains Genocide provider integration failure', self.pathOrionoid)
		if not OrionTools.fileCopy(self._path('orionhoster.py'), self.pathOrionHoster, overwrite = True):
			return self._integrateFailure('Chains Genocide hoster provider integration failure', self.pathOrionHoster)
		if not OrionTools.fileCopy(self._path('oriontorrent.py'), self.pathOrionTorrent, overwrite = True):
			return self._integrateFailure('Chains Genocide torrent provider integration failure', self.pathOrionTorrent)

		return self._integrateSuccess()

	##############################################################################
	# KODIVERSE
	##############################################################################

	def _kodiVerseInitialize(self):
		self.name = OrionIntegration.AddonKodiVerse
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.KodiVerse'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)

		self.pathPlugin = OrionTools.addonPath(self.idPlugin)

		self.pathAddon = OrionTools.pathJoin(self.pathPlugin, 'addon.xml')
		self.pathSettings = OrionTools.pathJoin(self.pathPlugin, 'resources', 'settings.xml')
		self.pathOrionoid = OrionTools.pathJoin(self.pathPlugin, 'resources', 'sources', 'orionoid.py')

		self.files = []
		self.files.append(self.pathAddon)
		self.files.append(self.pathSettings)

		self.deletes = []
		self.deletes.append(self.pathOrionoid)

	def _kodiVerseIntegrate(self):
		# settings.xml
		data = self._comment(self._content('settings1.xml'), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathSettings, '<!--\s*movie\s*sources\s*-->', data, flags = re.S | re.I):
			return self._integrateFailure('KodiVerse movie provider settings integration failure', self.pathSettings)
		data = self._comment(self._content('settings2.xml'), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathSettings, '<!--\s*tv\s*sources\s*-->', data, flags = re.S | re.I):
			return self._integrateFailure('KodiVerse show provider settings integration failure', self.pathSettings)

		# addon.xml
		data = self._comment(self._content('addon.xml') % (OrionTools.addonId(), OrionTools.addonVersion()), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathAddon, '<requires.*?(\r?\n?)\s*<\/requires>', data, flags = OrionTools.RegexDotAll, group = 1):
			return self._integrateFailure('KodiVerse addon metadata integration failure', self.pathAddon)

		# Orion.py
		if not OrionTools.fileCopy(self._path('orionoid.py'), self.pathOrionoid, overwrite = True):
			return self._integrateFailure('KodiVerse provider integration failure', self.pathOrionoid)

		return self._integrateSuccess()

	##############################################################################
	# OPEN SCRAPERS
	##############################################################################

	def _openScrapersInitialize(self):
		self.name = OrionIntegration.AddonOpenScrapers
		self.id = self.id(self.name)
		self.idPlugin = 'script.module.openscrapers'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		self.versionNumber = int(re.sub('[^0-9]', '', self.version)) if self.version else None

		self.pathPlugin = OrionTools.addonPath(self.idPlugin)

		self.pathSettings = OrionTools.pathJoin(self.pathPlugin, 'resources', 'settings.xml')
		self.pathAddon = OrionTools.pathJoin(self.pathPlugin, 'addon.xml')

		self.pathSources = OrionTools.pathJoin(self.pathPlugin, 'lib', 'openscrapers', '__init__.py')
		self.pathOrion = OrionTools.pathJoin(self.pathPlugin, 'lib', 'openscrapers', 'sources_openscrapers', 'orion')
		self.pathOrionoid = OrionTools.pathJoin(self.pathOrion, 'orionoid.py')
		self.pathInit = OrionTools.pathJoin(self.pathOrion, '__init__.py')

		self.files = []
		self.files.append(self.pathSettings)
		self.files.append(self.pathAddon)
		self.files.append(self.pathSources)
		self.files.append(self.pathInit)

		self.deletes = []
		self.deletes.append(self.pathOrion)

	def _openScrapersIntegrate(self):
		# settings.xml
		data = self._comment(self._content('settings.xml'), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathSettings, '<\s*/\s*category\s*>', data):
			return self._integrateFailure('Open Scrapers settings integration failure', self.pathSettings)

		# __init__.py
		data = self._comment(self._content('sources1.py'), OrionIntegration.LanguagePython, '\t\t\t\t\t')
		if not OrionTools.fileInsert(self.pathSources, '\.load_module\(module_name\)', data, validate = True):
			return self._integrateFailure('Open Scrapers sources integration failure', self.pathSources)
		data = self._comment(self._content('sources2.py'), OrionIntegration.LanguagePython, '\t\t')
		if not OrionTools.fileInsert(self.pathSources, 'return\s*sourceDict', data, validate = True, replace = True):
			return self._integrateFailure('Open Scrapers sources integration failure', self.pathSources)

		# addon.xml
		data = self._comment(self._content('addon.xml') % (OrionTools.addonId(), OrionTools.addonVersion()), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathAddon, '<import\s+addon\s*=\s*[\'"]xbmc\.python[\'"].*?\/>', data):
			return self._integrateFailure('Open Scrapers addon metadata integration failure', self.pathAddon)

		# orionoid.py
		if not OrionTools.directoryExists(self.pathOrion) and not OrionTools.directoryCreate(self.pathOrion):
			return self._integrateFailure('Open Scrapers directory creation error', self.pathOrion)
		if not OrionTools.fileCopy(self._path('orionoid.py'), self.pathOrionoid, overwrite = True):
			return self._integrateFailure('Open Scrapers provider integration failure', self.pathOrionoid)
		if not OrionTools.fileCopy(self._path('module.py'), self.pathInit, overwrite = True):
			return self._integrateFailure('Open Scrapers module integration failure', self.pathInit)

		return self._integrateSuccess()

	##############################################################################
	# LAMBDA SCRAPERS
	##############################################################################

	def _lambdaScrapersInitialize(self):
		self.name = OrionIntegration.AddonLambdaScrapers
		self.id = self.id(self.name)
		self.idPlugin = 'script.module.lambdascrapers'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		self.versionNumber = int(re.sub('[^0-9]', '', self.version)) if self.version else None

		self.pathPlugin = OrionTools.addonPath(self.idPlugin)

		self.pathSettings = OrionTools.pathJoin(self.pathPlugin, 'resources', 'settings.xml')
		self.pathAddon = OrionTools.pathJoin(self.pathPlugin, 'addon.xml')

		if self.versionNumber and self.versionNumber < 150: # version < 1.5.3
			self.pathSources = OrionTools.pathJoin(self.pathPlugin, 'lib', 'lambdascrapers', 'sources_ALL', '__init__.py')
			self.pathOrion = OrionTools.pathJoin(self.pathPlugin, 'lib', 'lambdascrapers', 'sources_ALL', 'orion')
			self.pathOrionoid = OrionTools.pathJoin(self.pathOrion, 'orionoid.py')
			self.pathInit = OrionTools.pathJoin(self.pathOrion, '__init__.py')

			self.files = []
			self.files.append(self.pathAddon)
			self.files.append(self.pathSources)
			self.files.append(self.pathInit)

			self.deletes = []
			self.deletes.append(self.pathOrion)
		else:
			self.pathSources = OrionTools.pathJoin(self.pathPlugin, 'lib', 'lambdascrapers', '__init__.py')
			self.pathOrion = OrionTools.pathJoin(self.pathPlugin, 'lib', 'lambdascrapers', 'sources_ lambdascrapers', 'orion')
			self.pathOrionoid = OrionTools.pathJoin(self.pathOrion, 'orionoid.py')
			self.pathInit = OrionTools.pathJoin(self.pathOrion, '__init__.py')

			self.files = []
			self.files.append(self.pathSettings)
			self.files.append(self.pathAddon)
			self.files.append(self.pathSources)
			self.files.append(self.pathInit)

			self.deletes = []
			self.deletes.append(self.pathOrion)

	def _lambdaScrapersIntegrate(self):
		if self.versionNumber < 150: # version < 1.5.3
			# __init__.py
			data = self._comment(self._content('sources.py'), OrionIntegration.LanguagePython, '                    ')
			if not OrionTools.fileInsert(self.pathSources, '\.load_module\(module_name\)', data, validate = True):
				return self._integrateFailure('Lambda Scrapers sources integration failure', self.pathSources)

			# addon.xml
			data = self._comment(self._content('addon.xml') % (OrionTools.addonId(), OrionTools.addonVersion()), OrionIntegration.LanguageXml, '\t\t')
			if not OrionTools.fileInsert(self.pathAddon, '<import\s+addon\s*=\s*[\'"]xbmc\.python[\'"].*?\/>', data):
				return self._integrateFailure('Lambda Scrapers addon metadata integration failure', self.pathAddon)

			# orionoid.py
			if not OrionTools.directoryExists(self.pathOrion) and not OrionTools.directoryCreate(self.pathOrion):
				return self._integrateFailure('Lambda Scrapers directory creation error', self.pathOrion)
			if not OrionTools.fileCopy(self._path('orionoid.py'), self.pathOrionoid, overwrite = True):
				return self._integrateFailure('Lambda Scrapers provider integration failure', self.pathOrionoid)
			if not OrionTools.fileCopy(self._path('module.py'), self.pathInit, overwrite = True):
				return self._integrateFailure('Lambda Scrapers module integration failure', self.pathInit)

			return self._integrateSuccess()
		else:
			# settings.xml
			data = self._comment(self._content('settings.xml'), OrionIntegration.LanguageXml, '\t')
			if not OrionTools.fileInsert(self.pathSettings, '<\s*category\s+label\s*=\s*[\'"]Providers[\'"]\s*>', data):
				return self._integrateFailure('Lambda Scrapers settings integration failure', self.pathSettings)

			# __init__.py
			data = self._comment(self._content('sources1.py'), OrionIntegration.LanguagePython, '                    ')
			if not OrionTools.fileInsert(self.pathSources, '\.load_module\(module_name\)', data, validate = True):
				return self._integrateFailure('Lambda Scrapers sources integration failure', self.pathSources)
			data = self._comment(self._content('sources2.py'), OrionIntegration.LanguagePython, '        ')
			if not OrionTools.fileInsert(self.pathSources, 'return\s*enabledHosters\(sourceDict\)', data, validate = True, replace = True):
				return self._integrateFailure('Lambda Scrapers sources integration failure', self.pathSources)

			# addon.xml
			data = self._comment(self._content('addon.xml') % (OrionTools.addonId(), OrionTools.addonVersion()), OrionIntegration.LanguageXml, '\t\t')
			if not OrionTools.fileInsert(self.pathAddon, '<import\s+addon\s*=\s*[\'"]xbmc\.python[\'"].*?\/>', data):
				return self._integrateFailure('Lambda Scrapers addon metadata integration failure', self.pathAddon)

			# orionoid.py
			if not OrionTools.directoryExists(self.pathOrion) and not OrionTools.directoryCreate(self.pathOrion):
				return self._integrateFailure('Lambda Scrapers directory creation error', self.pathOrion)
			if not OrionTools.fileCopy(self._path('orionoid.py'), self.pathOrionoid, overwrite = True):
				return self._integrateFailure('Lambda Scrapers provider integration failure', self.pathOrionoid)
			if not OrionTools.fileCopy(self._path('module.py'), self.pathInit, overwrite = True):
				return self._integrateFailure('Lambda Scrapers module integration failure', self.pathInit)

			return self._integrateSuccess()

	##############################################################################
	# FENOM SCRAPERS
	##############################################################################

	def _fenomScrapersInitialize(self):
		self.name = OrionIntegration.AddonFenomScrapers
		self.id = self.id(self.name)
		self.idPlugin = 'script.module.fenomscrapers'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		self.versionNumber = int(re.sub('[^0-9]', '', self.version)) if self.version else None

		self.pathPlugin = OrionTools.addonPath(self.idPlugin)

		self.pathSettings = OrionTools.pathJoin(self.pathPlugin, 'resources', 'settings.xml')
		self.pathAddon = OrionTools.pathJoin(self.pathPlugin, 'addon.xml')

		self.pathScrapers = OrionTools.pathJoin(self.pathPlugin, 'lib', 'fenomscrapers', 'sources_fenomscrapers')
		self.pathOrionoid = OrionTools.pathJoin(self.pathScrapers, 'orionoid.py')
		self.pathOrionHoster = OrionTools.pathJoin(self.pathScrapers, 'hosters', 'orionhoster.py')
		self.pathOrionTorrent = OrionTools.pathJoin(self.pathScrapers, 'torrents', 'oriontorrent.py')

		self.files = []
		self.files.append(self.pathSettings)
		self.files.append(self.pathAddon)

		self.deletes = []
		self.deletes.append(self.pathOrionoid)
		self.deletes.append(self.pathOrionHoster)
		self.deletes.append(self.pathOrionTorrent)

	def _fenomScrapersIntegrate(self):
		# settings.xml
		data = self._comment(self._content('settings1.xml'), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathSettings, '"32051".*?<setting\s*type\s*=\s*[\'"]sep[\'"]\s*\/>', data, flags = re.S):
			return self._integrateFailure('Fenom Scrapers hoster settings integration failure', self.pathSettings)
		data = self._comment(self._content('settings2.xml'), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathSettings, '"32052".*?<setting\s*type\s*=\s*[\'"]sep[\'"]\s*\/>.*?<setting\s*type\s*=\s*[\'"]sep[\'"]\s*\/>', data, flags = re.S):
			return self._integrateFailure('Fenom Scrapers torrent settings integration failure', self.pathSettings)

		# addon.xml
		data = self._comment(self._content('addon.xml') % (OrionTools.addonId(), OrionTools.addonVersion()), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathAddon, '<requires.*?(\r?\n?)\s*<\/requires>', data, flags = OrionTools.RegexDotAll, group = 1):
			return self._integrateFailure('Fenom Scrapers addon metadata integration failure', self.pathAddon)

		# orionoid.py
		if not OrionTools.fileCopy(self._path('orionoid.py'), self.pathOrionoid, overwrite = True):
			return self._integrateFailure('Fenom Scrapers provider integration failure', self.pathOrionoid)
		if not OrionTools.fileCopy(self._path('orionhoster.py'), self.pathOrionHoster, overwrite = True):
			return self._integrateFailure('Fenom Scrapers hoster provider integration failure', self.pathOrionHoster)
		if not OrionTools.fileCopy(self._path('oriontorrent.py'), self.pathOrionTorrent, overwrite = True):
			return self._integrateFailure('Fenom Scrapers torrent provider integration failure', self.pathOrionTorrent)

		return self._integrateSuccess()

	##############################################################################
	# NIGHTWING SCRAPERS
	##############################################################################

	def _nightwingScrapersInitialize(self):
		self.name = OrionIntegration.AddonNightwingScrapers
		self.id = self.id(self.name)
		self.idPlugin = 'script.module.nightwingscrapers'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		self.versionNumber = int(re.sub('[^0-9]', '', self.version)) if self.version else None

		self.pathPlugin = OrionTools.addonPath(self.idPlugin)

		self.pathSettings = OrionTools.pathJoin(self.pathPlugin, 'resources', 'settings.xml')
		self.pathAddon = OrionTools.pathJoin(self.pathPlugin, 'addon.xml')

		self.pathScrapers = OrionTools.pathJoin(self.pathPlugin, 'lib', 'nightwingscrapers', 'sources_nightwingscrapers')
		self.pathOrionoid = OrionTools.pathJoin(self.pathScrapers, 'en', 'orionoid.py')

		self.files = []
		self.files.append(self.pathSettings)
		self.files.append(self.pathAddon)

		self.deletes = []
		self.deletes.append(self.pathOrionoid)

	def _nightwingScrapersIntegrate(self):
		# settings.xml
		data = self._comment(self._content('settings.xml'), OrionIntegration.LanguageXml, '        ')
		if not OrionTools.fileInsert(self.pathSettings, '<category\s*label\s*=\s*"scraper\s*accounts">', data, flags = re.S | re.I):
			return self._integrateFailure('Nightwing Scrapers settings integration failure', self.pathSettings)

		# addon.xml
		data = self._comment(self._content('addon.xml') % (OrionTools.addonId(), OrionTools.addonVersion()), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathAddon, '<requires.*?(\r?\n?)\s*<\/requires>', data, flags = OrionTools.RegexDotAll, group = 1):
			return self._integrateFailure('Nightwing Scrapers addon metadata integration failure', self.pathAddon)

		# orionoid.py
		if not OrionTools.fileCopy(self._path('orionoid.py'), self.pathOrionoid, overwrite = True):
			return self._integrateFailure('Nightwing Scrapers provider integration failure', self.pathOrionoid)

		return self._integrateSuccess()

	##############################################################################
	# COCO SCRAPERS
	##############################################################################

	def _cocoScrapersInitialize(self):
		self.name = OrionIntegration.AddonCocoScrapers
		self.id = self.id(self.name)
		self.idPlugin = 'script.module.cocoscrapers'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		self.versionNumber = int(re.sub('[^0-9]', '', self.version)) if self.version else None

		self.pathPlugin = OrionTools.addonPath(self.idPlugin)

		self.pathStrings = OrionTools.pathJoin(self.pathPlugin, 'resources', 'language', 'resource.language.en_gb', 'strings.po')
		self.pathSettings = OrionTools.pathJoin(self.pathPlugin, 'resources', 'settings.xml')
		self.pathAddon = OrionTools.pathJoin(self.pathPlugin, 'addon.xml')

		self.pathScrapers = OrionTools.pathJoin(self.pathPlugin, 'lib', 'cocoscrapers', 'sources_cocoscrapers')
		self.pathOrionoid = OrionTools.pathJoin(self.pathScrapers, 'orionoid.py')

		#self.pathOrionHoster = OrionTools.pathJoin(self.pathScrapers, 'hosters', 'orionhoster.py')
		self.pathOrionHoster = None # New CocScrapers version has completely removed all hoster providers.

		self.pathOrionTorrent = OrionTools.pathJoin(self.pathScrapers, 'torrents', 'oriontorrent.py')

		self.files = []
		self.files.append(self.pathStrings)
		self.files.append(self.pathSettings)
		self.files.append(self.pathAddon)

		self.deletes = []
		self.deletes.append(self.pathOrionoid)
		if self.pathOrionHoster: self.deletes.append(self.pathOrionHoster)
		if self.pathOrionTorrent: self.deletes.append(self.pathOrionTorrent)

	def _cocoScrapersIntegrate(self):
		# strings.po
		data = self._comment(self._content('strings.po'), OrionIntegration.LanguagePython)
		if not OrionTools.fileInsert(self.pathStrings, '\Z', data, flags = re.S):
			return self._integrateFailure('Coco Scrapers strings integration failure', self.pathStrings)

		# settings.xml
		if self.pathOrionHoster:
			data = self._comment(self._content('settings1.xml'), OrionIntegration.LanguageXml, '\t\t')
			if not OrionTools.fileInsert(self.pathSettings, 'id\s*=\s*[\'"]hosters[\'"].*?<group.*?id\s*=\s*[\'"]3[\'"].*?\s*>', data, flags = re.S):
				return self._integrateFailure('Coco Scrapers hoster settings integration failure', self.pathSettings)
		if self.pathOrionTorrent:
			data = self._comment(self._content('settings2.xml'), OrionIntegration.LanguageXml, '\t\t')
			if not OrionTools.fileInsert(self.pathSettings, 'id\s*=\s*[\'"]torrents[\'"].*?<group.*?id\s*=\s*[\'"]3[\'"].*?\s*>', data, flags = re.S):
				return self._integrateFailure('Coco Scrapers torrent settings integration failure', self.pathSettings)

		# addon.xml
		data = self._comment(self._content('addon.xml') % (OrionTools.addonId(), OrionTools.addonVersion()), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathAddon, '<requires.*?(\r?\n?)\s*<\/requires>', data, flags = OrionTools.RegexDotAll, group = 1):
			return self._integrateFailure('Coco Scrapers addon metadata integration failure', self.pathAddon)

		# orionoid.py
		if not OrionTools.fileCopy(self._path('orionoid.py'), self.pathOrionoid, overwrite = True):
			return self._integrateFailure('Coco Scrapers provider integration failure', self.pathOrionoid)
		if self.pathOrionHoster and not OrionTools.fileCopy(self._path('orionhoster.py'), self.pathOrionHoster, overwrite = True):
			return self._integrateFailure('Coco Scrapers hoster provider integration failure', self.pathOrionHoster)
		if self.pathOrionTorrent and not OrionTools.fileCopy(self._path('oriontorrent.py'), self.pathOrionTorrent, overwrite = True):
			return self._integrateFailure('Coco Scrapers torrent provider integration failure', self.pathOrionTorrent)

		return self._integrateSuccess()

	##############################################################################
	# UMBRELLA SCRAPERS
	##############################################################################

	def _umbrellaScrapersInitialize(self):
		self.name = OrionIntegration.AddonUmbrellaScrapers
		self.id = self.id(self.name)
		self.idPlugin = 'script.module.umbrellascrapers'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		self.versionNumber = int(re.sub('[^0-9]', '', self.version)) if self.version else None

		self.pathPlugin = OrionTools.addonPath(self.idPlugin)

		self.pathSettings = OrionTools.pathJoin(self.pathPlugin, 'resources', 'settings.xml')
		self.pathAddon = OrionTools.pathJoin(self.pathPlugin, 'addon.xml')

		self.pathScrapers = OrionTools.pathJoin(self.pathPlugin, 'lib', 'umbrellascrapers', 'sources_umbrellascrapers')
		self.pathOrionoid = OrionTools.pathJoin(self.pathScrapers, 'orionoid.py')
		self.pathOrionHoster = OrionTools.pathJoin(self.pathScrapers, 'hosters', 'orionhoster.py')
		self.pathOrionTorrent = OrionTools.pathJoin(self.pathScrapers, 'torrents', 'oriontorrent.py')

		self.files = []
		self.files.append(self.pathSettings)
		self.files.append(self.pathAddon)

		self.deletes = []
		self.deletes.append(self.pathOrionoid)
		self.deletes.append(self.pathOrionHoster)
		self.deletes.append(self.pathOrionTorrent)

	def _umbrellaScrapersIntegrate(self):
		# settings.xml
		data = self._comment(self._content('settings1.xml'), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathSettings, '"32051".*?<setting\s*type\s*=\s*[\'"]sep[\'"]\s*\/>', data, flags = re.S):
			return self._integrateFailure('Umbrella Scrapers hoster settings integration failure', self.pathSettings)
		data = self._comment(self._content('settings2.xml'), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathSettings, '"32052".*?<setting\s*type\s*=\s*[\'"]sep[\'"]\s*\/>.*?<setting\s*type\s*=\s*[\'"]sep[\'"]\s*\/>', data, flags = re.S):
			return self._integrateFailure('Umbrella Scrapers torrent settings integration failure', self.pathSettings)

		# addon.xml
		data = self._comment(self._content('addon.xml') % (OrionTools.addonId(), OrionTools.addonVersion()), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathAddon, '<requires.*?(\r?\n?)\s*<\/requires>', data, flags = OrionTools.RegexDotAll, group = 1):
			return self._integrateFailure('Umbrella Scrapers addon metadata integration failure', self.pathAddon)

		# orionoid.py
		if not OrionTools.fileCopy(self._path('orionoid.py'), self.pathOrionoid, overwrite = True):
			return self._integrateFailure('Umbrella Scrapers provider integration failure', self.pathOrionoid)
		if not OrionTools.fileCopy(self._path('orionhoster.py'), self.pathOrionHoster, overwrite = True):
			return self._integrateFailure('Umbrella Scrapers hoster provider integration failure', self.pathOrionHoster)
		if not OrionTools.fileCopy(self._path('oriontorrent.py'), self.pathOrionTorrent, overwrite = True):
			return self._integrateFailure('Umbrella Scrapers torrent provider integration failure', self.pathOrionTorrent)

		return self._integrateSuccess()

	##############################################################################
	# KINGPIN SCRAPERS
	##############################################################################

	def _kingPinScrapersInitialize(self):
		self.name = OrionIntegration.AddonKingPinScrapers
		self.id = self.id(self.name)
		self.idPlugin = 'script.module.kingpinscrapers'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		self.versionNumber = int(re.sub('[^0-9]', '', self.version)) if self.version else None

		self.pathPlugin = OrionTools.addonPath(self.idPlugin)

		self.pathSettings = OrionTools.pathJoin(self.pathPlugin, 'resources', 'settings.xml')
		self.pathAddon = OrionTools.pathJoin(self.pathPlugin, 'addon.xml')

		self.pathScrapers = OrionTools.pathJoin(self.pathPlugin, 'lib', 'kingpinscrapers', 'sources_kingpinscrapers')
		self.pathOrionoid = OrionTools.pathJoin(self.pathScrapers, 'orionoid.py')
		self.pathOrionHoster = OrionTools.pathJoin(self.pathScrapers, 'hosters', 'orionhoster.py')
		self.pathOrionTorrent = OrionTools.pathJoin(self.pathScrapers, 'torrents', 'oriontorrent.py')

		self.files = []
		self.files.append(self.pathSettings)
		self.files.append(self.pathAddon)

		self.deletes = []
		self.deletes.append(self.pathOrionoid)
		self.deletes.append(self.pathOrionHoster)
		self.deletes.append(self.pathOrionTorrent)

	def _kingPinScrapersIntegrate(self):
		# settings.xml
		data = self._comment(self._content('settings1.xml'), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathSettings, '"32051".*?<setting\s*type\s*=\s*[\'"]sep[\'"]\s*\/>', data, flags = re.S):
			return self._integrateFailure('KingPin Scrapers hoster settings integration failure', self.pathSettings)
		data = self._comment(self._content('settings2.xml'), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathSettings, '"32052".*?<setting\s*type\s*=\s*[\'"]sep[\'"]\s*\/>.*?<setting\s*type\s*=\s*[\'"]sep[\'"]\s*\/>', data, flags = re.S):
			return self._integrateFailure('KingPin Scrapers torrent settings integration failure', self.pathSettings)

		# addon.xml
		data = self._comment(self._content('addon.xml') % (OrionTools.addonId(), OrionTools.addonVersion()), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathAddon, '<requires.*?(\r?\n?)\s*<\/requires>', data, flags = OrionTools.RegexDotAll, group = 1):
			return self._integrateFailure('KingPin Scrapers addon metadata integration failure', self.pathAddon)

		# orionoid.py
		if not OrionTools.fileCopy(self._path('orionoid.py'), self.pathOrionoid, overwrite = True):
			return self._integrateFailure('KingPin Scrapers provider integration failure', self.pathOrionoid)
		if not OrionTools.fileCopy(self._path('orionhoster.py'), self.pathOrionHoster, overwrite = True):
			return self._integrateFailure('KingPin Scrapers hoster provider integration failure', self.pathOrionHoster)
		if not OrionTools.fileCopy(self._path('oriontorrent.py'), self.pathOrionTorrent, overwrite = True):
			return self._integrateFailure('KingPin Scrapers torrent provider integration failure', self.pathOrionTorrent)

		return self._integrateSuccess()

	##############################################################################
	# EZ SCRAPERS
	##############################################################################

	def _ezScrapersInitialize(self):
		self.name = OrionIntegration.AddonEzScrapers
		self.id = self.id(self.name)
		self.idPlugin = 'script.module.ezscrapers'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		self.versionNumber = int(re.sub('[^0-9]', '', self.version)) if self.version else None

		self.pathPlugin = OrionTools.addonPath(self.idPlugin)

		self.pathSettings = OrionTools.pathJoin(self.pathPlugin, 'resources', 'settings.xml')
		self.pathAddon = OrionTools.pathJoin(self.pathPlugin, 'addon.xml')

		self.pathScrapers = OrionTools.pathJoin(self.pathPlugin, 'lib', 'ezscrapers', 'sources_ezscrapers')
		self.pathOrionoid = OrionTools.pathJoin(self.pathScrapers, 'orionoid.py')
		self.pathOrionHoster = OrionTools.pathJoin(self.pathScrapers, 'hosters', 'orionhoster.py')
		self.pathOrionTorrent = OrionTools.pathJoin(self.pathScrapers, 'torrents', 'oriontorrent.py')

		self.files = []
		self.files.append(self.pathSettings)
		self.files.append(self.pathAddon)

		self.deletes = []
		self.deletes.append(self.pathOrionoid)
		self.deletes.append(self.pathOrionHoster)
		self.deletes.append(self.pathOrionTorrent)

	def _ezScrapersIntegrate(self):
		# settings.xml
		data = self._comment(self._content('settings1.xml'), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathSettings, '"32051".*?<setting\s*type\s*=\s*[\'"]sep[\'"]\s*\/>', data, flags = re.S):
			return self._integrateFailure('Ez Scrapers hoster settings integration failure', self.pathSettings)
		data = self._comment(self._content('settings2.xml'), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathSettings, '"32052".*?<setting\s*type\s*=\s*[\'"]sep[\'"]\s*\/>.*?<setting\s*type\s*=\s*[\'"]sep[\'"]\s*\/>', data, flags = re.S):
			return self._integrateFailure('Ez Scrapers torrent settings integration failure', self.pathSettings)

		# addon.xml
		data = self._comment(self._content('addon.xml') % (OrionTools.addonId(), OrionTools.addonVersion()), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathAddon, '<requires.*?(\r?\n?)\s*<\/requires>', data, flags = OrionTools.RegexDotAll, group = 1):
			return self._integrateFailure('Ez Scrapers addon metadata integration failure', self.pathAddon)

		# orionoid.py
		if not OrionTools.fileCopy(self._path('orionoid.py'), self.pathOrionoid, overwrite = True):
			return self._integrateFailure('Ez Scrapers provider integration failure', self.pathOrionoid)
		if not OrionTools.fileCopy(self._path('orionhoster.py'), self.pathOrionHoster, overwrite = True):
			return self._integrateFailure('Ez Scrapers hoster provider integration failure', self.pathOrionHoster)
		if not OrionTools.fileCopy(self._path('oriontorrent.py'), self.pathOrionTorrent, overwrite = True):
			return self._integrateFailure('Ez Scrapers torrent provider integration failure', self.pathOrionTorrent)

		return self._integrateSuccess()

	##############################################################################
	# UNIVERSAL SCRAPERS
	##############################################################################

	def _universalScrapersInitialize(self):
		self.name = OrionIntegration.AddonUniversalScrapers
		self.id = self.id(self.name)
		self.idPlugin = 'script.module.universalscrapers'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)

		self.pathPlugin = OrionTools.addonPath(self.idPlugin)

		self.pathSettings = OrionTools.pathJoin(self.pathPlugin, 'resources', 'settings.xml')
		self.pathAddon = OrionTools.pathJoin(self.pathPlugin, 'addon.xml')
		self.pathOrionoid = OrionTools.pathJoin(self.pathPlugin, 'lib', 'universalscrapers', 'scraperplugins', 'orionoid.py')
		self.pathInit = OrionTools.pathJoin(self.pathPlugin, 'lib', 'universalscrapers', '__init__.py')

		self.files = []
		self.files.append(self.pathSettings)
		self.files.append(self.pathAddon)
		self.files.append(self.pathInit)

		self.deletes = []
		self.deletes.append(self.pathOrionoid)

	def _universalScrapersIntegrate(self):
		# settings.xml
		data = self._comment(self._content('settings.xml'), OrionIntegration.LanguageXml, '\t')
		if not OrionTools.fileInsert(self.pathSettings, '<\s*category\s+label\s*=\s*[\'"]Scrapers\s*1[\'"]\s*>', data):
			return self._integrateFailure('Universal Scrapers settings integration failure', self.pathSettings)

		# __init__.py
		data = self._comment(self._content('module.py'), OrionIntegration.LanguagePython, '    ')
		if not OrionTools.fileInsert(self.pathInit, 'relevant_scrapers\(\s*include_disabled\s*=\s*True\s*\),\s*key\s*=\s*lambda\s*x\s*:\s*x\.name\.lower\(\)\s*\)', data, validate = True):
			return self._integrateFailure('Universal Scrapers module integration failure', self.pathInit)

		# addon.xml
		data = self._comment(self._content('addon.xml') % (OrionTools.addonId(), OrionTools.addonVersion()), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathAddon, '<import\s+addon\s*=\s*[\'"]repository\.universalscrapers[\'"]\s*\/>', data):
			return self._integrateFailure('Universal Scrapers addon metadata integration failure', self.pathAddon)

		# orionoid.py
		if not OrionTools.fileCopy(self._path('orionoid.py'), self.pathOrionoid, overwrite = True):
			return self._integrateFailure('Universal Scrapers provider integration failure', self.pathOrionoid)

		return self._integrateSuccess()

	##############################################################################
	# UNIVERSAL DEBRID
	##############################################################################

	def _universalDebridInitialize(self):
		self.name = OrionIntegration.AddonUniversalDebrid
		self.id = self.id(self.name)
		self.idPlugin = 'script.module.universaldebrid'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)

		self.pathPlugin = OrionTools.addonPath(self.idPlugin)

		self.pathSettings = OrionTools.pathJoin(self.pathPlugin, 'resources', 'settings.xml')
		self.pathAddon = OrionTools.pathJoin(self.pathPlugin, 'addon.xml')
		self.pathOrionoid = OrionTools.pathJoin(self.pathPlugin, 'lib', 'universaldebrid', 'scraperplugins', 'orionoid.py')
		self.pathInit = OrionTools.pathJoin(self.pathPlugin, 'lib', 'universaldebrid', '__init__.py')

		self.files = []
		self.files.append(self.pathSettings)
		self.files.append(self.pathAddon)
		self.files.append(self.pathInit)

		self.deletes = []
		self.deletes.append(self.pathOrionoid)

	def _universalDebridIntegrate(self):
		# settings.xml
		data = self._comment(self._content('settings.xml'), OrionIntegration.LanguageXml, '\t')
		if not OrionTools.fileInsert(self.pathSettings, '<\s*category\s+label\s*=\s*[\'"]Scrapers\s*1[\'"]\s*>', data):
			return self._integrateFailure('Universal Debrid settings integration failure', self.pathSettings)

		# __init__.py
		data = self._comment(self._content('module.py'), OrionIntegration.LanguagePython, '    ')
		if not OrionTools.fileInsert(self.pathInit, 'relevant_scrapers\(\s*include_disabled\s*=\s*True\s*\),\s*key\s*=\s*lambda\s*x\s*:\s*x\.name\.lower\(\)\s*\)', data, validate = True):
			return self._integrateFailure('Universal Debrid module integration failure', self.pathInit)

		# addon.xml
		data = self._comment(self._content('addon.xml') % (OrionTools.addonId(), OrionTools.addonVersion()), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathAddon, '<import\s+addon\s*=\s*[\'"]repository\.(universalscrapers|universaldebrid|NarcacistWizard)[\'"]\s*\/>', data):
			return self._integrateFailure('Universal Debrid addon metadata integration failure', self.pathAddon)

		# orionoid.py
		if not OrionTools.fileCopy(self._path('orionoid.py'), self.pathOrionoid, overwrite = True):
			return self._integrateFailure('Universal Debrid provider integration failure', self.pathOrionoid)

		return self._integrateSuccess()

	##############################################################################
	# NAN SCRAPERS
	##############################################################################

	def _nanScrapersInitialize(self):
		self.name = OrionIntegration.AddonNanScrapers
		self.id = self.id(self.name)
		self.idPlugin = 'script.module.nanscrapers'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)

		self.pathPlugin = OrionTools.addonPath(self.idPlugin)

		self.pathSettings = OrionTools.pathJoin(self.pathPlugin, 'resources', 'settings.xml')
		self.pathAddon = OrionTools.pathJoin(self.pathPlugin, 'addon.xml')
		self.pathOrionoid = OrionTools.pathJoin(self.pathPlugin, 'lib', 'nanscrapers', 'scraperplugins', 'orionoid.py')
		self.pathInit = OrionTools.pathJoin(self.pathPlugin, 'lib', 'nanscrapers', '__init__.py')

		self.files = []
		self.files.append(self.pathSettings)
		self.files.append(self.pathAddon)
		self.files.append(self.pathInit)

		self.deletes = []
		self.deletes.append(self.pathOrionoid)

	def _nanScrapersIntegrate(self):
		# settings.xml
		data = self._comment(self._content('settings.xml'), OrionIntegration.LanguageXml, '\t')
		if not OrionTools.fileInsert(self.pathSettings, '<\s*category\s+label\s*=\s*[\'"]Scrapers\s*1[\'"]\s*>', data):
			return self._integrateFailure('NaN Scrapers settings integration failure', self.pathSettings)

		# __init__.py
		data = self._comment(self._content('module.py'), OrionIntegration.LanguagePython, '    ')
		if not OrionTools.fileInsert(self.pathInit, 'relevant_scrapers\(\s*include_disabled\s*=\s*True\s*\),\s*key\s*=\s*lambda\s*x\s*:\s*x\.name\.lower\(\)\s*\)', data, validate = True):
			return self._integrateFailure('NaN Scrapers module integration failure', self.pathInit)

		# addon.xml
		data = self._comment(self._content('addon.xml') % (OrionTools.addonId(), OrionTools.addonVersion()), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathAddon, '<import\s+addon\s*=\s*[\'"]script\.module\.six[\'"]\s*\/>', data):
			return self._integrateFailure('NaN Scrapers addon metadata integration failure', self.pathAddon)

		# orionoid.py
		if not OrionTools.fileCopy(self._path('orionoid.py'), self.pathOrionoid, overwrite = True):
			return self._integrateFailure('NaN Scrapers provider integration failure', self.pathOrionoid)

		return self._integrateSuccess()

	##############################################################################
	# ENCRYPTICSCRAPERS
	##############################################################################

	def _encrypticScrapersInitialize(self):
		self.name = OrionIntegration.AddonEncrypticScrapers
		self.id = self.id(self.name)
		self.idPlugin = 'script.module.encrypticscrapers'
		self.idSettings = self.idPlugin
		self.version = self._version(self.idPlugin)
		self.native = True
		self.files = []
		self.deletes = []

	##############################################################################
	# ELEMENTUM
	##############################################################################

	def _elementumInitialize(self):
		self.name = OrionIntegration.AddonElementum
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.elementum'
		self.idModule = 'script.elementum.burst'
		self.idSettings = self.idModule
		self.version = self._version(self.idPlugin, self.idModule)

		self.pathPlugin = OrionTools.addonPath(self.idPlugin)
		self.pathModule = OrionTools.addonPath(self.idModule)
		self.pathProfile = OrionTools.addonProfile(self.idModule)

		self.pathSettings = OrionTools.pathJoin(self.pathModule, 'resources', 'settings.xml')
		self.pathAddon = OrionTools.pathJoin(self.pathModule, 'addon.xml')
		self.pathBurst = OrionTools.pathJoin(self.pathModule, 'burst', 'burst.py')
		self.pathProvider = OrionTools.pathJoin(self.pathModule, 'burst', 'provider.py')
		self.pathOrionoid = OrionTools.pathJoin(self.pathModule, 'burst', 'providers', 'orionoid.py')
		self.pathIcon = OrionTools.pathJoin(self.pathModule, 'burst', 'providers', 'icons', 'orion.png')
		self.pathScraper = OrionTools.pathJoin(self.pathProfile, 'providers', 'orion.json')

		self.files = []
		self.files.append(self.pathSettings)
		self.files.append(self.pathAddon)
		self.files.append(self.pathBurst)
		self.files.append(self.pathProvider)

		self.deletes = []
		self.deletes.append(self.pathOrionoid)
		self.deletes.append(self.pathIcon)
		self.deletes.append(self.pathScraper)

	def _elementumIntegrate(self):
		# addon.xml
		data = self._comment(self._content('addon.xml') % (OrionTools.addonId(), OrionTools.addonVersion()), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathAddon, '<import\s+addon\s*=\s*[\'"]plugin\.video\.elementum[\'"].*\/>', data):
			return self._integrateFailure('Elementum addon metadata integration failure', self.pathAddon)

		# settings.xml
		data = self._comment(self._content('settings.xml'), OrionIntegration.LanguageXml, '\t')
		if not OrionTools.fileInsert(self.pathSettings, '<\s*category\s+label\s*=\s*[\'"]32128[\'"]\s*>', data):
			return self._integrateFailure('Elementum settings integration failure', self.pathSettings)

		# burst.py
		data = self._comment(self._content('burst.py'), OrionIntegration.LanguagePython, '    ')
		if not OrionTools.fileInsert(self.pathBurst, 'def\s*got_results\(provider,\s*results\).*?""".*?""".*?\n', data, validate = True, flags = re.S):
			return self._integrateFailure('Elementum burst integration failure', self.pathBurst)

		# provider.py
		data = self._comment(self._content('provider.py'), OrionIntegration.LanguagePython, '    ')
		if not OrionTools.fileInsert(self.pathProvider, 'token_auth\s*=\s*False.*', data, validate = True):
			return self._integrateFailure('Elementum provider integration failure', self.pathProvider)

		# orionoid.py
		if not OrionTools.fileCopy(self._path('orionoid.py'), self.pathOrionoid, overwrite = True):
			return self._integrateFailure('Elementum module integration failure', self.pathOrionoid)

		# orion.png
		if not OrionTools.fileCopy(self._path('orion.png'), self.pathIcon, overwrite = True):
			return self._integrateFailure('Elementum icon integration failure', self.pathIcon)

		# orion.json
		if not OrionTools.fileCopy(self._path('orion.json'), self.pathScraper, overwrite = True):
			return self._integrateFailure('Elementum scraper integration failure', self.pathScraper)

		return self._integrateSuccess()

	##############################################################################
	# QUASAR
	##############################################################################

	def _quasarInitialize(self):
		self.name = OrionIntegration.AddonQuasar
		self.id = self.id(self.name)
		self.idPlugin = 'plugin.video.quasar'
		self.idModule = 'script.quasar.burst'
		self.idSettings = self.idModule
		self.version = self._version(self.idPlugin, self.idModule)

		self.pathPlugin = OrionTools.addonPath(self.idPlugin)
		self.pathModule = OrionTools.addonPath(self.idModule)
		self.pathProfile = OrionTools.addonProfile(self.idModule)

		self.pathSettings = OrionTools.pathJoin(self.pathModule, 'resources', 'settings.xml')
		self.pathAddon = OrionTools.pathJoin(self.pathModule, 'addon.xml')
		self.pathBurst = OrionTools.pathJoin(self.pathModule, 'burst', 'burst.py')
		self.pathProvider = OrionTools.pathJoin(self.pathModule, 'burst', 'provider.py')
		self.pathOrionoid = OrionTools.pathJoin(self.pathModule, 'burst', 'providers', 'orionoid.py')
		self.pathIcon = OrionTools.pathJoin(self.pathModule, 'burst', 'providers', 'icons', 'orion.png')
		self.pathScraper = OrionTools.pathJoin(self.pathProfile, 'providers', 'orion.json')

		self.files = []
		self.files.append(self.pathSettings)
		self.files.append(self.pathAddon)
		self.files.append(self.pathBurst)
		self.files.append(self.pathProvider)

		self.deletes = []
		self.deletes.append(self.pathOrionoid)
		self.deletes.append(self.pathIcon)
		self.deletes.append(self.pathScraper)

	def _quasarIntegrate(self):
		# addon.xml
		data = self._comment(self._content('addon.xml') % (OrionTools.addonId(), OrionTools.addonVersion()), OrionIntegration.LanguageXml, '\t\t')
		if not OrionTools.fileInsert(self.pathAddon, '<import\s+addon\s*=\s*[\'"]plugin\.video\.quasar[\'"].*\/>', data):
			return self._integrateFailure('Quasar addon metadata integration failure', self.pathAddon)

		# settings.xml
		data = self._comment(self._content('settings.xml'), OrionIntegration.LanguageXml, '\t')
		if not OrionTools.fileInsert(self.pathSettings, '<\s*category\s+label\s*=\s*[\'"]32012[\'"]\s*>', data):
			return self._integrateFailure('Quasar settings integration failure', self.pathSettings)

		# burst.py
		data = self._comment(self._content('burst.py'), OrionIntegration.LanguagePython, '    ')
		if not OrionTools.fileInsert(self.pathBurst, 'max_results\s*=\s*get_setting.*', data, validate = True):
			return self._integrateFailure('Quasar burst integration failure', self.pathBurst)

		# provider.py
		data = self._comment(self._content('provider.py'), OrionIntegration.LanguagePython, '    ')
		if not OrionTools.fileInsert(self.pathProvider, 'token_auth\s*=\s*False.*', data, validate = True):
			return self._integrateFailure('Quasar provider integration failure', self.pathProvider)

		# orionoid.py
		if not OrionTools.fileCopy(self._path('orionoid.py'), self.pathOrionoid, overwrite = True):
			return self._integrateFailure('Quasar module integration failure', self.pathOrionoid)

		# orion.png
		if not OrionTools.fileCopy(self._path('orion.png'), self.pathIcon, overwrite = True):
			return self._integrateFailure('Quasar icon integration failure', self.pathIcon)

		# orion.json
		if not OrionTools.fileCopy(self._path('orion.json'), self.pathScraper, overwrite = True):
			return self._integrateFailure('Quasar scraper integration failure', self.pathScraper)

		return self._integrateSuccess()
