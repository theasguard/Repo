
"""
    Asguard Addon
    Copyright (C) 2026 MrBlamo

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
import json
import urllib.parse
from asguard_lib import scraper_utils
from asguard_lib.constants import VIDEO_TYPES, QUALITIES
import kodi
from . import scraper
import log_utils

logger = log_utils.Logger.get_logger()

BASE_URL = 'https://flixnest.app'

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url')
        # Config path for Flix-Finder: eyJtYXhSZXN1bHRzIjoxMDB9 (maxResults: 100)
        self.config_path = 'flix-finder/eyJtYXhSZXN1bHRzIjoxMDB9'
        self.movie_search_url = '/stream/movie/%s.json'
        self.tv_search_url = '/stream/series/%s:%s:%s.json'
        self.timeout = timeout

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'FlixFinder'

    def resolve_link(self, link):
        return link

    def get_sources(self, video):
        sources = []

        try:
            # Use centralized IMDB ID retrieval from base class
            imdb_id = self.get_imdb_id(video)
            if not imdb_id:
                logger.log('FlixFinder: No IMDB ID found for trakt_id: %s' % video.trakt_id, log_utils.LOGWARNING)
                return sources

            if video.video_type == VIDEO_TYPES.MOVIE:
                search_path = self.movie_search_url % imdb_id
                logger.log('FlixFinder: Searching for movie: %s' % imdb_id, log_utils.LOGDEBUG)
            elif video.video_type == VIDEO_TYPES.EPISODE:
                search_path = self.tv_search_url % (imdb_id, video.season, video.episode)
                logger.log('FlixFinder: Searching for episode: %s S%sE%s' % (imdb_id, video.season, video.episode), log_utils.LOGDEBUG)
            else:
                logger.log('FlixFinder: Unsupported video type: %s' % video.video_type, log_utils.LOGWARNING)
                return sources

            # Build full URL with config
            search_url = '%s/%s%s' % (self.base_url, self.config_path, search_path)

            response = self._http_get(search_url)
            if not response:
                logger.log('FlixFinder: No response from server', log_utils.LOGWARNING)
                return sources

            try:
                data = json.loads(response)
                streams = data.get('streams', [])
                logger.log('FlixFinder: Found %d streams' % len(streams), log_utils.LOGDEBUG)
            except json.JSONDecodeError as e:
                logger.log('FlixFinder: Failed to parse JSON response: %s' % str(e), log_utils.LOGERROR)
                return sources

            for stream in streams:
                try:
                    # Get the infoHash field from the stream
                    info_hash = stream.get('infoHash', '')
                    if not info_hash:
                        continue

                    # Extract stream information
                    name = stream.get('name', 'Unknown')
                    title = stream.get('title', '')
                    behavior_hints = stream.get('behaviorHints', {})

                    # Skip support messages
                    if 'Support' in title or 'Ko-fi' in title:
                        continue

                    # Extract seeders from title
                    seeders = 0
                    seeders_match = re.search(r'👥\s*S:(\d+)', title)
                    if seeders_match:
                        seeders = int(seeders_match.group(1))

                    # Extract size from title
                    size_gb = 0
                    size_label = ''
                    size_match = re.search(r'💾\s*([\d.]+)\s*(GB|MB|MiB)', title)
                    if size_match:
                        size_value = float(size_match.group(1))
                        size_unit = size_match.group(2)
                        size_label = '%s %s' % (size_value, size_unit)
                        if size_unit.upper() == 'GB':
                            size_gb = size_value
                        elif size_unit.upper() == 'MB' or size_unit.upper() == 'MIB':
                            size_gb = size_value / 1024

                    # Extract source from title
                    source = ''
                    source_match = re.search(r'🌐\s*([^\n👤💾🎞]+)', title)
                    if source_match:
                        source = source_match.group(1).strip()

                    # Extract codec from title
                    codec = ''
                    codec_match = re.search(r'🎞\s*([^\n👤💾🌐]+)', title)
                    if codec_match:
                        codec = codec_match.group(1).strip()

                    # Use title as the primary display name
                    display_name = title.split('\n')[0].strip()
                    display_name = scraper_utils.cleanse_title(display_name)

                    if not display_name:
                        continue

                    # Build label with size information
                    label_parts = [display_name]
                    if size_label:
                        label_parts.append(size_label)
                    display_label = ' | '.join(label_parts)

                    logger.log('FlixFinder: Processing: %s' % display_label, log_utils.LOGDEBUG)

                    # Extract quality from title
                    quality = self._extract_quality(title)

                    # Create magnet link
                    magnet_url = 'magnet:?xt=urn:btih:%s&dn=%s' % (info_hash, urllib.parse.quote(display_name))

                    # Build source info
                    info_parts = []
                    if source:
                        info_parts.append(source)
                    if codec:
                        info_parts.append(codec)
                    if seeders > 0:
                        info_parts.append('%d seeders' % seeders)

                    source_info = ' | '.join(info_parts) if info_parts else ''

                    source = {
                        'class': self,
                        'host': 'magnet',
                        'label': display_label,
                        'multi-part': False,
                        'quality': quality,
                        'url': magnet_url,
                        'info': source_info,
                        'direct': False,
                        'debridonly': True,
                        'size': size_gb
                    }

                    sources.append(source)
                    logger.log('FlixFinder: Found source: %s [%s]' % (display_label, source_info), log_utils.LOGDEBUG)

                except Exception as e:
                    logger.log('FlixFinder: Error processing stream: %s' % str(e), log_utils.LOGWARNING)
                    continue

        except Exception as e:
            logger.log('FlixFinder: Unexpected error in get_sources: %s' % str(e), log_utils.LOGERROR)

        logger.log('FlixFinder: Returning %d sources' % len(sources), log_utils.LOGDEBUG)
        return sources

    def _extract_quality(self, text):
        """Extract quality from stream information"""
        if not text:
            return QUALITIES.HIGH

        text_lower = text.lower()

        if any(q in text_lower for q in ['2160p', '4k', 'uhd']):
            return QUALITIES.HD4K
        elif any(q in text_lower for q in ['1080p', 'fhd']):
            return QUALITIES.HD1080
        elif any(q in text_lower for q in ['720p', 'hd']):
            return QUALITIES.HD720
        elif any(q in text_lower for q in ['480p']):
            return QUALITIES.HIGH
        elif any(q in text_lower for q in ['360p']):
            return QUALITIES.MEDIUM
        else:
            return QUALITIES.HIGH


    def search(self, video_type, title, year, season=''):
        """
        Search method implementation for FlixFinder scraper.
        FlixFinder requires IMDB IDs, so search functionality is limited.
        """
        logger.log('FlixFinder: Search not implemented - requires IMDB ID', log_utils.LOGDEBUG)
