"""
Enhanced Cloudflare Bypass Utility for Asguard Kodi Addon
Copyright (C) 2024 MrBlamo

Provides multiple methods to bypass different types of Cloudflare protection:
- Basic HTTP challenges  
- JavaScript challenges
- CAPTCHA challenges
- Bot detection
- Rate limiting

Usage:
    from asguard_lib.cloudflare_bypass import CFBypass
    
    cf = CFBypass()
    html = cf.get_html(url, headers=custom_headers, max_retries=3)
"""

import time
import re
import json
import random
import urllib.parse
import urllib.request
import urllib.error
from bs4 import BeautifulSoup

import kodi
import log_utils
from . import scraper_utils
from .constants import USER_AGENT

logger = log_utils.Logger.get_logger()

class CFBypass:
    """Enhanced Cloudflare bypass with multiple methods"""
    
    def __init__(self, timeout=30):
        self.timeout = timeout
        self.session_cookies = {}
        self.last_request_time = 0
        self.min_request_delay = 2  # Minimum seconds between requests
        
        # Enhanced User-Agent pool for rotation
        self.user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/119.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.1 Safari/605.1.15'
        ]
    
    def get_random_user_agent(self):
        """Get a random realistic user agent"""
        return random.choice(self.user_agents)
    
    def add_request_delay(self):
        """Add delay between requests to avoid rate limiting"""
        current_time = time.time()
        time_since_last = current_time - self.last_request_time
        
        if time_since_last < self.min_request_delay:
            delay = self.min_request_delay - time_since_last + random.uniform(0.5, 1.5)
            logger.log(f'CFBypass: Adding {delay:.2f}s delay to avoid rate limiting', log_utils.LOGDEBUG)
            time.sleep(delay)
        
        self.last_request_time = time.time()
    
    def get_browser_headers(self, referer=None, extra_headers=None):
        """Generate realistic browser headers"""
        headers = {
            'User-Agent': self.get_random_user_agent(),
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9',
            'Accept-Encoding': 'gzip, deflate, br',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Cache-Control': 'max-age=0'
        }
        
        if referer:
            headers['Referer'] = referer
            headers['Sec-Fetch-Site'] = 'same-origin'
        
        if extra_headers:
            headers.update(extra_headers)
        
        return headers
    
    def detect_cloudflare_protection(self, html, response_code=None):
        """Detect different types of Cloudflare protection"""
        if not html:
            return None
        
        html_lower = html.lower()
        
        # Check for various CF protection indicators
        cf_indicators = {
            'challenge': [
                'checking your browser before accessing',
                'browser verification',
                'cf-browser-verification',
                'ray id:',
                'cloudflare'
            ],
            'captcha': [
                'cf-captcha-bookmark',
                'captcha',
                'recaptcha',
                'cf-captcha'
            ],
            'block': [
                'access denied',
                'blocked',
                'error 1020',
                'error 1015'
            ],
            'rate_limit': [
                'rate limited',
                'too many requests',
                '429',
                'error 1015'
            ]
        }
        
        for protection_type, indicators in cf_indicators.items():
            for indicator in indicators:
                if indicator in html_lower:
                    logger.log(f'CFBypass: Detected {protection_type} protection', log_utils.LOGDEBUG)
                    return protection_type
        
        # Check response codes
        if response_code in [403, 503, 429]:
            if any(term in html_lower for term in ['cloudflare', 'cf-', 'ray id']):
                logger.log(f'CFBypass: Detected CF protection via response code {response_code}', log_utils.LOGDEBUG)
                return 'challenge'
        
        return None
    
    def bypass_js_challenge(self, url, html, headers=None):
        """Attempt to solve JavaScript challenge"""
        try:
            logger.log('CFBypass: Attempting to solve JS challenge', log_utils.LOGDEBUG)
            
            # Look for challenge form
            soup = BeautifulSoup(html, 'html.parser')
            form = soup.find('form', {'id': 'challenge-form'}) or soup.find('form')
            
            if not form:
                logger.log('CFBypass: No challenge form found', log_utils.LOGDEBUG)
                return None
            
            # Extract form action and method
            action = form.get('action', '')
            method = form.get('method', 'POST').upper()
            
            if action.startswith('/'):
                parsed_url = urllib.parse.urlparse(url)
                action = f"{parsed_url.scheme}://{parsed_url.netloc}{action}"
            
            # Extract hidden form fields
            form_data = {}
            for input_field in form.find_all('input', {'type': 'hidden'}):
                name = input_field.get('name')
                value = input_field.get('value', '')
                if name:
                    form_data[name] = value
            
            # Add delay to simulate human behavior
            time.sleep(random.uniform(4, 6))
            
            # Submit challenge form
            if method == 'POST':
                data = urllib.parse.urlencode(form_data).encode('utf-8')
            else:
                data = None
                if form_data:
                    action += '?' + urllib.parse.urlencode(form_data)
            
            # Make request with enhanced headers
            if not headers:
                headers = self.get_browser_headers(referer=url)
            
            request = urllib.request.Request(action, data=data, headers=headers)
            response = urllib.request.urlopen(request, timeout=self.timeout)
            
            result_html = response.read().decode('utf-8', errors='ignore')
            
            # Check if challenge was solved
            if not self.detect_cloudflare_protection(result_html):
                logger.log('CFBypass: JS challenge solved successfully', log_utils.LOGDEBUG)
                return result_html
            
        except Exception as e:
            logger.log(f'CFBypass: Error solving JS challenge: {e}', log_utils.LOGDEBUG)
        
        return None
    
    def get_html(self, url, headers=None, max_retries=3, method='GET', data=None):
        """
        Enhanced method to get HTML with Cloudflare bypass
        
        Args:
            url: Target URL
            headers: Optional custom headers
            max_retries: Maximum retry attempts
            method: HTTP method (GET/POST)
            data: POST data if needed
            
        Returns:
            HTML content or None if failed
        """
        
        logger.log(f'CFBypass: Getting URL with bypass: {url}', log_utils.LOGDEBUG)
        
        # Add request delay
        self.add_request_delay()
        
        # Use provided headers or generate browser-like ones
        if not headers:
            headers = self.get_browser_headers()
        
        for attempt in range(max_retries + 1):
            try:
                # Rotate user agent on retries
                if attempt > 0:
                    headers['User-Agent'] = self.get_random_user_agent()
                    # Add longer delay on retries
                    time.sleep(random.uniform(3, 7))
                
                logger.log(f'CFBypass: Attempt {attempt + 1}/{max_retries + 1}', log_utils.LOGDEBUG)
                
                # Make HTTP request
                request = urllib.request.Request(url, data=data, headers=headers)
                response = urllib.request.urlopen(request, timeout=self.timeout)
                
                html = response.read()
                if hasattr(html, 'decode'):
                    html = html.decode('utf-8', errors='ignore')
                
                response_code = response.getcode()
                
                # Check for Cloudflare protection
                protection_type = self.detect_cloudflare_protection(html, response_code)
                
                if not protection_type:
                    logger.log('CFBypass: Successfully bypassed CF protection', log_utils.LOGDEBUG)
                    return html
                
                # Handle different protection types
                if protection_type == 'challenge':
                    logger.log('CFBypass: Detected challenge, attempting bypass', log_utils.LOGDEBUG)
                    bypassed_html = self.bypass_js_challenge(url, html, headers)
                    if bypassed_html:
                        return bypassed_html
                
                elif protection_type == 'rate_limit':
                    logger.log('CFBypass: Rate limited, adding longer delay', log_utils.LOGDEBUG)
                    time.sleep(random.uniform(10, 20))
                    continue
                
                elif protection_type == 'captcha':
                    logger.log('CFBypass: CAPTCHA detected - requires manual solving', log_utils.LOGWARNING)
                    # Fall back to existing cf_captcha module if available
                    try:
                        from . import cf_captcha
                        result = cf_captcha.solve(url, {}, headers['User-Agent'], 'CFBypass')
                        if result:
                            return result
                    except ImportError:
                        pass
                
                elif protection_type == 'block':
                    logger.log('CFBypass: Site is blocking access - may need different approach', log_utils.LOGWARNING)
                    break
                
            except urllib.error.HTTPError as e:
                if e.code in [403, 503, 429]:
                    logger.log(f'CFBypass: HTTP {e.code} error, retrying with different headers', log_utils.LOGDEBUG)
                    continue
                else:
                    logger.log(f'CFBypass: HTTP error {e.code}: {e}', log_utils.LOGWARNING)
                    break
                    
            except Exception as e:
                logger.log(f'CFBypass: Unexpected error: {e}', log_utils.LOGDEBUG)
                if attempt == max_retries:
                    break
                continue
        
        logger.log(f'CFBypass: Failed to bypass CF protection after {max_retries + 1} attempts', log_utils.LOGWARNING)
        return None
    
    def get_html_with_session(self, url, **kwargs):
        """Get HTML while maintaining session cookies"""
        # This could be extended to maintain cookies across requests
        return self.get_html(url, **kwargs)

# Convenience function for easy use in scrapers
def get_html_with_cf_bypass(url, headers=None, max_retries=3, **kwargs):
    """
    Convenience function to get HTML with Cloudflare bypass
    
    Usage in scrapers:
        from asguard_lib.cloudflare_bypass import get_html_with_cf_bypass
        html = get_html_with_cf_bypass(url, headers=custom_headers)
    """
    cf = CFBypass()
    return cf.get_html(url, headers=headers, max_retries=max_retries, **kwargs) 