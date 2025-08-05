# -*- coding: utf-8 -*-

'''
    Covenant Add-on
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
'''
import json
from asguard_lib import client

TRAKT_API_URL = 'https://api.trakt.tv'
TRAKT_API_KEY = '523a3a5e356f78b0e4d3b4eddfc23b704f7576d69cd4229317304cc21e9753a7'  # Replace with your Trakt API key
TRAKT_API_VERSION = '2'

def get_scene_episode_number(tvdbid, season, episode):
    headers = {
        'Content-Type': 'application/json',
        'trakt-api-key': TRAKT_API_KEY,
        'trakt-api-version': TRAKT_API_VERSION
    }

    try:
        url = f'{TRAKT_API_URL}/search/tvdb/{tvdbid}?type=show'
        response = client.request(url, headers=headers)
        if response:
            show_data = json.loads(response)
            if show_data:
                show_id = show_data[0]['show']['ids']['trakt']
                url = f'{TRAKT_API_URL}/shows/{show_id}/seasons/{season}/episodes/{episode}'
                response = client.request(url, headers=headers)
                if response:
                    episode_data = json.loads(response)
                    if episode_data:
                        return episode_data['season'], episode_data['number']
    except Exception as e:
        print(f'Error fetching data from Trakt API: {e}')

    return season, episode