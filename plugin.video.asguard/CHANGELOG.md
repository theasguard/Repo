# Asguard Kodi Addon - Recent Updates

## Cache Management Improvements

We've implemented several enhancements to the cache management system in the Asguard addon to improve performance and user experience.

### New Features

- **Reconnected Prune Cache Function**: The prune cache functionality has been reconnected to the settings and is now accessible via the Database tab in the addon settings.

- **Automatic Cache Pruning**: When enabled, the addon will automatically prune the cache every 8 hours. This helps maintain optimal performance by clearing outdated data.

  - *Default setting*: OFF
  - *Location*: Settings → Database → Auto Prune Cache

- **Startup Cache Pruning Toggle**: Added a new option to control whether cache pruning occurs during addon startup.

  - *Default setting*: OFF
  - *Location*: Settings → Database → Prune Cache on Startup

- **Playback Cache Pruning Toggle**: Added a new option to control whether cache pruning occurs during playback.

  - *Default setting*: OFF
  - *Location*: Settings → Database → Prune Cache on Playback

## Development Updates

Several new scripts have been created and integrated into the addon codebase for potential future functionality:

- **AniList Integration**: Scripts for integrating with AniList service for enhanced anime metadata and tracking.

- **Simkl Integration**: Components for connecting with Simkl service to provide tracking and recommendation features.

- **Watchdog Manager**: A monitoring system to track addon performance and handle potential issues automatically.

- **Source Progress**: New display system for the "Get Sources" functionality, providing better visual feedback during source fetching.

- **Additional Utility Scripts**: Various modified and custom scripts to enhance addon functionality and reliability.

## User Benefits

These changes provide several benefits to users:

1. **Improved Performance**: Regular cache pruning helps maintain the addon's speed and responsiveness.

2. **Better Control**: Users now have more control over when and how cache pruning occurs.

3. **Enhanced Stability**: The new monitoring scripts help identify and address potential issues before they impact the user experience.

4. **Future-Ready**: The new integration scripts lay the groundwork for future service connections and enhanced features.

## How to Access New Settings

To configure the new cache management options:

1. Navigate to the Asguard addon in your Kodi addons menu.
2. Open the addon settings.
3. Go to the "Database" tab.
4. Configure the following options as desired:
   - Auto Prune Cache
   - Prune Cache on Startup
   - Prune Cache on Playback

## Feedback

We appreciate your feedback on these new features. If you encounter any issues or have suggestions for further improvements, please report them through our official support channels.
