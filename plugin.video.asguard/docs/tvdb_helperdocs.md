# TVDB Helper Module Documentation

## Overview

The TVDB Helper module provides functionality to manage TVDB IDs by using a local JSON cache that stores mappings between different ID systems (TMDB, Trakt, TVDB) and show titles. This reduces API calls to TMDB for TVDB ID lookups and allows for persistent storage of found IDs.

## JSON Structure

The helper will use a JSON file with the following structure:

```json
{
  "version": "1.0",
  "last_updated": "2023-11-15T12:34:56Z",
  "entries": {
    "tmdb_12345": {
      "title": "Example Show",
      "tmdb_id": 12345,
      "trakt_id": 67890,
      "tvdb_id": 11111
    },
    "trakt_67890": {
      "title": "Example Show",
      "tmdb_id": 12345,
      "trakt_id": 67890,
      "tvdb_id": 11111
    },
    "tvdb_11111": {
      "title": "Example Show",
      "tmdb_id": 12345,
      "trakt_id": 67890,
      "tvdb_id": 11111
    }
  }
}
```

Key aspects of the structure:
- Each entry is indexed by a prefix followed by the ID value (`tmdb_`, `trakt_`, `tvdb_`)
- This allows for quick lookups regardless of which ID type you start with
- Each entry contains all known IDs for the show
- Metadata includes version and last update timestamp

## Module Functionality

### 1. Initialization
- Download and store the JSON file from GitHub in the addon's profile directory
- Create the file if it doesn't exist locally
- Load the JSON into memory for efficient access

### 2. ID Lookup
- Search for a TVDB ID using any of the following:
  - TMDB ID
  - Trakt ID
  - Show title (exact or fuzzy match)
- Return the TVDB ID if found in the JSON cache

### 3. Fallback Mechanism
- If the ID is not found in the JSON:
  - Use TMDB API to look up the TVDB ID
  - Store the new mapping in the JSON for future use
  - Periodically save the updated JSON to disk

### 4. JSON Management
- Add new entries to the JSON as IDs are discovered
- Update existing entries when new information is found
- Maintain clean structure without duplicates
- Handle concurrent access and file locking

## Implementation Plan

### Main Classes and Functions

#### `TVDBHelper` Class
- Main class that handles all TVDB-related operations
- Manages the JSON cache file
- Provides lookup methods for different ID types

#### Key Methods:
- `__init__(profile_dir, json_url=None)`: Initialize with addon profile directory and optional JSON URL
- `load_json()`: Load JSON from disk or download if needed
- `save_json()`: Save current JSON to disk
- `get_tvdb_by_tmdb(tmdb_id, tmdb_api=None)`: Get TVDB ID using TMDB ID
- `get_tvdb_by_trakt(trakt_id, tmdb_api=None)`: Get TVDB ID using Trakt ID
- `get_tvdb_by_title(title, year=None, tmdb_api=None)`: Get TVDB ID using show title
- `add_mapping(title, tmdb_id=None, trakt_id=None, tvdb_id=None)`: Add new mapping to JSON
- `update_json_from_github()`: Download and merge updates from GitHub

### Usage Example

```python
from asguard_lib import tvdb_helper

# Initialize the helper
helper = tvdb_helper.TVDBHelper(json_url="https://raw.githubusercontent.com/theasguard/Asgard-Updates/main/asg_tvdb.json")

# Get TVDB ID from TMDB ID
tvdb_id = helper.get_tvdb_by_tmdb(12345, tmdb_api=tmdb_api)

# If not found in cache, will use TMDB API and store the result
if tvdb_id:
    # Use the TVDB ID
    pass
```

## Integration with Existing Code

The new helper will complement the existing `tvdb_persist.py` module by:

1. Providing a shared cache accessible to all addon components
2. Reducing TMDB API calls by storing mappings in a shared file
3. Allowing manual addition of mappings by developers
4. Supporting bulk updates from GitHub

## Error Handling

- Handle network errors when downloading from GitHub
- Gracefully fall back to local file if download fails
- Validate JSON structure on load
- Handle file I/O errors when saving
- Ensure thread-safe access to the JSON file

## Settings

Consider adding these addon settings:
- `tvdb_helper_enabled`: Enable/disable the helper
- `tvdb_helper_auto_update`: Automatically download updates from GitHub
- `tvdb_helper_update_interval`: Days between update checks
- `tvdb_helper_fallback_to_tmdb`: Allow TMDB API fallback when enabled

## Future Enhancements

- Add fuzzy matching for titles
- Support for movie IDs
- Export/import functionality for user-created mappings
- Statistics on cache hit rates
- Automatic cleanup of old entries
