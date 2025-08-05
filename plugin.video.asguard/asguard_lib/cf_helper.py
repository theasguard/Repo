"""
Simple Cloudflare Bypass Helper for Asguard Scrapers
Copyright (C) 2024 MrBlamo

Easy-to-use helper functions that can be added to any scraper to bypass Cloudflare protection.
This module provides simple drop-in replacements for HTTP requests.

Usage in any scraper:
    from asguard_lib.cf_helper import bypass_cf_get
    
    # Replace: html = self._http_get(url)
    # With:    html = bypass_cf_get(self, url)
"""

import time
import random
import urllib.request
import urllib.error
import urllib.parse
from bs4 import BeautifulSoup

import log_utils

logger = log_utils.Logger.get_logger()

def get_cf_headers(user_agent=None, referer=None):
    """Generate browser-like headers to bypass basic CF protection"""
    if not user_agent:
        user_agents = [
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/120.0',
            'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
        ]
        user_agent = random.choice(user_agents)
    
    headers = {
        'User-Agent': user_agent,
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.5',
        'Accept-Encoding': 'gzip, deflate',
        'Connection': 'keep-alive',
        'Upgrade-Insecure-Requests': '1',
    }
    
    if referer:
        headers['Referer'] = referer
    
    return headers

def is_cloudflare_challenge(html):
    """Detect if the response contains Cloudflare protection"""
    if not html:
        return False
    
    html_lower = html.lower()
    cf_indicators = [
        'checking your browser before accessing',
        'cf-browser-verification',
        'cloudflare',
        'cf-captcha',
        'ray id:'
    ]
    
    return any(indicator in html_lower for indicator in cf_indicators)

def bypass_cf_get(scraper_instance, url, max_retries=2, delay_range=(2, 5)):
    """
    Drop-in replacement for _http_get with Cloudflare bypass
    
    Args:
        scraper_instance: The scraper instance (to access base_url, _http_get, etc.)
        url: Target URL  
        max_retries: Number of retry attempts
        delay_range: Tuple of (min, max) seconds for random delays
        
    Returns:
        HTML content or empty string if failed
    """
    
    logger.log(f'CF Helper: Attempting to get {url}', log_utils.LOGDEBUG)
    
    # Method 1: Try standard scraper method first
    try:
        html = scraper_instance._http_get(url, require_debrid=True)
        if html and not is_cloudflare_challenge(html):
            logger.log('CF Helper: Standard method successful', log_utils.LOGDEBUG)
            return html
        elif is_cloudflare_challenge(html):
            logger.log('CF Helper: Cloudflare challenge detected, trying bypass', log_utils.LOGDEBUG)
    except Exception as e:
        logger.log(f'CF Helper: Standard method failed: {e}', log_utils.LOGDEBUG)
        html = None
    
    # Method 2: Try enhanced headers and delays
    for attempt in range(max_retries):
        try:
            logger.log(f'CF Helper: Bypass attempt {attempt + 1}/{max_retries}', log_utils.LOGDEBUG)
            
            # Add random delay to simulate human behavior
            if attempt > 0:
                delay = random.uniform(*delay_range)
                logger.log(f'CF Helper: Adding {delay:.1f}s delay', log_utils.LOGDEBUG)
                time.sleep(delay)
            
            # Generate browser-like headers
            base_url = getattr(scraper_instance, 'base_url', '')
            headers = get_cf_headers(referer=base_url)
            
            # Make request with enhanced headers
            html = scraper_instance._http_get(url, headers=headers, require_debrid=True)
            
            if html and not is_cloudflare_challenge(html):
                logger.log('CF Helper: Enhanced method successful', log_utils.LOGDEBUG)
                return html
            elif is_cloudflare_challenge(html):
                logger.log(f'CF Helper: Still getting CF challenge on attempt {attempt + 1}', log_utils.LOGDEBUG)
            
        except Exception as e:
            logger.log(f'CF Helper: Enhanced method attempt {attempt + 1} failed: {e}', log_utils.LOGDEBUG)
    
    # Method 3: Try the full Cloudflare bypass if available
    try:
        from .cloudflare_bypass import get_html_with_cf_bypass
        logger.log('CF Helper: Trying full CF bypass method', log_utils.LOGDEBUG)
        
        html = get_html_with_cf_bypass(url, max_retries=1)
        if html and not is_cloudflare_challenge(html):
            logger.log('CF Helper: Full CF bypass successful', log_utils.LOGDEBUG)
            return html
            
    except ImportError:
        logger.log('CF Helper: Full CF bypass not available', log_utils.LOGDEBUG)
    except Exception as e:
        logger.log(f'CF Helper: Full CF bypass failed: {e}', log_utils.LOGDEBUG)
    
    logger.log('CF Helper: All bypass methods failed', log_utils.LOGWARNING)
    return ''

def add_cf_bypass_to_scraper(scraper_class):
    """
    Decorator to automatically add CF bypass to any scraper
    
    Usage:
        @add_cf_bypass_to_scraper
        class MyScraper(scraper.Scraper):
            # Your scraper code here
    """
    
    # Store original _http_get method
    original_http_get = scraper_class._http_get
    
    def enhanced_http_get(self, url, **kwargs):
        """Enhanced _http_get with automatic CF bypass"""
        # Try original method first
        try:
            html = original_http_get(self, url, **kwargs)
            if html and not is_cloudflare_challenge(html):
                return html
        except:
            pass
        
        # Fall back to CF bypass
        return bypass_cf_get(self, url)
    
    # Replace the method
    scraper_class._http_get = enhanced_http_get
    
    return scraper_class

# Convenience functions for different bypass levels
def bypass_cf_simple(scraper_instance, url):
    """Simple CF bypass with minimal retries"""
    return bypass_cf_get(scraper_instance, url, max_retries=1, delay_range=(1, 3))

def bypass_cf_aggressive(scraper_instance, url):
    """Aggressive CF bypass with more retries and longer delays"""
    return bypass_cf_get(scraper_instance, url, max_retries=4, delay_range=(5, 10))

def bypass_cf_stealth(scraper_instance, url):
    """Stealth CF bypass with human-like timing"""
    return bypass_cf_get(scraper_instance, url, max_retries=3, delay_range=(3, 8)) 