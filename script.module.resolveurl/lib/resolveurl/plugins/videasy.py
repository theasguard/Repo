"""
    Plugin for ResolveURL - Videasy
    Minimal resolver
"""
import re
import json
from resolveurl.lib import helpers
from resolveurl import common
from resolveurl.resolver import ResolveUrl, ResolverError


class VideasyResolver(ResolveUrl):
    name = 'Videasy'
    domains = ['player.videasy.net', 'videasy.net']
    # Capture the full path segment (embed|tv|movie) so get_url preserves it
    pattern = r'(?://|\.)((?:player\.)?videasy\.net)/((?:embed|tv|movie)/[^\s\"\'<>]+)'

    def get_url(self, host, media_id):
        return f'https://{host}/{media_id}'

    def get_media_url(self, host, media_id, subs=False):  # noqa: ARG002
        url = self.get_url(host, media_id)
        headers = {
            'User-Agent': common.FF_USER_AGENT,
            'Referer': f'https://{host}/'
        }
        html = self.net.http_GET(url, headers=headers).content

        # Try Next.js data endpoint to discover sources/embeds
        next_best = self._extract_next_data_url(html, host, headers)
        if next_best:
            return next_best

        # m3u8
        m3u8 = self._extract_m3u8(html)
        if m3u8:
            return m3u8 + helpers.append_headers(headers)
        # sources list
        src = self._extract_from_sources_list(html, headers)
        if src:
            return src
        # video tag
        src = self._extract_from_video_sources(html, headers)
        if src:
            return src
        # iframe
        iframe = self._extract_iframe(html, host)
        if iframe:
            return iframe

        raise ResolverError('Videasy: Video Link Not Found')

    def _extract_m3u8(self, html):
        for f in re.findall(r'https?://[^"\'\s<>]+\.m3u8[^"\'\s<>]*', html):
            return f
        return None

    def _extract_from_sources_list(self, html, headers):
        m = re.search(r'sources\s*:\s*\[(.*?)\]', html, re.S)
        if not m:
            m = re.search(r'sources\s*:\s*\{(.*?)\}', html, re.S)
        if not m:
            return None
        body = m.group(1)
        best = None
        for f, _label in re.findall(r"['\"]?file['\"]?\s*:\s*['\"]([^'\"]+)['\"]\s*(?:,\s*['\"]?label['\"]?\s*:\s*['\"][^'\"]*['\"])?,?", body):
            if f.startswith('//'):
                f = 'https:' + f
            if f.startswith('http'):
                best = f
        if best:
            return best + helpers.append_headers(headers)
        return None

    def _extract_from_video_sources(self, html, headers):
        for f in re.findall(r'<source[^>]+src=["\']([^"\']+)["\']', html, re.I):
            if f.startswith('//'):
                f = 'https:' + f
            if f.startswith('http'):
                return f + helpers.append_headers(headers)
        return None

    def _extract_iframe(self, html, self_host):
        for src in re.findall(r'<iframe[^>]+src=["\']([^"\']+)["\']', html, re.I):
            if src.startswith('//'):
                src = 'https:' + src
            if not src.startswith('http'):
                continue
            try:
                from urllib.parse import urlparse
                if urlparse(src).hostname and urlparse(src).hostname.endswith(self_host):
                    continue
            except Exception:
                pass
            return src
        return None

    def _extract_next_data_url(self, html, host, headers):
        """
        Parse __NEXT_DATA__ to fetch /_next/data/<buildId>/<path>.json and
        extract a playable or embedded URL.
        """
        try:
            m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(\{.*?\})</script>', html, re.S)
            if not m:
                return None
            data = json.loads(m.group(1))
            build_id = data.get('buildId')
            query = (data.get('query') or {})
            params = query.get('params') or []
            if not (build_id and params and isinstance(params, list)):
                return None
            path = 'tv/' + '/'.join(params)
            next_url = f'https://{host}/_next/data/{build_id}/{path}.json'
            jtxt = self.net.http_GET(next_url, headers=headers).content
            if not jtxt:
                return None
            # Prefer direct HLS
            m3u8 = self._extract_m3u8(jtxt)
            if m3u8:
                return m3u8 + helpers.append_headers(headers)
            # Scan for common external hosts in JSON
            candidates = re.findall(r'https?://[^"\'\s<>]+', jtxt)
            if not candidates:
                return None
            # Prioritize known hosters and embed endpoints
            prefer = (
                'filemoon', 'streamtape', 'dood', 'ok.ru', 'okru', 'mixdrop',
                'mp4upload', 'voe.', 'uqload', 'vupload', 'vidsrc', 'embed'
            )
            # 1) pick first matching preferred host
            for u in candidates:
                if any(p in u for p in prefer):
                    return u
            # 2) otherwise return first http link
            return candidates[0]
        except Exception:
            return None
