import re
import logging
import urllib.request
import urllib.parse
from bs4 import BeautifulSoup, SoupStrainer
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
BASE_URL = 'https://anidex.info'
SEARCH_URL = '/?q=%s'
QUALITY_MAP = {'1080p': QUALITIES.HD1080, '720p': QUALITIES.HD720, '480p': QUALITIES.HIGH, '360p': QUALITIES.MEDIUM}

class Scraper(scraper.Scraper):
    base_url = BASE_URL
    debrid_resolvers = resolveurl

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url') or BASE_URL

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Anidex'

    def resolve_link(self, link):
        return link

    def get_sources(self, video):
        hosters = []
        query = self._build_query(video)
        logger.log(f'Anidex Scraper: Query: {query}', log_utils.LOGDEBUG)
        search_url = scraper_utils.urljoin(self.base_url, SEARCH_URL % urllib.parse.quote_plus(query))
        logger.log(f'Anidex Scraper: Search URL: {search_url}', log_utils.LOGDEBUG)
        html = self._http_get(search_url, require_debrid=True)
        logger.log(f'Anidex Scraper: HTML: {html}', log_utils.LOGDEBUG)
        soup = BeautifulSoup(html, "html.parser", parse_only=SoupStrainer('div', {'class': 'table-responsive'}))
        logger.log(f'Anidex Scraper: Soup: {soup}', log_utils.LOGDEBUG)
        
        for row in soup.select('table.table tbody tr'):
            try:
                # Align with Nyaa's element selection pattern
                name_link = row.select('td:nth-of-type(3) a.torrent')
                if not name_link: continue
                
                # Get all links in the row
                magnets = row.select('td:nth-of-type(6) a[href^="magnet:"]')
                downloads = row.select('td:nth-of-type(5) a[href*="/dl/"]')
                
                # Process first valid link pair like Nyaa does
                name = name_link[0].select_one('span').get('title', '').strip()
                magnet = magnets[0].get('href', '') if magnets else ''
                torrent_url = scraper_utils.urljoin(self.base_url, downloads[0].get('href', '')) if downloads else ''
                
                # Size and stats handling similar to Nyaa
                size_cell = row.select('td:nth-of-type(7)')
                seeders = row.select('td.text-success')
                leechers = row.select('td.text-danger')
                
                # Batch detection using Nyaa-style class checks
                is_batch = any('batch' in tag.text.lower() 
                             for tag in row.select('span.label.label-primary'))

                hosters.append({
                    'name': name,
                    'class': self,
                    'label': f"{name} | {scraper_utils.format_size(size_cell[0].text.strip())} | {int(seeders[0].text.strip())} | {int(leechers[0].text.strip())}",
                    'magnet': magnet,
                    'multi-part': False,
                    'url': torrent_url or magnet,
                    'quality': scraper_utils.get_tor_quality(name),
                    'size': scraper_utils.format_size(size_cell[0].text.strip()) if size_cell else '0',
                    'seeders': int(seeders[0].text.strip()) if seeders else 0,
                    'leechers': int(leechers[0].text.strip()) if leechers else 0,
                    'direct': False,
                    'debridonly': True
                })
                logging.debug("Added source: %s", hosters[-1])
                
            except (IndexError, AttributeError) as e:
                logger.log(f"Skipping row due to error: {str(e)}", log_utils.LOGDEBUG)
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
        filtered_sources = []
        episode_number = video.episode
        season_number = video.season
        # Anime-specific season number adjustments
        possible_season_numbers = [season_number]
        if season_number == 1:
            # If Trakt shows season 1, also check for season 2 in release names
            possible_season_numbers.append(2)
            logging.debug("Checking for both season 1 and 2 due to possible anime numbering")

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
                if matches_season or any(f"ep 0001-{episode_number:04d}" in name for episode_number in [999, 1001]):
                    is_season_pack = True
                    logging.debug("Valid season pack found: %s", name)
                else:
                    logging.debug("Batch/complete label found but wrong season: %s", name)

            # Allow season packs or exact season and episode matches
            if is_season_pack or (matches_season and matches_episode):
                filtered_sources.append(source)
                logging.debug("Filtered source: %s", source)

        return filtered_sources

    def _build_query(self, video):
        query = video.title
        if video.video_type == VIDEO_TYPES.EPISODE:
            query += f' S{int(video.season):02d}'
        elif video.video_type == VIDEO_TYPES.MOVIE:
            query += f' {video.year}'
        # Anidex requires these parameters for valid search
        return f"/?q={query}&s=seeders&o=desc"
