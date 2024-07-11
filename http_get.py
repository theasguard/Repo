import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

class Scraper(object):
    ...
    def _cached_http_get(self, url, base_url, timeout, params=None, data=None, multipart_data=None, headers=None, cookies=None, allow_redirect=True,
                        method=None, require_debrid=False, read_error=False, cache_limit=8):
        if require_debrid:
            if Scraper.debrid_resolvers is None:
                Scraper.debrid_resolvers = [resolver for resolver in resolveurl.resolve(url) if resolver.isUniversal()]
            if not Scraper.debrid_resolvers:
                logger.log('%s requires debrid: %s' % (self.__module__, Scraper.debrid_resolvers), log_utils.LOGDEBUG)
                return ''

        if cookies is None: cookies = {}
        if timeout == 0: timeout = None
        if headers is None: headers = {}
        if url.startswith('//'): url = 'http:' + url
        referer = headers['Referer'] if 'Referer' in headers else base_url
        if params:
            if url == base_url and not url.endswith('/'):
                url += '/'
            
            parts = urllib.parse.urlparse(url)
            if parts.query:
                params.update(scraper_utils.parse_query(url))
                url = urllib.parse.urlunparse((parts.scheme, parts.netloc, parts.path, parts.params, '', parts.fragment))
                
            url += '?' + urllib.parse.urlencode(params)

        logger.log('Getting Url: %s cookie=|%s| data=|%s| extra headers=|%s|' % (url, cookies, data, headers), log_utils.LOGDEBUG)
        if data is not None:
            if isinstance(data, str):
                data = data
            else:
                data = urllib.parse.urlencode(data, True)

        if multipart_data is not None:
            headers['Content-Type'] = 'multipart/form-data; boundary=X-X-X'
            data = multipart_data

        _created, _res_header, html = self.db_connection().get_cached_url(url, data, cache_limit)
        if html:
            logger.log('Returning cached result for: %s' % (url), log_utils.LOGDEBUG)
            return html

        try:
            session = requests.Session()
            retries = Retry(total=5, backoff_factor=1, status_forcelist=[429, 500, 502, 503, 504])
            adapter = HTTPAdapter(max_retries=retries)
            session.mount('http://', adapter)
            session.mount('https://', adapter)

            session.cookies.update(cookies)
            headers = headers.copy()
            headers['User-Agent'] = scraper_utils.get_ua()
            headers['Accept'] = '*/*'
            headers['Accept-Encoding'] = 'gzip'
            headers['Host'] = urllib.parse.urlparse(url).netloc
            if referer:
                headers['Referer'] = referer

            if method is None:
                method = 'GET'

            response = session.request(method, url, params=params, data=data, headers=headers, timeout=timeout, allow_redirects=allow_redirect)
            response.raise_for_status()

            session.cookies.update(response.cookies)
            if kodi.get_setting('cookie_debug') == 'true':
                logger.log('Response Cookies: %s - %s' % (url, scraper_utils.cookies_as_str(session.cookies)), log_utils.LOGDEBUG)
            session.cookies = scraper_utils.fix_bad_cookies(session.cookies)
            session.cookies.save(ignore_discard=True)

            if not allow_redirect and response.is_redirect:
                return response.headers['Location']

            content_length = response.headers.get('Content-Length', 0)
            if int(content_length) > MAX_RESPONSE:
                logger.log('Response exceeded allowed size. %s => %s / %s' % (url, content_length, MAX_RESPONSE), log_utils.LOGWARNING)
            
            if method == 'HEAD':
                return ''
            else:
                if response.headers.get('Content-Encoding') == 'gzip':
                    html = ungz(response.content)
                else:
                    html = response.content
        except requests.exceptions.RequestException as e:
            logger.log('Error (%s) during scraper http get: %s' % (str(e), url), log_utils.LOGWARNING)
            return ''

        self.db_connection().cache_url(url, html, data)
        return html
