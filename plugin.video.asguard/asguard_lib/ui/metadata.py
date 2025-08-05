import threading
import pickle
import json
import six
import cache
import logging
from asguard_lib import client
from six.moves import urllib_parse
from asguard_lib import db_utils
from asguard_lib.image_scraper import FanartTVScraper, TMDBScraper

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def collect_meta(anime_list):
    threads = []
    for anime in anime_list:
        if 'media' in anime:
            anime = anime['media']
        anilist_id = anime.get('id')
        if anilist_id:
            thread = threading.Thread(target=update_meta, args=(anilist_id,))
            threads.append(thread)
            thread.start()
        else:
            logger.warning("Anime ID not found in anime: %s", anime)

    for thread in threads:
        thread.join()

def update_meta(anilist_id, meta_ids={}, mtype='tv'):
    try:
        meta = FanartTVScraper()._extract_art(meta_ids, mtype)
        if not meta:
            meta = TMDBScraper().__get_best_image(meta_ids, mtype)
        elif 'fanart' not in meta:
            meta2 = TMDBScraper().__get_best_image(meta_ids, mtype)
            if meta2.get('fanart'):
                meta['fanart'] = meta2['fanart']
        db_utils.update_show_meta(anilist_id, meta_ids, meta)
    except Exception as e:
        logger.error("Failed to update metadata for AniList ID %s: %s", anilist_id, str(e))

class AniListAPI:
    baseUrl = 'https://graphql.anilist.co'

    def _json_request(self, query, variables):
        try:
            response = cache.get(
                client.request,
                72,
                self.baseUrl,
                data=json.dumps({'query': query, 'variables': variables}),
                headers={'Content-Type': 'application/json'},
                error=True,
                output='extended',
                timeout=30
            )
            if response and int(response[1]) < 300 and 'request failed!' not in response[0]:
                return json.loads(response[0])
            else:
                logger.error("Failed to get a valid response from AniList API: %s", response)
        except Exception as e:
            logger.error("Error during AniList API request: %s", str(e))
        return {}

    def get_anilist(self, anilist_id):
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
                coverImage {
                    extraLarge
                }
                startDate {
                    year
                    month
                    day
                }
                episodes
                status
                format
                duration
                averageScore
                description
            }
        }
        '''
        variables = {'id': anilist_id}
        return self._json_request(query, variables)

class AniDBAPI:
    baseUrl = 'https://api.anidb.net/'

    def _json_request(self, url):
        try:
            response = cache.get(
                client.request,
                72,
                urllib_parse.urljoin(self.baseUrl, url),
                error=True,
                output='extended',
                timeout=30
            )
            if response and int(response[1]) < 300 and 'request failed!' not in response[0]:
                return json.loads(response[0])
            else:
                logger.error("Failed to get a valid response from AniDB API: %s", response)
        except Exception as e:
            logger.error("Error during AniDB API request: %s", str(e))
        return {}

    def get_anidb(self, anidb_id):
        url = '/anime/{0}'.format(anidb_id)
        return self._json_request(url)