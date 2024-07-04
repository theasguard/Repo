import time
import random
import kodi
import importlib
import log_utils
from asguard_lib import scraper_utils, salts_utils, utils2
from asguard_lib.constants import VIDEO_TYPES
from asguard_lib.utils2 import i18n
from . import worker_pool

logger = log_utils.Logger.get_logger()

class ExternalScraperManager:
    def __init__(self, video):
        self.video = video
        self.hosters = []
        self.fails = set()
        self.counts = {}
        self.max_results = int(kodi.get_setting('source_results'))
        self.timeout = max_timeout = int(kodi.get_setting('source_timeout'))
        if max_timeout == 0: self.timeout = None

    def get_sources(self):
        begin = time.time()
        with kodi.ProgressDialog(i18n('getting_sources'), utils2.make_progress_msg(self.video), active=True) as pd:
            try:
                wp = worker_pool.WorkerPool()
                scrapers = self._get_relevant_scrapers()
                total_scrapers = len(scrapers)
                for i, cls in enumerate(scrapers):
                    if pd.is_canceled(): return False
                    scraper = cls(self.timeout)
                    wp.request(scraper_utils.parallel_get_sources, [scraper, self.video])
                    progress = i * 25 / total_scrapers
                    pd.update(progress, line2=i18n('requested_sources_from') % (cls.get_name()))
                    self.fails.add(cls.get_name())
                    self.counts[cls.get_name()] = 0

                result_count = 0
                while result_count < total_scrapers:
                    try:
                        logger.log('Waiting on sources - Timeout: %s' % (self.timeout), log_utils.LOGDEBUG)
                        result = wp.receive(self.timeout)
                        result_count += 1
                        hoster_count = len(result['hosters'])
                        self.counts[result['name']] = hoster_count
                        logger.log('Got %s Source Results from %s' % (hoster_count, result['name']), log_utils.LOGDEBUG)
                        progress = (result_count * 75 / total_scrapers) + 25
                        self.hosters += result['hosters']
                        self.fails.remove(result['name'])
                        if pd.is_canceled():
                            return False

                        if len(self.fails) > 5:
                            line3 = i18n('remaining_over') % (len(self.fails), total_scrapers)
                        else:
                            line3 = i18n('remaining_under') % (', '.join([name for name in self.fails]))
                        pd.update(progress, line2=i18n('received_sources_from') % (hoster_count, len(self.hosters), result['name']), line3=line3)

                        if self.max_results > 0 and len(self.hosters) >= self.max_results:
                            logger.log('Exceeded max results: %s/%s' % (self.max_results, len(self.hosters)), log_utils.LOGDEBUG)
                            self.fails = {}
                            break

                        if self.timeout > 0:
                            self.timeout = max_timeout - (time.time() - begin)
                            if self.timeout < 0: self.timeout = 0
                    except worker_pool.Empty:
                        logger.log('Get Sources Scraper Timeouts: %s' % (', '.join(self.fails)), log_utils.LOGWARNING)
                        break

                else:
                    logger.log('All source results received', log_utils.LOGDEBUG)
            finally:
                workers = wp.close()

        return self.hosters

    def _get_relevant_scrapers(self):
        # This function should return a list of relevant scraper classes
        # from both internal and external sources (e.g., Seren, CocoScrapers)
        scrapers = []
        # Add internal scrapers
        scrapers += salts_utils.relevant_scrapers(self.video.video_type)
        # Add external scrapers
        scrapers += self._get_external_scrapers()
        return scrapers

    def _get_external_scrapers(self):
        external_scrapers = []
        scraper_modules = ['seren_scrapers', 'coco_scrapers']
        for module_name in scraper_modules:
            try:
                module = importlib.import_module(module_name)
                external_scrapers.append(module.Scraper)
            except ImportError:
                logger.log(f'{module_name} not available', log_utils.LOGWARNING)
        return external_scrapers