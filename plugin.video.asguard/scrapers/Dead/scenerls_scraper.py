"""
    Asguard Addon
    Copyright (C) 2017 Mr Blamo

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
import urllib.parse
import kodi
import log_utils  # @UnusedImport
from bs4 import BeautifulSoup
from asguard_lib import scraper_utils, cloudflare, control
from asguard_lib.constants import FORCE_NO_MATCH, VIDEO_TYPES, XHR
from asguard_lib.utils2 import i18n
from . import scraper

BASE_URL = 'http://scene-rls.net'
MULTI_HOST = 'nfo.scene-rls.net'
LOCAL_UA = f'Asguard for Kodi/{kodi.get_version()}'
CATEGORIES = {
    VIDEO_TYPES.MOVIE: '/category/movies/',
    VIDEO_TYPES.EPISODE: '/category/tv-shows/'
}

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
        return 'scene-rls'

    def get_sources(self, video):
        source_url = self.get_url(video)
        hosters = []
        if not source_url or source_url == FORCE_NO_MATCH:
            return hosters

        url = scraper_utils.urljoin(self.base_url, source_url)
        headers = {'User-Agent': LOCAL_UA}
        html = self._http_get(url, require_debrid=True, cache_limit=.5)
        sources = self.__get_post_links(html)

        for source, value in sources.items():
            if scraper_utils.excluded_link(source):
                continue
            host = urllib.parse.urlparse(source).hostname
            meta = scraper_utils.parse_movie_link(value['release']) if video.video_type == VIDEO_TYPES.MOVIE else scraper_utils.parse_episode_link(value['release'])
            quality = scraper_utils.height_get_quality(meta['height'])
            hoster = {
                'multi-part': False,
                'host': host,
                'class': self,
                'views': None,
                'url': source,
                'rating': None,
                'quality': quality,
                'direct': False
            }
            if 'format' in meta:
                hoster['format'] = meta['format']
            hosters.append(hoster)

        return hosters

    def __get_post_links(self, html):
        sources = {}
        soup = BeautifulSoup(html, 'html.parser')
        post_content = soup.find('div', class_='postContent')
        if post_content:
            post_content = str(post_content)
            for result in re.finditer(r'<p\s+style="text-align:\s*center;">(.*?)<br.*?<h2(.*?)(?:<h4|<h3|</div>|$)', post_content, re.DOTALL):
                release, links = result.groups()
                release = re.sub('</?[^>]*>', '', release).upper()
                for match in re.finditer(r'href="([^"]+)', links):
                    stream_url = match.group(1)
                    if MULTI_HOST in stream_url:
                        continue
                    sources[stream_url] = {'release': release}

        return sources

    def get_url(self, video):
        return self._blog_get_url(video)

    @classmethod
    def get_settings(cls):
        settings = super().get_settings()
        settings = scraper_utils.disable_sub_check(settings)
        name = cls.get_name()
        settings.append(f'<setting id="{name}-filter" type="slider" range="0,180" option="int" label="{i18n("filter_results_days")}" default="30" visible="eq(-3,true)"/>')
        settings.append(f'<setting id="{name}-select" type="enum" label="{i18n("auto_select")}" lvalues="30636|30637" default="0" visible="eq(-4,true)"/>')
        return settings

    def search(self, video_type, title, year, season=''):  # @UnusedVariable
        search_url = scraper_utils.urljoin(self.base_url, f'/?s={urllib.parse.quote_plus(title)}/')
        headers = {'User-Agent': LOCAL_UA}
        headers.update(XHR)
        all_html = self._http_get(search_url, require_debrid=True, cache_limit=.5)

        html = ''
        soup = BeautifulSoup(all_html, 'html.parser')
        for post in soup.find_all('div', class_='post'):
            if CATEGORIES[video_type] in str(post):
                html += str(post)

        post_pattern = r'class="postTitle">.*?href="(?P<url>[^"]+)[^>]*>(?P<post_title>.*?)</a>'
        date_format = ''
        return self._blog_proc_results(html, post_pattern, date_format, video_type, title, year)