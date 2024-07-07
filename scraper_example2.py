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
import re
import json
import urllib.parse
import urllib.request
import urllib.error
import kodi
from bs4 import BeautifulSoup
from asguard_lib.utils2 import i18n
import xbmcgui
import log_utils
from asguard_lib import scraper_utils, control
from asguard_lib.constants import QUALITIES, VIDEO_TYPES
from . import scraper

import logging
try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)

logging.basicConfig(level=logging.DEBUG)

logger = log_utils.Logger.get_logger()
BASE_URL = 'https://example.com'
SEARCH_URL = '/search'
QUALITY_MAP = {'1080p': QUALITIES.HD1080, '720p': QUALITIES.HD720, '3D': QUALITIES.HD1080}

class Scraper(scraper.Scraper):
    """
    Example scraper for the Asguard Kodi addon.
    """
    base_url = BASE_URL
    debrid_resolvers = resolveurl

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        """
        Initializes the scraper with a timeout value.

        :param timeout: Timeout for HTTP requests.
        """
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url')
        self.result_limit = kodi.get_setting(f'{self.get_name()}-result_limit')

    @classmethod
    def provides(cls):
        """
        Specifies the types of videos this scraper can provide.

        :return: A set of video types.
        """
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        """
        Returns the name of the scraper.

        :return: The name of the scraper.
        """
        return 'ExampleScraper'

    def resolve_link(self, link):
        """
        Resolves the given link.

        :param link: The link to resolve.
        :return: The resolved link.
        """
        return link

    def get_sources(self, video):
        """
        Fetches sources for a given video.

        :param video: The video object containing details like title, year, etc.
        :return: A list of sources.
        """
        hosters = []
        query = self._build_query(video)
        search_url = scraper_utils.urljoin(self.base_url, SEARCH_URL)
        logging.debug("Search URL: %s", search_url)
        html = self._http_get(search_url, data=urllib.parse.urlencode(query).encode('utf-8'), require_debrid=True)
        logging.debug("Retrieved HTML: %s", html)
        soup = BeautifulSoup(html, "html.parser")
        soup_all = soup.find_all('div', class_='result')

        for entry in soup_all:
            try:
                title = entry.find('h2').text
                link = entry.find('a')['href']
                quality = self._get_quality(title)
                hoster = {
                    'multi-part': False,
                    'host': 'Example',
                    'class': self,
                    'quality': quality,
                    'views': None,
                    'rating': None,
                    'url': link,
                    'direct': False,
                    'debridonly': True
                }
                hosters.append(hoster)
                logging.debug("Retrieved source: %s", hoster)
            except AttributeError as e:
                logging.error("Failed to append source: %s", str(e))
                continue
        return self._filter_sources(hosters, video)

    def _build_query(self, video):
        """
        Builds the search query for the given video.

        :param video: The video object.
        :return: The search query.
        you can alter this how ever you like also.
        heres another example 
    def _search(self, title, year):
        results = []
        search_url = scraper_utils.urljoin(self.tv_base_url, '/the actual seach on the site/')
        html = self._http_get(search_url, cache_limit=48, requires_debrid=True)
        match_year = ''
        norm_title = scraper_utils.normalize_title(title)
        for attrs, match_title in dom_parser2.parse_dom(html, 'a', {'class': 'thread_link'}, req='href'):
            match_url = attrs['href']
            if match_title.upper().endswith(', THE'):
                match_title = 'The ' + match_title[:-5]
    
            if norm_title in scraper_utils.normalize_title(match_title) and (not year or not match_year or year == match_year):
                result = {'title': scraper_utils.cleanse_title(match_title), 'year': match_year, 'url': scraper_utils.pathify_url(match_url)}
                results.append(result)
        return results
        """
        query = {'q': video.title}
        if video.video_type == VIDEO_TYPES.MOVIE:
            query['q'] += f' {video.year}'
        query['q'] = query['q'].replace(' ', '+')
        query['qx'] = 1
        return query

    def _filter_sources(self, hosters, video):
        """
        Filters the sources based on the video type and episode matching.

        :param hosters: List of hosters.
        :param video: The video object.
        :return: Filtered list of sources.
        can also use the cleanse_name to filter as shown above
        """
        logging.debug("Filtering sources: %s", hosters)
        filtered_sources = []
        for source in hosters:
            if video.video_type == VIDEO_TYPES.EPISODE:
                if not self._match_episode(source['name'], video.season, video.episode):
                    continue
            filtered_sources.append(source)
            logging.debug("Filtered source: %s", source)
        return filtered_sources

    def _match_episode(self, title, season, episode):
        """
        Matches the episode number in the title with the given season and episode.

        :param title: The title of the source.
        :param season: The season number.
        :param episode: The episode number.
        :return: True if the episode matches, False otherwise.
        """
        regex_ep = re.compile(r'\bS(\d+)E(\d+)\b')
        match = regex_ep.search(title)
        if match:
            season_num = int(match.group(1))
            episode_num = int(match.group(2))
            if season_num == int(season) and episode_num == int(episode):
                return True
        return False

    def _get_quality(self, title):
        """
        Determines the quality of the video from the title.

        :param title: The title of the video.
        :return: The quality of the video.
        Several other quality function in the addon you can pick and choose.
        """
        for quality in QUALITY_MAP:
            if quality in title:
                return QUALITY_MAP[quality]
        return QUALITIES.HIGH

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
        the main http get alter according to the site or if the site allows it use the main http get, you can remove this and itll use the scraper.pys http get (it really depends on the site)
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
        add settings according to what you want but make sure it calls it somewhere in the scraper
        """
        settings = super(cls, cls).get_settings()
        name = cls.get_name()
        settings.append(f'         <setting id="{name}-result_limit" label="     {i18n("result_limit")}" type="slider" default="10" range="10,100" option="int" visible="true"/>')
        return settings
