"""
Sources Progress Window for Asguard (SALTS fork)

This module implements a reusable WindowXMLDialog for showing source scraping progress,
similar in spirit to the POV addon's sources window. It does not modify existing code;
import and use it where you prefer.

Expected XML (create next at resources/skins/Default/1080p/sources_progress.xml):
- Window ID and type don't strictly matter; suggested is a WindowDialog
- Controls (IDs):
  * 100: Header/Title label
  * 110: Line 1 (primary status)
  * 120: Line 2 (secondary status)
  * 130: Line 3 (tertiary status / remaining)
  * 140: Line 4 (optional details)
  * 200: Progress control
  * 210: Counts label (e.g., Found: X | Total: Y)
  * 220: Current scraper label
  * 230: Elapsed time label
  * 240: Quality label (e.g., Best: 1080p | 4K:2 1080p:12 720p:5)
  * 300: Cancel button

Minimal example usage:

    from asguard_lib.windows.sources_progress import SourcesProgressDialog, make_progress_title

    # Build a title similar to POV (Episode or Movie)
    title_test = make_progress_title(video_type='Episode', title='WIND BREAKER', year='2025', season='02', episode='04')

    dlg = SourcesProgressDialog('sources_progress.xml', xbmcaddon.Addon().getAddonInfo('path'), 'Default', '1080p',
                                header=title)
    dlg.doModal()  # The dialog will init with 0%
    # Update as scraping proceeds
    dlg.set_progress(12)
    dlg.set_line1('Requesting sources…')
    dlg.set_current_scraper('OpenScraper')
    dlg.set_counts(found=4, total=32, remaining_names=['OpenScraper2', 'FilePursuit'])
    # Close when finished
    dlg.close()

API:
- set_header(text)
- set_line1(text), set_line2(text), set_line3(text), set_line4(text)
- set_progress(percent)  # 0..100
- set_counts(found: int, total: int, remaining_names: Optional[List[str]] = None)
- set_current_scraper(name: str)
- set_elapsed(seconds: float)
- is_canceled() -> bool

Helper:
- make_progress_title(video_type, title, year='', season='', episode='') -> str
  Constructs a compact title like: "Episode: WIND BREAKER (2025) - S02E04"
"""
from __future__ import annotations

import time
from typing import Iterable, Optional, Sequence

import xbmc
import xbmcgui
import xbmcaddon


def _fmt_two(v) -> str:
    try:
        return f"{int(v):02d}"
    except Exception:
        try:
            return f"{int(float(v)):02d}"
        except Exception:
            return str(v)


def make_progress_title(video_type: str, video):
    video_type = (video_type or '').capitalize()
    base = f"{video_type}: {video.title}"
    if video.year:
        base += f" ({video.year})"
    if (video_type.lower() == 'episode') and video.season != '' and video.episode != '':
        base += f" - S{_fmt_two(video.season)}E{_fmt_two(video.episode)}"
    return base


class SourcesProgressDialog(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        super().__init__()
        # Optional startup values
        self._header = kwargs.get('header') or 'Getting sources…'
        self._line1 = kwargs.get('line1') or ''
        self._line2 = kwargs.get('line2') or ''
        self._line3 = kwargs.get('line3') or ''
        self._line4 = kwargs.get('line4') or ''
        self._progress = 0
        self._counts = (0, 0)  # found, total
        self._remaining = []   # type: list[str]
        self._scraper = ''
        self._quality = ''
        self._start_ts = time.time()
        self._canceled = False

    # --- Window lifecycle ---
    def onInit(self):
        self._apply_all()

    def onAction(self, action):
        # Close/cancel on Back, Close, or Stop
        ACTION_PREVIOUS_MENU = 10
        ACTION_NAV_BACK = 92
        ACTION_STOP = 13
        if action.getId() in (ACTION_PREVIOUS_MENU, ACTION_NAV_BACK, ACTION_STOP):
            self._canceled = True
            self.close()

    def onClick(self, control_id):
        if control_id == 300:
            self._canceled = True
            self.close()

    # --- Public API ---
    def is_canceled(self) -> bool:
        return self._canceled

    def set_header(self, text: str):
        self._header = text or ''
        self._set_label(100, self._header)

    def set_line1(self, text: str):
        self._line1 = text or ''
        self._set_label(110, self._line1)

    def set_line2(self, text: str):
        self._line2 = text or ''
        self._set_label(120, self._line2)

    def set_line3(self, text: str):
        self._line3 = text or ''
        self._set_label(130, self._line3)

    def set_line4(self, text: str):
        self._line4 = text or ''
        self._set_label(140, self._line4)

    def set_progress(self, percent: float):
        try:
            p = max(0, min(100, int(percent)))
        except Exception:
            p = 0
        self._progress = p
        self._set_progress(200, p)
        # Also keep elapsed refreshed
        self._update_elapsed()

    def set_counts(self, found: int, total: int, remaining_names: Optional[Sequence[str]] = None):
        try:
            f, t = int(found), int(total)
        except Exception:
            f, t = 0, 0
        self._counts = (f, t)
        self._remaining = list(remaining_names or [])
        self._set_label(210, f"Found: {f} | Total: {t}")
        if self._remaining:
            rem = ', '.join(map(str, self._remaining[:6]))
            if len(self._remaining) > 6:
                rem += f" (+{len(self._remaining) - 6})"
            self._set_label(130, f"Remaining: {rem}")

    def set_current_scraper(self, name: str):
        self._scraper = name or ''
        self._set_label(220, f"Scraper: {self._scraper}")

    def set_elapsed(self, seconds: float):
        self._set_label(230, f"Elapsed: {self._fmt_duration(seconds)}")

    def set_quality(self, text: str):
        """
        Set a quality summary line, e.g.:
        "Best: 1080p | 4K:2 1080p:12 720p:5 HD:8 SD:3"
        """
        self._quality = text or ''
        self._set_label(240, self._quality)

    def set_quality_counts(self, best: Optional[str], counts: Optional[dict] = None):
        """
        Convenience to build a quality summary line from a dict.
        counts example: { '4K': 2, '1080p': 12, '720p': 5 }
        """
        parts = []
        if counts:
            parts = [f"{k}:{counts[k]}" for k in counts if counts.get(k)]
        prefix = f"Best: {best}" if best else 'Quality:'
        summary = prefix
        if parts:
            summary += ' | ' + ' '.join(parts)
        self.set_quality(summary)

    # --- Helpers ---
    def _apply_all(self):
        self._set_label(100, self._header)
        self._set_label(110, self._line1)
        self._set_label(120, self._line2)
        self._set_label(130, self._line3)
        self._set_label(140, self._line4)
        self._set_progress(200, self._progress)
        f, t = self._counts
        self._set_label(210, f"Found: {f} | Total: {t}")
        if self._scraper:
            self._set_label(220, f"Scraper: {self._scraper}")
        if self._quality:
            self._set_label(240, self._quality)
        self._update_elapsed()

    def _update_elapsed(self):
        self._set_label(230, f"Elapsed: {self._fmt_duration(time.time() - self._start_ts)}")

    def _set_label(self, control_id: int, text: str):
        try:
            ctrl = self.getControl(control_id)
            if ctrl:
                ctrl.setLabel(text or '')
        except Exception:
            pass

    def _set_progress(self, control_id: int, percent: int):
        try:
            ctrl = self.getControl(control_id)
            if ctrl:
                ctrl.setPercent(percent)
        except Exception:
            pass

    @staticmethod
    def _fmt_duration(seconds: float) -> str:
        try:
            seconds = int(max(0, seconds))
            m, s = divmod(seconds, 60)
            h, m = divmod(m, 60)
            if h > 0:
                return f"{h:d}h {m:02d}m {s:02d}s"
            return f"{m:d}m {s:02d}s"
        except Exception:
            return "0m 00s"
