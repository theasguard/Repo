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
import json
import re
import urllib
import kodi
import log_utils  # @UnusedImport
import utils
from asguard_lib import scraper_utils
from asguard_lib.constants import FORCE_NO_MATCH
from asguard_lib.constants import VIDEO_TYPES
from asguard_lib.utils2 import i18n
import scraper
import xbmcgui

BASE_URL = 'https://thepiratebays3.com'
SEARCH_URL = '/search/?%s'     # Can also add search under base url as Example SEARCH_URL = '?s=%s+%s&go=Sea'

class Tpb_Scraper(scraper.Scraper):
    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting('%s-base_url' % (self.get_name()))
    
    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.TVSHOW, VIDEO_TYPES.SEASON, VIDEO_TYPES.EPISODE, VIDEO_TYPES.MOVIE])

# Names of the scraper
    @classmethod
    def get_name(cls):
        return 'TPB'
    
    def resolve_link(self, link):
        return link

    def format_source_label(self, item):
        pass
    
    def get_sources(self, video_type, title, year, season='', episode=''):
        hosters = []
        source_url = self.get_url(video)
        if not source_url or source_url == FORCE_NO_MATCH: return hosters
        params = scraper_utils.parse_query(source_url)
        if 'title' in params:
            search_title = re.sub("[^A-Za-z0-9. ]", "", urllib.unquote_plus(params['title']))
            query = search_title
            if video.video_type == VIDEO_TYPES.MOVIE:
                if 'year' in params: query += ' %s' % (params['year'])
            else:
                sxe = ''
                if 'season' in params:
                    sxe = 'S%02d' % (int(params['season']))
                if 'episode' in params:
                    sxe += 'E%02d' % (int(params['episode']))
                if sxe: query = '%s %s' % (query, sxe)
            query_url = '/search?q=?%s' % (query)
            hosters = self.__get_links(query_url, video)
            if not hosters and video.video_type == VIDEO_TYPES.EPISODE and params['air_date']:
                query = urllib.quote_plus('%s %s' % (search_title, params['air_date'].replace('-', '.')))
                query_url = '/search?q=?%s' % (query)
                hosters = self.__get_links(query_url, video)

# Result may need a small edit you can compare between other scrapers
    def get_url(self, video):
        url = None
        result = self.db_connection().get_related_url(video.video_type, video.title, video.year, self.get_name(), video.season, video.episode)
        if result:
            url = result[0][0]
            logger.log('Got local related url: |%s|%s|%s|%s|%s|' % (video.video_type, video.title, video.year, self.get_name(), url), log_utils.LOGDEBUG)
        else:
            if video.video_type == VIDEO_TYPES.MOVIE:
                query = 'title=%s&year=%s' % (urllib.quote_plus(video.title), video.year)
            else:
                query = 'title=%s&season=%s&episode=%s&air_date=%s' % (urllib.quote_plus(video.title), video.season, video.episode, video.ep_airdate)
            url = '/search?q=?%s' % (query)
            self.db_connection().set_related_url(video.video_type, video.title, video.year, self.get_name(), url, video.season, video.episode)
        return url

    def search(self, video_type, title, year):
        return []
