import sys
import xbmcaddon
import xbmcgui
import xbmcplugin
import kodi
import log_utils
from asguard_lib.wako_integration import WakoIntegration, wako_sources_menu
from asguard_lib import utils2

ADDON = xbmcaddon.Addon()
ADDON_ID = ADDON.getAddonInfo('id')

class WakoService:
    def __init__(self):
        self.wako = WakoIntegration()
        self.wako.api_key = kodi.get_setting('wako_api_key')
    
    def run(self):
        handle = int(sys.argv[1])
        params = utils2.get_params()
        
        mode = params.get('mode')
        
        if mode == 'wako_sources':
            self.show_sources(params)
        elif mode == 'wako_settings':
            self.show_settings()
        elif mode == 'wako_search':
            self.search_wako(params)
    
    def show_sources(self, params):
        imdb_id = params.get('imdb_id')
        season = params.get('season')
        episode = params.get('episode')
        
        if not imdb_id:
            kodi.notify('No IMDB ID provided')
            return
        
        sources = self.wako.get_sources(imdb_id, season, episode)
        
        if not sources:
            kodi.notify('No wako sources found')
            return
        
        items = []
        for source in sources:
            label = f"{source['name']} [{source['quality']}]"
            if source['verified']:
                label = f"✓ {label}"
            
            list_item = xbmcgui.ListItem(label)
            list_item.setInfo('video', {
                'title': label,
                'plot': f"Size: {source['size']}\nSeeds: {source['seeds']}\nPeers: {source['peers']}"
            })
            
            if source['debrid_required']:
                list_item.setProperty('debrid_required', 'true')
            
            items.append((source['url'], list_item, False))
        
        xbmcplugin.addDirectoryItems(int(sys.argv[1]), items)
        xbmcplugin.endOfDirectory(int(sys.argv[1]))
    
    def show_settings(self):
        api_key = kodi.get_keyboard('Enter wako API key', self.wako.api_key)
        if api_key:
            kodi.set_setting('wako_api_key', api_key)
            self.wako.api_key = api_key
            kodi.notify('Settings saved')
    
    def search_wako(self, params):
        query = params.get('query', '')
        if not query:
            query = kodi.get_keyboard('Search wako')
        
        if query:
            results = self.wako.search_title(query)
            # Display search results
            items = []
            for item in results:
                label = item.get('title', 'Unknown')
                list_item = xbmcgui.ListItem(label)
                list_item.setInfo('video', {
                    'title': label,
                    'year': item.get('year', ''),
                    'plot': item.get('overview', '')
                })
                items.append((f"plugin://{ADDON_ID}/?mode=wako_sources&imdb_id={item.get('imdb_id')}", list_item, True))
            
            xbmcplugin.addDirectoryItems(int(sys.argv[1]), items)
            xbmcplugin.endOfDirectory(int(sys.argv[1]))

if __name__ == "__main__":
    service = WakoService()
    service.run()