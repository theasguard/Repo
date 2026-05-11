
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

BASE_URL = 'https://cinepro-addon.onrender.com'

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url')
        self.movie_search_url = '/stream/movie/%s.json'
        self.tv_search_url = '/stream/series/%s:%s:%s.json'
        self.timeout = timeout

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'CinePro'

    def resolve_link(self, link):
        return link

    def get_sources(self, video):
        sources = []

        try:
            # Use centralized IMDB ID retrieval from base class
            imdb_id = self.get_imdb_id(video)
            if not imdb_id:
                logger.log('CinePro: No IMDB ID found for trakt_id: %s' % video.trakt_id, log_utils.LOGWARNING)
                return sources

            if video.video_type == VIDEO_TYPES.MOVIE:
                search_path = self.movie_search_url % imdb_id
                logger.log('CinePro: Searching for movie: %s' % imdb_id, log_utils.LOGDEBUG)
            elif video.video_type == VIDEO_TYPES.EPISODE:
                search_path = self.tv_search_url % (imdb_id, video.season, video.episode)
                logger.log('CinePro: Searching for episode: %s S%sE%s' % (imdb_id, video.season, video.episode), log_utils.LOGDEBUG)
            else:
                logger.log('CinePro: Unsupported video type: %s' % video.video_type, log_utils.LOGWARNING)
                return sources

            # Build full URL
            search_url = '%s%s' % (self.base_url, search_path)

            response = self._http_get(search_url)
            logger.log('CinePro: Response: %s' % response, log_utils.LOGDEBUG)
            if not response:
                logger.log('CinePro: No response from server', log_utils.LOGWARNING)
                return sources

            try:
                data = json.loads(response)
                streams = data.get('streams', [])
                logger.log('CinePro: Found %d streams' % len(streams), log_utils.LOGDEBUG)
            except json.JSONDecodeError as e:
                logger.log('CinePro: Failed to parse JSON response: %s' % str(e), log_utils.LOGERROR)
                return sources

            for stream in streams:
                try:
                    # Get the URL field from the stream
                    url = stream.get('url', '')
                    if not url:
                        continue

                    # Extract stream information
                    name = stream.get('name', 'Unknown')
                    title = stream.get('title', '')

                    # Extract provider from title
                    provider = ''
                    provider_match = re.search(r'📡\s*Provider:\s*([^\n]+)', title)
                    if provider_match:
                        provider = provider_match.group(1).strip()

                    # Extract type from title
                    stream_type = ''
                    type_match = re.search(r'⚡\s*Type:\s*([^\n]+)', title)
                    if type_match:
                        stream_type = type_match.group(1).strip()

                    # Use name as the primary display name
                    display_name = name
                    display_name = scraper_utils.cleanse_title(display_name)

                    if not display_name:
                        continue

                    logger.log('CinePro: Processing: %s' % display_name, log_utils.LOGDEBUG)

                    # Extract quality from name
                    quality = self._extract_quality(name)

                    # Extract size information (not available in this API structure)
                    size_gb = 0
                    size_label = ''

                    # Check if URL is a magnet link or needs to be converted
                    if url.startswith('magnet:'):
                        stream_url = url
                        host = 'magnet'
                    else:
                        stream_url = url
                        host = self._get_host(url)

                    # Build source info
                    info_parts = []
                    if provider:
                        info_parts.append(provider)
                    if stream_type:
                        info_parts.append(stream_type)

                    source_info = ' | '.join(info_parts) if info_parts else ''

                    source = {
                        'class': self,
                        'host': host,
                        'label': display_name,
                        'multi-part': False,
                        'quality': quality,
                        'url': stream_url,
                        'info': source_info,
                        'direct': False,
                        'debridonly': True
                    }

                    sources.append(source)
                    logger.log('CinePro: Found source: %s [%s]' % (display_name, source_info), log_utils.LOGDEBUG)

                except Exception as e:
                    logger.log('CinePro: Error processing stream: %s' % str(e), log_utils.LOGWARNING)
                    continue

        except Exception as e:
            logger.log('CinePro: Unexpected error in get_sources: %s' % str(e), log_utils.LOGERROR)

        logger.log('CinePro: Returning %d sources' % len(sources), log_utils.LOGDEBUG)
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

    def _get_host(self, url):
        """Extract the host from a URL"""
        try:
            parsed = urllib.parse.urlparse(url)
            host = parsed.netloc
            # Remove port if present
            if ':' in host:
                host = host.split(':')[0]
            return host
        except:
            return 'unknown' 


    def search(self, video_type, title, year, season=''):
        """
        Search method implementation for CinePro scraper.
        CinePro requires IMDB IDs, so search functionality is limited.
        """
        logger.log('CinePro: Search not implemented - requires IMDB ID', log_utils.LOGDEBUG)
