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
import json
import logging
import re
import urllib.parse
import requests
import urllib3
import xbmcgui
import kodi
import log_utils
from asguard_lib import scraper_utils, control
from asguard_lib.constants import VIDEO_TYPES, QUALITIES
from . import scraper

logging.basicConfig(level=logging.DEBUG)
logger = log_utils.Logger.get_logger()
BASE_URL = 'https://binged.live'
SEARCH_URL = '/search?q=%s'

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url')

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Binged'

    def get_sources(self, video):
        sources = []
        search_url = self._get_search_url(video)
        response = self._http_get(search_url, cache_limit=1)
        if not response:
            return sources

        try:
            results = self._parse_search_results(response)
        except Exception as e:
            logger.log('Failed to parse search results from Binged: %s' % str(e), log_utils.LOGERROR)
            return sources

        for result in results:
            try:
                title = result['title']
                url = result['url']
                quality, info = scraper_utils.get_release_quality(title, url)
                size = result.get('size', 0)
                info = ' | '.join(info)
                host = scraper_utils.get_direct_hostname(self, url)

                sources.append({
                    'host': host,
                    'host': 'source',
                    'name': title,
                    'quality': quality,
                    'url': url,
                    'info': info,
                    'multi-part': False,
                    'direct': False,
                    'size': size,
                })
            except Exception as e:
                logger.log('Error processing Binged source: %s' % str(e), log_utils.LOGERROR)
                continue

        return sources

    def _get_search_url(self, video):
        if video.video_type == VIDEO_TYPES.MOVIE:
            query = f'{video.title} {video.year}'
        else:
            query = f'{video.title} S{int(video.season):02d}E{int(video.episode):02d}'
        return urllib.parse.urljoin(self.base_url, SEARCH_URL % urllib.parse.quote_plus(query))

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

    def _parse_search_results(self, html):
        results = []
        pattern = re.compile(r'<a class="[^"]*" href="(/info/[^"]*)">.*?<div class="line-clamp-2[^>]*>([^<]*)</div>.*?<span>Rating: ([^<]*)</span>.*?<span>•</span><span>([^<]*)</span>', re.DOTALL)
        logging.debug(f"Pattern: {pattern}")
        for match in pattern.finditer(html):
            url, title, rating, year = match.groups()
            results.append({
                'url': urllib.parse.urljoin(self.base_url, url),
                'title': title.strip(),
                'rating': rating.strip(),
                'year': year.strip(),
                'size': 0  # Size is not available in the search results
            })
        return results

    def resolve_url(self, url):
        response = self._http_get(url)
        if not response:
            return None

        iframe_url = self._extract_iframe_url(response)
        if not iframe_url:
            return None

        return self._resolve_iframe(iframe_url)

    def _extract_iframe_url(self, html):
        match = re.search(r'<iframe[^>]+src="([^"]+)"', html)
        if match:
            return match.group(1)
        return None

    def _resolve_iframe(self, iframe_url):
        response = self._http_get(iframe_url)
        if not response:
            return None

        match = re.search(r'source src="([^"]+)"', response)
        if match:
            return match.group(1)
        return None
    
    def get_season_list(self, show_url):
        response = self._http_get(show_url)
        if not response:
            return []

        pattern = re.compile(r'<a href="(/show/[^"]+/season-\d+)">')
        seasons = pattern.findall(response)
        return [urllib.parse.urljoin(self.base_url, season) for season in seasons]

    def get_episode_list(self, season_url):
        response = self._http_get(season_url)
        if not response:
            return []

        pattern = re.compile(r'<a href="(/show/[^"]+/season-\d+/episode-\d+)">')
        episodes = pattern.findall(response)
        return [urllib.parse.urljoin(self.base_url, episode) for episode in episodes]