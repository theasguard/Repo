from resolveurl.plugins.alldebrid import AllDebridResolver
import json
import re

class AllDebrid:
    def __init__(self):
        self.resolver = AllDebridResolver()
        self.token = self.resolver.get_setting('token')
        self.api_url = 'https://api.alldebrid.com/v4'
        self.headers = {'User-Agent': self.resolver.USER_AGENT}

    def upload_magnet(self, magnet):
        url = f'{self.api_url}/magnet/upload?agent={self.resolver.AGENT}&apikey={self.token}&magnets[]={magnet}'
        result = json.loads(self.resolver.net.http_GET(url, headers=self.headers).content)
        if result.get('status', False) == "success":
            return result.get('data')
        else:
            raise Exception('Failed to upload magnet')

    def magnet_status(self, magnet_id):
        url = f'{self.api_url}/magnet/status?agent={self.resolver.AGENT}&apikey={self.token}&id={magnet_id}'
        result = json.loads(self.resolver.net.http_GET(url, headers=self.headers).content)
        if result.get('status', False) == "success":
            return result.get('data')
        else:
            raise Exception('Failed to get magnet status')

    def resolve_hoster(self, link):
        url = f'{self.api_url}/link/unlock?agent={self.resolver.AGENT}&apikey={self.token}&link={link}'
        result = json.loads(self.resolver.net.http_GET(url, headers=self.headers).content)
        if result.get('status', False) == "success":
            return result.get('data').get('link')
        else:
            raise Exception('Failed to resolve hoster link')

    def delete_magnet(self, magnet_id):
        url = f'{self.api_url}/magnet/delete?agent={self.resolver.AGENT}&apikey={self.token}&id={magnet_id}'
        result = json.loads(self.resolver.net.http_GET(url, headers=self.headers).content)
        if result.get('status', False) == "success":
            return True
        else:
            raise Exception('Failed to delete magnet')