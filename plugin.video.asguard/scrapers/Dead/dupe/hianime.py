"""
    Asguard Addon - HiAnime Scraper
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
from bs4 import BeautifulSoup, SoupStrainer

from asguard_lib import scraper_utils
from asguard_lib.constants import VIDEO_TYPES
from . import scraper
import log_utils
import kodi

logger = log_utils.Logger.get_logger()
BASE_URL = 'https://hianime.to'

# Supported/known embed server names (normalized)
ALL_EMBEDS = {
    'doodstream', 'filelions', 'filemoon', 'hd-1', 'hd-2', 'iga', 'kwik',
    'megaf', 'moonf', 'mp4upload', 'mp4u', 'mycloud', 'noads', 'noadsalt',
    'swish', 'streamtape', 'streamwish', 'vidcdn', 'vidhide', 'vidplay',
    'vidstream', 'yourupload', 'zto'
}


class Scraper(scraper.Scraper):
    base_url = BASE_URL

    def __init__(self, timeout=scraper.DEFAULT_TIMEOUT):
        self.timeout = timeout
        self.base_url = kodi.get_setting(f'{self.get_name()}-base_url') or BASE_URL
        # Known alternates
        self.domains = ['hianime.to', 'hianime.sx']

    @classmethod
    def provides(cls):
        return frozenset([VIDEO_TYPES.TVSHOW, VIDEO_TYPES.EPISODE])

    @classmethod
    def get_name(cls):
        return 'HiAnime'

    def get_sources(self, video):
        sources = []
        source_url = self.get_url(video)
        logger.log(f'[HiAnime] get_sources for: {video.title} S{getattr(video, "season", "")}E{getattr(video, "episode", "")} -> {source_url}', log_utils.LOGDEBUG)

        if not source_url or source_url == scraper_utils.FORCE_NO_MATCH:
            logger.log('[HiAnime] No source_url found', log_utils.LOGWARNING)
            return sources

        show_url = scraper_utils.urljoin(self.base_url, source_url)
        parsed = urllib.parse.urlparse(self.base_url)
        origin = f'{parsed.scheme}://{parsed.netloc}'
        headers = {
            'Referer': self.base_url,
            'Origin': origin,
            'X-Requested-With': 'XMLHttpRequest',
            'Accept': '*/*',
            'Content-Type': 'application/x-www-form-urlencoded; charset=UTF-8',
        }

        # Resolve film/slug id required by HiAnime AJAX endpoints
        slug_id = self._extract_slug_id_from_path(source_url)
        logger.log(f'[HiAnime] slug_id from path: {slug_id}', log_utils.LOGDEBUG)
        if not slug_id:
            html = self._http_get(show_url, cache_limit=1)
            logger.log(f'[HiAnime] Loaded show page HTML: {len(html) if html else 0}', log_utils.LOGDEBUG)
            if html:
                slug_id = self._extract_slug_id_from_html(html)
                logger.log(f'[HiAnime] slug_id from HTML: {slug_id}', log_utils.LOGDEBUG)
        # Fallback: if still no ID and URL is /anime/, try /watch/
        if not slug_id and source_url.startswith('/anime/'):
            watch_path = source_url.replace('/anime/', '/watch/')
            watch_url = scraper_utils.urljoin(self.base_url, watch_path)
            logger.log(f'[HiAnime] Trying watch URL for film id: {watch_url}', log_utils.LOGDEBUG)
            html = self._http_get(watch_url, cache_limit=1)
            if html:
                slug_id = self._extract_slug_id_from_html(html)
                logger.log(f'[HiAnime] slug_id from /watch/ HTML: {slug_id}', log_utils.LOGDEBUG)
            # Also update show_url to the watch URL as referer for later calls
            if slug_id:
                show_url = watch_url
        if not slug_id:
            logger.log('[HiAnime] Unable to resolve slug/film id from URL or page', log_utils.LOGWARNING)
            return sources

        # Fetch episode list for the title and pick our episode id
        ep_list_url = scraper_utils.urljoin(self.base_url, f'/ajax/v2/episode/list/{slug_id}')
        logger.log(f'[HiAnime] Episode list URL: {ep_list_url}', log_utils.LOGDEBUG)
        try:
            r = self._http_get(ep_list_url, headers=headers, cache_limit=1)
            html = json.loads(r).get('html') if r else ''
        except Exception as e:
            logger.log(f'[HiAnime] Error loading episode list: {e}', log_utils.LOGERROR)
            html = ''
        if not html:
            logger.log('[HiAnime] Empty episode list HTML', log_utils.LOGWARNING)
            return sources

        elink = SoupStrainer('div', {'class': re.compile('^ss-list')})
        ediv = BeautifulSoup(html, 'html.parser', parse_only=elink)
        items = ediv.find_all('a') if ediv else []
        ep_id = None
        try:
            for x in items:
                data_num = x.get('data-number')
                if data_num and int(data_num) == int(video.episode):
                    ep_id = x.get('data-id')
                    break
        except Exception:
            ep_id = None

        logger.log(f'[HiAnime] Matched episode id: {ep_id}', log_utils.LOGDEBUG)
        if not ep_id:
            logger.log('[HiAnime] Episode id not found in episode list', log_utils.LOGWARNING)
            return sources

        # Get servers for the specific episode
        servers_url = scraper_utils.urljoin(self.base_url, '/ajax/v2/episode/servers')
        # Build referers for XHR calls (try base first, then watch page)
        if source_url.startswith('/watch/'):
            watch_referer_path = source_url
        else:
            watch_referer_path = '/watch' + source_url
        watch_referer_url = scraper_utils.urljoin(self.base_url, watch_referer_path)
        if ep_id and '?ep=' not in watch_referer_url:
            watch_referer_url = f'{watch_referer_url}?ep={ep_id}'

        xheaders_base = headers.copy()
        xheaders_base['Referer'] = self.base_url
        xheaders_watch = headers.copy()
        xheaders_watch['Referer'] = watch_referer_url
        logger.log(f'[HiAnime] Base Referer: {xheaders_base["Referer"]}', log_utils.LOGDEBUG)
        logger.log(f'[HiAnime] Watch Referer: {xheaders_watch["Referer"]}', log_utils.LOGDEBUG)

        # Attempt with base referer
        try:
            r = self._http_get(servers_url, params={'episodeId': ep_id}, headers=xheaders_base, cache_limit=0)
            servers_html = json.loads(r).get('html') if r else ''
        except Exception as e:
            logger.log(f'[HiAnime] Error getting servers (base referer): {e}', log_utils.LOGERROR)
            servers_html = ''

        # Fallback: preload watch page and retry with watch referer
        if not servers_html:
            try:
                watch_html = self._http_get(watch_referer_url, headers={'Referer': self.base_url}, cache_limit=1)
            except Exception:
                watch_html = ''
            # Extract CSRF token if present and add to headers
            try:
                token_match = re.search(r'name=["\']csrf-token["\']\s+content=["\']([^"\']+)', watch_html or '')
                if token_match:
                    token = token_match.group(1)
                    xheaders_watch['X-CSRF-TOKEN'] = token
                    xheaders_base['X-CSRF-TOKEN'] = token
                    logger.log('[HiAnime] Added X-CSRF-TOKEN header from watch page', log_utils.LOGDEBUG)
            except Exception:
                pass
            try:
                r = self._http_get(servers_url, params={'episodeId': ep_id}, headers=xheaders_watch, cache_limit=0)
                servers_html = json.loads(r).get('html') if r else ''
            except Exception as e:
                logger.log(f'[HiAnime] Error getting servers (watch referer): {e}', log_utils.LOGERROR)
                servers_html = ''

        logger.log(f'[HiAnime] servers_html length: {len(servers_html) if servers_html else 0}', log_utils.LOGDEBUG)
        if servers_html:
            logger.log(f'[HiAnime] servers_html snippet: {servers_html[:300]}', log_utils.LOGDEBUG)
        if not servers_html:
            logger.log('[HiAnime] Empty servers HTML', log_utils.LOGWARNING)
            return sources

        soup = BeautifulSoup(servers_html, 'html.parser')
        lang_sections = ['sub', 'dub', 'raw']

        enabled_embeds = self._enabled_embeds()
        logger.log(f'[HiAnime] Enabled embeds: {enabled_embeds}', log_utils.LOGDEBUG)

        # Iterate langs and servers to collect embed links
        for lang in lang_sections:
            sdiv = soup.find('div', {'data-type': lang})
            if not sdiv:
                continue
            srcs = sdiv.find_all('div', {'class': 'item'})
            logger.log(f'[HiAnime] Found {len(srcs)} servers for lang={lang}', log_utils.LOGDEBUG)
            for src in srcs:
                server_id = src.get('data-id')
                raw_name = (src.text or '').strip().lower()
                server_key = self._normalize_server_name(raw_name)
                if not server_id:
                    continue
                if enabled_embeds and server_key not in enabled_embeds:
                    logger.log(f'[HiAnime] Skipping server {raw_name} (key={server_key}) not in enabled embeds', log_utils.LOGDEBUG)
                    continue

                # Request final embed link for this server
                try:
                    # Try base referer first
                    r = self._http_get(
                        scraper_utils.urljoin(self.base_url, '/ajax/v2/episode/sources'),
                        params={'id': server_id}, headers=xheaders_base, cache_limit=0
                    )
                    slink = json.loads(r).get('link') if r else None
                    if not slink:
                        r = self._http_get(
                            scraper_utils.urljoin(self.base_url, '/ajax/v2/episode/sources'),
                            params={'id': server_id}, headers=xheaders_watch, cache_limit=0
                        )
                        slink = json.loads(r).get('link') if r else None
                except Exception as e:
                    logger.log(f'[HiAnime] Error getting source link for server {raw_name}: {e}', log_utils.LOGERROR)
                    slink = None

                if not slink:
                    continue

                # Normalize // links
                if slink.startswith('//'):
                    slink = 'https:' + slink
                elif slink.startswith('/'):
                    slink = scraper_utils.urljoin(self.base_url, slink)

                host = urllib.parse.urlparse(slink).hostname or self.get_name()
                quality = scraper_utils.blog_get_quality(video, slink, host)

                # Expose as embed sources (resolveurl should handle major hosts)
                source = {
                    'class': self,
                    'quality': quality,
                    'url': slink,
                    'host': host,
                    'multi-part': False,
                    'rating': None,
                    'views': None,
                    'direct': False,
                    'label': f'{lang.upper()} {raw_name}'
                }
                sources.append(source)
                logger.log(f'[HiAnime] Added source: {source}', log_utils.LOGDEBUG)

        return sources

    def search(self, video_type, title, year, season=''):
        logger.log(f'[HiAnime] search: type={video_type}, title={title}, year={year}, season={season}', log_utils.LOGDEBUG)
        results = []

        # Build keyword (append year if available for better matching)
        keyword = title
        if year:
            keyword = f'{title} {year}'

        try:
            params = {'keyword': keyword}
            url = scraper_utils.urljoin(self.base_url, '/search')
            html = self._http_get(url, params=params, headers={'Referer': self.base_url}, cache_limit=1)
            if not html:
                return results

            # Parse search results
            mlink = SoupStrainer('div', {'class': 'flw-item'})
            mdiv = BeautifulSoup(html, 'html.parser', parse_only=mlink)
            sdivs = mdiv.find_all('h3') if mdiv else []
            sitems = []
            for sdiv in sdivs:
                try:
                    a = sdiv.find('a')
                    if not a:
                        continue
                    slug = (a.get('href') or '').split('?')[0]
                    stitle = a.get('data-jname') or a.get('title') or a.text
                    if slug.startswith('http'):
                        parts = urllib.parse.urlparse(slug)
                        slug = parts.path
                    sitems.append({'title': stitle or '', 'slug': slug})
                except Exception:
                    continue

            if not sitems:
                return results

            # Prefer normalized title match
            norm_query = scraper_utils.normalize_title(title)
            candidates = []
            for x in sitems:
                n = scraper_utils.normalize_title(x.get('title', ''))
                if n == norm_query or (n and (norm_query in n or n in norm_query)):
                    candidates.append(x)

            items = candidates or sitems
            slug = items[0]['slug'] if items else ''
            if slug:
                results.append({'title': title, 'year': year, 'url': slug})
        except Exception as e:
            logger.log(f'[HiAnime] search error: {e}', log_utils.LOGERROR)

        logger.log(f'[HiAnime] search results: {len(results)}', log_utils.LOGDEBUG)
        return results

    def _get_episode_url(self, url, video):
        """
        HiAnime uses AJAX for episode selection; keeping the show URL is sufficient.
        """
        return url

    def _enabled_embeds(self):
        try:
            embeds = [e for e in ALL_EMBEDS if kodi.get_setting(f'embed.{e}') == 'true']
            # If no settings are explicitly enabled, default to all embeds to avoid blocking everything
            return embeds if embeds else list(ALL_EMBEDS)
        except Exception:
            return list(ALL_EMBEDS)

    def _normalize_server_name(self, name):
        name = name.lower().replace(' ', '').replace('_', '')
        # Common alias fixes
        aliases = {
            'megacloud': 'mycloud',
            'mycloud': 'mycloud',
            'mp4upload': 'mp4upload',
            'mp4up': 'mp4upload',
            'mp4u': 'mp4u',
            'vidcloud': 'vidcdn',
            'vidcdn': 'vidcdn',
            'vidplay': 'vidplay',
            'vidstream': 'vidstream',
            'streamtape': 'streamtape',
            'streamwish': 'streamwish',
            'filemoon': 'filemoon',
            'dood': 'doodstream',
            'doodstream': 'doodstream',
            'yourupload': 'yourupload',
            'kwik': 'kwik',
            'zoro.to': 'zto',
            'zto': 'zto',
            'moonf': 'moonf',
            'megaf': 'megaf',
            'noads': 'noads',
            'noadsalt': 'noadsalt',
            'vidhide': 'vidhide',
            'iga': 'iga',
            'hd-1': 'hd-1',
            'hd-2': 'hd-2',
            'filelions': 'filelions',
            'swish': 'swish',
        }
        return aliases.get(name, name)

    def _extract_slug_id_from_path(self, path):
        try:
            last = path.rstrip('/').split('/')[-1]
            m = re.search(r'-(\d+)$', last)
            if m:
                return m.group(1)
            return None
        except Exception:
            return None

    def _extract_slug_id_from_html(self, html):
        try:
            # Common markers used by HiAnime/Zoro clones
            m = re.search(r'id=["\']film_id["\']\s+value=["\'](\d+)["\']', html)
            if m:
                return m.group(1)
            # Sometimes present as hidden input name="id" value="<film_id>"
            m = re.search(r'name=["\']id["\']\s+value=["\'](\d+)["\']', html)
            if m:
                return m.group(1)
            m = re.search(r'data-id=["\'](\d+)["\']', html)
            if m:
                return m.group(1)
        except Exception:
            pass
        return None
