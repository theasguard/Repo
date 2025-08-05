import logging
import re
import urllib.parse
import itertools
import pickle
from functools import partial
import kodi
import log_utils
import dom_parser2
from asguard_lib.ui import consumet
from asguard_lib import cloudflare
from asguard_lib import scraper_utils, control
from asguard_lib.constants import FORCE_NO_MATCH, VIDEO_TYPES, QUALITIES
from . import scraper
from . import proxy

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)
BASE_URL = 'https://gogoanime.ng'
LOCAL_UA = 'Asguard for Kodi/%s' % (kodi.get_version())
Q_MAP = {'TS': QUALITIES.LOW, 'CAM': QUALITIES.LOW, 'HDTS': QUALITIES.LOW, 'HD-720P': QUALITIES.HD720}

class Scraper(scraper.Scraper):
    base_url = BASE_URL
    
    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting('%s-base_url' % (self.get_name()))

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.SEASON, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'GogoHD'

    def get_sources(self, video):
        from asguard_lib import animedb
        all_results = []
        anime_db = animedb.AnimeDatabase()
        anilist_id = anime_db.get_thetvdb_id

        episode = video.episode
        title = video.title

        srcs = ['sub', 'dub']
        # if control.getSetting('general.source') == 'Sub':
        #     srcs.remove('dub')
        # elif control.getSetting('general.source') == 'Dub':
        #     srcs.remove('sub')

        for x in srcs:
            r = consumet.CONSUMETAPI().get_sources(anilist_id, episode, 'gogoanime', x)
            if r and r.get('sources'):
                sources = r.get('sources')
                for i in range(len(sources)):
                    sources[i].update({'type': x.upper()})
                referer = r.get('headers', {}).get('Referer', '')
                if referer:
                    referer = urllib.parse.urljoin(referer, '/')
                mapfunc = partial(self._process_ap, title=title, referer=referer)
                results = list(map(mapfunc, sources))
                results = list(itertools.chain(*results))
                all_results += results

        if not all_results:
            r = consumet.CONSUMETAPI().get_sources(anilist_id, episode, 'gogoanime')
            if r and r.get('url'):
                slink = r.get('url') + '|Referer={0}&User-Agent=iPad'.format(r.get('referer').split('?')[0])
                hoster = {'multi-part': False, 'label': title, 'hash': slink, 'class': self, 'language': 'en', 'source': 'torrent', 'url': slink, 'info': ['HLS'], 'host': 'magnet', 'quality': 'EQ', 'direct': False, 'debridonly': True, 'size': 'NA'}
                all_results.append(hoster)
            else:
                logging.error('No sources found for {0}'.format(title))

        return all_results

    def _process_ap(self, item, title='', referer=''):
        sources = []
        quality = 'EQ'
        slink = item.get('url') + '|Referer={0}&User-Agent=iPad'.format(referer)
        qual = item.get('quality')
        if qual.endswith('0p'):
            qual = int(qual[:-1])
            if qual < 361:
                quality = 'EQ'
            elif qual < 577:
                quality = 'NA'
            elif qual < 721:
                quality = '720p'
            elif qual < 1081:
                quality = '1080p'
            else:
                quality = '4K'

        source = {
            'release_title': title,
            'hash': slink,
            'class': self,
            'multi-part': False,
            'direct': False,
            'type': 'direct',
            'quality': quality,
            'debrid_only': False,
            'host': 'streamtape',
            'size': 'NA',
            'info': [item.get('type'), 'HLS' if item.get('isM3U8') else ''],
            'lang': 0 if item.get('type') == 'SUB' else 2
        }
        sources.append(source)
        logging.debug('sources: {0}'.format(sources))
        return sources

    def search(self, video_type, title, year, season=''):
        results = []
        search_url = scraper_utils.urljoin(self.base_url, '/?s=')
        title = re.sub('[^A-Za-z0-9 ]', '', title)
        title = re.sub('\s+', '-', title)
        search_url += title
        headers = {'User-Agent': LOCAL_UA}
        html = self._http_get(search_url, cache_limit=8)
        for _attrs, item in dom_parser2.parse_dom(html, 'div', {'class': 'ml-item'}):
            match_title = dom_parser2.parse_dom(item, 'span', {'class': 'mli-info'})
            match_url = dom_parser2.parse_dom(item, 'a', req='href')
            match_year = ''

            if not match_title or not match_url: continue
            match_url = match_url[0].attrs['href']
            match_title = match_title[0].content
            is_season = re.search('season\s+(\d+)', match_title, re.I)
            if (video_type == VIDEO_TYPES.MOVIE and not is_season) or (video_type == VIDEO_TYPES.SEASON and is_season):
                match_title = re.sub('</?h\d+>', '', match_title)
                if video_type == VIDEO_TYPES.SEASON:
                    if season and int(is_season.group(1)) != int(season): continue
                
                match_url += '/watching.html'
                if not year or not match_year or year == match_year:
                    result = {'title': scraper_utils.cleanse_title(match_title), 'year': match_year, 'url': scraper_utils.pathify_url(match_url)}
                    results.append(result)

        return results