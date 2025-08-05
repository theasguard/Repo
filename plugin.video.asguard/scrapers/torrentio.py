"""
    Asguard Addon
    Copyright (C) 2024
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
import logging
import re
import json
import urllib.parse
import requests
from asguard_lib.utils2 import i18n
import xbmcgui
import kodi
import log_utils
from asguard_lib import scraper_utils
from asguard_lib.constants import FORCE_NO_MATCH, VIDEO_TYPES, QUALITIES
from . import scraper


try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)
    
logger = log_utils.Logger.get_logger()

BASE_URL = 'https://torrentio.strem.fun'

class Scraper(scraper.Scraper):
    base_url = BASE_URL
    movie_search_url = '/stream/movie/%s.json'
    tv_search_url = '/stream/series/%s:%s:%s.json'
    debrid_resolvers = resolveurl

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url')
        self.movie_search_url = '/stream/movie/%s.json'
        self.timeout = timeout
        self.min_seeders = 0
        self._set_apikeys()

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Torrentio'
    
    def resolve_link(self, link):
        return link

    def _set_apikeys(self):
        self.pm_apikey = kodi.get_setting('premiumize.apikey')
        self.rd_apikey = kodi.get_setting('realdebrid.apikey')
        self.ad_apikey = kodi.get_setting('alldebrid_api_key')

    def get_intelligent_name(self, file_data, video_type):
        """
        Intelligently choose the best name based on content type and context
        """
        title = file_data.get('title', '')
        behavior_hints = file_data.get('behaviorHints', {})
        filename = behavior_hints.get('filename', '')
        
        # Parse title lines
        title_lines = title.split('\n')
        first_line = title_lines[0] if title_lines else ''
        second_line = title_lines[1] if len(title_lines) > 1 else ''
        
        # Detect if this is a season pack or individual episode
        is_season_pack = self._is_season_pack(first_line, second_line)
        logger.log('Torrentio: Season pack detection - is_season_pack: %s, first_line: %s' % (is_season_pack, first_line), log_utils.LOGDEBUG)
        
        if video_type == VIDEO_TYPES.EPISODE:
            if is_season_pack:
                # For season packs, show both pack info and specific episode
                pack_name = self._clean_pack_name(first_line)
                logger.log('Torrentio: Cleaned pack_name: %s (from: %s)' % (pack_name, first_line), log_utils.LOGDEBUG)
                episode_name = self._clean_episode_name(filename, second_line)
                return f"{pack_name}"
            else:
                # For individual episodes, prioritize the most descriptive name
                logger.log('Torrentio: Not a season pack, processing as individual episode', log_utils.LOGDEBUG)
                if filename and self._is_descriptive_episode_name(filename):
                    result = self._clean_episode_name(filename)
                    logger.log('Torrentio: Using descriptive filename: %s' % result, log_utils.LOGDEBUG)
                    return result
                elif second_line and '/' in second_line:
                    episode_file = second_line.split('/')[-1]
                    result = self._clean_episode_name(episode_file)
                    logger.log('Torrentio: Using episode file from path: %s' % result, log_utils.LOGDEBUG)
                    return result
                else:
                    result = self._clean_pack_name(first_line)
                    logger.log('Torrentio: Using cleaned first line: %s' % result, log_utils.LOGDEBUG)
                    return result
        else:
            # For movies, use the most descriptive name available
            if filename:
                return self._clean_episode_name(filename)
            else:
                return self._clean_pack_name(first_line)
    
    def _is_season_pack(self, first_line, second_line):
        """
        Detect if this is a season pack vs individual episode
        """
        pack_indicators = [
            r'season\s+\d+-\d+',  # Season 1-8
            r's\d+-s\d+',        # S01-S08
            r'complete',          # Complete series
            r'seasons?\s+\d+',    # Season 1, Seasons 1
        ]
        
        combined_text = f"{first_line} {second_line}".lower()
        return any(re.search(pattern, combined_text, re.IGNORECASE) for pattern in pack_indicators)
    
    def _is_descriptive_episode_name(self, filename):
        """
        Check if filename contains episode title (not just episode number)
        """
        if not filename:
            return False
        
        # Remove extension and clean
        clean_name = re.sub(r'\.(mkv|mp4|avi)$', '', filename, flags=re.IGNORECASE)
        
        # Check if it contains episode title indicators
        episode_title_indicators = [
            r'\s-\s[^\d]',  # " - Something" (episode title after dash)
            r'[a-zA-Z]{4,}.*[a-zA-Z]{4,}',  # Multiple words (likely episode title)
        ]
        
        return any(re.search(pattern, clean_name) for pattern in episode_title_indicators)
    
    def _clean_pack_name(self, pack_name):
        """
        Clean the pack/collection name for display by removing quality/encoding info
        """
        clean_name = pack_name
        
        # Remove [tags] at the end (release groups, etc.)
        clean_name = re.sub(r'\[.*?\]', '', clean_name)
        
        # Remove quality/encoding information in parentheses
        # Look for patterns like (1080p BluRay x265...), (720p HDTV...), etc.
        quality_patterns = [
            r'\([^)]*(?:1080p|720p|480p|2160p|4K)[^)]*\)',  # Resolution-based quality info
            r'\([^)]*(?:BluRay|HDTV|WEB-?DL|WEBRip|DVDRip)[^)]*\)',  # Source-based quality info
            r'\([^)]*(?:x265|x264|HEVC|AVC|XVID)[^)]*\)',  # Codec-based quality info
            r'\([^)]*(?:AAC|AC3|DTS|TrueHD|FLAC)[^)]*\)',  # Audio-based quality info
        ]
        
        for pattern in quality_patterns:
            clean_name = re.sub(pattern, '', clean_name, flags=re.IGNORECASE)
        
        # Remove group tags like -GROUP at the end
        clean_name = re.sub(r'-[A-Z0-9]+$', '', clean_name, flags=re.IGNORECASE)
        
        # Clean up multiple spaces and trim
        clean_name = re.sub(r'\s+', ' ', clean_name).strip()
        
        # If we've cleaned too much and it's empty, return original
        if not clean_name or len(clean_name) < 5:
            return pack_name
            
        return clean_name
    
    def _clean_episode_name(self, episode_name, fallback=''):
        """
        Clean individual episode name for display
        """
        name_to_clean = episode_name or fallback
        if not name_to_clean:
            return 'Unknown'
        
        # If it's a path, get just the filename
        if '/' in name_to_clean:
            name_to_clean = name_to_clean.split('/')[-1]
        
        # Remove file extension
        clean_name = re.sub(r'\.(mkv|mp4|avi)$', '', name_to_clean, flags=re.IGNORECASE)
        
        # Replace dots and underscores with spaces, but preserve version numbers
        clean_name = re.sub(r'(?<!\d)\.(?!\d)', ' ', clean_name)
        clean_name = re.sub(r'_', ' ', clean_name)
        
        # Clean up multiple spaces and metadata markers
        clean_name = re.sub(r'👤.*$', '', clean_name)  # Remove seeders and everything after
        clean_name = re.sub(r'\s+', ' ', clean_name).strip()
        
        return clean_name
    
    def extract_enhanced_metadata(self, file_data):
        """
        Extract metadata with better quality detection
        """
        title = file_data.get('title', '')
        filename = file_data.get('behaviorHints', {}).get('filename', '')
        
        metadata = {
            'seeders': 0,
            'size': 0,
            'size_gb': 0,
            'source': '',
            'quality_info': []
        }
        
        # Extract seeders
        seeders_match = re.search(r'👤\s*(\d+)', title)
        if seeders_match:
            metadata['seeders'] = int(seeders_match.group(1))
        
        # Extract size
        size_match = re.search(r'💾\s*([\d.]+)\s*(GB|MB)', title)
        if size_match:
            size_value = float(size_match.group(1))
            size_unit = size_match.group(2)
            if size_unit == 'GB':
                metadata['size'] = size_value * 1024  # MB for compatibility
                metadata['size_gb'] = size_value
            else:
                metadata['size'] = size_value
                metadata['size_gb'] = size_value / 1024
        
        # Extract source
        source_match = re.search(r'⚙️\s*([\w\d\-\.]+)', title)
        if source_match:
            metadata['source'] = source_match.group(1)
        
        # Enhanced quality detection
        combined_text = f"{filename} {title}".upper()
        quality_info = []
        
        
        # Source type  
        if 'REMUX' in combined_text:
            quality_info.append('REMUX')
        elif 'BLURAY' in combined_text:
            quality_info.append('BluRay')
        elif 'WEB' in combined_text:
            quality_info.append('WEB')
        
        # Codec
        if 'X265' in combined_text or 'HEVC' in combined_text:
            quality_info.append('x265')
        elif 'X264' in combined_text:
            quality_info.append('x264')
        
        metadata['quality_info'] = quality_info
        return metadata

    def get_sources(self, video):
        sources = []
        
        try:
            # Use centralized IMDB ID retrieval from base class
            imdb_id = self.get_imdb_id(video)
            if not imdb_id:
                logger.log('Torrentio: No IMDB ID found for trakt_id: %s' % video.trakt_id, log_utils.LOGWARNING)
                return sources
            
            if video.video_type == VIDEO_TYPES.MOVIE:
                search_url = self.movie_search_url % imdb_id
                logger.log('Torrentio: Searching for movie: %s' % search_url, log_utils.LOGDEBUG)
            elif video.video_type == VIDEO_TYPES.EPISODE:
                search_url = self.tv_search_url % (imdb_id, video.season, video.episode)
                logger.log('Torrentio: Searching for episode S%sE%s: %s' % (video.season, video.episode, search_url), log_utils.LOGDEBUG)
            else:
                logger.log('Torrentio: Unsupported video type: %s' % video.video_type, log_utils.LOGWARNING)
                return sources

            url = urllib.parse.urljoin(self.base_url, search_url)
            logger.log('Torrentio: Fetching from URL: %s' % url, log_utils.LOGDEBUG)
            response = self._http_get(url, cache_limit=1, require_debrid=True)
            if not response or response == FORCE_NO_MATCH:
                logger.log('Torrentio: No response or forced no match', log_utils.LOGDEBUG)
                return sources

            try:
                data = json.loads(response)
                files = data.get('streams', [])
                logger.log('Torrentio: Found %d streams from API' % len(files), log_utils.LOGDEBUG)
            except json.JSONDecodeError as e:
                logger.log('Torrentio: Failed to parse JSON response: %s' % str(e), log_utils.LOGERROR)
                return sources

            for file_data in files:
                try:
                    hash_value = file_data.get('infoHash')
                    if not hash_value:
                        continue
                    
                    # Get intelligent name based on content type
                    display_name = self.get_intelligent_name(file_data, video.video_type)
                    logger.log('Torrentio: Generated display_name: %s' % display_name, log_utils.LOGDEBUG)
                    
                    # Extract enhanced metadata
                    metadata = self.extract_enhanced_metadata(file_data)
                    
                    # Check minimum seeders requirement
                    if self.min_seeders > metadata['seeders']:
                        logger.log('Torrentio: Skipping source with %d seeders (min: %d)' % (metadata['seeders'], self.min_seeders), log_utils.LOGDEBUG)
                        continue
                    
                    # Create magnet URL with proper encoding
                    magnet_url = 'magnet:?xt=urn:btih:%s&dn=%s' % (hash_value, urllib.parse.quote(display_name))
                    
                    # Get quality using existing method
                    quality = scraper_utils.get_tor_quality(file_data.get('title', ''))
                    
                    # Create enhanced label
                    quality_str = ', '.join(metadata['quality_info'][:2])  # Max 2 quality tags
                    size_str = f"{metadata['size_gb']:.1f}GB" if metadata['size_gb'] > 0 else "Unknown"
                    
                    label_parts = [display_name]
                    if quality_str:
                        label_parts.append(quality_str)
                    label_parts.append(f"{size_str} | {metadata['seeders']}")
                    if metadata.get('source'):
                        label_parts.append(f"{metadata['source']}")
                    
                    label = ' | '.join(label_parts)
                    
                    source = {
                        'class': self,
                        'host': 'magnet',
                        'label': label,
                        'multi-part': False,
                        'seeders': metadata['seeders'],
                        'hash': hash_value,
                        'name': display_name,
                        'quality': quality,
                        'size': metadata['size'],
                        'language': 'en',
                        'url': magnet_url,
                        'direct': False,
                        'debridonly': True
                    }
                    
                    sources.append(source)
                    logger.log('Torrentio: Added source: %s [%s] [%d seeders]' % (display_name, quality, metadata['seeders']), log_utils.LOGDEBUG)
                    
                except Exception as e:
                    logger.log('Torrentio: Error processing stream: %s' % str(e), log_utils.LOGWARNING)
                    continue

        except Exception as e:
            logger.log('Torrentio: Unexpected error in get_sources: %s' % str(e), log_utils.LOGERROR)

        logger.log('Torrentio: Returning %d sources' % len(sources), log_utils.LOGDEBUG)
        return sources

    def search(self, video_type, title, year, season=''):
        """
        Search method for Torrentio scraper.
        Torrentio works best with IMDB IDs through get_sources.
        """
        logger.log('Torrentio: Text search not optimal - use get_sources with IMDB ID for best results', log_utils.LOGDEBUG)
        return []
    


