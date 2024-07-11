"""
    Asguard
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
import datetime, json, os, random, re
import xbmc, xbmcaddon, xbmcgui
import html.parser
import sqlite3
import resolveurl
import requests

from urllib.parse import parse_qs, urlparse, quote_plus, parse_qsl
from urllib.request import Request, urlopen


def clean_title(title):
    if title is None:
        return
    title = str(title)
    title = re.sub(r'&#(\d+);', '', title)
    title = re.sub(r'(&#[0-9]+)([^;^0-9]+)', r'\1;', title)
    title = title.replace('&quot;', '\"').replace('&amp;', '&')
    title = re.sub(r'\n|\[.*?\]|\(.*?\)|\s(vs|v[.])\s|[:;,\-\'"_\.\?]|', '', title)
    return title.lower()

def clean_search(title):
    if title is None:
        return
    title = title.lower()
    title = re.sub(r'&#(\d+);', '', title)
    title = re.sub(r'(&#[0-9]+)([^;^0-9]+)', r'\1;', title)
    title = title.replace('&quot;', '\"').replace('&amp;', '&')
    title = re.sub(r'[\\|/(){}\[\]:;*?"\'<>\._\?]', ' ', title)
    title = ' '.join(title.split())
    return title

def random_agent():
    br_vers = [
        ['%s.0' % i for i in range(60, 110)],  # Updated Firefox versions
        ['%s.0.0.0' % i for i in range(60, 110)],  # Updated Chrome versions
        ['11.0', '12.0', '13.0']  # Updated IE versions
    ]
    
    win_vers = [
        'Windows NT 11.0', 'Windows NT 10.0', 'Windows NT 6.3', 'Windows NT 6.2', 'Windows NT 6.1',
        'Windows NT 6.0', 'Windows NT 5.1', 'Windows NT 5.0'
    ]
    
    features = ['; WOW64', '; Win64; IA64', '; Win64; x64', '']
    
    rand_uas = [
        'Mozilla/5.0 ({win_ver}{feature}; rv:{br_ver}) Gecko/20100101 Firefox/{br_ver}',
        'Mozilla/5.0 ({win_ver}{feature}) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{br_ver} Safari/537.36',
        'Mozilla/5.0 ({win_ver}{feature}; Trident/7.0; rv:{br_ver}) like Gecko'
    ]
    
    index = random.randrange(len(rand_uas))
    return rand_uas[index].format(
        win_ver=random.choice(win_vers),
        feature=random.choice(features),
        br_ver=random.choice(br_vers[index])
    )

def replace_html_codes(txt):
    txt = re.sub(r"(&#[0-9]+)([^;^0-9]+)", r"\1;", txt)
    txt = html.parser.HTMLParser().unescape(txt)
    txt = txt.replace("&quot;", "\"").replace("&amp;", "&")
    return txt

def check_playable(url):
    """
    checks if passed url is a live link
    :param str url: stream url
    :return: playable stream url or None
    :rtype: str or None
    """

    try:
        headers = url.rsplit('|', 1)[1]
    except IndexError:
        headers = ''
    headers = quote_plus(headers).replace('%3D', '=') if ' ' in headers else headers
    headers = dict(parse_qsl(headers))

    try:
        if url.startswith('http') and '.m3u8' in url:
            result = requests.head(url.split('|')[0], headers=headers, timeout=5)
            if result.status_code == 200:
                return url
        elif url.startswith('http'):
            result = requests.head(url.split('|')[0], headers=headers, timeout=5)
            if result.status_code == 200:
                return url
        elif resolveurl.HostedMediaFile(url).valid_url():
            resolved_url = resolveurl.resolve(url)
            if resolved_url:
                return resolved_url
    except requests.RequestException as e:
        xbmc.log(f"Error checking playable URL: {str(e)}", xbmc.LOGERROR)
    except Exception as e:
        xbmc.log(f"Error resolving URL with resolveurl: {str(e)}", xbmc.LOGERROR)
    
    return None

def get_rd_domains():
    try:
        db_path = xbmc.translatePath(xbmcaddon.Addon("plugin.video.asguard").getAddonInfo('profile'))
        db_path = os.path.join(db_path, 'asguardcache.db')
        dbcon = sqlite3.connect(db_path)
        dbcur = dbcon.cursor()
        dbcur.execute("CREATE TABLE IF NOT EXISTS rd_domains (domains TEXT, added TEXT)")
        dbcur.execute("SELECT * FROM rd_domains")
        match = dbcur.fetchone()
        if match:
            sources = json.loads(match[0])
            return sources
        else:
            url = 'https://api.real-debrid.com/rest/1.0/hosts/domains'
            domains = requests.get(url).json()
            dbcur.execute("INSERT INTO rd_domains (domains, added) VALUES (?, ?)", (json.dumps(domains), datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
            dbcon.commit()
            return domains
    except Exception as e:
        xbmc.log(f"Error accessing RD domains: {str(e)}", xbmc.LOGERROR)
        return []

def get_ad_domains():
    try:
        db_path = xbmc.translatePath(xbmcaddon.Addon("plugin.video.asguard").getAddonInfo('profile'))
        db_path = os.path.join(db_path, 'asguardcache.db')
        dbcon = sqlite3.connect(db_path)
        dbcur = dbcon.cursor()
        dbcur.execute("CREATE TABLE IF NOT EXISTS ad_domains (domains TEXT, added TEXT)")
        dbcur.execute("SELECT * FROM ad_domains")
        match = dbcur.fetchone()
        if match:
            sources = json.loads(match[0])
            return sources
        else:
            # Check AllDebrid API status
            status_url = 'https://api.alldebrid.com/v4/status?agent=Asguard'
            status_response = requests.get(status_url)
            status_response.raise_for_status()
            status = status_response.json().get('status', {}).get('status')
            if status != 'ok':
                # Try with API key from settings
                api_key = xbmcaddon.Addon().getSetting('alldebrid_api_key')
                if api_key:
                    status_url = f'https://api.alldebrid.com/v4/status?agent=Asguard&apikey={api_key}'
                    status_response = requests.get(status_url)
                    status_response.raise_for_status()
                    status = status_response.json().get('status', {}).get('status')
                    if status != 'ok':
                        xbmc.log(f"AllDebrid API is not available: {status_response.json()}", xbmc.LOGERROR)
                        return []
                else:
                    xbmc.log(f"AllDebrid API is not available and no API key found in settings: {status_response.json()}", xbmc.LOGERROR)
                    return []

            # Fetch AllDebrid hosts
            api_key = xbmcaddon.Addon().getSetting('alldebrid_api_key')
            url = f'https://api.alldebrid.com/v4/hosts?agent=Asguard&apikey={api_key}'
            response = requests.get(url)
            response.raise_for_status()  # Ensure we raise an error for bad responses
            domains = response.json().get('hosts', [])
            dbcur.execute("INSERT INTO ad_domains (domains, added) VALUES (?, ?)", (json.dumps(domains), datetime.datetime.now().strftime("%Y-%m-%d %H:%M")))
            dbcon.commit()
            return domains
    except requests.RequestException as e:
        xbmc.log(f"Network error accessing AD domains: {str(e)}", xbmc.LOGERROR)
    except sqlite3.DatabaseError as e:
        xbmc.log(f"Database error accessing AD domains: {str(e)}", xbmc.LOGERROR)
    except Exception as e:
        xbmc.log(f"Unexpected error accessing AD domains: {str(e)}", xbmc.LOGERROR)
    finally:
        if 'dbcon' in locals():
            dbcon.close()
    return []

