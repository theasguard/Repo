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
import re
from urllib.parse import quote_plus, unquote_plus
import logging
import urllib.request
import urllib.error
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

BASE_URL = 'https://bitcq.com'
SEARCH_URL = '/search?q=%s&category[]=1'
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
        return 'BitCQ'

    def get_sources(self, video):
        sources = []
        source_url = self.get_url(video)
        if not source_url or source_url == FORCE_NO_MATCH:
            return sources

        html = self._http_get(source_url, require_debrid=True)
        rows = client.parseDOM(html, 'tr')
        for row in rows:
            try:
                if 'magnet:' not in row:
                    continue
                columns = re.findall(r'<td.*?>(.+?)</td>', row, re.DOTALL)
                url = unquote_plus(columns[0]).replace('&amp;', '&')
                try:
                    url = re.search(r'(magnet:.+?)&tr=', url, re.I).group(1).replace(' ', '.')
                except:
                    continue
                hash = re.search(r'btih:(.*?)&', url, re.I).group(1)
                name = scraper_utils.cleanTitle(url.split('&dn=')[1])
                name_info = scraper_utils.info_from_name(name, video.trakt_id, video.title, video.year, '', '')

                try:
                    seeders = int(columns[4].replace(',', ''))
                    if self.min_seeders > seeders:
                        continue
                except:
                    seeders = 0

                quality = scraper_utils.get_tor_quality(name_info)
                info = []
                try:
                    dsize, isize = scraper_utils._size(columns[3])
                    info.insert(0, isize)
                except:
                    dsize = 0
                info = ' | '.join(info)
                hoster = {
                    'multi-part': False,
                    'label': name,
                    'hash': hash,
                    'class': self,
                    'language': 'en',
                    'url': url,
                    'info': info,
                    'host': 'magnet',
                    'quality': quality,
                    'direct': False,
                    'debridonly': True,
                    'size': dsize
                }
                sources.append(hoster)
            except:
                logger.log('BitCQ: Error getting sources', log_utils.LOGERROR)
        return sources

    def get_url(self, video):
        if video.video_type == VIDEO_TYPES.MOVIE:
            query = f'{video.title} {video.year}'
        else:
            query = f'{video.title} S{int(video.season):02d}E{int(video.episode):02d}'
        query = re.sub(r'[^A-Za-z0-9\s\.-]+', '', query)  # Clean the query
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

