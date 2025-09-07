# Repo

# Still in Development
SALTS Fork Asguard - Kodi Addon Documentation
Overview
SALTS Fork Asguard is a powerful Kodi addon designed to provide users with a seamless streaming experience, integrating advanced features for movies, TV shows, and more. This fork builds upon the original SALTS foundation, introducing significant enhancements in metadata handling, database management, image scraping, torrent provider support, and API integrations.

Key Features & Enhancements
1. TMDB Group Episodes
New Data Handling: The addon now supports TMDB group episodes, allowing for improved episode grouping and metadata accuracy for TV series.
Benefits: Enhanced episode navigation and display, especially for series with complex episode structures.
2. TMDB Search Sections
Expanded Search: New TMDB search sections have been added, enabling users to search for movies, TV shows, and people directly from TMDB.
Internal TMDB IDs: TMDB IDs are now incorporated internally throughout the addon, improving metadata consistency and enabling advanced search and filtering capabilities.
3. Database Management
Improved Storage: The database management system has been overhauled for better performance and reliability.
Best Practices: SQLite databases are now stored in the addon's profile directory, reducing file locking issues and improving compatibility with Kodi's environment.
4. Image Scrapers
New Scrapers: Additional image scrapers have been integrated, providing higher-quality artwork and more sources for posters, fanart, and thumbnails.
Supported Sources: Includes TMDB, fanart.tv, and other popular image providers.
5. Trakt Integration
Rewritten Trakt API: The Trakt integration has been completely rewritten for better reliability, error handling, and performance.
New Functionality: A new Trakt function is coming soon, allowing users to search by ID (TMDB, IMDB, Trakt) for movies and TV shows.
Improved Exception Handling: Network errors and retries are now handled gracefully, preventing Kodi from hanging or requiring a force close.
6. Torrent Providers
Expanded Support: More torrent providers have been added, increasing the number of available sources for streaming content.
Provider Management: Users can enable or disable providers as needed for optimal performance and content availability.
7. API Access for Debrid Services
New Functions: The addon now includes API access for popular debrid services (e.g., Real-Debrid, Premiumize, AllDebrid), allowing users to stream high-quality content with fewer buffering issues.
Integration: Debrid services are seamlessly integrated into the search and playback workflow.
8. Additional New Functions
Search by ID: Users can now search for content using TMDB, IMDB, or Trakt IDs, making it easier to find specific movies or episodes.
Enhanced Metadata: Improved metadata retrieval and display throughout the addon.
Getting Started
Installation: Download the addon from the official repository or GitHub and install it via Kodi's Add-ons menu.
Configuration: Set up your Trakt and debrid service accounts in the addon settings for full functionality.
Usage: Browse, search, and stream content using the enhanced features described above.
Contributing
Contributions are welcome! Please submit issues, feature requests, or pull requests via GitHub.

# todo 
- the resolve URL I'm being sort of lazy on resolving the all debrid auto resolve if anyone is interested in helping me I'm open to help with that. (Complete for now)

- test cfscrape if error occurs remove from module and use in plugin.
- remember to add the torrentdownload and 1337x scrapers after label and title sorting has been fixed for them.
- look into the sort_keys in utils 2 to see if we can make it more robust and handle more list structures.
- (Important) sort out the select source for the resolveurl (I think it's mostly just for all debrid I'm having the auto resolve issues with the resolveurl for full season packs)
- fix 1337x to return season packs along with single episodes. 
- connect the tmdb sections listing episodes and movies to the get sources or create an alternate get sources for it then we can pass it to the resolveurl as we already do.
- check the trakt context for making new menu items (complete) 
- make sure all the trakt functions for adding to lists making new lists copying etc function properly.(complete) 
- create more scrapers for the addon.
- add some extra filtering for titles like "You", and "See" some single title names return wrong sources in torrentdownload and the other, look into that further
- incorporate an extended video function in the default.py and init of the scrapers directory for using anime ID's
- if I think of a anything else I'll update this. 

# Asguard Kodi Addon
Asguard is a Kodi addon that provides access to a wide range of streaming content. It is designed to be a successor to the popular SALTS (Stream All The Sources) addon, offering improved performance and additional features.

## Features

- Stream movies and TV shows from various sources.
- Integration with Trakt for tracking watched content.
- Customizable settings for a personalized experience.
- Support for subtitles and multiple languages.
- Cached content for faster access.

## Installation

### From Zip File

1. Download the zip file from the [[releases page](https://github.com/theasguard/Repo/releases/expanded_assets/release)]
2. Open Kodi and go to _Settings_ > _Add-ons_ > _Install from zip file_.
3. Navigate to the downloaded zip file and select it.
4. Wait for the installation to complete.
5. Go to _Settings_ > _Add-ons_ > _My add-ons_ > _Video add-ons_ > **Asguard**.
6. Open **Asguard** and configure it as needed.

### From Source

1. Clone this repository into your Kodi **addons** folder:
2. git clone https://github.com/theasguard/repo.git plugin.video.asguard

2. Restart Kodi if it is already running.
3. Go to _Settings_ > _Add-ons_ > _My add-ons_ > _Video add-ons_ > **Asguard**.
4. Open **Asguard** and configure it as needed.

## Usage

1. Open the Asguard addon from the Kodi home screen.
2. Browse through the available categories such as Movies, TV Shows, etc.
3. Select a title to view more details and start streaming.

## Contributing

We welcome contributions from the community! If you would like to contribute to Asguard, please follow these steps:

1. Fork the repository on GitHub.
2. Create a new branch for your feature or bugfix:
3. Make your changes and commit them with a descriptive message:
4.  Push your changes to your forked repository:
5. Open a pull request on the main repository and describe your changes.

### Reporting Issues

If you encounter any issues or have suggestions for improvements, please open an issue on the [GitHub Issues](https://github.com/theasguard/repo/issues) page.

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for more details.

## Acknowledgements

- Special thanks to all contributors and the Kodi community for their support.
- This addon is inspired by the original SALTS addon.

---

For more information, visit the [official documentation](https://github.com/theasguard/Repo/wiki).
