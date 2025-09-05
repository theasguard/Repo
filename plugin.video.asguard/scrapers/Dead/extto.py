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

import logging
import re
import urllib.parse
from bs4 import BeautifulSoup
import log_utils
from asguard_lib import scraper_utils
from asguard_lib.constants import VIDEO_TYPES
from asguard_lib.utils2 import i18n
import kodi
from . import scraper

# cfscrape (cloudscraper) optional import
try:
    from asguard_lib import cfscrape as _cfscrape
except Exception:
    try:
        import cfscrape as _cfscrape  # fallback to global module if available
    except Exception:
        _cfscrape = None

try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)

logger = log_utils.Logger.get_logger()
BASE_URL = 'https://ext.to'
SEARCH_URL = '/browse/?q=%s'
FALLBACK_SEARCH_URL = '/search/?q=%s'

class Scraper(scraper.Scraper):
    base_url = BASE_URL
    debrid_resolvers = resolveurl

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        # Allow overriding via settings
        try:
            self.base_url = kodi.get_setting('%s-base_url' % (self.get_name())) or BASE_URL
        except Exception:
            self.base_url = BASE_URL

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE, VIDEO_TYPES.SEASON, VIDEO_TYPES.MOVIE])

    @classmethod
    def get_name(cls):
        return 'EXT.to'

    def resolve_link(self, link):
        return link

    def parse_number(self, text):
        if text is None:
            return 0
        s = text.strip().upper()
        try:
            if s.endswith('K'):
                return int(float(s[:-1].replace(',', '')) * 1000)
            return int(s.replace(',', ''))
        except Exception:
            # fallback for e.g. '-' or empty
            try:
                return int(re.sub(r'\D+', '', s) or 0)
            except Exception:
                return 0

    def _looks_like_cf(self, text):
        if not text:
            return True
        try:
            s = text[:2000]
        except Exception:
            s = text
        patterns = (
            'cf-browser-verification',
            '__cf_chl_jschl_tk__',
            '__cf_chl_captcha_tk__',
            'challenge-platform',
            'Attention Required! | Cloudflare',
            'cf-captcha-bookmark'
        )
        return any(p in s for p in patterns)

    def _get_with_cfscrape(self, url, headers=None, cache_limit=0):
        if _cfscrape is None:
            return ''
        try:
            _created, _res_header, html = self.db_connection().get_cached_url(url, None, cache_limit)
            if html:
                if isinstance(html, bytes):
                    try:
                        html = html.decode('utf-8', errors='ignore')
                    except Exception:
                        pass
                return html
        except Exception:
            pass
        try:
            sess = _cfscrape.create_scraper(interpreter='native')
        except Exception:
            try:
                sess = _cfscrape.create_scraper()
            except Exception:
                sess = None
        if not sess:
            return ''
        ua = scraper_utils.get_ua()
        req_headers = {'User-Agent': ua, 'Accept': '*/*', 'Referer': self.base_url or BASE_URL}
        if headers:
            req_headers.update(headers)
        try:
            resp = sess.get(url, headers=req_headers, timeout=self.timeout or 15, allow_redirects=True)
            if getattr(resp, 'status_code', 0) in (200, 201):
                html = resp.text
                try:
                    self.db_connection().cache_url(url, html, None)
                except Exception:
                    pass
                return html
        except Exception as e:
            logger.log(f'cfscrape fetch failed for {url}: {e}', log_utils.LOGWARNING)
        return ''

    def _get_html_cfaware(self, url, cache_limit=.5):
        html = self._http_get_alt(url, require_debrid=False, cache_limit=cache_limit, use_flaresolver=False)
        if not html or self._looks_like_cf(html):
            ch = self._get_with_cfscrape(url, cache_limit=cache_limit)
            if ch:
                return ch
            html = self._http_get_alt(url, require_debrid=False, cache_limit=0, use_flaresolver=True)
        return html

    def get_sources(self, video):
        sources = []
        seen_hashes = set()

        def add_source(item):
            h = item.get('hash')
            if not h or h in seen_hashes:
                return
            seen_hashes.add(h)
            sources.append(item)

        def parse_card_from_anchor(a, mark_as_pack_default=None):
            # Prefer table row as the main container for stats and title if available
            row_tr = None
            try:
                row_tr = a.find_parent('tr')
            except Exception:
                row_tr = None

            # Fallback: climb a few levels
            card = a
            levels = 0
            while card and levels < 6 and not (card.name in ('tr', 'article', 'div', 'li')):
                card = card.parent
                levels += 1

            magnet_link = a.get('href')
            if not magnet_link:
                return

            # Infohash
            m = re.search(r'btih:([A-F0-9]{16,40})', magnet_link, re.I)
            if not m:
                return
            infohash = m.group(1).upper()

            # Title / name
            name = None
            title_a = None
            # Prefer a title link within the table row first column
            if row_tr:
                try:
                    first_td = row_tr.find('td')
                    if first_td:
                        cand = first_td.find('a', href=True)
                        if cand and cand.get_text(strip=True):
                            title_a = cand
                except Exception:
                    pass
            # Fallback: search container for a reasonable title link
            if not title_a and card:
                for ta in card.find_all('a', href=True):
                    hrefv = ta.get('href', '')
                    if hrefv.startswith('/') and ta.get_text(strip=True):
                        title_a = ta
                        break
            if title_a and title_a.get_text(strip=True):
                name = title_a.get_text(strip=True)
            if not name:
                dn_match = re.search(r'[?&]dn=([^&]+)', magnet_link)
                if dn_match:
                    try:
                        name = urllib.parse.unquote(dn_match.group(1))
                    except Exception:
                        name = dn_match.group(1)
            if not name:
                return
            clean_name = scraper_utils.cleanTitle(name)

            # Size
            size_text = ''
            # Seeders / Leechers
            seeders = 0
            leechers = 0
            # Prefer reading from the table row columns
            if row_tr:
                try:
                    tds = row_tr.find_all('td')
                    if len(tds) >= 6:
                        # Size in 2nd column
                        sz_col = tds[1].get_text(' ', strip=True)
                        sm = re.search(r'(\d+(?:[.,]\d+)?)\s*(TB|GB|MB)', sz_col, re.I)
                        if sm:
                            size_text = f"{sm.group(1).replace(',', '.')} {sm.group(2).upper()}"
                        # Seeds in 5th column
                        seeds_col = tds[4].get_text(' ', strip=True)
                        mseed = re.search(r'(\d+[\d,\.K]*)', seeds_col)
                        if mseed:
                            seeders = self.parse_number(mseed.group(1))
                        # Leechs in 6th column
                        leech_col = tds[5].get_text(' ', strip=True)
                        mlee = re.search(r'(\d+[\d,\.K]*)', leech_col)
                        if mlee:
                            leechers = self.parse_number(mlee.group(1))
                except Exception:
                    pass
            # Fallback to scanning the container text
            if (not size_text) and card:
                text = card.get_text(' ', strip=True)
                sm = re.search(r'(\d+(?:[.,]\d+)?)\s*(TB|GB|MB)', text, re.I)
                if sm:
                    size_text = f"{sm.group(1).replace(',', '.')} {sm.group(2).upper()}"
            if (seeders == 0 or leechers == 0) and card:
                def find_stat(lbl):
                    s = card.find('span', string=lambda s: isinstance(s, str) and lbl in s.lower())
                    if s and s.parent:
                        num = re.search(r'(\d+[\d,\.K]*)', s.parent.get_text(' ', strip=True))
                        if num:
                            return self.parse_number(num.group(1))
                    return 0
                tmp_seed = find_stat('seed')
                tmp_leech = find_stat('leech')
                seeders = tmp_seed or seeders
                leechers = tmp_leech or leechers
            dsize, isize = None, ''
            if size_text:
                try:
                    dsize, isize = scraper_utils._size(size_text)
                except Exception:
                    isize = size_text

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

            quality = scraper_utils.get_tor_quality(clean_name)

            item = {
                'class': self,
                'host': 'magnet',
                'label': f"{clean_name} | {dsize}" if dsize else clean_name,
                'seeders': seeders,
                'hash': infohash,
                'name': clean_name,
                'quality': quality,
                'multi-part': False,
                'url': magnet_link,
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
            # Parse magnets directly on search page (if present)
            for a in soup.find_all('a', href=lambda h: isinstance(h, str) and h.startswith('magnet:')):
                try:
                    parse_card_from_anchor(a, mark_as_pack_default)
                except Exception as e:
                    logger.log(f'EXT.to parse magnet error: {e}', log_utils.LOGWARNING)
                    continue
            # Also parse table rows explicitly (new EXT layout)
            for tr in soup.select('table.search-table tbody tr'):
                try:
                    # Class-based selector for download button
                    mag_btn = tr.find('a', class_=lambda c: isinstance(c, str) and 'torrent-dwn' in c, href=True)
                    if not mag_btn or not isinstance(mag_btn.get('href'), str) or not mag_btn['href'].startswith('magnet:'):
                        # Fallback: any magnet in the row
                        mag_btn = tr.find('a', href=lambda h: isinstance(h, str) and h.startswith('magnet:'))
                    if mag_btn:
                        parse_card_from_anchor(mag_btn, mark_as_pack_default)
                except Exception as e:
                    logger.log(f'EXT.to table row parse error: {e}', log_utils.LOGWARNING)
                    continue

            # Also follow detail pages to pick up magnets
            detail_links = []
            for a in soup.find_all('a', href=True):
                href = a['href']
                if not isinstance(href, str):
                    continue
                if (href.startswith('/') or href.startswith('http')) and any(k in href for k in ['/torrent', '/tor/', '/details']):
                    detail_links.append(scraper_utils.urljoin(self.base_url, href, scheme='https', replace_path=True))
            # Deduplicate and limit to avoid heavy crawling
            seen = set()
            for link in detail_links[:30]:
                if link in seen:
                    continue
                seen.add(link)
                try:
                    detail_html = self._get_html_cfaware(link, cache_limit=.25)
                    if not detail_html:
                        continue
                    sd = BeautifulSoup(detail_html, 'html.parser')
                    mag_a = sd.find('a', href=lambda h: isinstance(h, str) and isinstance(h, str) and h.startswith('magnet:'))
                    if not mag_a:
                        # Try attribute-based magnet (e.g., data-clipboard-text)
                        magnet_link = None
                        for tag in sd.find_all(True):
                            # Check common attributes for magnet
                            for attr_key in ('data-clipboard-text', 'data-href', 'href', 'data-url'):
                                val = tag.get(attr_key)
                                if isinstance(val, str) and val.startswith('magnet:'):
                                    magnet_link = val
                                    break
                            if magnet_link:
                                break
                        if not magnet_link:
                            # Regex scan as last resort
                            m = re.search(r'(magnet:\?[^"\s<]+)', detail_html)
                            if m:
                                magnet_link = m.group(1)
                        if magnet_link:
                            try:
                                temp_a = sd.new_tag('a', href=magnet_link)
                                mag_a = temp_a
                            except Exception:
                                mag_a = None
                    if mag_a:
                        parse_card_from_anchor(mag_a, mark_as_pack_default)
                except Exception as e:
                    logger.log(f'EXT.to follow detail error: {e}', log_utils.LOGWARNING)
                    continue

        # Build queries
        queries = []
        main_q = self._build_query(video)
        if main_q:
            for pattern in (SEARCH_URL, FALLBACK_SEARCH_URL):
                main_url = scraper_utils.urljoin(self.base_url or BASE_URL, pattern % urllib.parse.quote_plus(main_q))
                queries.append((main_url, None))
        # Add season pack search for episodes
        if getattr(video, 'video_type', None) == VIDEO_TYPES.EPISODE and getattr(video, 'season', None):
            season_q = self._build_season_query(video)
            if season_q:
                for pattern in (SEARCH_URL, FALLBACK_SEARCH_URL):
                    season_url = scraper_utils.urljoin(self.base_url or BASE_URL, pattern % urllib.parse.quote_plus(season_q))
                    queries.append((season_url, True))
        # Direct season searches
        if getattr(video, 'video_type', None) == VIDEO_TYPES.SEASON and getattr(video, 'season', None):
            season_q = self._build_season_query(video)
            if season_q:
                for pattern in (SEARCH_URL, FALLBACK_SEARCH_URL):
                    season_url = scraper_utils.urljoin(self.base_url or BASE_URL, pattern % urllib.parse.quote_plus(season_q))
                    queries.append((season_url, True))

        for url, mark_pack in queries:
            logger.log(f"EXT.to page_url: {url}", log_utils.LOGDEBUG)
            html = self._get_html_cfaware(url, cache_limit=.5)
            logger.log(f"EXT.to html len: {len(html) if html else 0}", log_utils.LOGDEBUG)
            parse_search_page(html, mark_as_pack_default=mark_pack)

        return sources

    def _build_query(self, video):
        query = video.title
        logging.debug("EXT.to Initial query: %s", query)

        episode_range = re.search(r'[Ee]p?(\d+)(?:[-~](\d+))?', video.title)
        season_range = re.search(r'[Ss]eason\s?(\d+)|[Ss](\d+)', video.title)

        if video.video_type == VIDEO_TYPES.EPISODE:
            if season_range:
                start_season, end_season = map(int, season_range.groups(default=season_range.group(1)))
                if episode_range:
                    start_ep, end_ep = map(int, episode_range.groups(default=episode_range.group(1)))
                    query += f' S{start_season:02d}E{start_ep:02d}-E{end_ep:02d}'
                else:
                    query = f'"Season {start_season:02d}"|"Complete"|"Batch"|"S{start_season:02d}"'
            else:
                query += f' S{int(video.season):02d}E{int(video.episode):02d}'
            logging.debug("EXT.to Episode query: %s", query)
        elif video.video_type == VIDEO_TYPES.MOVIE:
            if getattr(video, 'year', None):
                query += f' {video.year}'
            logging.debug("EXT.to Movie query: %s", query)
        elif video.video_type == VIDEO_TYPES.SEASON:
            # Season pack specific by default
            try:
                season_num = int(video.season)
            except Exception:
                season_num = 0
            if season_num:
                query = f'{video.title} S{season_num:02d}'

        query = query.replace(' ', '+').replace('+-', '-')
        logging.debug("EXT.to Final query: %s", query)
        return query

    def _build_season_query(self, video):
        try:
            season_num = int(getattr(video, 'season', 0) or 0)
        except Exception:
            season_num = 0
        if not season_num:
            return ''
        q = f"{video.title} S{season_num:02d}"
        q = q.replace(' ', '+').replace('+-', '-')
        return q

    @classmethod
    def get_settings(cls):
        settings = super(cls, cls).get_settings()
        name = cls.get_name()
        parent_id = f"{name}-enable"
        label_id = kodi.Translations.get_scraper_label_id(name)

        return [
            f'''\t\t<setting id="{parent_id}" type="boolean" label="{label_id}" help="">
\t\t\t<level>0</level>
\t\t\t<default>true</default>
\t\t\t<dependencies>
\t\t\t\t<dependency type="visible">
\t\t\t\t\t<condition on="property" name="InfoBool">true</condition>
\t\t\t\t</dependency>
\t\t\t</dependencies>
\t\t\t<control type="toggle"/>
\t\t</setting>''',
            f'''\t\t<setting id="{name}-base_url" type="string" label="30175" help="">
\t\t\t<level>0</level>
\t\t\t<default>{cls.base_url}</default>
\t\t\t<dependencies>
\t\t\t\t<dependency type="visible">
\t\t\t\t\t<condition operator="is" setting="{parent_id}">true</condition>
\t\t\t\t</dependency>
\t\t\t</dependencies>
\t\t\t<control type="edit" format="string">
\t\t\t\t<heading>{i18n('base_url')}</heading>
\t\t\t</control>
\t\t</setting>'''
        ]
