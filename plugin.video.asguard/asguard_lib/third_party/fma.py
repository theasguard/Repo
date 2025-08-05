import requests

class FMAProvider:
    BASE_URL = "https://find-my-anime.dtimur.de/api"
    
    def search(self, query, provider="Anilist", include_adult=True, collection_consent=True):
        params = {
            "query": query,
            "provider": provider,
            "includeAdult": str(include_adult).lower(),
            "collectionConsent": str(collection_consent).lower()
        }
        
        try:
            response = requests.get(self.BASE_URL, params=params)
            response.raise_for_status()
            return self._parse_results(response.json())
        except requests.exceptions.RequestException as e:
            print(f"FMA API Error: {e}")
            return []

    def _parse_results(self, data):
        results = []
        for item in data:
            result = {
                "title": item.get("title"),
                "alt_titles": item.get("synonyms", []),
                "type": item.get("type"),
                "status": item.get("status"),
                "episodes": item.get("episodes"),
                "season": item.get("animeSeason", {}).get("season"),
                "year": item.get("animeSeason", {}).get("year"),
                "image": item.get("picture"),
                "thumbnail": item.get("thumbnail"),
                "duration": f"{item.get('duration', {}).get('value', 0)//60} min" if item.get('duration') else None,
                "sources": item.get("sources", []),
                "score": item.get("score", {}).get("arithmeticMean"),
                "tags": item.get("tags", []),
                "related": item.get("relatedAnime", []),
                "provider_ids": item.get("providerMapping", {}),
                "plot": item.get("description"),
                "episode_list": self._generate_episode_list(
                    item.get("episodes"),
                    item.get("status"),
                    item.get("animeSeason", {})
                )
            }
            results.append(result)
        return results

    def _generate_episode_list(self, total_episodes, status, season_info):
        if not total_episodes or total_episodes < 1:
            return []
        
        episodes = []
        base_date = self._estimate_season_dates(season_info)
        
        for ep in range(1, total_episodes + 1):
            episodes.append({
                "title": f"Episode {ep}",
                "episode": ep,
                "aired": self._calculate_air_date(base_date, ep) if base_date else "TBA",
                "is_available": status == "FINISHED" or ep <= self._available_episodes(status)
            })
        return episodes

    def _estimate_season_dates(self, season_info):
        # Simple estimation based on typical seasonal anime schedules
        season_map = {
            "WINTER": ("January", 1),
            "SPRING": ("April", 1),
            "SUMMER": ("July", 1),
            "FALL": ("October", 1)
        }
        if season_info.get("year") and season_info.get("season"):
            month, week = season_map.get(season_info["season"], (None, None))
            return f"{month} {week}, {season_info['year']}" if month else None
        return None

    def _calculate_air_date(self, base_date, episode_num):
        # Simple weekly progression from season start date
        from dateutil.parser import parse
        from dateutil.relativedelta import relativedelta
        try:
            start_date = parse(base_date)
            return (start_date + relativedelta(weeks=episode_num-1)).strftime("%Y-%m-%d")
        except:
            return "TBA"

    def _available_episodes(self, status):
        # Simple logic for ongoing series (adjust based on current date)
        if status == "ONGOING":
            return 3  # Example: assume 3 episodes have aired
        return 0
