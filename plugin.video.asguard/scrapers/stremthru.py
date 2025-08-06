"""
    Asguard Addon
    Copyright (C) 2025 MrBlamo

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

BASE_URL = 'https://stremthru.elfhosted.com'

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    
    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url')
        # Base64 encoded config: {"stores":[{"c":"p2p","t":""}]}
        self.config_path = 'stremio/torz/eyJzdG9yZXMiOlt7ImMiOiJwMnAiLCJ0IjoiIn1dfQ=='
        self.movie_search_url = '/stream/movie/%s.json'
        self.tv_search_url = '/stream/series/%s:%s:%s.json'
        self.timeout = timeout

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'StreamThru'

    def resolve_link(self, link):
        return link

    def get_sources(self, video):
        sources = []

        try:
            # Use centralized IMDB ID retrieval from base class
            imdb_id = self.get_imdb_id(video)
            if not imdb_id:
                logger.log('StreamThru: No IMDB ID found for trakt_id: %s' % video.trakt_id, log_utils.LOGWARNING)
                return sources

            if video.video_type == VIDEO_TYPES.MOVIE:
                search_path = self.movie_search_url % imdb_id
                logger.log('StreamThru: Searching for movie: %s' % imdb_id, log_utils.LOGDEBUG)
            elif video.video_type == VIDEO_TYPES.EPISODE:
                search_path = self.tv_search_url % (imdb_id, video.season, video.episode)
                logger.log('StreamThru: Searching for episode: %s S%sE%s' % (imdb_id, video.season, video.episode), log_utils.LOGDEBUG)
            else:
                logger.log('StreamThru: Unsupported video type: %s' % video.video_type, log_utils.LOGWARNING)
                return sources

            # Build full URL with config
            search_url = '%s/%s%s' % (self.base_url, self.config_path, search_path)
            
            response = self._http_get(search_url)
            if not response:
                logger.log('StreamThru: No response from server', log_utils.LOGWARNING)
                return sources

            try:
                data = json.loads(response)
                streams = data.get('streams', [])
                logger.log('StreamThru: Found %d streams' % len(streams), log_utils.LOGDEBUG)
            except json.JSONDecodeError as e:
                logger.log('StreamThru: Failed to parse JSON response: %s' % str(e), log_utils.LOGERROR)
                return sources

            for stream in streams:
                try:
                    info_hash = stream.get('infoHash', '')
                    if not info_hash:
                        continue

                    # Extract stream information
                    name = stream.get('name', 'Unknown')
                    description = stream.get('description', '')
                    behavior_hints = stream.get('behaviorHints', {})
                    
                    # Get filename from behaviorHints or description
                    filename = behavior_hints.get('filename', '')
                    if not filename and description:
                        # Try to extract filename from description
                        filename_match = re.search(r'📄\s*(.+?)(?:\n|$)', description)
                        if filename_match:
                            filename = filename_match.group(1).strip()
                    
                    # Use filename as the primary name, fallback to stream name
                    display_name = filename if filename else name
                    display_name = scraper_utils.cleanse_title(display_name)
                    
                    if not display_name:
                        continue

                    logger.log('StreamThru: Processing: %s' % display_name, log_utils.LOGDEBUG)

                    # Extract quality from name, description, or filename
                    quality_source = filename or description or name
                    quality = self._extract_quality(quality_source)

                    # Extract size information
                    size_gb = 0
                    size_label = ''
                    video_size = behavior_hints.get('videoSize', 0)
                    
                    if video_size > 0:
                        # Convert bytes to GB
                        size_gb = video_size / (1024 * 1024 * 1024)
                        if size_gb >= 1:
                            size_label = '%.1f GB' % size_gb
                        else:
                            size_mb = video_size / (1024 * 1024)
                            size_label = '%.0f MB' % size_mb
                    else:
                        # Try to extract size from description
                        size_match = re.search(r'💾\s*([\d.]+)\s*(GB|MB)', description)
                        if size_match:
                            size_value = float(size_match.group(1))
                            size_unit = size_match.group(2)
                            size_label = '%s %s' % (size_value, size_unit)
                            if size_unit.upper() == 'GB':
                                size_gb = size_value
                            else:
                                size_gb = size_value / 1024

                    # Create magnet link
                    magnet_url = 'magnet:?xt=urn:btih:%s&dn=%s' % (info_hash, urllib.parse.quote(display_name))

                    # Build source info
                    info_parts = []
                    if size_label:
                        info_parts.append(size_label)
                    
                    # Extract additional info from description
                    codec_match = re.search(r'🎞️\s*([A-Z0-9]+)', description)
                    if codec_match:
                        info_parts.append(codec_match.group(1))
                        
                    audio_match = re.search(r'🎧\s*([^🎞️💾📦⚙️🌐🔤📄\n]+)', description)
                    if audio_match:
                        audio_info = audio_match.group(1).strip()
                        if audio_info:
                            info_parts.append(audio_info)
                    
                    source_info = ' | '.join(info_parts) if info_parts else ''

                    source = {
                        'class': self,
                        'host': 'magnet',
                        'label': display_name,
                        'multi-part': False,
                        'quality': quality,
                        'url': magnet_url,
                        'info': source_info,
                        'direct': False,
                        'debridonly': True,
                        'size': size_gb
                    }

                    sources.append(source)
                    logger.log('StreamThru: Found source: %s [%s]' % (display_name, source_info), log_utils.LOGDEBUG)

                except Exception as e:
                    logger.log('StreamThru: Error processing stream: %s' % str(e), log_utils.LOGWARNING)
                    continue

        except Exception as e:
            logger.log('StreamThru: Unexpected error in get_sources: %s' % str(e), log_utils.LOGERROR)

        logger.log('StreamThru: Returning %d sources' % len(sources), log_utils.LOGDEBUG)
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
        Search method implementation for StreamThru scraper.
        StreamThru requires IMDB IDs, so search functionality is limited.
        """
        logger.log('StreamThru: Search not implemented - requires IMDB ID', log_utils.LOGDEBUG)
        return [] 