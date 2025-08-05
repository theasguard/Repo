from asguard_lib import db_utils
import json
import logging
import cache
import kodi
import log_utils
import urllib.request
import ssl

logger = log_utils.Logger.get_logger()

class TVDBAPI:
    def __init__(self):
        self.base_url = "https://api4.thetvdb.com/v4"
        self.token = None
        self.api_key = 'b64a2c35-ba29-4353-b46c-1e306874afb6'
        self.headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            'User-Agent': 'Asguard for Kodi'
        }
        self.get_token()
        
    def get_token(self):
        """Authenticate with TVDB API and get token"""
        url = f"{self.base_url}/login"
        payload = json.dumps({"apikey": self.api_key})
        
        try:
            # Create SSL context that works with TVDB's certificate
            context = ssl.create_default_context()
            context.set_ciphers('DEFAULT@SECLEVEL=1')
            
            req = urllib.request.Request(url, data=payload.encode('utf-8'), headers=self.headers)
            req.get_method = lambda: 'POST'
            
            with urllib.request.urlopen(req, timeout=10, context=context) as response:
                res = response.read().decode('utf-8')
                data = json.loads(res)
                
                if data.get('status') == 'success':
                    token = data.get('data', {}).get('token')
                    if token:
                        self.token = token
                        self.headers['Authorization'] = f'Bearer {token}'
                        logger.log('TVDB API login successful', log_utils.LOGDEBUG)
                        return token
                else:
                    error_msg = data.get('message', 'Unknown error')
                    logger.log(f'TVDB API login failed: {error_msg}', log_utils.LOGERROR)
                    return None
                    
        except Exception as e:
            logger.log(f'TVDB API login exception: {str(e)}', log_utils.LOGERROR)
            return None

    def get_request(self, url):
        """Make authenticated GET request to TVDB API"""
        if not self.token:
            self.get_token()
            if not self.token:
                logger.log('TVDB token not available for request', log_utils.LOGERROR)
                return None
                
        full_url = f"{self.base_url}{url}"
        
        try:
            # Create SSL context
            context = ssl.create_default_context()
            context.set_ciphers('DEFAULT@SECLEVEL=1')
            
            req = urllib.request.Request(full_url, headers=self.headers)
            with urllib.request.urlopen(req, timeout=10, context=context) as response:
                return json.loads(response.read().decode('utf-8'))
                
        except Exception as e:
            logger.log(f'TVDB API request exception: {str(e)}', log_utils.LOGERROR)
            return None

    def get_episode(self, tvdb_id, season, episode):
        """Get episode details by season and episode number"""
        try:
            url = f"/series/{tvdb_id}/episodes/query?season={season}&episodeNumber={episode}"
            response = self.get_request(url)
            
            if not response:
                logger.log(f'TVDB API returned no data for TVDB ID {tvdb_id}', log_utils.LOGWARNING)
                return None
                
            if 'data' in response and response['data']:
                return response['data'][0]
                
            logger.log(f'TVDB API returned empty episode data for TVDB ID {tvdb_id}', log_utils.LOGDEBUG)
            return None
            
        except Exception as e:
            logger.log(f'TVDB API exception: {str(e)}', log_utils.LOGERROR)
            return None

    def get_imdb_id(self, tvdb_id):
        imdb_id = None
        url = 'series/{}/extended'.format(tvdb_id)
        data = self.get_request(url)
        if data:
            imdb_id = [x.get('id') for x in data['remoteIds'] if x.get('type') == 2]
        return imdb_id[0] if imdb_id else None

    def get_seasons(self, tvdb_id):
        url = 'seasons/{}/extended'.format(tvdb_id)
        data = self.get_request(url)
        return data
    
    def get_episodes(self, tvdb_id, season_number):
        url = f'series/{tvdb_id}/episodes?season={season_number}'
        data = self.get_request(url)
        return data

    def get_series_extended(self, tvdb_id):
        try:
            res = self.get_request(f"series/{tvdb_id}/extended?meta=episodes&short=false")
            if not res:  # Add null check for response
                logger.log('TVDB API request returned empty response', log_utils.LOGERROR)
                return None
                
            data = res
            if data.get('status') != 'success':
                logger.log(f"TVDB API failed: {data.get('message', 'Unknown error')}", log_utils.LOGERROR)
                return None
                
            series_data = data
            return {
                'id': series_data['id'],
                'title': series_data.get('name'),
                'year': series_data.get('year'),
                'plot': series_data.get('overview'),
                'episodes': self._parse_episodes(series_data.get('episodes', [])),
                'art': self._parse_artwork(series_data.get('artworks', [])),
                'genres': [g['name'] for g in series_data.get('genres', [])],
                'status': series_data.get('status', {}).get('name'),
                'rating': series_data.get('score'),
                'network': series_data.get('originalNetwork', {}).get('name')
            }
            
        except Exception as e:
            logger.log(f"Failed to get series data: {str(e)}", log_utils.LOGERROR)
            return None

    def _parse_episodes(self, episodes):
        parsed = []
        for ep in episodes:
            if not ep.get('aired'):
                continue
            
            parsed.append({
                'episode_id': ep['id'],
                'season': ep.get('seasonNumber', 0),
                'episode': ep.get('number', 0),
                'title': ep.get('name'),
                'aired': ep.get('aired'),
                'runtime': ep.get('runtime'),
                'plot': ep.get('overview'),
                'image': self._full_image_url(ep.get('image')),
                'absolute_number': ep.get('absoluteNumber'),
                'finale_type': ep.get('finaleType')
            })
        return parsed

    def _parse_artwork(self, artworks):
        return {
            'poster': next((a['image'] for a in artworks if a['type'] == 2), None),
            'fanart': next((a['image'] for a in artworks if a['type'] == 3), None)
        }

    def _full_image_url(self, path):
        if path and not path.startswith('http'):
            return f"https://artworks.thetvdb.com{path}"
        return path
