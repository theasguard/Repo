"""
    Asguard Addon
    Copyright (C) 2017 Thor

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import re
import urlparse
import urllib
import kodi
import log_utils
import dom_parser
from asguard_lib import scraper_utils
from asguard_lib.constants import FORCE_NO_MATCH
from asguard_lib.constants import QUALITIES
from asguard_lib.constants import VIDEO_TYPES
from asguard_lib.constants import XHR
import xml.etree.ElementTree as ET
import scraper

BASE_URL = 'https://5movies.cloud'
LINK_URL = '/player/'
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
        return 'Watch5s'

    def get_sources(self, video):
        source_url = self.get_url(video)
        hosters = []
        sources = {}
        if source_url and source_url != FORCE_NO_MATCH:
            page_url = urlparse.urljoin(self.base_url, source_url)
            sources.update(self.__scrape_sources(page_url))
            if video.video_type == VIDEO_TYPES.MOVIE:
                html = self._http_get(page_url, cache_limit=2)
                pages = set(dom_parser.parse_dom(html, 'a', {'class': '[^"]*btn-eps[^"]*'}, ret='href'))
                active = set(dom_parser.parse_dom(html, 'a', {'class': '[^"]*active[^"]*'}, ret='href'))
                for page_url in list(pages - active):
                    sources.update(self.__scrape_sources(page_url))
        
        for source in sources:
            if not source.lower().startswith('http'): continue
            if sources[source]['direct']:
                host = self._get_direct_hostname(source)
                if host != 'gvideo':
                    stream_url = source + '|User-Agent=%s&Referer=%s' % (scraper_utils.get_ua(), urllib.quote(page_url))
                else:
                    stream_url = source
            else:
                host = urlparse.urlparse(source).hostname
                stream_url = source
            hoster = {'multi-part': False, 'host': host, 'class': self, 'quality': sources[source]['quality'], 'views': None, 'rating': None, 'url': stream_url, 'direct': sources[source]['direct']}
            hosters.append(hoster)
        return hosters

    def __scrape_sources(self, page_url):
        html = self._http_get(page_url, cache_limit=2)
        match = re.search('url_playlist\s*=\s*"([^"]+)', html)
        if match:
            headers = {'Referer': page_url}
            label = dom_parser.parse_dom(html, 'a', {'class': '[^"]*active[^"]*'})
            label = label[0] if label else ''
            return self.__get_links_from_xml(match.group(1), headers, '')
        else:
            return {}
    
    def __get_links_from_xml(self, xml_url, headers, button_label):
        sources = {}
        try:
            xml = self._http_get(xml_url, headers=headers, cache_limit=.25)
            root = ET.fromstring(xml)
            for item in root.findall('.//item'):
                for source in item.findall('{http://rss.jwpcdn.com/}source'):
                    stream_url = source.get('file')
                    label = source.get('label')
                    if self._get_direct_hostname(stream_url) == 'gvideo':
                        quality = scraper_utils.gv_get_quality(stream_url)
                    elif label:
                        quality = scraper_utils.height_get_quality(label)
                    else:
                        quality = Q_MAP.get(button_label, QUALITIES.HIGH)
                    sources[stream_url] = {'quality': quality, 'direct': True}
                    log_utils.log('Adding stream: %s Quality: %s' % (stream_url, quality), log_utils.LOGDEBUG)
        except Exception as e:
            log_utils.log('Exception during Watch5s XML Parse: %s' % (e), log_utils.LOGWARNING)

        return sources
    
    def _get_episode_url(self, season_url, video):
        url = urlparse.urljoin(self.base_url, season_url)
        html = self._http_get(url, cache_limit=8)
        links = dom_parser.parse_dom(html, 'a', {'class': '[^"]*btn-eps[^"]*'}, ret="href")
        labels = dom_parser.parse_dom(html, 'a', {'class': '[^"]*btn-eps[^"]*'})
        for episode in zip(labels, links):
            match = re.search('Ep(?:isode)?\s+(\d+)', episode[0], re.I)
            if match:
                ep_num = match.group(1)
                try: ep_num = int(ep_num)
                except: ep_num = 0
                if int(video.episode) == ep_num:
                    return scraper_utils.pathify_url(episode[1])
        
    def search(self, video_type, title, year, season=''):
        search_url = urlparse.urljoin(self.base_url, '/search/?q=')
        search_url += urllib.quote_plus(title)
        html = self._http_get(search_url, cache_limit=8)
        results = []
        for item in dom_parser.parse_dom(html, 'div', {'class': 'ml-item'}):
            match_title = dom_parser.parse_dom(item, 'span', {'class': 'mli-info'})
            match_url = re.search('href="([^"]+)', item, re.DOTALL)
            year_frag = dom_parser.parse_dom(item, 'img', ret='alt')
            is_episodes = dom_parser.parse_dom(item, 'span', {'class': 'mli-eps'})
            
            if (video_type == VIDEO_TYPES.MOVIE and not is_episodes) or (video_type == VIDEO_TYPES.SEASON and is_episodes):
                if match_title and match_url:
                    match_url = match_url.group(1)
                    match_title = match_title[0]
                    match_title = re.sub('</?h2>', '', match_title)
                    match_title = re.sub('\s+\d{4}$', '', match_title)
                    if video_type == VIDEO_TYPES.SEASON:
                        if season and not re.search('Season\s+%s$' % (season), match_title): continue
                        
                    if not match_url.endswith('/'): match_url += '/'
                    match_url = urlparse.urljoin(match_url, 'watch/')
                    match_year = ''
                    if video_type == VIDEO_TYPES.MOVIE and year_frag:
                        match = re.search('\s*-\s*(\d{4})$', year_frag[0])
                        if match:
                            match_year = match.group(1)
    
                    if not year or not match_year or year == match_year:
                        result = {'title': scraper_utils.cleanse_title(match_title), 'year': match_year, 'url': scraper_utils.pathify_url(match_url)}
                        results.append(result)

        return results