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

BASE_URL = 'https://bflix.sh'
SEARCH_PATTERNS = [
    '/search/%s',                # e.g., /search/stargate
    '/search?keyword=%s',        # fallback querystring
]


class Scraper(scraper.Scraper):
    base_url = BASE_URL
    debrid_resolvers = resolveurl

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        try:
            self.base_url = kodi.get_setting('%s-base_url' % (self.get_name())) or BASE_URL
        except Exception:
            self.base_url = BASE_URL
        logger.log(f"BFlix init base_url: {self.base_url}", log_utils.LOGDEBUG)

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE, VIDEO_TYPES.SEASON, VIDEO_TYPES.MOVIE])

    @classmethod
    def get_name(cls):
        return 'BFlix'

    def resolve_link(self, link):
        return link

    def _slug(self, q):
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
        logger.log(f"BFlix _build_query: '{query}' for video_type={getattr(video, 'video_type', None)}", log_utils.LOGDEBUG)
        return query

    def _search(self, query):
        """Return list of dicts: {title, url, type, year?} from site search"""
        results = []
        for pat in SEARCH_PATTERNS:
            url = scraper_utils.urljoin(self.base_url or BASE_URL, pat % urllib.parse.quote_plus(query))
            logger.log(f"BFlix search URL: {url}", log_utils.LOGDEBUG)
            html = self._http_get_alt(url, require_debrid=False, cache_limit=.5, use_flaresolver=True)
            logger.log(f"BFlix search HTML length: {len(html) if html else 0}", log_utils.LOGDEBUG)
            if not html:
                continue
            soup = BeautifulSoup(html, 'html.parser')
            links_found = 0
            # Common list/grid containers
            for a in soup.find_all('a', href=True):
                href = a['href']
                if not isinstance(href, str):
                    continue
                if not (href.startswith('/') or href.startswith('http')):
                    continue
                if '/movie/' in href or '/series/' in href:
                    links_found += 1
                    t = a.get('title') or a.get_text(' ', strip=True)
                    t = t.strip() if isinstance(t, str) else ''
                    item = {
                        'title': t,
                        'url': scraper_utils.urljoin(self.base_url, href, scheme='https', replace_path=True),
                        'type': 'movie' if '/movie/' in href else 'series'
                    }
                    # Try to extract year nearby
                    year = None
                    parent = a.parent
                    try:
                        ytxt = parent.get_text(' ', strip=True) if parent else ''
                        m = re.search(r'(19\d{2}|20\d{2})', ytxt)
                        if m:
                            year = m.group(1)
                    except Exception:
                        pass
                    if year:
                        item['year'] = year
                    logger.log(f"BFlix found result: title='{item['title']}', type={item['type']}, year={item.get('year')}, url={item['url']}", log_utils.LOGDEBUG)
                    results.append(item)
            logger.log(f"BFlix links scanned: {links_found}, results so far: {len(results)}", log_utils.LOGDEBUG)
            if results:
                break
        logger.log(f"BFlix _search final results: {len(results)}", log_utils.LOGDEBUG)
        return results

    def _choose_result(self, video, results, expect_type):
        if not results:
            logger.log("BFlix _choose_result: no results to choose from", log_utils.LOGDEBUG)
            return None
        norm_target = scraper_utils.normalize_title(video.title)
        year = str(getattr(video, 'year', '') or '')
        best = None
        score = -1
        for r in results:
            if expect_type and r.get('type') != expect_type:
                continue
            t = scraper_utils.normalize_title(r.get('title') or '')
            s = 0
            if t == norm_target:
                s += 5
            elif t and (t in norm_target or norm_target in t):
                s += 3
            if year and r.get('year') == year:
                s += 2
            logger.log(f"BFlix scoring: cand_title='{r.get('title')}', norm='{t}', score={s}", log_utils.LOGDEBUG)
            if s > score:
                best = r
                score = s
        if not best:
            # fallback any type
            for r in results:
                t = scraper_utils.normalize_title(r.get('title') or '')
                if t and (t in norm_target or norm_target in t):
                    logger.log(f"BFlix fallback picked: {r}", log_utils.LOGDEBUG)
                    return r
            logger.log(f"BFlix default picked first result: {results[0]}", log_utils.LOGDEBUG)
            return results[0]
        logger.log(f"BFlix chosen result: {best}", log_utils.LOGDEBUG)
        return best

    def _extract_iframe_sources(self, html, referer):
        sources = []
        if not html:
            logger.log("BFlix _extract_iframe_sources: empty html", log_utils.LOGDEBUG)
            return sources
        soup = BeautifulSoup(html, 'html.parser')
        # Collect iframes
        iframe_srcs = set()
        for iframe in soup.find_all('iframe', src=True):
            src = iframe['src']
            if not isinstance(src, str):
                continue
            # Make absolute
            src = scraper_utils.urljoin(self.base_url, src, scheme='https', replace_path=True)
            iframe_srcs.add(src)
        logger.log(f"BFlix iframe srcs found: {len(iframe_srcs)}", log_utils.LOGDEBUG)
        # Scan for obvious embed urls in page text
        if not iframe_srcs:
            m_all = re.findall(r"(https?://[^\s\"'<>]+)", html)
            logger.log(f"BFlix raw URL candidates in page: {len(m_all)}", log_utils.LOGDEBUG)
            for u in m_all:
                if re.search(r'(embed|player|stream|cloud|mcloud|upcloud|rapid|filemoon|streamtape|dood|ok\.ru|vid|vidplay)', u, re.I):
                    iframe_srcs.add(u)
        logger.log(f"BFlix embed candidates after filter: {len(iframe_srcs)}", log_utils.LOGDEBUG)
        for u in iframe_srcs:
            host = urllib.parse.urlsplit(u).hostname or 'embed'
            label = host
            q = scraper_utils.get_tor_quality(u)
            item = {
                'class': self,
                'host': host,
                'label': label,
                'quality': q,
                'multi-part': False,
                'url': u,
                'direct': False,
                'debridonly': False,
            }
            # Provide referer header for hosts that need it
            item['headers'] = {'Referer': referer}
            logger.log(f"BFlix adding source: host={host}, quality={q}, url={u}", log_utils.LOGDEBUG)
            sources.append(item)
        logger.log(f"BFlix total sources extracted: {len(sources)}", log_utils.LOGDEBUG)
        return sources

    def _find_episode_link(self, series_html, video):
        """Try to locate a link for the requested SxxExx on the series page"""
        if not series_html:
            logger.log("BFlix _find_episode_link: empty series_html", log_utils.LOGDEBUG)
            return None
        s = int(getattr(video, 'season', 0) or 0)
        e = int(getattr(video, 'episode', 0) or 0)
        if not s or not e:
            logger.log(f"BFlix _find_episode_link: missing s/e (s={s}, e={e})", log_utils.LOGDEBUG)
            return None
        soup = BeautifulSoup(series_html, 'html.parser')
        # Strategy 1: look for explicit SxxExx in link text
        sxe = f'S{s:02d}E{e:02d}'
        for a in soup.find_all('a', href=True):
            txt = a.get_text(' ', strip=True) or ''
            if sxe in txt:
                ep_url = scraper_utils.urljoin(self.base_url, a['href'], scheme='https', replace_path=True)
                logger.log(f"BFlix _find_episode_link: matched by SxxExx: {ep_url}", log_utils.LOGDEBUG)
                return ep_url
        # Strategy 2: look for Episode N within a Season S section
        season_blocks = []
        for blk in soup.find_all(True):
            cls = ' '.join(blk.get('class') or [])
            if re.search(r'season', cls, re.I):
                season_blocks.append(blk)
        for blk in season_blocks or [soup]:
            for a in blk.find_all('a', href=True):
                txt = a.get_text(' ', strip=True) or ''
                if re.search(r'\b(Ep|Episode)\s*0?%d\b' % e, txt, re.I):
                    ep_url = scraper_utils.urljoin(self.base_url, a['href'], scheme='https', replace_path=True)
                    logger.log(f"BFlix _find_episode_link: matched by Episode N: {ep_url}", log_utils.LOGDEBUG)
                    return ep_url
        # Strategy 3: some clones use watch urls with ?ep=ID present on the series page
        m = re.search(r'href=["\'](/watch[^"\']+\?ep=\d+)', series_html)
        if m:
            ep_url = scraper_utils.urljoin(self.base_url, m.group(1), scheme='https', replace_path=True)
            logger.log(f"BFlix _find_episode_link: matched by watch?ep=: {ep_url}", log_utils.LOGDEBUG)
            return ep_url
        logger.log("BFlix _find_episode_link: no episode link found", log_utils.LOGDEBUG)
        return None

    def get_sources(self, video):
        sources = []
        # Build a site search and choose best match
        q = self._build_query(video)
        logger.log(f"BFlix get_sources query: '{q}'", log_utils.LOGDEBUG)
        results = self._search(q)
        logger.log(f"BFlix get_sources results count: {len(results)}", log_utils.LOGDEBUG)
        exp = 'movie' if video.video_type == VIDEO_TYPES.MOVIE else 'series'
        chosen = self._choose_result(video, results, expect_type=exp)
        logger.log(f"BFlix get_sources chosen: {chosen}", log_utils.LOGDEBUG)
        if not chosen:
            return sources

        page_url = chosen['url']
        logger.log(f"BFlix opening detail page: {page_url}", log_utils.LOGDEBUG)
        html = self._http_get_alt(page_url, require_debrid=False, cache_limit=.5, use_flaresolver=True)
        logger.log(f"BFlix detail HTML length: {len(html) if html else 0}", log_utils.LOGDEBUG)
        if not html:
            return sources

        # If movie, parse embeds directly from page
        if video.video_type == VIDEO_TYPES.MOVIE:
            srcs = self._extract_iframe_sources(html, page_url)
            sources.extend(srcs)
            logger.log(f"BFlix movie sources: {len(sources)}", log_utils.LOGDEBUG)
            return sources

        # If TV episode or season, locate the specific episode page then extract embeds
        if video.video_type in (VIDEO_TYPES.EPISODE, VIDEO_TYPES.SEASON, VIDEO_TYPES.TVSHOW):
            # If EPISODE, try to navigate to its link
            target_url = None
            if video.video_type == VIDEO_TYPES.EPISODE:
                target_url = self._find_episode_link(html, video)
            # If not found, fall back to detail page (some sites load the first ep embeds here)
            target_url = target_url or page_url
            logger.log(f"BFlix target_url for sources: {target_url}", log_utils.LOGDEBUG)
            ep_html = html if target_url == page_url else self._http_get_alt(target_url, require_debrid=False, cache_limit=.25, use_flaresolver=True)
            logger.log(f"BFlix episode HTML length: {len(ep_html) if ep_html else 0}", log_utils.LOGDEBUG)
            srcs = self._extract_iframe_sources(ep_html, target_url)
            # If we didn't get anything, try to probe AJAX endpoints present in page
            if not srcs:
                ajax_links = set()
                for m in re.finditer(r'href=["\'](/ajax/[^"\']+)["\']', ep_html or ''):
                    ajax_links.add(scraper_utils.urljoin(self.base_url, m.group(1), scheme='https', replace_path=True))
                logger.log(f"BFlix ajax_links discovered: {len(ajax_links)}", log_utils.LOGDEBUG)
                for al in list(ajax_links)[:5]:
                    logger.log(f"BFlix probing ajax: {al}", log_utils.LOGDEBUG)
                    aj = self._http_get_alt(al, require_debrid=False, cache_limit=.1, use_flaresolver=True)
                    if not aj:
                        continue
                    srcs2 = self._extract_iframe_sources(aj, target_url)
                    if srcs2:
                        srcs.extend(srcs2)
                        break
            sources.extend(srcs)
            logger.log(f"BFlix TV sources: {len(sources)}", log_utils.LOGDEBUG)
            return sources

        return sources

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
