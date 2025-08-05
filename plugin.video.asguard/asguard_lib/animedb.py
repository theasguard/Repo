import sqlite3 as db
import threading
import os
import kodi

def __enum(**enums):
    return type('Enum', (), enums)

DB_TYPES = __enum(MYSQL='mysql', SQLITE='sqlite')

class AnimeDatabase:
    def __init__(self, db_path=None):
        self.db_path = os.path.join(os.path.expanduser('~'), 'tmdb_cache.db') if db_path is None else db_path
        self.db_type = DB_TYPES.SQLITE
        self.db = None
        self.lock = threading.Lock()

    def _dict_factory(self, cursor, row):
        d = {}
        for idx, col in enumerate(cursor.description):
            d[col[0]] = row[idx]
        return d

    def get_anime_id(self, trakt_id, db_query):
        self.lock.acquire()
        try:
            conn = db.connect(self.db_path, timeout=60.0)
            conn.row_factory = self._dict_factory
            conn.execute("PRAGMA FOREIGN_KEYS = 1")
            cursor = conn.cursor()
            mapping = None
            if trakt_id:
                cursor.execute(db_query, (trakt_id,))
                mapping = cursor.fetchone()
                cursor.close()
        finally:
            self.lock.release()
        return mapping

    def get_thetvdb_id(self, trakt_id):
        db_query = 'SELECT thetvdb_id FROM anime WHERE trakt_id = ?'
        mapping = self.get_anime_id(trakt_id, db_query)
        return mapping['thetvdb_id'] if mapping else None

    def get_themoviedb_id(self, trakt_id):
        db_query = 'SELECT themoviedb_id FROM anime WHERE trakt_id = ?'
        mapping = self.get_anime_id(trakt_id, db_query)
        return mapping['themoviedb_id'] if mapping else None

    def get_imdb_id(self, trakt_id):
        db_query = 'SELECT imdb_id FROM anime WHERE trakt_id = ?'
        mapping = self.get_anime_id(trakt_id, db_query)
        return mapping['imdb_id'] if mapping else None

    def get_anilist_id(self, trakt_id):
        db_query = 'SELECT anilist_id FROM anime WHERE trakt_id = ?'
        mapping = self.get_anime_id(trakt_id, db_query)
        return mapping['anilist_id'] if mapping else None
    
    def get_anidb_id(self, tmdb_id):
        db_query = 'SELECT anidb_id FROM anime WHERE themoviedb_id = ?'
        mapping = self.get_anime_id(tmdb_id, db_query)
        return mapping['anidb_id'] if mapping else None

# Example usage
# if __name__ == "__main__":
#     db_path = 'path_to_your_database.db'
#     anime_db = AnimeDatabase(db_path)
#     anilist_id = 12345  # Example AniList ID

#     thetvdb_id = anime_db.get_thetvdb_id(anilist_id)
#     themoviedb_id = anime_db.get_themoviedb_id(anilist_id)
#     imdb_id = anime_db.get_imdb_id(anilist_id)
#     trakt_id = anime_db.get_trakt_id(anilist_id)

#     print(f"TheTVDB ID: {thetvdb_id}")
#     print(f"TheMovieDB ID: {themoviedb_id}")
#     print(f"IMDB ID: {imdb_id}")
#     print(f"Trakt ID: {trakt_id}")