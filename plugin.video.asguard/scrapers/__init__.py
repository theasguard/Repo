# -*- coding: UTF-8 -*-
#######################################################################
 # ----------------------------------------------------------------------------
 # "THE BEER-WARE LICENSE" (Revision 42):
 # @Daddy_Blamo wrote this file.  As long as you retain this notice you
 # can do whatever you want with this stuff. If we meet some day, and you think
 # this stuff is worth it, you can buy me a beer in return. - MrBlamo
 # ----------------------------------------------------------------------------
#######################################################################

# Addon Name: Asguard
# Addon id: plugin.video.asguard
# Addon Provider: MrBlamo


import os
import re
import time
import six
from scrapers import scraper
from scrapers import proxy
import kodi
import log_utils  # @UnusedImport
from asguard_lib import utils2
from asguard_lib.constants import FORCE_NO_MATCH
from asguard_lib.constants import VIDEO_TYPES
from asguard_lib import control

files = os.listdir(os.path.dirname(__file__))
__all__ = [filename[:-3] for filename in files if not filename.startswith('__') and filename.endswith('.py')]

from . import *

logger = log_utils.Logger.get_logger()
  
class ScraperVideo:
    def __init__(self, video_type, title, year, trakt_id, season='', episode='', ep_title='', ep_airdate=''):
        """
        Constructs all the necessary attributes for the ScraperVideo object.

        Args:
            video_type (str): The type of video (e.g., movie, TV show, episode).
            title (str): The title of the video.
            year (str): The release year of the video.
            trakt_id (str): The Trakt ID of the video.
            season (str, optional): The season number (for TV shows). Defaults to ''.
            episode (str, optional): The episode number (for TV shows). Defaults to ''.
            ep_title (str, optional): The title of the episode (for TV shows). Defaults to ''.
            ep_airdate (str, optional): The air date of the episode in the format 'YYYY-MM-DD' (for TV shows). Defaults to None.
        """
        assert(video_type in (VIDEO_TYPES.__dict__[k] for k in VIDEO_TYPES.__dict__ if not k.startswith('__')))
        self.video_type = video_type
        if six.PY2 and isinstance(title, six.text_type): self.title = title.encode('utf-8')
        else: self.title = title
        self.year = str(year)
        self.season = season
        self.episode = episode
        if six.PY2 and isinstance(ep_title, six.text_type): self.ep_title = ep_title.encode('utf-8')
        else: self.ep_title = ep_title
        self.trakt_id = trakt_id
        self.ep_airdate = utils2.to_datetime(ep_airdate, "%Y-%m-%d").date() if ep_airdate else None

    def __str__(self):
        return '|%s|%s|%s|%s|%s|%s|%s|' % (self.video_type, self.title, self.year, self.season, self.episode, self.ep_title, self.ep_airdate)

class ScraperVideoExtended(ScraperVideo):
    def __init__(self, video_type, title, year, trakt_id, season='', episode='', ep_title='', ep_airdate='', aliases=None, anidb_id=None, mal_id=None, anilist_id=None):
        """
        Constructs all the necessary attributes for the ScraperVideoExtended object.

        Args:
            video_type (str): The type of video (e.g., movie, TV show, episode).
            title (str): The title of the video.
            year (str): The release year of the video.
            trakt_id (str): The Trakt ID of the video.
            season (str, optional): The season number (for TV shows). Defaults to ''.
            episode (str, optional): The episode number (for TV shows). Defaults to ''.
            ep_title (str, optional): The title of the episode (for TV shows). Defaults to ''.
            ep_airdate (str, optional): The air date of the episode in the format 'YYYY-MM-DD' (for TV shows). Defaults to None.
            aliases (list, optional): List of aliases for the video. Defaults to None.
            anidb_id (str, optional): The AniDB ID of the video. Defaults to None.
            mal_id (str, optional): The MyAnimeList ID of the video. Defaults to None.
            anilist_id (str, optional): The AniList ID of the video. Defaults to None.
        """
        super().__init__(video_type, title, year, trakt_id, season, episode, ep_title, ep_airdate)
        self.aliases = aliases if aliases else []
        self.anidb_id = anidb_id
        self.mal_id = mal_id
        self.anilist_id = anilist_id

    def __str__(self):
        return super().__str__() + '|%s|%s|%s|%s|' % (self.aliases, self.anidb_id, self.mal_id, self.anilist_id)

def update_xml(xml, new_settings, cat_count):
    # Map category numbers to their corresponding language string IDs
    CATEGORY_LABELS = {
        1: 30318,  # Scrapers 1
        2: 30319,  # Scrapers 2
        3: 30320,  # Scrapers 3
        4: 30321,  # Scrapers 4
        5: 30322,  # Scrapers 5
        6: 30323,  # Scrapers 6
        7: 40710,  # Scrapers 7
        8: 40711,  # Scrapers 8
        9: 40712,  # Scrapers 9
        10: 40713,  # Scrapers 10
        11: 40714,  # Scrapers 11
        12: 40715,  # Scrapers 12
        # Add more mappings as needed
    }
    
    category_label = CATEGORY_LABELS.get(cat_count, 30000)  # Fallback to default
    
    # Format settings with proper indentation for Kodi 21+ structure
    formatted_settings = []
    for setting in new_settings:
        # Add proper indentation (3 tabs) to each line of the setting
        indented_lines = []
        for line in setting.split('\n'):
            if line.strip():  # Only indent non-empty lines
                indented_lines.append('\t\t\t' + line)
            else:
                indented_lines.append(line)
        formatted_settings.append('\n'.join(indented_lines))
    
    settings_str = '\n'.join(formatted_settings)
    
    # Create properly formatted category with Kodi 21+ structure
    # Use unique group IDs (100+) to avoid conflicts with existing groups
    group_id = 100 + cat_count
    category_tag = '\t\t<category id="scrapers_%s" label="%s" help="">\n\t\t\t<group id="%s">\n%s\n\t\t\t</group>\n\t\t</category>' % (cat_count, category_label, group_id, settings_str)
    
    # Look for existing category with same ID within the section
    pattern = r'(\t\t<category id="scrapers_%s" label="[^"]*"[^>]*>.*?</category>)' % (cat_count)
    match = re.search(pattern, xml, re.DOTALL)
    
    if match:
        # Replace existing category content
        old_category = match.group(1)
        xml = xml.replace(old_category, category_tag)
        logger.log('Updated existing scraper category %s' % (cat_count), log_utils.LOGDEBUG)
    else:
        # Find the end of the section and insert before it
        section_end_pattern = r'(\t</section>)'
        section_match = re.search(section_end_pattern, xml)
        
        if section_match:
            # Insert new category before the section end
            xml = xml.replace(section_match.group(1), '%s\n%s' % (category_tag, section_match.group(1)))
            logger.log('Added new scraper category %s' % (cat_count), log_utils.LOGDEBUG)
        else:
            logger.log('Unable to match category: %s' % (cat_count), log_utils.LOGWARNING)
    
    return xml



def cleanup_old_scrapers(xml):
    """Remove existing scraper categories to regenerate them properly"""
    # Remove existing scraper categories with IDs
    pattern = r'\t\t<category id="scrapers_\d+"[^>]*>.*?</category>\n?'
    xml = re.sub(pattern, '', xml, flags=re.DOTALL)
    
    # Remove any simple text-based scraper categories (from temporary fix)
    pattern = r'\t\t<category label="Scrapers \d+">.*?</category>\n?'
    xml = re.sub(pattern, '', xml, flags=re.DOTALL)
    
    logger.log('Cleaned up existing scraper categories for regeneration', log_utils.LOGDEBUG)
    return xml

def validate_xml_basic(xml):
    """Basic XML validation to ensure structure is intact"""
    try:
        # Check for basic required elements
        if '<settings version="1">' not in xml:
            logger.log('Missing settings version tag', log_utils.LOGWARNING)
            return False
        if '<section id="plugin.video.asguard">' not in xml:
            logger.log('Missing main section tag', log_utils.LOGWARNING)
            return False
        if '</section>' not in xml:
            logger.log('Missing section close tag', log_utils.LOGWARNING)
            return False
        if '</settings>' not in xml:
            logger.log('Missing settings close tag', log_utils.LOGWARNING)
            return False
            
        # Count opening and closing tags
        open_categories = xml.count('<category')
        close_categories = xml.count('</category>')
        if open_categories != close_categories:
            logger.log('Mismatched category tags: %s open, %s close' % (open_categories, close_categories), log_utils.LOGWARNING)
            return False
            
        open_groups = xml.count('<group')
        close_groups = xml.count('</group>')
        if open_groups != close_groups:
            logger.log('Mismatched group tags: %s open, %s close' % (open_groups, close_groups), log_utils.LOGWARNING)
            return False
            
        logger.log('Basic XML validation passed', log_utils.LOGDEBUG)
        return True
        
    except Exception as e:
        logger.log('XML validation error: %s' % (e), log_utils.LOGERROR)
        return False

def update_settings():
    full_path = os.path.join(kodi.get_path(), 'resources', 'settings.xml')
    logger.log('Updating settings: %s' % (full_path), log_utils.LOGDEBUG)
    
    try:
        # open for append; skip update if it fails
        with open(full_path, 'a') as f:
            pass
    except Exception as e:
        logger.log('Dynamic settings update skipped: %s' % (e), log_utils.LOGWARNING)
        return
    
    try:
        with open(full_path, 'r') as f:
            original_xml = f.read()

        # Generate new settings content first
        new_settings_categories = []
        new_settings = []
        cat_count = 1
        classes = scraper.Scraper.__class__.__subclasses__(scraper.Scraper)
        classes += proxy.Proxy.__class__.__subclasses__(proxy.Proxy)
        
        for cls in sorted(classes, key=lambda x: x.get_name().upper()):
            if not cls.get_name() or cls.has_proxy(): 
                continue
            
            # Get settings as strings/list
            settings = cls.get_settings()
            if isinstance(settings, list):
                new_settings.extend(settings)
            else:
                new_settings.append(settings)
                
            if len(new_settings) > 20:  # Smaller categories for better navigation
                new_settings_categories.append((cat_count, new_settings[:]))
                new_settings = []
                cat_count += 1

        if new_settings:
            new_settings_categories.append((cat_count, new_settings))

        # Check if the new settings would be different from existing ones
        temp_xml = cleanup_old_scrapers(original_xml)
        for cat_num, settings_list in new_settings_categories:
            temp_xml = update_xml(temp_xml, settings_list, cat_num)

        # Validate the XML structure before comparing
        if not validate_xml_basic(temp_xml):
            logger.log('Generated XML failed validation, skipping update', log_utils.LOGWARNING)
            return

        # Only update if there are actual changes
        if temp_xml != original_xml:
            with open(full_path, 'w') as f:
                f.write(temp_xml)
            logger.log('Settings updated successfully', log_utils.LOGDEBUG)
        else:
            logger.log('No Settings Update Needed', log_utils.LOGDEBUG)
            
    except Exception as e:
        logger.log('Settings update failed: %s' % str(e), log_utils.LOGERROR)


def update_all_scrapers():
    try:
        last_check = int(kodi.get_setting('last_list_check'))
    except:
        last_check = 0
    now = int(time.time())
    list_url = kodi.get_setting('scraper_url')
    scraper_password = kodi.get_setting('scraper_password')
    list_path = os.path.join(kodi.translate_path(kodi.get_profile()), 'scraper_list.txt')
    exists = os.path.exists(list_path)
    if list_url and scraper_password and (not exists or (now - last_check) > 15 * 60):
        _etag, scraper_list = utils2.get_and_decrypt(list_url, scraper_password)
        if scraper_list:
            try:
                with open(list_path, 'w') as f:
                    f.write(scraper_list)

                kodi.set_setting('last_list_check', str(now))
                kodi.set_setting('scraper_last_update', time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(now)))
                for line in scraper_list.split('\n'):
                    line = line.replace(' ', '')
                    if line:
                        scraper_url, filename = line.split(',')
                        if scraper_url.startswith('http'):
                            update_scraper(filename, scraper_url)
            except Exception as e:
                logger.log('Exception during scraper update: %s' % (e), log_utils.LOGWARNING)

def update_scraper(filename, scraper_url):
    try:
        if not filename:
            return
        py_path = os.path.join(kodi.get_path(), 'scrapers', filename)
        exists = os.path.exists(py_path)
        scraper_password = kodi.get_setting('scraper_password')
        if scraper_url and scraper_password:
            old_lm = None
            old_py = ''
            if exists:
                with open(py_path, 'r') as f:
                    old_py = f.read()
                    match = re.search('^#\s+Last-Modified:\s*(.*)', old_py)
                    if match:
                        old_lm = match.group(1).strip()

            new_lm, new_py = utils2.get_and_decrypt(scraper_url, scraper_password, old_lm)
            if new_py:
                logger.log('%s path: %s, new_py: %s, match: %s' % (filename, py_path, bool(new_py), new_py == old_py), log_utils.LOGDEBUG)
                if old_py != new_py:
                    with open(py_path, 'w') as f:
                        f.write('# Last-Modified: %s\n' % (new_lm))
                        f.write(new_py)
                    kodi.notify(msg=utils2.i18n('scraper_updated') + filename)
                        
    except Exception as e:
        logger.log('Failure during %s scraper update: %s' % (filename, e), log_utils.LOGWARNING)



update_settings()
update_all_scrapers()
