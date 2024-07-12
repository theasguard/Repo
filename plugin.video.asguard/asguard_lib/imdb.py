import requests
import json
import xbmcgui
import xbmcaddon


# Get the TMDb API key from Kodi add-on settings
addon = xbmcaddon.Addon()
TMDB_API_KEY = addon.getSetting('tmdb_key')
# TMDb API endpoint
TMDB_API_URL = 'https://api.themoviedb.org/3'



class IMDbDetails:
    def __init__(self):
        self.api_key = TMDB_API_KEY

    def get_movie_details(self, imdb_id):
        url = f'{TMDB_API_URL}/find/{imdb_id}?api_key={self.api_key}&external_source=imdb_id'
        response = requests.get(url)
        if response.status_code == 200:
            data = json.loads(response.text)
            if data['movie_results']:
                movie = data['movie_results'][0]
                return {
                    'title': movie['title'],
                    'year': movie['release_date'].split('-')[0],
                    'imdb_id': imdb_id,
                    'genre': ', '.join([genre['name'] for genre in movie['genre_ids']]),
                    'plot': movie['overview'],
                    'poster': f"https://image.tmdb.org/t/p/w500{movie['poster_path']}",
                    'rating': movie['vote_average'],
                    'director': 'N/A',  # TMDb does not provide director info in this endpoint
                    'cast': 'N/A'  # TMDb does not provide cast info in this endpoint
                }
        return None

    def get_tv_show_details(self, imdb_id):
        url = f'{TMDB_API_URL}/find/{imdb_id}?api_key={self.api_key}&external_source=imdb_id'
        response = requests.get(url)
        if response.status_code == 200:
            data = json.loads(response.text)
            if data['tv_results']:
                show = data['tv_results'][0]
                return {
                    'title': show['name'],
                    'year': show['first_air_date'].split('-')[0],
                    'imdb_id': imdb_id,
                    'genre': ', '.join([genre['name'] for genre in show['genre_ids']]),
                    'plot': show['overview'],
                    'poster': f"https://image.tmdb.org/t/p/w500{show['poster_path']}",
                    'rating': show['vote_average'],
                    'creator': 'N/A',  # TMDb does not provide creator info in this endpoint
                    'cast': 'N/A'  # TMDb does not provide cast info in this endpoint
                }
        return None

    def get_episode_details(self, imdb_id, season, episode):
        # First, get the TV show ID from the IMDb ID
        url = f'{TMDB_API_URL}/find/{imdb_id}?api_key={self.api_key}&external_source=imdb_id'
        response = requests.get(url)
        if response.status_code == 200:
            data = json.loads(response.text)
            if data['tv_results']:
                show_id = data['tv_results'][0]['id']
                # Now, get the episode details using the show ID, season, and episode number
                url = f'{TMDB_API_URL}/tv/{show_id}/season/{season}/episode/{episode}?api_key={self.api_key}'
                response = requests.get(url)
                if response.status_code == 200:
                    data = json.loads(response.text)
                    return {
                        'title': data['name'],
                        'season': season,
                        'episode': episode,
                        'imdb_id': imdb_id,
                        'air_date': data['air_date'],
                        'plot': data['overview'],
                        'rating': data['vote_average'],
                        'director': 'N/A',  # TMDb does not provide director info in this endpoint
                        'cast': ', '.join([cast['name'] for cast in data['guest_stars']])
                    }
        return None

# Example usage
imdb_details = IMDbDetails()
movie_details = imdb_details.get_movie_details('tt0111161')  # Replace with your movie IMDb ID
tv_show_details = imdb_details.get_tv_show_details('tt0903747')  # Replace with your TV show IMDb ID
episode_details = imdb_details.get_episode_details('tt0903747', 1, 1)  # Replace with your TV show IMDb ID, season, and episode

# Print the results
print('Movie Details:')
print(json.dumps(movie_details, indent=4))
print('TV Show Details:')
print(json.dumps(tv_show_details, indent=4))
print('Episode Details:')
print(json.dumps(episode_details, indent=4))