"""
Sources Progress Window for Asguard (SALTS fork)

This module implements a reusable WindowXMLDialog for showing source scraping progress,
similar in spirit to the POV addon's sources window. It does not use Window(10000);
instead, it relies solely on the dialog's own properties.

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

    from asguard_lib.windows.sources_progress_fixed import SourcesProgressDialog, make_progress_title

    # Build a title similar to POV (Episode or Movie)
    video = ScraperVideo('episode', 'WIND BREAKER', '2025', '', '02', '04', '', '')
    title_test = make_progress_title('episode', video)

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
- make_progress_title(video_type: str, video: ScraperVideo) -> str
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
        try:
            super(SourcesProgressDialog, self).__init__(*args, **kwargs)
        except:
            xbmcgui.WindowXMLDialog.__init__(self)
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
        self._quality = 'Quality: | 4K:0 1080p:0 720p:0 SD:0'
        self._start_ts = time.time()
        self._canceled = False
        self._fanart = ''
        # Window property prefix for communicating with XML
        self._prop_prefix = 'asguard.source_progress.'

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

    def doModal(self):
        try:
            super(SourcesProgressDialog, self).doModal()
        except:
            import traceback
            traceback.print_exc()

    # --- Public API ---
    def is_canceled(self) -> bool:
        return self._canceled

    def set_header(self, text: str):
        self._header = text or ''
        self.setProperty(self._prop_prefix + 'header', self._header)

    def set_line1(self, text: str):
        self._line1 = text or ''
        self.setProperty(self._prop_prefix + 'line1', self._line1)

    def set_line2(self, text: str):
        self._line2 = text or ''
        # Set notifier property for source colors
        self.setProperty(self._prop_prefix + 'notifier', self._line2)
        self.setProperty(self._prop_prefix + 'line2', self._line2)

    def set_line3(self, text: str):
        self._line3 = text or ''
        self.setProperty(self._prop_prefix + 'line3', self._line3)

    def set_line4(self, text: str):
        self._line4 = text or ''
        self.setProperty(self._prop_prefix + 'line4', self._line4)

    def set_progress(self, percent: float):
        try:
            p = max(0, min(100, int(percent)))
        except Exception:
            p = 0
        self._progress = p
        try:
            # Try to get the progress control and update it directly
            progress_control = self.getControl(200)
            if progress_control:
                progress_control.setPercent(p)
        except Exception:
            # Fallback to window property if control not found
            self.setProperty(self._prop_prefix + 'progress', str(p))
        self._update_elapsed()

    def set_counts(self, found: int, total: int, remaining_names: Optional[Sequence[str]] = None):
        try:
            f, t = int(found), int(total)
        except Exception:
            f, t = 0, 0
        self._counts = (f, t)
        self._remaining = list(remaining_names or [])
        self.setProperty(self._prop_prefix + 'counts', f"Found: {f} | Total: {t}")
        if self._remaining:
            rem = ', '.join(map(str, self._remaining[:6]))
            if len(self._remaining) > 6:
                rem += f" (+{len(self._remaining) - 6})"
            self.setProperty(self._prop_prefix + 'remaining', rem)

    def set_current_scraper(self, name: str):
        self._scraper = name or ''
        self.setProperty(self._prop_prefix + 'scraper', f"Scraper: {self._scraper}")

    def set_elapsed(self, seconds: float):
        elapsed_text = f"Elapsed: {self._fmt_duration(seconds)}"
        self.setProperty(self._prop_prefix + 'elapsed', elapsed_text)

    def set_quality(self, text: str):
        """
        Set a quality summary line, e.g.:
        "Best: 1080p | 4K:2 1080p:12 720p:5 HD:8 SD:3"
        """
        self._quality = text or ''
        self.setProperty(self._prop_prefix + 'quality', self._quality)

    def set_quality_counts(self, best: Optional[str], counts: Optional[dict] = None):
        """
        Convenience to build a quality summary line from a dict.
        counts example: { '4K': 2, '1080p': 12, '720p': 5 }
        """
        parts = []
        if counts:
            # Show all quality categories, even those with 0 values
            parts = [f"{k}:{counts.get(k, 0)}" for k in ['4K', '1080p', '720p', 'SD'] if k in counts]
        prefix = f"Best: {best}" if best else 'Quality:'
        summary = prefix
        if parts:
            summary += ' | ' + ' '.join(parts)
        self.set_quality(summary)

    def set_fanart(self, fanart_url: str):
        """
        Set the fanart background image for the dialog.
        """
        self._fanart = fanart_url or ''
        self.setProperty(self._prop_prefix + 'fanart', self._fanart)

    def set_fanart_from_trakt(self, trakt_id: str, video_type: str = 'movie', season: str = '', episode: str = ''):
        """
        Set the fanart background image for the dialog using trakt_id.
        This method works for both movies and TV shows.

        Args:
            trakt_id: The Trakt ID of the video
            video_type: 'movie' or 'tvshow' (default: 'movie')
            season: Season number for TV shows (optional)
            episode: Episode number for TV shows (optional)
        """
        try:
            from asguard_lib import image_scraper
            video_ids = {'trakt': trakt_id}
            art = image_scraper.get_images(video_type, video_ids, season, episode)
            fanart_url = art.get('fanart', '')
            self.set_fanart(fanart_url)
        except Exception as e:
            import xbmc
            xbmc.log(f'Error setting fanart from trakt_id: {e}', xbmc.LOGERROR)

    # --- Helpers ---
    def _apply_all(self):
        # Set properties on dialog only (no Window(10000))
        self.setProperty(self._prop_prefix + 'header', self._header)
        self.setProperty(self._prop_prefix + 'line1', self._line1)
        self.setProperty(self._prop_prefix + 'line2', self._line2)
        self.setProperty(self._prop_prefix + 'notifier', self._line2)  # For source colors
        self.setProperty(self._prop_prefix + 'line3', self._line3)
        self.setProperty(self._prop_prefix + 'line4', self._line4)
        self.setProperty(self._prop_prefix + 'progress', str(self._progress))
        f, t = self._counts
        self.setProperty(self._prop_prefix + 'counts', f"Found: {f} | Total: {t}")
        if self._remaining:
            rem = ', '.join(map(str, self._remaining[:6]))
            if len(self._remaining) > 6:
                rem += f" (+{len(self._remaining) - 6})"
            self.setProperty(self._prop_prefix + 'remaining', rem)
        self.setProperty(self._prop_prefix + 'fanart', self._fanart)
        if self._scraper:
            self.setProperty(self._prop_prefix + 'scraper', f"Scraper: {self._scraper}")
        if self._quality:
            self.setProperty(self._prop_prefix + 'quality', self._quality)
        self._update_elapsed()

    def _update_elapsed(self):
        elapsed_text = f"Elapsed: {self._fmt_duration(time.time() - self._start_ts)}"
        self.setProperty(self._prop_prefix + 'elapsed', elapsed_text)



    def close(self):
        """Override close to clear properties"""

        # Clear all progress dialog properties
        for prop in ['header', 'line1', 'line2', 'line3', 'line4', 'progress', 
                      'counts', 'remaining', 'scraper', 'quality', 'elapsed', 'fanart', 'notifier']:
            self.clearProperty(self._prop_prefix + prop)

        super(SourcesProgressDialog, self).close()

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