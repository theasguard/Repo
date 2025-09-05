"""
    Asguard Addon
    Copyright (C) 2025

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""

import re
import urllib.parse
from bs4 import BeautifulSoup
import log_utils
from asguard_lib import scraper_utils
from asguard_lib.constants import VIDEO_TYPES
from asguard_lib.utils2 import i18n
import kodi
from . import scraper

try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)

logger = log_utils.Logger.get_logger()

BASE_URL = 'https://www.limetorrents.fun'
SEARCH_URL = '/search/all/%s/'


class Scraper(scraper.Scraper):
    base_url = BASE_URL
    debrid_resolvers = resolveurl

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        try:
            self.base_url = kodi.get_setting('%s-base_url' % (self.get_name())) or BASE_URL
        except Exception:
            self.base_url = BASE_URL

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE, VIDEO_TYPES.SEASON, VIDEO_TYPES.MOVIE])

    @classmethod
    def get_name(cls):
        return 'LimeTorrents'

    def resolve_link(self, link):
        return link

    def parse_number(self, text):
        if text is None:
            return 0
        s = str(text).strip().upper()
        try:
            if s.endswith('K'):
                return int(float(s[:-1].replace(',', '')) * 1000)
            return int(s.replace(',', ''))
        except Exception:
            try:
                return int(re.sub(r'\D+', '', s) or 0)
            except Exception:
                return 0

    def _slug(self, q):
        # Convert query to a URL path-safe slug the site accepts in /search/all/<slug>/
        q = q.strip()
        q = re.sub(r'\s+', ' ', q)
        slug = re.sub(r'[^A-Za-z0-9]+', '-', q).strip('-')
        return slug

    def _build_query(self, video):
        query = video.title
        if getattr(video, 'video_type', None) == VIDEO_TYPES.EPISODE:
            try:
                query += ' S%02dE%02d' % (int(video.season), int(video.episode))
            except Exception:
                pass
        elif getattr(video, 'video_type', None) == VIDEO_TYPES.SEASON:
            try:
                query = f"{video.title} S{int(video.season):02d}"
            except Exception:
                query = video.title
        elif getattr(video, 'video_type', None) == VIDEO_TYPES.MOVIE:
            if getattr(video, 'year', None):
                query += f' {video.year}'
        return query

    def _build_season_query(self, video):
        try:
            season_num = int(getattr(video, 'season', 0) or 0)
        except Exception:
            season_num = 0
        if not season_num:
            return ''
        return f"{video.title} S{season_num:02d}"

    def get_sources(self, video):
        sources = []
        seen_hashes = set()

        def add_source(item):
            h = item.get('hash')
            if not h or h in seen_hashes:
                return
            seen_hashes.add(h)
            sources.append(item)

        def parse_row(tr, mark_as_pack_default=None):
            # Extract torrent hash and title
            name = ''
            infohash = ''
            size_text = ''
            seeders = 0
            leechers = 0

            tt_name_div = tr.find('div', class_='tt-name')
            if not tt_name_div:
                return

            a_tags = tt_name_div.find_all('a', href=True)
            torrent_link = None
            title_link = None
            for a in a_tags:
                href = a.get('href', '')
                if isinstance(href, str) and 'itorrents.org/torrent/' in href:
                    torrent_link = href
                elif isinstance(href, str) and (href.startswith('/') or href.startswith('http')):
                    # Prefer the non-itorrents title link
                    title_link = a
            if title_link and title_link.get_text(strip=True):
                name = title_link.get_text(strip=True)
            else:
                # fallback from itorrents title param
                if torrent_link:
                    m_dn = re.search(r'[?&]title=([^&]+)', torrent_link)
                    if m_dn:
                        try:
                            name = urllib.parse.unquote(m_dn.group(1))
                        except Exception:
                            name = m_dn.group(1)
            if not name:
                return

            if torrent_link:
                m = re.search(r'/torrent/([A-F0-9]{16,40})\.torrent', torrent_link, re.I)
                if m:
                    infohash = m.group(1).upper()
            if not infohash:
                # As a last resort, try scanning the whole row for a magnet
                m = re.search(r'btih:([A-F0-9]{16,40})', tr.decode() if hasattr(tr, 'decode') else str(tr), re.I)
                if m:
                    infohash = m.group(1).upper()
            if not infohash:
                return

            # Columns: Added (tdnormal), Size (tdnormal), Seed (tdseed), Leech (tdleech)
            # Safely detect size from any tdnormal that has a size unit
            for td in tr.find_all('td'):
                cls = td.get('class') or []
                text = td.get_text(' ', strip=True)
                if 'tdnormal' in cls:
                    sm = re.search(r'(\d+(?:[.,]\d+)?)\s*(TB|GB|MB|KB)', text, re.I)
                    if sm:
                        size_text = f"{sm.group(1).replace(',', '.')} {sm.group(2).upper()}"
                elif 'tdseed' in cls:
                    mseed = re.search(r'(\d+[\d,\.K]*)', text)
                    if mseed:
                        seeders = self.parse_number(mseed.group(1))
                elif 'tdleech' in cls:
                    mlee = re.search(r'(\d+[\d,\.K]*)', text)
                    if mlee:
                        leechers = self.parse_number(mlee.group(1))

            dsize, isize = None, ''
            if size_text:
                try:
                    dsize, isize = scraper_utils._size(size_text)
                except Exception:
                    isize = size_text

            clean_name = scraper_utils.cleanTitle(name)
            quality = scraper_utils.get_tor_quality(clean_name)

            # Pack detection
            pack = False
            if mark_as_pack_default is not None:
                pack = bool(mark_as_pack_default)
            else:
                try:
                    season_num = int(getattr(video, 'season', 0) or 0)
                except Exception:
                    season_num = 0
                if season_num:
                    if re.search(r'(?:complete|pack|full|collection)', clean_name, re.I):
                        pack = True
                    if re.search(r'\bseason\s*0?%02d\b' % season_num, clean_name, re.I):
                        pack = True
                    if re.search(r'\bS%02d\b(?!E\d{2})' % season_num, clean_name, re.I):
                        pack = True
                    if re.search(r'E\d{2}\s*[-–]\s*E\d{2}', clean_name, re.I):
                        pack = True

            magnet = f"magnet:?xt=urn:btih:{infohash}&dn={urllib.parse.quote_plus(name)}"
            item = {
                'class': self,
                'host': 'magnet',
                'label': f"{clean_name} | {dsize}" if dsize else clean_name,
                'seeders': seeders,
                'hash': infohash,
                'name': clean_name,
                'quality': quality,
                'multi-part': False,
                'url': magnet,
                'info': isize,
                'direct': False,
                'debridonly': True,
                'size': dsize
            }
            if pack:
                item['pack'] = True
                item['extra'] = 'PACK'
                try:
                    item['season'] = int(video.season)
                except Exception:
                    pass

            add_source(item)

        def parse_search_page(html, mark_as_pack_default=None):
            if not html:
                return
            soup = BeautifulSoup(html, 'html.parser')
            table = soup.find('table', class_='table2')
            if not table:
                return
            for tr in table.find_all('tr'):
                # Skip header rows
                if tr.find('th'):
                    continue
                try:
                    parse_row(tr, mark_as_pack_default)
                except Exception as e:
                    logger.log(f'LimeTorrents parse row error: {e}', log_utils.LOGWARNING)
                    continue

        # Build search URLs
        queries = []
        main_q = self._build_query(video)
        if main_q:
            main_url = scraper_utils.urljoin(self.base_url or BASE_URL, SEARCH_URL % self._slug(main_q))
            queries.append((main_url, None))
        # Also attempt season pack when looking for an episode
        if getattr(video, 'video_type', None) == VIDEO_TYPES.EPISODE and getattr(video, 'season', None):
            season_q = self._build_season_query(video)
            if season_q:
                season_url = scraper_utils.urljoin(self.base_url or BASE_URL, SEARCH_URL % self._slug(season_q))
                queries.append((season_url, True))
        # Explicit season searches
        if getattr(video, 'video_type', None) == VIDEO_TYPES.SEASON and getattr(video, 'season', None):
            season_q = self._build_season_query(video)
            if season_q:
                season_url = scraper_utils.urljoin(self.base_url or BASE_URL, SEARCH_URL % self._slug(season_q))
                queries.append((season_url, True))

        for url, mark_pack in queries:
            logger.log(f"LimeTorrents search url: {url}", log_utils.LOGDEBUG)
            html = self._http_get_alt(url, require_debrid=False, cache_limit=.5)
            logger.log(f"LimeTorrents html len: {len(html) if html else 0}", log_utils.LOGDEBUG)
            parse_search_page(html, mark_as_pack_default=mark_pack)

        return sources

