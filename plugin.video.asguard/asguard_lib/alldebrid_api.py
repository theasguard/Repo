import sqlite3
import time
import requests
import kodi
import xbmc
import utils
import log_utils
import urllib.request
import urllib.parse
import urllib.error
import json
from asguard_lib import scraper_utils, control
import xbmcaddon
import os

logger = log_utils.Logger.get_logger()

class Alldebrid_API():
    def __init__(self):
        self.base_url = 'https://api.alldebrid.com/v4'
        self.agent = 'Asguard'
        self.api_key = control.getSetting('alldebrid_api_key')
        self.token = None

    def unlock_link(self, link):
        """
        Unlock a link using AllDebrid's API and cache the result.
        """
        if not self.token:
            if not self.authenticate():
                return None

        # Check if the link is already cached
        cached_link = self.get_cached_link(link)
        if cached_link:
            return cached_link

        # Unlock the link using AllDebrid API
        response = self.__call_alldebrid('/link/unlock', params={'agent': self.agent, 'apikey': self.token, 'link': link})
        if response and response['status'] == 'success':
            resolved_link = response['data']['link']
            self.cache_link(link, resolved_link)
            return resolved_link
        else:
            logger.log(f"Failed to unlock link: {response.get('error', 'Unknown error')}", log_utils.LOGERROR)
        return None

    def get_cached_link(self, link):
        """
        Retrieve a cached link from the database.
        """
        try:
            db_path = xbmc.translatePath(xbmcaddon.Addon("plugin.video.asguard").getAddonInfo('profile'))
            db_path = os.path.join(db_path, 'asguardcache.db')
            dbcon = sqlite3.connect(db_path)
            dbcur = dbcon.cursor()
            dbcur.execute("SELECT source FROM source_cache WHERE source=?", (link,))
            match = dbcur.fetchone()
            if match:
                return match[0]
        except sqlite3.DatabaseError as e:
            logger.log(f"Database error accessing cached link: {str(e)}", log_utils.LOGERROR)
        finally:
            if 'dbcon' in locals():
                dbcon.close()
        return None

    def cache_link(self, original_link, resolved_link):
        """
        Cache the resolved link in the database.
        """
        try:
            db_path = xbmc.translatePath(xbmcaddon.Addon("plugin.video.asguard").getAddonInfo('profile'))
            db_path = os.path.join(db_path, 'asguardcache.db')
            dbcon = sqlite3.connect(db_path)
            dbcur = dbcon.cursor()
            dbcur.execute("INSERT INTO source_cache (source) VALUES (?)", (resolved_link,))
            dbcon.commit()
        except sqlite3.DatabaseError as e:
            logger.log(f"Database error caching link: {str(e)}", log_utils.LOGERROR)
        finally:
            if 'dbcon' in locals():
                dbcon.close()

    def get_user_profile(self, username=None, cached=True):
        if username is None: username = 'me'
        url = '/users/%s' % (utils.to_slug(username))
        return url

    def authenticate(self):
        response = self.__call_alldebrid('/pin/get', params={'agent': self.agent}, auth=False)
        if not response or 'data' not in response:
            logger.log("Failed to start authentication process", log_utils.LOGERROR)
            return False

        self.device_code = response['data']['pin']
        self.poll_url = response['data']['check_url']
        expires_in = response['data']['expires_in']

        logger.log(f"Please visit {response['data']['base_url']} and enter the PIN: {self.device_code}", log_utils.LOGINFO)

        start_time = time.time()
        while time.time() - start_time < expires_in:
            time.sleep(5)  # Poll every 5 seconds
            if self.__poll_auth():
                logger.log("Authentication successful.", log_utils.LOGINFO)
                return True
        logger.log("Authentication timed out.", log_utils.LOGERROR)
        return False

    def __poll_auth(self):
        response = self.__call_alldebrid(self.poll_url, auth=False)
        if response and response.get('status') == 'success':
            self.token = response['data']['token']
            return True
        return False
    
    def check_hash(self, hash_list):
        return self.post_json("magnet/instant", {"magnets[]": hash_list})

    def update_relevant_hosters(self):
        return self.get_json("hosts")

    def get_hosters(self, hosters):
        host_list = self.update_relevant_hosters()
        if host_list is not None:
            hosters["premium"]["all_debrid"] = [
                (d, d.split(".")[0])
                for l in host_list["hosts"].values()
                if "status" in l and l["status"]
                for d in l["domains"]
            ]
        else:
            hosters["premium"]["all_debrid"] = []

    def resolve_hoster(self, url):
        resolve = self.get_json("link/unlock", link=url)
        return resolve["link"]

    def magnet_status(self, magnet_id):
        return self.get_json("magnet/status", id=magnet_id) if magnet_id else self.get_json("magnet/status")

    def saved_magnets(self):
        return self.get_json("magnet/status")['magnets']

    def delete_magnet(self, magnet_id):
        return self.get_json("magnet/delete", id=magnet_id)

    def saved_links(self):
        return self.get_json("user/links")


    def get_user_info(self):
        return self._extract_data(self.get_json("user")).get("user", {})
    
    def post_json(self, url, post_data=None, **params):
        return self._extract_data(self.post(url, post_data, **params).json())

    def _extract_data(self, response):
        return response["data"] if "data" in response else response

    def resolve_magnet_with_alldebrid(self, magnet_link):
        """
        Resolve magnet link using AllDebrid.
        """
        if not self.token:
            if not self.authenticate():
                return None

        response = self.__call_alldebrid('/magnet/instant', method='POST', params={'agent': self.agent, 'apikey': self.token, 'magnet': magnet_link})
        if response and response['status'] == 'success' and response['data']['magnets']:
            return response['data']['magnets'][0]['link']
        else:
            logger.log(f"Failed to resolve magnet link: {response.get('error', 'Unknown error')}", log_utils.LOGERROR)
        return None

    def get_streaming_links(self, link):
        """
        Get streaming links from AllDebrid.
        """
        if not self.token:
            if not self.authenticate():
                return None

        response = self.__call_alldebrid('/link/unlock', params={'agent': self.agent, 'apikey': self.token, 'link': link})
        if response and response['status'] == 'success':
            return response['data']['streams']
        else:
            logger.log(f"Failed to get streaming links: {response.get('error', 'Unknown error')}", log_utils.LOGERROR)
        return None

    def get_download_link(self, link):
        """
        Get a direct download link from AllDebrid.
        """
        if not self.token:
            if not self.authenticate():
                return None

        response = self.__call_alldebrid('/link/unlock', params={'agent': self.agent, 'apikey': self.token, 'link': link})
        if response and response['status'] == 'success':
            return response['data']['link']
        else:
            logger.log(f"Failed to get download link: {response.get('error', 'Unknown error')}", log_utils.LOGERROR)
        return None