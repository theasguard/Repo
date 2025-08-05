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
import logging
import re
import requests
import kodi
import log_utils  # @UnusedImport
import dom_parser2
import html
from asguard_lib import scraper_utils, cloudflare
from asguard_lib.constants import FORCE_NO_MATCH, VIDEO_TYPES, QUALITIES
import urllib.parse
import urllib.request
from . import scraper
from asguard_lib.utils2 import i18n
from urllib.parse import quote_plus, unquote_plus
from asguard_lib import client, scraper_utils
import workers

logger = log_utils.Logger.get_logger()

BASE_URL = 'https://yourbittorrent.com'

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.language = ['en']
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url') or BASE_URL
        self.search_link = '?q=%s&sort=size'
        self.min_seeders = 0  # to many items with no value but cached links
        self.scraper = requests.Session()

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE, VIDEO_TYPES.MOVIE])

    @classmethod
    def get_name(cls):
        return 'YourBittorrent'

    def resolve_link(self, link):
        return link

    def get_sources(self, video):
        sources = []
        source_url = self.get_url(video)
        if not source_url or source_url == FORCE_NO_MATCH:
            return sources

        results = self._http_get(source_url, cache_limit=5)
        if not results:
            return sources

        links = re.findall(r'<a\s*href\s*=\s*["\'](/torrent/.+?)["\']', results, re.DOTALL | re.I)
        threads = []
        append = threads.append
        for link in links:
            append(workers.Thread(self._get_sources, link))
        [i.start() for i in threads]
        [i.join() for i in threads]
        return self.sources

    def _get_sources(self, video):
        sources = []
        try:
            url = '%s%s' % (self.base_url, video)
            result = self._http_get(url, cache_limit=5)
            if result is None: return
            if '<kbd>' not in result: return
            hash = re.search(r'<kbd>(.+?)<', result, re.I).group(1)
            name = re.search(r'<h3\s*class\s*=\s*["\']card-title["\']>(.+?)<', result, re.I).group(1).replace('Original Name: ', '')
            name = scraper_utils.cleanTitle(unquote_plus(name))


            url = 'magnet:?xt=urn:btih:%s&dn=%s' % (hash, name)
            try:
                seeders = int(re.search(r'>Seeders:.*?>\s*([0-9]+|[0-9]+,[0-9]+)\s*</', result, re.I).group(1).replace(',', ''))
                if self.min_seeders > seeders: return
            except: seeders = 0

            quality = scraper_utils.get_tor_quality(name)
            info = []
            try:
                size = re.search(r'File size:.*?["\']>(.+?)<', result, re.I).group(1)
                size = re.sub('\s*in.*', '', size, re.I)
                dsize, isize = scraper_utils._size(size)
                info.insert(0, isize)
            except: dsize = 0
            info = ' | '.join(info)

            sources.append({'class': self, 'host': 'torrent', 'multi-part': False, 'seeders': seeders, 'hash': hash, 'name': name,
                                 'quality': quality, 'language': 'en', 'url': url, 'info': info, 'direct': False, 'debridonly': True, 'size': dsize})
        except Exception as e:
            logger.log(f'YOURBITTORRENT Error: {e}', log_utils.LOGERROR)
        return sources

    def get_url(self, video):
        url = None
        result = self.db_connection().get_related_url(video.video_type, video.title, video.year, self.get_name(), video.season, video.episode)
        if result:
            url = result[0][0]
            logger.log(f'Got local related url: |{video.video_type}|{video.title}|{video.year}|{self.get_name()}|{url}|', log_utils.LOGDEBUG)
        else:
            if video.video_type == VIDEO_TYPES.MOVIE:
                query = f'title={quote_plus(video.title)}&year={video.year}'
            else:
                query = f'title={quote_plus(video.title)}&season={video.season}'
            url = f'{self.base_url}/search?{query}'
            self.db_connection().set_related_url(video.video_type, video.title, video.year, self.get_name(), url, video.season, video.episode)
        return url

    @classmethod
    def get_settings(cls):
        settings = super(cls, cls).get_settings()
        settings = scraper_utils.disable_sub_check(settings)
        name = cls.get_name()
        parent_id = f"{name}-enable"
        label_id = kodi.Translations.get_scraper_label_id(name)
        
        return [
            f'''\t\t<setting id="{parent_id}" type="boolean" label="{label_id}" help="">
\t\t\t<level>0</level>
\t\t\t<default>true</default>
\t\t\t<dependencies>
\t\t\t\t<dependency type="visible">
\t\t\t\t\t<condition on="property" name="InfoBool">true</condition>
\t\t\t\t</dependency>
\t\t\t</dependencies>
\t\t\t<control type="toggle"/>
\t\t</setting>''',
            f'''\t\t<setting id="{name}-base_url" type="string" label="30175" help="">
\t\t\t<level>0</level>
\t\t\t<default>{cls.base_url}</default>
\t\t\t<dependencies>
\t\t\t\t<dependency type="visible">
\t\t\t\t\t<condition operator="is" setting="{parent_id}">true</condition>
\t\t\t\t</dependency>
\t\t\t</dependencies>
\t\t\t<control type="edit" format="string">
\t\t\t\t<heading>{i18n('base_url')}</heading>
\t\t\t</control>
\t\t</setting>'''
        ]