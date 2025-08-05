import requests
import xbmcaddon
from urllib.parse import urlencode
import log_utils
from asguard_lib.utils2 import i18n
import time

logger = log_utils.Logger.get_logger()
addon = xbmcaddon.Addon('plugin.video.asguard')

CLIENT_ID = "1fc5c54a3879a1a41b0ace9f9fb52411f607631379ea8a6b57fcc789832aeca0"
CLIENT_SECRET = "eb9bd1ec3d932c3197096e90ae04f6dbd2ea11f0afec0f021822bec746ebab30"
BASE_URL = "https://api.simkl.com"

class SimklAPI:
    def __init__(self):
        self.access_token = addon.getSetting('simkl_token')
        self.refresh_token = addon.getSetting('simkl_refresh_token')
        self._update_headers()

    def _update_headers(self):
        self.headers = {
            'Authorization': f'Bearer {self.access_token}',
            'simkl-api-key': CLIENT_ID,
            'Content-Type': 'application/json'
        }

    def _get(self, endpoint, params=None):
        url = f"{BASE_URL}/{endpoint}"
        try:
            response = requests.get(url, headers=self.headers, params=params, timeout=10)
            if response.status_code == 401 and self.refresh_token:
                if self.refresh_auth_token():
                    response = requests.get(url, headers=self.headers, params=params, timeout=10)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.log(f"Simkl API Error: {str(e)}", log_utils.LOGERROR)
            return None

    def get_trending_anime(self):
        return self._get("anime/trending") or []

    def get_popular_anime(self):
        return self._get("anime/popular") or []

    def search_anime(self, query):
        return self._get("search/anime", {'q': query}) or []

    def get_anime_episodes(self, simkl_id):
        return self._get(f"anime/{simkl_id}/episodes") or []

    @staticmethod
    def get_auth_url():
        params = {
            'response_type': 'code',
            'client_id': CLIENT_ID,
            'redirect_uri': 'urn:ietf:wg:oauth:2.0:oob'
        }
        return f"https://simkl.com/oauth/authorize?{urlencode(params)}"

    def get_user_profile(self):
        return self._get("users/settings") or {}

    def get_device_code(self):
        url = "https://api.simkl.com/oauth/token"
        data = {'client_id': CLIENT_ID}
        response = requests.post(url, json=data)
        response.raise_for_status()
        return response.json()

    def poll_authentication(self, device_code):
        url = "https://api.simkl.com/oauth/authorize"
        data = {
            'response_type': 'code',
            'client_id': CLIENT_ID,
            'redirect_uri': 'urn:ietf:wg:oauth:2.0:oob'
        }
        
        start_time = time.time()
        expires_in = 600  # 10 minutes
        interval = 5  # polling interval in seconds
        
        while (time.time() - start_time) < expires_in:
            try:
                response = requests.post(url, json=data)
                if response.status_code == 200:
                    token_data = response.json()
                    self._store_tokens(token_data)
                    return True
                elif response.status_code == 400:
                    time.sleep(interval)
                else:
                    response.raise_for_status()
            except Exception as e:
                logger.log(f"Simkl Polling Error: {str(e)}", log_utils.LOGERROR)
                return False
        return False

    def authenticate(self, code):
        """Exchange authorization code for access token"""
        url = "https://api.simkl.com/oauth/token"
        data = {
            'client_id': CLIENT_ID,
            'redirect_uri': 'urn:ietf:wg:oauth:2.0:oob',
            'response_type': 'code'
        }
        
        try:
            response = requests.post(url, json=data)
            response.raise_for_status()
            self._store_tokens(response.json())
            return True
        except Exception as e:
            logger.log(f"Authentication Failed: {str(e)}", log_utils.LOGERROR)
            return False

    def _store_tokens(self, token_data):
        self.access_token = token_data['access_token']
        self.refresh_token = token_data.get('refresh_token', '')
        addon.setSetting('simkl_token', self.access_token)
        addon.setSetting('simkl_refresh_token', self.refresh_token)
        self._update_headers()

    def refresh_auth_token(self):
        """Refresh expired access token"""
        if not self.refresh_token:
            return False
            
        url = "https://api.simkl.com/oauth/token"
        data = {
            'client_id': CLIENT_ID,
            'client_secret': CLIENT_SECRET,
            'refresh_token': self.refresh_token,
            'grant_type': 'refresh_token'
        }
        
        try:
            response = requests.post(url, json=data)
            response.raise_for_status()
            self._store_tokens(response.json())
            return True
        except Exception as e:
            logger.log(f"Token Refresh Failed: {str(e)}", log_utils.LOGERROR)
            return False
