import urllib.parse
import requests
from bs4 import BeautifulSoup
import re, kodi
from asguard_lib.cf_captcha import NoRedirection
import log_utils
import cfscrape
from asguard_lib import scraper_utils, control, cloudflare, cf_captcha
from asguard_lib.constants import FORCE_NO_MATCH, VIDEO_TYPES, QUALITIES, Q_ORDER
from asguard_lib.utils2 import i18n, ungz
import resolveurl
from . import scraper

logger = log_utils.Logger.get_logger()

BASE_URL = 'https://nunflix.com'
LOCAL_UA = 'Asguard for Kodi/%s' % (kodi.get_version())
FLARESOLVERR_URL = 'http://localhost:8191/v1'
MAX_RESPONSE = 1024 * 1024 * 5
CF_CAPCHA_ENABLED = kodi.get_setting('cf_captcha') == 'true'

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting('%s-base_url' % (self.get_name()))
        self.scraper = cfscrape.create_scraper()

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE, VIDEO_TYPES.MOVIE])

    @classmethod
    def get_name(cls):
        return 'NunFlix'

    @classmethod
    def get_settings(cls):
        settings = super(cls, cls).get_settings()
        settings = scraper_utils.disable_sub_check(settings)
        name = cls.get_name()
        settings.append('         <setting id="%s-filter" type="slider" range="0,180" option="int" label="     %s" default="60" visible="eq(-3,true)"/>' % (name, i18n('filter_results_days')))
        settings.append('         <setting id="%s-select" type="enum" label="     %s" lvalues="30636|30637" default="0" visible="eq(-4,true)"/>' % (name, i18n('auto_select')))
        return settings

    def get_sources(self, video):
        hosters = []
        source_url = self.get_url(video)
        if not source_url or source_url == FORCE_NO_MATCH:
            return hosters
        page_url = scraper_utils.urljoin(self.base_url, source_url)
        headers = {'User-Agent': LOCAL_UA}
        html = self._http_get(page_url, headers=headers, require_debrid=False, cache_limit=.5)
        
        # Log the HTML content to verify it is being fetched correctly
        logger.log(f'Fetched HTML content for URL: {page_url}', log_utils.LOGDEBUG)
        logger.log(html, log_utils.LOGDEBUG)
        
        soup = BeautifulSoup(html, 'html.parser')
        for iframe in soup.find_all('iframe', src=True):
            embed_url = iframe['src']
            quality = scraper_utils.height_get_quality(720)  # default quality
            hosters.append({
                'quality': quality,
                'url': embed_url,
                'host': 'direct',
                'class': self,
                'rating': None,
                'views': None,
                'multi-part': False,
                'direct': True,
                'debridonly': False
            })
        return hosters

    def search(self, video_type, title, year, season=''):
        results = []
        search_url = scraper_utils.urljoin(self.base_url, '/search/')
        search_url = scraper_utils.urljoin(search_url, urllib.parse.quote_plus(title))
        headers = {'User-Agent': LOCAL_UA}
        html = self._http_get(search_url, headers=headers, require_debrid=False, cache_limit=8)
        
        # Log the HTML content to verify it is being fetched correctly
        logger.log(f'Fetched HTML content for search URL: {search_url}', log_utils.LOGDEBUG)
        logger.log(html, log_utils.LOGDEBUG)
        
        soup = BeautifulSoup(html, 'html.parser')
        for div in soup.find_all('div', class_='search-result'):
            a = div.find('a', href=True)
            if a:
                match_url = a['href']
                match_title_year = a.get_text()
                match_title, match_year = scraper_utils.extra_year(match_title_year)
                if not year or not match_year or year == match_year:
                    result = {'url': scraper_utils.pathify_url(match_url), 'title': scraper_utils.cleanse_title(match_title), 'year': match_year}
                    results.append(result)
        return results

    def _http_get(self, url, params=None, data=None, multipart_data=None, headers=None, cookies=None, allow_redirect=True, method=None, require_debrid=True, read_error=False, cache_limit=8):
        if headers is None:
            headers = {}
        if cookies is None:
            cookies = {}

        if url.startswith('//'):
            url = 'http:' + url

        referer = headers.get('Referer', self.base_url)
        headers['User-Agent'] = scraper_utils.get_ua()
        headers['Accept'] = '*/*'
        headers['Host'] = urllib.parse.urlparse(url).hostname
        if referer:
            headers['Referer'] = referer

        logger.log(f'Getting Url: {url} cookie=|{cookies}| data=|{data}| extra headers=|{headers}|', log_utils.LOGDEBUG)

        try:
            response = requests.get(url, headers=headers, cookies=cookies, allow_redirects=allow_redirect)
            response.raise_for_status()
            if response.headers.get('Content-Encoding') == 'gzip':
                html = response.content.decode('utf-8')
            else:
                html = response.text
        except requests.exceptions.RequestException as e:
            logger.log(f'Error ({str(e)}) during scraper http get: {url}', log_utils.LOGWARNING)
            if not read_error:
                return ''
            html = ''

        self.db_connection().cache_url(url, html, data)
        return html