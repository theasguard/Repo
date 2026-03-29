"""
    Plugin for ResolveURL
    Copyright (c) 2024 pikdum

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

import json
import re

import requests

from resolveurl import common
from resolveurl.common import i18n
from resolveurl.lib import helpers
from resolveurl.resolver import ResolverError, ResolveUrl
from six.moves import urllib_error, urllib_parse

logger = common.log_utils.Logger.get_logger(__name__)
# logger.disable()  # Temporarily enabled for debugging Usenet support

AGENT = "ResolveURL for Kodi"
VERSION = common.addon_version
USER_AGENT = "{0}/{1}".format(AGENT, VERSION)
FORMATS = common.VIDEO_FORMATS
ip_url = 'https://api.ipify.org'

class TorBoxResolver(ResolveUrl):
    name = "TorBox"
    domains = ["*"]
    api_url = "https://api.torbox.app/v1/api"

    def __init__(self):
        self.hosters = None
        self.hosts = None
        self.headers = {
            "User-Agent": USER_AGENT,
            "Authorization": "Bearer %s" % self.__get_token(),
        }

    def __api(self, endpoint, query=None, data=None, empty=None, json_data=False):
        try:
            if query:
                url = "{0}/{1}?{2}".format(
                    self.api_url, endpoint, urllib_parse.urlencode(query)
                )
                logger.log_debug("TorBox: GET request to %s" % url)
                result = self.net.http_GET(url, headers=self.headers).content
            if data:
                url = "{0}/{1}".format(self.api_url, endpoint)
                logger.log_debug("TorBox: POST request to %s with data: %s" % (url, str(data)))
                result = self.net.http_POST(
                    url,
                    data,
                    headers=self.headers,
                    timeout=90,
                    jdata=json_data,
                ).content
            if not query and not data:
                url = "{0}/{1}".format(self.api_url, endpoint)
                logger.log_debug("TorBox: GET request to %s" % url)
                result = self.net.http_GET(url, headers=self.headers).content
            if not result:
                logger.log_debug("TorBox: API returned empty response")
                return empty
            result = json.loads(result)
            logger.log_debug("TorBox: API response: %s" % str(result))
            if result.get("success"):
                return result.get("data")
            else:
                logger.log_error("TorBox: API returned success=False: %s" % str(result))
            return empty
        except urllib_error.HTTPError as e:
            logger.log_error("TorBox: HTTP Error %s: %s" % (e.code, str(e)))
            if e.code == 429:
                common.kodi.sleep(1500)
                return self.__api(endpoint, query, data, empty)
            return empty
        except Exception as e:
            logger.log_error("TorBox: API Exception: %s" % str(e))
            return empty

    def __get(self, endpoint, query, empty=None):
        return self.__api(endpoint, query=query, empty=empty)

    def __post(self, endpoint, data, empty=None, json_data=False):
        return self.__api(endpoint, data=data, empty=empty, json_data=json_data)

    def __check_torrent_cached(self, btih):
        result = self.__get(
            "torrents/checkcached",
            {"hash": btih, "format": "list", "list_files": False},
        )
        return bool(result)

    def __create_torrent(self, magnet):
        result = self.__post(
            "torrents/createtorrent",
            {"magnet": magnet, "seed": 3, "allow_zip": False},
            {},
        )
        return result

    def __get_torrent_info(self, torrent_id):
        result = self.__get(
            "torrents/mylist", {"id": torrent_id, "bypass_cache": True}, {}
        )
        return result

    def __request_torrent_download(self, torrent_id, file_id):
        return self.__get(
            "torrents/requestdl",
            {"torrent_id": torrent_id, "file_id": file_id, "token": self.__get_token()},
        )

    def __delete_torrent(self, torrent_id):
        return self.__post(
            "torrents/controltorrent",
            {"torrent_id": torrent_id, "operation": "delete"},
            json_data=True,
        )

    def __create_webdl(self, url):
        result = self.__post("webdl/createwebdownload", {"link": url})
        return result

    def __get_webdl_info(self, webdl_id):
        result = self.__get("webdl/mylist", {"id": webdl_id, "bypass_cache": True}, {})
        return result

    def __request_webdl_download(self, webdl_id, file_id):
        return self.__get(
            "webdl/requestdl",
            {"web_id": webdl_id, "file_id": file_id, "token": self.__get_token()},
        )

    def __delete_webdl(self, webdl_id):
        return self.__post(
            "webdl/controlwebdownload",
            {"webdl_id": webdl_id, "operation": "delete"},
            json_data=True,
        )

    def __create_usenet(self, nzb_id):
        logger.log_debug("TorBox: Creating Usenet download for: %s" % nzb_id)
        result = self.__post("usenet/createusenetdownload", {"link": nzb_id}, {})
        logger.log_debug("TorBox: Usenet API response: %s" % str(result))
        if not result:
            logger.log_error("TorBox: Failed to create Usenet download for %s" % nzb_id)
        return result

    def __get_usenet_info(self, usenet_id):
        result = self.__get("usenet/mylist", {"id": usenet_id, "bypass_cache": True}, {})
        logger.log_debug("TorBox: Usenet info response: %s" % str(result))
        return result

    def __request_usenet_download(self, usenet_id, file_id):
        logger.log_debug("TorBox: Requesting download link for usenet_id=%s, file_id=%s" % (usenet_id, file_id))
        # According to TorBox API documentation, the usenet/requestdl endpoint requires:
        # usenetdownload_id and file_id as parameters, and the token should be in the headers
    # Get user IP
        try: user_ip = self.net.http_GET("https://api.ipify.org", timeout=2.0).content
        except: user_ip = ''
        params = {
            "token": self.__get_token(),
            "usenet_id": usenet_id,
            "file_id": file_id
        }
        if user_ip:
            params["user_ip"] = user_ip
    
        result = self.__get("usenet/requestdl", params)
        logger.log_debug("TorBox: Usenet download link response: %s" % str(result))
        # Extract the actual download link from the response
        # If result is already a string (the download link), return it
        if isinstance(result, str):
            logger.log_debug("TorBox: Extracted download link: %s" % result)
            return result
        if result and isinstance(result, dict):
            # The API response should contain the download link
            download_link = result.get("link") or result.get("url") or result.get("download_link")
            if download_link:
                logger.log_debug("TorBox: Extracted download link: %s" % download_link)
                return download_link
            # If result is a dict but no link found, return the result itself
            logger.log_debug("TorBox: No link found in response, returning full result")
            return result
        # If result is None, return None
        logger.log_error("TorBox: Could not extract download link from response: %s" % str(result))
        return None

    def __delete_usenet(self, usenet_id):
        result = self.__post(
            "usenet/controlusenetdownload",
            {"usenet_id": usenet_id, "operation": "delete"},
            json_data=True,
        )
        logger.log_debug("TorBox: Usenet delete response: %s" % str(result))
        return result

    def __get_token(self):
        return self.get_setting("apikey")

    def __get_hash(self, media_id):
        r = re.search("""magnet:.+?urn:([a-zA-Z0-9]+):([a-zA-Z0-9]+)""", media_id, re.I)
        if not r or len(r.groups()) < 2:
            return None
        return r.group(2)

    # hacky workaround to get return_all working
    # we prefix with tb:$file_id| to indicate which file to download
    # then handle it when re-resolving
    def __get_file_id(self, media_id):
        r = re.search(r"""tb:(\d*)\|(.*)""", media_id, re.I)
        if not r or len(r.groups()) < 2:
            return (None, media_id)
        return (int(r.group(1)), r.group(2))

    def __get_media_url_torrent(
        self, host, media_id, cached_only=False, return_all=False
    ):
        with common.kodi.ProgressDialog("ResolveURL TorBox") as d:
            (file_id, media_id) = self.__get_file_id(media_id)
            btih = self.__get_hash(media_id)

            d.update(0, line1="Checking cache...")
            cached = self.__check_torrent_cached(btih)
            cached_only = self.get_setting("cached_only") == "true" or cached_only
            if not cached and cached_only:
                raise ResolverError("TorBox: {0}".format(i18n("cached_torrents_only")))

            d.update(0, line1="Adding torrent...")
            torrent_id = self.__create_torrent(media_id).get("torrent_id")
            if not torrent_id:
                raise ResolverError("Errror adding torrent")

            ready = cached
            while not ready:
                info = self.__get_torrent_info(torrent_id)
                ready = info.get("download_present", False)
                if ready:
                    break
                if d.is_canceled():
                    raise ResolverError("Cancelled by user")
                torrent_name = info.get("name")
                progress = int(info.get("progress", 0) * 100)
                status = "%s (ETA: %ss)" % (info.get("download_state"), info.get("eta"))
                d.update(
                    progress,
                    line1="Waiting for download...",
                    line2=status,
                    line3=torrent_name,
                )
                common.kodi.sleep(1500)

        files = self.__get_torrent_info(torrent_id).get("files", [])
        files = [f for f in files if any(f["name"].lower().endswith(x) for x in FORMATS)]

        if return_all:
            links = [
                {
                    "name": f.get("short_name"),
                    "link": "tb:%s|%s" % (f.get("id"), media_id),
                }
                for f in files
            ]
            return links

        if len(files) > 1 and file_id is None:
            links = [[f.get("short_name"), f.get("id")] for f in files]
            links.sort(key=lambda x: x[1])
            file_id = helpers.pick_source(links, auto_pick=False)
        elif isinstance(file_id, int):
            pass
        else:
            file_id = files[0]["id"]

        download_link = self.__request_torrent_download(torrent_id, file_id)

        if self.get_setting("clear_finished") == "true":
            self.__delete_torrent(torrent_id)

        return download_link

    def __get_media_url_webdl(
        self, host, media_id, cached_only=False, return_all=False
    ):
        with common.kodi.ProgressDialog("ResolveURL TorBox") as d:
            (file_id, media_id) = self.__get_file_id(media_id)

            # can't check cache with just a url, so skip
            # otherwise, follow similar implementation as torrents

            d.update(0, line1="Adding web download...")
            webdl_id = self.__create_webdl(media_id).get("webdownload_id")
            if not webdl_id:
                raise ResolverError("Errror adding web download")

            ready = False
            while not ready:
                info = self.__get_webdl_info(webdl_id)
                ready = info.get("download_present", False)
                if ready:
                    break
                if d.is_canceled():
                    raise ResolverError("Cancelled by user")
                webdl_name = info.get("name")
                progress = int(info.get("progress", 0) * 100)
                status = "%s (ETA: %ss)" % (info.get("download_state"), info.get("eta"))
                d.update(
                    progress,
                    line1="Waiting for download...",
                    line2=status,
                    line3=webdl_name,
                )
                common.kodi.sleep(1500)

        # don't think web downloads can have multiple files right now
        # but this might handle it if they ever do
        files = self.__get_webdl_info(webdl_id).get("files", [])

        if return_all:
            links = [
                {
                    "name": f.get("short_name"),
                    "link": "tb:%s|%s" % (f.get("id"), media_id),
                }
                for f in files
            ]
            return links

        # allow user to pick if multiple files
        if len(files) > 1 and file_id is None:
            links = [[f.get("short_name"), f.get("id")] for f in files]
            links.sort(key=lambda x: x[1])
            file_id = helpers.pick_source(links, auto_pick=False)
        else:
            file_id = 0

        download_link = self.__request_webdl_download(webdl_id, file_id)

        if self.get_setting("clear_finished") == "true":
            self.__delete_webdl(webdl_id)

        return download_link

    def __get_media_url_usenet(
        self, host, media_id, cached_only=False, return_all=False
    ):
        with common.kodi.ProgressDialog("ResolveURL TorBox") as d:
            (file_id, media_id) = self.__get_file_id(media_id)

            # can't check cache with just a nzb, so skip
            # otherwise, follow similar implementation as webdl

            d.update(0, line1="Adding Usenet download...")
            result = self.__create_usenet(media_id)
            if not result:
                raise ResolverError("Failed to create Usenet download - API returned no response")
            usenet_id = result.get("usenetdownload_id")
            if not usenet_id:
                logger.log_error("TorBox Usenet API response: %s" % str(result))
                raise ResolverError("Error adding Usenet download - No usenetdownload_id in response")

            ready = False
            while not ready:
                info = self.__get_usenet_info(usenet_id)
                ready = info.get("download_present", False)
                if ready:
                    break
                if d.is_canceled():
                    raise ResolverError("Cancelled by user")
                usenet_name = info.get("name")
                progress = int(info.get("progress", 0) * 100)
                status = "%s (ETA: %ss)" % (info.get("download_state"), info.get("eta"))
                d.update(
                    progress,
                    line1="Waiting for download...",
                    line2=status,
                    line3=usenet_name,
                )
                common.kodi.sleep(1500)

        # don't think usenet downloads can have multiple files right now
        # but this might handle it if they ever do
        files = self.__get_usenet_info(usenet_id).get("files", [])
        logger.log_debug("TorBox Usenet: Files: %s" % str(files))
        # Filter files to only include video files
        video_extensions = ('.mkv', '.mp4', '.avi', '.mov', '.flv', '.wmv', '.m4v', '.mpeg', '.mpg', '.webm')
        video_files = [f for f in files if f.get('name', '').lower().endswith(video_extensions)]
        logger.log_debug("TorBox: Video files: %s" % str(video_files))

        if return_all:
            links = [
                {
                    "name": f.get("short_name"),
                    "link": "tb:%s|%s" % (f.get("id"), media_id),
                }
                for f in files
            ]
            return links

        # If only one video file, select it automatically
        if len(video_files) == 1:
            file_id = video_files[0]['id']
            return self.__request_usenet_download(usenet_id, file_id)
        
        # If multiple video files, show selection dialog
        if len(video_files) > 1:
            # Helper function to extract episode number from filename
            def extract_episode_number(filename):
                """Extract episode number from filename (e.g., S02E10 -> 10)"""
                match = re.search(r'[Ss](\d+)[Ee](\d+)', filename)
                if match:
                    return int(match.group(2))
                return 999  # Default to high number if no episode number found
            
            # Sort video files by episode number first, then by size (largest first), then by name
            sorted_videos = sorted(video_files, key=lambda k: (
                extract_episode_number(k.get('name', '')),  # Primary: episode number
                -k.get('size', 0),  # Secondary: size (descending)
                
                k.get('name', '').lower()  # Tertiary: name
            ))
            logger.log_debug("TorBox: Sorted video files: %s" % str(sorted_videos))

            # Create selection list with size information in the display name
            selection_list = []
            for video in sorted_videos:
                name = video.get('short_name', 'Unknown')
                size = video.get('size', 0)
                size_str = self.__format_size(size)
                # Extract episode number for display
                episode_match = re.search(r'[Ss](\d+)[Ee](\d+)', name)
                if episode_match:
                    episode_info = "S%02dE%02d" % (int(episode_match.group(1)), int(episode_match.group(2)))
                    display_name = "%s (%s) (%s)" % (episode_info, size_str, name)
                else:
                    display_name = "%s (%s)" % (name, size_str)
    
                selection_list.append([display_name, video.get('id')])
            
            logger.log_debug("TorBox: Selection list: %s" % str(selection_list))
            
            # Show selection dialog
            index = self.pick_source(selection_list, auto_pick=False)
            logger.log_debug("TorBox: Selected index: %s" % str(index))
            if index < 0:
                logger.log_debug("TorBox: User cancelled file selection")
                return None
            
            # CRITICAL FIX: Find the selected file by ID, not by index!
            selected_id = selection_list[index][1]  # Get the ID from selection_list
            logger.log_debug("TorBox: Selected ID: %s" % str(selected_id))
            selected_file = next((f for f in video_files if f['id'] == selected_id), None)
            logger.log_debug("TorBox: Selected file: %s" % str(selected_file))
            if not selected_file:
                logger.log_error("TorBox: Could not find selected file with id %s" % selected_id)
                return None
            file_id = selected_file['id']
            
            return self.__request_usenet_download(usenet_id, file_id)

        if self.get_setting("clear_finished") == "true":
            self.__delete_usenet(usenet_id)
    
        # Fallback - select first video file
        file_id = video_files[0]['id']

        return self.__request_usenet_download(usenet_id, file_id)

    @staticmethod
    def pick_source(sources, auto_pick=False):
        """
        Custom pick_source method for TorBox that returns the index instead of the ID.
        This fixes the issue where clicking on an episode in the dialog results in playing a different episode.
        """
        import xbmcgui
        
        if len(sources) == 1:
            return 0  # Return index 0 for single source
        elif len(sources) > 1:
            if auto_pick:
                return 0  # Return index 0 for auto-pick
            else:
                result = xbmcgui.Dialog().select(
                    common.i18n('choose_the_link'), 
                    [str(source[0]) if source[0] else 'Unknown' for source in sources]
                )
                if result == -1:
                    raise ResolverError(common.i18n('no_link_selected'))
                else:
                    return result  # Return the index, not the ID
        else:
            raise ResolverError(common.i18n('no_video_link'))

    def __format_size(self, size_bytes):
        if size_bytes == 0:
            return "0 B"
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return "%.1f %s" % (size_bytes, unit)
            size_bytes /= 1024.0
        return "%.1f PB" % size_bytes

    def __fetch_nzb_content(self, url):
        """Fetch NZB content from a URL, handling redirects and special cases."""
        try:
            logger.log_debug("TorBox: Fetching NZB content from: %s" % url)
            response = self.net.http_GET(url, headers=self.headers, timeout=30)
            content = response.content
            
            # Validate that we got NZB content
            if content and (b'<?xml' in content or b'<nzb' in content.lower()):
                logger.log_debug("TorBox: Successfully fetched NZB content (%d bytes)" % len(content))
                return content
            else:
                logger.log_error("TorBox: Fetched content doesn't appear to be NZB")
                return None
        except Exception as e:
            logger.log_error("TorBox: Error fetching NZB content: %s" % str(e))
            return None

    def get_media_url(self, host, media_id, cached_only=False, return_all=False):
        (_, parsed_media_id) = self.__get_file_id(media_id)
        logger.log_debug("TorBox: get_media_url called with media_id: %s" % media_id)
        logger.log_debug("TorBox: Parsed media_id: %s" % parsed_media_id)
        if parsed_media_id.startswith("magnet:"):
            logger.log_debug("TorBox: Routing to torrent handler")
            return self.__get_media_url_torrent(host, media_id, cached_only, return_all)
        elif parsed_media_id.lower().endswith(".nzb") or "/nzb:" in parsed_media_id.lower() or parsed_media_id.startswith("nzb:"):
            logger.log_debug("TorBox: Routing to usenet handler")
            return self.__get_media_url_usenet(host, media_id, cached_only, return_all)
        else:
            logger.log_debug("TorBox: Routing to webdl handler")
            return self.__get_media_url_webdl(host, media_id, cached_only, return_all)

    def get_url(self, host, media_id):
        return media_id

    def get_host_and_id(self, url):
        return "torbox.app", url

    def valid_url(self, url, host):
        if not self.hosts:
            self.hosts = self.get_all_hosters()

        if url:
            # handle multi-file hack
            if url.startswith("tb:"):
                return True

            # magnet link
            if url.startswith("magnet:"):
                btih = self.__get_hash(url)
                return bool(btih) and self.get_setting("torrents") == "true"

            # usenet - expanded to handle more NZB URL formats
            if (url.lower().endswith(".nzb") or 
                "/nzb:" in url.lower() or 
                url.startswith("nzb:")):
                return self.get_setting("usenet") == "true"

            # webdl
            if not self.get_setting("web_downloads") == "true":
                return False

            try:
                host = urllib_parse.urlparse(url).hostname
            except:
                host = "unknown"

            host = host.replace("www.", "")
            if any(host in item for item in self.hosts):
                return True

        elif host:
            host = host.replace("www.", "")
            if any(host in item for item in self.hosts):
                return True

        return False

    @common.cache.cache_method(cache_limit=8)
    def get_all_hosters(self):
        hosts = []
        try:
            result = self.__get("webdl/hosters", None, [])
            hosts = [h.get("domains") for h in result if h.get("status", False)]
            hosts = [host for sublist in hosts for host in sublist]
            if self.get_setting("torrents") == "true":
                hosts.extend(["torrent", "magnet"])
            if self.get_setting("usenet") == "true":
                hosts.extend(["usenet", "nzb"])
        except Exception as e:
            logger.log_error("Error getting TorBox hosts: %s" % (e))
        return hosts

    @classmethod
    def get_settings_xml(cls):
        xml = super(cls, cls).get_settings_xml(include_login=False)
        xml.append(
            '<setting id="%s_torrents" type="bool" label="%s" default="true"/>'
            % (cls.__name__, i18n("torrents"))
        )
        xml.append(
            '<setting id="%s_cached_only" enable="eq(-1,true)" type="bool" label="%s" default="false" />'
            % (cls.__name__, i18n("cached_only"))
        )
        xml.append(
            '<setting id="%s_web_downloads" type="bool" label="%s" default="true"/>'
            % (cls.__name__, "Web Download Support")
        )
        xml.append(
            '<setting id="%s_usenet" type="bool" label="%s" default="true"/>'
            % (cls.__name__, "Usenet Support")
        )
        xml.append(
            '<setting id="%s_clear_finished" type="bool" label="%s" default="true"/>'
            % (cls.__name__, "Clear Finished downloads from account")
        )
        xml.append(
            '<setting id="%s_apikey" enable="eq(-5,true)" type="text" label="%s" default=""/>'
            % (cls.__name__, "API Key")
        )
        return xml

    @classmethod
    def isUniversal(cls):
        return True

    @classmethod
    def _is_enabled(cls):
        return cls.get_setting("enabled") == "true" and cls.get_setting("apikey")
