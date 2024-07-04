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
import datetime
import re
import sys
import urllib.parse
import dom_parser
import dom_parser2
import kodi
import log_utils  # @UnusedImport
from . import scraper
from asguard_lib.constants import FORCE_NO_MATCH
from asguard_lib.utils2 import SHORT_MONS
from asguard_lib.utils2 import VIDEO_TYPES
from asguard_lib.utils2 import i18n
from asguard_lib import cloudflare
from asguard_lib import scraper_utils

logger = log_utils.Logger.get_logger(__name__)

BASE_URL = 'https://www.ddlvalley.me'
LOCAL_UA = 'Asguard for Kodi/%s' % (kodi.get_version())
CATEGORIES = {VIDEO_TYPES.MOVIE: '/category/movies/', VIDEO_TYPES.TVSHOW: '/category/tv-shows/'}

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
        return 'DDLValley'

    def get_sources(self, video):
        source_url = self.get_url(video)
        hosters = []
        if source_url and source_url != FORCE_NO_MATCH:
            url = urllib.parse.urljoin(self.base_url, source_url)
            headers = {'User-Agent': LOCAL_UA}
            try:
                html = self._http_get(url, require_debrid=True, cache_limit=.5)
            except Exception as e:
                logger.log(f"Error fetching URL {url}: {str(e)}", log_utils.LOGERROR)
                return hosters

            for match in re.finditer("<span\s+class='info1'(.*?)(<span\s+class='info2|<hr\s*/>)", html, re.DOTALL):
                for match2 in re.finditer('href="([^"]+)', match.group(1)):
                    stream_url = match2.group(1)
                    host = urllib.parse.urlparse(stream_url).hostname
                    quality = scraper_utils.blog_get_quality(video, stream_url, host)
                    hoster = {
                        'multi-part': False,
                        'host': host,
                        'class': self,
                        'views': None,
                        'url': stream_url,
                        'rating': None,
                        'quality': quality,
                        'direct': False
                    }
                    hosters.append(hoster)
                    
        return hosters

    @classmethod
    def get_settings(cls):
        settings = super(cls, cls).get_settings()
        settings = scraper_utils.disable_sub_check(settings)
        name = cls.get_name()
        settings.append('         <setting id="%s-filter" type="slider" range="0,180" option="int" label="     %s" default="60" visible="eq(-4,true)"/>' % (name, i18n('filter_results_days')))
        return settings

    def _get_episode_url(self, show_url, video):
        force_title = scraper_utils.force_title(video)
        title_fallback = kodi.get_setting('title-fallback') == 'true'
        norm_title = scraper_utils.normalize_title(video.ep_title)
        page_url = [show_url]
        too_old = False
        while page_url and not too_old:
            url = urllib.parse.urljoin(self.base_url, page_url[0])
            headers = {'User-Agent': LOCAL_UA}
            html = self._http_get(url, require_debrid=True, cache_limit=.1)
            headings = re.findall('<h2>\s*<a\s+href="([^"]+)[^>]+>(.*?)</a>', html)
            posts = dom_parser.parse_dom(html, 'div', {'id': 'post-\d+'})
            for heading, post in zip(headings, posts):
                if self.__too_old(post):
                    too_old = True
                    break
                if CATEGORIES[VIDEO_TYPES.TVSHOW] in post and show_url in post:
                    url, title = heading
                    if not force_title:
                        if scraper_utils.release_check(video, title, require_title=False):
                            return scraper_utils.pathify_url(url)
                    else:
                        if title_fallback and norm_title:
                            match = re.search('<strong>(.*?)</strong>', post)
                            if match and norm_title == scraper_utils.normalize_title(match.group(1)):
                                return scraper_utils.pathify_url(url)
                
            page_url = dom_parser.parse_dom(html, 'a', {'class': 'nextpostslink'}, ret='href')
    
    def search(self, video_type, title, year, season=''):  # @UnusedVariable
        results = []
        if video_type == VIDEO_TYPES.TVSHOW and title:
            test_url = '/show/%s/' % (self.__to_slug(title))
            test_url = urllib.parse.urljoin(self.base_url, test_url)
            headers = {'User-Agent': LOCAL_UA}
            html = self._http_get(test_url, require_debrid=True, cache_limit=.4)
            posts = dom_parser.parse_dom(html, 'div', {'id': 'post-\d+'})
            if posts and CATEGORIES[video_type] in posts[0]:
                match = re.search('<div[^>]*>\s*show\s+name:.*?<a\s+href="([^"]+)[^>]+>(?!Season\s+\d+)([^<]+)', posts[0], re.I)
                if match:
                    show_url, match_title = match.groups()
                    result = {'url': scraper_utils.pathify_url(show_url), 'title': scraper_utils.cleanse_title(match_title), 'year': ''}
                    results.append(result)
        elif video_type == VIDEO_TYPES.MOVIE:
            search_url = urllib.parse.urljoin(self.base_url, '/?s=%s')
            search_title = re.sub('[^A-Za-z0-9 ]', '', title.lower())
            search_url = search_url % (urllib.parse.quote_plus(search_title))
            headers = {'User-Agent': LOCAL_UA}
            html = self._http_get(search_url, require_debrid=True, cache_limit=.1)
            headings = re.findall('<h2>\s*<a\s+href="([^"]+).*?">(.*?)</a>', html)
            posts = dom_parser.parse_dom(html, 'div', {'id': 'post-\d+'})
            norm_title = scraper_utils.normalize_title(title)
            for heading, post in zip(headings, posts):
                if not re.search('[._ -]S\d+E\d+[._ -]', heading[1], re.I) and not self.__too_old(post):
                    post_url, post_title = heading
                    post_title = re.sub('<[^>]*>', '', post_title)
                    match = re.search('(.*?)\s*[.\[(]?(\d{4})[.)\]]?\s*(.*)', post_title)
                    if match:
                        match_title, match_year, extra_title = match.groups()
                        full_title = '%s [%s]' % (match_title, extra_title)
                    else:
                        full_title = match_title = post_title
                        match_year = ''
                    
                    match_norm_title = scraper_utils.normalize_title(match_title)
                    if (match_norm_title in norm_title or norm_title in match_norm_title) and (not year or not match_year or year == match_year):
                        result = {'url': scraper_utils.pathify_url(post_url), 'title': scraper_utils.cleanse_title(full_title), 'year': match_year}
                        results.append(result)
        
        return results

    def __to_slug(self, title):
        slug = title.lower()
        slug = re.sub('[^A-Za-z0-9 -]', ' ', slug)
        slug = re.sub('\s\s+', ' ', slug)
        slug = re.sub(' ', '-', slug)
        return slug
        
    def __too_old(self, post):
        filter_days = datetime.timedelta(days=int(kodi.get_setting('%s-filter' % (self.get_name()))))
        if filter_days:
            today = datetime.date.today()
            match = re.search('<span\s+class="date">(.*?)\s+(\d+)[^<]+(\d{4})<', post)
            if match:
                try:
                    mon_name, post_day, post_year = match.groups()
                    post_month = SHORT_MONS.index(mon_name) + 1
                    post_date = datetime.date(int(post_year), post_month, int(post_day))
                    if today - post_date > filter_days:
                        return True
                except ValueError:
                    return False
        
        return False