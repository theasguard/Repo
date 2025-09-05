"""
    Asguard Addon - Vidbox Scraper
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
from asguard_lib.constants import VIDEO_TYPES
from . import scraper
import log_utils
import kodi

logger = log_utils.Logger.get_logger()
BASE_URL = 'https://vidbox.to'


class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        # Allow overriding via settings
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url') or BASE_URL
        self.domains = ['vidbox.to']
        # Aggregator domains that we should deep-parse to reveal real hosters
        self.aggregator_hosts = [
            'dl.vidsrc.vip', 'vidsrc.vip', 'vidsrc.to', 'vidsrc.pro', 'vidsrc.xyz', 'vidsrc.stream'
        ]

    @classmethod
    def provides(cls):
        # Vidbox pages exist for movies and TV episodes
        return frozenset([VIDEO_TYPES.MOVIE, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'Vidbox'

    # ------------------ Public API ------------------
    def get_sources(self, video):
        sources = []
        source_url = self.get_url(video)
        if not source_url or source_url == scraper_utils.FORCE_NO_MATCH:
            logger.log(f'[Vidbox] No source URL for video: {video}', log_utils.LOGWARNING)
            return sources

        url = scraper_utils.urljoin(self.base_url, source_url)
        logger.log(f'[Vidbox] Fetching URL: {url}', log_utils.LOGDEBUG)
        html = self._http_get(url, cache_limit=1)
        if not html:
            logger.log('[Vidbox] Empty HTML', log_utils.LOGWARNING)
            return sources

        # 1) Direct player sources on main page (JW/Clappr style)
        try:
            parsed_sources = self._parse_sources_list(html)
            for stream_url, meta in parsed_sources.items():
                host = urllib.parse.urlparse(stream_url).hostname or 'vidbox'
                quality = meta.get('quality') or scraper_utils.blog_get_quality(video, stream_url, host)
                sources.append({
                    'class': self,
                    'quality': quality,
                    'url': stream_url,
                    'host': host,
                    'multi-part': False,
                    'rating': None,
                    'views': None,
                    'direct': meta.get('direct', False),
                })
        except Exception as e:
            logger.log(f'[Vidbox] _parse_sources_list error: {e}', log_utils.LOGDEBUG)

        soup = BeautifulSoup(html, 'html.parser')

        # 2) Pull candidate links from DOM (iframes, data-*, onclick, scripts)
        candidate_urls = set()
        candidate_urls.update(self._collect_iframe_urls(soup, self.base_url))
        candidate_urls.update(self._collect_data_attribute_urls(soup, self.base_url))
        candidate_urls.update(self._collect_onclick_urls(html))
        candidate_urls.update(self._collect_script_json_urls(html))
        candidate_urls.update(self._collect_anchor_urls(html, self.base_url))

        # 3) Attempt to fetch Next.js data JSON for this page using buildId
        try:
            build_id = self._extract_next_build_id(html)  # e.g., 'iVzyt2DcDJRDuSs9_Gpz2'
            page_path = self._build_next_data_path(video)
            if build_id and page_path:
                next_json_url = scraper_utils.urljoin(self.base_url, f'/_next/data/{build_id}{page_path}.json')
                jtxt = self._http_get_alt(next_json_url, cache_limit=0, use_flaresolver=True)
                urls = self._try_extract_json_urls(jtxt or '', base_url=self.base_url)
                candidate_urls.update(urls)
        except Exception as e:
            logger.log(f'[Vidbox] Next data fetch failed: {e}', log_utils.LOGDEBUG)

        # 4) Probe common internal endpoints (best-effort)
        try:
            ids = self.get_all_ids(video) or {}
            tmdb_id = ids.get('tmdb')
        except Exception:
            tmdb_id = None
        ajax_candidates = self._guess_ajax_endpoints(tmdb_id, video)
        for aurl in ajax_candidates:
            try:
                body = self._http_get_alt(aurl, cache_limit=0, use_flaresolver=True)
                if not body:
                    continue
                urls = self._try_extract_json_urls(body, base_url=self.base_url)
                if not urls:
                    urls.update(set(re.findall(r'href=[\"\'](https?://[^\"\']+)[\"\']', body, re.I)))
                    urls.update(set(re.findall(r'src=[\"\'](https?://[^\"\']+)[\"\']', body, re.I)))
                for u in urls:
                    normalized = self._normalize_url(u, base_url=self.base_url)
                    if normalized:
                        candidate_urls.add(normalized)
            except Exception as e:
                logger.log(f'[Vidbox] AJAX probe failed: {e}', log_utils.LOGDEBUG)

        # 5) Generate known embed URLs (vidsrc.*) using TMDB IDs and expand
        embed_candidates = self._generate_known_embeds(tmdb_id, video)
        candidate_urls.update(embed_candidates)

        # 6) Deep-parse both same-domain and aggregator domains
        deep_urls = set()
        for cu in list(candidate_urls):
            host = urllib.parse.urlparse(cu).hostname or ''
            should_deep = any(d in host for d in self.domains) or any(h in host for h in self.aggregator_hosts)
            if not should_deep:
                continue
            try:
                ch = self._http_get_alt(cu, cache_limit=.25, use_flaresolver=True)
                if not ch:
                    continue
                # Parse nested sources/iframes
                ps = self._parse_sources_list(ch)
                for stream_url, meta in ps.items():
                    deep_urls.add(stream_url)
                deep_urls.update(self._collect_iframe_urls(BeautifulSoup(ch, 'html.parser'), self.base_url))
                # Also greedy URL scrape for known streaming hosts
                deep_urls.update(self._scan_for_known_hosts(ch))
            except Exception as e:
                logger.log(f'[Vidbox] Deep fetch error for {cu}: {e}', log_utils.LOGDEBUG)
        candidate_urls.update(deep_urls)

        # 7) Convert all candidate URLs to sources
        for href in candidate_urls:
            try:
                host = urllib.parse.urlparse(href).hostname
                if not host:
                    continue
                # Skip self pages without embed paths
                if any(d in host for d in self.domains) and '/embed' not in href and '/player' not in href:
                    continue
                quality = scraper_utils.blog_get_quality(video, href, host)
                sources.append({
                    'class': self,
                    'quality': quality,
                    'url': href,
                    'host': host,
                    'multi-part': False,
                    'rating': None,
                    'views': None,
                    'direct': False,
                })
            except Exception:
                continue

        # De-duplicate by URL while keeping insertion order
        seen = set()
        uniq = []
        for s in sources:
            if s['url'] in seen:
                continue
            seen.add(s['url'])
            uniq.append(s)
        logger.log(f'[Vidbox] Returning {len(uniq)} sources (from {len(candidate_urls)} candidates)', log_utils.LOGDEBUG)
        return uniq

    def get_url(self, video):
        """
        Build a watch URL using TMDB IDs detected via Trakt mapping.
        Examples:
        - Movie:  /watch/movie/<tmdb>
        - TV Ep:  /watch/tv/<tmdb>?season=S&episode=E
        - TVShow: /watch/tv/<tmdb>
        """
        try:
            ids = self.get_all_ids(video) or {}
            tmdb_id = ids.get('tmdb')
            if not tmdb_id:
                logger.log(f'[Vidbox] Missing TMDB ID for {video}', log_utils.LOGWARNING)
                return None

            if video.video_type == VIDEO_TYPES.MOVIE:
                return f'/watch/movie/{tmdb_id}'
            elif video.video_type == VIDEO_TYPES.EPISODE:
                s = int(getattr(video, 'season', 0) or 0)
                e = int(getattr(video, 'episode', 0) or 0)
                if s and e:
                    return f'/watch/tv/{tmdb_id}?season={s}&episode={e}'
                # Fallback to series page if S/E missing
                return f'/watch/tv/{tmdb_id}'
            elif video.video_type == VIDEO_TYPES.TVSHOW:
                return f'/watch/tv/{tmdb_id}'
        except Exception as e:
            logger.log(f'[Vidbox] get_url error: {e}', log_utils.LOGERROR)
        return None

    def search(self, video_type, title, year, season=''):
        """
        Vidbox uses TMDB-backed IDs in its watch URLs. We can only build a
        deterministic URL when we have the Trakt mapping (via get_url(video)).
        For the generic search() contract, return an empty list; get_url() is
        the primary path used by this scraper.
        """
        logger.log(f'[Vidbox] search not used: type={video_type}, title={title}, year={year}, season={season}', log_utils.LOGDEBUG)
        return []

    def resolve_link(self, link):
        # Ensure absolute URL if relative is passed
        if not link.startswith('http'):
            return scraper_utils.urljoin(self.base_url, link)
        return link

    # ------------------ Helpers ------------------
    def _normalize_url(self, url, base_url):
        try:
            if not url:
                return None
            if url.startswith('//'):
                return 'https:' + url
            if url.startswith('/'):
                return scraper_utils.urljoin(base_url, url)
            return url if url.startswith('http') else None
        except Exception:
            return None

    def _collect_iframe_urls(self, soup, base_url):
        urls = set()
        try:
            for iframe in soup.find_all('iframe'):
                for key in ('src', 'data-src'):
                    val = iframe.get(key)
                    if not val:
                        continue
                    norm = self._normalize_url(val, base_url)
                    if norm:
                        urls.add(norm)
        except Exception:
            pass
        return urls

    def _collect_data_attribute_urls(self, soup, base_url):
        urls = set()
        try:
            # Search broadly for elements with common data-* attributes used by players
            data_keys = ['data-href', 'data-src', 'data-url', 'data-link', 'data-embed', 'data-file']
            for tag in soup.find_all(True):
                for key in data_keys:
                    if key in tag.attrs:
                        val = tag.attrs.get(key)
                        norm = self._normalize_url(val, base_url)
                        if norm:
                            urls.add(norm)
        except Exception:
            pass
        return urls

    def _collect_onclick_urls(self, html):
        urls = set()
        try:
            # window.open('...') patterns
            for m in re.finditer(r"window\.open\(['\"](https?://[^'\"]+)['\"]", html):
                urls.add(m.group(1))
            # Generic function call with URL literal
            for m in re.finditer(r"\(['\"](https?://[^'\"]+)['\"]\)", html):
                urls.add(m.group(1))
        except Exception:
            pass
        return urls

    def _collect_script_json_urls(self, html):
        urls = set()
        try:
            # Look for JSON-like arrays containing server name/url/link fields
            # Example: [{"name":"Vidfast","url":"https://..."}]
            for m in re.finditer(r"[{,]\s*\"(name|server)\"\s*:\s*\"[^\"]*\"\s*,\s*\"(url|link|file|embed)\"\s*:\s*\"([^\"]+)\"", html):
                urls.add(m.group(3))
            # Also capture bare JSON arrays/objects and scan them
            for m in re.finditer(r"(\[\s*{.*?}\s*\])", html, re.DOTALL):
                frag = m.group(1)
                urls.update(self._try_extract_json_urls(frag, base_url=self.base_url))
            for m in re.finditer(r"(\{\s*\"[a-zA-Z0-9_]+\"\s*:\s*.*?\})", html, re.DOTALL):
                frag = m.group(1)
                urls.update(self._try_extract_json_urls(frag, base_url=self.base_url))
            # Flight data chunks (__next_f.push) may contain escaped JSON with URLs
            for m in re.finditer(r"__next_f\.push\(\[[^\]]+\]\)", html):
                urls.update(set(re.findall(r"https?://[^'\"\s<>]+", m.group(0))))
        except Exception:
            pass
        # Normalize
        return set(self._normalize_url(u, self.base_url) for u in urls if u)

    def _collect_anchor_urls(self, html, base_url):
        urls = set()
        try:
            for m in re.finditer(r'href=[\"\']([^\"\']+)[\"\']', html, re.I):
                u = m.group(1)
                # Skip internal navigation links without http scheme
                norm = self._normalize_url(u, base_url)
                if norm:
                    urls.add(norm)
        except Exception:
            pass
        return urls

    def _try_extract_json_urls(self, text, base_url):
        out = set()
        try:
            if not text:
                return out
            t = text.strip()
            if t.startswith('{') or t.startswith('['):
                data = json.loads(t)
            else:
                # Attempt to find a JSON object/array within the text
                m = re.search(r"(\{.*\}|\[.*\])", t, re.DOTALL)
                if not m:
                    return out
                data = json.loads(m.group(1))
            out.update(self._extract_urls_from_json(data, base_url))
        except Exception:
            pass
        return out

    def _extract_urls_from_json(self, obj, base_url):
        urls = set()
        try:
            if isinstance(obj, dict):
                for k, v in obj.items():
                    if isinstance(v, (dict, list)):
                        urls.update(self._extract_urls_from_json(v, base_url))
                    elif isinstance(v, str):
                        norm = self._normalize_url(v, base_url)
                        if norm and (norm.startswith('http') or norm.startswith('https')):
                            urls.add(norm)
            elif isinstance(obj, list):
                for item in obj:
                    urls.update(self._extract_urls_from_json(item, base_url))
            elif isinstance(obj, str):
                norm = self._normalize_url(obj, base_url)
                if norm and (norm.startswith('http') or norm.startswith('https')):
                    urls.add(norm)
        except Exception:
            pass
        return urls

    def _guess_ajax_endpoints(self, tmdb_id, video):
        urls = []
        try:
            if not tmdb_id:
                return urls
            base = self.base_url.rstrip('/')
            if video.video_type == VIDEO_TYPES.EPISODE:
                s = int(getattr(video, 'season', 0) or 0)
                e = int(getattr(video, 'episode', 0) or 0)
                if s and e:
                    urls.append(f"{base}/api/episode/servers?tmdb={tmdb_id}&season={s}&episode={e}")
                    urls.append(f"{base}/api/v2/episode/servers?tmdb={tmdb_id}&season={s}&episode={e}")
                    urls.append(f"{base}/api/servers?type=tv&tmdb={tmdb_id}&season={s}&episode={e}")
            elif video.video_type == VIDEO_TYPES.MOVIE:
                urls.append(f"{base}/api/movie/servers?tmdb={tmdb_id}")
                urls.append(f"{base}/api/v2/movie/servers?tmdb={tmdb_id}")
                urls.append(f"{base}/api/servers?type=movie&tmdb={tmdb_id}")
        except Exception:
            pass
        return urls

    def _scan_for_known_hosts(self, html):
        urls = set()
        try:
            # Use resolveurl host list to discover embedded hosters
            host_list = set(self.getHostDict() or [])
            # Add extra common streaming hosts that may not appear in host list
            extra_hosts = {
                'filemoon', 'streamtape', 'dood', 'ok.ru', 'okru', 'mixdrop',
                'vidcloud', 'streamlare', 'mp4upload', 'voe.', 'uqload', 'vupload'
            }
            # Simple greedy URL scanner
            for m in re.finditer(r"https?://[^'\"\s<>]+", html):
                u = m.group(0)
                host = urllib.parse.urlparse(u).hostname or ''
                if not host:
                    continue
                # If host domain matches or endswith one of known hosts, add
                if any(h in host for h in host_list) or any(h in host for h in extra_hosts):
                    urls.add(u)
        except Exception:
            pass
        return urls

    def _extract_next_build_id(self, html):
        try:
            # Inlined flight data contains a token like: '"b":"iVzyt2DcDJRDuSs9_Gpz2"'
            m = re.search(r'\"b\":\"([A-Za-z0-9_-]+)\"', html)
            if m:
                return m.group(1)
            # Fallback: search for /_next/static/ build assets and infer build id
            m2 = re.search(r"/_next/static/([^/]+)/", html)
            if m2:
                return m2.group(1)
        except Exception:
            pass
        return ''

    def _build_next_data_path(self, video):
        try:
            if video.video_type == VIDEO_TYPES.MOVIE:
                ids = self.get_all_ids(video) or {}
                tmdb_id = ids.get('tmdb')
                if tmdb_id:
                    return f"/watch/movie/{tmdb_id}"
            elif video.video_type == VIDEO_TYPES.EPISODE:
                ids = self.get_all_ids(video) or {}
                tmdb_id = ids.get('tmdb')
                s = int(getattr(video, 'season', 0) or 0)
                e = int(getattr(video, 'episode', 0) or 0)
                if tmdb_id:
                    if s and e:
                        # Query params might not be used by Next data, but include path base
                        return f"/watch/tv/{tmdb_id}"
                    return f"/watch/tv/{tmdb_id}"
        except Exception:
            pass
        return ''

    def _generate_known_embeds(self, tmdb_id, video):
        urls = set()
        try:
            if not tmdb_id:
                return urls
            if video.video_type == VIDEO_TYPES.MOVIE:
                # vidsrc variants
                urls.add(f'https://vidsrc.to/embed/movie?tmdb={tmdb_id}')
                urls.add(f'https://vidsrc.to/embed/movie/{tmdb_id}')
                urls.add(f'https://vidsrc.vip/embed/movie/{tmdb_id}')
                urls.add(f'https://vidsrc.pro/embed/movie/{tmdb_id}')
                urls.add(f'https://vidsrc.xyz/embed/movie/{tmdb_id}')
                urls.add(f'https://mapple.uk/watch/movie/{tmdb_id}?autoPlay=false&autoNext=false')
                urls.add(f'https://vidrock.net/embed/movie/{tmdb_id}')
                urls.add(f'https://player.videasy.net/movie/{tmdb_id}')
                urls.add(f'https://vidfast.pro/movie/{tmdb_id}?autoplay=true')
                # Direct download/aggregator spotted on page
                urls.add(f'https://dl.vidsrc.vip/movie/{tmdb_id}')
            elif video.video_type == VIDEO_TYPES.EPISODE:
                s = int(getattr(video, 'season', 0) or 0)
                e = int(getattr(video, 'episode', 0) or 0)
                if s and e:
                    urls.add(f'https://vidsrc.to/embed/tv?tmdb={tmdb_id}&season={s}&episode={e}')
                    urls.add(f'https://vidsrc.to/embed/tv/{tmdb_id}/{s}/{e}')
                    urls.add(f'https://vidsrc.vip/embed/tv/{tmdb_id}?season={s}&episode={e}')
                    urls.add(f'https://vidsrc.pro/embed/tv/{tmdb_id}?season={s}&episode={e}')
                    urls.add(f'https://vidsrc.xyz/embed/tv/{tmdb_id}/{s}/{e}')
                    urls.add(f'https://mapple.uk/watch/tv/{s}-{e}/{tmdb_id}?autoPlay=false&autoNext=false')
                    urls.add(f'https://vidrock.net/embed/tv/{tmdb_id}/{s}/{e}')
                    urls.add(f'https://player.videasy.net/tv/{tmdb_id}/{s}/{e}')
                    urls.add(f'https://vidfast.pro/tv/{tmdb_id}/{s}/{e}?autoplay=true')
        except Exception:
            pass
        return urls
