# -*- coding: utf-8 -*-

'''
	Orion Addon

	THE BEERWARE LICENSE (Revision 42)
	Orion (orionoid.com) wrote this file. As long as you retain this notice you
	can do whatever you want with this stuff. If we meet some day, and you think
	this stuff is worth it, you can buy me a beer in return.
'''

import logging
from orion import *
from orion.modules.orionnetworker import *
import threading
import urllib.parse
import base64
import time
import sys
import re
import xbmc
import kodi
from . import scraper
from . import proxy
from asguard_lib import scraper_utils
from asguard_lib.constants import VIDEO_TYPES
from asguard_lib.constants import QUALITIES
from asguard_lib.constants import HOST_Q
import log_utils

logger = log_utils.Logger.get_logger()

BASE_URL = 'https://orionoid.com'

class Scraper(scraper.Scraper):
	base_url = BASE_URL

	CacheLimit = 100
	PremiumizeLink = 'https://www.premiumize.me/api/torrent/checkhashes'

	def __init__(self, timeout = scraper.DEFAULT_TIMEOUT):
		self.base_url = kodi.get_setting('%s-base_url' % (self.get_name()))
		self.key = 'VDBOQ1IwbEdSV2RYVTBKR1NVVm5aMVJwUWxsSlJXOW5WME5CTWtsR1JXZFZhVUpMU1VWbloxSjVRbEpKUlhkblZHbENUVWxGVVdkU1UwSlNTVVZKWjFOcFFrMUpSR3RuVW5sQ1dVbEZZMmRQVTBKUA=='
		self.hosts = self._hosts()

	@classmethod
	def provides(self):
		return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

	@classmethod
	def get_name(self):
		return 'Orion'

	@classmethod
	def _hosts(self):
		hosts = []
		for key, value in HOST_Q.items():
			hosts.extend(value)
		hosts = [i.lower() for i in hosts]
		return hosts

	def _link(self, data, orion = False):
		links = data['links']
		for link in links:
			if link.lower().startswith('magnet:') or link.lower().startswith('http'):
				return link
		if orion:
			for link in links:
				if 'orionoid.com' in link.lower():
					return link
		return links[0]

	def _quality(self, data):
		try:
			quality = data['video']['quality']
			if quality in [Orion.QualityHd8k, Orion.QualityHd6k, Orion.QualityHd4k, Orion.QualityHd2k]:
				return QUALITIES.HD4K
			elif quality in [Orion.QualityHd1080]:
				return QUALITIES.HD1080
			elif quality in [Orion.QualityHd720]:
				return QUALITIES.HD720
			elif quality in [Orion.QualityScr1080, Orion.QualityScr720, Orion.QualityScr]:
				return QUALITIES.MEDIUM
			elif quality in [Orion.QualityCam1080, Orion.QualityCam720, Orion.QualityCam]:
				return QUALITIES.LOW
		except: pass
		return QUALITIES.HIGH

	def _language(self, data):
		try:
			language = data['audio']['language']
			if 'en' in language: return 'en'
			return language[0]
		except: return 'en'

	def _source(self, data, label = True):
		if label:
			try: hoster = data['stream']['hoster']
			except: hoster = None
			if hoster: return hoster
			try: source = data['stream']['source']
			except: source = None
			return source if source else ''
		else:
			try: return data['stream']['source']
			except: return None

	def _days(self, data):
		try: days = (time.time() - data['time']['updated']) / 86400.0
		except: days = 0
		days = int(days)
		return str(days) + ' Day' + ('' if days == 1 else 's')

	def _popularity(self, data, percent = True):
		if percent:
			try: return data['popularity']['percent'] * 100
			except: return None
		else:
			try: return data['popularity']['count']
			except: return None

	def _domain(self, data):
		elements = urllib.parse.urlparse(self._link(data))
		domain = elements.netloc or elements.path
		domain = domain.split('@')[-1].split(':')[0]
		result = re.search('(?:www\.)?([\w\-]*\.[\w\-]{2,3}(?:\.[\w\-]{2,3})?)$', domain)
		if result: domain = result.group(1)
		return domain.lower()

	def _valid(self, data):
		if data['access']['direct']:
			return True
		elif data['stream']['type'] == Orion.StreamTorrent:
			return True
		elif data['stream']['type'] == Orion.StreamUsenet:
			return True
		elif data['stream']['type'] == Orion.StreamHoster:
			return True
		elif data['stream']['type'] == Orion.streamOrigin:
			return True
		else:
			domain = self._domain(data)
			for host in self.hosts:
				if domain.startswith(host) or host.startswith(domain):
					return True
			import resolveurl
			return resolveurl.HostedMediaFile(self._link(data)).valid_url()

	def _premiumizeParameters(self, parameters = None):
		from resolveurl.plugins.premiumize_me import PremiumizeMeResolver
		if parameters: parameters = [urllib.parse.urlencode(parameters, doseq = True)]
		else: parameters = []
		parameters.append(urllib.parse.urlencode({'access_token' : PremiumizeMeResolver.get_setting('token')}, doseq = True))
		return '&'.join(parameters)

	def _premiumizeRequest(self, link, parameters = None):
		networker = OrionNetworker(link = link, parameters = parameters, timeout = 60, agent = OrionNetworker.AgentOrion, debug = False, json = True)
		return networker.request()

	def _premiumizeCached(self, hashes):
		return self._premiumizeRequest(link = Scraper.PremiumizeLink, parameters = self._premiumizeParameters({'hashes[]' : hashes}))

	def _cached(self, sources):
		try:
			hashes = []
			for i in sources:
				try:
					if i['stream']['type'] == Orion.StreamTorrent:
						hash = i['file']['hash']
						if hash: hashes.append(hash)
				except: pass
			chunks = [hashes[i:i + Scraper.CacheLimit] for i in range(0, len(hashes), Scraper.CacheLimit)]
			threads = [threading.Thread(target = self._cachedCheck, args = (i,)) for i in chunks]
			self.cachedHashes = []
			self.cachedLock = threading.Lock()
			[i.start() for i in threads]
			[i.join() for i in threads]
			for i in range(len(sources)):
				sources[i]['cached'] = False
			for i in range(len(sources)):
				try:
					if sources[i]['file']['hash'] in self.cachedHashes:
						sources[i]['cached'] = True
				except: pass
		except Exception as e:
			logger.log('Orion: Error in caching check: %s' % str(e), log_utils.LOGWARNING)
		return sources

	def _cachedCheck(self, hashes):
		try:
			data = self._premiumizeCached(hashes = hashes)['hashes']
			self.cachedLock.acquire()
			for key, value in data.iteritems():
				if value['status'] == 'finished':
					self.cachedHashes.append(key)
			self.cachedLock.release()
		except Exception as e:
			logger.log('Orion: Error checking cached hashes: %s' % str(e), log_utils.LOGWARNING)

	def get_sources(self, video):
		sources = []
		try:
			# Decode the key properly
			decoded_key = base64.b64decode(base64.b64decode(base64.b64decode(self.key.encode('utf-8')))).decode('utf-8').replace(' ', '')
			orion = Orion(decoded_key)
			if not orion.userEnabled() or not orion.userValid(): 
				logger.log('Orion: User not enabled or invalid', log_utils.LOGWARNING)
				return sources

			# Use centralized IMDB ID retrieval from base class
			imdb_id = self.get_imdb_id(video)
			if not imdb_id:
				logger.log('Orion: No IMDB ID found for trakt_id: %s' % video.trakt_id, log_utils.LOGWARNING)
				return sources

			# Get all IDs for comprehensive Orion search
			all_ids = self.get_all_ids(video)
			
			type = Orion.TypeMovie if video.video_type == VIDEO_TYPES.MOVIE else Orion.TypeShow
			idTrakt = video.trakt_id
			idImdb = imdb_id
			idTmdb = all_ids.get('tmdb') if all_ids else None
			idTvdb = all_ids.get('tvdb') if all_ids else None
			numberSeason = None
			numberEpisode = None
			query = None

			if type == Orion.TypeShow:
				numberSeason = video.season
				numberEpisode = video.episode
				logger.log('Orion: Searching for episode: %s S%sE%s' % (imdb_id, video.season, video.episode), log_utils.LOGDEBUG)
			else:
				logger.log('Orion: Searching for movie: %s' % imdb_id, log_utils.LOGDEBUG)

			# Fallback query if no IDs available
			if type == Orion.TypeMovie and not idTrakt and not idImdb and not idTmdb:
				query = '%s %s' % (str(video.title), str(video.year))
			elif type == Orion.TypeShow and not idTrakt and not idImdb and not idTvdb:
				query = '%s S%sE%s' % (str(video.title), str(video.season), str(video.episode))

			logger.log('Orion: Requesting streams with IMDB: %s, TMDB: %s, TVDB: %s' % (idImdb, idTmdb, idTvdb), log_utils.LOGDEBUG)

			results = orion.streams(
				type = type,
				idTrakt = idTrakt,
				idImdb = idImdb,
				idTmdb = idTmdb,
				idTvdb = idTvdb,
				numberSeason = numberSeason,
				numberEpisode = numberEpisode,
				query = query,
			)

			logger.log('Orion: Found %d streams from API' % len(results), log_utils.LOGDEBUG)

			results = (results)
			for data in results:
				try:
					if self._valid(data):
						orion = {}
						try: orion['stream'] = data['id']
						except: pass
						try: orion['item'] = data
						except: pass

						stream = {
							'orion' : orion,
							'class' : self,
							'label' : data['file']['name'],
							'multi-part' : False,
							'host' : self._source(data, True),
							'quality' : self._quality(data),
							'language' : self._language(data),
							'url' : self._link(data, orion = True),
							'views' : self._popularity(data, False),
							'rating' : int(self._popularity(data, True)),
							'direct' : data['access']['direct'],
						}

						if data['video']['codec']:
							stream['format'] = data['video']['codec']

						if data['file']['size']:
							stream['size'] = scraper_utils.format_size(data['file']['size'])

						if data['video']['3d']:
							stream['3D'] = data['video']['3d']

						if data['subtitle']['languages'] and len(data['subtitle']['languages']) > 0:
							stream['subs'] = '-'.join(data['subtitle']['languages']).upper()

						sources.append(stream)
						logger.log('Orion: Added source: %s [%s]' % (data['file']['name'], self._source(data, True)), log_utils.LOGDEBUG)
				except Exception as e:
					logger.log('Orion: Error processing stream: %s' % str(e), log_utils.LOGWARNING)
					continue
		except Exception as e:
			logger.log('Orion: Unexpected error in get_sources: %s' % str(e), log_utils.LOGERROR)

		logger.log('Orion: Returning %d sources' % len(sources), log_utils.LOGDEBUG)
		return sources

	def resolve_link(self, link):
		return link

	def search(self, video_type, title, year, season = ''):
		"""
		Search method implementation for Orion scraper.
		Orion works best with IDs but can fallback to text search.
		"""
		logging.log('Orion: Text search not optimal - works best with Trakt/IMDB IDs', logging.LOGDEBUG)
		return []