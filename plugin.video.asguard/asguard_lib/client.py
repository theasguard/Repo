# -*- coding: utf-8 -*-

'''
    Asguard Add-on
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
'''

from html import unescape
from io import BytesIO, StringIO
import re, sys, gzip, time, random, base64
import urllib.request
import urllib.error
import urllib.parse as urllib_parse
import six
import http.cookiejar as cookielib
import html.parser as HTMLParser
import urllib3
import cache
import dom_parser
from asguard_lib import worker_pool, control
import log_utils
import workers

logger = log_utils.Logger.get_logger(__name__)

def request(url, close=True, redirect=True, error=False, proxy=None, post=None, headers=None, mobile=False, XHR=False, limit=None, referer=None, cookie=None, compression=True, output='', timeout='30'):
    try:
        handlers = []

        if not proxy == None:
            handlers += [urllib.request.ProxyHandler({'http':'%s' % (proxy)}), urllib.request.HTTPHandler]
            opener = urllib.request.build_opener(*handlers)
            opener = urllib.request.install_opener(opener)


        if output == 'cookie' or output == 'extended' or not close == True:
            cookies = cookielib.LWPCookieJar()
            handlers += [urllib.request.HTTPHandler(), urllib.request.HTTPSHandler(), urllib.request.HTTPCookieProcessor(cookies)]
            opener = urllib.request.build_opener(*handlers)
            opener = urllib.request.install_opener(opener)

        if (2, 7, 9) <= sys.version_info < (2, 7, 11):
            try:
                import ssl; ssl_context = ssl.create_default_context()
                ssl_context.check_hostname = False
                ssl_context.verify_mode = ssl.CERT_NONE
                handlers += [urllib.request.HTTPSHandler(context=ssl_context)]
                opener = urllib.request.build_opener(*handlers)
                opener = urllib.request.install_opener(opener)
            except:
                pass

        if url.startswith('//'): url = 'http:' + url

        try: headers.update(headers)
        except: headers = {}
        if 'User-Agent' in headers:
            pass
        elif not mobile == True:
            headers['User-Agent'] = agent()
            headers['User-Agent'] = cache.get(randomagent, 1)
        else:
            headers['User-Agent'] = 'Apple-iPhone/701.341'
        if 'Referer' in headers:
            pass
        elif referer == None:
            headers['Referer'] = '%s://%s/' % (urllib_parse.urlparse(url).scheme, urllib_parse.urlparse(url).netloc)
        else:
            headers['Referer'] = referer
        if not 'Accept-Language' in headers:
            headers['Accept-Language'] = 'en-US'
        if 'X-Requested-With' in headers:
            pass
        elif XHR == True:
            headers['X-Requested-With'] = 'XMLHttpRequest'
        if 'Cookie' in headers:
            pass
        elif not cookie == None:
            headers['Cookie'] = cookie
        if 'Accept-Encoding' in headers:
            pass
        elif compression and limit is None:
            headers['Accept-Encoding'] = 'gzip'


        if redirect == False:

            class NoRedirection(urllib.request.HTTPErrorProcessor):
                def http_response(self, request, response): return response

            opener = urllib.request.build_opener(NoRedirection)
            opener = urllib.request.install_opener(opener)

            try: del headers['Referer']
            except: pass


        request = urllib.request.Request(url, data=post, headers=headers)


        try:
            response = urllib.request.urlopen(request, timeout=int(timeout))
        except urllib.request.HTTPError as response:

            if response.code == 503:
                cf_result = response.read(5242880)
                try: encoding = response.info().getheader('Content-Encoding')
                except: encoding = None
                if encoding == 'gzip':
                    cf_result = gzip.GzipFile(fileobj=StringIO.StringIO(cf_result)).read()

                if 'cf-browser-verification' in cf_result:

                    netloc = '%s://%s' % (urllib_parse.urlparse(url).scheme, urllib_parse.urlparse(url).netloc)

                    ua = headers['User-Agent']

                    cf = cache.get(cfcookie().get, 168, netloc, ua, timeout)

                    headers['Cookie'] = cf

                    request = urllib.request.Request(url, data=post, headers=headers)

                    response = urllib.request.urlopen(request, timeout=int(timeout))

                elif error == False:
                    return

            elif error == False:
                return


        if output == 'cookie':
            try: result = '; '.join(['%s=%s' % (i.name, i.value) for i in cookies])
            except: pass
            try: result = cf
            except: pass
            if close == True: response.close()
            return result

        elif output == 'geturl':
            result = response.geturl()
            if close == True: response.close()
            return result

        elif output == 'headers':
            result = response.headers
            if close == True: response.close()
            return result

        elif output == 'chunk':
            try: content = int(response.headers['Content-Length'])
            except: content = (2049 * 1024)
            if content < (2048 * 1024): return
            result = response.read(16 * 1024)
            if close == True: response.close()
            return result


        if limit == '0':
            result = response.read(224 * 1024)
        elif not limit == None:
            result = response.read(int(limit) * 1024)
        else:
            result = response.read(5242880)

        try: encoding = response.info().getheader('Content-Encoding')
        except: encoding = None
        if encoding == 'gzip':
            result = gzip.GzipFile(fileobj=StringIO.StringIO(result)).read()


        if 'sucuri_cloudproxy_js' in result:
            su = sucuri().get(result)

            headers['Cookie'] = su

            request = urllib.request.Request(url, data=post, headers=headers)

            response = urllib.request.urlopen(request, timeout=int(timeout))

            if limit == '0':
                result = response.read(224 * 1024)
            elif not limit == None:
                result = response.read(int(limit) * 1024)
            else:
                result = response.read(5242880)

            try: encoding = response.info().getheader('Content-Encoding')
            except: encoding = None
            if encoding == 'gzip':
                result = gzip.GzipFile(fileobj=StringIO.StringIO(result)).read()


        if output == 'extended':
            response_headers = response.headers
            response_code = str(response.code)
            try: cookie = '; '.join(['%s=%s' % (i.name, i.value) for i in cookies])
            except: pass
            try: cookie = cf
            except: pass
            if close == True: response.close()
            return (result, response_code, response_headers, headers, cookie)
        else:
            if close == True: response.close()
            return result
    except:
        return


def _basic_request(url, headers=None, post=None, method='GET', timeout='30', limit=None, ret_code=None):
	try:
		try: headers.update(headers)
		except: headers = {}
		req = urllib.request.Request(url, data=post, method=method)
		_add_request_header(req, headers)
		response = urllib.request.urlopen(req, timeout=int(timeout))
		return _get_result(response, limit, ret_code)
	except:
		logger.log('Error making basic request', log_utils.LOGERROR)

def _add_request_header(_request, headers):
	try:
		if not headers: headers = {}
		scheme = _request.type
		host = _request.host
		referer = headers.get('Referer') if 'Referer' in headers else '%s://%s/' % (scheme, host)
		_request.add_unredirected_header('Host', host)
		_request.add_unredirected_header('Referer', referer)
		for key in headers:
			_request.add_header(key, headers[key])
	except:
		logger.log('Error adding request header', log_utils.LOGERROR)

def _get_result(response, limit=None, ret_code=None):
	try:
		if ret_code: return response.code
		if limit == '0': result = response.read(224 * 1024)
		elif limit: result = response.read(int(limit) * 1024)
		else: result = response.read(5242880)
		try: encoding = response.headers["Content-Encoding"]
		except: encoding = None
		if encoding == 'gzip': result = gzip.GzipFile(fileobj=BytesIO(result)).read()
		return result
	except:
		logger.log('Error getting result', log_utils.LOGERROR)

def parseDOM(html, name='', attrs=None, ret=False):
    if attrs:
        attrs = {key: re.compile(value + ('$' if value else '')) for key, value in attrs.items()}
    results = dom_parser.parse_dom(html, name, attrs, ret)
    if ret:
        results = [result.attrs[ret.lower()] for result in results]
    else:
        results = [result.content for result in results]
    return results

def replaceHTMLCodes(txt):
	# Some HTML entities are encoded twice. Decode double.
	return _replaceHTMLCodes(_replaceHTMLCodes(txt))

def _replaceHTMLCodes(txt):
	try:
		if not txt: return ''
		txt = re.sub(r"(&#[0-9]+)([^;^0-9]+)", "\\1;\\2", txt)
		txt = unescape(txt)
		txt = txt.replace("&quot;", "\"")
		txt = txt.replace("&amp;", "&")
		txt = txt.replace("&lt;", "<")
		txt = txt.replace("&gt;", ">")
		txt = txt.replace("&#38;", "&")
		txt = txt.replace("&nbsp;", "")
		txt = txt.replace('&#8230;', '...')
		txt = txt.replace('&#8217;', '\'')
		txt = txt.replace('&#8211;', '-')
		txt = txt.strip()
		return txt
	except:
		logger.log('Error replacing HTML codes', log_utils.LOGERROR)
		return txt


def randomagent():
    BR_VERS = [
        ['%s.0' % i for i in range(18, 50)],
        ['37.0.2062.103', '37.0.2062.120', '37.0.2062.124', '38.0.2125.101', '38.0.2125.104', '38.0.2125.111', '39.0.2171.71', '39.0.2171.95', '39.0.2171.99',
         '40.0.2214.93', '40.0.2214.111',
         '40.0.2214.115', '42.0.2311.90', '42.0.2311.135', '42.0.2311.152', '43.0.2357.81', '43.0.2357.124', '44.0.2403.155', '44.0.2403.157', '45.0.2454.101',
         '45.0.2454.85', '46.0.2490.71',
         '46.0.2490.80', '46.0.2490.86', '47.0.2526.73', '47.0.2526.80', '48.0.2564.116', '49.0.2623.112', '50.0.2661.86', '51.0.2704.103', '52.0.2743.116',
         '53.0.2785.143', '54.0.2840.71'],
        ['11.0'],
        ['8.0', '9.0', '10.0', '10.6']]
    WIN_VERS = ['Windows NT 11.0','Windows NT 10.0', 'Windows NT 7.0', 'Windows NT 6.3', 'Windows NT 6.2', 'Windows NT 6.1', 'Windows NT 6.0', 'Windows NT 5.1', 'Windows NT 5.0']
    FEATURES = ['; WOW64', '; Win64; IA64', '; Win64; x64', '']
    RAND_UAS = ['Mozilla/5.0 ({win_ver}{feature}; rv:{br_ver}) Gecko/20100101 Firefox/{br_ver}',
                'Mozilla/5.0 ({win_ver}{feature}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{br_ver} Safari/537.36',
                'Mozilla/5.0 ({win_ver}{feature}; Trident/7.0; rv:{br_ver}) like Gecko',
                'Mozilla/5.0 (compatible; MSIE {br_ver}; {win_ver}{feature}; Trident/6.0)']
    index = random.randrange(len(RAND_UAS))
    return RAND_UAS[index].format(win_ver=random.choice(WIN_VERS), feature=random.choice(FEATURES), br_ver=random.choice(BR_VERS[index]))

def agent():
	return 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/80.0.3987.149 Safari/537.36' # works on glodls


class cfcookie:
    def __init__(self):
        self.cookie = None


    def get(self, netloc, ua, timeout):
        threads = []

        for i in range(0, 15): threads.append(workers.Thread(self.get_cookie, netloc, ua, timeout))
        [i.start() for i in threads]

        for i in range(0, 30):
            if not self.cookie == None: return self.cookie
            time.sleep(1)


    def get_cookie(self, netloc, ua, timeout):
        try:
            headers = {'User-Agent': ua}

            request = urllib.request.Request(netloc, headers=headers)

            try:
                response = urllib.request.urlopen(request, timeout=int(timeout))
            except urllib.request.HTTPError as response:
                result = response.read(5242880)
                try: encoding = response.info().getheader('Content-Encoding')
                except: encoding = None
                if encoding == 'gzip':
                    result = gzip.GzipFile(fileobj=BytesIO(result)).read()

            jschl = re.findall('name="jschl_vc" value="(.+?)"/>', result)[0]

            init = re.findall('setTimeout\(function\(\){\s*.*?.*:(.*?)};', result)[-1]

            builder = re.findall(r"challenge-form\'\);\s*(.*)a.v", result)[0]

            decryptVal = self.parseJSString(init)

            lines = builder.split(';')

            for line in lines:

                if len(line) > 0 and '=' in line:

                    sections=line.split('=')
                    line_val = self.parseJSString(sections[1])
                    decryptVal = int(eval(str(decryptVal)+sections[0][-1]+str(line_val)))

            answer = decryptVal + len(urllib_parse.urlparse(netloc).netloc)

            query = '%s/cdn-cgi/l/chk_jschl?jschl_vc=%s&jschl_answer=%s' % (netloc, jschl, answer)

            if 'type="hidden" name="pass"' in result:
                passval = re.findall('name="pass" value="(.*?)"', result)[0]
                query = '%s/cdn-cgi/l/chk_jschl?pass=%s&jschl_vc=%s&jschl_answer=%s' % (netloc, urllib.quote_plus(passval), jschl, answer)
                time.sleep(6)

            cookies = cookielib.LWPCookieJar()
            handlers = [urllib.request.HTTPHandler(), urllib.request.HTTPSHandler(), urllib.request.HTTPCookieProcessor(cookies)]
            opener = urllib.request.build_opener(*handlers)
            opener = urllib.request.install_opener(opener)

            try:
                request = urllib.request.Request(query, headers=headers)
                response = urllib.request.urlopen(request, timeout=int(timeout))
            except:
                pass

            cookie = '; '.join(['%s=%s' % (i.name, i.value) for i in cookies])

            if 'cf_clearance' in cookie: self.cookie = cookie
        except:
            pass


    def parseJSString(self, s):
        try:
            offset=1 if s[0]=='+' else 0
            val = int(eval(s.replace('!+[]','1').replace('!![]','1').replace('[]','0').replace('(','str(')[offset:]))
            return val
        except:
            pass


class sucuri:
    def __init__(self):
        self.cookie = None


    def get(self, result):
        try:
            s = re.compile("S\s*=\s*'([^']+)").findall(result)[0]
            s = base64.b64decode(s)
            s = s.replace(' ', '')
            s = re.sub('String\.fromCharCode\(([^)]+)\)', r'chr(\1)', s)
            s = re.sub('\.slice\((\d+),(\d+)\)', r'[\1:\2]', s)
            s = re.sub('\.charAt\(([^)]+)\)', r'[\1]', s)
            s = re.sub('\.substr\((\d+),(\d+)\)', r'[\1:\1+\2]', s)
            s = re.sub(';location.reload\(\);', '', s)
            s = re.sub(r'\n', '', s)
            s = re.sub(r'document\.cookie', 'cookie', s)

            cookie = '' ; exec(s)
            self.cookie = re.compile('([^=]+)=(.*)').findall(cookie)[0]
            self.cookie = '%s=%s' % (self.cookie[0], self.cookie[1])

            return self.cookie
        except:
            pass