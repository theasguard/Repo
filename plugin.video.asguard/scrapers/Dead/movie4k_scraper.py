"""
    Asguard Addon
    Copyright (C) 2017 Thor

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
import kodi
import dom_parser2
import urllib.request
import log_utils  # @UnusedImport
from asguard_lib import scraper_utils
from asguard_lib import cfscrape
from asguard_lib import cloudflare
from asguard_lib.constants import FORCE_NO_MATCH
from asguard_lib.constants import QUALITIES
from asguard_lib.constants import VIDEO_TYPES
from . import scraper


BASE_URL = 'https://movie4kto.lat'
LOCAL_UA = 'Asguard for Kodi/%s' % (kodi.get_version())
QUALITY_MAP = {None: None, '0': QUALITIES.LOW, '1': QUALITIES.MEDIUM, '2': QUALITIES.HIGH, '3': QUALITIES.HIGH, '4': QUALITIES.HD720, '5': QUALITIES.HD1080}
logger = log_utils.Logger.get_logger()

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting('%s-base_url' % (self.get_name()))

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE, VIDEO_TYPES.MOVIE])

    @classmethod
    def get_name(cls):
        return 'Movie4K'

    def resolve_link(self, link):
        url = scraper_utils.urljoin(self.base_url, link)
        html = self._http_get(url, cache_limit=0)
        match = re.search('href="([^"]+).*?src="/img/click_link.jpg"', html)
        if match:
            return match.group(1)

    def get_sources(self, video):
        hosters = []
        source_url = self.get_url(video)
        if not source_url or source_url == FORCE_NO_MATCH: return hosters
        url = scraper_utils.urljoin(self.base_url, source_url)
        headers = {'User-Agent': LOCAL_UA}
        html = self._http_get(url, cache_limit=.5)
        pattern = '''<div class="container">.*?href\s*=\s*['"]([^'"]+).*?&nbsp;([^<]+)'''
        for match in re.finditer(pattern, html, re.DOTALL):
            url, host = match.groups()
            if not url.startswith('/'): url = '/' + url
            quality = scraper_utils.blog_get_quality(video, url, host)
            hoster = {'multi-part': False, 'host': host, 'class': self, 'quality': quality, 'views': None, 'rating': None, 'url': url, 'direct': False}
            hosters.append(hoster)
        return hosters

    def search(self, video_type, title, year, season=''):  # @UnusedVariable
        """
        Search for videos on the Movie4K website.

        This function performs a search on the Movie4K website based on the provided video type, title, and year.
        It returns a list of search results that match the criteria.

        Args:
            video_type (str): The type of video to search for (e.g., VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW).
            title (str): The title of the video to search for.
            year (str): The year of the video to search for.
            season (str, optional): The season number for TV shows. Defaults to an empty string.

        Returns:
            list: A list of dictionaries containing search results. Each dictionary contains the URL, title, and year of a matching video.
        """
        results = []
        search_url = scraper_utils.urljoin(self.base_url, '/filter?keyword=')
        cookies = {'onlylanguage': 'en', 'lang': 'en'}
        params = {'list': 'search', 'search': title}
        headers = {'User-Agent': LOCAL_UA}
        html = self._http_get(search_url, params=params, headers=headers)
        
        for _attrs, content in dom_parser2.parse_dom(html, 'div', {'class': 'container'}):
            match = dom_parser2.parse_dom(content, 'a', req='href')
            if not match:
                continue
            
            match_url, match_title = match[0].attrs['href'], match[0].content
            is_show = re.search('\(tvshow\)', match_title, re.I)
            if (video_type == VIDEO_TYPES.MOVIE and is_show) or (video_type == VIDEO_TYPES.TVSHOW and not is_show):
                continue

            match_title = match_title.replace('(TVshow)', '')
            match_title = match_title.strip()
            
            match_year = ''
            for _attrs, div in dom_parser2.parse_dom(content, 'div'):
                match = re.match('\s*(\d{4})\s*', div)
                if match:
                    match_year = match.group(1)

            if not year or not match_year or year == match_year:
                result = {'url': scraper_utils.pathify_url(match_url), 'title': scraper_utils.cleanse_title(match_title), 'year': match_year}
                results.append(result)
        
        return results

    def _get_episode_url(self, show_url, video):
        if not scraper_utils.force_title(video):
            url = scraper_utils.urljoin(self.base_url, show_url)
            headers = {'User-Agent': LOCAL_UA}
            html = self._http_get(url, cache_limit=2, headers=headers)
            season_div = 'episodediv%s' % (video.season)
            fragment = dom_parser2.parse_dom(html, 'div', {'id': season_div})
            if not fragment: return

            pattern = 'value="([^"]+)[^>]*>Episode %s\s*<' % (video.episode)
            match = re.search(pattern, fragment[0].content, re.I)
            if not match: return
            
            return scraper_utils.pathify_url(match.group(1))
        
    def _http_get(self, url, data=None, retry=True, allow_redirect=True, cache_limit=8, require_debrid=True):
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