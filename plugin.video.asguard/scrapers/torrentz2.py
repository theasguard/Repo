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
import urllib.parse
from bs4 import BeautifulSoup
import requests
import log_utils
from asguard_lib import scraper_utils, control
from asguard_lib.constants import FORCE_NO_MATCH, VIDEO_TYPES, QUALITIES
from asguard_lib.utils2 import i18n
import kodi
from . import scraper
from . import proxy

try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)

logger = log_utils.Logger.get_logger()
BASE_URL = 'https://torrentz2.nz'
SEARCH_URL = '/search?q=%s'
SERVER_ERROR = ('something went wrong', 'Connection timed out', '521: Web server is down', '503 Service Unavailable')

class Scraper(scraper.Scraper):
    base_url = BASE_URL
    debrid_resolvers = resolveurl

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting('%s-base_url' % (self.get_name()))

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE, VIDEO_TYPES.MOVIE])

    @classmethod
    def get_name(cls):
        return 'Torrentz2'

    def resolve_link(self, link):
        return link

    def parse_number(self,text):
        """Convert a string with 'K' to an integer."""
        if 'K' in text:
            return int(float(text.replace('K', '').replace(',', '')) * 1000)
        return int(text.replace(',', ''))

    def get_sources(self, video):
        sources = []
        search_url = self._build_query(video)
        page_url = scraper_utils.urljoin(self.base_url, SEARCH_URL % urllib.parse.quote_plus(search_url))
        logger.log(f"torrentz2 Retrieved page_url: {page_url}", log_utils.LOGDEBUG)
        html = self._http_get(page_url, require_debrid=True, cache_limit=.5)
        logger.log(f"torrentz2 Retrieved html: {html}", log_utils.LOGDEBUG)

        soup = BeautifulSoup(html, 'html.parser')
        logger.log(f"torrentz2 Retrieved soup: {soup}", log_utils.LOGDEBUG)
        rows = soup.find_all('dl')
        logger.log(f"torrentz2 Retrieved rows: {rows}", log_utils.LOGDEBUG)
        for row in rows:
            try:
                # Extract the magnet link from the first <span> within <dd>
                magnet_link = row.find('dd').find('a')['href']
                logger.log(f"Magnet link: {magnet_link}", log_utils.LOGDEBUG)

                # Extract other details from the <span> elements
                spans = row.find_all('span')
                age = spans[1].get_text()
                size = spans[2].get_text()
                seeders = self.parse_number(spans[3].get_text())
                leechers = self.parse_number(spans[4].get_text())

                # Extract hash from the magnet link
                hash = re.search(r'btih:(.*?)&', magnet_link, re.I).group(1)
                logger.log(f"Hash: {hash}", log_utils.LOGDEBUG)

                # Extract name and quality
                name = scraper_utils.cleanTitle(magnet_link.split('&dn=')[1])
                quality = scraper_utils.get_tor_quality(name)

                # Convert size to a displayable format
                dsize, isize = scraper_utils._size(size)
                logger.log('Size: %s' % isize, log_utils.LOGDEBUG)

                # Construct the source dictionary
                sources.append({
                    'class': self,
                    'host': 'magnet',
                    'label': f"{name} | {dsize}",
                    'seeders': seeders,
                    'hash': hash,
                    'name': name,
                    'quality': quality,
                    'multi-part': False,
                    'url': magnet_link,
                    'info': isize,
                    'direct': False,
                    'debridonly': True,
                    'size': dsize
                })
            except Exception as e:
                logger.log(f'Error processing Torrentz2 source: {str(e)}', log_utils.LOGERROR)
                continue
        return sources

    def _build_query(self, video):
        query = video.title
        logging.debug("Initial query: %s", query)

        # Check for episode and season range in the title
        episode_range = re.search(r'[Ee]p?(\d+)(?:[-~](\d+))?', video.title)
        season_range = re.search(r'[Ss]eason\s?(\d+)|[Ss](\d+)', video.title)
        logging.debug("torrentz2 Retrieved episode_range: %s", episode_range)
        logging.debug("torrentz2 Retrieved season_range: %s", season_range)

        # Construct the query based on the video type
        if video.video_type == VIDEO_TYPES.EPISODE:
            if season_range:
                start_season, end_season = map(int, season_range.groups(default=season_range.group(1)))
                logging.debug("torrentz2 Retrieved start_season: %s", start_season)
                logging.debug("torrentz2 Retrieved end_season: %s", end_season)
                if episode_range:
                    start_ep, end_ep = map(int, episode_range.groups(default=episode_range.group(1)))
                    logging.debug("torrentz2 Retrieved start_ep: %s", start_ep)
                    logging.debug("torrentz2 Retrieved end_ep: %s", end_ep)
                    query += f' S{start_season:02d}E{start_ep:02d}-E{end_ep:02d}'
                else:
                    # Handle full season queries
                    query = f'"Season {start_season:02d}"|"Complete"|"Batch"|"S{start_season:02d}"'
            else:
                query += f' S{int(video.season):02d}E{int(video.episode):02d}'
            logging.debug("Episode query: %s", query)
        elif video.video_type == VIDEO_TYPES.MOVIE:
            query += f' {video.year}'
            logging.debug("Movie query: %s", query)

        query = query.replace(' ', '+').replace('+-', '-')
        logging.debug("Final query: %s", query)
        return query

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
        settings = super(cls, cls).get_settings()
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