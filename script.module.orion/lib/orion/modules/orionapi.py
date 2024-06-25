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
# ORIONAPI
##############################################################################
# API connection and queries to the Orion server
##############################################################################

import copy
import threading
from orion.modules.oriontools import *
from orion.modules.orionsettings import *
from orion.modules.orioninterface import *
from orion.modules.orionnetworker import *

class OrionApi:

	##############################################################################
	# CONSTANTS
	##############################################################################

	# Used by OrionSettings.
	# Determines which API results to not show a notification for.
	TypesEssential = ['userkey', 'userlogin', 'userauth', 'userauthexpired', 'userauthinvalid', 'userauthinreject', 'abuseregister', 'abuselogin']
	TypesNonessential = ['exception', 'success', 'streammissing']
	TypesBlock = ['streamvoteabuse', 'streamremoveabuse', 'streamupdate']
	TypesAuthentication = ['userkey', 'userlogin']
	TypesSubscription = ['subscriptionexpired', 'subscriptionstreams', 'subscriptionhashes', 'subscriptioncontainers']

	ParameterMode = 'mode'
	ParameterAction = 'action'
	ParameterKeyApp = 'keyapp'
	ParameterKeyUser = 'keyuser'
	ParameterKey = 'key'
	ParameterToken = 'token'
	ParameterCode = 'code'
	ParameterVersion = 'version'
	ParameterId = 'id'
	ParameterEmail = 'email'
	ParameterUser = 'user'
	ParameterPassword = 'password'
	ParameterLink = 'link'
	ParameterLinks = 'links'
	ParameterHash = 'hash'
	ParameterResult = 'result'
	ParameterQuery = 'query'
	ParameterStatus = 'status'
	ParameterType = 'type'
	ParameterItem = 'item'
	ParameterStream = 'stream'
	ParameterDescription = 'description'
	ParameterMessage = 'message'
	ParameterData = 'data'
	ParameterCount = 'count'
	ParameterTotal = 'total'
	ParameterRequested = 'requested'
	ParameterRetrieved = 'retrieved'
	ParameterTime = 'time'
	ParameterDirection = 'direction'
	ParameterVersion = 'version'
	ParameterCategory = 'category'
	ParameterSubject = 'subject'
	ParameterFile = 'file'
	ParameterFiles = 'files'
	ParameterAll = 'all'
	ParameterAutomatic = 'automatic'
	ParameterIdItem = 'iditem'
	ParameterIdStream = 'idstream'
	ParameterRefresh = 'refresh'
	ParameterOutput = 'output'
	ParameterIp = 'ip'
	ParameterGlobal = 'global'
	ParameterContainer = 'container'
	ParameterContainerData = 'containerdata'
	ParameterContainerName = 'containername'
	ParameterContainerType = 'containertype'
	ParameterContainerSize = 'containersize'

	ModeStream = 'stream'
	ModeContainer = 'container'
	ModeApp = 'app'
	ModeUser = 'user'
	ModeTicket = 'ticket'
	ModeNotification = 'notification'
	ModePromotion = 'promotion'
	ModeServer = 'server'
	ModeAddon = 'addon'
	ModeDebrid = 'debrid'
	ModeCoupon = 'coupon'

	ActionAdd = 'add'
	ActionUpdate = 'update'
	ActionRetrieve = 'retrieve'
	ActionAnonymous = 'anonymous'
	ActionDownload = 'download'
	ActionLogin = 'login'
	ActionAuthenticate = 'authenticate'
	ActionRemove = 'remove'
	ActionIdentifier = 'identifier'
	ActionSegment = 'segment'
	ActionHash = 'hash'
	ActionVote = 'vote'
	ActionTest = 'test'
	ActionRedeem = 'redeem'
	ActionVersion = 'version'
	ActionStatus = 'status'
	ActionSupport = 'support'
	ActionLookup = 'lookup'
	ActionResolve = 'resolve'

	StatusUnknown = 'unknown'
	StatusBusy = 'busy'
	StatusSuccess = 'success'
	StatusError = 'error'
	StatusConnection = 'connection'

	TypeMovie = 'movie'
	TypeShow = 'show'

	StreamTorrent = 'torrent'
	StreamUsenet = 'usenet'
	StreamHoster = 'hoster'

	AudioStandard = 'standard'
	AudioDubbed = 'dubbed'

	SubtitleSoft = 'soft'
	SubtitleHard = 'hard'

	VoteUp = 'up'
	VoteDown = 'down'

	DebridPremiumize = 'premiumize'
	DebridOffcloud = 'offcloud'
	DebridRealdebrid = 'realdebrid'
	DebridDebridlink = 'debridlink'
	DebridAlldebrid = 'alldebrid'

	FileOriginal = 'original'
	FileStream = 'stream'
	FileSequential = 'sequential'

	OutputList = 'list'
	OutputChoice = 'choice'
	OutputExpression = 'expression'
	OutputDomain = 'domain'

	DataJson = 'json'
	DataRaw = 'raw'
	DataBoth = 'both'

	AddonKodi = 'kodi'

	Last = None
	Error = {}

	##############################################################################
	# CONSTRUCTOR
	##############################################################################

	def __init__(self):
		self.mStatus = None
		self.mType = None
		self.mDescription = None
		self.mMessage = None
		self.mData = None

	##############################################################################
	# DESTRUCTOR
	##############################################################################

	def __del__(self):
		pass

	##############################################################################
	# INTERNAL
	##############################################################################

	@classmethod
	def _keyInternal(self, key = None):
		value = OrionSettings.getString('internal.api.orion', raw = True, obfuscate = True)
		if not value:
			if OrionSettings.adapt():
				value = OrionSettings.getString('internal.api.orion', raw = True, obfuscate = True)
			if not value:
				OrionInterface.dialogConfirm(message = 33038)
				OrionTools.quit()
		if key: return key == value
		else: return value

	@classmethod
	def _keyWeb(self, key):
		value = '0' * 8
		return key and key.startswith(value) and key.endswith(value)

	@classmethod
	def _keyHidden(self, key):
		return self._keyInternal(key = key) or self._keyWeb(key = key)

	def _logMessage(self):
		result = []
		if not self.mStatus is None: result.append(self.mStatus)
		if not self.mType is None: result.append(self.mType)
		if not self.mDescription is None: result.append(self.mDescription)
		if not self.mMessage is None: result.append(self.mMessage)
		return ' | '.join(result)

	##############################################################################
	# REQUEST
	##############################################################################

	def _request(self, mode = None, action = None, parameters = {}, data = DataJson, silent = False):
		self.mStatus = None
		self.mType = None
		self.mDescription = None
		self.mMessage = None
		self.mData = None

		result = None
		networker = None
		identifier = ''

		debug = not OrionSettings.silentDebug()
		if mode == OrionApi.ModeStream and action == OrionApi.ActionUpdate: debug = False

		try:
			app = [OrionTools.addonId(id = False), OrionTools.addonVersion(id = False), OrionTools.addonName(id = False)]
			app = ' | '.join([i if i else '' for i in app])

			if not mode is None: parameters[OrionApi.ParameterMode] = mode
			if not action is None: parameters[OrionApi.ParameterAction] = action

			from orion.modules.orionapp import OrionApp
			keyApp = OrionApp.instance().key()

			# Use the internal API key for retrieving settings backups.
			# Otherwise if Orion is authenticated from a third-party addon and then asked if the online settings should be imported, the import fails since the current addon's API key is used which probably does not have permission for this.
			if (keyApp is None and mode == OrionApi.ModeApp and action == OrionApi.ActionRetrieve) or mode == OrionApi.ModeAddon: keyApp = self._keyInternal()
			if not keyApp is None and not keyApp == '': parameters[OrionApi.ParameterKeyApp] = keyApp

			from orion.modules.orionuser import OrionUser
			user = OrionUser.instance()
			keyUser = user.key()
			if not keyUser is None and not keyUser == '':
				# Do not add the user API key when authenticating using a QR code.
				# This can happen when a user has already authenticated an account previously (the previous API key is still available), and wants to reauthenticate  the account or authenticate a new account.
				# When adding a user API key in such a case, the API will assume it is an API call from the user entering the code on the website, and not an API call from Kodi that checks if the authentication was completed in intervals (OrionNavigator.settingsAccountCode()).
				# The API will then return an 'The authentication process failed.' error, causing the QR dialog to close.
				if not(mode == OrionApi.ModeUser and action == OrionApi.ActionAuthenticate):
					parameters[OrionApi.ParameterKeyUser] = keyUser
			else:
				token = user.token()
				if not token is None and not token == '': parameters[OrionApi.ParameterToken] = token

			parameters[OrionApi.ParameterVersion] = OrionTools.addonVersion()

			if debug:
				query = copy.deepcopy(parameters)
				if query:
					truncate = [OrionApi.ParameterId, OrionApi.ParameterPassword, OrionApi.ParameterKey, OrionApi.ParameterKeyApp, OrionApi.ParameterKeyUser, OrionApi.ParameterToken, OrionApi.ParameterData, OrionApi.ParameterLink, OrionApi.ParameterLinks, OrionApi.ParameterFiles, OrionApi.ParameterItem, OrionApi.ParameterHash, OrionApi.ParameterContainer, OrionApi.ParameterContainerData]
					for key, value in OrionTools.iterator(query):
						if key in truncate: query[key] = '-- truncated --'
				queryString = OrionTools.jsonTo(query)
				identifier = ' [' + OrionTools.hash(queryString)[:5] + ']'
				OrionTools.log('Orion API Request' + identifier + ': ' + queryString)

			timeout = 90
			if OrionSettings.getBoolean('general.connection.custom'):
				timeout = max(20, OrionSettings.getInteger('general.connection.timeout'))

			networker = OrionNetworker(
				link = OrionTools.linkApi(),
				parameters = parameters,
				headers = {'Premium' : 1 if user.subscriptionPackagePremium() else 0, 'App' : app},
				timeout = timeout,
				agent = OrionNetworker.AgentOrion,
				debug = debug
			)

			result = networker.request()

			# No internet connection or domain name issues.
			if not result and networker.errorTypeNetwork():
				if not silent and OrionSettings.silentAllow(self.mType):
					if networker.errorCodeConnection(): message = 33071
					elif networker.errorCodeResolve(): message = 33072
					else: message = 33073
					OrionInterface.dialogNotification(title = 32320, message = message, icon = OrionInterface.IconError)
				self.mStatus = OrionApi.StatusError
				OrionApi.Last = {'status' : self.mStatus, 'type' : OrionApi.StatusConnection, 'description' : None, 'message' : None}
				return self.statusSuccess()

			if data == self.DataBoth:
				if not OrionTools.jsonIs(result): return result
			elif data == self.DataRaw:
				return {'status' : networker.status(), 'headers' : networker.headersResponse(), 'body' : result, 'response' : networker.response()}
			json = OrionTools.jsonFrom(result)

			result = json[OrionApi.ParameterResult]
			if OrionApi.ParameterStatus in result: self.mStatus = result[OrionApi.ParameterStatus]
			if OrionApi.ParameterType in result: self.mType = result[OrionApi.ParameterType]
			if OrionApi.ParameterDescription in result: self.mDescription = result[OrionApi.ParameterDescription]
			if OrionApi.ParameterMessage in result: self.mMessage = result[OrionApi.ParameterMessage]
			OrionApi.Last = {'status' : self.mStatus, 'type' : self.mType, 'description' : self.mDescription, 'message' : self.mMessage}

			if OrionApi.ParameterData in json: self.mData = json[OrionApi.ParameterData]

			time = OrionTools.timestamp()
			notify = not silent and OrionSettings.silentAllow(self.mStatus)
			if self.mStatus == OrionApi.StatusError:
				if debug:
					OrionTools.log('Orion API Error' + identifier + ': ' + self._logMessage())
				if not silent and OrionSettings.silentAllow(self.mType):
					allow = True

					# Do not show multiple notifications if multiple debrid lookups or resolves are done within 60 seconds.
					# Multiple debrid lookups: multiple threads with chunks of hashes.
					# Multiple debrid resolves: sequential playback.
					if mode == OrionApi.ModeDebrid and (action == OrionApi.ActionLookup or action == OrionApi.ActionResolve):
						if mode in OrionApi.Error and action in OrionApi.Error[mode]:
							if time - OrionApi.Error[mode][action]['time'] < (60 if action == OrionApi.ActionLookup else 15): allow = False

					if allow: OrionInterface.dialogNotification(title = 32048, message = self.mDescription, icon = OrionInterface.IconError)
				if not mode in OrionApi.Error: OrionApi.Error[mode] = {}
				OrionApi.Error[mode][action] = {'status' : self.mStatus, 'type' : self.mType, 'description' : self.mDescription, 'message' : self.mMessage, 'time' : time}
			elif self.mStatus == OrionApi.StatusSuccess:
				if debug:
					OrionTools.log('Orion API Success' + identifier + ': ' + self._logMessage())
				if mode == OrionApi.ModeStream:
					if action == OrionApi.ActionVote:
						if notify: OrionInterface.dialogNotification(title = 32202, message = 33029, icon = OrionInterface.IconSuccess)
					elif action == OrionApi.ActionRemove:
						if notify: OrionInterface.dialogNotification(title = 32203, message = 33030, icon = OrionInterface.IconSuccess)
					elif action == OrionApi.ActionRetrieve:
						count = self.mData[OrionApi.ParameterCount]
						message = OrionTools.translate(32062) + ': ' + str(count[OrionApi.ParameterTotal]) + ' • ' + OrionTools.translate(32063) + ': ' + str(count[OrionApi.ParameterRetrieved])
						if debug: OrionTools.log('Orion Streams Found' + identifier + ': ' + message)
						if notify:
							notifications = []
							if self.mDescription: notifications.append({'title' : self.mDescription, 'message' : self.mMessage, 'icon' : OrionInterface.IconInformation})
							notifications.append({'title' : 32060, 'message' : message, 'icon' : OrionInterface.IconSuccess})
							thread = threading.Thread(target = self._notification, args = (notifications,))
							thread.start()
				elif mode == OrionApi.ModeContainer:
					if action == OrionApi.ActionRetrieve:
						count = self.mData[OrionApi.ParameterCount]
						message = OrionTools.translate(32232) + ': ' + str(count[OrionApi.ParameterRequested]) + ' • ' + OrionTools.translate(32233) + ': ' + str(count[OrionApi.ParameterRetrieved])
						if debug: OrionTools.log('Orion Containers Found' + identifier + ': ' + message)
					elif action == OrionApi.ActionHash:
						count = self.mData[OrionApi.ParameterCount]
						message = OrionTools.translate(32228) + ': ' + str(count[OrionApi.ParameterRequested]) + ' • ' + OrionTools.translate(32229) + ': ' + str(count[OrionApi.ParameterRetrieved])
						if debug: OrionTools.log('Orion Hashes Found' + identifier + ': ' + message)
						# Do not show a notification if hashes are found, especailly if they are requested in chunks, too many popups.
						#if notify: OrionInterface.dialogNotification(title = 32227, message = message, icon = OrionInterface.IconSuccess)
		except:
			try:
				self.mStatus = OrionApi.StatusError
				if not networker is None and networker.error() and not silent and debug:
					if not(mode == OrionApi.ModeStream and action == OrionApi.ActionUpdate):
						OrionInterface.dialogNotification(title = 32064, message = 33007, icon = OrionInterface.IconNativeWarning)
				else:
					if debug:
						OrionTools.error('Orion API Exception' + identifier + '')
						OrionTools.log('Orion API Data' + identifier + ': ' + str(result))
					if not silent and OrionSettings.silentAllow('exception'):
						OrionInterface.dialogNotification(title = 32061, message = 33006, icon = OrionInterface.IconError)
				OrionApi.Last = {'status' : self.mStatus, 'type' : OrionApi.StatusConnection, 'description' : None, 'message' : None}
			except:
				OrionTools.error('Orion Unknown API Exception' + identifier)

		return self.statusSuccess()

	##############################################################################
	# NOTIFICATION
	##############################################################################

	@classmethod
	def _notification(self, notifications):
		time = 5000
		single = len(notifications) <= 1
		for notification in notifications:
			OrionInterface.dialogNotification(title = notification['title'], message = notification['message'], icon = notification['icon'], time = time)
			if not single: OrionTools.sleep(time / 1000.0)

	##############################################################################
	# LAST
	##############################################################################

	@classmethod
	def last(self):
		try: return OrionApi.Last
		except: return None

	@classmethod
	def lastStatus(self):
		try: return OrionApi.Last['status']
		except: return None

	@classmethod
	def lastStatusSuccess(self):
		try: return OrionApi.Last['status'] == OrionApi.StatusSuccess
		except: return None

	@classmethod
	def lastStatusError(self):
		try: return OrionApi.Last['status'] == OrionApi.StatusError
		except: return None

	@classmethod
	def lastType(self):
		try: return OrionApi.Last['type']
		except: return None

	@classmethod
	def lastTypeConnection(self):
		try: return OrionApi.Last['type'] == OrionApi.StatusConnection
		except: return None

	@classmethod
	def lastTypeAuthentication(self):
		try: return OrionApi.Last['type'] in OrionApi.TypesAuthentication
		except: return None

	@classmethod
	def lastTypeSubscription(self):
		try: return OrionApi.Last['type'] in OrionApi.TypesSubscription
		except: return None

	@classmethod
	def lastDescription(self):
		try: return OrionApi.Last['description']
		except: return None

	@classmethod
	def lastMessage(self):
		try: return OrionApi.Last['message']
		except: return None

	##############################################################################
	# STATUS
	##############################################################################

	def status(self):
		return self.mStatus

	def statusHas(self):
		return not self.mStatus is None

	def statusSuccess(self):
		return self.mStatus == OrionApi.StatusSuccess

	def statusError(self):
		return self.mStatus == OrionApi.StatusError

	##############################################################################
	# ERROR
	##############################################################################

	def errorUserKey(self):
		return self.statusError() and self.type() == OrionApi.ErrorUserKey

	##############################################################################
	# TYPE
	##############################################################################

	def type(self):
		return self.mType

	def typeHas(self):
		return not self.mType is None

	##############################################################################
	# DESCRIPTION
	##############################################################################

	def description(self):
		return self.mDescription

	def descriptionHas(self):
		return not self.mDescription is None

	##############################################################################
	# MESSAGE
	##############################################################################

	def message(self):
		return self.mMessage

	def messageHas(self):
		return not self.mMessage is None

	##############################################################################
	# DATA
	##############################################################################

	def data(self):
		return self.mData

	def dataHas(self):
		return not self.mData is None

	##############################################################################
	# RANGE
	##############################################################################

	@classmethod
	def range(self, value):
		if OrionTools.isArray(value):
			result = ''
			if len(value) == 0: return result
			if len(value) > 1 and not value[0] is None: result += str(value[0])
			result += '_'
			if len(value) > 1 and not value[1] is None: result += str(value[1])
			elif len(value) == 1: result += str(value[0])
			return result
		else:
			return str(value)

	##############################################################################
	# APP
	##############################################################################

	def appRetrieve(self, id = None, key = None):
		single = False
		if not id is None:
			single = OrionTools.isString(id)
			result = self._request(mode = OrionApi.ModeApp, action = OrionApi.ActionRetrieve, parameters = {OrionApi.ParameterId : id})
		elif not key is None:
			single = OrionTools.isString(key)
			result = self._request(mode = OrionApi.ModeApp, action = OrionApi.ActionRetrieve, parameters = {OrionApi.ParameterKey : key})
		else:
			result = self._request(mode = OrionApi.ModeApp, action = OrionApi.ActionRetrieve, parameters = {OrionApi.ParameterAll : True})
		try:
			if single: self.mData = self.mData[0]
			elif OrionTools.isDictionary(self.mData): self.mData = [self.mData]
		except: pass
		return result

	##############################################################################
	# USER
	##############################################################################

	def userRetrieve(self):
		return self._request(mode = OrionApi.ModeUser, action = OrionApi.ActionRetrieve)

	def userLogin(self, user, password):
		return self._request(mode = OrionApi.ModeUser, action = OrionApi.ActionLogin, parameters = {OrionApi.ParameterUser : user, OrionApi.ParameterPassword : password})

	def userAuthenticate(self, code = None):
		parameters = {}
		if code: parameters[OrionApi.ParameterCode] = code
		return self._request(mode = OrionApi.ModeUser, action = OrionApi.ActionAuthenticate, parameters = parameters)

	def userAnonymous(self):
		x = [OrionTools.randomInteger(1,9) for i in range(3)]
		return self._request(mode = OrionApi.ModeUser, action = OrionApi.ActionAnonymous, parameters = {OrionApi.ParameterKey : str(str(x[0])+str(x[1])+str(x[2])+str(x[0]+x[1]*x[2]))[::-1]}, silent = False)

	##############################################################################
	# TICKET
	##############################################################################

	def ticketRetrieve(self, id = None):
		parameters = {}
		if not id is None: parameters[OrionApi.ParameterId] = id
		return self._request(mode = OrionApi.ModeTicket, action = OrionApi.ActionRetrieve, parameters = parameters)

	def ticketAdd(self, category, subject, message, files = None):
		parameters = {OrionApi.ParameterCategory : category, OrionApi.ParameterSubject : subject, OrionApi.ParameterMessage : message}
		if not files is None: parameters[OrionApi.ParameterFiles] = files
		return self._request(mode = OrionApi.ModeTicket, action = OrionApi.ActionAdd, parameters = parameters)

	def ticketUpdate(self, id, message, files = None):
		parameters = {OrionApi.ParameterId : id, OrionApi.ParameterMessage : message}
		if not files is None: parameters[OrionApi.ParameterFiles] = files
		return self._request(mode = OrionApi.ModeTicket, action = OrionApi.ActionUpdate, parameters = parameters)

	def ticketClose(self, id):
		from orion.modules.orionticket import OrionTicket
		return self._request(mode = OrionApi.ModeTicket, action = OrionApi.ActionUpdate, parameters = {OrionApi.ParameterId : id, OrionApi.ParameterStatus : OrionTicket.StatusClosed})

	def ticketStatus(self):
		return self._request(mode = OrionApi.ModeTicket, action = OrionApi.ActionStatus)

	##############################################################################
	# COUPON
	##############################################################################

	def couponRedeem(self, code):
		return self._request(mode = OrionApi.ModeCoupon, action = OrionApi.ActionRedeem, parameters = {OrionApi.ParameterCode : code})

	##############################################################################
	# ADDON
	##############################################################################

	def addonRetrieve(self, silent = True):
		return self._request(mode = OrionApi.ModeAddon, action = OrionApi.ActionRetrieve, parameters = {OrionApi.ParameterType : OrionApi.AddonKodi}, silent = silent)

	def addonUpdate(self, data, silent = True):
		return self._request(mode = OrionApi.ModeAddon, action = OrionApi.ActionUpdate, parameters = {OrionApi.ParameterType : OrionApi.AddonKodi, OrionApi.ParameterData : data}, silent = silent)

	def addonVersion(self, silent = True):
		return self._request(mode = OrionApi.ModeAddon, action = OrionApi.ActionVersion, silent = silent)

	##############################################################################
	# STREAM
	##############################################################################

	def streamRetrieve(self, filters):
		return self._request(mode = OrionApi.ModeStream, action = OrionApi.ActionRetrieve, parameters = {OrionApi.ParameterData : filters})

	def streamUpdate(self, item):
		return self._request(mode = OrionApi.ModeStream, action = OrionApi.ActionUpdate, parameters = {OrionApi.ParameterData : item})

	def streamVote(self, item, stream, vote = VoteUp, automatic = False, silent = True):
		return self._request(mode = OrionApi.ModeStream, action = OrionApi.ActionVote, parameters = {OrionApi.ParameterItem : item, OrionApi.ParameterStream : stream, OrionApi.ParameterDirection : vote, OrionApi.ParameterAutomatic : automatic}, silent = silent)

	def streamRemove(self, item, stream, automatic = False, silent = True):
		return self._request(mode = OrionApi.ModeStream, action = OrionApi.ActionRemove, parameters = {OrionApi.ParameterItem : item, OrionApi.ParameterStream : stream, OrionApi.ParameterAutomatic : automatic}, silent = silent)

	##############################################################################
	# CONTAINER
	##############################################################################

	def containerRetrieve(self, links):
		return self._request(mode = OrionApi.ModeContainer, action = OrionApi.ActionRetrieve, parameters = {OrionApi.ParameterLinks : links})

	def containerIdentifier(self, links):
		return self._request(mode = OrionApi.ModeContainer, action = OrionApi.ActionIdentifier, parameters = {OrionApi.ParameterLinks : links})

	def containerHash(self, links):
		return self._request(mode = OrionApi.ModeContainer, action = OrionApi.ActionHash, parameters = {OrionApi.ParameterLinks : links})

	def containerSegment(self, links):
		return self._request(mode = OrionApi.ModeContainer, action = OrionApi.ActionSegment, parameters = {OrionApi.ParameterLinks : links})

	def containerDownload(self, id):
		data = self._request(mode = OrionApi.ModeContainer, action = OrionApi.ActionDownload, parameters = {OrionApi.ParameterId : id}, data = self.DataBoth)
		return None if OrionTools.isBoolean(data) else data

	##############################################################################
	# DEBRID
	##############################################################################

	def debridSupport(self, idItem = None, idStream = None, link = None, type = None, status = None, globally = None, output = None):
		parameters = {}
		if idItem: parameters[OrionApi.ParameterIdItem] = idItem
		if idStream: parameters[OrionApi.ParameterIdStream] = idStream
		if link: parameters[OrionApi.ParameterLink] = link
		if type: parameters[OrionApi.ParameterType] = type
		if status: parameters[OrionApi.ParameterStatus] = status
		if globally: parameters[OrionApi.ParameterGlobal] = globally
		if output: parameters[OrionApi.ParameterOutput] = output
		return self._request(mode = OrionApi.ModeDebrid, action = OrionApi.ActionSupport, parameters = parameters)

	def debridLookup(self, idItem = None, idStream = None, link = None, hash = None, item = None, type = None, refresh = False):
		parameters = {OrionApi.ParameterRefresh : refresh}
		if idItem: parameters[OrionApi.ParameterIdItem] = idItem
		if idStream: parameters[OrionApi.ParameterIdStream] = idStream
		if link: parameters[OrionApi.ParameterLink] = link
		if hash: parameters[OrionApi.ParameterHash] = hash
		if item: parameters[OrionApi.ParameterItem] = item
		if type: parameters[OrionApi.ParameterType] = type
		return self._request(mode = OrionApi.ModeDebrid, action = OrionApi.ActionLookup, parameters = parameters)

	def debridResolve(self, idItem = None, idStream = None, link = None, type = None, file = None, output = None, ip = None, container = None, containerData = None, containerName = None, containerType = None, containerSize = None):
		parameters = {}
		if idItem: parameters[OrionApi.ParameterIdItem] = idItem
		if idStream: parameters[OrionApi.ParameterIdStream] = idStream
		if link: parameters[OrionApi.ParameterLink] = link
		if type: parameters[OrionApi.ParameterType] = type
		if file: parameters[OrionApi.ParameterFile] = file
		if output: parameters[OrionApi.ParameterOutput] = output
		if ip: parameters[OrionApi.ParameterIp] = ip

		if containerData: parameters[OrionApi.ParameterContainerData] = OrionTools.base64To(containerData)
		elif container: parameters[OrionApi.ParameterContainer] = OrionTools.base64To(container)
		if containerName: parameters[OrionApi.ParameterContainerName] = containerName
		if containerType: parameters[OrionApi.ParameterContainerType] = containerType
		if containerSize: parameters[OrionApi.ParameterContainerSize] = containerSize

		return self._request(mode = OrionApi.ModeDebrid, action = OrionApi.ActionResolve, parameters = parameters)

	##############################################################################
	# NOTIFICATION
	##############################################################################

	def notificationRetrieve(self, time = None, count = None):
		parameters = {}
		parameters[OrionApi.ParameterVersion] = OrionTools.addonVersion()
		if not time is None: parameters[OrionApi.ParameterTime] = time
		if not count is None: parameters[OrionApi.ParameterCount] = count
		return self._request(mode = OrionApi.ModeNotification, action = OrionApi.ActionRetrieve, parameters = parameters)

	##############################################################################
	# PROMOTION
	##############################################################################

	def promotionRetrieve(self):
		return self._request(mode = OrionApi.ModePromotion, action = OrionApi.ActionRetrieve)

	##############################################################################
	# SERVER
	##############################################################################

	def serverRetrieve(self, time = None):
		parameters = {}
		if not time is None: parameters[OrionApi.ParameterTime] = time
		return self._request(mode = OrionApi.ModeServer, action = OrionApi.ActionRetrieve, parameters = parameters)

	def serverTest(self):
		return self._request(mode = OrionApi.ModeServer, action = OrionApi.ActionTest)
