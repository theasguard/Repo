"""
    Asguard Kodi Addon
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

import json
import re
import urllib.parse
import urllib.request
import urllib.error
import cache
from bs4 import BeautifulSoup, SoupStrainer
from asguard_lib import scraper_utils, control
from asguard_lib.constants import HOST_Q, QUALITIES, VIDEO_TYPES
from asguard_lib.jscrypto import jscrypto
from asguard_lib.third_party.malsync import MALSYNC
import kodi
import log_utils
from . import scraper

import logging
try:
    import resolveurl
except ImportError:
    control.notify(msg='ResolveURL import failed', duration=5000)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

BASE_URL = 'https://hianime.sx' if kodi.get_setting('Hianimealt-enable') == 'true' else 'https://hianime.to'
SEARCH_URL = '/search?keyword='
QUALITY_MAP = {'1080p': QUALITIES.HD1080, '720p': QUALITIES.HD720, '480p': QUALITIES.HIGH, '360p': QUALITIES.HIGH}

class Scraper(scraper.Scraper):
    base_url = BASE_URL
    debrid_resolvers = resolveurl

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url') or BASE_URL
        self.result_limit = kodi.get_setting(f'{self.get_name()}-result_limit')
        self.hosts = self._hosts()
        self.headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:102.0) Gecko/20100101 Firefox/102.0'}


    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'H!anime'

    @classmethod
    def _hosts(self):
        hosts = []
        for key, value in HOST_Q.items():
            hosts.extend(value)
        hosts = [i.lower() for i in hosts]
        return hosts

    def _link(self, data):
        links = data['links']
        for link in links:
            if link.lower().startswith('http'):
                return link

    def _domain(self, data):
        elements = urllib.parse.urlparse(self._link(data))
        domain = elements.netloc or elements.path
        domain = domain.split('@')[-1].split(':')[0]
        result = re.search('(?:www\.)?([\w\-]*\.[\w\-]{2,3}(?:\.[\w\-]{2,3})?)$', domain)
        if result: domain = result.group(1)
        return domain.lower()

    def resolve_link(self, link):
        return link

    def resolve_sources(self, sources):
        return sources

    def get_sources(self, video):
        """
        Fetches sources for the given video.

        :param video: The video to fetch sources for.
        :return: A list of sources.
        """
        sources = []
        query = self.__build_query(video)
        search_url = scraper_utils.urljoin(self.base_url, SEARCH_URL + query)
        logger.debug("Retrieved show from database: %s", search_url)
        html = self._http_get(search_url, data=query)
        logger.debug(f"Search HTML: {html}")

        if not html:
            logger.error("Search HTML is empty")
            return sources

        soup = BeautifulSoup(html, 'html.parser')
        items = soup.find_all('div', {'class': 'list_search_ajax'})

        for item in items:
            title = item.find('a').text.strip()
            if video.title.lower() in title.lower():
                slug = item.find('a').get('href').split('/')[-1]
                sources.extend(self._process_aw(slug, video))

        return sources

    def __build_query(self, video):
        query = re.sub(r'[^A-Za-z0-9\s\.-]+', '', video.title)
        if video.video_type == VIDEO_TYPES.MOVIE:
            query += f' {video.year}'
        else:
            query += f' {video.title}'
        return urllib.parse.quote_plus(query)

    def _process_aw(self, slug, title, episode, langs):
        sources = []
        headers = {'Referer': self.base_url}
        r = self._http_get(self.base_url + 'ajax/v2/episode/list/' + slug.split('-')[-1], headers=headers, XHR=True, allow_redirect=True)
        logger.debug(f"Episode List HTML: {r}")
        res = json.loads(r).get('html')
        elink = SoupStrainer('div', {'class': re.compile('^ss-list')})
        ediv = BeautifulSoup(res, "html.parser", parse_only=elink)
        items = ediv.find_all('a')
        e_id = [x.get('data-id') for x in items if x.get('data-number') == episode]
        if e_id:
            params = {'episodeId': e_id[0]}
            r = self._http_get(self.base_url + 'ajax/v2/episode/servers', data=params, headers=headers, XHR=True)
            eres = json.loads(r).get('html')
            for lang in langs:
                elink = SoupStrainer('div', {'data-type': lang})
                sdiv = BeautifulSoup(eres, "html.parser", parse_only=elink)
                srcs = sdiv.find_all('div', {'class': 'item'})
                for src in srcs:
                    slink = src.get('data-video')
                    edata_name = src.get('data-name')
                    if 'streamtape' in slink:
                        source = {
                            'release_title': '{0} - Ep {1}'.format(title, episode),
                            'url': slink,
                            'quality': '720p',
                            'debrid_only': False,
                            'multi-part': False,
                            'direct': True,
                            'class': self,
                            'host': 'stream',
                            'size': 'NA',
                            'info': ['DUB' if lang == 'dub' else 'SUB', edata_name],
                            'lang': 2 if lang == 'dub' else 0
                        }
                        sources.append(source)
                    else:
                        headers = {'Referer': slink}
                        sl = urllib.parse.urlparse(slink)
                        spath = sl.path.split('/')
                        spath.insert(2, 'ajax')
                        sid = spath.pop(-1)
                        eurl = '{}://{}{}/getSources'.format(sl.scheme, sl.netloc, '/'.join(spath))
                        params = {'id': sid}
                        res = self._http_get(eurl, data=params, headers=headers, XHR=True, allow_redirect=True)
                        logger.debug(f"Get Sources HTML: {res}")
                        res = json.loads(res)
                        subs = res.get('tracks')
                        if subs:
                            subs = [{'url': x.get('file'), 'lang': x.get('label')} for x in subs if x.get('kind') == 'captions']
                        skip = {}
                        if res.get('intro'):
                            skip.update({'intro': res.get('intro')})
                        if res.get('outro'):
                            skip.update({'outro': res.get('outro')})
                        if res.get('encrypted'):
                            slink = self._process_link(res.get('sources'))
                        else:
                            slink = res.get('sources')[0].get('file')
                        if not slink:
                            continue
                        res = self._http_get(slink, headers=headers, allow_redirect=True)
                        logger.debug(f"Source HTML: {res}")
                        quals = re.findall(r'#EXT.+?RESOLUTION=\d+x(\d+).+\n(?!#)(.+)', res)
                        for qual, qlink in quals:
                            if qual is None:
                                continue
                            qual = int(qual)
                            if qual < 577:
                                quality = 'EQ'
                            elif qual < 721:
                                quality = '720p'
                            elif qual < 1081:
                                quality = '1080p'
                            else:
                                quality = '4K'

                            source = {
                                'release_title': '{0} - Ep {1}'.format(title, episode),
                                'url': urllib.parse.urljoin(slink, qlink),
                                'quality': quality,
                                'debrid_only': False,
                                'multi-part': False,
                                'direct': True,
                                'class': self,
                                'host': 'stream',
                                'size': 'NA',
                                'info': ['DUB' if lang == 'dub' else 'SUB', edata_name],
                                'lang': 2 if lang == 'dub' else 0,
                                'subs': subs,
                                'skip': skip
                            }
                            sources.append(source)
        return sources

    def _process_link(self, sources):
        keyhints = self.get_keyhints()
        try:
            key = ''
            orig_src = sources
            y = 0
            for m, p in keyhints:
                f = m + y
                x = f + p
                key += orig_src[f:x]
                sources = sources.replace(orig_src[f:x], '')
                y += p
            sources = json.loads(jscrypto.decode(sources, key))
            return sources[0].get('file')
        except:
            control.log('decryption key not working')
            return ''

    def get_keyhints(self):
        def to_int(num):
            if num.startswith('0x'):
                return int(num, 16)
            return int(num)

        def chunked(varlist, count):
            return [varlist[i:i + count] for i in range(0, len(varlist), count)]

        js = self._http_get(self.js_file, allow_redirect=True)
        cases = re.findall(r'switch\(\w+\){([^}]+?)partKey', js)[0]
        vars = re.findall(r"\w+=(\w+)", cases)
        consts = re.findall(r"((?:[,;\s]\w+=0x\w{1,2}){%s,})" % len(vars), js)[0]
        indexes = []
        for var in vars:
            var_value = re.search(r',{0}=(\w+)'.format(var), consts)
            if var_value:
                indexes.append(to_int(var_value.group(1)))

        return chunked(indexes, 2)

    @classmethod
    def get_settings(cls):
        settings = super(cls, cls).get_settings()
        name = cls.get_name()
        settings.append(f'<setting id="{name}-result_limit" label="     Result Limit" type="slider" default="10" range="10,100" option="int" visible="true"/>')
        return settings