"""
    Asguard Kodi Addon Example Scraper
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

import urllib.parse
import requests
from bs4 import BeautifulSoup
import re, kodi
from asguard_lib.cf_captcha import NoRedirection
import log_utils
import cfscrape
from asguard_lib import scraper_utils, control, cloudflare, cf_captcha
from asguard_lib.constants import FORCE_NO_MATCH, VIDEO_TYPES, QUALITIES, Q_ORDER
from asguard_lib.utils2 import i18n, ungz
import resolveurl
from . import scraper

logger = log_utils.Logger.get_logger()

BASE_URL = 'https://example.com'
LOCAL_UA = 'Asguard for Kodi/%s' % (kodi.get_version())
FLARESOLVERR_URL = 'http://localhost:8191/v1'
MAX_RESPONSE = 1024 * 1024 * 5
CF_CAPCHA_ENABLED = kodi.get_setting('cf_captcha') == 'true'

class ExampleScraper(scraper.Scraper):
    """
    Example scraper for the SALTS Kodi addon.
    """
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        """
        Initializes the scraper with a timeout value.

        :param timeout: Timeout for HTTP requests.
        """
        self.timeout = timeout
        self.base_url = kodi.get_setting('%s-base_url' % (self.get_name()))
        self.scraper = cfscrape.create_scraper()

    @classmethod
    def provides(cls):
        """
        Specifies the types of videos this scraper can provide.

        :return: A set of video types.
        """
        return frozenset([VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE, VIDEO_TYPES.MOVIE])

    @classmethod
    def get_name(cls):
        """
        Returns the name of the scraper.

        :return: The name of the scraper.
        """
        return 'ExampleScraper'
    
    def get_sources(self, video):
        """
        Retrieves sources for the given video.

        :param video: The video object containing details about the video.
        :return: A list of hosters (sources).
        """
        hosters = []
        source_url = self.get_url(video)
        if not source_url or source_url == FORCE_NO_MATCH:
            return hosters
        page_url = scraper_utils.urljoin(self.base_url, source_url)
        headers = {'User-Agent': LOCAL_UA}
        html = self._http_get(page_url, headers=headers, require_debrid=True, cache_limit=.5)
        if video.video_type == VIDEO_TYPES.MOVIE:
            page_url = self.__get_release(html, video)
            if page_url is None:
                return hosters
            page_url = scraper_utils.urljoin(self.base_url, page_url)
            html = self._http_get(page_url, headers=headers, require_debrid=True, cache_limit=.5)
        
        soup = BeautifulSoup(html, 'html.parser')
        hevc = False
        for span in soup.find_all('span', class_='releaselabel'):
            content = span.get_text()
            if re.search('(hevc|x265)', content, re.I):
                hevc = 'x265'
            match = re.search('(\d+)x(\d+)', content)
            if match:
                quality = scraper_utils.height_get_quality(int(match.group(2)))
                hosters.append({'quality': quality, 'url': page_url, 'host': 'direct', 'class': self, 'rating': None, 'views': None, 'direct': True, 'debridonly': False})
        return hosters

    def __get_release(self, html, video):
        """
        Retrieves the release page URL for the given video.

        :param html: The HTML content of the page.
        :param video: The video object containing details about the video.
        :return: The release page URL.
        """
        try:
            select = int(kodi.get_setting('%s-select' % (self.get_name())))
        except:
            select = 0
        soup = BeautifulSoup(html, 'html.parser')
        ul_id = 'releases' if video.video_type == VIDEO_TYPES.MOVIE else 'episodes'
        fragment = soup.find('ul', id=ul_id)
        if fragment:
            best_qorder = 0
            best_page = None
            for item in fragment.find_all('li'):
                link = item.find('a', href=True, title=True)
                if not link:
                    continue
                page_url, release = link['href'], link['title']
                time_span = item.find('span', class_='time')
                if time_span and self.__too_old(time_span.get_text()):
                    continue
                qorder = Q_ORDER.get(release, 0)
                if qorder > best_qorder:
                    best_qorder = qorder
                    best_page = page_url
            return best_page
        return None

    def _http_get(self, url, data=None, retry=True, allow_redirect=True, cache_limit=8, require_debrid=True):
        """
        Performs an HTTP GET request.

        :param url: The URL to fetch.
        :param data: Data to send in the request.
        :param retry: Whether to retry on failure.
        :param allow_redirect: Whether to allow redirects.
        :param cache_limit: Cache limit for the request.
        :param require_debrid: Whether debrid is required.
        :return: The response text.
        """
        if require_debrid:
            if Scraper.debrid_resolvers is None:
                Scraper.debrid_resolvers = [resolver for resolver in resolveurl.relevant_resolvers() if resolver.isUniversal()]
            if not Scraper.debrid_resolvers:
                logger.log('%s requires debrid: %s' % (self.__module__, Scraper.debrid_resolvers), log_utils.LOGDEBUG)
                return ''
        try:
            headers = {'User-Agent': scraper_utils.get_ua()}
            req = urllib.request.Request(url, data=data, headers=headers)
            logging.debug("HTTP request: %s", req)
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
