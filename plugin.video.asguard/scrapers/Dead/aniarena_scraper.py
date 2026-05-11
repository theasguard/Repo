import re
import logging
import urllib.parse
from bs4 import BeautifulSoup
from asguard_lib import scraper_utils
from asguard_lib.constants import VIDEO_TYPES, QUALITIES
import kodi
import log_utils
import resolveurl
from . import scraper

logger = logging.getLogger(__name__)
BASE_URL = 'https://www.anirena.com'
SEARCH_URL = '/index.php?t=2&s=%s'

class Scraper(scraper.Scraper):
    base_url = BASE_URL
    debrid_resolvers = resolveurl

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url')

    @classmethod
    def provides(cls):
        """
        Specifies the types of videos this scraper can provide.

        :return: A set of video types.
        """
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'AniRena'

    def resolve_link(self, link):
        return link

    def _build_query(self, video):
        if video.video_type == VIDEO_TYPES.EPISODE:
            query = f'{video.title}'
            # logging.debug("Episode query: %s", query)
        elif video.video_type == VIDEO_TYPES.SEASON:
            # Use quotes to search for the entire season and include common batch terms
            query = f'"{video.title} Season {int(video.season):02d}"|"Complete"|"Batch"|"S{int(video.season):02d}"'
        elif video.video_type == VIDEO_TYPES.MOVIE:
            query += f' {video.year}'
            # logging.debug("Movie query: %s", query)

        query = query.replace(' ', '+').replace('+-', '-')
        # logging.debug("Final query: %s", query)
        return query

    def get_sources(self, video):
        hosters = []
        search_url = scraper_utils.urljoin(self.base_url, SEARCH_URL % urllib.parse.quote_plus(video.title))
        html = self._http_get(search_url, require_debrid=True, allow_redirect=True)
        
        soup = BeautifulSoup(html, 'html.parser')
        # logging.debug("AniRena soup: %s", soup)
        for torrent in soup.find_all('div', class_='full2'):
            # Look for the torrent table within each full2 div
            table = torrent.find('table')
            if not table: continue

            info = table.find('td', class_='torrents_small_info_data1')
            # logging.debug("AniRena info: %s", info)
            if not info:
                continue

            # Extract title
            title_link = info.find_all('a')
            if len(title_link) < 2: continue
            full_title = title_link[1].get_text(strip=True)

            # Extract magnet link
            magnet = table.find('a', title='Magnet Link')
            # logging.debug("AniRena magnet: %s", magnet)
            if not magnet or not magnet.get('href'): continue

            # Extract size, seeders, leechers
            size_td = table.find('td', class_='torrents_small_size_data1')
            seeders_td = table.find('td', class_='torrents_small_seeders_data1')
            leechers_td = table.find('td', class_='torrents_small_leechers_data1')

            # Extract size, seeders, leechers
            size = scraper_utils.parse_size(size_td.get_text(strip=True)) if size_td else 0
            seeders = int(seeders_td.get_text(strip=True)) if seeders_td else 0
            leechers = int(leechers_td.get_text(strip=True)) if leechers_td else 0

            # Quality detection
            quality = scraper_utils.get_tor_quality(full_title)
            
            # Episode detection
            label = f"{full_title} | {size} | {seeders} | {leechers}"

            result = {
                'title': full_title,
                'class': self,
                'label': label,
                'multi-part': False,
                'debridonly': True,
                'url': magnet['href'],
                'host': 'magnet',
                'seeders': seeders,
                'size': size,
                'quality': quality,
                'direct': False
            }

            hosters.append(result)

        return self._filter_sources(hosters, video)

    def _filter_sources(self, hosters, video):
        # Return immediately for movies since they don't have season/episode data
        if video.video_type == VIDEO_TYPES.MOVIE:
            return hosters
        
        filtered_sources = []
        episode_number = int(video.episode)
        season_number = int(video.season)
        
        # Anime-specific season number adjustments
        possible_season_numbers = [season_number]
        if season_number == 1:
            possible_season_numbers.append(2)  # Check for split-cour shows

        for source in hosters:
            name = source['title'].lower()

            # Check season patterns
            matches_season = False
            for season_num in possible_season_numbers:
                if any([
                    f"s{season_num:02d}" in name,      # s01
                    f"s{season_num}" in name,          # s1
                    f"season {season_num:02d}" in name, # season 01
                    f"season {season_num}" in name,     # season 1
                    f"seasons {season_num}" in name,    # seasons 1
                    f"seasons {season_num:02d}" in name, # seasons 01
                    f"seasons {season_num}-" in name, # seasons 1-5
                    f"seasons {season_num:02d}-" in name, # seasons 01-05
                    f"season{season_num:02d}" in name,  # season01
                    f"season{season_num}" in name       # season1
                ]):
                    matches_season = True
                    break

            # Check episode patterns
            matches_episode = any([
                f"e{episode_number:02d}" in name,         # e01
                f"episode {episode_number}" in name,      # episode 1
                f"episode{episode_number:02d}" in name,   # episode01
                f" {episode_number:03d} " in name,        # 001
                f" {episode_number:04d} " in name,        # 0001
                f" {episode_number:02d} " in name,        # " 01 "
                f"_{episode_number:02d}" in name,         # _01
                f"_{episode_number:02d}_" in name,        # _01_
                f" - {episode_number:02d}" in name,       # - 01
                f" - {episode_number}" in name,           # - 1
                f"-{episode_number:02d}" in name,         # -01
                f" - {episode_number:03d}" in name,       # - 001
                f" - {episode_number:04d}" in name,        # - 0001
                f"-{episode_number}" in name,             # -1
                f" {episode_number} " in name,            # " 1 "
                f".{episode_number:02d}." in name,        # .01.
                f".{episode_number}." in name             # .1.
            ])

            # Check if it's a valid season pack
            is_season_pack = False
            season_pack_keywords = ['complete', 'batch', 'seasons', 'collection']
            if any(keyword in name for keyword in season_pack_keywords):
                if matches_season or any(f"ep 0001-{episode_number:04d}" in name for episode_number in [999, 1001]):
                    is_season_pack = True
                    logging.debug("Valid season pack found: %s", name)
                else:
                    logging.debug("Batch/complete label found but wrong season: %s", name)

            # Allow season packs or exact season and episode matches
            if is_season_pack or (matches_season and matches_episode):
                filtered_sources.append(source)
                # logging.debug("Filtered source: %s", source)

        return filtered_sources

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

    def _get_episode_url(self, show_url, video):
        return show_url  # Direct magnet links in search results

    def get_resolved_url(self, url):
        return url  # Return magnet links directly for debrid handling