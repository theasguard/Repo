"""
Group episode mapping utilities for Asguard (SALTS fork)

What this provides
- TMDB episode group mapper: map (group season, group ep order) -> (actual season, actual episode)
- TVDB absolute-number mapper: map absolute episode number -> (season, episode)

Why this exists
Many shows (especially anime) use multiple numbering schemes (absolute, DVD, digital, production). 
Scrapers often match best on a group/absolute order, while metadata, Trakt, bookmarks and art expect
canonical season/episode. These helpers let you keep group numbering for scraping, but resolve the
actual season/episode for playback, tracking and UI.

How to use (typical integration)
1) For TMDB Episode Groups listings, keep the group numbers for the scrapers but compute the
   effective season/episode just before playback:

    from asguard_lib.group_mapper import map_group_to_actual

    mapped = map_group_to_actual(group_id, group_season, group_episode)
    if mapped:
        eff_season, eff_episode = mapped
    else:
        eff_season, eff_episode = season, episode  # fallback

    # Use eff_* when calling play_source(...) and for Trakt/bookmarks/art resolution.

2) For globally absolute-ordered shows via TVDB, translate absolute -> (season, episode) once:

    from asguard_lib.group_mapper import map_absolute_to_actual_tvdb

    mapped = map_absolute_to_actual_tvdb(tvdb_id, abs_episode_number)
    if mapped:
        eff_season, eff_episode = mapped

Notes
- These mappers are read-only helpers with internal caching (1 hour TTL).
- They do not mutate your input queries. Continue to send group/absolute values to scrapers,
  but prefer the mapped eff_season/eff_episode when fetching metadata, setting window properties,
  bookmarks, subtitles, and scrobbling.
- Safe to call repeatedly; internal caches avoid excessive API calls.
"""
from __future__ import annotations

import time
from typing import Dict, Tuple, Optional

import log_utils
import kodi

# Import TMDB and Trakt API wrappers from Asguard library
# default.py imports it as: from asguard_lib import tmdb_api
# so we follow the same convention to use the shared request/keys/caching behavior
from asguard_lib import tmdb_api
from asguard_lib.trakt_api import Trakt_API

logger = log_utils.Logger.get_logger()

# ------------------------
# TMDB Episode Group Mapper
# ------------------------

# Cache: group_id -> { 'map': {(group_season, group_ep): (actual_season, actual_ep)}, 'ts': epoch_seconds }
_GROUP_MAPPER_CACHE: Dict[str, Dict[str, object]] = {}
_GROUP_MAPPER_TTL: int = 3600  # seconds


def _build_group_mapper(group_id: str) -> Dict[Tuple[int, int], Tuple[int, int]]:
    """
    Build a mapping for a TMDB episode group.

    Key: (group_season_number, group_episode_order+1)
    Val: (actual_season_number, actual_episode_number)

    The TMDB episode group details endpoint provides, per group:
      - groups: [ { order: <int>, episodes: [ { order: <int>, season_number: <int>, episode_number: <int>, ... } ] } ]

    We normalize mapping keys to 1-based group episode numbers (order+1), and group_season derived from group.order.
    """
    mapping: Dict[Tuple[int, int], Tuple[int, int]] = {}
    try:
        details = tmdb_api.get_episode_group_details(group_id)
        if not details or 'groups' not in details:
            logger.log('Group mapper: no details/groups for %s' % group_id, log_utils.LOGDEBUG)
            return mapping

        for s_idx, season_group in enumerate(details.get('groups', []) or []):
            try:
                group_season_num = season_group.get('order', s_idx)
                # group season number may be zero-based in TMDB, normalize to int as-is
                group_season_num = int(group_season_num)
            except Exception:
                group_season_num = int(s_idx)

            episodes = season_group.get('episodes', []) or []
            for ep in episodes:
                try:
                    group_ep = int(ep.get('order', 0)) + 1
                except Exception:
                    group_ep = 1

                try:
                    actual_s = int(ep.get('season_number') or 0)
                except Exception:
                    actual_s = 0
                try:
                    actual_e = int(ep.get('episode_number') or 0)
                except Exception:
                    actual_e = 0

                if actual_s > 0 and actual_e > 0:
                    mapping[(group_season_num, group_ep)] = (actual_s, actual_e)

        logger.log('Group mapper: built for %s with %d entries' % (group_id, len(mapping)), log_utils.LOGDEBUG)
        return mapping
    except Exception as e:
        logger.log('Group mapper build failed for %s: %s' % (group_id, e), log_utils.LOGWARNING)
        return mapping


def _get_group_mapper(group_id: str) -> Dict[Tuple[int, int], Tuple[int, int]]:
    now = time.time()
    entry = _GROUP_MAPPER_CACHE.get(str(group_id))
    if not entry or (now - entry['ts'] > _GROUP_MAPPER_TTL):
        mapping = _build_group_mapper(group_id)
        _GROUP_MAPPER_CACHE[str(group_id)] = {'map': mapping, 'ts': now}
        return mapping
    return entry['map']  # type: ignore[return-value]


def map_group_to_actual(group_id: str, group_season: int | str, group_episode: int | str) -> Optional[Tuple[int, int]]:
    """
    Translate group ordering -> actual season/episode.

    Args:
        group_id: TMDB episode group id
        group_season: group "season" number (from group.order)
        group_episode: group episode order+1

    Returns:
        (season, episode) or None if no mapping was found.
    """
    try:
        gs = int(group_season)
        ge = int(group_episode)
        mapping = _get_group_mapper(group_id)
        result = mapping.get((gs, ge))
        if result:
            logger.log('Group mapper: %s/%s -> %s/%s' % (gs, ge, result[0], result[1]), log_utils.LOGDEBUG)
        else:
            logger.log('Group mapper: no match for %s/%s in group %s' % (gs, ge, group_id), log_utils.LOGDEBUG)
        return result
    except Exception as e:
        logger.log('Group map lookup failed (%s): %s' % (group_id, e), log_utils.LOGWARNING)
        return None


# -----------------------------
# TVDB Absolute-Number Mapper
# -----------------------------

# Cache: tvdb_id -> { 'map': { abs_no: (season, episode) }, 'ts': epoch_seconds }
_TVDB_ABS_CACHE: Dict[str, Dict[str, object]] = {}
_TVDB_ABS_TTL: int = 3600


def _build_tvdb_abs_mapper(tvdb_id: str) -> Dict[int, Tuple[int, int]]:
    """
    Build absolute-number mapping for a TVDB show.

    Key: absoluteNumber (int)
    Val: (airedSeason, airedEpisodeNumber)

    Iterates seasons (including 0 for specials) and indexes absoluteNumber where available.
    """
    mapping: Dict[int, Tuple[int, int]] = {}
    try:
        # Lazy import to avoid hard dependency when TVDB is unavailable
        try:
            from asguard_lib.tvdb_api.tvdb_api import TheTvDb  # type: ignore
        except Exception as e_imp:
            logger.log('TVDB abs mapper: tvdb_api unavailable: %s' % e_imp, log_utils.LOGWARNING)
            return mapping

        api = TheTvDb()

        # Iterate reasonably through seasons; stop after a few consecutive empty seasons
        empty_streak = 0
        for season_num in range(0, 101):  # include 0 (specials), up to 100 seasons safeguard
            try:
                episodes = api.get_episodes_by_season(tvdb_id, season_num) or []
            except Exception:
                episodes = []

            if not episodes:
                empty_streak += 1
                # break after a few empty seasons to avoid long loops
                if empty_streak >= 3 and season_num > 1:
                    break
                continue
            else:
                empty_streak = 0

            for ep in episodes:
                # TVDB payload keys vary; try both common forms
                abs_no = ep.get('absoluteNumber') if isinstance(ep, dict) else None
                if abs_no is None:
                    abs_no = ep.get('absolute_number') if isinstance(ep, dict) else None

                aired_ep = ep.get('airedEpisodeNumber') if isinstance(ep, dict) else None
                if aired_ep is None:
                    aired_ep = ep.get('aired_episode_number') if isinstance(ep, dict) else None

                try:
                    if abs_no is not None and aired_ep is not None:
                        abs_no_i = int(abs_no)
                        aired_ep_i = int(aired_ep)
                        mapping[abs_no_i] = (int(season_num), aired_ep_i)
                except Exception:
                    # ignore conversion issues for odd data
                    pass

        logger.log('TVDB abs mapper: built for %s with %d entries' % (tvdb_id, len(mapping)), log_utils.LOGDEBUG)
        return mapping

    except Exception as e:
        logger.log('TVDB abs mapper build failed for %s: %s' % (tvdb_id, e), log_utils.LOGWARNING)
        return mapping


def _get_tvdb_abs_mapper(tvdb_id: str) -> Dict[int, Tuple[int, int]]:
    now = time.time()
    key = str(tvdb_id)
    entry = _TVDB_ABS_CACHE.get(key)
    if not entry or (now - entry['ts'] > _TVDB_ABS_TTL):
        mapping = _build_tvdb_abs_mapper(tvdb_id)
        _TVDB_ABS_CACHE[key] = {'map': mapping, 'ts': now}
        return mapping
    return entry['map']  # type: ignore[return-value]


def map_absolute_to_actual_tvdb(tvdb_id: str, abs_episode_number: int | str) -> Optional[Tuple[int, int]]:
    """
    Translate TVDB absolute episode number -> (season, episode) using TVDB metadata.

    Returns None if TVDB is unavailable or mapping was not found.
    """
    try:
        abs_no = int(abs_episode_number)
        mapping = _get_tvdb_abs_mapper(tvdb_id)
        result = mapping.get(abs_no)
        if result:
            logger.log('TVDB abs mapper: %s -> %s/%s' % (abs_no, result[0], result[1]), log_utils.LOGDEBUG)
        else:
            logger.log('TVDB abs mapper: no match for abs=%s tvdb_id=%s' % (abs_no, tvdb_id), log_utils.LOGDEBUG)
        return result
    except Exception as e:
        logger.log('TVDB abs map lookup failed (%s): %s' % (tvdb_id, e), log_utils.LOGWARNING)
        return None


# -----------------------------
# Trakt-based Mappers (best-effort)
# -----------------------------

# Cache: (trakt_id, season) -> [episodes]
_TRAKT_SEASON_CACHE: Dict[Tuple[str, int], Dict[str, object]] = {}
_TRAKT_CACHE_TTL: int = 1800


def _get_trakt_api() -> Optional[Trakt_API]:
    try:
        token = kodi.get_setting('trakt_oauth_token')
        if not token:
            return None
        use_https = kodi.get_setting('use_https') == 'true'
        list_size = int(kodi.get_setting('list_size') or 30)
        trakt_timeout = int(kodi.get_setting('trakt_timeout') or 20)
        trakt_offline = kodi.get_setting('trakt_offline') == 'true'
        return Trakt_API(token, use_https, list_size, trakt_timeout, trakt_offline)
    except Exception:
        return None


def _get_trakt_season(trakt_id: str, season: int) -> list:
    now = time.time()
    key = (str(trakt_id), int(season))
    entry = _TRAKT_SEASON_CACHE.get(key)
    if entry and (now - entry['ts'] <= _TRAKT_CACHE_TTL):
        return entry['eps']  # type: ignore[return-value]

    api = _get_trakt_api()
    eps = []
    try:
        if api:
            eps = api.get_episodes(trakt_id, season) or []
    except Exception as e:
        logger.log('Trakt mapper: get_episodes failed for %s S%s: %s' % (trakt_id, season, e), log_utils.LOGDEBUG)
        eps = []

    _TRAKT_SEASON_CACHE[key] = {'eps': eps, 'ts': now}
    return eps


def map_trakt_by_airdate(trakt_id: str, air_date_iso: str) -> Optional[Tuple[int, int]]:
    """
    Map an ISO air date (YYYY-MM-DD) to (season, episode) using Trakt's season lists.
    Returns None if not found or Trakt is not configured/available.
    """
    api = _get_trakt_api()
    if not api or not air_date_iso:
        return None

    try:
        # Try looking through a reasonable season range (1..50) until a match is found.
        for season in range(0, 51):  # include 0 (specials)
            for ep in _get_trakt_season(trakt_id, season):
                try:
                    if ep.get('first_aired', '').split('T', 1)[0] == air_date_iso:
                        return (int(season), int(ep.get('number') or 0))
                except Exception:
                    continue
    except Exception as e:
        logger.log('Trakt mapper: map_by_airdate failed: %s' % e, log_utils.LOGDEBUG)
    return None


def map_trakt_by_absolute(trakt_id: str, abs_no: int) -> Optional[Tuple[int, int]]:
    """
    Best-effort absolute->(season, episode) using Trakt sequences.
    This assumes episodes are ordered by airdate across seasons and counts a running index.
    Not guaranteed for all shows; prefer TVDB absolute mapping when possible.
    """
    api = _get_trakt_api()
    if not api or not abs_no or abs_no <= 0:
        return None

    running = 0
    try:
        # Iterate seasons and accumulate counts until reaching the abs_no
        for season in range(0, 101):
            eps = _get_trakt_season(trakt_id, season)
            if not eps and season > 1:
                break
            for ep in eps:
                running += 1
                if running == abs_no:
                    return (int(season), int(ep.get('number') or 0))
    except Exception as e:
        logger.log('Trakt mapper: map_by_absolute failed: %s' % e, log_utils.LOGDEBUG)
    return None


# -----------------------------
# TMDB group -> Trakt numbering remappers
# -----------------------------

def _get_group_episode_airdate(group_id: str, group_season: int | str, group_episode: int | str) -> Optional[str]:
    """
    Resolve an episode's air date from a TMDB episode group, given group season/order.
    Returns YYYY-MM-DD or None.
    """
    try:
        details = tmdb_api.get_episode_group_details(group_id)
        if not details or 'groups' not in details:
            return None
        gs = int(group_season)
        ge = int(group_episode)
        for s_idx, g in enumerate(details.get('groups', []) or []):
            try:
                order = int(g.get('order', s_idx))
            except Exception:
                order = int(s_idx)
            if order != gs:
                continue
            for ep in g.get('episodes', []) or []:
                try:
                    ord_ep = int(ep.get('order', 0)) + 1
                except Exception:
                    ord_ep = 1
                if ord_ep == ge:
                    ad = ep.get('air_date') or ep.get('first_air_date')
                    if ad:
                        return ad.split('T', 1)[0]
                    return None
        return None
    except Exception as e:
        logger.log('Group mapper: _get_group_episode_airdate failed: %s' % e, log_utils.LOGDEBUG)
        return None


def map_group_to_trakt(trakt_id: str, group_id: str, group_season: int | str, group_episode: int | str, air_date_iso: Optional[str] = None) -> Optional[Tuple[int, int]]:
    """
    Map a TMDB episode group reference to Trakt numbering (season, episode).

    Strategy:
    - Use the provided air_date if available (best path) via Trakt airdate mapping.
    - Else, fetch the air_date from the group details and map via airdate.

    Returns:
      (trakt_season, trakt_episode) or None.
    """
    # Prefer explicit airdate
    if air_date_iso:
        res = map_trakt_by_airdate(trakt_id, air_date_iso)
        if res:
            return res

    # Derive airdate from group
    ad = _get_group_episode_airdate(group_id, group_season, group_episode)
    if ad:
        return map_trakt_by_airdate(trakt_id, ad)

    return None


def map_actual_to_trakt(trakt_id: str, actual_season: int | str, actual_episode: int | str, air_date_iso: Optional[str] = None, tvdb_id: Optional[str] = None) -> Optional[Tuple[int, int]]:
    """
    Map an actual (season, episode) to Trakt numbering using air dates.
    - If air_date is provided, map directly by airdate.
    - Else, if tvdb_id is provided, fetch episode from TVDB to obtain aired date and map.
    """
    if air_date_iso:
        res = map_trakt_by_airdate(trakt_id, air_date_iso)
        if res:
            return res

    if tvdb_id:
        try:
            from asguard_lib.tvdb_api.tvdb_api import TheTvDb  # type: ignore
            tvdb = TheTvDb()
            ep = tvdb.get_episode_by_number(tvdb_id, int(actual_season), int(actual_episode)) or {}
            ad = (ep.get('aired') or ep.get('firstAired') or ep.get('first_aired'))
            if ad:
                return map_trakt_by_airdate(trakt_id, ad.split('T', 1)[0])
        except Exception as e:
            logger.log('Trakt mapper: TVDB lookup failed: %s' % e, log_utils.LOGDEBUG)

    return None


__all__ = [
    'map_group_to_actual',
    'map_absolute_to_actual_tvdb',
    'map_trakt_by_airdate',
    'map_trakt_by_absolute',
    'map_group_to_trakt',
    'map_actual_to_trakt',
]
