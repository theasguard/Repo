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
import urllib.request
import urllib.error
import urllib.parse
import logging
import re
from urllib.parse import quote_plus, unquote_plus
import xbmcgui
import kodi
import log_utils, workers
from asguard_lib import scraper_utils, control, client
from asguard_lib.constants import FORCE_NO_MATCH, VIDEO_TYPES, QUALITIES, DELIM
from asguard_lib.utils2 import i18n
from . import scraper
from . import proxy

try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)
    
logger = log_utils.Logger.get_logger()

BASE_URL = 'https://www.torrentdownload.info'
SEARCH_URL = '/search?q=%s'
VIDEO_EXT = ['MKV', 'AVI', 'MP4']

class Scraper(scraper.Scraper):
    base_url = BASE_URL
    debrid_resolvers = resolveurl

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url')
        min_seeders_setting = kodi.get_setting(f'{self.get_name()}-min_seeders')
        try:
            self.min_seeders = int(min_seeders_setting) if min_seeders_setting else 0
        except (ValueError, TypeError):
            self.min_seeders = 0

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'TorrentDownload'

    def get_sources(self, video):
        sources = []
        source_url = self.get_url(video)
        if not source_url or source_url == FORCE_NO_MATCH:
            return sources

        html = self._http_get(source_url, require_debrid=True, cache_limit=1)
        for row in re.findall(r'<tr>(.*?)</tr>', html, re.DOTALL):
            if any(value in row for value in ('<th', 'nofollow')):
                continue
            columns = re.findall(r'<td.*?>(.+?)</td>', row, re.DOTALL)
            logger.log(f'Found columns: {columns}', log_utils.LOGDEBUG)
            link = re.search(r'href\s*=\s*["\']/(.+?)["\']>', columns[0], re.I).group(1).split('/')
            logger.log(f'Found link: {link}', log_utils.LOGDEBUG)
            hash = link[0]
            name = scraper_utils.cleanTitle(unquote_plus(link[1]).replace('&amp;', '&'))
            logger.log(f'Found torrent: {name}', log_utils.LOGDEBUG)

            url = f'magnet:?xt=urn:btih:{hash}&dn={name}'
            try:
                seeders = int(columns[3].replace(',', ''))
                if self.min_seeders > seeders:
                    continue
            except:
                seeders = 0

            quality = scraper_utils.get_tor_quality(name)
            logger.log(f'Found quality: {quality}', log_utils.LOGDEBUG)
            info = []
            dsize = columns[2].strip()

            info = ' | '.join(info)
            label = f"{name} | {dsize}"
            hoster = {'class': self, 'multi-part': False, 'label': label, 'hash': hash, 'language': 'en', 'source': 'torrent', 'url': url, 'info': info, 'host': 'magnet', 'quality': quality, 'direct': False, 'debridonly': True, 'size': dsize}
            sources.append(hoster)
            # sources.append({
            #     'class': self,
            #     'source': 'torrent',
            #     'seeders': seeders,
            #     'hash': hash,
            #     'name': name,
            #     'quality': quality,
            #     'language': 'en',
            #     'url': url,
            #     'info': info,
            #     'direct': False,
            #     'debridonly': True,
            #     'size': dsize
            # })
        return sources

    def get_url(self, video):
        if video.video_type == VIDEO_TYPES.MOVIE:
            query = f'{video.title} {video.year}'
        else:
            query = f'{video.title} S{int(video.season):02d} E{int(video.episode):02d}'
        return f'{self.base_url}{SEARCH_URL % quote_plus(query)}'

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
\t\t</setting>''',
            f'''\t\t<setting id="{name}-min_seeders" type="integer" label="40486" help="">
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
\t\t</setting>'''
        ]

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