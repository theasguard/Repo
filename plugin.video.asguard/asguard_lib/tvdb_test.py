import json
import urllib
import urllib.request
from http import HTTPStatus
from urllib.error import HTTPError
from typing import Any, Dict, List


# ------------------------
#  CODE YOU PROVIDED
#  (unchanged except indentation and syntax fixes)
# ------------------------

class Auth:
    def __init__(self, url, apikey, pin=""):
        loginInfo = {"apikey": apikey}
        if pin != "":
            loginInfo["pin"] = pin

        loginInfoBytes = json.dumps(loginInfo, indent=2).encode("utf-8")
        req = urllib.request.Request(url, data=loginInfoBytes)
        req.add_header("Content-Type", "application/json")

        try:
            with urllib.request.urlopen(req, data=loginInfoBytes) as response:
                res = json.load(response)
                self.token = res["data"]["token"]
        except HTTPError as e:
            res = json.load(e)
            raise Exception("Code:{}, {}".format(e, res["message"]))

    def get_token(self):
        return self.token


class Request:
    def __init__(self, auth_token):
        self.auth_token = auth_token
        self.links = None

    def make_request(self, url, if_modified_since=None):
        req = urllib.request.Request(url)
        req.add_header("Authorization", "Bearer {}".format(self.auth_token))

        if if_modified_since:
            req.add_header("If-Modified-Since", "{}".format(if_modified_since))

        try:
            with urllib.request.urlopen(req) as response:
                res = json.load(response)
        except HTTPError as e:
            try:
                if e.code == HTTPStatus.NOT_MODIFIED:
                    return {
                        "code": HTTPStatus.NOT_MODIFIED.real,
                        "message": "Not-Modified",
                    }

                res = json.load(e)
            except Exception:
                res = {}

            data = res.get("data", None)
            if data is not None and res.get("status", "failure") != "failure":
                self.links = res.get("links", None)
                return data

            msg = res.get("message", None)
            if not msg:
                msg = "UNKNOWN FAILURE"
            raise ValueError("failed to get " + url + "\n " + str(msg))

        data = res.get("data", None)
        if data is not None:
            self.links = res.get("links", None)
            return data

        raise ValueError("No 'data' in response for " + url)


class Url:
    def __init__(self):
        self.base_url = "https://api4.thetvdb.com/v4/"

    def construct(self, url_sect, url_id=None, url_subsect=None, url_lang=None, **query):
        url = self.base_url + url_sect

        if url_id:
            url += "/" + str(url_id)
        if url_subsect:
            url += "/" + url_subsect
        if url_lang:
            url += "/" + url_lang

        if query:
            query = {var: val for var, val in query.items() if val is not None}
            if query:
                url += "?" + urllib.parse.urlencode(query)

        return url


class TVDB:
    def __init__(self, apikey: str, pin: str = ""):
        self.url = Url()
        login_url = self.url.construct("login")
        self.auth = Auth(login_url, apikey, pin)
        auth_token = self.auth.get_token()
        self.request = Request(auth_token)

    def get_req_links(self) -> dict:
        return self.request.links

    def get_all_series(self, page=None, meta=None, if_modified_since=None) -> list:
        url = self.url.construct("series", page=page, meta=meta)
        return self.request.make_request(url, if_modified_since)

    def get_series(self, id: int, meta=None, if_modified_since=None) -> dict:
        url = self.url.construct("series", id, meta=meta)
        return self.request.make_request(url, if_modified_since)

    def get_series_extended(self, id: int, meta=None, short=False, if_modified_since=None) -> dict:
        url = self.url.construct("series", id, "extended", meta=meta, short=short)
        return self.request.make_request(url, if_modified_since)

    def get_series_episodes(
        self,
        id: int,
        season_type: str = "default",
        page: int = 0,
        lang: str = None,
        meta=None,
        if_modified_since=None,
        **kwargs
    ) -> dict:
        url = self.url.construct(
            "series",
            id,
            "episodes/" + season_type,
            lang,
            page=page,
            meta=meta,
            **kwargs
        )
        return self.request.make_request(url, if_modified_since)

    def get_episode(self, id: int, meta=None, if_modified_since=None) -> dict:
        url = self.url.construct("episodes", id, meta=meta)
        return self.request.make_request(url, if_modified_since)

    def get_episode_extended(self, id: int, meta=None, if_modified_since=None) -> dict:
        url = self.url.construct("episodes", id, "extended", meta=meta)
        return self.request.make_request(url, if_modified_since)

    # NOTE: The full class has many more methods. For this test we only need the ones above.
    # You can paste the rest of your class here if you plan to use them.


# ------------------------
#  TEST HARNESS
# ------------------------

API_KEY = "b64a2c35-ba29-4353-b46c-1e306874afb6"
PIN = ""  # put your PIN here if your key uses one, otherwise leave empty

SERIES_IDS = {
    "Solo Leveling": 389597,
    "IT": 418424,
}


def extract_artwork_fields(ep_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    TVDB v4 episodes can have different shapes.
    This tries to pull any obvious artwork-related fields so you can see what exists.
    """
    keys_of_interest = [
        "image",
        "filename",
        "thumbnail",
        "artwork",
        "photo",
        "poster",
        "still",
    ]

    found = {}
    for key in keys_of_interest:
        if key in ep_data and ep_data[key]:
            found[key] = ep_data[key]

    # Some responses may nest artwork; try a few common spots conservatively
    if "artworks" in ep_data and isinstance(ep_data["artworks"], list):
        found["artworks"] = ep_data["artworks"]

    return found


def print_episode_page_info(series_name: str, series_id: int, page_data: Dict[str, Any]) -> None:
    """
    page_data is the result of get_series_episodes(...).
    According to TVDB v4, this usually has keys like 'episodes', maybe paging.
    """
    episodes = page_data.get("episodes") or page_data.get("data") or []

    print(f"\nSeries: {series_name} (ID {series_id})")
    print(f"Number of episodes in this page: {len(episodes)}")

    for ep in episodes:
        # Try to identify season/episode numbers
        season_num = ep.get("seasonNumber") or ep.get("season_number") or "?"
        episode_num = ep.get("number") or ep.get("episodeNumber") or ep.get("episode_number") or "?"
        name = ep.get("name") or ep.get("episodeName") or "<no name>"

        # Try to extract artwork
        artwork_info = extract_artwork_fields(ep)

        print(f"  S{season_num}E{episode_num} – {name}")
        if artwork_info:
            for k, v in artwork_info.items():
                # Truncate URLs for readability
                v_str = str(v)
                if isinstance(v, str) and len(v_str) > 100:
                    v_str = v_str[:97] + "..."
                print(f"    {k}: {v_str}")
        else:
            print("    No obvious artwork fields on this episode object")


def main() -> None:
    if not API_KEY or API_KEY == "PUT_YOUR_TVDB_V4_API_KEY_HERE":
        print("ERROR: Set your TVDB v4 API key in API_KEY before running this script.")
        return

    print("Initializing TVDB client...")
    tvdb = TVDB(API_KEY, PIN)

    for series_name, series_id in SERIES_IDS.items():
        print("\n" + "-" * 80)
        print(f"Testing series: {series_name} (ID {series_id})")

        # Basic series check
        try:
            series_info = tvdb.get_series(series_id)
            print("Series info title:", series_info.get("name") or series_info.get("seriesName"))
        except Exception as e:
            print(f"Failed to fetch series info for {series_name} ({series_id}): {e}")
            continue

        # Episode listing:
        # - season_type="default" is usually what you want
        # - we'll only grab the first page to keep this as a quick test
        try:
            episodes_page = tvdb.get_series_episodes(
                series_id,
                season_type="default",
                page=0,
                lang=None,   # or "en"
                meta=None
            )
            print_episode_page_info(series_name, series_id, episodes_page)
        except Exception as e:
            print(f"Failed to fetch episodes for {series_name} ({series_id}): {e}")


if __name__ == "__main__":
    main()