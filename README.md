# Repo

# Still in Development

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
