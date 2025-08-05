import logging
import urllib.parse
import urllib.request
import urllib.error
import kodi
from asguard_lib.utils2 import i18n
from bs4 import BeautifulSoup
import requests
from asguard_lib import scraper_utils
from asguard_lib.constants import VIDEO_TYPES
from . import scraper

logger = logging.getLogger(__name__)
BASE_URL = 'https://pkmovies.xyz'
SEARCH_URL = '/search?q=%s'

class PkMoviesScraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = BASE_URL

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'PkMovies'

    def get_sources(self, video):
        hosters = []
        query = self._build_query(video)
        search_url = urllib.parse.urljoin(self.base_url, SEARCH_URL % urllib.parse.quote_plus(query))
        html = self._http_get(search_url)
        soup = BeautifulSoup(html, "html.parser")

        for item in soup.select("#searchResult li"):
            try:
                title = item.text
                data_id = item.get('data-id')
                if title and data_id:
                    hosters.append({
                        'class': self,
                        'title': title,
                        'host': title,
                        'direct': False,
                        'debridonly': False,
                        'multi-part': False,
                        'url': f"{self.base_url}/download?id={data_id}"
                    })
            except Exception as e:
                logger.error(f"Error parsing item: {e}")

        return hosters

    def _build_query(self, video):
        query = video.title
        if video.video_type == VIDEO_TYPES.MOVIE:
            query += f' {video.year}'
        elif video.video_type == VIDEO_TYPES.EPISODE:
            query += f' S{int(video.season):02d}'
        return query.replace(' ', '+')

    def _http_get(self, url):
        try:
            headers = {'User-Agent': scraper_utils.get_ua()}
            response = requests.get(url, headers=headers, timeout=self.timeout)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            logger.error(f"HTTP request failed: {e}")
            return ''
        
    @classmethod
    def get_settings(cls):
        """
        Returns the settings for the scraper.

        :return: List of settings.
        """
        settings = super(cls, cls).get_settings()
        name = cls.get_name()
        settings.append(f'         <setting id="{name}-result_limit" label="     {i18n("result_limit")}" type="slider" default="10" range="10,100" option="int" visible="true"/>')
        return settings