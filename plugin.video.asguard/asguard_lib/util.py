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
import os, json, re, sys, pickle, queue
import url_dispatcher
import traceback
import six
from six.moves import urllib_request, urllib_parse, urllib_error, html_entities
from six.moves import http_cookiejar as cookielib
import threading

import string
from bs4 import BeautifulSoup
from . import cloudflare

UA = 'Mozilla/6.0 (Windows; U; Windows NT 5.1; en-GB; rv:1.9.0.5) Gecko/2008092417 Firefox/3.0.3'
LOG = 2
sys.path.append(os.path.join(os.path.dirname(__file__), 'contentprovider'))

_cookie_jar = None

CACHE_COOKIES = 'cookies'


class _StringCookieJar(cookielib.LWPCookieJar):

    def __init__(self, string=None, filename=None, delayload=False, policy=None, cache=None):
        self.cache = cache
        cookielib.LWPCookieJar.__init__(self, filename, delayload, policy)
        if string and len(string) > 0:
            self._cookies = pickle.loads(str(string))

    def dump(self):
        return pickle.dumps(self._cookies)


def init_urllib(cache=None):
    """
    Initializes urllib cookie handler
    """
    global _cookie_jar
    data = None
    if cache is not None:
        data = cache.get(CACHE_COOKIES)
        _cookie_jar = _StringCookieJar(data, cache=cache)
    else:
        _cookie_jar = _StringCookieJar(data)
    opener = urllib_request.build_opener(urllib_request.HTTPCookieProcessor(_cookie_jar))
    urllib_request.install_opener(opener)


def cache_cookies(cache=None):
    """
    Saves cookies to cache
    """
    global _cookie_jar
    if _cookie_jar and cache is not None:
        cache.set(CACHE_COOKIES, _cookie_jar.dump())
    else:
        try:
            _cookie_jar.cache.set(CACHE_COOKIES, _cookie_jar.dump())
        except:
            pass


def _solve_http_errors(url, error):
    global _cookie_jar
    data = error.read()
    if error.code == 503 and 'cf-browser-verification' in data:
        data = cloudflare.solve(url, _cookie_jar, UA)
    error.close()
    return data


def request(url, headers={}):
    debug('request: %s' % url)
    req = urllib_request.Request(url, headers=headers)
    req.add_header('User-Agent', UA)
    if _cookie_jar is not None:
        _cookie_jar.add_cookie_header(req)
    try:
        response = urllib_request.urlopen(req)
        data = response.read()
        response.close()
    except urllib_error.HTTPError as error:
        data = _solve_http_errors(url, error)
    debug('len(data) %s' % len(data))
    return data


def post(url, data, headers={}):
    postdata = urllib_parse.urlencode(data).encode('utf-8')
    req = urllib_request.Request(url, postdata, headers)
    req.add_header('User-Agent', UA)
    if _cookie_jar is not None:
        _cookie_jar.add_cookie_header(req)
    try:
        response = urllib_request.urlopen(req)
        data = response.read()
        response.close()
    except urllib_error.HTTPError as error:
        data = _solve_http_errors(url, error)
    return data


def post_json(url, data, headers={}):
    postdata = json.dumps(data).encode('utf-8')
    headers['Content-Type'] = 'application/json'
    req = urllib_request.Request(url, postdata, headers)
    req.add_header('User-Agent', UA)
    if _cookie_jar is not None:
        _cookie_jar.add_cookie_header(req)
    try:
        response = urllib_request.urlopen(req)
        data = response.read()
        response.close()
    except urllib_error.HTTPError as error:
        data = _solve_http_errors(url, error)
    return data


def run_parallel_in_threads(target, args_list):
    result = queue.Queue()
    # wrapper to collect return value in a Queue

    def task_wrapper(*args):
        result.put(target(*args))

    threads = [threading.Thread(target=task_wrapper, args=args) for args in args_list]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return result


def icon(name):
    return 'https://github.com/lzoubek/xbmc-doplnky/raw/dharma/icons/' + name


def substr(data, start, end):
    i1 = data.find(start)
    i2 = data.find(end, i1)
    return data[i1:i2]


def _create_plugin_url(params, plugin=sys.argv[0]):
    url = []
    print(url)
    for key in params.keys():
        value = decode_html(params[key])
        value = value.encode('ascii', 'ignore')
        url.append(key + '=' + value.encode('hex') + '&')
    return plugin + '?' + ''.join(url)


def save_to_file(url, file):
    try:
        return save_data_to_file(request(url), file)
    except:
        traceback.print_exc()


def save_data_to_file(data, file):
    try:
        with open(file, 'wb') as f:
            f.write(data)
        info('File %s saved' % file)
        return True
    except:
        traceback.print_exc()


def read_file(file):
    if not os.path.exists(file):
        return ''
    with open(file, 'r') as f:
        data = f.read()
    return data


n2cp = html_entities.name2codepoint

def _substitute_entity(match):
    ent = match.group(3)
    if match.group(1) == '#':
        # decoding by number
        if match.group(2) == '':
            # number is in decimal
            return six.unichr(int(ent))
        elif match.group(2) == 'x':
            # number is in hex
            return six.unichr(int('0x' + ent, 16))
    else:
        # they were using a name
        cp = n2cp.get(ent)
        if cp:
            return six.unichr(cp)
        else:
            return match.group()


def decode_html(data):
    if not isinstance(data, str):
        return data
    try:
        if not isinstance(data, str):
            data = str(data, 'utf-8', errors='ignore')
        entity_re = re.compile(r'&(#?)(x?)(\w+);')
        return entity_re.subn(_substitute_entity, data)[0]
    except:
        traceback.print_exc()
        print([data])
        return data


try:
    import xbmc

    def debug(text):
        xbmc.log(str([text]), xbmc.LOGDEBUG)

    def info(text):
        xbmc.log(str([text]), xbmc.LOGNOTICE)

    def error(text):
        xbmc.log(str([text]), xbmc.LOGERROR)
except:
    def debug(text):
        if LOG > 1:
            print('[DEBUG] ' + str([text]))

    def info(text):
        if LOG > 0:
            print('[INFO] ' + str([text]))

    def error(text):
        print('[ERROR] ' + str([text]))

_diacritic_replace = {u'\u00f3': 'o',
                      u'\u0213': '-',
                      u'\u00e1': 'a',
                      u'\u010d': 'c',
                      u'\u010c': 'C',
                      u'\u010f': 'd',
                      u'\u010e': 'D',
                      u'\u00e9': 'e',
                      u'\u011b': 'e',
                      u'\u00ed': 'i',
                      u'\u0148': 'n',
                      u'\u0159': 'r',
                      u'\u0161': 's',
                      u'\u0165': 't',
                      u'\u016f': 'u',
                      u'\u00fd': 'y',
                      u'\u017e': 'z',
                      u'\xed': 'i',
                      u'\xe9': 'e',
                      u'\xe1': 'a',
                      }


def replace_diacritic(string):
    ret = []
    for char in string:
        if char in _diacritic_replace:
            ret.append(_diacritic_replace[char])
        else:
            ret.append(char)
    return ''.join(ret)


def params(url=None):
    if not url:
        url = sys.argv[2]
    param = {}
    paramstring = url
    if len(paramstring) >= 2:
        params = url
        cleanedparams = params.replace('?', '')
        if (params[len(params) - 1] == '/'):
            params = params[0:len(params) - 2]
        pairsofparams = cleanedparams.split('&')
        param = {}
        for i in range(len(pairsofparams)):
            splitparams = {}
            splitparams = pairsofparams[i].split('=')
            if (len(splitparams)) == 2:
                param[splitparams[0]] = splitparams[1]
    for p in param.keys():
        param[p] = bytes.fromhex(param[p]).decode('utf-8')
    return param


def int_to_base(number, base):
    digs = string.digits + string.ascii_letters
    if number < 0:
        sign = -1
    elif number == 0:
        return digs[0]
    else:
        sign = 1
    number *= sign
    digits = []
    while number:
        digits.append(digs[number % base])
        number //= base
    if sign < 0:
        digits.append('-')
    digits.reverse()
    return ''.join(digits)


def extract_jwplayer_setup(data):
    """
    Extracts jwplayer setup configuration and returns it as a dictionary.

    :param data: A string to extract the setup from
    :return: A dictionary containing the setup configuration
    """
    data = re.search(r'<script.+?}\(\'(.+)\',\d+,\d+,\'([\w\|]+)\'.*</script>', data, re.I | re.S)
    if data:
        replacements = data.group(2).split('|')
        data = data.group(1)
        for i in reversed(range(len(replacements))):
            if len(replacements[i]) > 0:
                data = re.sub(r'\b%s\b' % int_to_base(i, 36), replacements[i], data)
        data = re.search(r'\.setup\(([^\)]+?)\);', data)
        if data:
            # Decode the string escape sequences
            decoded_data = data.group(1).encode().decode('unicode_escape')
            return json.loads(decoded_data)
    return None


def parse_html(url):
    return BeautifulSoup(request(url), 'html5lib', from_encoding='utf-8')
