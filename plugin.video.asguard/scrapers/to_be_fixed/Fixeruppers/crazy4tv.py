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
import datetime
import re
import urllib
import urlparse
import kodi
import log_utils  # @UnusedImport
import dom_parser
import dom_parser2
from asguard_lib.utils2 import i18n
from asguard_lib import scraper_utils
from asguard_lib.constants import FORCE_NO_MATCH
from asguard_lib.constants import VIDEO_TYPES
from asguard_lib.utils2 import i18n
import scraper

BASE_URL = 'http://crazy4tv.com'

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting('%s-base_url' % (self.get_name()))

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Crazy4'

    def get_sources(self, video):
        source_url = self.get_url(video)
        hosters = []
        if source_url and source_url != FORCE_NO_MATCH:
            url = urlparse.urljoin(self.base_url, source_url)
            html = self._http_get(url, require_debrid=True, cache_limit=.5)
            post = dom_parser.parse_dom(html, 'div', {'class': 'entry-content'})
            if post:
                for p in dom_parser.parse_dom(post[0], 'p'):
                    for match in re.finditer('href="([^"]+)[^>]+>([^<]+)', p):
                        stream_url, q_str = match.groups()
                        if re.search('\.part\.?\d+', q_str, re.I) or '.rar' in q_str or 'sample' in q_str or q_str.endswith('.nfo'): continue
                        host = urlparse.urlparse(stream_url).hostname
                        if video.video_type == VIDEO_TYPES.MOVIE:
                            meta = scraper_utils.parse_movie_link(q_str)
                        else:
                            meta = scraper_utils.parse_episode_link(q_str)
                        quality = scraper_utils.height_get_quality(meta['height'])
                        hoster = {'multi-part': False, 'host': host, 'class': self, 'views': None, 'url': stream_url, 'rating': None, 'quality': quality, 'direct': False}
                        if 'format' in meta: hoster['format'] = meta['format']
                        hosters.append(hoster)
        return hosters

    def get_url(self, video):
        return self._blog_get_url(video)

    @classmethod
    def get_settings(cls):
        settings = super(cls, cls).get_settings()
        settings = scraper_utils.disable_sub_check(settings)
        name = cls.get_name()
        settings.append('         <setting id="%s-select" type="enum" label="     %s" lvalues="30636|30637" default="0" visible="eq(-4,true)"/>' % (name, i18n('auto_select')))
        return settings

    def search(self, video_type, title, year, season=''):
        search_url = urlparse.urljoin(self.base_url, '/?s=%s')
        search_url = search_url % (urllib.quote_plus(title))
        html = self._http_get(search_url, require_debrid=True, cache_limit=1)
        post_pattern = 'class="entry-title">\s*<a[^>]+href="(?P<url>[^"]+)[^>]*>(?P<post_title>[^<]+)'
        return self._blog_proc_results(html, post_pattern, '', video_type, title, year)