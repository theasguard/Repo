# -*- coding: utf-8 -*-

'''
	Orion Addon

	THE BEERWARE LICENSE (Revision 42)
	Orion (orionoid.com) wrote this file. As long as you retain this notice you
	can do whatever you want with this stuff. If we meet some day, and you think
	this stuff is worth it, you can buy me a beer in return.
'''

try: from resources.modules.general import Addon
except: import Addon

import re
import sys
import xbmc

from orion import *
from orion.modules.oriontools import *
from orion.modules.orionnetworker import *

global global_var, stop_all
global_var = []
stop_all = 0
type=['movie', 'tv', 'torrent']

key = 'VTNsQ1JFbEdVV2RWUTBKWFNVVlZaMVpEUWtsSlJVMW5WR2xDU1VsRlJXZFNlVUpKU1VWRloxUlRRbE5KUlVsblZrTkNSVWxGYjJkVFEwSkxTVVZ2WjA5VFFrSkpSVmxuVTBOQ1FrbEZkMmRYUTBKRA=='

def _error():
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
	xbmc.log('KODIVERSE ORION [ERROR]: ' + parameters, xbmc.LOGERROR)

def _default(data):
	return '' if data is None else data

def _link(data):
	links = data['links']
	for link in links:
		if link.lower().startswith('magnet:'):
			return link
	return links[0]

def _name(data):
	return _default(data['file']['name'])

def _quality(data):
	try:
		quality = data['video']['quality']
		if quality in [Orion.QualityHd8k, Orion.QualityHd6k, Orion.QualityHd4k]:
			return '2160'
		elif quality in [Orion.QualityHd2k]:
			return '1440'
		elif quality in [Orion.QualityHd1080]:
			return '1080'
		elif quality in [Orion.QualityHd720]:
			return '720'
		elif quality in [Orion.QualityScr1080, Orion.QualityScr720, Orion.QualityScr]:
			return 'scr'
		elif quality in [Orion.QualityCam1080, Orion.QualityCam720, Orion.QualityCam]:
			return 'cam'
	except: pass
	return 'hd'

def _provider(data):
	try: return data['stream']['source']
	except: return None

def _size(data):
	size = data['file']['size']
	if size: return size / 1073741824.0
	else: return 0

def get_links(tv_movie, original_title, season_n, episode_n, season, episode, show_original_year, id):
	global global_var, key

	sources = []
	try:
		orion = Orion(OrionTools.base64From(OrionTools.base64From(OrionTools.base64From(key))).replace(' ', ''))
		if not orion.userEnabled() or not orion.userValid(): raise Exception()

		isMovie = tv_movie == 'movie'
		isShow = tv_movie == 'tv'
		type = Orion.TypeShow if isShow else Orion.TypeMovie
	
		try: year = int(show_original_year)
		except: year = None

		if isShow:
			try: season = int(season)
			except: pass
			try: episode = int(episode)
			except: pass

		query = None
		if original_title:
			query = original_title
			if isMovie and year: query += ' %s' % str(year)
			elif isShow and season and episode: query += ' S%02dE%02d' % (season, episode)
		
		results = orion.streams(
			type = type,
			query = query,
			idTmdb = id,
			numberSeason = season,
			numberEpisode = episode,
			streamType = orion.streamTypes([OrionStream.TypeTorrent]),
			protocolTorrent = Orion.ProtocolMagnet
		)

		if results:
			sizeLimit = int(Addon.getSetting('size_limit'))
			for data in results:
				try:
					size = _size(data)
					if size < sizeLimit: sources.append((_name(data), _link(data), str(size), _quality(data)))
				except: _error()
	except: _error()
	global_var = sources
	return global_var
