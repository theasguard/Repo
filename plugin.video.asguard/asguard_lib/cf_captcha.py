import re
import log_utils
import requests
import urllib.error
import urllib.request as urllib_request
import urllib.parse as urllib_parse
import urllib.error as urllib_error

from asguard_lib import recaptcha_v2
from asguard_lib.constants import USER_AGENT

logger = log_utils.Logger.get_logger(__name__)

logger.disable()

class NoRedirection(urllib_request.HTTPErrorProcessor):
    def http_response(self, request, response):  # @UnusedVariable
        logger.log('Stopping Redirect', log_utils.LOGDEBUG)
        return response

    https_response = http_response

def solve(url, cj, user_agent=None, name=None):
    if user_agent is None: user_agent = USER_AGENT
    headers = {'User-Agent': user_agent, 'Referer': url}
    request = urllib_request.Request(url)
    for key in headers: request.add_header(key, headers[key])
    try:
        response = urllib_request.urlopen(request)
        html = response.read()
        # Decode bytes to string for pattern matching
        if isinstance(html, bytes):
            html = html.decode('utf-8', errors='ignore')
    except urllib_error.HTTPError as e:
        html = e.read()
        # Decode bytes to string for pattern matching
        if isinstance(html, bytes):
            html = html.decode('utf-8', errors='ignore')

    match = re.search('data-sitekey="([^"]+)', html)
    match1 = re.search('data-ray="([^"]+)', html)
    if match and match1:
        token = recaptcha_v2.UnCaptchaReCaptcha().processCaptcha(match.group(1), lang='en', name=name, referer=url)
        if token:
            data = {'g-recaptcha-response': token, 'id': match1.group(1)}
            scheme = urllib_parse.urlparse(url).scheme
            domain = urllib_parse.urlparse(url).hostname
            url = '%s://%s/cdn-cgi/l/chk_captcha?%s' % (scheme, domain, urllib_parse.urlencode(data))
            if cj is not None:
                try: cj.load(ignore_discard=True)
                except: pass
                opener = urllib_request.build_opener(urllib_request.HTTPCookieProcessor(cj))
                urllib_request.install_opener(opener)

            try:
                request = urllib_request.Request(url)
                for key in headers: request.add_header(key, headers[key])
                opener = urllib_request.build_opener(NoRedirection)
                urllib_request.install_opener(opener)
                response = urllib_request.urlopen(request)
                while response.getcode() in [301, 302, 303, 307]:
                    if cj is not None:
                        cj.extract_cookies(response, request)
                    redir_url = response.info().getheader('location')
                    if not redir_url.startswith('http'):
                        redir_url = urllib_parse.urljoin(url, redir_url)
                    request = urllib_request.Request(redir_url)
                    for key in headers: request.add_header(key, headers[key])
                    if cj is not None:
                        cj.add_cookie_header(request)
                        
                    response = urllib_request.urlopen(request)

                final = response.read()
                # Decode bytes to string for consistent return type
                if isinstance(final, bytes):
                    final = final.decode('utf-8', errors='ignore')
                    
                if cj is not None:
                    cj.extract_cookies(response, request)
                    cj.save(ignore_discard=True)
                    
                return final
            except urllib_error.HTTPError as e:
                logger.log('CF Captcha Error: %s on url: %s' % (e.code, url), log_utils.LOGWARNING)
                return False
    else:
        logger.log('CF Captcha without sitekey/data-ray: %s' % (url), log_utils.LOGWARNING)
