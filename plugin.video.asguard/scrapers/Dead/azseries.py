"""
    Asguard Addon - AZSeries Scraper
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
import json
import urllib.parse
from bs4 import BeautifulSoup

import kodi
import log_utils
from asguard_lib import scraper_utils
from asguard_lib.constants import VIDEO_TYPES, QUALITIES, FORCE_NO_MATCH
from . import scraper

logger = log_utils.Logger.get_logger()

BASE_URL = 'https://azseries.org'


class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        # Allow override from settings, fallback to default
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url') or BASE_URL

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'AZSeries'

    def resolve_link(self, link):
        return link

    # -----------------------------
    # Core flow
    # -----------------------------
    def get_sources(self, video):
        sources = []
        source_url = self.get_url(video)
        if not source_url or source_url == FORCE_NO_MATCH:
            return sources

        url = scraper_utils.urljoin(self.base_url, source_url)
        logger.log(f'[AZSeries] Fetching source page: {url}', log_utils.LOGDEBUG)

        # Use alternate getter for better CF handling
        html = self._http_get_alt(url, cache_limit=0.5, use_flaresolver=True)
        if not html or html == FORCE_NO_MATCH:
            logger.log('[AZSeries] No HTML returned from content page', log_utils.LOGWARNING)
            return sources

        # 1) Try DooPlay-style AJAX player buttons
        sources.extend(self._extract_dooplay_ajax_sources(html, url, video))

        # 2) Fallbacks: data-id / data-iframe direct embeds
        try:
            soup = BeautifulSoup(html, 'html.parser')

            # data-iframe links
            for a in soup.find_all(['a', 'div'], attrs={'data-iframe': True}):
                iframe_url = (a.get('data-iframe') or '').strip()
                if iframe_url:
                    self._append_server_source(sources, iframe_url, video)

            # data-id links (often direct server links)
            for a in soup.find_all(['a', 'div', 'li'], attrs={'data-id': True}):
                data_id = (a.get('data-id') or '').strip()
                if data_id:
                    if data_id.startswith('//'):
                        data_id = 'https:' + data_id
                    if data_id.startswith('http'):
                        self._append_server_source(sources, data_id, video)

            # iframes on page
            for iframe in soup.find_all('iframe'):
                src = iframe.get('src') or ''
                if src:
                    if src.startswith('//'):
                        src = 'https:' + src
                    self._append_server_source(sources, src, video)
        except Exception as e:
            logger.log(f'[AZSeries] Error parsing fallback server patterns: {e}', log_utils.LOGDEBUG)

        logger.log(f'[AZSeries] Returning {len(sources)} sources', log_utils.LOGDEBUG)
        return sources

    def search(self, video_type, title, year, season=''):
        results = []
        try:
            q = urllib.parse.quote_plus(title)
            search_url = f'/?s={q}'
            url = scraper_utils.urljoin(self.base_url, search_url)
            logger.log(f'[AZSeries] Search URL: {url}', log_utils.LOGDEBUG)

            html = self._http_get_alt(url, cache_limit=1)
            if not html:
                return results

            soup = BeautifulSoup(html, 'html.parser')

            # Try common result containers
            anchors = []
            # Direct anchors in lists or grids
            anchors.extend(soup.find_all('a', href=True))

            def normalize(s):
                try:
                    return scraper_utils.normalize_title(s)
                except Exception:
                    return (s or '').strip().lower()

            norm_search = normalize(title)
            for a in anchors:
                href = a['href']
                text = a.get_text(strip=True) or ''
                if not href.startswith('http'):
                    continue

                # Prefer content pages only
                is_movie = '/movie/' in href
                is_show = any(x in href for x in ['/series/', '/tvshows/', '/tv-show/', '/show/'])
                is_episode = '/episodes/' in href

                # Filter by video_type
                if video_type == VIDEO_TYPES.MOVIE and not is_movie:
                    continue
                if video_type in (VIDEO_TYPES.TVSHOW, VIDEO_TYPES.SEASON) and not (is_show or is_episode):
                    continue
                if video_type == VIDEO_TYPES.EPISODE and not (is_show or is_episode):
                    continue

                # Title check
                if text:
                    if norm_search not in normalize(text) and normalize(text) not in norm_search:
                        # Sometimes the title is in parent elements; be permissive
                        pass

                # Extract year if present in sibling/parent
                result_year = ''
                m = re.search(r'(19\d{2}|20\d{2})', text)
                if m:
                    result_year = m.group(1)

                # If looking for episode, try to give show URL first when present
                url_out = href
                if video_type == VIDEO_TYPES.EPISODE and is_episode and not is_show:
                    # Keep episode href as-is if we cannot find show
                    pass

                results.append({
                    'title': text or title,
                    'year': result_year or year,
                    'url': url_out
                })

            # De-duplicate, keep first unique URLs
            seen = set()
            dedup = []
            for r in results:
                u = r['url']
                if u not in seen:
                    seen.add(u)
                    # Ensure we return a path fragment relative to site
                    r['url'] = scraper_utils.pathify_url(u)
                    dedup.append(r)
            results = dedup
            logger.log(f'[AZSeries] Search found {len(results)} results', log_utils.LOGDEBUG)
        except Exception as e:
            logger.log(f'[AZSeries] Search error: {e}', log_utils.LOGWARNING)
        return results

    def get_url(self, video):
        """
        Prefer constructing the direct player page URL for azseries.org to avoid
        missing results from site search. Fallback to default behavior if needed.
        """
        try:
            title = getattr(video, 'title', '') or ''
            year = getattr(video, 'year', '') or ''
            season = getattr(video, 'season', '') or ''
            episode = getattr(video, 'episode', '') or ''

            def slugify(s):
                s = (s or '').lower()
                # Replace non-alphanumeric with hyphens
                s = re.sub(r'[^a-z0-9]+', '-', s)
                s = re.sub(r'-{2,}', '-', s).strip('-')
                return s

            if video.video_type == VIDEO_TYPES.EPISODE and title and season and episode:
                base_slug = slugify(title)
                # ex: /episodes/the-x-files-season-1-episode-1/
                path = f"/episodes/{base_slug}-season-{int(season)}-episode-{int(episode)}/"
                return path

            if video.video_type == VIDEO_TYPES.MOVIE and title and year:
                base_slug = slugify(title)
                # ex: /movie/nobody-2-2025/ or /movie/some-movie-2025/
                path = f"/movie/{base_slug}-{year}/"
                return path
        except Exception:
            pass

        # Fallback to default which uses search and caches related URLs
        return self._default_get_url(video)

    def _get_episode_url(self, show_url, video):
        try:
            if not show_url:
                return None
            url = scraper_utils.urljoin(self.base_url, show_url)
            html = self._http_get_alt(url, cache_limit=2)
            if not html:
                return None

            # Pattern 1: /episodes/<slug>-season-<s>-episode-<e>
            s = int(video.season)
            e = int(video.episode)
            patt = rf'href=["\']([^"\']*/episodes/[^"\']*season-0?{s}[^"\']*episode-0?{e}[^"\']*)["\']'
            m = re.search(patt, html, re.IGNORECASE)
            if m:
                return scraper_utils.pathify_url(m.group(1))

            # Pattern 2: generic SxxExx URLs
            patt2 = rf'href=["\']([^"\']*s{int(video.season):02d}e{int(video.episode):02d}[^"\']*)["\']'
            m2 = re.search(patt2, html, re.IGNORECASE)
            if m2:
                return scraper_utils.pathify_url(m2.group(1))

            # Pattern 3: Title-based episode links
            if video.ep_title:
                norm_ep = scraper_utils.normalize_title(video.ep_title)
                for href, text in re.findall(r'href=["\']([^"\']+)["\'][^>]*>([^<]+)<', html, re.I):
                    if scraper_utils.normalize_title(text) == norm_ep:
                        return scraper_utils.pathify_url(href)
        except Exception as e:
            logger.log(f'[AZSeries] _get_episode_url error: {e}', log_utils.LOGDEBUG)
        return None

    # -----------------------------
    # Helpers
    # -----------------------------
    def _extract_post_id(self, html):
        patterns = [
            r'postid-(\d+)',
            r'data-post=[\'\"](\d+)[\'\"]',
            r'post\s*[:=]\s*[\'\"]?(\d+)[\'\"]?',
            r'movie[_-]?id\s*[:=]\s*[\'\"]?(\d+)[\'\"]?',
        ]
        for patt in patterns:
            m = re.search(patt, html, re.IGNORECASE)
            if m:
                return m.group(1)
        return None

    def _extract_nonce(self, html):
        candidates = []
        for patt, keyname in [
            (r'data-nonce=[\'\"]([A-Za-z0-9]+)[\'\"]', 'nonce'),
            (r'["\']nonce["\']\s*[:=]\s*[\'\"]([A-Za-z0-9]+)[\'\"]', 'nonce'),
            (r'["\']security["\']\s*[:=]\s*[\'\"]([A-Za-z0-9]+)[\'\"]', 'security'),
            (r'_wpnonce\s*value=[\'\"]([A-Za-z0-9]+)[\'\"]', '_wpnonce'),
        ]:
            m = re.search(patt, html, re.IGNORECASE)
            if m:
                candidates.append((m.group(1), keyname))
        if candidates:
            for val, key in candidates:
                if key == 'nonce':
                    return val, key
            return candidates[0]
        return None, None

    def _dooplay_rest_request(self, post_id, data_nume, referer_url):
        try:
            headers = {
                'Referer': referer_url,
                'User-Agent': scraper_utils.get_ua(),
                'Accept': 'application/json, text/plain, */*'
            }
            n = str(data_nume)
            endpoints = [
                f'/wp-json/dooplayer/v1/post/?id={post_id}&nume={n}',
                f'/wp-json/dooplayer/v1/embed/?post={post_id}&nume={n}',
                f'/wp-json/dooplay/v1/post/?id={post_id}&nume={n}',
                f'/wp-json/doo/v1/post/?id={post_id}&nume={n}',
            ]
            for ep in endpoints:
                url = scraper_utils.urljoin(self.base_url, ep)
                resp = self._http_get_alt(url, headers=headers, cache_limit=0)
                if not resp:
                    continue
                data = None
                try:
                    data = json.loads(resp)
                except Exception:
                    data = None
                if isinstance(data, dict):
                    embed = data.get('embed_url') or data.get('url') or ''
                    if not embed:
                        html_part = data.get('html') or data.get('iframe') or ''
                        if html_part:
                            m = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', html_part, re.I)
                            if m:
                                embed = m.group(1)
                    if embed:
                        if embed.startswith('//'):
                            embed = 'https:' + embed
                        return embed
                else:
                    m = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', resp, re.I)
                    if m:
                        embed = m.group(1)
                        if embed.startswith('//'):
                            embed = 'https:' + embed
                        return embed
        except Exception:
            return None
        return None

    def _extract_dooplay_ajax_sources(self, html, referer_url, video):
        sources = []
        try:
            nonce, nonce_key = self._extract_nonce(html)
            # Find player options li/anchor blocks which include data-type, data-post, data-nume
            items = re.findall(r'<li[^>]*id=[\'\"]player-option[^>]*>(.*?)</li>', html, re.DOTALL | re.IGNORECASE)
            if not items:
                # Some themes wrap in anchor directly
                items = re.findall(r'<a[^>]*data-type=[\'\"](.*?)[\'\"][^>]*data-post=[\'\"](\d+)[\'\"][^>]*data-nume=[\'\"](\d+)[\'\"][^>]*>', html, re.I)
                if items:
                    # items as tuples already
                    for data_type, data_post, data_nume in items:
                        embed = self._dooplay_ajax_request(data_type, data_post, data_nume, referer_url, nonce, nonce_key)
                        if embed:
                            self._append_server_source(sources, embed, video)
                    # Even if we found some, continue to try fallbacks for more servers

            for result in items or []:
                # English-only preference if language icon present
                if '/en.png' in result and '/en.' not in result:
                    pass  # Keep; if site uses other language filters, extend here
                # Extract tuples inside
                ajax_matches = re.findall(r'data-type=[\'\"](.+?)[\'\"]\s+data-post=[\'\"](\d+)[\'\"]\s+data-nume=[\'\"](\d+)[\'\"]', result, re.DOTALL)
                for data_type, data_post, data_nume in ajax_matches:
                    embed = self._dooplay_ajax_request(data_type, data_post, data_nume, referer_url, nonce, nonce_key)
                    if embed:
                        self._append_server_source(sources, embed, video)

            # Fallback: brute-force DooPlay-style AJAX using post ID if present
            if not sources:
                # Gather post IDs and nume/type candidates from any element
                post_ids = []
                try:
                    soup = BeautifulSoup(html, 'html.parser')
                    for el in soup.find_all(attrs={'data-post': True}):
                        pid = el.get('data-post')
                        if pid and pid.isdigit():
                            post_ids.append(pid)
                except Exception:
                    pass
                if not post_ids:
                    m_pid = self._extract_post_id(html)
                    if m_pid:
                        post_ids = [m_pid]
                # Collect nume candidates from markup
                numes = set()
                for n in re.findall(r'data-nume=[\'\"](\d+)[\'\"]', html):
                    try:
                        numes.add(int(n))
                    except Exception:
                        pass
                if not numes:
                    numes = set(range(1, 10))
                # Collect type candidates from markup
                types = set()
                for t in re.findall(r'data-type=[\'\"]([a-zA-Z0-9_-]+)[\'\"]', html):
                    types.add(t)
                if not types:
                    types = set(['movie', 'tv', 'episode', 'iframe', 'player'])
                # Try combos
                for post_id in post_ids[:2]:  # limit attempts
                    for data_type in sorted(types):
                        for data_nume in sorted(numes):
                            embed = self._dooplay_ajax_request(data_type, post_id, str(data_nume), referer_url, nonce, nonce_key)
                            if embed:
                                self._append_server_source(sources, embed, video)
            # If still no sources, try REST endpoints as a fallback
            if not sources:
                pid = self._extract_post_id(html)
                if pid:
                    tried = set()
                    for n in sorted(list(numes)) if 'numes' in locals() and numes else range(1, 10):
                        if n in tried:
                            continue
                        tried.add(n)
                        embed = self._dooplay_rest_request(pid, n, referer_url)
                        if embed:
                            self._append_server_source(sources, embed, video)
        except Exception as e:
            logger.log(f'[AZSeries] DooPlay AJAX parse error: {e}', log_utils.LOGDEBUG)
        return sources

    def _dooplay_ajax_request(self, data_type, data_post, data_nume, referer_url, nonce=None, nonce_key=None):
        try:
            ajax_url = scraper_utils.urljoin(self.base_url, '/wp-admin/admin-ajax.php')
            headers = {
                'Origin': self.base_url,
                'Referer': referer_url,
                'X-Requested-With': 'XMLHttpRequest',
                'User-Agent': scraper_utils.get_ua(),
                'Accept': '*/*'
            }
            payload = {
                'post': data_post,
                'nume': data_nume,
                'type': data_type,
            }
            if nonce:
                keyname = nonce_key if nonce_key in ('nonce', 'security', '_wpnonce', '_nonce') else 'nonce'
                payload[keyname] = nonce

            # Try a few common action names
            actions = ['doo_player_ajax', 'player_ajax', 'muvipro_player_ajax']
            for action in actions:
                payload['action'] = action
                resp = self._http_get_alt(ajax_url, method='POST', headers=headers, data=payload, cache_limit=0)
                if not resp:
                    continue

                # Some themes return JSON, others return HTML with iframe
                try:
                    data = json.loads(resp)
                except Exception:
                    data = None

                if isinstance(data, dict):
                    embed = data.get('embed_url') or data.get('url') or ''
                    if embed:
                        embed = embed.replace('\\', '')
                        if embed.startswith('//'):
                            embed = 'https:' + embed
                        if embed.startswith('http'):
                            logger.log(f'[AZSeries] AJAX embed via {action}: {embed}', log_utils.LOGDEBUG)
                            return embed
                else:
                    # Parse iframe src from HTML
                    m = re.search(r'<iframe[^>]+src=["\']([^"\']+)["\']', resp, re.I)
                    if m:
                        embed = m.group(1)
                        if embed.startswith('//'):
                            embed = 'https:' + embed
                        logger.log(f'[AZSeries] AJAX iframe via {action}: {embed}', log_utils.LOGDEBUG)
                        return embed
        except Exception as e:
            logger.log(f'[AZSeries] AJAX request error: {e}', log_utils.LOGDEBUG)
        return None

    def _append_server_source(self, sources, link, video):
        try:
            # Normalize link
            url = link.strip()
            if not url:
                return
            if not url.startswith('http'):
                url = scraper_utils.urljoin(self.base_url, url)

            host = urllib.parse.urlparse(url).hostname or self.get_name()

            # Determine quality using blog_get_quality when available
            post_quality = None
            try:
                if hasattr(scraper_utils, 'blog_get_quality'):
                    post_quality = scraper_utils.blog_get_quality(video, url, host)
            except Exception:
                post_quality = None

            if post_quality is None:
                # Fallback heuristics
                u = url.upper()
                if '4K' in u or '2160' in u:
                    post_quality = QUALITIES.HD4K
                elif '1080' in u:
                    post_quality = QUALITIES.HD1080
                elif '720' in u:
                    post_quality = QUALITIES.HD720
                elif any(x in u for x in ['HDRIP', 'DVDRIP', 'BDRIP', '480P', 'HDTV']):
                    post_quality = QUALITIES.HIGH
                else:
                    post_quality = QUALITIES.HIGH

            quality = scraper_utils.get_quality(video, host, post_quality)

            source = {
                'class': self,
                'multi-part': False,
                'host': host,
                'quality': quality,
                'views': None,
                'rating': None,
                'url': url,
                'direct': False,
            }
            sources.append(source)
            logger.log(f'[AZSeries] Added source: {host} -> {url}', log_utils.LOGDEBUG)
        except Exception as e:
            logger.log(f'[AZSeries] _append_server_source error: {e}', log_utils.LOGDEBUG)
