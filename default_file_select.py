def apply_urlresolver(hosters):
    """
    Filters and processes hosters using the resolveurl library and debrid services.

    This function applies filtering to the provided list of hosters based on the user's settings for unusable links and debrid services.
    It uses the resolveurl library to validate and resolve hosters, and it caches the results for known and unknown hosts.

    Args:
        hosters (list): A list of hoster dictionaries to be filtered and processed. Each dictionary should contain:
            - 'direct' (bool): Indicates if the link is a direct link.
            - 'host' (str): The hostname of the link.
            - 'class' (object): The scraper class instance that provided the hoster.

    Returns:
        list: A filtered list of hosters that are valid and optionally supported by debrid services.

    Detailed Description:
    - The function first checks the user's settings for filtering unusable links and showing debrid links.
    - If neither setting is enabled, the function returns the original list of hosters.
    - The function initializes a list of debrid resolvers using the resolveurl library. These resolvers are used to check if a host is supported by debrid services.
    - The function iterates over the list of hosters and applies the following logic:
        - If the hoster is not a direct link and has a host:
            - If filtering unusable links is enabled:
                - The function checks if the host is in the cache of unknown or known hosts.
                - If the host is unknown, it is added to the unknown hosts cache and skipped.
                - If the host is known, it is added to the filtered hosters list.
                - If the host is not in the cache, the function uses resolveurl to validate the host and updates the cache accordingly.
            - If filtering unusable links is not enabled, the hoster is added to the filtered hosters list.
            - The function checks if the host is supported by any debrid resolvers and updates the hoster with the supported debrid services.
        - If the hoster is a direct link or does not have a host, it is added to the filtered hosters list.
    - The function logs the discarded hosts and returns the filtered list of hosters.

    Example Usage:
        filtered_hosters = apply_urlresolver(hosters)

    Notes:
    - The `debrid_resolvers` list is initialized with relevant resolvers from the resolveurl library that support universal links.
    - The `hmf` (HostedMediaFile) object is used to validate the host by creating a dummy media file with a fake media ID.

    References:
    - `resolveurl.relevant_resolvers`: Retrieves a list of relevant resolvers from the resolveurl library.
    - `resolveurl.HostedMediaFile`: Creates a HostedMediaFile object to validate and resolve media links.
    """
    filter_unusable = kodi.get_setting('filter_unusable') == 'true'
    show_debrid = kodi.get_setting('show_debrid') == 'true'
    if not filter_unusable and not show_debrid:
        return hosters
    
    debrid_resolvers = [resolver() for resolver in resolveurl.relevant_resolvers(order_matters=True) if resolver.isUniversal()]
    filtered_hosters = []
    debrid_hosts = {}
    unk_hosts = {}
    known_hosts = {}
    for hoster in hosters:
        if 'direct' in hoster and hoster['direct'] is False and hoster['host']:
            host = hoster['host']
            if filter_unusable:
                if host in unk_hosts:
                    logger.log('Unknown Hit: %s from %s' % (host, hoster['class'].get_name()), log_utils.LOGDEBUG)
                    unk_hosts[host] += 1
                    continue
                elif host in known_hosts:
                    logger.log('Known Hit: %s from %s' % (host, hoster['class'].get_name()), log_utils.LOGDEBUG)
                    known_hosts[host] += 1
                    filtered_hosters.append(hoster)
                else:
                    hmf = resolveurl.HostedMediaFile(host=host, media_id='12345678901', return_all=True)  # use dummy media_id to force host validation
                    logger.log('Hoster URL: %s' % (host), log_utils.LOGDEBUG)

                    if hmf:
                        logger.log('Known Miss: %s from %s' % (host, hoster['class'].get_name()), log_utils.LOGDEBUG)
                        known_hosts[host] = known_hosts.get(host, 0) + 1
                        filtered_hosters.append(hoster)
                    else:
                        logger.log('Unknown Miss: %s from %s' % (host, hoster['class'].get_name()), log_utils.LOGDEBUG)
                        unk_hosts[host] = unk_hosts.get(host, 0) + 1
                        continue
            else:
                filtered_hosters.append(hoster)
            
            if host in debrid_hosts:
                logger.log('Debrid cache found for %s: %s' % (host, debrid_hosts[host]), log_utils.LOGDEBUG)
                hoster['debrid'] = debrid_hosts[host]
            else:
                temp_resolvers = [resolver.name[:3].upper() for resolver in debrid_resolvers if resolver.valid_url('', host)]
                logger.log('%s supported by: %s' % (host, temp_resolvers), log_utils.LOGDEBUG)
                debrid_hosts[host] = temp_resolvers
                if temp_resolvers:
                    hoster['debrid'] = temp_resolvers
        else:
            filtered_hosters.append(hoster)
            
    logger.log('Discarded Hosts: %s' % (sorted(unk_hosts.items(), key=lambda x: x[1], reverse=True)), log_utils.LOGDEBUG)
    return filtered_hosters

@url_dispatcher.register(MODES.RESOLVE_SOURCE, ['mode', 'class_url', 'direct', 'video_type', 'trakt_id', 'class_name'], ['season', 'episode'])
@url_dispatcher.register(MODES.DIRECT_DOWNLOAD, ['mode', 'class_url', 'direct', 'video_type', 'trakt_id', 'class_name'], ['season', 'episode'])
def resolve_source(mode, class_url, direct, video_type, trakt_id, class_name, season='', episode=''):
    """
    Resolves a media source URL and initiates playback or download.

    This function identifies the appropriate scraper based on the provided class name,
    resolves the media source URL using the scraper, and then either plays or downloads
    the media based on the mode.

    Args:
        mode (str): The mode in which the function is called. It can be one of several modes such as 'RESOLVE_SOURCE', 'DIRECT_DOWNLOAD', etc.
        class_url (str): The URL fragment associated with the media source to be resolved.
        direct (bool): Indicates whether the URL is a direct link to the media file.
        video_type (str): The type of video, either 'movie' or 'episode'.
        trakt_id (str): The Trakt ID of the video.
        class_name (str): The name of the scraper class to be used for resolving the URL.
        season (str, optional): The season number (for TV shows). Defaults to ''.
        episode (str, optional): The episode number (for TV shows). Defaults to ''.

    Returns:
        bool: True if the media was successfully played or downloaded, False otherwise.

    Raises:
        Exception: If the URL resolution fails or the resolved URL is invalid.

    Detailed Description:
    - The function first identifies the appropriate scraper class based on the provided class name.
    - If the scraper class is found, an instance of the scraper is created.
    - The `resolve_link` method of the scraper instance is called to resolve the media source URL.
    - If the mode is 'DIRECT_DOWNLOAD', the function ends the Kodi directory and returns.
    - Otherwise, the `play_source` function is called to play or download the media.

    Example Usage:
        resolve_source(MODES.RESOLVE_SOURCE, 'http://example.com/video', False, VIDEO_TYPES.MOVIE, '12345', 'ExampleScraper')
    """
    for cls in salts_utils.relevant_scrapers(video_type):
        if cls.get_name() == class_name:
            scraper_instance = cls()
            break
    else:
        logger.log('Unable to locate scraper with name: %s' % (class_name), log_utils.LOGWARNING)
        return False

    hoster_url = scraper_instance.resolve_link(class_url)
    logger.log('Hoster URL resolved: %s' % (hoster_url), log_utils.LOGDEBUG)
    if mode == MODES.DIRECT_DOWNLOAD:
        kodi.end_of_directory()
    return play_source(mode, hoster_url, direct, video_type, trakt_id, season, episode)


@url_dispatcher.register(MODES.PLAY_TRAILER, ['stream_url'])
def play_trailer(stream_url):
    xbmc.Player().play(stream_url)

def download_subtitles(language, title, year, season, episode):
    srt_scraper = SRT_Scraper()
    tvshow_id = srt_scraper.get_tvshow_id(title, year)
    if tvshow_id is None:
        return

    subs = srt_scraper.get_episode_subtitles(language, tvshow_id, season, episode)
    sub_labels = [utils2.format_sub_label(sub) for sub in subs]

    index = 0
    if len(sub_labels) > 1 and kodi.get_setting('subtitle-autopick') == 'false':
        dialog = xbmcgui.Dialog()
        index = dialog.select(i18n('choose_subtitle'), sub_labels)

    if subs and index > -1:
        return srt_scraper.download_subtitle(subs[index]['url'])

def play_source(mode, hoster_url, direct, video_type, trakt_id, season='', episode=''):
    """
    Plays a media source in Kodi.

    This function handles the resolution and playback of a media source URL. It supports both direct and indirect URLs,
    resolves them using the `resolveurl` library, and manages playback properties such as resume points and metadata.

    Args:
        mode (str): The mode in which the function is called. It can be one of several modes such as 'GET_SOURCES', 'DOWNLOAD_SOURCE', etc.
        hoster_url (str): The URL of the media source to be played.
        direct (bool): Indicates whether the URL is a direct link to the media file.
        video_type (str): The type of video, either 'movie' or 'episode'.
        trakt_id (str): The Trakt ID of the video.
        season (str, optional): The season number (for TV shows). Defaults to ''.
        episode (str, optional): The episode number (for TV shows). Defaults to ''.

    Returns:
        bool: True if the media was successfully played or downloaded, False otherwise.

    Raises:
        Exception: If the URL resolution fails or the resolved URL is invalid.

    Detailed Description:
    - The function first checks if the `hoster_url` is None. If it is, it notifies the user of the failure and returns False.
    - If the URL is direct, it is used as-is for playback.
    - If the URL is indirect, it is resolved using the `resolveurl` library:
        - `resolveurl.HostedMediaFile(url=hoster_url)`: This function creates a `HostedMediaFile` object for the given URL.
        - `hmf.resolve()`: This function attempts to resolve the URL to a direct media link.
    - If the URL resolution fails, an exception is raised, and the user is notified of the failure.
    - The function then checks for a resume point if the video is not being downloaded or directly downloaded.
    - Metadata and artwork for the video are fetched from the Trakt API and set as properties.
    - If the mode is for downloading, the media is downloaded to the specified path.
    - If subtitles are enabled, they are downloaded and set as properties.
    - Finally, the media is played using `xbmc.Player().play()` or resolved using `xbmcplugin.setResolvedUrl()`.

    Example Usage:
        play_source(MODES.GET_SOURCES, 'http://example.com/video.mp4', True, VIDEO_TYPES.MOVIE, '12345')

    """
    if hoster_url is None:
        if direct is not None:
            kodi.notify(msg=i18n('resolve_failed') % (i18n('no_stream_found')), duration=7500)
        return False

    with kodi.WorkingDialog() as wd:
        if direct:
            logger.log('Treating hoster_url as direct: %s' % (hoster_url), log_utils.LOGDEBUG)
            stream_url = hoster_url
        else:
            wd.update_progress(25)

            hmf = resolveurl.HostedMediaFile(url=hoster_url, return_all=True)
            if not hmf:
                logger.log('Indirect hoster_url not supported by resolveurl: %s' % (hoster_url), log_utils.LOGDEBUG)
                stream_url = hoster_url
                logger.log('Stream URL: %s' % (stream_url), log_utils.LOGDEBUG)
            else:
                try:
                    stream_url = hmf.resolve()
                    logger.log('Resolved stream_url: %s' % (stream_url), log_utils.LOGDEBUG)

                    # Check if the resolved URL is a list of files
                    if isinstance(stream_url, list):
                        # Present a selection dialog to the user
                        names = [file['name'] for file in stream_url]
                        logger.log('Names: %s' % (names), log_utils.LOGDEBUG)
                        dialog = xbmcgui.Dialog()
                        index = dialog.select(i18n('choose_file'), names)
                        if index == -1:
                            return False
                        selected_url = stream_url[index]['link']
                        logger.log('Selected stream_url: %s' % (selected_url), log_utils.LOGDEBUG)
                        if resolveurl.HostedMediaFile(selected_url):
                            selected_url = resolveurl.resolve(selected_url)
                            logger.log('Re-resolved selected stream_url: %s' % (selected_url), log_utils.LOGDEBUG)
                        stream_url = selected_url
                except Exception as e:
                    try: 
                        msg = str(e)
                    except: 
                        msg = hoster_url
                    kodi.notify(msg=i18n('resolve_failed') % (msg), duration=7500)
                    return False
        wd.update_progress(50)
    
    resume_point = 0
    pseudo_tv = xbmcgui.Window(10000).getProperty('PseudoTVRunning').lower()
    if pseudo_tv != 'true' and mode not in [MODES.DOWNLOAD_SOURCE, MODES.DIRECT_DOWNLOAD]:
        if salts_utils.bookmark_exists(trakt_id, season, episode):
            if salts_utils.get_resume_choice(trakt_id, season, episode):
                resume_point = salts_utils.get_bookmark(trakt_id, season, episode)
                logger.log('Resume Point: %s' % (resume_point), log_utils.LOGDEBUG)
    
    with kodi.WorkingDialog() as wd:
        from_library = xbmc.getInfoLabel('Container.PluginName') == ''
        wd.update_progress(50)
        win = xbmcgui.Window(10000)
        win.setProperty('asguard.playing', 'True')
        win.setProperty('asguard.playing.trakt_id', str(trakt_id))
        win.setProperty('asguard.playing.season', str(season))
        win.setProperty('asguard.playing.episode', str(episode))
        win.setProperty('asguard.playing.library', str(from_library))
        if resume_point > 0:
            if kodi.get_setting('trakt_bookmark') == 'true':
                win.setProperty('asguard.playing.trakt_resume', str(resume_point))
            else:
                win.setProperty('asguard.playing.asguard_resume', str(resume_point))

        art = {'thumb': '', 'fanart': ''}
        info = {}
        show_meta = {}
        try:
            if video_type == VIDEO_TYPES.EPISODE:
                path = kodi.get_setting('tv-download-folder')
                file_name = utils2.filename_from_title(trakt_id, VIDEO_TYPES.TVSHOW)
                file_name = file_name % ('%02d' % int(season), '%02d' % int(episode))
    
                ep_meta = trakt_api.get_episode_details(trakt_id, season, episode)
                show_meta = trakt_api.get_show_details(trakt_id)
                if 'ids' in show_meta:
                    win.setProperty('script.trakt.ids', json.dumps(show_meta['ids']))
                else:
                    logger.log('Show metadata does not contain ids', log_utils.LOGWARNING)
                people = trakt_api.get_people(SECTIONS.TV, trakt_id) if kodi.get_setting('include_people') == 'true' else None
                info = salts_utils.make_info(ep_meta, show_meta, people)
                info = salts_utils.make_info(ep_meta, show_meta, people)
                art = image_scraper.get_images(VIDEO_TYPES.EPISODE, show_meta['ids'], season, episode)

    
                path = make_path(path, VIDEO_TYPES.TVSHOW, show_meta['title'], season=season)
                file_name = utils2.filename_from_title(show_meta['title'], VIDEO_TYPES.TVSHOW)
                file_name = file_name % ('%02d' % int(season), '%02d' % int(episode))
            else:
                path = kodi.get_setting('movie-download-folder')
                file_name = utils2.filename_from_title(trakt_id, video_type)
    
                movie_meta = trakt_api.get_movie_details(trakt_id)
                win.setProperty('script.trakt.ids', json.dumps(movie_meta['ids']))
                people = trakt_api.get_people(SECTIONS.MOVIES, trakt_id) if kodi.get_setting('include_people') == 'true' else None
                info = salts_utils.make_info(movie_meta, people=people)
                art = image_scraper.get_images(VIDEO_TYPES.MOVIE, movie_meta['ids'])
    
                path = make_path(path, video_type, movie_meta['title'], movie_meta['year'])
                file_name = utils2.filename_from_title(movie_meta['title'], video_type, movie_meta['year'])
        except TransientTraktError as e:
            logger.log('During Playback: %s' % (str(e)), log_utils.LOGWARNING)  # just log warning if trakt calls fail and leave meta and art blank
        wd.update_progress(75)

    if mode in [MODES.DOWNLOAD_SOURCE, MODES.DIRECT_DOWNLOAD]:
        utils.download_media(stream_url, path, file_name, kodi.Translations(strings.STRINGS))
        return True

    with kodi.WorkingDialog() as wd:
        wd.update_progress(75)
        if video_type == VIDEO_TYPES.EPISODE and utils2.srt_download_enabled() and show_meta:
            srt_path = download_subtitles(kodi.get_setting('subtitle-lang'), show_meta['title'], show_meta['year'], season, episode)
            if utils2.srt_show_enabled() and srt_path:
                logger.log('Setting srt path: %s' % (srt_path), log_utils.LOGDEBUG)
                win.setProperty('asguard.playing.srt', srt_path)
    
        listitem = xbmcgui.ListItem(path=stream_url)
        listitem.setArt({'icon': art['thumb'], 'thumb': art['thumb'], 'fanart': art['fanart']})
        listitem.setPath(stream_url)
        listitem.setInfo('video', info)
        wd.update_progress(100)

    if mode == MODES.RESOLVE_SOURCE or from_library or utils2.from_playlist():
        xbmcplugin.setResolvedUrl(int(sys.argv[1]), True, listitem)
    else:
        xbmc.Player().play(stream_url, listitem)
    return True
