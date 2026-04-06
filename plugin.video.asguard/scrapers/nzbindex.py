
"""
    Asguard Addon
    Copyright (C) 2024 MrBlamo

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
import urllib.request
import urllib.error
import urllib.parse
import logging
import re
from urllib.parse import quote_plus, unquote_plus
import xbmcgui
import kodi
import log_utils, workers
from asguard_lib import scraper_utils, control, client
from asguard_lib.constants import FORCE_NO_MATCH, VIDEO_TYPES, QUALITIES, DELIM
from asguard_lib.utils2 import i18n
from . import scraper
from . import proxy

try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)

logger = log_utils.Logger.get_logger()

BASE_URL = 'https://www.nzbindex.com'
SEARCH_URL = '/api/search?q=%s&minage=&maxage=&minsize=&maxsize=&sort=agedesc&max=100&poster=&groups='
VIDEO_EXT = ['MKV', 'AVI', 'MP4']

class Scraper(scraper.Scraper):
    base_url = BASE_URL
    debrid_resolvers = resolveurl

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url')
        min_size_setting = kodi.get_setting(f'{self.get_name()}-min_size')
        try:
            self.min_size = int(min_size_setting) if min_size_setting else 0
        except (ValueError, TypeError):
            self.min_size = 0

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'NZBIndex'

    def get_sources(self, video):
        sources = []
        source_url = self.get_url(video)
        logger.log(f'NZBIndex: Source URL: {source_url}', log_utils.LOGDEBUG)
        if not source_url or source_url == FORCE_NO_MATCH:
            return sources

        json_data = self._http_get(source_url, require_debrid=True, cache_limit=1)
        logger.log(f'NZBIndex: JSON response: {json_data}', log_utils.LOGDEBUG)
        if not json_data:
            logger.log('NZBIndex: No data returned', log_utils.LOGWARNING)
            return sources

        try:
            # Parse the JSON response from NZBIndex API
            data = scraper_utils.parse_json(json_data, source_url)
            logger.log(f'NZBIndex: JSON response: {data}', log_utils.LOGDEBUG)
            if not data or 'data' not in data or 'content' not in data['data']:
                logger.log('NZBIndex: Invalid JSON response', log_utils.LOGWARNING)
                return sources

            # Process each NZB entry
            for item in data['data']['content']:
                try:
                    # Extract item details
                    nzb_id = item.get('id', '')
                    name = item.get('name', '')
                    size_bytes = item.get('size', 0)
                    file_count = item.get('fileCount', 0)
                    complete = item.get('complete', False)
                    logger.log(f'NZBIndex: Item: {nzb_id}, {name}, {size_bytes}, {file_count}, {complete}', log_utils.LOGDEBUG)

                    # Skip incomplete or empty results
                    if not complete or not name or not nzb_id:
                        continue

                    patterns = [
                        r'S(\d{1,2})E(\d{1,2})',
                        r'Season\s*(\d{1,2})\s*Episode\s*(\d{1,2})',
                        r'\b(\d{1,2})x(\d{1,2})\b',
                        r'S(\d{1,2})\s*(?!E\d)',
                        r'Season\s*(\d{1,2})\s*(?!Episode)'
                    ]

                    for i, pattern in enumerate(patterns):
                        match = re.search(pattern, name, re.IGNORECASE)
                        if match:
                            logger.log(f'NZBIndex: Pattern {i+1} matched: {pattern}', log_utils.LOGDEBUG)



                    # Clean up the title
                    name = scraper_utils.cleanTitle(name)


                    # Convert bytes to human-readable format
                    if size_bytes >= 1024**3:
                        size = f'{size_bytes / 1024**3:.2f} GB'
                    elif size_bytes >= 1024**2:
                        size = f'{size_bytes / 1024**2:.2f} MB'
                    else:
                        size = f'{size_bytes / 1024:.2f} KB'

                    # Check minimum size requirement
                    if self.min_size > 0 and size_bytes < (self.min_size * 1024 * 1024):
                        continue

                    # Get quality from filename
                    quality = scraper_utils.get_tor_quality(name)

                    # Create download URL
                    url = f'{self.base_url}/download/{nzb_id}.nzb'

                    host = scraper_utils.get_direct_hostname(self, url)

                    # Build info string
                    info = []
                    if file_count > 1:
                        info.append(f'{file_count} files')
                    info = ' | '.join(info)
                    label = f"{name} | {size}"

                    # Add source to list
                    hoster = {
                        'class': self,
                        'name': name,
                        'multi-part': False,
                        'label': label,
                        'url': url,
                        'info': info,
                        'host': 'magnet',
                        'quality': quality,
                        'direct': False,
                        'debridonly': True,
                        'size': size
                    }
                    sources.append(hoster)

                    logger.log(f'Found NZB: {name} - {size}', log_utils.LOGDEBUG)

                except Exception as e:
                    logger.log(f'Error parsing NZB item: {str(e)}', log_utils.LOGWARNING)
                    continue

            logger.log(f'NZBIndex found {len(sources)} sources', log_utils.LOGDEBUG)

        except Exception as e:
            logger.log(f'Error parsing NZBIndex response: {str(e)}', log_utils.LOGERROR)

        return self._filter_sources(sources, video)

    def _filter_sources(self, sources, video):
        """
        Filters torrent sources based on anime-specific naming patterns and season/episode matching.

        Args:
            sources (list): List of torrent sources containing 'name' and metadata
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
            3. Season-only matches (no episode specified)
        """
        # Return immediately for movies since they don't have season/episode data
        if video.video_type == VIDEO_TYPES.MOVIE:
            return sources

        filtered_sources = []
        episode_number = int(video.episode)
        season_number = int(video.season)
        
        # Anime-specific season number adjustments
        possible_season_numbers = [season_number]

        for source in sources:
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

            # Check if the source has explicit episode information
            has_episode_info = self._has_episode_info(name)
            
            # Check if the source matches the current episode (only if it has episode info)
            matches_episode = False
            if has_episode_info:
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

            # Allow season packs, exact season+episode matches, or season-only matches
            if is_season_pack or (matches_season and (not has_episode_info or matches_episode)):
                filtered_sources.append(source)
                logger.log(f'Filtered source: {source}', log_utils.LOGDEBUG)

        return filtered_sources

    def _has_episode_info(self, name):
        """Check if name contains explicit episode information"""
        # More specific patterns that are less likely to match non-episode numbers
        patterns = [
            r'\be\d{1,2}\b',              # e01, e1 (with word boundaries)
            r'\bepisode\s*\d{1,2}\b',     # episode 1, episode01 (with word boundaries)
            r'\b\d{1,2}x\d{1,2}\b',       # 1x01, 1x1 (season x episode format)
            r'\bs\d{1,2}e\d{1,2}\b',      # s01e01, s1e1 (season x episode format)
        ]
        
        return any(re.search(p, name, re.IGNORECASE) for p in patterns)



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

    def get_url(self, video):
        if video.video_type == VIDEO_TYPES.MOVIE:
            query = f'{video.title} {video.year}'
        else:
            # Try multiple formats for TV shows
            # Format 1: S02E03
            query = f'{video.title}'

        # Remove colons and other special characters that might cause URL encoding issues
        query = query.replace(':', '').replace(';', '')

        return f'{self.base_url}{SEARCH_URL % quote_plus(query)}'

    @classmethod
    def get_settings(cls):
        settings = super(cls, cls).get_settings()
        settings = scraper_utils.disable_sub_check(settings)
        name = cls.get_name()
        parent_id = f"{name}-enable"
        label_id = kodi.Translations.get_scraper_label_id(name)
        return [
            f'''\t\t<setting id="{parent_id}" type="boolean" label="{label_id}" help="">
\t\t\t<level>0</level>
\t\t\t<default>true</default>
\t\t\t<dependencies>
\t\t\t\t<dependency type="visible">
\t\t\t\t\t<condition on="property" name="InfoBool">true</condition>
\t\t\t\t</dependency>
\t\t\t</dependencies>
\t\t\t<control type="toggle"/>
\t\t</setting>''',
            f'''\t\t<setting id="{name}-base_url" type="string" label="30175" help="">
\t\t\t<level>0</level>
\t\t\t<default>{cls.base_url}</default>
\t\t\t<dependencies>
\t\t\t\t<dependency type="visible">
\t\t\t\t\t<condition operator="is" setting="{parent_id}">true</condition>
\t\t\t\t</dependency>
\t\t\t</dependencies>
\t\t\t<control type="edit" format="string">
\t\t\t\t<heading>{i18n('base_url')}</heading>
\t\t\t</control>
\t\t</setting>''',
            f'''\t\t<setting id="{name}-min_size" type="integer" label="Minimum Size (MB)" help="">
\t\t\t<level>0</level>
\t\t\t<default>0</default>
\t\t\t<constraints>
\t\t\t\t<minimum>0</minimum>
\t\t\t\t<maximum>10000</maximum>
\t\t\t</constraints>
\t\t\t<dependencies>
\t\t\t\t<dependency type="visible">
\t\t\t\t\t<condition operator="is" setting="{parent_id}">true</condition>
\t\t\t\t</dependency>
\t\t\t</dependencies>
\t\t\t<control type="slider" format="integer">
\t\t\t\t<popup>false</popup>
\t\t\t</control>
\t\t</setting>'''
        ]

    def _http_get(self, url, data=None, retry=True, allow_redirect=True, cache_limit=8, require_debrid=True):
        if require_debrid:
            if Scraper.debrid_resolvers is None:
                Scraper.debrid_resolvers = [resolver for resolver in resolveurl.choose_source(url) if resolver.isUniversal()]
            if not Scraper.debrid_resolvers:
                logger.log('%s requires debrid: %s' % (self.__module__, Scraper.debrid_resolvers), log_utils.LOGDEBUG)
                return ''
        try:
            headers = {'User-Agent': scraper_utils.get_ua()}
            req = urllib.request.Request(url, data=data, headers=headers)
            logging.debug("Retrieved req: %s", req)
            with urllib.request.urlopen(req, timeout=self.timeout) as response:
                return response.read().decode('utf-8')
        except urllib.error.HTTPError as e:
            logger.log(f'HTTP Error: {e.code} - {url}', log_utils.LOGWARNING)
        except urllib.error.URLError as e:
            logger.log(f'URL Error: {e.reason} - {url}', log_utils.LOGWARNING)
        return ''
