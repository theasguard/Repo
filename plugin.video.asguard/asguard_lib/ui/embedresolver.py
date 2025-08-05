from asguard_lib.utils2 import i18n
import xbmc
import kodi
import traceback
from asguard_lib import control
from asguard_lib.ui import embed_extractor
try:
    import resolveurl
except ImportError:
    kodi.notify(msg=i18n('smu_failed'), duration=5000)

class EmbedResolver:
    def __init__(self, sources, source_select=False):
        self.sources = sources
        self.source_select = source_select
        self.return_data = None
        self.canceled = False
        self.resolvers = resolveurl

    def resolve(self):
        # Move last played source to top of list
        if len(self.sources) > 1 and not self.source_select:
            last_played = control.getSetting('last_played_source')
            for index, source in enumerate(self.sources):
                if source['type'] == 'embed' and str(source['class']) + " ".join(map(str, source['info'])) == last_played:
                    self.sources.insert(0, self.sources.pop(index))
                    break
                elif str(source['release_title']) == last_played:
                    self.sources.insert(0, self.sources.pop(index))
                    break

        try:
            # Begin resolving links
            for i in self.sources:
                try:
                    if self.is_canceled():
                        return

                    if i['type'] == 'embed':
                        stream_link = embed_extractor.load_video_from_url(i['hash'])

                        if stream_link is None:
                            continue
                        else:
                            self.return_data = stream_link
                            if i.get('subs') or i.get('skip'):
                                self.return_data = {'url': stream_link}
                                if i.get('subs'):
                                    self.return_data.update({'subs': i.get('subs')})
                                if i.get('skip'):
                                    self.return_data.update({'skip': i.get('skip')})
                            return

                except:
                    traceback.print_exc()
                    continue

        except:
            traceback.print_exc()

    def is_canceled(self):
        return self.canceled