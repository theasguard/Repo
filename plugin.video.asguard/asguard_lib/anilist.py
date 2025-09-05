# -*- coding: utf-8 -*-

'''
    Asgard Add-on
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
'''

import urllib.parse, urllib.request
import requests
import cache
import kodi
import log_utils
import utils
import xbmcaddon
import json
import re
from asguard_lib import client

logger = log_utils.Logger.get_logger()

ADDON = xbmcaddon.Addon()
ANILIST_API = 'https://graphql.anilist.co'

class AniListAPI:
    """
    AniList GraphQL API client for anime metadata and title resolution
    """
    
    def __init__(self):
        self.base_url = ANILIST_API
        self.session = requests.Session()
        self.session.headers.update({
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'Asguard Kodi Addon/1.0'
        })

    def _make_request(self, query, variables=None, cache_hours=24):
        """
        Make a GraphQL request to AniList API with caching
        """
        try:
            payload = {
                'query': query,
                'variables': variables or {}
            }
            
            # Create cache key from query and variables
            cache_key = f"anilist_{hash(str(payload))}"
            
            # Try to get from cache first
            cached_result = cache.get(lambda: None, cache_hours, cache_key)
            if cached_result:
                logger.log(f'[ANILIST] Cache hit for query', log_utils.LOGDEBUG)
                return cached_result
            
            logger.log(f'[ANILIST] Making API request to {self.base_url}', log_utils.LOGDEBUG)
            
            response = self.session.post(self.base_url, json=payload, timeout=30)
            response.raise_for_status()
            
            data = response.json()
            
            if 'errors' in data:
                logger.log(f'[ANILIST] API returned errors: {data["errors"]}', log_utils.LOGERROR)
                return None
            
            result = data.get('data')
            
            # Cache the result
            cache.get(lambda: result, cache_hours, cache_key)
            
            return result
            
        except requests.exceptions.RequestException as e:
            logger.log(f'[ANILIST] Request error: {str(e)}', log_utils.LOGERROR)
            return None
        except json.JSONDecodeError as e:
            logger.log(f'[ANILIST] JSON decode error: {str(e)}', log_utils.LOGERROR)
            return None
        except Exception as e:
            logger.log(f'[ANILIST] Unexpected error: {str(e)}', log_utils.LOGERROR)
            return None

    def get_anime_by_id(self, anilist_id):
        """
        Get anime details by AniList ID
        """
        query = '''
        query ($id: Int) {
            Media(id: $id, type: ANIME) {
                id
                title {
                    romaji
                    english
                    native
                    userPreferred
                }
                synonyms
                coverImage {
                    extraLarge
                    large
                    medium
                }
                bannerImage
                startDate {
                    year
                    month
                    day
                }
                endDate {
                    year
                    month
                    day
                }
                episodes
                duration
                status
                format
                genres
                averageScore
                popularity
                description
                studios {
                    nodes {
                        name
                    }
                }
                externalLinks {
                    url
                    site
                }
                relations {
                    edges {
                        node {
                            id
                            title {
                                romaji
                                english
                            }
                        }
                        relationType
                    }
                }
            }
        }
        '''
        
        variables = {'id': int(anilist_id)}
        result = self._make_request(query, variables)
        
        if result and 'Media' in result:
            return result['Media']
        return None

    def search_anime(self, title, year=None, format_filter=None):
        """
        Search for anime by title with optional year and format filtering
        """
        query = '''
        query ($search: String, $year: Int, $format: MediaFormat) {
            Page(page: 1, perPage: 20) {
                media(search: $search, type: ANIME, year: $year, format: $format, sort: POPULARITY_DESC) {
                    id
                    title {
                        romaji
                        english
                        native
                        userPreferred
                    }
                    synonyms
                    startDate {
                        year
                    }
                    episodes
                    format
                    status
                    averageScore
                    popularity
                    coverImage {
                        medium
                    }
                }
            }
        }
        '''
        
        variables = {'search': title}
        if year:
            variables['year'] = int(year)
        if format_filter:
            variables['format'] = format_filter
            
        result = self._make_request(query, variables)
        
        if result and 'Page' in result and 'media' in result['Page']:
            return result['Page']['media']
        return []

    def get_anime_titles(self, anilist_id):
        """
        Get all available titles for an anime (romaji, english, synonyms)
        Returns a list of title variations that can be used for scraping
        """
        anime = self.get_anime_by_id(anilist_id)
        if not anime:
            return []
        
        titles = []
        title_data = anime.get('title', {})
        
        # Add main titles
        if title_data.get('romaji'):
            titles.append(title_data['romaji'])
        if title_data.get('english'):
            titles.append(title_data['english'])
        if title_data.get('native'):
            titles.append(title_data['native'])
        if title_data.get('userPreferred'):
            titles.append(title_data['userPreferred'])
        
        # Add synonyms
        synonyms = anime.get('synonyms', [])
        if synonyms:
            titles.extend(synonyms)
        
        # Remove duplicates while preserving order
        unique_titles = []
        seen = set()
        for title in titles:
            if title and title not in seen:
                unique_titles.append(title)
                seen.add(title)
        
        logger.log(f'[ANILIST] Found {len(unique_titles)} title variations for ID {anilist_id}: {unique_titles}', log_utils.LOGDEBUG)
        return unique_titles

    def find_best_match(self, search_title, year=None):
        """
        Find the best matching anime for a given title and year
        Returns the anime data with confidence score
        """
        logger.log(f'[ANILIST] Searching for best match: "{search_title}" ({year})', log_utils.LOGDEBUG)
        
        # Search for anime
        results = self.search_anime(search_title, year)
        if not results:
            logger.log(f'[ANILIST] No results found for "{search_title}"', log_utils.LOGDEBUG)
            return None
        
        best_match = None
        best_score = 0
        
        for anime in results:
            score = self._calculate_match_score(search_title, anime, year)
            logger.log(f'[ANILIST] Match score for "{anime.get("title", {}).get("romaji", "Unknown")}": {score}', log_utils.LOGDEBUG)
            
            if score > best_score:
                best_score = score
                best_match = anime
        
        if best_match and best_score > 0.6:  # Minimum confidence threshold
            logger.log(f'[ANILIST] Best match found: "{best_match.get("title", {}).get("romaji", "Unknown")}" (score: {best_score})', log_utils.LOGDEBUG)
            return {
                'anime': best_match,
                'confidence': best_score
            }
        
        logger.log(f'[ANILIST] No confident match found (best score: {best_score})', log_utils.LOGDEBUG)
        return None

    def _calculate_match_score(self, search_title, anime, search_year=None):
        """
        Calculate how well an anime matches the search criteria
        Returns a score between 0 and 1
        """
        score = 0
        search_title_lower = search_title.lower().strip()
        
        # Get all titles for this anime
        titles = []
        title_data = anime.get('title', {})
        
        if title_data.get('romaji'):
            titles.append(title_data['romaji'])
        if title_data.get('english'):
            titles.append(title_data['english'])
        if title_data.get('userPreferred'):
            titles.append(title_data['userPreferred'])
        
        synonyms = anime.get('synonyms', [])
        if synonyms:
            titles.extend(synonyms)
        
        # Check for exact matches first
        for title in titles:
            if not title:
                continue
            title_lower = title.lower().strip()
            
            if title_lower == search_title_lower:
                score = max(score, 1.0)  # Perfect match
            elif search_title_lower in title_lower or title_lower in search_title_lower:
                score = max(score, 0.9)  # Very good match
        
        # Check word overlap
        search_words = set(search_title_lower.split())
        for title in titles:
            if not title:
                continue
            title_words = set(title.lower().split())
            
            if search_words and title_words:
                overlap = len(search_words & title_words)
                total_words = len(search_words | title_words)
                word_score = overlap / total_words if total_words > 0 else 0
                score = max(score, word_score * 0.8)  # Word overlap match
        
        # Year bonus/penalty
        if search_year:
            anime_year = anime.get('startDate', {}).get('year')
            if anime_year:
                year_diff = abs(int(search_year) - anime_year)
                if year_diff == 0:
                    score += 0.1  # Exact year match bonus
                elif year_diff <= 1:
                    score += 0.05  # Close year match bonus
                elif year_diff > 3:
                    score *= 0.8  # Significant year difference penalty
        
        # Popularity bonus (slight preference for more popular anime)
        popularity = anime.get('popularity', 0)
        if popularity > 10000:
            score += 0.02
        elif popularity > 5000:
            score += 0.01
        
        return min(score, 1.0)  # Cap at 1.0

    def get_anime_by_mal_id(self, mal_id):
        """
        Get anime by MyAnimeList ID using external links
        """
        query = '''
        query ($malId: Int) {
            Media(idMal: $malId, type: ANIME) {
                id
                title {
                    romaji
                    english
                    native
                    userPreferred
                }
                synonyms
                startDate {
                    year
                }
                episodes
                format
                status
            }
        }
        '''
        
        variables = {'malId': int(mal_id)}
        result = self._make_request(query, variables)
        
        if result and 'Media' in result:
            return result['Media']
        return None

    def get_seasonal_anime(self, year, season):
        """
        Get anime from a specific season
        season: 'WINTER', 'SPRING', 'SUMMER', 'FALL'
        """
        query = '''
        query ($year: Int, $season: MediaSeason) {
            Page(page: 1, perPage: 50) {
                media(year: $year, season: $season, type: ANIME, sort: POPULARITY_DESC) {
                    id
                    title {
                        romaji
                        english
                        userPreferred
                    }
                    episodes
                    format
                    status
                    averageScore
                    coverImage {
                        medium
                    }
                }
            }
        }
        '''
        
        variables = {
            'year': int(year),
            'season': season.upper()
        }
        
        result = self._make_request(query, variables)
        
        if result and 'Page' in result and 'media' in result['Page']:
            return result['Page']['media']
        return []

    def clean_title_for_search(self, title):
        """
        Clean anime title for better search results
        Removes common suffixes and normalizes the title
        """
        if not title:
            return title
        
        # Remove common anime suffixes that might interfere with search
        suffixes_to_remove = [
            r'\s*\(dub\)$',
            r'\s*\(sub\)$', 
            r'\s*\(uncensored\)$',
            r'\s*\(tv\)$',
            r'\s*\(ova\)$',
            r'\s*\(movie\)$',
            r'\s*\(special\)$',
            r'\s*season\s*\d+$',
            r'\s*s\d+$',
            r'\s*\d+nd\s*season$',
            r'\s*\d+rd\s*season$',
            r'\s*\d+th\s*season$',
            r'\s*second\s*season$',
            r'\s*third\s*season$',
            r'\s*final\s*season$'
        ]
        
        cleaned_title = title
        for suffix_pattern in suffixes_to_remove:
            cleaned_title = re.sub(suffix_pattern, '', cleaned_title, flags=re.IGNORECASE)
        
        # Clean up extra whitespace
        cleaned_title = re.sub(r'\s+', ' ', cleaned_title).strip()
        
        logger.log(f'[ANILIST] Cleaned title: "{title}" -> "{cleaned_title}"', log_utils.LOGDEBUG)
        return cleaned_title

    def get_title_variations_for_scraping(self, anilist_id):
        """
        Get title variations optimized for scraping anime sites
        Returns titles in order of preference for scraping
        """
        titles = self.get_anime_titles(anilist_id)
        if not titles:
            return []
        
        # Prioritize titles for scraping
        # 1. English title (most common on western anime sites)
        # 2. Romaji title (common on anime sites)
        # 3. Synonyms (alternative titles)
        
        anime = self.get_anime_by_id(anilist_id)
        if not anime:
            return titles
        
        title_data = anime.get('title', {})
        prioritized_titles = []
        
        # Add English title first if available
        if title_data.get('english'):
            prioritized_titles.append(title_data['english'])
        
        # Add Romaji title
        if title_data.get('romaji') and title_data['romaji'] not in prioritized_titles:
            prioritized_titles.append(title_data['romaji'])
        
        # Add user preferred if different
        if title_data.get('userPreferred') and title_data['userPreferred'] not in prioritized_titles:
            prioritized_titles.append(title_data['userPreferred'])
        
        # Add synonyms
        synonyms = anime.get('synonyms', [])
        for synonym in synonyms:
            if synonym and synonym not in prioritized_titles:
                prioritized_titles.append(synonym)
        
        # Clean titles for better scraping compatibility
        cleaned_titles = []
        for title in prioritized_titles:
            cleaned = self.clean_title_for_search(title)
            if cleaned and cleaned not in cleaned_titles:
                cleaned_titles.append(cleaned)
        
        logger.log(f'[ANILIST] Title variations for scraping (ID {anilist_id}): {cleaned_titles}', log_utils.LOGDEBUG)
        return cleaned_titles

# Global instance for easy access
anilist_api = AniListAPI()

def get_anime_titles_for_scraping(anilist_id):
    """
    Convenience function to get anime titles for scraping
    """
    return anilist_api.get_title_variations_for_scraping(anilist_id)

def search_anime_by_title(title, year=None):
    """
    Convenience function to search for anime and get the best match
    """
    return anilist_api.find_best_match(title, year)

def get_anime_info(anilist_id):
    """
    Convenience function to get anime information
    """
    return anilist_api.get_anime_by_id(anilist_id)