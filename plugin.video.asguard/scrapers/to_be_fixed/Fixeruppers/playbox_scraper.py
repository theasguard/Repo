"""
    Asguard Addon
    Copyright (C) 2014 Mr Blamo.Blamo

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
import urllib
import urlparse
import kodi
import log_utils  # @UnusedImport
import base64
import dom_parser
import dom_parser2
from asguard_lib import scraper_utils
from asguard_lib.constants import FORCE_NO_MATCH
from asguard_lib.constants import VIDEO_TYPES
from asguard_lib.constants import QUALITIES
from asguard_lib.constants import Q_ORDER
from asguard_lib.utils2 import i18n
import scraper

BASE_URL = 'http://playboxhd.net'
SEARCH_URL = '/api/box?type=search&keyword=%s&os=Android&v=2.0.2&k=0'
DETAIL_URL = '/api/box?type=detail&id=%s&os=Android&v=2.0.2&k=0'
STREAM_URL = '/api/box?type=stream&id=%s&os=Android&v=2.0.2&k=0'
PB_KEY = base64.decodestring('cXdlcnR5dWlvcGFzZGZnaGprbHp4YzEyMzQ1Njc4OTA=')
IV = '\0' * 16

RESULT_URL = '/video_type=%s&id=%s'
QUALITY_MAP = {'720p': QUALITIES.HD720, '1080p': QUALITIES.HD1080, '360p': QUALITIES.MEDIUM, 'Auto': QUALITIES.HIGH}


class Playbox_Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = xbmcaddon.Addon().getSetting('%s-base_url' % (self.get_name()))

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.TVSHOW, VIDEO_TYPES.SEASON, VIDEO_TYPES.EPISODE, VIDEO_TYPES.MOVIE])

    @classmethod
    def get_name(cls):
        return 'PlayBox'

    def resolve_link(self, link):
        return link

    def format_source_label(self, item):
        if 'resolution' in item:
            return '[%s] (%s) %s' % (item['quality'], item['resolution'], item['host'])
        else:
            return '[%s] %s' % (item['quality'], item['host'])

    def get_sources(self, video):
        source_url = self.get_url(video)
        sources = []
        if source_url:
            params = urlparse.parse_qs(source_url)
            # movie ids are to the catalog, episode ids are to the stream
            if video.video_type == VIDEO_TYPES.MOVIE:
                stream_id = self.__get_movie_stream_id(params['id'][0])
            else:
                stream_id = params['id'][0]

            if stream_id:
                stream_url = STREAM_URL % (stream_id)
                url = urlparse.urljoin(self.base_url, stream_url)
                html = self._http_get(url, cache_limit=.5)
                try:
                    js_data = json.loads(html)
                except ValueError:
                    log_utils.log('Invalid JSON returned for: %s' % (url), xbmc.LOGWARNING)
                else:
                    for stream in js_data['data']:
                        stream_url = self.__decrypt(base64.decodestring(stream['stream']))
                        if stream['server'] == 'ggvideo':
                            direct = True
                            quality = self._gv_get_quality(stream_url)
                            host = self._get_direct_hostname(stream_url)
                            if 'http' not in stream_url: continue
                        elif stream['server'] == 'amvideo':
                            for match in re.finditer('<iframe\s+src="([^"]+)', stream_url, re.I):
                                embed_url = match.group(1)
                                host = urlparse.urlparse(embed_url).hostname.lower()
                                quality = self._get_quality(video, host, QUALITIES.HIGH)
                                source = {'multi-part': False, 'url': embed_url, 'host': host, 'class': self, 'quality': quality, 'views': None, 'rating': None, 'direct': False}
                                if 'quality' in stream: source['resolution'] = stream['quality']
                                sources.append(source)
                            continue
                        else:
                            try:
                                direct = False
                                host = urlparse.urlparse(stream_url).hostname.lower()
                                quality = self._get_quality(video, host, QUALITIES.HIGH)
                            except:
                                continue
                        source = {'multi-part': False, 'url': stream_url, 'host': host, 'class': self, 'quality': quality, 'views': None, 'rating': None, 'direct': direct}
                        if 'quality' in stream: source['resolution'] = stream['quality']
                        sources.append(source)
            
        return sources

    def __get_movie_stream_id(self, catalog_id):
        detail_url = DETAIL_URL % (catalog_id)
        url = urlparse.urljoin(self.base_url, detail_url)
        html = self._http_get(url, cache_limit=.5)
        try:
            js_data = json.loads(html)
        except ValueError:
            log_utils.log('Invalid JSON returned for: %s' % (url), xbmc.LOGWARNING)
        else:
            if js_data['data']['chapters']:
                return js_data['data']['chapters'][0]['id']

    def __decrypt(self, cipher_text):
        decrypter = pyaes.Decrypter(pyaes.AESModeOfOperationCBC(PB_KEY, IV))
        plain_text = decrypter.feed(cipher_text)
        plain_text += decrypter.feed()
        return plain_text
        
    def get_url(self, video):
        return super(Playbox_Scraper, self)._default_get_url(video)

    def _get_episode_url(self, show_url, video):
        params = urlparse.parse_qs(show_url)
        show_url = DETAIL_URL % (params['id'][0])
        url = urlparse.urljoin(self.base_url, show_url)
        html = self._http_get(url, cache_limit=.5)
        try:
            js_data = json.loads(html)
        except ValueError:
            log_utils.log('Invalid JSON returned for: %s' % (url), xbmc.LOGWARNING)
        else:
            force_title = self._force_title(video)
            if not force_title and 'chapters' in js_data['data']:
                for chapter in js_data['data']['chapters']:
                    if 'S%02dE%03d' % (int(video.season), int(video.episode)) == chapter['title']:
                        return RESULT_URL % (video.video_type, chapter['id'])
    
    def search(self, video_type, title, year):
        results = []
        search_url = urlparse.urljoin(self.base_url, SEARCH_URL)
        search_url = search_url % (urllib.quote_plus(title))
        html = self._http_get(search_url, cache_limit=.25)
        if html:
            try:
                js_data = json.loads(html)
            except ValueError:
                log_utils.log('Invalid JSON returned for: %s' % (search_url), xbmc.LOGWARNING)
            else:
                if 'films' in js_data['data']:
                    for item in js_data['data']['films']:
                        result_url = RESULT_URL % (video_type, item['id'])
                        result = {'title': item['title'], 'url': result_url, 'year': ''}
                        results.append(result)
        return results

    def _http_get(self, url, data=None, cache_limit=8):
        return super(Playbox_Scraper, self)._cached_http_get(url, self.base_url, self.timeout, data=data, cache_limit=cache_limit)