# -*- coding: utf-8 -*-

'''
	Orion Addon

	THE BEERWARE LICENSE (Revision 42)
	Orion (orionoid.com) wrote this file. As long as you retain this notice you
	can do whatever you want with this stuff. If we meet some day, and you think
	this stuff is worth it, you can buy me a beer in return.
'''

from orion import *
from orion.modules.oriontools import *
from orion.modules.orionnetworker import *

import traceback
import sys
import os
import re
import xbmc
import xbmcvfs
import xbmcaddon

global global_var
global stop_all
global_var = []
stop_all = 0
type = ['movie', 'tv', 'torrent', 'api']

def get_links(tv_movie,original_title,season_n,episode_n,season,episode,show_original_year,id):
	if original_title == '%20': original_title = None
	if season_n == '%20': season_n = None
	if episode_n == '%20': episode_n = None
	if season == '%20': season = None
	if episode == '%20': episode = None
	if show_original_year == '%20': show_original_year = None
	if id == '%20': id = None

	idImdb = None
	idTmdb = None
	idTvdb = None
	if id and id.startswith('tt'): idImdb = id
	else: idTmdb = id # Seems like the ID is always from TMDb, for both movies and shows.

	if tv_movie == 'movie': type = Orion.TypeMovie
	else: type = Orion.TypeShow

	global global_var
	global_var = Orionoid().sources(type = type, title = original_title, year = show_original_year, idImdb = idImdb, idTmdb = idTmdb, idTvdb = idTvdb, numberSeason = season, numberEpisode = episode)
	return global_var


class Orionoid(object):

	TimeDays = 86400
	CacheLimit = 100

	SizeMegaByte = 1048576
	SizeGigaByte = 1073741824

	def __init__(self):
		self.addon = xbmcaddon.Addon('plugin.video.asgard')
		profile = xbmcvfs.translatePath(OrionTools.unicodeDecode(self.addon.getAddonInfo('profile')))
		try: os.mkdir(profile)
		except: pass
		self.cachePath = os.path.join(profile, 'orion.cache')
		self.cacheData = None
		self.key = 'VTNsQ1IwbEZVV2RTVTBKSlNVVlJaMUZUUWxsSlJHTm5VbE5DVTBsRlJXZFRhVUpPU1VWdloxUkRRa1JKUkdkblRtbENUMGxGVFdkUFUwSkVTVVpSWjFSRFFrbEpSVWxuVW1sQk5VbEdTV2RUUTBKTg=='

	def _error(self):
		type, value, trace = sys.exc_info()
		try: filename = trace.tb_frame.f_code.co_filename
		except: filename = None
		try: linenumber = trace.tb_lineno
		except: linenumber = None
		try: name = trace.tb_frame.f_code.co_name
		except: name = None
		try: errortype = type.__name__
		except: errortype = None
		try: errormessage = value.message
		except:
			try:
				import traceback
				errormessage = traceback.format_exception(type, value, trace)
			except: pass
		message = str(errortype) + ' -> ' + str(errormessage)
		parameters = [filename, linenumber, name, message]
		parameters = ' | '.join([str(parameter) for parameter in parameters])
		xbmc.log('ASGARD ORION [ERROR]: ' + parameters, xbmc.LOGERROR)

	def _cacheSave(self, data):
		self.cacheData = data
		OrionTools.fileWrite(self.cachePath, OrionTools.jsonTo(data))

	def _cacheLoad(self):
		if self.cacheData == None: self.cacheData = OrionTools.jsonFrom(OrionTools.fileRead(self.cachePath))
		return self.cacheData

	def _cacheFind(self, url):
		cache = self._cacheLoad()
		for i in cache:
			if i['url'] == url:
				return i
		return None

	def _link(self, data):
		links = data['links']
		for link in links:
			if link.lower().startswith('magnet:'):
				return link
		return links[0]

	def _quality(self, data):
		try:
			quality = data['video']['quality']
			if quality in [Orion.QualityHd8k, Orion.QualityHd6k, Orion.QualityHd4k]:
				return '2160'
			elif quality in [Orion.QualityHd1080]:
				return '1080'
			elif quality in [Orion.QualityHd720]:
				return '720'
			elif quality in [Orion.QualityScr1080, Orion.QualityScr720, Orion.QualityScr]:
				return '480'
			elif quality in [Orion.QualityCam1080, Orion.QualityCam720, Orion.QualityCam]:
				return '360'
		except: pass
		return '480'

	def _language(self, data):
		try:
			language = data['audio']['language']
			if 'en' in language: return 'en'
			return language[0]
		except: return 'en'

	def _source(self, data, label = True):
		if label:
			if data['stream']['type'] == Orion.StreamTorrent: return data['stream']['type']
			try: hoster = data['stream']['hoster']
			except: hoster = None
			if hoster: return hoster
			try: source = data['stream']['source']
			except: source = None
			return source if source else ''
		else:
			try: return data['stream']['source']
			except: return None

	def _size(self, data, string = True):
		size = data['file']['size']
		if size:
			if string:
				if size < Orionoid.SizeGigaByte: return '%d MB' % int(size / float(Orionoid.SizeMegaByte))
				else: return '%0.1f GB' % (size / float(Orionoid.SizeGigaByte))
			else:
				return size / float(Orionoid.SizeGigaByte)
		return None

	def _seeds(self, data):
		seeds = data['stream']['seeds']
		if seeds:
			seeds = int(seeds)
			return str(seeds) + ' Seed' + ('' if seeds == 1 else 's')
		return None

	def _days(self, data):
		try: days = (OrionTools.timestamp() - data['time']['updated']) / float(Orionoid.TimeDays)
		except: days = 0
		days = int(days)
		return str(days) + ' Day' + ('' if days == 1 else 's')

	def _popularity(self, data):
		try: popularity = data['popularity']['percent'] * 100
		except: popularity = 0
		return '+' + str(int(popularity)) + '%'

	def _domain(self, data):
		elements = OrionTools.urlParse(self._link(data))
		domain = elements.netloc or elements.path
		domain = domain.split('@')[-1].split(':')[0]
		result = re.search('(?:www\.)?([\w\-]*\.[\w\-]{2,3}(?:\.[\w\-]{2,3})?)$', domain)
		if result: domain = result.group(1)
		return domain.lower()

	def _name(self, data):
		try: return data['file']['name']
		except: return None

	def sources(self, type, title = None, year = None, idImdb = None, idTmdb = None, idTvdb = None, numberSeason = None, numberEpisode = None):
		sources = []
		try:
			orion = Orion(OrionTools.base64From(OrionTools.base64From(OrionTools.base64From(self.key))).replace(' ', ''))
			if not orion.userEnabled() or not orion.userValid(): raise Exception()

			sizeMaximum = None
			try:
				try: from resources.modules.general import Addon
				except: import Addon
				sizeMaximum = int(Addon.getSetting('size_limit'))
			except: pass

			query = None
			if title:
				query = title
				if type == Orion.TypeMovie and year: query += ' ' + str(year)

			results = orion.streams(
				type = type,
				query = query,
				idImdb = idImdb,
				idTmdb = idTmdb,
				idTvdb = idTvdb,
				numberSeason = numberSeason,
				numberEpisode = numberEpisode,
				streamType = orion.streamTypes([OrionStream.TypeTorrent, OrionStream.TypeHoster]),
				protocolTorrent = Orion.ProtocolMagnet
			)

			for data in results:
				try:
					orion = {}
					try: orion['stream'] = data['id']
					except: pass
					try: orion['item'] = data
					except: pass

					size = self._size(data, string = False)
					if size and sizeMaximum and size <= sizeMaximum:
						sources.append((
							self._name(data),
							self._link(data),
							str(size) if size else '0',
							self._quality(data)
						))
				except: self._error()
		except: self._error()

		self._cacheSave(sources)
		return sources
