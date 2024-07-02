import re
import logging
import urllib.parse
from bs4 import BeautifulSoup, SoupStrainer
from functools import partial
import resolveurl
import log_utils
from asguard_lib import scraper_utils
from asguard_lib.utils2 import i18n
from asguard_lib.constants import VIDEO_TYPES, QUALITIES
import kodi
from asguard_lib import utils2
from . import scraper

logging.basicConfig(level=logging.DEBUG)

logger = log_utils.Logger.get_logger()
BASE_URL = 'https://nyaa.si'
SEARCH_URL = '/?f=0&c=1_2&q=%s&s=downloads&o=desc'
QUALITY_MAP = {'1080p': QUALITIES.HD1080, '720p': QUALITIES.HD720, '480p': QUALITIES.HIGH, '360p': QUALITIES.MEDIUM}

class Scraper(scraper.Scraper):
    base_url = BASE_URL
    debrid_resolvers = resolveurl

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url')
        self.result_limit = kodi.get_setting(f'{self.get_name()}-result_limit')

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Nyaa'

    def resolve_link(self, link):
        logging.debug("Resolving link: %s", link)
        return link

    def get_sources(self, video):
        hosters = []
        query = self._build_query(video)
        if video.video_type == VIDEO_TYPES.TVSHOW:
            query = self._build_season_pack_query(video)
        search_url = scraper_utils.urljoin(self.base_url, SEARCH_URL % urllib.parse.quote_plus(query))
        logging.debug("Search URL: %s", search_url)
        html = self._http_get(search_url, require_debrid=True)
        logging.debug("Retrieved HTML: %s", html)
        soup = BeautifulSoup(html, "html.parser", parse_only=SoupStrainer('div', {'class': 'table-responsive'}))
        logging.debug("Parsed HTML: %s", soup)

        for entry in soup.select("tr.danger,tr.default,tr.success"):
            try:
                name = entry.find_all('a', {'class': None})[1].get('title')
                logging.debug("Retrieved name: %s", name)
                magnet = entry.find('a', {'href': re.compile(r'(magnet:)+[^"]*')}).get('href')
                logging.debug("Retrieved magnet: %s", magnet)
                size = entry.find_all('td', {'class': 'text-center'})[1].text.replace('i', '')
                logging.debug("Retrieved size: %s", size)
                downloads = int(entry.find_all('td', {'class': 'text-center'})[-1].text)
                logging.debug("Retrieved downloads: %s", downloads)

                quality_match = re.search(r'\b(1080p|720p|480p|360p)\b', name)
                if quality_match:
                    quality = QUALITY_MAP.get(quality_match.group(0), QUALITIES.HD1080)
                else:
                    quality = QUALITIES.HD1080
                logging.debug("Retrieved quality: %s", quality)

                host = scraper_utils.get_direct_hostname(self, magnet)
                label = f"{name} | {quality} | {size}"
                hosters.append({
                    'name': name,
                    'label': label,
                    'multi-part': False,
                    'class': self,
                    'url': magnet,
                    'size': size,
                    'downloads': downloads,
                    'quality': quality,
                    'host': 'magnet',
                    'direct': False,
                    'debridonly': True
                })
                logging.debug("Retrieved sources: %s", hosters[-1])
            except AttributeError as e:
                logging.error("Failed to append source: %s", str(e))
                continue

        return self._filter_sources(hosters, video)

    def _build_query(self, video):
        query = video.title
        logging.debug("Initial query: %s", query)
        if video.video_type == VIDEO_TYPES.EPISODE:
            query += f' S{int(video.season):02d}E{int(video.episode):02d}'
            logging.debug("Episode query: %s", query)
        elif video.video_type == VIDEO_TYPES.MOVIE:
            query += f' {video.year}'
            logging.debug("Movie query: %s", query)
        query = query.replace(' ', '+').replace('+-', '-')
        logging.debug("Final query: %s", query)
        return query

    def _build_season_pack_query(self, video):
        query = f'{video.title} "Batch"|"Complete Series"'
        logging.debug("Initial season pack query: %s", query)
        if video.video_type == VIDEO_TYPES.TVSHOW:
            query += f' S{int(video.season):02d}'
            logging.debug("Season pack query with season: %s", query)
        query = query.replace(' ', '+').replace('+-', '-')
        logging.debug("Final season pack query: %s", query)
        return query

    def _filter_sources(self, hosters, video):
        logging.debug("Filtering sources: %s", hosters)
        filtered_sources = []
        for source in hosters:
            if video.video_type == VIDEO_TYPES.EPISODE:
                if not self._match_episode(source['name'], video.season, video.episode):
                    continue
            filtered_sources.append(source)
            logging.debug("Filtered source: %s", source)
        return filtered_sources

    def _match_episode(self, title, season, episode):
        regex_ep = re.compile(r'\bS(\d+)E(\d+)\b')
        match = regex_ep.search(title)
        if match:
            season_num = int(match.group(1))
            episode_num = int(match.group(2))
            if season_num == int(season) and episode_num == int(episode):
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
        settings.append(f'         <setting id="{name}-result_limit" label="     {i18n("result_limit")}" type="slider" default="10" range="10,100" option="int" visible="true"/>')
        return settings
