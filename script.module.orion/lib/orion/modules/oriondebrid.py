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
# ORIONDEBRID
##############################################################################
# Class for managing Orion debrid features.
##############################################################################

from orion.modules.orionapi import *

class OrionDebrid:

	TypePremiumize = OrionApi.DebridPremiumize
	TypeOffcloud = OrionApi.DebridOffcloud
	TypeRealdebrid = OrionApi.DebridRealdebrid
	TypeDebridlink = OrionApi.DebridDebridlink
	TypeAlldebrid = OrionApi.DebridAlldebrid

	FileOriginal = OrionApi.FileOriginal
	FileStream = OrionApi.FileStream
	FileSequential = OrionApi.FileSequential

	OutputList = OrionApi.OutputList
	OutputChoice = OrionApi.OutputChoice
	OutputExpression = OrionApi.OutputExpression
	OutputDomain = OrionApi.OutputDomain

	##############################################################################
	# SUPPORT
	##############################################################################

	@classmethod
	def support(self, idItem = None, idStream = None, link = None, type = None, status = None, globally = None, output = None):
		api = OrionApi()
		api.debridSupport(idItem = idItem, idStream = idStream, link = link, type = type, status = status, globally = globally, output = output)
		return api.data()

	##############################################################################
	# LOOKUP
	##############################################################################

	@classmethod
	def lookup(self, idItem = None, idStream = None, link = None, hash = None, item = None, type = None, refresh = None):
		if refresh is None:
			if idItem and idStream: refresh = False
			else: refresh = True
		api = OrionApi()
		api.debridLookup(idItem = idItem, idStream = idStream, link = link, hash = hash, item = item, type = type, refresh = refresh)
		return api.data()

	##############################################################################
	# RESOLVE
	##############################################################################

	@classmethod
	def resolve(self, idItem = None, idStream = None, link = None, type = None, file = None, output = None, ip = None, container = None, containerData = None, containerName = None, containerType = None, containerSize = None):
		api = OrionApi()
		api.debridResolve(idItem = idItem, idStream = idStream, link = link, type = type, file = file, output = output, ip = ip, container = container, containerData = containerData, containerName = containerName, containerType = containerType, containerSize = containerSize)
		return api.data()
