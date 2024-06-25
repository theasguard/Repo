try: from .providers.orionoid import Orionoid # Kodi 19
except: from providers.orionoid import Orionoid
if provider == Orionoid.Id:
    max_results = Orionoid.limit()
else:
	def get_max_results():
		global max_results
		return max_results
	max_results = get_max_results()
