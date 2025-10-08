import json
import requests
import urllib.parse
import log_utils
from asguard_lib import utils2

logger = log_utils.Logger.get_logger()
class WakoIntegration:
    def __init__(self, api_key=None, base_url="https://api.wako.app"):
        self.api_key = api_key
        self.base_url = base_url
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Asguard-Kodi-21/1.0',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        })
        
    def get_sources(self, imdb_id, season=None, episode=None):
        """Get streaming sources from wako for a specific title"""
        try:
            if season and episode:
                # TV Show episode
                url = f"{self.base_url}/sources/{imdb_id}/{season}/{episode}"
            else:
                # Movie
                url = f"{self.base_url}/sources/{imdb_id}"
                
            params = {
                'api_key': self.api_key,
                'quality': '1080p,720p',
                'limit': 50
            }
            
            response = self.session.get(url, params=params)
            response.raise_for_status()
            
            data = response.json()
            return self._parse_sources(data)
            
        except Exception as e:
            logger.log(f"Wako API Error: {str(e)}", log_utils.LOGERROR)
            return []
    
    def _parse_sources(self, data):
        """Parse wako API response into Asguard-compatible format"""
        sources = []
        
        if not isinstance(data, list):
            return sources
            
        for source in data:
            try:
                parsed_source = {
                    'name': source.get('name', 'Unknown'),
                    'url': source.get('url', ''),
                    'quality': source.get('quality', 'Unknown'),
                    'size': source.get('size', 0),
                    'seeds': source.get('seeds', 0),
                    'peers': source.get('peers', 0),
                    'source': 'wako',
                    'debrid_required': source.get('debrid_required', False),
                    'verified': source.get('verified', False)
                }
                
                # Validate URL
                if parsed_source['url'] and self._is_valid_url(parsed_source['url']):
                    sources.append(parsed_source)
                    
            except Exception as e:
                logger.log(f"Error parsing source: {str(e)}", log_utils.LOGWARNING)
                continue
                
        return sources
    
    def _is_valid_url(self, url):
        """Validate URL format"""
        try:
            result = urllib.parse.urlparse(url)
            return all([result.scheme, result.netloc])
        except:
            return False
    
    def search_title(self, query, media_type=None):
        """Search wako for titles"""
        try:
            url = f"{self.base_url}/search"
            params = {
                'api_key': self.api_key,
                'q': query,
                'type': media_type or 'movie,tv'
            }
            
            response = self.session.get(url, params=params)
            response.raise_for_status()
            
            return response.json()
            
        except Exception as e:
            logger.log(f"Wako Search Error: {str(e)}", log_utils.LOGERROR)
            return []

# Kodi integration functions
def wako_sources_menu(imdb_id, season=None, episode=None):
    """Display wako sources in Kodi menu"""
    import kodi
    
    wako = WakoIntegration()
    sources = wako.get_sources(imdb_id, season, episode)
    
    if not sources:
        kodi.notify('No sources found from wako')
        return
    
    items = []
    for source in sources:
        label = f"{source['name']} [{source['quality']}]"
        if source['verified']:
            label = f"✓ {label}"
        
        item = {
            'label': label,
            'path': source['url'],
            'is_playable': True,
            'info': {
                'title': label,
                'plot': f"Size: {utils2.format_size(source['size'])}\\nSeeds: {source['seeds']}"
            }
        }
        items.append(item)
    
    kodi.add_directory_items(items)

# Settings integration
def wako_settings():
    """Wako settings dialog"""
    import kodi
    # API Key setting
    api_key = kodi.get_setting('wako_api_key')
    new_key = kodi.get_keyboard('Enter wako API key', api_key)
    
    if new_key:
        kodi.set_setting('wako_api_key', new_key)
        kodi.notify('Wako API key updated')

# Main integration hook
def integrate_wako():
    """Register wako as a source provider"""
    from asguard_lib import source_manager
    
    wako = WakoIntegration()
    source_manager.register_provider('wako', wako.get_sources)
    
    log_utils.log("Wako integration initialized", log_utils.LOGINFO)

if __name__ == "__main__":
    integrate_wako()