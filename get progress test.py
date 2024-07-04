def parallel_get_progress(trakt_id, cached, cache_limit):
    def _get_progress(trakt_id, cached, cache_limit, result):
        progress = trakt_api.get_show_progress(trakt_id, full=True, cached=cached, cache_limit=cache_limit)
        progress['trakt'] = trakt_id  # add in a hacked show_id to be used to match progress up to the show its for
        logger.log('Got progress for Trakt ID: %s' % (trakt_id), log_utils.LOGDEBUG)
        result.append(progress)

    result = []
    threads = []
    for id in trakt_id:
        thread = threading.Thread(target=_get_progress, args=(id, cached, cache_limit, result))
        threads.append(thread)
        thread.start()

    for thread in threads:
        thread.join()

    return result
