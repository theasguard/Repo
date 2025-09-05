"""
TMDB Episode Group remapper for Asguard playback

Purpose
- When TMDB Episode Groups (cours/different orders) are used to drive scraping, the incoming
  season/episode may reflect the group order rather than the actual TV season/episode. This helper
  maps the group order to the actual season/episode using TMDB group definitions, so the rest of 
  playback (Trakt metadata, subtitles, images, bookmarks) can use canonical numbering.

Usage
    from asguard_lib.group_remap import remap_via_tmdb_groups
    mapped = remap_via_tmdb_groups(trakt_id, season, episode, video_type)
    if mapped:
        season, episode = mapped  # use remapped values for the remainder of playback

Notes
- This only converts TMDB group ordering to actual season/episode. If Trakt collapses multiple
  cours into a single season (common for anime), use group_mapper.map_trakt_by_airdate or the
  airdate-based remap block in play_source to convert to Trakt numbering.
- This utility performs no network remap when video_type is not Episode or when TMDB groups are
  absent for the show; it returns None in those cases.
"""
from __future__ import annotations

from typing import Optional, Tuple

import kodi
import log_utils

from asguard_lib.trakt_api import Trakt_API
from asguard_lib import tmdb_api
from asguard_lib.group_mapper import map_group_to_actual
from asguard_lib.constants import VIDEO_TYPES

logger = log_utils.Logger.get_logger()


def _get_trakt_api() -> Optional[Trakt_API]:
    try:
        token = kodi.get_setting('trakt_oauth_token')
        if not token:
            logger.log('Group remap: No Trakt token configured', log_utils.LOGDEBUG)
            return None
        use_https = kodi.get_setting('use_https') == 'true'
        try:
            list_size = int(kodi.get_setting('list_size') or 30)
        except Exception:
            list_size = 30
        try:
            trakt_timeout = int(kodi.get_setting('trakt_timeout') or 20)
        except Exception:
            trakt_timeout = 20
        trakt_offline = kodi.get_setting('trakt_offline') == 'true'
        return Trakt_API(token, use_https, list_size, trakt_timeout, trakt_offline)
    except Exception as e:
        logger.log('Group remap: Failed to create Trakt API: %s' % e, log_utils.LOGDEBUG)
        return None


def remap_via_tmdb_groups(trakt_id: str, season: str | int, episode: str | int, video_type) -> Optional[Tuple[str, str]]:
    """
    Map a TMDB Episode Group (group season/order) to the actual TV season/episode.

    Args:
        trakt_id: Trakt show id
        season: incoming season (group season in Episode Groups context)
        episode: incoming episode (group order + 1 in Episode Groups context)
        video_type: should equal VIDEO_TYPES.EPISODE for remapping to run

    Returns:
        (season, episode) as strings if remapped, else None.
    """
    try:
        # Only apply to episodes
        if not (video_type == VIDEO_TYPES.EPISODE or str(video_type).lower() == 'episode'):
            return None

        api = _get_trakt_api()
        if not api:
            return None

        # Fetch show metadata from Trakt to retrieve TMDB id
        show_meta = api.get_show_details(trakt_id) or {}
        ids = show_meta.get('ids') or {}
        tmdb_id = ids.get('tmdb')
        tvdb_id = ids.get('tvdb')  # kept here for reference/logging if needed
        logger.log('Group remap: Show ids: tmdb=%s tvdb=%s trakt=%s' % (tmdb_id, tvdb_id, trakt_id), log_utils.LOGDEBUG)
        if not tmdb_id:
            return None

        # Retrieve Episode Groups for the show
        groups = tmdb_api.get_tv_episode_groups(tmdb_id)
        logger.log('TMDB Episode Groups (remap): %s' % groups, log_utils.LOGDEBUG)
        if not groups:
            logger.log('Group remap: No TMDB episode groups found', log_utils.LOGDEBUG)
            return None

        # Prioritize group types (type 6 often indicates original/primary ordering)
        valid_groups = sorted(groups, key=lambda g: 0 if g.get('type') == 6 else g.get('type', 999))

        # Try mapping against the first available groups in priority order
        for g in valid_groups:
            group_id = g.get('id')
            if not group_id:
                continue
            try:
                mapped = map_group_to_actual(group_id, season, episode)
            except Exception as e:
                logger.log('Group remap: map_group_to_actual failed for %s: %s' % (group_id, e), log_utils.LOGDEBUG)
                mapped = None

            logger.log('Group remap: mapped via group %s -> %s' % (group_id, mapped), log_utils.LOGDEBUG)
            if mapped:
                # Return as strings to align with most caller expectations
                return str(mapped[0]), str(mapped[1])

        return None

    except Exception as e:
        logger.log('Group remap: remap_via_tmdb_groups failed: %s' % e, log_utils.LOGDEBUG)
        return None


__all__ = ['remap_via_tmdb_groups']
