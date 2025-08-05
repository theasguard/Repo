import re
from urllib.parse import quote_plus, unquote_plus
import logging
import urllib.request
import urllib.error
import xbmcgui
import kodi
import log_utils, workers
from asguard_lib import scraper_utils, control, client
from asguard_lib.constants import FORCE_NO_MATCH, VIDEO_TYPES, QUALITIES, DELIM
from asguard_lib.utils2 import i18n
from . import scraper
from . import proxy

try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)

logger = log_utils.Logger.get_logger()

BASE_URL = 'https://isohunts.to'
SEARCH_URL = '/torrent/?ihq=%s&fiht=2&age=0&Torrent_sort=seeders&Torrent_page=0'
VIDEO_EXT = ['MKV', 'AVI', 'MP4']

class Scraper(scraper.Scraper):
    base_url = BASE_URL
    debrid_resolvers = resolveurl

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url')
        self.min_seeders = 0

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'IsoHunt2'

    def get_sources(self, video):
        sources = []
        source_url = self.get_url(video)

        html = self._http_get(source_url, require_debrid=True)
        rows = client.parseDOM(html, 'tr', attrs={'data-key': '0'})
        threads = []
        for row in rows:
            threads.append(workers.Thread(self._get_sources, row, sources, video))
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        return sources

    def _get_sources(self, row, sources, video):
        row = re.sub(r'[\n\t]', '', row)
        data = re.findall(r'<a\s*href\s*=\s*["\'](/torrent_details/.+?)["\']><span>(.+?)</span>.*?<td\s*class\s*=\s*["\']size-row["\']>(.+?)</td><td\s*class\s*=\s*["\']sn["\']>([0-9]+)</td>', row, re.I)
        if not data:
            return
        for items in data:
            try:
                link = f'{self.base_url}{items[0]}'
                result = client.request(link, timeout=5)
                if not result:
                    continue
                try:
                    url = unquote_plus(re.search(r'(magnet.*?)["\']', result).group(1)).replace('&amp;', '&').split('&tr')[0].replace(' ', '.')
                except:
                    continue
                url = unquote_plus(url)
                hash = re.search(r'btih:(.*?)&', url, re.I).group(1)
                name = scraper_utils.cleanTitle(url.split('&dn=')[1])

                try:
                    seeders = int(items[3].replace(',', ''))
                    if self.min_seeders > seeders:
                        continue
                except:
                    seeders = 0

                quality = scraper_utils.get_tor_quality(name)
                label = f"{name}"

                hoster = {
                    'label': label,
                    'class': self,
                    'host': 'magnet',                    
                    'multi-part': False,
                    'hash': hash,
                    'url': url,
                    'quality': quality,
                    'direct': False,
                    'debridonly': True
                }
                sources.append(hoster)
            except:
                logger.log('IsoHunt2: Error getting sources', log_utils.LOGERROR)

    def get_url(self, video):
        if video.video_type == VIDEO_TYPES.MOVIE:
            query = f'{video.title} {video.year}'
        else:
            query = f'{video.title} S{int(video.season):02d}E{int(video.episode):02d}'
        return f'{self.base_url}{SEARCH_URL % quote_plus(query)}'
