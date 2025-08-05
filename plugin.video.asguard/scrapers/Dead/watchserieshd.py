# -*- coding: utf-8 -*-

import re
import urllib.parse
import requests
import kodi
import log_utils
import logging
import dom_parser2
from asguard_lib import scraper_utils
from asguard_lib.constants import FORCE_NO_MATCH, VIDEO_TYPES, QUALITIES, XHR
from asguard_lib.ui import cleantitle
from .. import scraper

logger = log_utils.Logger.get_logger()

BASE_URL = 'https://watchserieshd.stream'
SEARCH_URL = '/?s='
LOCAL_UA = 'Asguard for Kodi/%s' % (kodi.get_version())

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting('%s-base_url' % (self.get_name()))

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'WatchSeriesHD'

    def resolve_link(self, link):
        if not link.startswith('http'):
            url = scraper_utils.urljoin(self.base_url, link)
            html = self._http_get(url, cache_limit=0)
            for attrs, content in dom_parser2.parse_dom(html, 'a', req='href'):
                if re.search('Click Here To Play', content, re.I):
                    return attrs['href']
        else:
            return link

    def get_sources(self, video):
        source_url = self.get_url(video)
        hosters = []
        data = urllib.parse.parse_qs(source_url)
        logger.log('Data: %s' % data, log_utils.LOGDEBUG)
        data = dict([(i, data[i][0]) if data[i] else (i, '') for i in data])
        logger.log('Data: %s' % data, log_utils.LOGDEBUG)
        title = data['tvshowtitle'] if 'tvshowtitle' in data else None
        logger.log('Title: %s' % title, log_utils.LOGDEBUG)
        season, episode = (data['season'], data['episode']) if 'tvshowtitle' in data else ('0', '0')
        year = data['premiered'].split('-')[0] if 'tvshowtitle' in data else None
        search_url = scraper_utils.urljoin(self.base_url, SEARCH_URL % urllib.parse.quote_plus(title))
        search_request = self._http_get(search_url)
        html = search_request[0]
        logger.log('HTML WatchSeriesHD: %s' % html, log_utils.LOGDEBUG)
        headers = search_request[1]
        r = dom_parser2.parse_dom(html, 'div', {'class': 'item'})
        r = [(dom_parser2.parse_dom(i, 'a', ret='href'), dom_parser2.parse_dom(i, 'a', ret='title')) for i in r]
        r = [(i[0][0], i[1][0]) for i in r if len(i[0]) > 0 and len(i[1]) > 0]
        r = [(i[0], re.findall('(.+?)(?:\((\d{4}))', i[1])) for i in r]
        r = [(i[0], i[1][0]) for i in r if len(i[1]) > 0]
        logger.log('R WatchSeriesHD: %s' % r, log_utils.LOGDEBUG)
        result_url = [i[0] for i in r if cleantitle.match_alias(i[1][0]) and cleantitle.match_year(i[1][1], year, data['year'])][0]
        if 'tvshowtitle' in data:
            check_url = '-season-%s-episode-%s/' % (season, episode)
            show_html = self._http_get(result_url, headers=headers)
            results = dom_parser2.parse_dom(show_html, 'a', ret='href')
            result_url = [i for i in results if check_url in i][0]
        result_html = self._http_get(result_url, headers=headers)
        try:
            qual = dom_parser2.parse_dom(result_html, 'span', {'class': 'quality'})[0]
        except:
            qual = ''
        if 'tvshowtitle' in data:
            links = dom_parser2.parse_dom(result_html, 'li', ret='data-vs')
        else:
            links = dom_parser2.parse_dom(result_html, 'div', ret='data-vs')
        for link in links:
            try:
                link = self._http_get(link, headers=headers, output='geturl')
                host = urllib.parse.urlparse(link).hostname
                quality = scraper_utils.get_quality(video, host, QUALITIES.HIGH)
                hoster = {'multi-part': False, 'host': host, 'class': self, 'quality': qual, 'views': None, 'rating': None, 'url': link, 'direct': False}
                hosters.append(hoster)
            except:
                pass
        return hosters

    def __episode_match(self, video, label):
        return re.search('(episode)?\s*0*%s' (video.episode), label, re.I) is not None

    def _get_episode_url(self, season_url, video):
        season_url = scraper_utils.urljoin(self.base_url, season_url)
        headers = {'User-Agent': LOCAL_UA}
        html = self._http_get(season_url, cache_limit=.5)
        for match in re.finditer('episode-data="([^"]+)', html):
            if self.__episode_match(video, match.group(1)):
                return season_url

    def search(self, video_type, title, year, season=''):  # @UnusedVariable
        results = []
        search_url = scraper_utils.urljoin(self.base_url, SEARCH_URL % urllib.parse.quote_plus(title))
        headers = {'User-Agent': LOCAL_UA}
        headers.update(XHR)
        html = self._http_get(search_url, headers=headers, cache_limit=1)
        for attrs, match_title in dom_parser2.parse_dom(html, 'a', req='href'):
            match_url = attrs['href']
            match_title = re.sub('</?[^>]*>', '', match_title)
            match = re.search('\((\d{4})\)$', match_url)
            match_year = match.group(1) if match else ''
            if not year or not match_year or year == match_year:
                result = {'url': scraper_utils.pathify_url(match_url), 'title': scraper_utils.cleanse_title(match_title), 'year': match_year}
                results.append(result)
        return results
