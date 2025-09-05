import itertools
import re
import logging
import urllib.parse
from bs4 import BeautifulSoup, SoupStrainer
from functools import partial
import resolveurl
import log_utils
from asguard_lib import scraper_utils, db_utils
from asguard_lib.utils2 import i18n
from asguard_lib.tvdb_api.tvdbdata import TVDBAPI
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

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Nyaa'

    def resolve_link(self, link):
        return link

    def get_sources(self, video):
        hosters = []
        listnames = []  # List to store names
        query = self._build_query(video)
        search_url = scraper_utils.urljoin(self.base_url, SEARCH_URL % urllib.parse.quote_plus(query))
        logger.log(f'Search URL: {search_url}', log_utils.LOGDEBUG)
        html = self._http_get(search_url, require_debrid=True)
        soup = BeautifulSoup(html, "html.parser", parse_only=SoupStrainer('div', {'class': 'table-responsive'}))

        for entry in soup.select("tr.danger,tr.default,tr.success"):
            try:
                name = entry.find_all('a', {'class': None})[1].get('title')
                listnames.append(name)
                logger.log(f'Retrieved listnames: {listnames}', log_utils.LOGDEBUG)
                magnet = entry.find('a', {'href': re.compile(r'(magnet:)+[^"]*')}).get('href')
                size = entry.find_all('td', {'class': 'text-center'})[1].text.replace('i', '')
                downloads = int(entry.find_all('td', {'class': 'text-center'})[-1].text)

                quality = scraper_utils.get_tor_quality(name)

                host = scraper_utils.get_direct_hostname(self, magnet)
                label = f"{name} | {size} | {downloads}"
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
                logger.log(f'Retrieved sources: {hosters[-1]}', log_utils.LOGDEBUG)
            except AttributeError as e:
                logger.log(f'Failed to append source: {str(e)}', log_utils.LOGERROR)
                continue

        return self._filter_sources(hosters, video)
    
    def _filter_sources(self, hosters, video):
        """
        Filters torrent sources based on anime-specific naming patterns and season/episode matching.

        Args:
            hosters (list): List of torrent sources containing 'name' and metadata
            video (Video): Video object containing trakt_id, season, and episode information

        Returns:
            list: Filtered list of sources that match either:
                - Exact season+episode patterns
                - Valid season packs containing the episode
                - Anime-specific numbering variations

        Notes:
            Handles special anime cases:
            - Automatically checks season 2 when Trakt shows season 1
            - Accepts multiple season patterns (s01, season1, season01)
            - Matches episode formats (e01, episode1, 001, .01., -01)
            - Allows batch/complete collections with valid season markers
            - Uses flexible numbering to account for TVDB vs production numbering differences

            Matching priorities:
            1. Season packs with complete/batch keywords
            2. Exact season+episode matches
            3. Episode ranges within valid season contexts
        """
        # Return immediately for movies since they don't have season/episode data
        if video.video_type == VIDEO_TYPES.MOVIE:
            return hosters
        
        filtered_sources = []
        episode_number = int(video.episode)
        season_number = int(video.season)
        # Anime-specific season number adjustments
        possible_season_numbers = [season_number]
        if season_number == 1:
            # If Trakt shows season 1, also check for season 2 in release names
            possible_season_numbers.append(2)
            logger.log('Checking for both season 1 and 2 due to possible anime numbering', log_utils.LOGDEBUG)

        for source in hosters:
            name = source['name'].lower()

            # Check if the source matches any of the possible seasons
            matches_season = False
            for season_num in possible_season_numbers:
                if any([
                    f"s{season_num:02d}" in name,      # s01
                    f"s{season_num}" in name,          # s1
                    f"season {season_num:02d}" in name, # season 01
                    f"season {season_num}" in name,     # season 1
                    f"seasons {season_num}" in name,    # seasons 1
                    f"seasons {season_num:02d}" in name,# seasons 01
                    f"season{season_num:02d}" in name,  # season01
                    f"season{season_num}" in name       # season1
                ]):
                    matches_season = True
                    break

            # Check if the source matches the current episode
            matches_episode = False
            if any([
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
                f"~{episode_number:02d}" in name,         # ~01
                f"~{episode_number:03d}" in name,        # ~001
                f"~ {episode_number}" in name,           # ~ 1
                f"~{episode_number:02d}" in name,        # ~ 01
                f".{episode_number}." in name             # .1.
            ]):
                matches_episode = True
            
            # Check if it's a valid season pack
            is_season_pack = False
            season_pack_keywords = ['complete', 'batch', 'all.seasons', 'collection']
            if any(keyword in name for keyword in season_pack_keywords):
                # Accept if: matches season, has full series range, or has no season indicator
                if (matches_season or 
                    self.episode_in_range(name, episode_number) or 
                    not self.has_any_season_indicator(name)):
                    is_season_pack = True
                    logger.log(f'Valid season pack found: {name}', log_utils.LOGDEBUG)
                else:
                    logger.log(f'Batch/complete label found but wrong season: {name}', log_utils.LOGDEBUG)

            # Allow season packs or exact season and episode matches
            if is_season_pack or (matches_season and matches_episode):
                filtered_sources.append(source)
                logger.log(f'Filtered source: {source}', log_utils.LOGDEBUG)

        return filtered_sources

    def has_any_season_indicator(self, name):
        """Check if name contains any season pattern (s01, season 1, etc.)"""
        patterns = [
            r's\d{1,2}',          # s1, s01
            r'season\s*\d{1,2}',  # season 1, season01
            r'seasons\s*\d{1,2}'  # seasons 1
        ]
        return any(re.search(p, name) for p in patterns)

    def episode_in_range(self, name, target_ep):
        """Check for episode ranges like 01-24, 001~112, or 01 to 24"""
        # More flexible range detection
        match = re.search(r'(\d{2,4})[-~](\d{2,4})', name) or \
                re.search(r'(\d{2,4})\s*to\s*(\d{2,4})', name)
        if match:
            start, end = int(match.group(1)), int(match.group(2))
            return start <= target_ep <= end
        return False
    
    def _build_query(self, video):
        query = video.title
        if video.video_type == VIDEO_TYPES.EPISODE:
            query += f'|"Complete"|"Batch"|"E{int(video.episode):02d}"'
            logger.log(f'Episode query: {query}', log_utils.LOGDEBUG)
        elif video.video_type == VIDEO_TYPES.SEASON:
            query = f'"{video.title} Season {int(video.season):02d}"|"Complete"|"Batch"|"S{int(video.season):02d}"'
        elif video.video_type == VIDEO_TYPES.MOVIE:
            query += f' {video.year}'
        query = query.replace(' ', '+').replace('+-', '-')
        logger.log(f'Final query: {query}', log_utils.LOGDEBUG)
        return query

    