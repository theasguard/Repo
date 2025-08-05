"""
    SALTS Addon
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
import urllib.request
import urllib.error
import kodi
import log_utils
from bs4 import BeautifulSoup
from asguard_lib import scraper_utils, control
from asguard_lib.constants import QUALITIES, VIDEO_TYPES
from asguard_lib.utils2 import i18n
from .. import scraper
try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)

logger = log_utils.Logger.get_logger()
BASE_URL = 'https://www.limetorrents.pro'
SEARCH_URL = '/search/all/%s'

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url')
        self.result_limit = kodi.get_setting(f'{self.get_name()}-result_limit')

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Limetorrents'

    def resolve_link(self, link):
        return link

    def get_sources(self, video):
        from asguard_lib.trakt_api import Trakt_API
        hosters = []
        # query = video.title
        type = VIDEO_TYPES.MOVIE if video.video_type == VIDEO_TYPES.MOVIE else VIDEO_TYPES.TVSHOW
        idTrakt = video.trakt_id
        idImdb = None
        idTmdb = None
        idTvdb = None

        if type == VIDEO_TYPES.MOVIE:
            details = Trakt_API().get_movie_details(idTrakt)
        else:
            details = Trakt_API().get_show_details(idTrakt)
        try: idImdb = details['ids']['imdb']
        except: pass
        try: idTmdb = details['ids']['tmdb']
        except: pass
        try: idTvdb = details['ids']['tvdb']
        except: pass

        if type == VIDEO_TYPES.MOVIE and not idTrakt and not idImdb and not idTmdb:
            query = '%s %s' % (str(video.title), str(video.year))
        elif type == VIDEO_TYPES.TVSHOW and not idTrakt and not idImdb and not idTvdb:
            query = '%s S%sE%s' % (str(video.title), str(video.season), str(video.episode))
            logger.log('Query: %s' % query, log_utils.LOGDEBUG)
            
        query = video.title
        search_url = scraper_utils.urljoin(self.base_url, SEARCH_URL % urllib.parse.quote_plus(query))
        logger.log('Search URL: %s' % search_url, log_utils.LOGDEBUG)
        html = self._http_get(search_url, require_debrid=True)
        logger.log('HTML: %s' % html, log_utils.LOGDEBUG)
        soup = BeautifulSoup(html, 'html.parser')
        rows = soup.select('table.table2 tr')
        for row in rows:
            try:
                columns = row.find_all('td')
                if len(columns) < 4:
                    continue
                name = columns[0].a['href']
                torrent_page_url = columns[0].a['href']
                torrent_page_url = urllib.parse.urljoin(self.base_url, torrent_page_url)
                logger.log('Torrent Page URL: %s' % torrent_page_url, log_utils.LOGDEBUG)
                
                # Fetch the torrent detail page
                torrent_page_html = self._http_get(torrent_page_url, require_debrid=True)
                if not torrent_page_html:
                    logger.log('No HTML returned from torrent page URL: %s' % torrent_page_url, log_utils.LOGDEBUG)
                    continue
                
                # Extract the magnet link from the torrent detail page
                magnet_match = re.search(r'href\s*=\s*["\'](magnet:.+?)["\']', torrent_page_html, re.I)
                if not magnet_match:
                    logger.log('No magnet link found on page: %s' % torrent_page_url, log_utils.LOGDEBUG)
                    continue
                magnet = magnet_match.group(1)
                
                size = columns[1].text
                seeders = int(columns[2].text.replace(',', ''))
                quality = scraper_utils.get_tor_quality(name)

                hoster = {'class': self, 'multi-part': False, 'url': magnet, 'size': size, 'quality': quality, 'host': 'magnet', 'direct': False, 'debridonly': True, 'seeders': seeders}
                hosters.append(hoster)
                logger.log("Retrieved source: %s" % hoster, log_utils.LOGDEBUG)
            except Exception as e:
                logger.log(f"Failed to append source: {e}", log_utils.LOGDEBUG)
                continue
        return hosters

    def _http_get(self, url, data=None, retry=True, allow_redirect=True, cache_limit=8, require_debrid=True):
        if require_debrid:
            if Scraper.debrid_resolvers is None:
                Scraper.debrid_resolvers = [resolver for resolver in resolveurl.relevant_resolvers() if resolver.isUniversal()]
            if not Scraper.debrid_resolvers:
                logger.log('%s requires debrid: %s' % (self.__module__, Scraper.debrid_resolvers), log_utils.LOGDEBUG)
                return ''
        try:
            headers = {'User-Agent': scraper_utils.get_ua()}
            req = urllib.request.Request(url, data=data, headers=headers)
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
        settings.append(f'         <setting id="{name}-result_limit" label="     {i18n("result_limit")}" type="slider" default="10" range="10,100" option="int" visible="true"/>')
        return settings