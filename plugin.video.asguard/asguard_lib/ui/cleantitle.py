
import re

from six import ensure_str, ensure_text, PY2
from six.moves.urllib_parse import unquote


def get(title):
	try:
		if not title: return
		title = re.sub(r'(&#[0-9]+)([^;^0-9]+)', '\\1;\\2', title) # fix html codes with missing semicolon between groups
		title = re.sub(r'&#(\d+);', '', title).lower()
		title = title.replace('&quot;', '\"').replace('&amp;', '&').replace('&nbsp;', '')
		#title = re.sub(r'[<\[({].*?[})\]>]|[^\w0-9]|[_]', '', title) #replaced with lines below to stop removing () and everything between.
		title = re.sub(r'\([^\d]*(\d+)[^\d]*\)', '', title) #eliminate all numbers between ()
		title = re.sub(r'[<\[{].*?[}\]>]|[^\w0-9]|[_]', '', title)
		return title
	except:
		import log_utils
		log_utils.error()
		return title

def getsearch(title):
    if not title:
        return
    title = ensure_str(title, errors='ignore')
    title = title.lower()
    title = re.sub('&#(\d+);', '', title)
    title = re.sub('(&#[0-9]+)([^;^0-9]+)', '\\1;\\2', title)
    title = title.replace('&quot;', '\"').replace('&amp;', '&').replace('–', '-')
    title = re.sub('\\\|/|-|–|:|;|!|\*|\?|"|\'|<|>|\|', '', title)
    return title

def get_simple(title):
	try:
		if not title: return
		title = re.sub(r'(&#[0-9]+)([^;^0-9]+)', '\\1;\\2', title).lower()# fix html codes with missing semicolon between groups
		title = re.sub(r'&#(\d+);', '', title)
		title = re.sub(r'(\d{4})', '', title)
		title = title.replace('&quot;', '\"').replace('&amp;', '&').replace('&nbsp;', '')
		title = re.sub(r'\n|[()[\]{}]|[:;–\-",\'!_.?~$@]|\s', '', title) # stop trying to remove alpha characters "vs" or "v", they're part of a title
		title = re.sub(r'<.*?>', '', title) # removes tags
		return title
	except:
		import log_utils
		log_utils.error()
		return title

def geturl(title):
	if not title: return
	try:
		title = title.lower().rstrip()
		try: title = title.translate(None, ':*?"\'\.<>|&!,')
		except:
			try: title = title.translate(title.maketrans('', '', ':*?"\'\.<>|&!,'))
			except:
				for c in ':*?"\'\.<>|&!,': title = title.replace(c, '')
		title = title.replace('/', '-').replace(' ', '-').replace('--', '-').replace('–', '-').replace('!', '')
		return title
	except:
		import log_utils
		log_utils.error()
		return title

def normalize(title):
	try:
		import unicodedata
		title = ''.join(c for c in unicodedata.normalize('NFKD', title) if unicodedata.category(c) != 'Mn')
		return str(title)
	except:
		import log_utils
		log_utils.error()
		return title

def get_plus(title):
    if not title:
        return
    title = getsearch(title)
    title = title.replace(' ', '+')
    title = title.replace('++', '+')
    return title

def match_alias(title, aliases):
    try:
        for alias in aliases:
            if get(title) == get(alias['title']):
                return True
        return False
    except:
        return False


def match_year(item, year, premiered=None):
    try:
        if premiered == None:
            check1 = [(int(year))]
            check2 = [(int(year)-1), (int(year)), (int(year)+1)]
        else:
            check1 = [(int(year)), (int(premiered))]
            check2 = [(int(year)-1), (int(year)), (int(year)+1), (int(premiered)-1), (int(premiered)), (int(premiered)+1)]
        if any(str(y) in str(item) for y in check1):
            return True
        if any(str(y) in str(item) for y in check2):
            return True
        return False
    except:
        return False