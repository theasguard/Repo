try: from .providers.orionoid import Orionoid # Kodi 19
except: from providers.orionoid import Orionoid
if provider == Orionoid.Id:
    return Orionoid.streams(filtering)
