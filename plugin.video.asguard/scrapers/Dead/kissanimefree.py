"""
    Asguard Addon
    KissAnimeFree Scraper
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

from asguard_lib import scraper_utils
from asguard_lib.constants import VIDEO_TYPES, QUALITIES
from . import scraper
import log_utils
import kodi

# AniList integration for robust title handling
try:
    from asguard_lib.anilist import anilist_api
except Exception:
    anilist_api = None

logger = log_utils.Logger.get_logger()
BASE_URL = 'https://w1.kissanimefree.cc'

class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url') or BASE_URL
        self.domains = ['kissanimefree.cc', 'w1.kissanimefree.cc', 'kissanime.cc']

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'KissAnimeFree'

    def get_sources(self, video):
        logger.log(f'[KISSANIMEFREE] get_sources: {video.title} S{video.season}E{video.episode}', log_utils.LOGDEBUG)
        sources = []
        source_url = self.get_url(video)

        if not source_url or source_url == scraper_utils.FORCE_NO_MATCH:
            logger.log(f'[KISSANIMEFREE] No source URL for video: {video}', log_utils.LOGWARNING)
            return sources

        url = scraper_utils.urljoin(self.base_url, source_url)
        logger.log(f'[KISSANIMEFREE] Fetching page: {url}', log_utils.LOGDEBUG)
        html = self._http_get(url, cache_limit=1)
        if not html:
            logger.log('[KISSANIMEFREE] Empty HTML', log_utils.LOGWARNING)
            return sources

        # Try JWPlayer-like "sources" block first (rare but cheap to check)
        try:
            parsed_sources = self._parse_sources_list(html)
            for stream_url, meta in parsed_sources.items():
                src = self._make_source(stream_url, label='JW', direct=meta.get('direct', True), quality=meta.get('quality'))
                if src:
                    sources.append(src)
        except Exception as e:
            logger.log(f'[KISSANIMEFREE] _parse_sources_list error: {e}', log_utils.LOGDEBUG)

        try:
            soup = BeautifulSoup(html, 'html.parser')

            # Collect server candidates from typical gogoanime-style markup
            server_candidates = self._collect_server_candidates(soup, html)
            logger.log(f'[KISSANIMEFREE] Server candidates found: {len(server_candidates)}', log_utils.LOGDEBUG)

            for candidate in server_candidates:
                stream_url = candidate.get('url')
                label = candidate.get('label')
                src = self._make_source(stream_url, label=label)
                if src:
                    sources.append(src)

            # Fallback: embedded iframes
            iframes = soup.find_all('iframe', src=True)
            for iframe in iframes:
                stream_url = iframe['src']
                src = self._make_source(stream_url, label='Iframe')
                if src:
                    sources.append(src)

            # Fallback: scan for ajax/embed endpoints and resolve
            ajax_patterns = [r'/ajax/[^"\']+', r'/api/[^"\']+', r'/embed/[^"\']+']
            for pattern in ajax_patterns:
                for rel in re.findall(pattern, html):
                    try:
                        test_url = scraper_utils.urljoin(self.base_url, rel)
                        data_html = self._http_get(test_url, cache_limit=0.25)
                        if not data_html:
                            continue
                        # Try JSON first
                        try:
                            data = json.loads(data_html)
                            for key in ('file', 'link', 'url', 'source'):
                                su = data.get(key)
                                if isinstance(su, str) and su.startswith('http'):
                                    src = self._make_source(su, label='ajax', direct=True)
                                    if src:
                                        sources.append(src)
                        except Exception:
                            # Regex scan for http links
                            for su in re.findall(r'"(https?://[^"\\]+)"', data_html):
                                src = self._make_source(su, label='ajax-scan', direct=True)
                                if src:
                                    sources.append(src)
                    except Exception:
                        continue

        except Exception as e:
            logger.log(f'[KISSANIMEFREE] Parsing error: {e}', log_utils.LOGERROR)

        logger.log(f'[KISSANIMEFREE] Found {len(sources)} sources', log_utils.LOGDEBUG)
        return sources

    def _collect_server_candidates(self, soup, html):
        """
        Collect potential server/embed URLs from common patterns used by kissanime/gogoanime clones.
        Returns a list of dicts with {'url': ..., 'label': ...}
        """
        candidates = []

        def add(url, label=''):
            try:
                if not url:
                    return
                u = url.strip()
                if u.startswith('//'):
                    u = 'https:' + u
                elif u.startswith('/'):
                    u = scraper_utils.urljoin(self.base_url, u)
                if not u.startswith('http'):
                    return
                candidates.append({'url': u, 'label': label})
            except Exception:
                pass

        # Pattern 1: li/link elements with data-video (gogoanime style)
        for li in soup.select('li.linkserver, li.link-server, li.server-item, a.server-item, a.linkserver, div.server-item, div.mirror_link a'):
            for attr in ('data-video', 'data-src', 'data-url', 'data-embed', 'data-href'):
                if li.has_attr(attr):
                    add(li[attr], label=li.get_text(strip=True) or attr)
                    break

        # Pattern 2: any element with data-video/src/url/embed attributes
        for el in soup.find_all(lambda t: any(a in t.attrs for a in ('data-video', 'data-src', 'data-url', 'data-embed', 'data-href'))):
            for attr in ('data-video', 'data-src', 'data-url', 'data-embed', 'data-href'):
                if el.has_attr(attr):
                    add(el.get(attr), label=el.get('title', '') or el.get_text(strip=True) or attr)
                    break

        # Pattern 3: onclick handlers that pass embed URL
        for btn in soup.find_all(attrs={'onclick': True}):
            onclick = btn.get('onclick') or ''
            m = re.search(r"['\"](https?://[^'\"]+)['\"]", onclick)
            if m:
                add(m.group(1), label=btn.get_text(strip=True) or 'onclick')

        # Pattern 4: direct regex scan for data-video/data-src in HTML
        for pattern in (r'data-video=["\']([^"\']+)["\']', r'data-src=["\']([^"\']+)["\']', r'data-url=["\']([^"\']+)["\']'):
            for match in re.findall(pattern, html, flags=re.IGNORECASE):
                add(match, label='data-attr')

        # Pattern 5: known server list containers
        for container in soup.select('#list-server-more li, ul#servers li, .server_list li, .list-server-more li'):
            data = container.get('data-video') or container.get('data-src') or container.get('data-url')
            if data:
                add(data, label=container.get_text(strip=True))

        # Deduplicate while preserving order
        seen = set()
        uniq = []
        for c in candidates:
            key = c['url']
            if key not in seen:
                seen.add(key)
                uniq.append(c)
        return uniq

    def _make_source(self, stream_url, label='', direct=False, quality=None):
        try:
            if not stream_url:
                return None
            u = stream_url.strip()
            if u.startswith('//'):
                u = 'https:' + u
            elif u.startswith('/'):
                u = scraper_utils.urljoin(self.base_url, u)
            if not u.startswith('http'):
                return None

            host = urllib.parse.urlparse(u).hostname
            if not host:
                return None

            if quality is None:
                quality = self._determine_quality_from_url(u)

            return {
                'class': self,
                'quality': quality,
                'url': u,
                'host': host,
                'multi-part': False,
                'rating': None,
                'views': None,
                'direct': direct,
                'extra': label
            }
        except Exception:
            return None

    def _determine_quality_from_url(self, url):
        u = url.lower()
        if any(q in u for q in ['1080', 'fhd']):
            return QUALITIES.HD1080
        if any(q in u for q in ['720', 'hd']):
            return QUALITIES.HD720
        if '480' in u:
            return QUALITIES.HIGH
        if '360' in u:
            return QUALITIES.MEDIUM
        if '240' in u:
            return QUALITIES.LOW
        return QUALITIES.HIGH

    def get_url(self, video):
        # Rely on default flow which caches show URL then resolves episode URL
        return self._default_get_url(video)

    def _get_episode_url(self, show_url, video):
        try:
            if not show_url:
                return None

            target_episode = int(video.episode)
            # Estimate absolute episode if multiple seasons
            if hasattr(video, 'season') and str(video.season).isdigit() and int(video.season) > 1:
                target_episode = (int(video.season) - 1) * 12 + int(video.episode)

            # If show_url already is an episode URL
            if re.search(r'/eps/\d+', show_url):
                return show_url

            # Fetch the show page and try to find specific episode link
            url = scraper_utils.urljoin(self.base_url, show_url)
            html = self._http_get(url, cache_limit=1)
            if html:
                # Direct match for episode link
                m = re.search(r'href=["\']([^"\']+/eps/(?:%s|0*%s))["\']' % (target_episode, target_episode), html)
                if m:
                    ep_url = m.group(1)
                    if ep_url.startswith('/'):
                        return ep_url
                    # Combine with base path
                    return urllib.parse.urljoin(show_url if show_url.endswith('/') else show_url + '/', urllib.parse.urlparse(ep_url).path)

            # Fallback: construct from slug
            # Expect show_url like /watch-anime/<slug>
            slug_match = re.search(r'/watch-anime/([^/?#]+)', show_url)
            if slug_match:
                slug = slug_match.group(1)
                candidates = [
                    f'/watch-anime/{slug}/eps/{target_episode}',
                ]
                # Try sub/dub variants
                if not slug.endswith('-sub'):
                    candidates.append(f'/watch-anime/{slug}-sub/eps/{target_episode}')
                if not slug.endswith('-dub'):
                    candidates.append(f'/watch-anime/{slug}-dub/eps/{target_episode}')

                for cand in candidates:
                    test_html = self._http_get(scraper_utils.urljoin(self.base_url, cand), cache_limit=0.25, read_error=True)
                    if test_html:
                        return cand

            return None
        except Exception as e:
            logger.log(f'[KISSANIMEFREE] _get_episode_url error: {e}', log_utils.LOGERROR)
            return None

    def search(self, video_type, title, year, season=''):
        logger.log(f'[KISSANIMEFREE] search: type={video_type} title={title} year={year}', log_utils.LOGDEBUG)
        results = []

        # Build candidate titles: use AniList if available
        candidate_titles = []
        try:
            # Clean given title
            if anilist_api:
                cleaned = anilist_api.clean_title_for_search(title)
                if cleaned:
                    candidate_titles.append(cleaned)
            if title not in candidate_titles:
                candidate_titles.append(title)
        except Exception:
            if title not in candidate_titles:
                candidate_titles.append(title)

        # Site search endpoints to try
        def _do_search(q):
            found = []
            sanitized_q = self._sanitize_search_query(q)
            search_urls = [
                f'{self.base_url}/search?keyword={urllib.parse.quote_plus(sanitized_q)}',
                f'{self.base_url}/search?q={urllib.parse.quote_plus(sanitized_q)}',
                f'{self.base_url}/?s={urllib.parse.quote_plus(sanitized_q)}',
            ]
            logger.log(f'[KISSANIMEFREE] Using sanitized search query: "{sanitized_q}"', log_utils.LOGDEBUG)
            logger.log(f'[KISSANIMEFREE] Search URLs: {search_urls}', log_utils.LOGDEBUG)
            for su in search_urls:
                try:
                    html = self._http_get(su, cache_limit=1)
                    if not html:
                        continue
                    soup = BeautifulSoup(html, 'html.parser')

                    # Prefer links that begin with /watch-anime/
                    for a in soup.find_all('a', href=True):
                        href = a['href']
                        text = a.get_text(strip=True) or ''

                        # Normalize URL to relative
                        if href.startswith(self.base_url):
                            href = href.replace(self.base_url, '')
                        if not href.startswith('/'):
                            continue

                        if not re.search(r'^/watch-anime/[^/]+/?$', href):
                            continue

                        # Filter out social or junk
                        if any(bad in href.lower() for bad in ['discord', 'twitter', 'reddit', 'telegram']):
                            continue

                        # Title
                        result_title = text
                        # Try to get better title from nested elements
                        if not result_title:
                            parent = a.find_parent(['div','article','li'])
                            if parent:
                                h = parent.find(['h2','h3','h4'])
                                if h:
                                    result_title = h.get_text(strip=True)
                        result_title = result_title or a.get('title') or ''

                        # Year filtering is weak for anime; accept and let Asguard cache best
                        if self._title_matches(title, result_title):
                            found.append({
                                'title': result_title,
                                'year': year,
                                'url': href
                            })
                except Exception as e:
                    logger.log(f'[KISSANIMEFREE] search endpoint error: {e}', log_utils.LOGDEBUG)
            return found

        for q in candidate_titles:
            items = _do_search(q)
            for it in items:
                if it not in results:
                    results.append(it)
            if results:
                break  # stop after first non-empty query

        # If still nothing, try constructing direct slug and probing
        if not results and candidate_titles:
            slug = self._clean_title_for_slug(candidate_titles[0])
            for variant in [slug, f'{slug}-sub', f'{slug}-dub']:
                path = f'/watch-anime/{variant}'
                html = self._http_get(scraper_utils.urljoin(self.base_url, path), cache_limit=0.25, read_error=True)
                if html:
                    results.append({'title': candidate_titles[0], 'year': year, 'url': path})
                    break

        logger.log(f'[KISSANIMEFREE] search results: {len(results)}', log_utils.LOGDEBUG)
        return results

    def _clean_title_for_slug(self, title):
        try:
            if hasattr(scraper_utils, 'to_slug'):
                return scraper_utils.to_slug(title)
        except Exception:
            pass
        # fallback
        t = title.lower()
        t = re.sub(r"[^\w\s-:]", '', t)
        t = re.sub(r"[\s:]+", '-', t)
        t = re.sub(r"-+", '-', t).strip('-')
        return t

    def _sanitize_search_query(self, q):
        """
        Site-specific search sanitization:
        - lowercase
        - remove punctuation like dots, apostrophes, commas, etc.
        - collapse whitespace
        - keep alphanumerics and spaces so `quote_plus` turns them into +
        """
        if not q:
            return q
        # normalize to lowercase for more consistent site behavior
        q = str(q).lower()
        # remove most punctuation characters that hurt site search
        q = re.sub(r"[\.!?,:'\"\-_/\\()\[\]{}]", ' ', q)
        # also normalize dots in abbreviations (e.g., "Dr.")
        q = q.replace('.', ' ')
        # collapse whitespace
        q = re.sub(r"\s+", ' ', q).strip()
        return q

    def _title_matches(self, search_title, result_title):
        search_lower = (search_title or '').lower()
        result_lower = (result_title or '').lower()
        if not search_lower or not result_lower:
            return False
        if search_lower == result_lower:
            return True
        if search_lower in result_lower or result_lower in search_lower:
            return True
        s_words = set(search_lower.split())
        r_words = set(result_lower.split())
        return len(s_words & r_words) >= max(1, int(len(s_words) * 0.5))

    def resolve_link(self, link):
        try:
            # If it's an AJAX endpoint, attempt to resolve to final URL
            if '/ajax/' in link or '/api/' in link:
                html = self._http_get(link, cache_limit=0.25)
                if html:
                    try:
                        data = json.loads(html)
                        for key in ('file', 'link', 'url', 'source'):
                            if key in data and str(data[key]).startswith('http'):
                                return data[key]
                    except Exception:
                        pass
            return link
        except Exception as e:
            logger.log(f'[KISSANIMEFREE] resolve_link error: {e}', log_utils.LOGERROR)
            return link
