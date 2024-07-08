import requests

class Trakt_API():
    # ... other methods ...

    def __call_trakt(self, url: str, method: str = None, data: Any = None, params: dict = None, auth: bool = True, cache_limit: float = .25, cached: bool = True) -> Union[str, list, dict, Any]:
        res_headers = {}
        if not cached: cache_limit = 0
        if self.offline:
            db_cache_limit = int(time.time()) / 60 / 60
        else:
            if cache_limit > 8:
                db_cache_limit = cache_limit
            else:
                db_cache_limit = 8
        json_data = json.dumps(data) if data else None
        logger.log('***Trakt Call: %s, data: %s cache_limit: %s cached: %s' % (url, json_data, cache_limit, cached), log_utils.LOGDEBUG)

        headers = {
            'Content-Type': 'application/json',
            'trakt-api-key': V2_API_KEY,
            'trakt-api-version': '2'
        }
        if auth:
            headers['Authorization'] = 'Bearer {}'.format(self.token)
        url = '{}{}{}'.format(self.protocol, BASE_URL, url)
        if params:
            url = url + '?' + urllib_parse.urlencode(params)

        db_connection = self.__get_db_connection()
        created, cached_headers, cached_result = db_connection.get_cached_url(url, json_data, db_cache_limit)
        if cached_result and (self.offline or (time.time() - created) < (60 * 60 * cache_limit)):
            result = cached_result
            res_headers = dict(cached_headers)
            logger.log('***Using cached result for: %s' % (url), log_utils.LOGDEBUG)
        else:
            auth_retry = False
            while True:
                try:
                    logger.log('***Trakt Call: %s, header: %s, data: %s cache_limit: %s cached: %s' % (url, headers, json_data, cache_limit, cached), log_utils.LOGDEBUG)
                    if method is None or method.upper() == 'GET':
                        response = requests.get(url, headers=headers, params=params, timeout=self.timeout)
                    elif method.upper() == 'POST':
                        response = requests.post(url, headers=headers, json=data, timeout=self.timeout)
                    elif method.upper() == 'DELETE':
                        response = requests.delete(url, headers=headers, json=data, timeout=self.timeout)
                    response.raise_for_status()  # Will raise HTTPError for bad requests (400 or 500 level responses)
                    result = response.text
                    logger.log('***Trakt Response: %s' % (result), log_utils.LOGDEBUG)

                    db_connection.cache_url(url, result, json_data, response.headers.items())
                    break
                except requests.exceptions.HTTPError as e:
                    if e.response.status_code in TEMP_ERRORS:
                        logger.log('Temporary Trakt Error ({}). Using Cached Page Instead.'.format(str(e)), log_utils.LOGWARNING)
                        if cached_result:
                            return cached_result
                        else:
                            raise TransientTraktError('Temporary Trakt Error: ' + str(e))
                    elif e.response.status_code == 401 or e.response.status_code == 405:
                        if 'X-Private-User' in e.response.headers and e.response.headers.get('X-Private-User') == 'true':
                            raise TraktAuthError('Object is No Longer Available (%s)' % (e.response.status_code))
                        elif auth_retry or url.endswith('/oauth/token'):
                            self.token = None
                            kodi.set_setting('trakt_oauth_token', '')
                            kodi.set_setting('trakt_refresh_token', '')
                            raise TraktAuthError('Trakt Call Authentication Failed (%s)' % (e.response.status_code))
                        else:
                            result = self.refresh_token(kodi.get_setting('trakt_refresh_token'))
                            self.token = result['access_token']
                            kodi.set_setting('trakt_oauth_token', result['access_token'])
                            kodi.set_setting('trakt_refresh_token', result['refresh_token'])
                            auth_retry = True
                    elif e.response.status_code == 404:
                        raise TraktNotFoundError('Object Not Found (%s): %s' % (e.response.status_code, url))
                    else:
                        raise
                except requests.exceptions.RequestException as e:
                    logger.log('Unexpected error: {}'.format(e), log_utils.LOGERROR)
                    raise

        try:
            js_data = utils.json_loads_as_str(result)
            if 'x-sort-by' in res_headers and 'x-sort-how' in res_headers:
                js_data = utils2.sort_list(res_headers['x-sort-by'], res_headers['x-sort-how'], js_data)
        except ValueError:
            js_data = ''
            if result:
                logger.log('Invalid JSON Trakt API Response: %s - |%s|' % (url, js_data), log_utils.LOGERROR)

        return js_data
