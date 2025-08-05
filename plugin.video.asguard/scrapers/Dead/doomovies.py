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
import re
import urllib.parse
import requests
import json
import log_utils
import kodi
import dom_parser2
from asguard_lib import scraper_utils
from asguard_lib.constants import FORCE_NO_MATCH
from asguard_lib.constants import QUALITIES
from asguard_lib.constants import VIDEO_TYPES
from asguard_lib.utils2 import i18n
from . import scraper

try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)

logger = log_utils.Logger.get_logger()

BASE_URL = 'https://doomovies.net'

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting('%s-base_url' % (self.get_name()))
        self.session = requests.Session()

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])


    @classmethod
    def get_name(cls):
        return 'DoMovies'

    def get_sources(self, video):
        hosters = []
        source_url = self.get_url(video)
        
        if not source_url or source_url == FORCE_NO_MATCH:
            return hosters

        url = scraper_utils.urljoin(self.base_url, source_url)
        logger.log('DoMovies: Getting sources for: %s' % url, log_utils.LOGDEBUG)
        html = self._http_get(url, cache_limit=.5)
            
        if not html or html == FORCE_NO_MATCH:
            return hosters

        try:
            # Get quality info if available
            qual = ''
            quality_match = dom_parser2.parse_dom(html, 'strong', {'class': 'quality'})
            if quality_match:
                qual = quality_match[0].content

            # Process streaming sources using AJAX
            hosters.extend(self._get_streaming_sources(html, url, qual, video))
            
            # Process download links
            hosters.extend(self._get_download_sources(html, qual, video))

        except Exception as e:
            logger.log('Error getting sources: %s' % str(e), log_utils.LOGWARNING)

        return hosters

    def _get_streaming_sources(self, html, referer_url, quality_info, video):
        """Extract streaming sources from AJAX player options"""
        hosters = []
        
        try:
            # Extract player options
            results = re.findall(r'''<li id='player-option(.+?)</li>''', html, re.DOTALL)
            
            for result in results:
                try:
                    # Only process English sources
                    if '/en.png' not in result:
                        continue
                        
                    # Extract AJAX parameters
                    ajax_matches = re.findall(r'''data-type=['"](.+?)['"] data-post=['"](.+?)['"] data-nume=['"](\d+)['"]>''', result, re.DOTALL)
                    
                    for data_type, data_post, data_nume in ajax_matches:
                        try:
                            stream_url = self._get_ajax_stream(data_type, data_post, data_nume, referer_url)
                            if stream_url and 'imdb.com' not in stream_url:
                                host = urllib.parse.urlparse(stream_url).hostname
                                if host:
                                    quality = scraper_utils.get_quality(None, host, QUALITIES.HIGH)
                                    if quality_info:
                                        quality = scraper_utils.get_quality(None, quality_info, quality)
                                    
                                    hoster = {
                                        'class': self,
                                        'multi-part': False,
                                        'host': host,
                                        'quality': quality,
                                        'views': None,
                                        'rating': None,
                                        'url': stream_url,
                                        'direct': False,
                                        'debridonly': False
                                    }
                                    hosters.append(hoster)
                                    logger.log('Found streaming source: %s from %s' % (stream_url, host), log_utils.LOGDEBUG)
                                    
                        except Exception as e:
                            logger.log('Error processing AJAX source: %s' % str(e), log_utils.LOGDEBUG)
                            continue
                            
                except Exception as e:
                    logger.log('Error processing player option: %s' % str(e), log_utils.LOGDEBUG)
                    continue
                    
        except Exception as e:
            logger.log('Error getting streaming sources: %s' % str(e), log_utils.LOGWARNING)
            
        return hosters

    def _get_ajax_stream(self, data_type, data_post, data_nume, referer_url):
        """Make AJAX request to get stream URL"""
        try:
            ajax_url = scraper_utils.urljoin(self.base_url, '/wp-admin/admin-ajax.php')
            
            headers = {
                'Host': urllib.parse.urlparse(self.base_url).hostname,
                'Accept': '*/*',
                'Origin': self.base_url,
                'X-Requested-With': 'XMLHttpRequest',
                'User-Agent': scraper_utils.get_ua(),
                'Referer': referer_url,
                'Accept-Encoding': 'gzip, deflate',
                'Accept-Language': 'en-US,en;q=0.9'
            }
            
            payload = {
                'action': 'doo_player_ajax',
                'post': data_post,
                'nume': data_nume,
                'type': data_type
            }
            
            response = self.session.post(ajax_url, headers=headers, data=payload, timeout=self.timeout)
            
            if response.status_code == 200:
                json_data = response.json()
                if json_data.get('type') == 'iframe':
                    embed_url = json_data.get('embed_url', '').replace('\\', '')
                    return embed_url
                    
        except Exception as e:
            logger.log('AJAX request failed: %s' % str(e), log_utils.LOGDEBUG)
            
        return None

    def _get_download_sources(self, html, quality_info, video):
        """Extract download sources from tables"""
        hosters = []
        
        try:
            tbody = dom_parser2.parse_dom(html, 'tbody')
            if not tbody:
                return hosters
                
            tr_elements = dom_parser2.parse_dom(html, 'tr')
            
            # Filter for English downloads, exclude certain domains
            english_rows = []
            for tr in tr_elements:
                if 'English' in tr and not any(x in tr for x in ['domain=filefactory.com', 'domain=za.gl']):
                    english_rows.append(tr)
            
            for row in english_rows:
                try:
                    # Extract download link and quality
                    link_match = dom_parser2.parse_dom(row, 'a', {'target': '_blank'}, req='href')
                    quality_match = dom_parser2.parse_dom(row, 'strong', {'class': 'quality'})
                    
                    if link_match:
                        download_url = link_match[0].attrs['href']
                        row_quality = quality_match[0].content if quality_match else quality_info
                        
                        # Follow redirect to get actual URL
                        try:
                            final_url = self._http_get(download_url, allow_redirect=True, method='HEAD')
                            if final_url:
                                host = urllib.parse.urlparse(final_url).hostname
                                if host:
                                    quality = scraper_utils.get_quality(None, host, QUALITIES.HIGH)
                                    if row_quality:
                                        quality = scraper_utils.get_quality(None, row_quality, quality)
                                    
                                    hoster = {
                                        'class': self,
                                        'multi-part': False,
                                        'host': host,
                                        'quality': quality,
                                        'views': None,
                                        'rating': None,
                                        'url': final_url,
                                        'direct': False,
                                        'debridonly': False
                                    }
                                    hosters.append(hoster)
                                    logger.log('Found download source: %s from %s' % (final_url, host), log_utils.LOGDEBUG)
                                    
                        except Exception as e:
                            logger.log('Error following download redirect: %s' % str(e), log_utils.LOGDEBUG)
                            continue
                            
                except Exception as e:
                    logger.log('Error processing download row: %s' % str(e), log_utils.LOGDEBUG)
                    continue
                    
        except Exception as e:
            logger.log('Error getting download sources: %s' % str(e), log_utils.LOGWARNING)
            
        return hosters

    def search(self, video_type, title, year, season=''):
        results = []
            
        try:
            # Use RSS search like the original scrubsv2 implementation
            search_url = scraper_utils.urljoin(self.base_url, '/search/%s/feed/rss2/' % scraper_utils.cleanse_title(title).replace(' ', '+'))
            
            html = self._http_get(search_url, cache_limit=1)
            if not html:
                return results

            # Parse RSS items
            items = dom_parser2.parse_dom(html, 'item')
            
            for item in items:
                try:
                    link_match = dom_parser2.parse_dom(item, 'link')
                    title_match = dom_parser2.parse_dom(item, 'title')
                    
                    if link_match and title_match:
                        result_url = link_match[0].content
                        logger.log('DoMovies: Result URL: %s' % result_url, log_utils.LOGDEBUG)
                        result_title = title_match[0].content
                        
                        # Check if this matches our search and video type
                        if scraper_utils.normalize_title(title) in scraper_utils.normalize_title(result_title):
                            # Determine if this is a movie or TV show based on URL
                            is_movie = '/movies/' in result_url
                            is_tvshow = '/tvshows/' in result_url
                            
                            # Filter by video type
                            if video_type == VIDEO_TYPES.MOVIE and not is_movie:
                                continue
                            elif video_type in [VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE] and not is_tvshow:
                                continue
                            
                            # Extract year from title or URL if possible
                            result_year = year
                            year_match = re.search(r'(\d{4})', result_title)
                            if year_match:
                                result_year = year_match.group(1)
                            
                            result = {
                                'url': scraper_utils.pathify_url(result_url),
                                'title': scraper_utils.cleanse_title(result_title),
                                'year': result_year
                            }
                            results.append(result)
                            logger.log('Found search result: %s (%s) - %s' % (result_title, result_year, 'Movie' if is_movie else 'TV Show'), log_utils.LOGDEBUG)
                            
                except Exception as e:
                    logger.log('Error processing search result: %s' % str(e), log_utils.LOGDEBUG)
                    continue
                    
        except Exception as e:
            logger.log('Search error: %s' % str(e), log_utils.LOGWARNING)
            
        return results

    def get_url(self, video):
        """Get URL for video based on type"""
        return self._default_get_url(video)

    def _get_episode_url(self, show_url, video):
        """Get episode URL from show page"""
        episode_pattern = r'href="([^"]*[sS]%s[eE]%s[^"]*)"' % (video.season, video.episode)
        title_pattern = r'href="([^"]+)">([^<]+)</a>'
        
        show_url = scraper_utils.urljoin(self.base_url, show_url)
        html = self._http_get(show_url, cache_limit=2)
        
        if not html:
            return
            
        # Try direct episode pattern match first
        episode_match = re.search(episode_pattern, html, re.I)
        if episode_match:
            return scraper_utils.pathify_url(episode_match.group(1))
            
        # Look for season/episode in links
        links = re.findall(title_pattern, html, re.I)
        for link, link_title in links:
            # Check if link contains season/episode info
            if ('season' in link_title.lower() and 'episode' in link_title.lower()) or \
               (f's{video.season}' in link_title.lower() and f'e{video.episode}' in link_title.lower()) or \
               (f's{video.season:02d}' in link_title.lower() and f'e{video.episode:02d}' in link_title.lower()):
                return scraper_utils.pathify_url(link)
                
        return

