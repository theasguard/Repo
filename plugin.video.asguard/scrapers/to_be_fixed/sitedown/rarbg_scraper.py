"""
    Stream All The Sources Addon
    Copyright (C) 2017 k3l3vra

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
from asguard_lib import cloudflare
import dom_parser
import dom_parser2
import kodi
import log_utils  # @UnusedImport
import scraper
from asguard_lib import debrid
from asguard_lib.constants import FORCE_NO_MATCH
from asguard_lib.utils2 import SHORT_MONS
from asguard_lib.utils2 import i18n
from asguard_lib import scraper_utils

BASE_URL = 'https://rargb.to'
LOCAL_UA = 'Asguard for Kodi/%s' % (kodi.get_version())

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.search_link = '/search/?search={0}'
        self.min_seeders = int(control.setting('torrent.min.seeders'))
        self.base_url = kodi.get_setting('%s-base_url' % (self.get_name()))

    @classmethod
    def get_name(cls):
        return 'RARBG'

    def movie(self, imdb, title, localtitle, aliases, year):
        if debrid.status(True) is False:
            return

        try:
            url = {'imdb': imdb, 'title': title, 'year': year}
            url = urllib.urlencode(url)
            return url

    def tvshow(self, imdb, tvdb, tvshowtitle, localtvshowtitle, aliases, year):
        if debrid.status(True) is False:
            return

        try:
            url = {'imdb': imdb, 'tvdb': tvdb, 'tvshowtitle': tvshowtitle, 'year': year}
            url = urllib.urlencode(url)
            return url

    def episode(self, url, imdb, tvdb, title, premiered, season, episode):
        if debrid.status(True) is False:
            return

        try:
            if url is None:
                return

            url = urlparse.parse_qs(url)
            url = dict([(i, url[i][0]) if url[i] else (i, '') for i in url])
            url['title'], url['premiered'], url['season'], url['episode'] = title, premiered, season, episode
            url = urllib.urlencode(url)
            return url

    def get_sources(self, video):
        hosters = []
        source_url = self.get_url(video)
        if not source_url or source_url == FORCE_NO_MATCH: return hosters
        url = scraper_utils.urljoin(self.base_url, source_url)
        headers = {'User-Agent': LOCAL_UA}
        html = self._http_get(url, require_debrid=True, headers=headers, cache_limit=.5)
        try:
            sources = []

            if url is None:
                return sources

            data = urlparse.parse_qs(url)
            data = dict([(i, data[i][0]) if data[i] else (i, '') for i in data])

            title = data['tvshowtitle'] if 'tvshowtitle' in data else data['title']

            hdlr = 'S{:02d}E{:02d}'.format(int(data['season']), int(data['episode'])) if 'tvshowtitle' in data else data['year']

            query = '{0} S{1:02d}E{2:02d}'.format(
                data['tvshowtitle'], int(data['season']), int(data['episode'])) if 'tvshowtitle' in data else '{0} {1}'.format(
                data['title'], data['year'])
            query = re.sub('(\\\|/| -|:|;|\*|\?|"|<|>|\|)', ' ', query)

            # Using %20 for the search. However the site will accept + as well
            url = self.search_link.format(query.replace(' ', '%20'))
            url = urlparse.urljoin(self.base_url, url)

            shell = requests.Session()
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 6.1; Win64; x64; rv:69.0) Gecko/20100101 Firefox/69.0'
            }
            req = shell.get(url, headers=headers).content
            try:
                results = dom_parser2.parse_dom(req, 'tr', attrs={'class': 'lista2'})
            except Exception:
                return sources

            items = []

            for result in results:
                try:
                    t = re.compile('''title=['"](.*?)['"]>''').findall(result)[0]
                    u = re.compile('''<td align=['"]left['"]\s*class=['"]lista['"]>\s*<a\s*href=['"](.*?)['"]''').findall(result)
                    s = re.search('((?:\d+\.\d+|\d+\,\d+|\d+)\s*(?:GB|GiB|MB|MiB))', result)
                    s = s.groups()[0] if s else '0'
                    p = re.compile('''class=['"]lista['"]><font\s*color=['"].*?['"]>(.*?)</font>''').findall(result)
                    items += [(t, i, s, p) for i in u]
                except Exception:
                    pass

            for item in items:
                try:
                    seeders = ' '.join([str(x) for x in item[-1]])
                    if self.min_seeders > int(seeders):
                        continue

                    name = item[0]
                    name = dom_parser2.replaceHTMLCodes(name)

                    t = re.sub('(\.|\(|\[|\s)(\d{4}|S\d*E\d*|S\d*|3D)(\.|\)|\]|\s|)(.+|)', '', name, flags=re.I)

                    if not cleantitle.get(t) in cleantitle.get(title):
                        continue

                    if 'tvshowtitle' in data:
                        y = re.findall('[\.|\(|\[|\s|\_|\-](S\d*E\d*|S\d*)[\.|\)|\]|\s|\_|\-]', name)[-1].upper()
                    else:
                        y = re.findall('[\.|\(|\[|\s](\d{4})[\.|\)|\]|\s]', name)[-1].upper()

                    if not y == hdlr:
                        continue

                    page_url = urlparse.urljoin(self.base_url, item[1])
                    r = shell.get(page_url, headers=headers).content

                    try:
                        link = 'magnet:{0}'.format(re.findall('a href="magnet:(.*?)"', r, re.DOTALL)[0])
                        link = str(dom_parser2.replaceHTMLCodes(link).split('&tr')[0])
                    except Exception:
                        continue

                    quality, info = scraper_utils.get_release_quality(name, name)
                    try:
                        size = re.findall('((?:\d+\.\d+|\d+\,\d+|\d+)\s*(?:GB|GiB|MB|MiB))', item[2])[-1]
                        div = 1 if size.endswith(('GB', 'GiB')) else 1024
                        size = float(re.sub('[^0-9|/.|/,]', '', size)) / div
                        size = '{:.2f} GB'.format(size)
                        info.append(size)
                    except Exception:
                        pass

                    info = ' | '.join(info)

                    sources.append({'source': 'Torrent', 'quality': quality, 'language': 'en',
                                    'url': link, 'info': info, 'direct': False, 'debridonly': True})
                except Exception:
                    pass

            check = [i for i in sources if not i['quality'] == 'CAM']
            if check:
                sources = check

            return sources

    @classmethod
    def get_settings(cls):
        settings = super(cls, cls).get_settings()
        settings = scraper_utils.disable_sub_check(settings)
        name = cls.get_name()
        settings.append('         <setting id="%s-filter" type="slider" range="0,180" option="int" label="     %s" default="60" visible="eq(-3,true)"/>' % (name, i18n('filter_results_days')))
        return settings

    def search(self, video_type, title, year, season=''):  # @UnusedVariable
        results = []
        search_url = scraper_utils.urljoin(self.base_url, '/search/%s/')
        search_title = re.sub('[^A-Za-z0-9 ]', '', title.lower())
        search_url = search_url % (urllib.quote_plus(search_title))
        headers = {'User-Agent': LOCAL_UA}
        html = self._http_get(search_url, headers=headers, require_debrid=True, cache_limit=1)
        headings = re.findall('<h2>\s*<a\s+href="([^"]+).*?">(.*?)</a>', html)
        norm_title = scraper_utils.normalize_title(title)
        
        return results