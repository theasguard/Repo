import datetime
import xbmc
import xbmcaddon
import log_utils
from asguard_lib.db_utils import DB_Connection
from asguard_lib.constants import VIDEO_TYPES

logger = log_utils.Logger.get_logger(__name__)

# SQL Queries
GET_WATCHED_ITEM = "SELECT * FROM watched_status WHERE db_type = ? AND media_id = ? AND season = ? AND episode = ?"
SET_WATCHED_STATUS = "INSERT OR REPLACE INTO watched_status (db_type, media_id, title, season, episode, last_played, trakt_id, tmdb_id, tvdb_id, imdb_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
DELETE_WATCHED_STATUS = "DELETE FROM watched_status WHERE db_type = ? AND media_id = ? AND season = ? AND episode = ?"
GET_WATCHED_MOVIES = "SELECT media_id, title, last_played, trakt_id, tmdb_id, tvdb_id, imdb_id FROM watched_status WHERE db_type = ? AND season = \'\' AND episode = \'\' ORDER BY last_played DESC"
GET_WATCHED_EPISODES = "SELECT media_id, title, last_played, season, episode, trakt_id, tmdb_id, tvdb_id, imdb_id FROM watched_status WHERE db_type = ? ORDER BY last_played DESC"
GET_NEXT_EPISODES = "SELECT media_id, title, last_played, season, episode, trakt_id, tmdb_id, tvdb_id, imdb_id FROM (SELECT *, ROW_NUMBER() OVER (PARTITION BY media_id ORDER BY season DESC, episode DESC) AS r FROM watched_status WHERE db_type = ?) AS t WHERE r = 1"
CLEAR_ALL_WATCHED = "DELETE FROM watched_status"
GET_WATCHED_COUNT = "SELECT COUNT(*) FROM watched_status WHERE db_type = ? AND media_id = ?"
GET_WATCHED_BY_ID = "SELECT * FROM watched_status WHERE (trakt_id = ? OR tmdb_id = ? OR tvdb_id = ? OR imdb_id = ?) AND db_type = ? AND season = ? AND episode = ?"
GET_WATCHED_BY_ANY_ID = "SELECT * FROM watched_status WHERE trakt_id = ? OR tmdb_id = ? OR tvdb_id = ? OR imdb_id = ?"


class WatchedCache:
    def __init__(self):
        self.db = DB_Connection()
        self._init_tables()

    def _init_tables(self):
        try:
            if not self.db.__table_exists('watched_status'):
                logger.log('Creating watched_status table', log_utils.LOGNOTICE)
                self.db.__execute('CREATE TABLE IF NOT EXISTS watched_status (db_type TEXT NOT NULL, media_id TEXT NOT NULL, title TEXT, season TEXT NOT NULL, episode TEXT NOT NULL, last_played TEXT NOT NULL, trakt_id TEXT, tmdb_id TEXT, tvdb_id TEXT, imdb_id TEXT, PRIMARY KEY(db_type, media_id, season, episode))')
                logger.log('watched_status table created successfully', log_utils.LOGNOTICE)
        except Exception as e:
            logger.log('Failed to create watched_status table: %s' % str(e), log_utils.LOGERROR)

    def mark_watched(self, video_type, media_id, title='', season='', episode='', trakt_id='', tmdb_id='', tvdb_id='', imdb_id=''):
        try:
            video_type = str(video_type)
            media_id = str(media_id)
            season = str(season) if season else ''
            episode = str(episode) if episode else ''
            trakt_id = str(trakt_id) if trakt_id else ''
            tmdb_id = str(tmdb_id) if tmdb_id else ''
            tvdb_id = str(tvdb_id) if tvdb_id else ''
            imdb_id = str(imdb_id) if imdb_id else ''
            last_played = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            self.db.__execute(SET_WATCHED_STATUS, (video_type, media_id, title, season, episode, last_played, trakt_id, tmdb_id, tvdb_id, imdb_id))
            logger.log('Marked as watched: %s %s S%sE%s (IDs: trakt=%s, tmdb=%s, tvdb=%s, imdb=%s)' % (video_type, media_id, season, episode, trakt_id, tmdb_id, tvdb_id, imdb_id), log_utils.LOGDEBUG)
            return True
        except Exception as e:
            logger.log('Failed to mark as watched: %s' % str(e), log_utils.LOGERROR)
            return False

    def mark_unwatched(self, video_type, media_id, season='', episode=''):
        try:
            video_type = str(video_type)
            media_id = str(media_id)
            season = str(season) if season else ''
            episode = str(episode) if episode else ''
            self.db.__execute(DELETE_WATCHED_STATUS, (video_type, media_id, season, episode))
            logger.log('Marked as unwatched: %s %s S%sE%s' % (video_type, media_id, season, episode), log_utils.LOGDEBUG)
            return True
        except Exception as e:
            logger.log('Failed to mark as unwatched: %s' % str(e), log_utils.LOGERROR)
            return False

    def is_watched(self, video_type, media_id, season='', episode=''):
        try:
            video_type = str(video_type)
            media_id = str(media_id)
            season = str(season) if season else ''
            episode = str(episode) if episode else ''
            result = self.db.__execute(GET_WATCHED_ITEM, (video_type, media_id, season, episode))
            return bool(result)
        except Exception as e:
            logger.log('Failed to check watched status: %s' % str(e), log_utils.LOGERROR)
            return False

    def is_watched_by_any_id(self, trakt_id='', tmdb_id='', tvdb_id='', imdb_id='', season='', episode=''):
        """Check if item is watched using any of the provided IDs"""
        try:
            trakt_id = str(trakt_id) if trakt_id else ''
            tmdb_id = str(tmdb_id) if tmdb_id else ''
            tvdb_id = str(tvdb_id) if tvdb_id else ''
            imdb_id = str(imdb_id) if imdb_id else ''
            season = str(season) if season else ''
            episode = str(episode) if episode else ''
            result = self.db.__execute(GET_WATCHED_BY_ANY_ID, (trakt_id, tmdb_id, tvdb_id, imdb_id))
            return bool(result)
        except Exception as e:
            logger.log('Failed to check watched status by any ID: %s' % str(e), log_utils.LOGERROR)
            return False

    def get_watched_movies(self):
        try:
            movies = []
            rows = self.db.__execute(GET_WATCHED_MOVIES, ('movie',))
            for row in rows:
                movies.append({
                    'media_id': row[0], 
                    'title': row[1], 
                    'last_played': row[2],
                    'trakt_id': row[3],
                    'tmdb_id': row[4],
                    'imdb_id': row[5]
                })
            return movies
        except Exception as e:
            logger.log('Failed to get watched movies: %s' % str(e), log_utils.LOGERROR)
            return []

    def get_watched_episodes(self):
        try:
            episodes = []
            rows = self.db.__execute(GET_WATCHED_EPISODES, ('episode',))
            for row in rows:
                episodes.append({
                    'media_id': row[0], 
                    'title': row[1], 
                    'last_played': row[2], 
                    'season': row[3], 
                    'episode': row[4],
                    'trakt_id': row[5],
                    'tmdb_id': row[6],
                    'tvdb_id': row[7],
                    'imdb_id': row[8]
                })
            return episodes
        except Exception as e:
            logger.log('Failed to get watched episodes: %s' % str(e), log_utils.LOGERROR)
            return []

    def get_next_episodes(self):
        try:
            episodes = []
            rows = self.db.__execute(GET_NEXT_EPISODES, ('episode',))
            for row in rows:
                episodes.append({
                    'media_id': row[0], 
                    'title': row[1], 
                    'last_played': row[2], 
                    'season': row[3], 
                    'episode': row[4],
                    'trakt_id': row[5],
                    'tmdb_id': row[6],
                    'tvdb_id': row[7],
                    'imdb_id': row[8]
                })
            return episodes
        except Exception as e:
            logger.log('Failed to get next episodes: %s' % str(e), log_utils.LOGERROR)
            return []

    def get_watched_count(self, video_type, media_id):
        try:
            video_type = str(video_type)
            media_id = str(media_id)
            result = self.db.__execute(GET_WATCHED_COUNT, (video_type, media_id))
            return result[0][0] if result else 0
        except Exception as e:
            logger.log('Failed to get watched count: %s' % str(e), log_utils.LOGERROR)
            return 0

    def clear_all(self):
        try:
            self.db.__execute(CLEAR_ALL_WATCHED)
            logger.log('Cleared all watched status from cache', log_utils.LOGNOTICE)
            return True
        except Exception as e:
            logger.log('Failed to clear watched cache: %s' % str(e), log_utils.LOGERROR)
            return False


_watched_cache = None


def get_watched_cache():
    global _watched_cache
    if _watched_cache is None:
        _watched_cache = WatchedCache()
    return _watched_cache


def mark_watched_from_playback(media_id, season='', episode='', video_type='episode', trakt_id='', tmdb_id='', tvdb_id='', imdb_id='', title=''):
    """Mark an item as watched after playback completes.
    This function is called from the service when playback ends.
    It stores multiple metadata IDs to ensure watched status is preserved
    even if Trakt fails to mark the item as watched.
    """
    try:
        cache = get_watched_cache()
        cache.mark_watched(video_type, media_id, title, season, episode, trakt_id, tmdb_id, tvdb_id, imdb_id)
        logger.log('Marked as watched from playback: %s (trakt=%s, tmdb=%s, tvdb=%s, imdb=%s)' % (media_id, trakt_id, tmdb_id, tvdb_id, imdb_id), log_utils.LOGNOTICE)
    except Exception as e:
        logger.log('Failed to mark as watched from playback: %s' % str(e), log_utils.LOGERROR)
