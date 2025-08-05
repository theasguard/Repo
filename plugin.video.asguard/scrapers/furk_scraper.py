"""
    Asguard Addon
    Copyright (C) 2024 MrBlamo

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
import json
import re
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET

import kodi
import log_utils
import utils
from asguard_lib import scraper_utils, control
from asguard_lib.constants import FORCE_NO_MATCH, VIDEO_TYPES
from asguard_lib.utils2 import i18n
from . import scraper
import xbmcgui

logger = log_utils.Logger.get_logger()
BASE_URL = 'https://www.furk.net'
SEARCH_URL = '/api/plugins/metasearch'
LOGIN_URL = '/api/login/login'
MIN_DURATION = 10 * 60 * 1000  # 10 minutes in milliseconds

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url')
        self.username = kodi.get_setting(f'{self.get_name()}-username')
        self.password = kodi.get_setting(f'{self.get_name()}-password')
        self.max_results = int(kodi.get_setting(f'{self.get_name()}-result_limit'))
        self.max_gb = kodi.get_setting(f'{self.get_name()}-size_limit')
        self.max_bytes = int(self.max_gb) * 1024 * 1024 * 1024

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Furk.net'

    def resolve_link(self, link):
        playlist = super(self.__class__, self)._http_get(link, cache_limit=.5)
        try:
            ns = '{http://xspf.org/ns/0/}'
            root = ET.fromstring(playlist)
            tracks = root.findall(f'.//{ns}track')
            locations = [
                {'duration': int(track.find(f'{ns}duration').text) / 1000, 'url': track.find(f'{ns}location').text}
                for track in tracks if int(track.find(f'{ns}duration').text) >= MIN_DURATION
            ]

            if len(locations) > 1:
                result = xbmcgui.Dialog().select(i18n('choose_stream'), [utils.format_time(loc['duration']) for loc in locations])
                if result > -1:
                    return locations[result]['url']
            elif locations:
                return locations[0]['url']
        except Exception as e:
            logger.log(f'Failure during furk playlist parse: {e}', log_utils.LOGWARNING)
        
    def get_sources(self, video):
        hosters = []
        source_url = self.get_url(video)
        if not source_url or source_url == FORCE_NO_MATCH:
            return hosters

        params = scraper_utils.parse_query(source_url)
        if 'title' in params:
            search_title = re.sub("[^A-Za-z0-9. ]", "", urllib.parse.unquote_plus(params['title']))
            query = search_title
            if video.video_type == VIDEO_TYPES.MOVIE and 'year' in params:
                query += f' {params["year"]}'
            elif video.video_type == VIDEO_TYPES.EPISODE:
                sxe = f'S{int(params["season"]):02d}E{int(params["episode"]):02d}'
                query += f' {sxe}'

            search_url = scraper_utils.urljoin(self.base_url, SEARCH_URL)
            search_data = self.__translate_search(search_url)
            search_data['q'] = query
            search_results = self._http_get(search_url, data=urllib.parse.urlencode(search_data).encode('utf-8'))

            for item in search_results.get('files', []):
                if 'url_pls' in item:
                    size_gb = scraper_utils.format_size(int(item['size']), 'B')
                    if self.max_bytes and int(item['size']) > self.max_bytes:
                        logger.log(f'Result skipped, Too big: |{item["name"]}| - {item["size"]} ({size_gb}) > {self.max_bytes} ({self.max_gb}GB)')
                        continue

                    stream_url = item['url_pls']
                    host = scraper_utils.get_direct_hostname(self, stream_url)
                    hoster = {
                        'multi-part': False, 'class': self, 'views': None, 'url': stream_url,
                        'rating': None, 'host': host, 'quality': scraper_utils.width_get_quality(item.get('width', 0)),
                        'direct': True, 'size': size_gb, 'extra': item['name']
                    }
                    hosters.append(hoster)
                else:
                    logger.log(f'Furk.net result skipped - no playlist: |{json.dumps(item)}|', log_utils.LOGDEBUG)
                    
        return hosters
    
    def get_url(self, video):
        url = None
        result = self.db_connection().get_related_url(video.video_type, video.title, video.year, self.get_name(), video.season, video.episode)
        if result:
            url = result[0][0]
            logger.log(f'Got local related url: |{video.video_type}|{video.title}|{video.year}|{self.get_name()}|{url}|', log_utils.LOGDEBUG)
        else:
            if video.video_type == VIDEO_TYPES.MOVIE:
                query = f'title={urllib.parse.quote_plus(video.title)}&year={video.year}'
            else:
                query = f'title={urllib.parse.quote_plus(video.title)}&season={video.season}&episode={video.episode}&air_date={video.ep_airdate}'
            url = f'/search?{query}'
            self.db_connection().set_related_url(video.video_type, video.title, video.year, self.get_name(), url, video.season, video.episode)
        return url

    def search(self, video_type, title, year, season=''):  # @UnusedVariable
        return []

    @classmethod
    def get_settings(cls):
        settings = super(cls, cls).get_settings()
        settings = scraper_utils.disable_sub_check(settings)
        name = cls.get_name()
        parent_id = f"{name}-enable"
        
        # Add Furk-specific settings
        settings.extend([
            f'''\t\t<setting id="{name}-username" type="string" label="30177" help="">
\t\t\t<level>0</level>
\t\t\t<default></default>
\t\t\t<constraints>
\t\t\t\t<allowempty>true</allowempty>
\t\t\t</constraints>
\t\t\t<dependencies>
\t\t\t\t<dependency type="visible">
\t\t\t\t\t<condition operator="is" setting="{parent_id}">true</condition>
\t\t\t\t</dependency>
\t\t\t</dependencies>
\t\t\t<control type="edit" format="string">
\t\t\t\t<heading>{i18n('username')}</heading>
\t\t\t</control>
\t\t</setting>''',
            f'''\t\t<setting id="{name}-password" type="string" label="30178" help="">
\t\t\t<level>0</level>
\t\t\t<default></default>
\t\t\t<constraints>
\t\t\t\t<allowempty>true</allowempty>
\t\t\t</constraints>
\t\t\t<dependencies>
\t\t\t\t<dependency type="visible">
\t\t\t\t\t<condition operator="is" setting="{parent_id}">true</condition>
\t\t\t\t</dependency>
\t\t\t</dependencies>
\t\t\t<control type="edit" format="string">
\t\t\t\t<heading>{i18n('password')}</heading>
\t\t\t\t<hidden>true</hidden>
\t\t\t</control>
\t\t</setting>''',
            f'''\t\t<setting id="{name}-result_limit" type="integer" label="30229" help="">
\t\t\t<level>0</level>
\t\t\t<default>0</default>
\t\t\t<constraints>
\t\t\t\t<minimum>0</minimum>
\t\t\t\t<maximum>100</maximum>
\t\t\t</constraints>
\t\t\t<dependencies>
\t\t\t\t<dependency type="visible">
\t\t\t\t\t<condition operator="is" setting="{parent_id}">true</condition>
\t\t\t\t</dependency>
\t\t\t</dependencies>
\t\t\t<control type="slider" format="integer">
\t\t\t\t<popup>false</popup>
\t\t\t</control>
\t\t</setting>''',
            f'''\t\t<setting id="{name}-size_limit" type="integer" label="30279" help="">
\t\t\t<level>0</level>
\t\t\t<default>0</default>
\t\t\t<constraints>
\t\t\t\t<minimum>0</minimum>
\t\t\t\t<maximum>50</maximum>
\t\t\t</constraints>
\t\t\t<dependencies>
\t\t\t\t<dependency type="visible">
\t\t\t\t\t<condition operator="is" setting="{parent_id}">true</condition>
\t\t\t\t</dependency>
\t\t\t</dependencies>
\t\t\t<control type="slider" format="integer">
\t\t\t\t<popup>false</popup>
\t\t\t</control>
\t\t</setting>'''
        ])
        
        return settings

    def _http_get(self, url, data=None, retry=True, allow_redirect=True, cache_limit=8):
        if not self.username or not self.password:
            return {}
        
        js_result = {}
        result = super(self.__class__, self)._http_get(url, data=data, allow_redirect=allow_redirect, cache_limit=cache_limit)
        if result:
            try:
                js_result = json.loads(result)
            except (ValueError, TypeError):
                if 'msg_key=session_invalid' in result:
                    logger.log(f'Logging in for url ({url}) (Session Expired)', log_utils.LOGDEBUG)
                    self.__login()
                    js_result = self._http_get(url, data=data, retry=False, allow_redirect=allow_redirect, cache_limit=0)
                else:
                    logger.log(f'Invalid JSON returned: {url}: {result}', log_utils.LOGWARNING)
                    js_result = {}
            else:
                if js_result.get('status') == 'error':
                    error = js_result.get('error', 'Unknown Error')
                    if retry and any(e in error for e in ['access denied', 'session has expired', 'clear cookies']):
                        logger.log(f'Logging in for url ({url}) - ({error})', log_utils.LOGDEBUG)
                        self.__login()
                        js_result = self._http_get(url, data=data, retry=False, allow_redirect=allow_redirect, cache_limit=0)
                    else:
                        logger.log(f'Error received from furk.net ({error})', log_utils.LOGWARNING)
                        js_result = {}
            
        return js_result
        
    def __login(self):
        url = scraper_utils.urljoin(self.base_url, LOGIN_URL)
        data = {'login': self.username, 'pwd': self.password}
        result = self._http_get(url, data=data, cache_limit=0)
        if result.get('status') != 'ok':
            raise Exception(f'furk.net login failed: {result.get("error", "Unknown Error")}')
        
    def __translate_search(self, url):
        query = {'moderated': 'yes', 'offset': 0, 'limit': self.max_results, 'match': 'all', 'cached': 'yes', 'attrs': 'name'}
        parsed_query = scraper_utils.parse_query(url)
        query['q'] = parsed_query.get('query', '')
        return query