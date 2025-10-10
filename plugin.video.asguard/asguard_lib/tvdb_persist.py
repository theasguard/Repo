"""
Asguard Addon - TVDB ID persistence helper

This module provides a tiny, opt-in helper to enrich a show's ids with a TVDB ID
and optionally persist it in the database so it survives normal cache expiry.

Usage (example within make_item):

    from asguard_lib import tvdb_persist

    # Enrich show['ids']['tvdb'] if possible and optionally persist when enabled
    tvdb_id = tvdb_persist.enrich_tvdb_id(show, tmdb_api, trakt_api=trakt_api)

    # Now proceed to build artwork, etc.

Behavior:
- If setting 'persist_tvdb_ids' is enabled, the helper reads/writes a per-show
  mapping in db_info using key: 'tvdb_map_{trakt_id}'
- If the mapping exists, it is used immediately and no network call is made
- If mapping is missing, it will try TMDB external_ids (if tmdb is present)
- If still missing and a Trakt client is provided, it will try one Trakt detail lookup
- If a tvdb_id is found and the setting is enabled, it will be persisted for next time

This is intentionally minimal and defensive. It mutates show['ids'] in-place when found.
"""
from typing import Optional, Dict, Any

import kodi
import log_utils
from asguard_lib.db_utils import DB_Connection

logger = log_utils.Logger.get_logger(__name__)

_PERSIST_SETTING = 'persist_tvdb_ids'  # boolean toggle in addon settings
_DB_KEY_TEMPLATE = 'tvdb_map_{trakt_id}'


def _persist_enabled() -> bool:
    try:
        return kodi.get_setting(_PERSIST_SETTING) == 'true'
    except Exception:
        return False


def _db_key(trakt_id: Any) -> str:
    return _DB_KEY_TEMPLATE.format(trakt_id=str(trakt_id))


def _coerce_int(value: Any) -> Optional[int]:
    if value in (None, '', 'None'):
        return None
    try:
        return int(value)
    except Exception:
        # Some APIs may return non-int-like values; just return as-is in that case
        try:
            return int(float(value))
        except Exception:
            return None


def _get_persisted(trakt_id: Any) -> Optional[int]:
    try:
        db = DB_Connection()
        val = db.get_setting(_db_key(trakt_id))
        return _coerce_int(val)
    except Exception as e:
        logger.log(f'TVDB persist: read error for {trakt_id}: {e}', log_utils.LOGDEBUG)
        return None


def _set_persisted(trakt_id: Any, tvdb_id: int) -> None:
    try:
        db = DB_Connection()
        db.set_setting(_db_key(trakt_id), str(tvdb_id))
        logger.log(f'TVDB persist: stored mapping trakt={trakt_id} -> tvdb={tvdb_id}', log_utils.LOGDEBUG)
    except Exception as e:
        logger.log(f'TVDB persist: write error for {trakt_id}: {e}', log_utils.LOGDEBUG)


def _fetch_tvdb_from_tmdb(tmdb_api, tmdb_id: Any) -> Optional[int]:
    """Try to get tvdb_id from TMDB external_ids via a single-ID batch.
    Returns an int or None. Safe for missing/unexpected shapes.
    """
    if not tmdb_id:
        return None
    try:
        batch = tmdb_api.get_tv_details_batch(tmdb_id, overview=False) or {}
        details = batch.get(str(tmdb_id)) or batch.get(tmdb_id) or {}
        ext_ids = details.get('external_ids') or {}
        return _coerce_int(ext_ids.get('tvdb_id'))
    except Exception as e:
        logger.log(f'TVDB persist: TMDB fetch error for {tmdb_id}: {e}', log_utils.LOGDEBUG)
        return None


def _fetch_tvdb_from_trakt(trakt_api, trakt_id: Any) -> Optional[int]:
    """Last-resort lookup from Trakt show details. Returns int or None."""
    if not trakt_api or not trakt_id:
        return None
    try:
        details = trakt_api.get_show_details(trakt_id) or {}
        ids = details.get('ids') or {}
        return _coerce_int(ids.get('tvdb'))
    except Exception as e:
        logger.log(f'TVDB persist: Trakt fetch error for {trakt_id}: {e}', log_utils.LOGDEBUG)
        return None


def enrich_tvdb_id(show: Dict[str, Any], tmdb_api, trakt_api=None) -> Optional[int]:
    """Ensure show['ids']['tvdb'] is populated when possible, optionally persisting it.

    - If persist setting is enabled and a stored mapping exists for this trakt_id,
      it will be applied immediately without network calls.
    - Otherwise, try TMDB external_ids when tmdb is present.
    - If still missing and trakt_api provided, try a single Trakt details call.
    - If found and persist setting is enabled, store it for next time.

    Returns the tvdb_id found (int) or None. Mutates show['ids'] in place.
    """
    try:
        ids = show.get('ids') or {}
    except Exception:
        return None

    # Already present
    current = ids.get('tvdb')
    co_current = _coerce_int(current)
    if co_current:
        return co_current

    # Persisted mapping by trakt
    trakt_id = ids.get('trakt')
    if _persist_enabled() and trakt_id:
        stored = _get_persisted(trakt_id)
        if stored:
            ids['tvdb'] = stored
            show['ids'] = ids
            return stored

    # Try TMDB external_ids
    tmdb_id = ids.get('tmdb')
    tvdb_id = _fetch_tvdb_from_tmdb(tmdb_api, tmdb_id)

    # Fallback: Trakt details (optional)
    if not tvdb_id:
        return None

    # Persist & apply if found
    if tvdb_id:
        ids['tvdb'] = tvdb_id
        show['ids'] = ids
        if _persist_enabled() and trakt_id:
            _set_persisted(trakt_id, tvdb_id)
        return tvdb_id

    return None


def clear_persisted_tvdb(trakt_id: Any) -> None:
    """Clear a persisted mapping for a single show (no-op if none)."""
    try:
        db = DB_Connection()
        db.set_setting(_db_key(trakt_id), '')
    except Exception as e:
        logger.log(f'TVDB persist: clear error for {trakt_id}: {e}', log_utils.LOGDEBUG)
