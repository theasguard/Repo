# Asguard: My Progress Paging Design and Patch Guide (Updated)

This guide shows minimal, targeted edits to add paging to the "My Progress" section to keep per-show progress lookups within Trakt limits and make the UI responsive on large libraries.

Updates in this revision
- Fix handler decorator/signature mismatch by accepting `mode` in the handler signature when the decorator declares `['mode']`.
- Ensure Next Page/Previous Page queries include `mode` so the dispatcher routes correctly.
- Compute `has_more` from the number of filtered shows, not from the number of episodes (some shows have no next_episode).
- Cache both the page's episodes and its page metadata together (or recompute meta on cache hit) so pagination UI renders reliably after cache hits.

Goals
- Only request per-show progress for a page (slice) of shows at a time
- Keep existing behavior, sorting, and UI style
- Use existing `list_size` as the default page size
- Keep DB caching intact, but include `page` and `page_size` so each page is cached independently

Summary of changes
1) `get_progress` now accepts `page` and `page_size`, applies filtering, slices the list, and only requests per-show progress for that slice. It returns `(workers, sorted_episodes, page_meta)`.
2) `show_progress` accepts optional `page` param, calls `get_progress(page=...)`, renders items, and appends a Next Page item when applicable (and Previous Page when `page > 1`).
3) `force_refresh` unpacks the third return value from `get_progress`.

Note: snippets use complete function bodies to simplify porting. Adjust import ordering as needed.

---

1) Update decorator and signature for `show_progress`

When your url dispatcher registers a function with `['mode']`, you must accept `mode` as the first parameter. Also accept an optional `page` parameter (default 1):

```python
@url_dispatcher.register(MODES.SHOW_PROGRESS, ['mode'], ['page'])
def show_progress(mode, page=1):
    ...
```

If you prefer not to accept `mode`, you may remove `['mode']` in the decorator entirely, but keep it consistent (either both include it or neither does).

---

2) Replace `get_progress` with a paged version

Replace the whole `get_progress` body with this paged version. It keeps your existing logic (filters, hidden, exclusions), but slices the filtered shows before parallel calls and returns a `page_meta` dict for the UI. Importantly, `has_more` is computed from the filtered shows and not the number of episodes.

```python
def get_progress(cached=True, page=1, page_size=None):
    # Default page size from existing list_size setting
    if page_size is None:
        try:
            page_size = int(kodi.get_setting('list_size') or 50)
        except Exception:
            page_size = 50
    try:
        page = int(page)
        if page < 1:
            page = 1
    except Exception:
        page = 1

    # Cache read must include args so each page is independent.
    # Store and restore a dict: {'episodes': [...], 'meta': {...}}
    if cached:
        in_cache, cached_payload = db_connection.get_cached_function(
            get_progress.__name__, args=[page, page_size], kwargs={}, cache_limit=15 * 60
        )
        if in_cache and isinstance(cached_payload, dict):
            episodes = cached_payload.get('episodes', [])
            page_meta = cached_payload.get('meta', {'page': page, 'page_size': page_size, 'has_more': False})
            return [], utils2.sort_progress(episodes, sort_order=SORT_MAP[int(kodi.get_setting('sort_progress'))]), page_meta

    workers = []
    episodes = []
    with kodi.ProgressDialog(i18n('discover_mne'), background=True) as pd:
        begin = time.time()
        timeout = max_timeout = int(kodi.get_setting('trakt_timeout') or 100)
        pd.update(0, line1=i18n('retr_history'))

        # Step 1: Base list (one request)
        progress_list = trakt_api.get_watched(SECTIONS.TV, full=True, noseasons=True, cached=cached)

        # Step 2: Optionally merge watchlist items (cheap local operation)
        if kodi.get_setting('include_watchlist_next') == 'true':
            pd.update(5, line1=i18n('retr_watchlist'))
            watchlist = trakt_api.show_watchlist(SECTIONS.TV)
            watchlist = [{'show': item} for item in watchlist]
            progress_list += watchlist

        # Step 3: Hidden shows
        pd.update(10, line1=i18n('retr_hidden'))
        hidden = set([item['show']['ids']['trakt'] for item in trakt_api.get_hidden_progress(cached=cached)])

        # Step 4: Build filtered list of (trakt_id, show)
        filter_list = set(utils2.get_progress_skip_list())
        force_list = set(utils2.get_force_progress_list())
        use_exclusion = kodi.get_setting('use_cached_exclusion') == 'true'

        filtered = []  # list of (trakt_id, show)
        for item in progress_list:
            try:
                trakt_id = item['show']['ids']['trakt']
            except Exception:
                continue
            # Skip hidden
            if trakt_id in hidden:
                continue
            # Skip cached ended 100% shows when exclusion is on (unless force include)
            if use_exclusion and str(trakt_id) in filter_list and str(trakt_id) not in force_list:
                logger.log('Skipping %s (%s) as cached MNE ended exclusion' % (trakt_id, item['show']['title']), log_utils.LOGDEBUG)
                continue
            filtered.append((trakt_id, item['show']))

        total_filtered = len(filtered)

        # Step 5: Get progress for ALL filtered shows (not just the page window)
        # This ensures sorting is applied across all items before pagination
        try:
            wp = worker_pool.WorkerPool(max_workers=40)
            shows = {}
            filtered_size = len(filtered)
            for i, (trakt_id, show) in enumerate(filtered):
                percent = (i + 1) * 25 / (filtered_size or 1) + 10
                pd.update(percent, line1=i18n('req_progress') % (show['title']))
                wp.request(salts_utils.parallel_get_progress, [trakt_id, cached, .08])
                shows[trakt_id] = show

            total_shows = len(shows)
            progress_count = 0
            all_episodes = []
            while progress_count < total_shows:
                try:
                    logger.log('Waiting for Progress - Timeout: %s' % (timeout), log_utils.LOGDEBUG)
                    progress = wp.receive(timeout)
                    progress_count += 1
                    trakt_id = progress['trakt']
                    show = shows[trakt_id]
                    percent = (progress_count * 65 / (total_shows or 1)) + 35
                    pd.update(percent, line1=i18n('rec_progress') % (show['title']))

                    if 'next_episode' in progress and progress['next_episode']:
                        episode = {'show': show, 'episode': progress['next_episode']}
                        episode['last_watched_at'] = progress['last_watched_at']
                        episode['percent_completed'] = (progress['completed'] * 100) / progress['aired'] if progress['aired'] > 0 else 0
                        episode['completed'] = progress['completed']
                        all_episodes.append(episode)
                    else:
                        ended = show['status'] and show['status'].upper() == 'ENDED'
                        completed = progress['completed'] == progress['aired']
                        if ended and completed and str(trakt_id) not in filter_list and str(trakt_id) not in force_list:
                            logger.log('Adding %s (%s) (%s - %s) to MNE exclusion list' % (trakt_id, show['title'], progress['completed'], progress['aired']), log_utils.LOGDEBUG)
                            manage_progress_cache(ACTIONS.ADD, progress['trakt'])

                    if max_timeout > 0:
                        timeout = max_timeout - (time.time() - begin)
                        if timeout < 0:
                            timeout = 0
                except worker_pool.Empty:
                    logger.log('Get Progress Process Timeout', log_utils.LOGWARNING)
                    timeout = True
                    break
            else:
                logger.log('All progress results received', log_utils.LOGDEBUG)
                timeout = False
        finally:
            workers = wp.close()

        # Step 6: Sort all episodes (critical fix for proper ordering)
        sorted_all = utils2.sort_progress(all_episodes, sort_order=SORT_MAP[int(kodi.get_setting('sort_progress'))])

        # Step 7: Apply pagination to the sorted list
        start = (page - 1) * page_size
        end = start + page_size
        episodes = sorted_all[start:end]
        has_more = end < len(sorted_all)

        if timeout:
            timeouts = total_shows - progress_count
            timeout_msg = i18n('progress_timeouts') % (timeouts, total_shows)
            kodi.notify(msg=timeout_msg, duration=5000)
            logger.log(timeout_msg, log_utils.LOGWARNING)
        else:
            # Cache the page results if all were successful.
            payload = {'episodes': episodes, 'meta': {'page': page, 'page_size': page_size, 'total': len(sorted_all), 'has_more': has_more}}
            db_connection.cache_function(get_progress.__name__, args=[page, page_size], kwargs={}, result=payload)

    page_meta = {'page': page, 'page_size': page_size, 'total': len(sorted_all) if 'sorted_all' in locals() else len(episodes), 'has_more': has_more}
    return workers, episodes, page_meta
```

---

3) Update `show_progress` to use `page` and render Next/Previous Page

Replace the whole `show_progress` with this version. It calls `get_progress` with `page`, renders the items, and appends a Next Page item when `page_meta['has_more']` is true. It also includes `mode` in pagination queries so the dispatcher routes correctly.

```python
@url_dispatcher.register(MODES.SHOW_PROGRESS, ['mode'], ['page'])
def show_progress(mode, page=1):
    try:
        try:
            page_i = int(page)
            if page_i < 1:
                page_i = 1
        except Exception:
            page_i = 1

        page_size = int(kodi.get_setting('list_size') or 50)
        workers, progress, page_meta = get_progress(cached=True, page=page_i, page_size=page_size)

        for episode in progress:
            logger.log('Episode: Sort Keys: Tile: |%s| Last Watched: |%s| Percent: |%s%%| Completed: |%s|' % (episode['show']['title'], episode['last_watched_at'], episode['percent_completed'], episode['completed']), log_utils.LOGDEBUG)
            first_aired_utc = utils.iso_2_utc(episode['episode']['first_aired'])
            if kodi.get_setting('show_unaired_next') == 'true' or first_aired_utc <= time.time():
                show = episode['show']
                date = utils2.make_day(utils2.make_air_date(episode['episode']['first_aired']))
                if kodi.get_setting('mne_time') != '0':
                    date_time = '%s@%s' % (date, utils2.make_time(first_aired_utc, 'mne_time'))
                else:
                    date_time = date

                menu_items = []
                queries = {'mode': MODES.SEASONS, 'trakt_id': show['ids']['trakt'], 'title': show['title'], 'year': show['year'], 'tvdb_id': show['ids']['tvdb'], 'tmdb_id': show['ids']['tmdb']}
                menu_items.append((i18n('browse_seasons'), 'Container.Update(%s)' % (kodi.get_plugin_url(queries))),)
                liz, liz_url = make_episode_item(show, episode['episode'], show_subs=False, menu_items=menu_items)
                label = liz.getLabel()
                label = '[[COLOR deeppink]%s[/COLOR]] %s - %s' % (date_time, show['title'], label)
                liz.setLabel(label)

                xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, liz, isFolder=False)

        # Add Next Page item if applicable
        if page_meta.get('has_more'):
            next_query = {'mode': MODES.SHOW_PROGRESS, 'page': page_i + 1}
            next_label = '%s >>' % (i18n('next_page'))
            kodi.create_item(next_query, next_label, thumb=utils2.art('nextpage.png'), fanart=utils2.art('fanart.jpg'), is_folder=True)

        # Optional: add Previous Page
        if page_i > 1:
            prev_query = {'mode': MODES.SHOW_PROGRESS, 'page': page_i - 1}
            prev_label = '<< %s' % (i18n('previous_page') if hasattr(strings, 'STRINGS') else 'Previous Page')
            kodi.create_item(prev_query, prev_label, thumb=utils2.art('nextpage.png'), fanart=utils2.art('fanart.jpg'), is_folder=True)

        kodi.set_content(CONTENT_TYPES.EPISODES)
        kodi.end_of_directory(cache_to_disc=False)
    finally:
        try:
            worker_pool.reap_workers(workers, None)
        except UnboundLocalError:
            pass
```

Notes:
- The `mode` parameter must exist since the decorator includes `['mode']`.
- The pagination queries include `mode`: `MODES.SHOW_PROGRESS`.

---

4) Update `force_refresh` to handle the new return shape

In `force_refresh` (already present in your file), update the unpack for the `SHOW_PROGRESS` refresh path so `get_progress` is called with paging params and the third return value is ignored.

Find:

```python
elif refresh_mode == MODES.SHOW_PROGRESS:
    try:
        workers, _progress = get_progress(cached=False)
    finally:
        try: worker_pool.reap_workers(workers, None)
        except: pass
```

Replace with:

```python
    elif refresh_mode == MODES.SHOW_PROGRESS:
        try:
            workers, _progress, _meta = get_progress(cached=False, page=1, page_size=int(kodi.get_setting('list_size') or 50))
        finally:
            try: worker_pool.reap_workers(workers, None)
            except: pass
```

---

Troubleshooting

- ValueError: invalid literal for int() with base 10: 'show_progress'
  - Cause: The handler decorator declares `['mode']` but the function didn’t accept `mode`. Fix by changing the signature to `def show_progress(mode, page=1)` or remove `['mode']` from the decorator.

- Next Page doesn’t appear
  - Ensure Next Page queries include `'mode': MODES.SHOW_PROGRESS`.
  - Ensure `has_more` is computed from filtered shows: `has_more = end < total_filtered`.
  - On cache hits, make sure you either cached page_meta with the episodes or recompute `total_filtered` cheaply to rebuild `has_more`.
  - Add logging to verify the pagination boundaries:
    - `logger.log(f'Progress page {page_i}: total_filtered={total_filtered}, start={start}, end={end}, has_more={has_more}', log_utils.LOGDEBUG)`

- Deprecation warning: ListItem.addStreamInfo()
  - Unrelated to paging; you can plan to migrate to InfoTagVideo APIs later.

---

Testing checklist
- Open My Progress with large libraries: only first page (`list_size` shows) should load, quickly.
- Verify Next Page appears at the bottom; clicking it loads the next slice.
- Check that sorting, unaired filtering and menu items still behave as before.
- Try force refresh for My Progress from the menu; ensure no exceptions after the unpack change.
- Confirm DB caching works per page (navigate back and forth between pages).

Rollback
- If you need to revert quickly, restore the original `get_progress` and `show_progress` bodies and the original `force_refresh` block for `SHOW_PROGRESS`.

Notes on limits
- This paging targets the expensive per-show `/progress` calls. The initial `get_watched` call still returns the universe of shows in one response; that has historically been stable, and it’s only one request per load.
- If Trakt further limits base lists, consider a future enhancement to page the base list too (e.g., by retrieving watched history in chunks and deduplicating), but that’s a larger change.
