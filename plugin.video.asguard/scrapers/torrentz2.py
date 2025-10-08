"""
    Asguard Addon
    Copyright (C) 2024 MrBlamo

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
import urllib.request, urllib.error
from bs4 import BeautifulSoup
import requests
import log_utils
from asguard_lib import scraper_utils, control
from asguard_lib.constants import FORCE_NO_MATCH, VIDEO_TYPES, QUALITIES
from asguard_lib.utils2 import i18n
import kodi
from . import scraper
from . import proxy

try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)

logger = log_utils.Logger.get_logger()
BASE_URL = 'https://torrentz2.nz'
SEARCH_URL = '/search?q=%s'
SERVER_ERROR = ('something went wrong', 'Connection timed out', '521: Web server is down', '503 Service Unavailable')

class Scraper(scraper.Scraper):
    base_url = BASE_URL
    debrid_resolvers = resolveurl

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting('%s-base_url' % (self.get_name()))

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE, VIDEO_TYPES.MOVIE])

    @classmethod
    def get_name(cls):
        return 'Torrentz2'

    def resolve_link(self, link):
        return link

    def parse_number(self,text):
        """Convert a string with 'K' to an integer."""
        if 'K' in text:
            return int(float(text.replace('K', '').replace(',', '')) * 1000)
        return int(text.replace(',', ''))

    def get_sources(self, video):
        sources = []
        seen_hashes = set()

        def parse_page(html, mark_as_pack_default=None):
            if not html:
                return
            soup = BeautifulSoup(html, 'html.parser')
            for a in soup.find_all('a', href=lambda h: isinstance(h, str) and h.startswith('magnet:')):
                try:
                    magnet_link = a.get('href')
                    m = re.search(r'btih:([A-F0-9]+)', magnet_link, re.I)
                    if not m:
                        continue
                    infohash = m.group(1).upper()
                    if infohash in seen_hashes:
                        continue

                    # locate card container for metadata
                    card = a
                    while card and (card.name != 'div' or 'p-6' not in (card.get('class') or [])):
                        card = card.parent

                    # Title
                    name = None
                    if card:
                        h3 = card.find('h3')
                        if h3:
                            title_a = h3.find('a')
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
                        continue
                    clean_name = scraper_utils.cleanTitle(name)

                    # Size
                    size_text = ''
                    if card:
                        text = card.get_text(" ", strip=True)
                        size_m = re.search(r'(\d+(?:\.\d+)?)\s*(TB|GB|MB)', text, re.I)
                        if size_m:
                            size_text = f"{size_m.group(1)} {size_m.group(2).upper()}"
                    dsize = None
                    isize = ''
                    if size_text:
                        try:
                            dsize, isize = scraper_utils._size(size_text)
                            logger.log('Size: %s' % isize, log_utils.LOGDEBUG)
                        except Exception:
                            isize = size_text

                    # Seeders/Leechers
                    seeders = 0
                    leechers = 0
                    if card:
                        def get_stat(lbl):
                            s = card.find('span', string=lambda s: isinstance(s, str) and s.strip().lower() == lbl)
                            if s and s.parent:
                                num_span = s.parent.find('span', class_='font-medium')
                                if num_span:
                                    try:
                                        return self.parse_number(num_span.get_text(strip=True))
                                    except Exception:
                                        return 0
                            return 0
                        seeders = get_stat('seeders')
                        leechers = get_stat('leechers')

                    # Determine if this is a season pack
                    pack = False
                    if mark_as_pack_default is not None:
                        pack = bool(mark_as_pack_default)
                    else:
                        try:
                            season_num = int(getattr(video, 'season', 0) or 0)
                        except Exception:
                            season_num = 0
                        if season_num:
                            # Heuristics: contains Season XX, Complete, Pack, range E01-E??, or Sxx without Eyy
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

                    sources.append(item)
                    seen_hashes.add(infohash)
                except Exception as e:
                    logger.log(f'Error processing Torrentz2 source: {str(e)}', log_utils.LOGERROR)
                    continue

        # Build one or more queries
        queries = []
        # Primary query
        search_url = self._build_query(video)
        page_url = scraper_utils.urljoin(self.base_url or BASE_URL, SEARCH_URL % urllib.parse.quote_plus(search_url))
        queries.append((page_url, None))  # None -> let parser decide pack by heuristics

        # If EPISODE, also add season pack query
        if getattr(video, 'video_type', None) == VIDEO_TYPES.EPISODE and getattr(video, 'season', None):
            season_q = self._build_season_query(video)
            if season_q:
                season_url = scraper_utils.urljoin(self.base_url or BASE_URL, SEARCH_URL % urllib.parse.quote_plus(season_q))
                queries.append((season_url, True))  # mark season results as pack

        # If SEASON request, just add season query (in case default builder didn't)
        if getattr(video, 'video_type', None) == VIDEO_TYPES.SEASON and getattr(video, 'season', None):
            if not queries:
                season_q = self._build_season_query(video)
                if season_q:
                    season_url = scraper_utils.urljoin(self.base_url or BASE_URL, SEARCH_URL % urllib.parse.quote_plus(season_q))
                    queries.append((season_url, True))

        # Fetch and parse all queries
        for url, mark_pack in queries:
            html = self._http_get_alt(url, require_debrid=True, cache_limit=.5)
            parse_page(html, mark_as_pack_default=mark_pack)

        return sources

    def _build_query(self, video):
        query = video.title

        # Check for episode and season range in the title
        episode_range = re.search(r'[Ee]p?(\d+)(?:[-~](\d+))?', video.title)
        season_range = re.search(r'[Ss]eason\s?(\d+)|[Ss](\d+)', video.title)


        # Construct the query based on the video type
        if video.video_type == VIDEO_TYPES.EPISODE:
            if season_range:
                start_season, end_season = map(int, season_range.groups(default=season_range.group(1)))

                if episode_range:
                    start_ep, end_ep = map(int, episode_range.groups(default=episode_range.group(1)))

                    query += f' S{start_season:02d}E{start_ep:02d}-E{end_ep:02d}'
                else:
                    # Handle full season queries
                    query = f'"Season {start_season:02d}"|"Complete"|"Batch"|"S{start_season:02d}"'
            else:
                query += f' S{int(video.season):02d}E{int(video.episode):02d}'

        elif video.video_type == VIDEO_TYPES.MOVIE:
            query += f' {video.year}'

        query = query.replace(' ', '+').replace('+-', '-')
        return query

    def _build_season_query(self, video):
        """Build a query aimed at season packs for the given video."""
        try:
            season_num = int(getattr(video, 'season', 0) or 0)
        except Exception:
            season_num = 0
        if not season_num:
            return ''
        base_title = video.title
        # Prefer Sxx form which the site understands well
        query = f"{base_title} S{season_num:02d}"
        query = query.replace(' ', '+').replace('+-', '-')
        return query


    
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