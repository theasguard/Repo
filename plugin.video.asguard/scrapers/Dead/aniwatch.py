import base64
import json
import logging
import re
import six
import urllib.parse
import requests
import kodi
import log_utils
import cfscrape
from bs4 import BeautifulSoup, SoupStrainer
from asguard_lib import scraper_utils, cloudflare, cf_captcha
from asguard_lib.utils2 import i18n
from asguard_lib.constants import FORCE_NO_MATCH, QUALITIES, VIDEO_TYPES
from .. import scraper

logger = log_utils.Logger.get_logger(__name__)

BASE_URL = 'https://aniwatchtv.to'
SEARCH_URL = BASE_URL + '/search'
DEFAULT_HEADERS = {'User-Agent': scraper_utils.get_ua()}
CATEGORIES = {VIDEO_TYPES.TVSHOW: '/tv/', VIDEO_TYPES.MOVIE: '/movie/'}
LOCAL_UA = 'Asguard for Kodi/%s' % (kodi.get_version())


class Scraper(scraper.Scraper):
    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting('%s-base_url' % (self.get_name())) or BASE_URL
        self.scraper = cfscrape.create_scraper()
        self.headers = {
            'User-Agent': scraper_utils.get_ua(),
            'Referer': self.base_url
        }

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Aniwave'

    def get_sources(self, video):
        source_url = self._get_episode_url(video)
        hosters = []
        if source_url and source_url != FORCE_NO_MATCH:
            try:
                url = urllib.parse.urljoin(self.base_url, source_url)
                html = self._http_get(url, headers={'User-Agent': LOCAL_UA}, cache_limit=.5)
                logger.log('Aniwatch HTML: %s' % html, log_utils.LOGDEBUG)
                
                # Parse embedded iframe sources
                iframe_match = re.search(r'<iframe id="main-iframe".*?src="(.*?)"', html)
                if iframe_match:
                    hosters.append({
                        'quality': 1080,
                        'host': 'Embed',
                        'class': self,
                        'url': iframe_match.group(1),
                        'direct': False,
                        'debridonly': False
                    })

                # Parse direct video sources
                for match in re.finditer(r'file:"(.*?)".*?label:"(.*?)"', html):
                    url, quality_label = match.groups()
                    quality = self.__parse_quality(quality_label)
                    hosters.append({
                        'quality': quality,
                        'host': 'Direct',
                        'class': self,
                        'url': url,
                        'direct': True,
                        'debridonly': False
                    })

            except Exception as e:
                logger.log(f"Error fetching sources: {str(e)}", log_utils.LOGERROR)
        
        return hosters

    def get_episodes(self, show_url):
        episode_links = []
        try:
            html = self._http_get(show_url, cache_limit=24)
            soup = BeautifulSoup(html, 'html.parser')
            
            # Improved container detection
            main_container = soup.select_one('div.container.m_t_5') or soup.select_one('div.anime-detail-body')
            
            if main_container:
                # Better season detection
                season_tabs = main_container.select('div.season-div, div.tab-pane')
                for tab in season_tabs:
                    season_number = self.__parse_season(tab)
                    episodes = tab.select('a.ssl-item, a.episode')
                    
                    for ep in episodes:
                        ep_number = self.__parse_episode_number(ep)
                        ep_url = urllib.parse.urljoin(self.base_url, ep['href'])
                        
                        episode_links.append({
                            'season': season_number,
                            'number': ep_number,
                            'url': ep_url,
                            'title': ep.select_one('span.episode-title').text.strip() if ep.select_one('span.episode-title') else ''
                        })

            # Fallback to alternative detection
            if not episode_links:
                episodes_grid = soup.select('div.episodes-grid a.episode, div.anime_list_body ul li a')
                for idx, ep in enumerate(episodes_grid, 1):
                    episode_links.append({
                        'season': self.__detect_season_from_fallback(ep, idx),
                        'number': idx,
                        'url': urllib.parse.urljoin(self.base_url, ep['href']),
                        'title': ep.text.strip()
                    })

        except Exception as e:
            logger.log(f"Episode parsing failed: {str(e)}", log_utils.LOGERROR)
            kodi.notify(msg=i18n('episode_parse_error'), duration=3000)
        
        return episode_links

    def _get_episode_url(self, video):
        try:
            episodes = self.get_episodes(video)
            for ep in episodes:
                # Fuzzy matching for different numbering formats
                season_match = ep['season'] == video.season
                number_match = (
                    ep['number'] == video.episode or
                    f"E{video.episode:02}" in ep['title'] or
                    f"EP{video.episode}" in ep['title'].upper()
                )
                
                if season_match and number_match:
                    logger.log(f"Matched S{video.season}E{video.episode} to {ep['url']}", log_utils.LOGDEBUG)
                    return ep['url']
            
            # Fallback to closest match
            closest = min(episodes, key=lambda x: abs(x['number'] - video.episode))
            return closest['url']

        except Exception as e:
            logger.log(f"Matching failed: {str(e)}", log_utils.LOGERROR)
            kodi.notify(msg=i18n('episode_match_error'), duration=3000)
            return None

    def search(self, video_type, title, year, season=''):
        results = []
        params = {'keyword': self.__to_slug(title)}
        try:
            html = self._http_get(SEARCH_URL, params=params, headers={'User-Agent': LOCAL_UA}, cache_limit=.4)
            results = self.__parse_search(html, video_type, year)
        except Exception as e:
            logger.log(f"Search failed: {str(e)}", log_utils.LOGERROR)
        return results

    def __parse_search(self, html, video_type, year):
        results = []
        soup = BeautifulSoup(html, 'html.parser')
        for item in soup.select('div.flw-item'):
            try:
                result = {
                    'title': item.select_one('h2.film-name a').text.strip(),
                    'url': urllib.parse.urljoin(self.base_url, item.a['href']),
                    'year': self.__parse_year(item.select_one('span.fdi-item').text)
                }
                if self.__valid_result(result, video_type, year):
                    results.append(result)
            except Exception as e:
                logger.log(f"Parse error: {str(e)}", log_utils.LOGERROR)
        return results

    def __valid_result(self, result, video_type, year):
        if CATEGORIES[video_type] not in result['url']:
            return False
        if year and result.get('year') and abs(int(year) - result['year']) > 2:
            return False
        return True

    def __parse_year(self, text):
        try:
            return int(re.search(r'\d{4}', text).group())
        except:
            return None

    def __parse_quality(self, label):
        return {
            '1080': QUALITIES.HD1080,
            '720': QUALITIES.HD720,
            '480': QUALITIES.HIGH
        }.get(label.strip(), QUALITIES.HIGH)

    def __to_slug(self, title):
        return re.sub('[^A-Za-z0-9]+', '-', title.lower()).strip('-')

    def __parse_season(self, element):
        try:
            # Get from data attributes
            if 'data-season' in element.attrs:
                return int(element['data-season'])
            # Extract from tab titles
            season_text = element.select_one('h3.season-title, a.nav-link.active').text
            return int(re.search(r'Season\s*(\d+)', season_text, re.I).group(1))
        except:
            return 1  # Default to season 1

    def __parse_episode_number(self, element):
        try:
            # Multiple number sources
            num_element = element.select_one('span.episode-number, span.ep-no')
            number_text = num_element.text.strip()
            return int(re.search(r'\d+', number_text).group())
        except:
            # Fallback to position in list
            return len(self.episode_links) + 1

    def __detect_season_from_fallback(self, element, index):
        try:
            # Extract from episode titles
            title = element.text.lower()
            if 'ova' in title: return 99
            if 'special' in title: return 0
            # Detect season patterns in URLs
            url = element['href'].lower()
            season_match = re.search(r'season-(\d+)', url)
            return int(season_match.group(1)) if season_match else 1
        except:
            return 1

    @classmethod
    def get_settings(cls):
        settings = super().get_settings()
        name = cls.get_name()
        settings.append(f'<setting id="{name}-quality" type="enum" label="Preferred Quality" values="1080p|720p|480p" default="0"/>')
        return settings