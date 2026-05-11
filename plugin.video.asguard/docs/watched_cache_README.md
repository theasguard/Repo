# Asguard Watched Cache Integration Guide

## Overview
The `watched_cache.py` module provides a local watched status cache system for the Asguard Kodi plugin. This cache can serve as a fallback when the Trakt API or Trakt application fails to mark items as watched.

## Main Features

### WatchedCache Class
Provides the core class for managing local watched status, including the following methods:

- `mark_watched(video_type, trakt_id, title='', season='', episode='')`: Mark a video as watched
- `mark_unwatched(video_type, trakt_id, season='', episode='')`: Mark a video as unwatched
- `is_watched(video_type, trakt_id, season='', episode='')`: Check whether a video has been watched
- `get_watched_movies()`: Get all watched movies
- `get_watched_episodes()`: Get all watched episodes
- `get_next_episodes()`: Get the last watched episode for each TV show
- `get_watched_count(video_type, trakt_id)`: Get the number of watched episodes for a TV show
- `clear_all()`: Clear all watched statuses

### Global Functions
- `get_watched_cache()`: Get the global WatchedCache instance
- `mark_watched_from_playback(trakt_id, season='', episode='', video_type='episode')`: Mark as watched when playback ends

## Integration Steps

### 1. Integrate into `service.py`

Call `watched_cache` when playback ends:

```python
from asguard_lib.watched_cache import mark_watched_from_playback

def onPlayBackEnded(self):
    logger.log('Service: Playback completed', log_utils.LOGNOTICE)

    # Check whether playback progress reaches the watched threshold (e.g. 90%)
    percent_played = int((self._lastPos / self._totalTime) * 100)
    if percent_played >= 90:
        # Mark as locally watched
        mark_watched_from_playback(
            trakt_id=self.trakt_id,
            season=self.season,
            episode=self.episode,
            video_type='episode' if self.season else 'movie'
        )

    self.onPlayBackStopped()
```

### 2. Integrate into `default.py`

Check watched status when displaying lists:

```python
from asguard_lib.watched_cache import get_watched_cache

def make_episode_item(show, episode, **kwargs):
    cache = get_watched_cache()
    trakt_id = show.get('ids', {}).get('trakt')

    # Check local watched status
    is_watched = cache.is_watched('episode', trakt_id, episode.get('season'), episode.get('number'))

    # Set play count and overlay icon
    playcount = 1 if is_watched else 0
    overlay = 5 if is_watched else 4

    # Use these values when creating the list item
    ...
```

### 3. Add Menu Items

Add mark watched/unwatched options to the context menu:

```python
from asguard_lib.watched_cache import get_watched_cache

def add_context_menu_items(item, video_type, trakt_id, season='', episode=''):
    cache = get_watched_cache()
    is_watched = cache.is_watched(video_type, trakt_id, season, episode)

    if is_watched:
        label = i18n('mark_as_unwatched')
        action = lambda: cache.mark_unwatched(video_type, trakt_id, season, episode)
    else:
        label = i18n('mark_as_watched')
        action = lambda: cache.mark_watched(video_type, trakt_id, '', season, episode)

    item.addContextMenuItems([(label, action)])
```

## Database Table Structure

`watched_cache` creates the following table in `asguard_cache.db`:

```sql
CREATE TABLE IF NOT EXISTS watched_status (
    db_type TEXT NOT NULL,      -- 'movie' or 'episode'
    media_id TEXT NOT NULL,     -- Trakt ID
    title TEXT,                 -- Title
    season TEXT NOT NULL,       -- Season number (empty string for movies)
    episode TEXT NOT NULL,      -- Episode number (empty string for movies)
    last_played TEXT NOT NULL,  -- Last playback time
    PRIMARY KEY(db_type, media_id, season, episode)
)
```

## Use Cases

1. **When the Trakt API fails**: If the Trakt API is unavailable or fails, the local cache ensures watched status is still recorded
2. **When the Trakt app sync is delayed**: The local cache provides immediate feedback while the Trakt application sync is delayed
3. **Offline mode**: In offline mode, the local cache allows users to track watched status
4. **Fast access**: The local cache provides faster access than a remote API

## Notes

1. `watched_cache` uses the same connection mechanism as Asguard’s existing database
2. All operations include error handling and logging
3. The local cache complements Trakt rather than replacing it
4. The playback progress threshold for marking as watched can be adjusted as needed (default is 90%)

## Troubleshooting

If you encounter issues, please check:
1. Make sure the module is imported correctly
2. Check Kodi logs for error messages
3. Verify database file permissions
4. Ensure the correct `video_type` is used (`'movie'` or `'episode'`)