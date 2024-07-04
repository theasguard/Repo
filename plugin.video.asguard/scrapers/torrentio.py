"""
    Asguard Addon
    Copyright (C) 2024
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
import logging
import re
import json
import urllib.parse
import requests
from asguard_lib.utils2 import i18n
import xbmcgui
import kodi
import log_utils
from asguard_lib import scraper_utils, control
from asguard_lib.constants import VIDEO_TYPES, QUALITIES
from . import scraper


try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)
    
logger = log_utils.Logger.get_logger()

class Scraper(scraper.Scraper):
    base_url = 'https://torrentio.strem.fun'
    movie_search_url = '/stream/movie/%s.json'
    tv_search_url = '/stream/series/%s:%s:%s.json'
    debrid_resolvers = resolveurl

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.min_seeders = 0
        self.bypass_filter = control.getSetting('Torrentio-bypass_filter') == 'true'
        self._set_apikeys()

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Torrentio'
    
    def resolve_link(self, link):
        logging.debug("Resolving link: %s", link)
        return link

    def _set_apikeys(self):
        self.pm_apikey = kodi.get_setting('premiumize.apikey')
        self.rd_apikey = kodi.get_setting('realdebrid.apikey')
        self.ad_apikey = kodi.get_setting('alldebrid_api_key')

    def get_sources(self, video):
        from asguard_lib.trakt_api import Trakt_API
        sources = []
        trakt_id = video.trakt_id

        try:
            if video.video_type == VIDEO_TYPES.MOVIE:
                if not hasattr(video, 'imdb_id'):
                    details = Trakt_API().get_movie_details(trakt_id)
                    video.imdb_id = details['ids']['imdb']
                search_url = self.movie_search_url % (video.imdb_id)
                logger.log('Searching for movie: %s' % search_url, log_utils.LOGDEBUG)
            else:
                if not all(hasattr(video, attr) for attr in ['imdb_id', 'season', 'episode']):
                    details = Trakt_API().get_show_details(trakt_id)
                    video.imdb_id = details['ids']['imdb']
                    video.season = video.season
                    video.episode = video.episode
                search_url = self.tv_search_url % (video.imdb_id, video.season, video.episode)
                logger.log('Searching for episode: %s' % search_url, log_utils.LOGDEBUG)

            url = urllib.parse.urljoin(self.base_url, search_url)
            response = self._http_get(url, cache_limit=1, require_debrid=True)
            if not response:
                return sources

            try:
                files = json.loads(response).get('streams', [])
                logger.log('Found %d files' % len(files), log_utils.LOGDEBUG)
            except json.JSONDecodeError as e:
                logger.log('Failed to parse JSON response from Torrentio: %s' % str(e), log_utils.LOGERROR)
                return sources

            for file in files:
                try:
                    hash = file['infoHash']
                    logger.log('Found file: %s' % hash, log_utils.LOGDEBUG)
                    name = file['title']
                    url = 'magnet:?xt=urn:btih:%s&dn=%s' % (hash, name)
                    logger.log('Found file: %s' % url, log_utils.LOGDEBUG)
                    seeders = int(file.get('seeds', 0))
                    if self.min_seeders > seeders:
                        continue

                    quality, info = scraper_utils.get_release_quality(name, url)
                    size_match = re.search(r'💾\s*([\d.]+)\s*(GB|MB)', name)
                    size = 0
                    if size_match:
                        size_value = float(size_match.group(1))
                        size_unit = size_match.group(2)
                        if size_unit == 'GB':
                            size = size_value * 1024  # Convert GB to MB
                        else:
                            size = size_value

                    info = ' | '.join(info)
                    label = f"{name} | {quality} | {size}MB | {seeders} seeders"
                    sources.append({
                        'host': 'magnet',
                        'label': label,
                        'multi-part': False,
                        'seeders': seeders,
                        'class': self,
                        'hash': hash,
                        'name': name,
                        'quality': quality,
                        'size': size,
                        'language': 'en',
                        'url': url,
                        'info': info,
                        'direct': False,
                        'debridonly': True
                    })
                except Exception as e:
                    logger.log('Error processing Torrentio source: %s' % str(e), log_utils.LOGERROR)
                    continue
                logger.log('Found source: %s' % sources, log_utils.LOGDEBUG)

        except AttributeError as e:
            logger.log('AttributeError: %s' % str(e), log_utils.LOGERROR)
        except Exception as e:
            logger.log('Unexpected error: %s' % str(e), log_utils.LOGERROR)

        return sources

    def _http_get(self, url, data=None, retry=True, allow_redirect=True, cache_limit=8, require_debrid=True):
        if require_debrid:
            if Scraper.debrid_resolvers is None:
                Scraper.debrid_resolvers = [resolver for resolver in resolveurl.choose_source(url) if resolver.isUniversal()]
            if not Scraper.debrid_resolvers:
                logger.log('%s requires debrid: %s' % (self.__module__, Scraper.debrid_resolvers), log_utils.LOGDEBUG)
                return ''
        try:
            headers = {'User-Agent': scraper_utils.get_ua()}
            req = urllib.request.Request(url, data=data, headers=headers)
            logging.debug("Retrieved req: %s", req)
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return response.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            logger.log(f'HTTP Error: {e.code} - {url}', log_utils.LOGWARNING)
        except urllib.error.URLError as e:
            logger.log(f'URL Error: {e.reason} - {url}', log_utils.LOGWARNING)
        return ''

    @classmethod
    def get_settings(cls):
        """
        Returns the settings for the scraper.

        :return: List of settings.
        """
        settings = super(cls, cls).get_settings()
        name = cls.get_name()
        settings.append(f'         <setting id="{name}-result_limit" label="     {i18n("result_limit")}" type="slider" default="10" range="10,100" option="int" visible="true"/>')
        return settings