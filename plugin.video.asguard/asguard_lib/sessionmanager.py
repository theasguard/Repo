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

# Third-party library imports
import cache, requests, urllib3
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util import Retry

# Kodi-specific imports
import xbmcaddon

# Local module imports
import kodi, log_utils
logger = log_utils.Logger.get_logger(__name__)


UA = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36'


class SessionManager:
    _instance = None
    _session = None
    _executor = None
    _initialized = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialize()
            cls._initialized = True
        return cls._instance
    
    def _initialize(self):
        """Initialize shared session and thread pool"""
        cls = SessionManager
        
        # Create shared session with connection pooling
        cls._session = requests.Session()
        
        # Configure retry strategy
        retry_strategy = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS", "POST"]
        )
        
        # Mount adapter with connection pooling
        adapter = HTTPAdapter(
            max_retries=retry_strategy,
            pool_connections=15,
            pool_maxsize=15,
            pool_block=False
        )
        
        # Get HTTPS setting
        use_https = kodi.get_setting('use_https') == 'true'

        # Mount for each image API domain using the shared adapter
        # FanartTV
        if use_https:
            cls._session.mount('https://webservice.fanart.tv', adapter)
        else:
            cls._session.mount('http://webservice.fanart.tv', adapter)

        # TMDB
        if use_https:
            cls._session.mount('https://api.themoviedb.org', adapter)
        else:
            cls._session.mount('http://api.themoviedb.org', adapter)

        # TVDB
        if use_https:
            cls._session.mount('https://api.thetvdb.com', adapter)
            cls._session.mount('https://api4.thetvdb.com', adapter)
            cls._session.mount('https://artworks.thetvdb.com', adapter)
        else:
            cls._session.mount('http://api.thetvdb.com', adapter)
            cls._session.mount('http://api4.thetvdb.com', adapter)
            cls._session.mount('http://artworks.thetvdb.com', adapter)

        # TVMaze
        if use_https:
            cls._session.mount('https://api.tvmaze.com', adapter)
        else:
            cls._session.mount('http://api.tvmaze.com', adapter)

        # OMDb
        if use_https:
            cls._session.mount('https://www.omdbapi.com', adapter)
        else:
            cls._session.mount('http://www.omdbapi.com', adapter)

        # IMDb
        if use_https:
            cls._session.mount('https://www.imdb.com', adapter)
        else:
            cls._session.mount('http://www.imdb.com', adapter)

        # TVDB images (always HTTP based on code)
        cls._session.mount('http://thetvdb.com', adapter)
        
        cls._session.mount('http://', adapter)
        cls._session.mount('https://', adapter)
        
        # Create shared thread pool with reduced workers
        cls._executor = ThreadPoolExecutor(max_workers=7, thread_name_prefix='image_scraper')
    
    @classmethod
    def get_session(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance._session
    
    @classmethod
    def get_executor(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance._executor
    
    @classmethod
    def close(cls):
        """Clean up resources"""
        if cls._instance:
            if cls._instance._executor:
                cls._instance._executor.shutdown(wait=False)
            if cls._instance._session:
                cls._instance._session.close()
            cls._instance = None
            cls._initialized = False