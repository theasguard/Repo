import re
import logging
import urllib.parse
from bs4 import BeautifulSoup, SoupStrainer
import resolveurl
import log_utils
from asguard_lib import scraper_utils
from asguard_lib.utils2 import i18n
from asguard_lib.constants import VIDEO_TYPES, QUALITIES
import kodi
from asguard_lib import utils2
from . import scraper
import concurrent.futures

logging.basicConfig(level=logging.DEBUG)

logger = log_utils.Logger.get_logger()
BASE_URL = 'https://1337x.to'
SEARCH_URL_MOVIE = '/sort-category-search/%s/Movies/size/desc/1/'
SEARCH_URL_TV = '/sort-category-search/%s/TV/size/desc/1/'
QUALITY_MAP = {'1080p': QUALITIES.HD1080, '720p': QUALITIES.HD720, '480p': QUALITIES.HIGH, '360p': QUALITIES.MEDIUM}

class Scraper(scraper.Scraper):
    base_url = BASE_URL
    debrid_resolvers = resolveurl

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url')
        self.result_limit = kodi.get_setting(f'{self.get_name()}-result_limit')
        self.min_seeders = 0

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return '1337x'

    def resolve_link(self, link):
        return link

    def get_sources(self, video):
        hosters = []
        query = self._build_query(video)
        if video.video_type == VIDEO_TYPES.EPISODE:
            search_url = scraper_utils.urljoin(self.base_url, SEARCH_URL_TV % urllib.parse.quote_plus(query))
        elif video.video_type == VIDEO_TYPES.MOVIE:
            search_url = scraper_utils.urljoin(self.base_url, SEARCH_URL_MOVIE % urllib.parse.quote_plus(query))

        html = self._http_get(search_url, require_debrid=True, cache_limit=1)
        soup = BeautifulSoup(html, "html.parser", parse_only=SoupStrainer('tbody'))


        items = []
        for entry in soup.select("tr"):
            try:
                columns = entry.find_all('td')
                name = columns[0].find_all('a')[1].text.strip()
                # logging.debug("Retrieved name: %s", name)
                torrent_page = columns[0].find_all('a')[1].get('href')
                # logging.debug("Retrieved torrent page: %s", torrent_page)
                torrent_page_url = urllib.parse.urljoin(self.base_url, torrent_page)
                # logging.debug("Retrieved torrent page url: %s", torrent_page_url)
                items.append((name, torrent_page_url))
            except Exception as e:
                logging.error("Error parsing entry: %s", str(e))
                continue
                
        def fetch_source(item):
            try:
                name, torrent_page_url = item
                torrent_page_html = self._http_get(torrent_page_url, cache_limit=1)
                # logging.debug("Retrieved torrent page html: %s", torrent_page_html)
                magnet = re.search(r'href\s*=\s*["\'](magnet:.+?)["\']', torrent_page_html, re.I).group(1)
                # logging.debug("Retrieved magnet: %s", magnet)
                
                size = columns[4].text
                # logging.debug("Retrieved size: %s", size)
                seeders = int(columns[1].text.replace(',', ''))
                # logging.debug("Retrieved seeders: %s", seeders)

                if self.min_seeders > seeders:
                    return

                quality = scraper_utils.get_tor_quality(name)

                host = scraper_utils.get_direct_hostname(self, magnet)
                label = f"{name} | {size} | {seeders} seeders"
                hosters.append({
                    'name': name,
                    'label': label,
                    'multi-part': False,
                    'class': self,
                    'url': magnet,
                    'size': size,
                    'seeders': seeders,
                    'quality': quality,
                    'host': 'magnet',
                    'direct': False,
                    'debridonly': True
                })
                # logging.debug("Retrieved sources: %s", hosters[-1])
            except Exception as e:
                logging.error("Error fetching source: %s", str(e))

        with concurrent.futures.ThreadPoolExecutor() as executor:
            executor.map(fetch_source, items)

        return self._filter_sources(hosters, video)

    def _build_query(self, video):
        query = video.title

        if video.video_type == VIDEO_TYPES.MOVIE:
            query += f' {video.year}'
        else:
            query += f' S{int(video.season):02d}E{int(video.episode):02d}'
        query = query.replace(' ', '+').replace('+-', '-')
        return query

    def _filter_sources(self, hosters, video):
        filtered_sources = []
        for source in hosters:
            if video.video_type == VIDEO_TYPES.TVSHOW:
                if not self._match_episode(source['title'], video.trakt_id, video.season, video.episode):
                    continue
            filtered_sources.append(source)
        return filtered_sources

    def _match_episode(self, video, season, episode):
        regex_ep = re.compile(r'\bS(\d+)E(\d+)\b')
        match = regex_ep.search(video.title)
        if match:
            season_num = int(match.group(1))
            episode_num = int(match.group(2))
            if season_num == int(video.season) and episode_num == int(video.episode):
                return True
        return False

    def _http_get(self, url, data=None, retry=True, allow_redirect=True, cache_limit=8, require_debrid=True):
        if require_debrid:
            if Scraper.debrid_resolvers is None:
                Scraper.debrid_resolvers = [resolver for resolver in resolveurl.relevant_resolvers() if resolver.isUniversal()]
            if not Scraper.debrid_resolvers:
                logger.log('%s requires debrid: %s' % (self.__module__, Scraper.debrid_resolvers), log_utils.LOGDEBUG)
                return ''
        try:
            headers = {'User-Agent': scraper_utils.get_ua()}
            req = urllib.request.Request(url, data=data, headers=headers)
            logging.debug("HTTP request: %s", req)
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return response.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            logger.log(f'HTTP Error: {e.code} - {url}', log_utils.LOGWARNING)
        except urllib.error.URLError as e:
            logger.log(f'URL Error: {e.reason} - {url}', log_utils.LOGWARNING)
        return ''
    
    @classmethod
    def get_settings(cls):
        settings = super(cls, cls).get_settings()
        name = cls.get_name()
        parent_id = f"{name}-enable"
        
        settings.extend([
            f'''\t\t<setting id="{name}-result_limit" type="integer" label="30229" help="">
\t\t\t<level>0</level>
\t\t\t<default>0</default>
\t\t\t<constraints>
\t\t\t\t<minimum>0</minimum>
\t\t\t\t<maximum>100</maximum>
\t\t\t</constraints>
\t\t\t<dependencies>
\t\t\t\t<dependency type="visible">
\t\t\t\t\t<condition operator="is" setting="{parent_id}">true</condition>
\t\t\t\t</dependency>
\t\t\t</dependencies>
\t\t\t<control type="slider" format="integer">
\t\t\t\t<popup>false</popup>
\t\t\t</control>
\t\t</setting>'''
        ])
        
        return settings