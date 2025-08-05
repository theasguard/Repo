import logging
import ssl
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

BASE_URL = 'https://rmz.cr'
LOCAL_UA = 'Asguard_for_Kodi/%s' % (kodi.get_version())
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
        return 'RMZ'
    
    def get_sources(self, video):
        hosters = []
        source_url = self.get_url(video)
        if not source_url or source_url == FORCE_NO_MATCH:
            return hosters

        page_url = scraper_utils.urljoin(self.base_url, source_url)
        headers = {'User-Agent': LOCAL_UA}
        html = self._http_get(page_url, headers=headers, require_debrid=True, cache_limit=.5)
        logger.log(f'Fetched HTML for page URL: {page_url}', log_utils.LOGDEBUG)

        if video.video_type == VIDEO_TYPES.MOVIE:
            page_url = self.__get_release(html, video)
            if page_url is None:
                return hosters
            page_url = scraper_utils.urljoin(self.base_url, page_url)
            html = self._http_get(page_url, headers=headers, require_debrid=True, cache_limit=.5)
            logger.log(f'Fetched HTML for release page URL: {page_url}', log_utils.LOGDEBUG)

        soup = BeautifulSoup(html, 'html.parser')
        hevc = False
        for span in soup.find_all('span', class_='releaselabel'):
            content = span.get_text()
            logger.log(f'Found releaselabel content: {content}', log_utils.LOGDEBUG)
            if re.search('(hevc|x265)', content, re.I):
                hevc = 'x265'
            match = re.search(r'(\d+)x(\d+)', content)
            if match:
                quality = scraper_utils.height_get_quality(int(match.group(2)))
                hosters.append({
                    'quality': quality,
                    'url': page_url,
                    'host': 'direct',
                    'class': self,
                    'rating': None,
                    'views': None,
                    'direct': True,
                    'debridonly': True
                })
                logger.log(f'Added hoster: {hosters[-1]}', log_utils.LOGDEBUG)
        return hosters

    def __get_release(self, html, video):
        try:
            select = int(kodi.get_setting('%s-select' % (self.get_name())))
        except:
            select = 0
        soup = BeautifulSoup(html, 'html.parser')
        ul_id = 'releases' if video.video_type == VIDEO_TYPES.MOVIE else 'episodes'
        fragment = soup.find('ul', id=ul_id)
        if fragment:
            best_qorder = 0
            best_page = None
            for item in fragment.find_all('li'):
                link = item.find('a', href=True, title=True)
                if not link:
                    continue
                page_url, release = link['href'], link['title']
                time_span = item.find('span', class_='time')
                if time_span and self.__too_old(time_span.get_text()):
                    break
                release = re.sub('^\[[^\]]*\]\s*', '', release)
                if video.video_type == VIDEO_TYPES.MOVIE:
                    meta = scraper_utils.parse_movie_link(release)
                else:
                    if not scraper_utils.release_check(video, release, require_title=False):
                        continue
                    meta = scraper_utils.parse_episode_link(release)
                if select == 0:
                    best_page = page_url
                    break
                else:
                    quality = scraper_utils.height_get_quality(meta['height'])
                    logger.log('result: |%s|%s|%s|' % (page_url, quality, Q_ORDER[quality]), log_utils.LOGDEBUG)
                    if Q_ORDER[quality] > best_qorder:
                        logger.log('Setting best as: |%s|%s|%s|' % (page_url, quality, Q_ORDER[quality]), log_utils.LOGDEBUG)
                        best_page = page_url
                        best_qorder = Q_ORDER[quality]
            return best_page
        return None

    def __too_old(self, age):
        filter_days = int(kodi.get_setting('%s-filter' % (self.get_name())))
        return filter_days and scraper_utils.get_days(age) > filter_days

    @classmethod
    def get_settings(cls):
        settings = super(cls, cls).get_settings()
        settings = scraper_utils.disable_sub_check(settings)
        name = cls.get_name()
        settings.append('         <setting id="%s-filter" type="slider" range="0,180" option="int" label="     %s" default="60" visible="eq(-3,true)"/>' % (name, i18n('filter_results_days')))
        settings.append('         <setting id="%s-select" type="enum" label="     %s" lvalues="30636|30637" default="0" visible="eq(-4,true)"/>' % (name, i18n('auto_select')))
        return settings

    def _get_episode_url(self, show_url, video):
        show_url = scraper_utils.urljoin(self.base_url, show_url)
        html = self._http_get(show_url, require_debrid=True, cache_limit=.5)
        return self.__get_release(html, video)

    def search(self, video_type, title, year, season=''):
        results = []
        search_url = scraper_utils.urljoin(self.base_url, '/search/')
        search_url = scraper_utils.urljoin(search_url, urllib.parse.quote_plus(title))
        headers = {'User-Agent': LOCAL_UA}
        html = self._http_get(search_url, headers=headers, require_debrid=True, cache_limit=8)
        soup = BeautifulSoup(html, 'html.parser')
        for div in soup.find_all('div', class_='list'):
            if not div.find('div', class_='lists_titles'):
                continue
            for a in div.find_all('a', class_='title', href=True):
                match_url = a['href']
                match_title_year = re.sub('</?[^>]*>', '', a.get_text())
                is_show = re.search('\(\d{-\)', match_title_year)
                if (is_show and video_type == VIDEO_TYPES.MOVIE) or (not is_show and video_type == VIDEO_TYPES.TVSHOW):
                    continue
                match_title, match_year = scraper_utils.extra_year(match_title_year)
                if not year or not match_year or year == match_year:
                    result = {'url': scraper_utils.pathify_url(match_url), 'title': scraper_utils.cleanse_title(match_title), 'year': match_year}
                    results.append(result)
        return results

    def _http_get(self, url, headers=None, require_debrid=True, cache_limit=8):
        if require_debrid:
            if Scraper.debrid_resolvers is None:
                Scraper.debrid_resolvers = [resolver for resolver in resolveurl.relevant_resolvers() if resolver.isUniversal()]
            if not Scraper.debrid_resolvers:
                logger.log('%s requires debrid: %s' % (self.__module__, Scraper.debrid_resolvers), log_utils.LOGDEBUG)
                return ''
        try:
            headers = headers or {'User-Agent': scraper_utils.get_ua()}
            req = urllib.request.Request(url, headers=headers)
            context = ssl._create_unverified_context()  # Disable SSL verification
            with urllib.request.urlopen(req, context=context, timeout=self.timeout) as response:
                return response.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            logger.log(f'HTTP Error: {e.code} - {url}', log_utils.LOGWARNING)
        except urllib.error.URLError as e:
            logger.log(f'URL Error: {e.reason} - {url}', log_utils.LOGWARNING)
        return ''