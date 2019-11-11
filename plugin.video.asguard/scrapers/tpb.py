"""
    Death Streams Addon
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

import datetime
import re
import sys
import urllib
import urlparse
import log_utils  # @UnusedImport
import dom_parser
import dom_parser2
import kodi
import scraper
from asguard_lib import cfscrape
from asguard_lib.utils2 import i18n
from asguard_lib import scraper_utils
from asguard_lib.constants import FORCE_NO_MATCH
from asguard_lib.constants import SHORT_MONS
from asguard_lib.constants import VIDEO_TYPES
from asguard_lib import debrid

BASE_URL = 'https://openpirate.org/'
CATEGORIES = {VIDEO_TYPES.MOVIE: '/category/movies/', VIDEO_TYPES.TVSHOW: '/category/tv-shows/'}
LOCAL_UA = 'Asguard for Kodi/%s' % (kodi.get_version())
SEARCH_URL = '/search.php?q=%s&page=0&orderby=99'

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting('%s-base_url' % (self.get_name()))
        self.scraper = cfscrape.create_scraper()

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE, VIDEO_TYPES.MOVIE])

    @classmethod
    def get_name(cls):
        return 'TPB'

    def format_source_label(self, item):
        pass
    
    def get_sources(self, video_type, title, year, season='', episode=''):
        source_url = self.get_url(title)
        hosters = []
        if not source_url or source_url == FORCE_NO_MATCH: return hosters
        page_url = scraper_utils.urljoin(self.base_url, source_url)

    @classmethod
    def get_settings(cls):
        settings = super(cls, cls).get_settings()
        settings = scraper_utils.disable_sub_check(settings)
        name = cls.get_name()
        settings.append('         <setting id="%s-filter" type="slider" range="0,180" option="int" label="     %s" default="60" visible="eq(-3,true)"/>' % (name, i18n('filter_results_days')))
        return settings

# Result may need a small edit you can compare between other scrapers
    def get_url(self, video):
        result = self.db_connection().get_related_url(video.video_type, video.title, video.year, self.get_name(), video.season, video.episode)
        if result:
            return result[0][0]

    def search(self, video_type, title, year):                                                           # part of the link on search results page.
        results = []
        page_url = scraper_utils.urljoin(self.base_url, '/search.php?q=%s&page=0&orderby=99')
        norm_title = scraper_utils.normalize_title(title)
        for _attrs, td in dom_parser2.parse_dom(html, 'td', {'class': 'topic_content'}):

            match_title, match_year = scraper_utils.extra_year(norm_title)
            if (norm_title in scraper_utils.normalize_title(match_title)) and (not year or not match_year or year == match_year):
                result = {'url': scraper_utils.pathify_url(page_url), 'title': scraper_utils.cleanse_title(match_title), 'year': match_year}
                results.append(result)

        return results

    def _get_episode_url(self, show_url, video):
        episode_pattern = '"href="([^"]+/season-%s-episode-%s)">' % (video.season, video.episode)
        title_pattern = 'href="(?P<url>[^"]+).*?class="tv_episode_name">\s+-\s+(?P<title>[^<]+)'
        airdate_pattern = 'href="([^"]+)(?:[^<]+<){3}span\s+class="tv_episode_airdate">\s+-\s+{year}-{p_month}-{p_day}'
        show_url = scraper_utils.urljoin(self.base_url, show_url)
        html = self._http_get(show_url, cache_limit=2)
        fragment = dom_parser2.parse_dom(html, 'div', {'data-id': video.season, 'class': 'show_season'})
        return self._default_get_episode_url(fragment or html, video, episode_pattern, title_pattern, airdate_pattern)

    def resolve(self, url):
        return url