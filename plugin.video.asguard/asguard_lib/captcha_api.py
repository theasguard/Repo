import requests
from time import sleep

# Add these values
API_KEY = 'b61fc27d04b54604f14a8e053dedda63'  # Your 2captcha API KEY
site_key = '6LfhhC4UAAAAACpqw0wI0w5qA93DN6ntoSx4m_PZ'  # site-key, read the 2captcha docs on how to get this
url = 'https://www1.mydownloadtube.com/'  # example url
proxy = '127.0.0.1:6969'  # example proxy

proxy = {'http': 'http://' + proxy, 'https': 'https://' + proxy}

s = requests.Session()

# here we post site key to 2captcha to get captcha ID (and we parse it here too)
captcha_id = s.post("http://2captcha.com/in.php?key={}&method=userrecaptcha&googlekey={}&pageurl={}".format(API_KEY, site_key, url), proxies=proxy).text.split('|')[1]
# then we parse gresponse from 2captcha response
recaptcha_answer = s.get("http://2captcha.com/res.php?key={}&action=get&id={}".format(API_KEY, captcha_id), proxies=proxy).text
print("solving ref captcha...")
while 'CAPCHA_NOT_READY' in recaptcha_answer:
    sleep(5)
    recaptcha_answer = s.get("http://2captcha.com/res.php?key={}&action=get&id={}".format(API_KEY, captcha_id), proxies=proxy).text
recaptcha_answer = recaptcha_answer.split('|')[1]

# we make the payload for the post data here, use something like mitmproxy or fiddler to see what is needed
payload = {
    'key': 'value',
    'gresponse': recaptcha_answer  # This is the response from 2captcha, which is needed for the post request to go through.
    }


# then send the post request to the url
response = s.post(url, payload, proxies=proxy)

# And that's all there is to it other than scraping data from the website, which is dynamic for every website.
