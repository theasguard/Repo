
Based on my analysis of the code, here's a comprehensive breakdown of how to implement TMDB lists in default.py, using Trakt lists as a reference:

## Analysis of Current Implementation

### Trakt Lists Implementation
1. **API Layer (trakt_api.py)**:
   - `get_lists()` - Retrieves user's lists
   - `show_list(slug, section, username, auth, cached)` - Gets items in a specific list
   - `get_list_header(slug, username, auth)` - Gets list metadata

2. **UI Layer (default.py)**:
   - `browse_lists(section)` - Displays all user lists
   - `show_list(section, slug, username)` - Shows items in a specific list
   - `add_list_item(section, user_list, total_items)` - Creates list item with context menu
   - Integration in `browse_menu(section)` - Lists are shown under "My Lists" menu item

### TMDB Lists Implementation
The `tmdb_api.py` already has list management functions:
- `get_user_lists(page=1)` - Get user's custom lists
- `get_list_details(list_id)` - Get details of a specific list
- `create_list(list_name, description, public)` - Create new list
- `add_items_to_list(list_id, items)` - Add items to list
- `remove_items_from_list(list_id, items)` - Remove items from list
- `update_list(list_id, name, description, public)` - Update list
- `clear_list(list_id)` - Clear all items from list
- `delete_list(list_id)` - Delete a list

## Implementation Plan for TMDB Lists

### 1. Add New Modes to constants.py
```python
MODES = __enum(
    # ... existing modes ...
    TMDB_LISTS='tmdb_lists',
    TMDB_SHOW_LIST='tmdb_show_list',
    TMDB_CREATE_LIST='tmdb_create_list',
    TMDB_MANAGE_LIST='tmdb_manage_list',
    TMDB_WATCHLIST='tmdb_watchlist',
    TMDB_FAVORITES='tmdb_favorites'
)
```

### 2. Add TMDB List Functions to default.py

#### Display TMDB Lists
```python
@url_dispatcher.register(MODES.TMDB_LISTS, ['section'])
def browse_tmdb_lists(section):
    """Display all TMDB user lists"""
    account_id = kodi.get_setting('tmdb_account_id')
    if not account_id:
        kodi.notify(msg=i18n('tmdb_not_authenticated'), duration=5000)
        return
    
    # Add special lists
    kodi.create_item(
        {'mode': MODES.TMDB_WATCHLIST, 'section': section},
        i18n('tmdb_watchlist'),
        thumb=utils2.art('my_watchlist.png'),
        fanart=utils2.art('fanart.jpg')
    )
    
    kodi.create_item(
        {'mode': MODES.TMDB_FAVORITES, 'section': section},
        i18n('tmdb_favorites'),
        thumb=utils2.art('my_favorites.png'),
        fanart=utils2.art('fanart.jpg')
    )
    
    kodi.create_item(
        {'mode': MODES.TMDB_CREATE_LIST},
        i18n('tmdb_create_list'),
        thumb=utils2.art('add_other.png'),
        fanart=utils2.art('fanart.jpg'),
        is_folder=False,
        is_playable=False
    )
    
    # Get user's custom lists
    lists = tmdb_api.get_user_lists()
    if lists and 'results' in lists:
        for tmdb_list in lists['results']:
            add_tmdb_list_item(section, tmdb_list)
    
    kodi.set_content(CONTENT_TYPES.ADDONS)
    kodi.end_of_directory()
```

#### Display TMDB List Items
```python
@url_dispatcher.register(MODES.TMDB_SHOW_LIST, ['section', 'list_id'])
def show_tmdb_list(section, list_id):
    """Display items in a TMDB list"""
    list_details = tmdb_api.get_list_details(list_id)
    if not list_details:
        kodi.notify(msg=i18n('tmdb_list_not_found'), duration=5000)
        return
    
    items = list_details.get('items', [])
    total_items = len(items)
    
    for item in items:
        if item.get('media_type') == 'movie':
            liz, liz_url = makeitem.make_tmdb_movie_item(item)
            xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, liz, isFolder=False, totalItems=total_items)
        elif item.get('media_type') == 'tv':
            liz, liz_url = makeitem.make_tv_show_item(item)
            xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, liz, isFolder=True, totalItems=total_items)
    
    content_type = CONTENT_TYPES.EPISODES if section == SECTIONS.TV else CONTENT_TYPES.MOVIES
    kodi.set_view(content_type, True)
    kodi.end_of_directory()
```

#### Display TMDB Watchlist/Favorites
```python
@url_dispatcher.register(MODES.TMDB_WATCHLIST, ['section'])
def show_tmdb_watchlist(section):
    """Display TMDB watchlist"""
    mediatype = 'tv' if section == SECTIONS.TV else 'movie'
    watchlist = tmdb_api.get_user_watchlist(mediatype)
    
    if not watchlist:
        kodi.notify(msg=i18n('tmdb_watchlist_empty'), duration=5000)
        return
    
    items = watchlist.get('results', [])
    total_items = len(items)
    
    for item in items:
        if section == SECTIONS.MOVIES:
            liz, liz_url = makeitem.make_tmdb_movie_item(item)
            xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, liz, isFolder=False, totalItems=total_items)
        else:
            liz, liz_url = makeitem.make_tv_show_item(item)
            xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, liz, isFolder=True, totalItems=total_items)
    
    content_type = CONTENT_TYPES.EPISODES if section == SECTIONS.TV else CONTENT_TYPES.MOVIES
    kodi.set_view(content_type, True)
    kodi.end_of_directory()

@url_dispatcher.register(MODES.TMDB_FAVORITES, ['section'])
def show_tmdb_favorites(section):
    """Display TMDB favorites"""
    mediatype = 'tv' if section == SECTIONS.TV else 'movie'
    favorites = tmdb_api.get_user_favorites(mediatype)
    
    if not favorites:
        kodi.notify(msg=i18n('tmdb_favorites_empty'), duration=5000)
        return
    
    items = favorites.get('results', [])
    total_items = len(items)
    
    for item in items:
        if section == SECTIONS.MOVIES:
            liz, liz_url = makeitem.make_tmdb_movie_item(item)
            xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, liz, isFolder=False, totalItems=total_items)
        else:
            liz, liz_url = makeitem.make_tv_show_item(item)
            xbmcplugin.addDirectoryItem(int(sys.argv[1]), liz_url, liz, isFolder=True, totalItems=total_items)
    
    content_type = CONTENT_TYPES.EPISODES if section == SECTIONS.TV else CONTENT_TYPES.MOVIES
    kodi.set_view(content_type, True)
    kodi.end_of_directory()
```

#### Create TMDB List
```python
@url_dispatcher.register(MODES.TMDB_CREATE_LIST)
def create_tmdb_list():
    """Create a new TMDB list"""
    dialog = xbmcgui.Dialog()
    
    name = dialog.input(i18n('tmdb_list_name'), type=xbmcgui.INPUT_ALPHANUM)
    if not name:
        return
    
    description = dialog.input(i18n('tmdb_list_description'), type=xbmcgui.INPUT_ALPHANUM)
    
    public = dialog.yesno(i18n('tmdb_make_public'), i18n('tmdb_public_question'))
    
    list_id = tmdb_api.create_list(name, description, public)
    if list_id:
        kodi.notify(msg=i18n('tmdb_list_created'), duration=5000)
    else:
        kodi.notify(msg=i18n('tmdb_list_create_failed'), duration=5000)
```

#### Helper Function for TMDB List Items
```python
def add_tmdb_list_item(section, tmdb_list):
    """Create a list item for TMDB list with context menu"""
    list_id = tmdb_list.get('id')
    list_name = tmdb_list.get('name', 'Unknown')
    description = tmdb_list.get('description', '')
    item_count = tmdb_list.get('item_count', 0)
    
    menu_items = []
    
    # Add context menu items
    queries = {'mode': MODES.TMDB_SHOW_LIST, 'section': section, 'list_id': list_id}
    menu_items.append((i18n('view_list'), 'ActivateWindow(Videos, %s)' % (kodi.get_plugin_url(queries))))
    
    # Add refresh option
    queries = {'mode': MODES.TMDB_SHOW_LIST, 'section': section, 'list_id': list_id}
    menu_items.append((i18n('force_refresh'), 'RunPlugin(%s)' % (kodi.get_plugin_url(queries))))
    
    label = f'{list_name} ({item_count})'
    if description:
        label += f' - {description}'
    
    kodi.create_item(
        {'mode': MODES.TMDB_SHOW_LIST, 'section': section, 'list_id': list_id},
        label,
        thumb=utils2.art('list.png'),
        fanart=utils2.art('fanart.jpg'),
        is_folder=True,
        total_items=0,
        menu_items=menu_items,
        replace_menu=False
    )
```

### 3. Integrate TMDB Lists into Browse Menu

Modify the `browse_menu(section)` function to add TMDB lists:

```python
@url_dispatcher.register(MODES.BROWSE, ['section'])
def browse_menu(section):
    # ... existing code ...
    
    # Add TMDB Lists option
    account_id = kodi.get_setting('tmdb_account_id')
    if account_id and utils2.menu_on('tmdb_lists'):
        kodi.create_item(
            {'mode': MODES.TMDB_LISTS, 'section': section},
            i18n('tmdb_lists'),
            thumb=utils2.art('tmdb_lists.png'),
            fanart=utils2.art('fanart.jpg')
        )
    
    # ... rest of existing code ...
```

### 4. Add TMDB Authentication Check

Before accessing TMDB lists, you need to ensure the user is authenticated with TMDB. You can add a function similar to Trakt's authentication:

```python
def check_tmdb_auth():
    """Check if TMDB is authenticated"""
    account_id = kodi.get_setting('tmdb_account_id')
    bearer_token = kodi.get_setting('tmdb_bearer_token')
    
    if not account_id or not bearer_token:
        kodi.notify(msg=i18n('tmdb_not_authenticated'), duration=5000)
        return False
    
    return True
```

### 5. Add Settings for TMDB Lists

In settings.xml, you may want to add:
- Toggle to show/hide TMDB lists in browse menu
- TMDB account ID setting (if not already present)

## Key Differences from Trakt Implementation

1. **Authentication**: TMDB uses bearer tokens and account IDs instead of OAuth tokens
2. **List Structure**: TMDB lists use numeric IDs instead of slugs
3. **API Version**: TMDB lists use API v4, while most other functions use v3
4. **Response Format**: TMDB API responses have different structure than Trakt

## Important Notes

1. **TMDB Account ID Required**: Users need to authenticate with TMDB and get their account ID. This requires implementing a TMDB authentication flow similar to Trakt's.

2. **Bearer Token**: The TMDB API v4 requires a bearer token for list operations. This must be configured in settings.

3. **Error Handling**: Need to handle cases where TMDB authentication fails or lists are not accessible.

4. **Caching**: Consider implementing caching for TMDB lists similar to Trakt's caching mechanism.

5. **Menu Integration**: You may want to add TMDB lists as an alternative to Trakt lists in the browse menu, allowing users to choose which service to use.

This implementation provides a comprehensive TMDB lists feature that mirrors the functionality of Trakt lists while accounting for the differences in API structure and authentication methods.