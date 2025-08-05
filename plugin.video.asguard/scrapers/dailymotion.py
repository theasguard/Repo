import urllib.parse
import requests
from bs4 import BeautifulSoup
import re, kodi
import log_utils
from asguard_lib import scraper_utils, control
from asguard_lib.constants import FORCE_NO_MATCH, VIDEO_TYPES
from asguard_lib.utils2 import i18n
from . import scraper

logger = log_utils.Logger.get_logger()

BASE_URL = 'https://www.dailymotion.com'
SEARCH_URL = '/search/{query}'

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url')

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Dailymotion'

    def get_sources(self, video):
        hosters = []
        source_url = self.get_url(video)
        if not source_url or source_url == FORCE_NO_MATCH:
            return hosters

        query = self.__build_query(video)
        search_url = scraper_utils.urljoin(self.base_url, SEARCH_URL.format(query=query))
        html = self._http_get(search_url, cache_limit=.5)
        
        # Log the HTML content to verify it is being fetched correctly
        logger.log(f'Fetched HTML content for URL: {search_url}', log_utils.LOGDEBUG)
        logger.log(html, log_utils.LOGDEBUG)
        
        hosters.extend(self.__parse_sources(html, video))
        return hosters

    def __build_query(self, video):
        query = re.sub(r'[^A-Za-z0-9\s\.-]+', '', video.title)
        if video.video_type == VIDEO_TYPES.MOVIE:
            query += f' {video.year}'
        else:
            query += f' S{int(video.season):02d}E{int(video.episode):02d}'
        return urllib.parse.quote_plus(query)

    def __parse_sources(self, html, video):
        hosters = []
        soup = BeautifulSoup(html, 'html.parser')
        for video_tag in soup.find_all('a', class_='video_link'):
            try:
                url = video_tag['href']
                title = video_tag['title']
                quality = scraper_utils.get_quality(title)
                hosters.append({
                    'multi-part': False, 'class': self, 'views': None, 'url': url,
                    'rating': None, 'host': 'dailymotion', 'quality': quality, 'direct': True,
                    'debridonly': False, 'extra': title
                })
            except Exception as e:
                logger.log(f'Error parsing Dailymotion source: {e}', log_utils.LOGWARNING)
        return hosters

    def get_url(self, video):
        url = None
        result = self.db_connection().get_related_url(video.video_type, video.title, video.year, self.get_name(), video.season, video.episode)
        if result:
            url = result[0][0]
            logger.log(f'Got local related url: |{video.video_type}|{video.title}|{video.year}|{self.get_name()}|{url}|', log_utils.LOGDEBUG)
        else:
            query = self.__build_query(video)
            url = f'/search?query={query}'
            self.db_connection().set_related_url(video.video_type, video.title, video.year, self.get_name(), url, video.season, video.episode)
        return url

    def search(self, video_type, title, year, season=''):  # @UnusedVariable
        return []

    @classmethod
    def get_settings(cls):
        settings = super(cls, cls).get_settings()
        settings = scraper_utils.disable_sub_check(settings)
        name = cls.get_name()

        return settings

    # def _http_get(self, url, data=None, headers=None, allow_redirect=True, cache_limit=8):
    #     return super(self.__class__, self)._http_get(url, data=data, headers=headers, allow_redirect=allow_redirect, cache_limit=cache_limit)
