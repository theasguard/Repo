"""
    Asguard Addon
    Copyright (C) 2025 tknorris

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
import gc
import re, subprocess
import socket
import sys
import xbmc, xbmcgui, xbmcaddon
import time
import kodi
import log_utils
import utils
from urllib.parse import quote
import os
import urllib.request
import ssl
from asguard_lib import control, salts_utils, image_proxy, utils2
from asguard_lib.utils2 import i18n
from asguard_lib.constants import MODES
from asguard_lib.db_utils import DB_Connection
from asguard_lib.trakt_api import Trakt_API
from threading import Thread
from dialogs import NextEpisodeDialog

logger = log_utils.Logger.get_logger()
addon = xbmcaddon.Addon('plugin.video.asguard')
path_setting = addon.getSetting('xml_folder')
addon_path = addon.getAddonInfo('path')
use_https = kodi.get_setting('use_https') == 'true'
list_size = int(kodi.get_setting('list_size'))
trakt_timeout = int(kodi.get_setting('trakt_timeout'))
trakt_offline = kodi.get_setting('trakt_offline') == 'true'
TOKEN = kodi.get_setting('trakt_oauth_token')
logger.log(f'Service: TOKEN: {TOKEN}', log_utils.LOGDEBUG)

class Service(xbmc.Player):
    def __init__(self, *args, **kwargs):
        logger.log('Service: starting...', log_utils.LOGNOTICE)
        self.db_connection = DB_Connection()
        xbmc.Player.__init__(self, *args, **kwargs)
        self.win = xbmcgui.Window(10000)
        self.reset()

    def reset(self):
        logger.log('Service: Resetting...', log_utils.LOGDEBUG)
        self.win.clearProperty('asguard.playing')
        self.win.clearProperty('asguard.playing.trakt_id')
        self.win.clearProperty('asguard.playing.season')
        self.win.clearProperty('asguard.playing.episode')
        self.win.clearProperty('asguard.playing.srt')
        self.win.clearProperty('asguard.playing.trakt_resume')
        self.win.clearProperty('asguard.playing.asguard_resume')
        self.win.clearProperty('asguard.playing.library')
        self._from_library = False
        self.tracked = False
        self._totalTime = 999999
        self.trakt_id = None
        self.season = None
        self.episode = None
        self._lastPos = 0
        self._next_episode_shown = False

    def show_next_episode_prompt(self):
        if not self.season or not self.episode:
            return
            
        token = TOKEN
        if not token or self._next_episode_shown:
            return

        try:
            current_season = int(self.season)
            logger.log(f'Service: Current Season: {current_season}', log_utils.LOGDEBUG)
            current_episode = int(self.episode)
            logger.log(f'Service: Current Episode: {current_episode}', log_utils.LOGDEBUG)
            
            trakt_api = Trakt_API(token, use_https, list_size, trakt_timeout, trakt_offline)

            # Create a custom opener without authentication handlers
            opener = urllib.request.build_opener(
                urllib.request.HTTPHandler(),
                urllib.request.HTTPSHandler(context=ssl.create_default_context())
            )

            # First get SERIES metadata
            show_details = trakt_api.get_show_details(self.trakt_id)
            logger.log(f'Service: Show Details: {show_details}', log_utils.LOGDEBUG)
            progress = trakt_api.get_show_progress(self.trakt_id, full=True)
            logger.log(f'Service: Progress 2: {progress}', log_utils.LOGDEBUG)
            all_episodes = trakt_api.get_episodes(self.trakt_id, current_season)
            logger.log(f'Service: All Episodes: {all_episodes}', log_utils.LOGDEBUG)
            
            # Manual next episode detection
            next_ep = None
            current_ep_index = None
            
            # Find current episode in season
            for idx, ep in enumerate(all_episodes):
                if ep['number'] == current_episode:
                    current_ep_index = idx
                    break
            
            if current_ep_index is not None:
                # Check next episode in same season
                if current_ep_index + 1 < len(all_episodes):
                    next_ep = all_episodes[current_ep_index + 1]
                else:
                    # Check first episode of next season
                    next_season_eps = trakt_api.get_episodes(self.trakt_id, current_season + 1)
                    if next_season_eps:
                        next_ep = next_season_eps[0]
            
            # Fallback to Trakt's next_episode if manual lookup fails
            if not next_ep and 'next_episode' in progress and progress['next_episode']:
                next_ep = progress['next_episode']
                logger.log('Using Trakt fallback next episode', log_utils.LOGDEBUG)

            if next_ep:
                logger.log(f'Service: Calculated Next Episode: {next_ep}', log_utils.LOGDEBUG)
                show_title = show_details.get('title', '')
                alt_year = show_details.get('year', '')
                logger.log(f'Service: Show Title: {show_title}', log_utils.LOGDEBUG)
                logger.log(f'Service: Alt Year: {alt_year}', log_utils.LOGDEBUG)
                show_year = self.win.getProperty('asguard.playing.year')
                logger.log(f'Service: Show Year: {show_year}', log_utils.LOGDEBUG)
        
                date = utils2.make_day(utils2.make_air_date(next_ep['first_aired']))
                date_time = f'{date}@{utils2.make_time(utils.iso_2_utc(next_ep["first_aired"]), "next_time")}' \
                            if kodi.get_setting('next_time') != '0' else date
                            
                msg = (f'[[COLOR deeppink]{alt_year}[/COLOR]] - {next_ep["season"]}x{next_ep["number"]}' +
                    (f' - {next_ep.get("title", "")}' if next_ep.get('title') else ''))
                logger.log(f'Service: Msg: {msg}', log_utils.LOGDEBUG)
                    
                xml_path = os.path.join(addon_path, 'resources', 'skins', 'Default', '1080p', 'playing_next.xml')
                logger.log(f'Checking XML existence at: {xml_path}', log_utils.LOGDEBUG)

                # Replace the yesno dialog with XML implementation
                dialog = NextEpisodeDialog('playing_next.xml', kodi.get_path(), 'Default', '1080p',
                                        title=show_title, 
                                        message=msg)

                dialog.doModal()
                
                if dialog.result:
                    self._next_episode_shown = True
                    show_title_encoded = quote(show_title)
                    logger.log(f'Service: Show Title Encoded: {show_title_encoded}', log_utils.LOGDEBUG)
                    alt_year_encoded = quote(str(alt_year)) if alt_year else ''
                    logger.log(f'Service: Alt Year Encoded: {alt_year_encoded}', log_utils.LOGDEBUG)
                    url = (f'plugin://{kodi.get_id()}/?mode={MODES.GET_SOURCES}&video_type=Episode'
                           f'&title={show_title_encoded}&year={alt_year_encoded}'
                           f'&season={next_ep["season"]}&episode={next_ep["number"]}&trakt_id={self.trakt_id}')
                    logger.log(f'Service: Playing next episode: {url}', log_utils.LOGDEBUG)
                    xbmc.executebuiltin(f'PlayMedia({url})')
                
                del dialog
            
        except Exception as e:
            logger.log(f'Next episode prompt failed: {str(e)}', log_utils.LOGERROR)
        finally:
            gc.collect()
            
    def onPlayBackStarted(self):
        logger.log('Service: Playback started', log_utils.LOGNOTICE)
        self._next_episode_shown = False  # Add reset when new playback starts
        playing = self.win.getProperty('asguard.playing') == 'True'
        self.trakt_id = self.win.getProperty('asguard.playing.trakt_id')
        self.season = self.win.getProperty('asguard.playing.season')
        self.episode = self.win.getProperty('asguard.playing.episode')
        srt_path = self.win.getProperty('asguard.playing.srt')
        trakt_resume = self.win.getProperty('asguard.playing.trakt_resume')
        logger.log('Service: trakt_resume: %s' % (trakt_resume), log_utils.LOGDEBUG)
        asguard_resume = self.win.getProperty('asguard.playing.asguard_resume')
        self._from_library = self.win.getProperty('asguard.playing.library') == 'True'
        if playing:   # Playback is ours
            logger.log('Service: tracking progress...', log_utils.LOGNOTICE)
            self.tracked = True
            if srt_path:
                logger.log('Service: Enabling subtitles: %s' % (srt_path), log_utils.LOGDEBUG)
                self.setSubtitles(srt_path)
            else:
                self.showSubtitles(False)

            # Capture metadata BEFORE playback takes focus
            self.win.setProperty('asguard.playing.year', xbmc.getInfoLabel('ListItem.Year'))
            logger.log(f'Service: Year: {self.win.getProperty("asguard.playing.year")}', log_utils.LOGDEBUG)

        self._totalTime = 0
        while self._totalTime == 0:
            try:
                self._totalTime = self.getTotalTime()
            except RuntimeError:
                self._totalTime = 0
                break
            xbmc.sleep(1000)

        if asguard_resume:
            logger.log("Salts Local Resume: Resume Time: %s Total Time: %s" % (asguard_resume, self._totalTime), log_utils.LOGDEBUG)
            self.seekTime(float(asguard_resume))
        elif trakt_resume:
            resume_time = float(trakt_resume) * self._totalTime / 100
            logger.log("Salts Trakt Resume: Percent: %s, Resume Time: %s Total Time: %s" % (trakt_resume, resume_time, self._totalTime), log_utils.LOGDEBUG)
            self.seekTime(resume_time)

        if playing and self._totalTime > 0:
            logger.log(f'Service: Starting monitoring thread - TotalTime: {self._totalTime}', log_utils.LOGDEBUG)
            try:
                Thread(target=self.monitor_playback_progress).start()
            except Exception as e:
                logger.log(f'Service: Failed to start monitoring thread: {str(e)}', log_utils.LOGERROR)

    def monitor_playback_progress(self):
        try:
            logger.log('Service: Starting playback monitoring', log_utils.LOGDEBUG)
            logger.log(f'Service: Initial State - Playing: {self.isPlaying()}, Tracked: {self.tracked}, Shown: {self._next_episode_shown}', log_utils.LOGDEBUG)
            
            while self.isPlaying() and self.tracked and not self._next_episode_shown:
                if self._is_video_window_open():
                    current_pos = float(self._lastPos)
                    try: 
                        progress = int((current_pos / self._totalTime) * 100)
                    except: 
                        progress = 0  # guard div by zero
                    # pTime = utils.format_time(current_pos)
                    # tTime = utils.format_time(self._totalTime)
                    # logger.log('Service: Played %s of %s total = %s%%' % (pTime, tTime, progress), log_utils.LOGDEBUG)
                    
                    if progress >= 97 and not self._from_library:
                        self.show_next_episode_prompt()
                        break
                    xbmc.sleep(1000)
        except:
            pass
        finally:
            logger.log('Service: Monitoring thread exited', log_utils.LOGDEBUG)

    def onPlayBackStopped(self):
        logger.log('Service: Playback Stopped', log_utils.LOGNOTICE)
        if self.tracked:
            # clear the playlist if SALTS was playing and only one item in playlist to
            # use playlist to determine playback method in get_sources
            pl = xbmc.PlayList(xbmc.PLAYLIST_VIDEO)
            plugin_url = 'plugin://%s/' % (kodi.get_id())
            if pl.size() == 1 and pl[0].getPath().lower().startswith(plugin_url):
                logger.log('Service: Clearing Single Item Asguard Playlist', log_utils.LOGDEBUG)
                pl.clear()
                
            playedTime = float(self._lastPos)
            try: 
                percent_played = int((playedTime / self._totalTime) * 100)
            except: 
                percent_played = 0  # guard div by zero
            pTime = utils.format_time(playedTime)
            tTime = utils.format_time(self._totalTime)
            logger.log('Service: Played %s of %s total = %s%%' % (pTime, tTime, percent_played), log_utils.LOGDEBUG)
            if playedTime == 0 and self._totalTime == 999999:
                logger.log('Kodi silently failed to start playback', log_utils.LOGWARNING)
            elif playedTime >= 5:
                if percent_played <= 98:
                    logger.log('Service: Setting bookmark on |%s|%s|%s| to %s seconds' % (self.trakt_id, self.season, self.episode, playedTime), log_utils.LOGDEBUG)
                    self.db_connection.set_bookmark(self.trakt_id, playedTime, self.season, self.episode)
                    
                if percent_played >= 75 and self._from_library:
                    if kodi.has_addon('script.trakt'):
                        run = 'RunScript(script.trakt, action=sync, silent=True)'
                        xbmc.executebuiltin(run)
            self.reset()

    def onPlayBackEnded(self):
        logger.log('Service: Playback completed', log_utils.LOGNOTICE)
        self.onPlayBackStopped()

    @staticmethod
    def _is_video_window_open():

        if xbmcgui.getCurrentWindowId() != 12005:
            return False
        return True

    def skip_to_end(self):
        """Skip to last 5 seconds of playback"""
        if self.isPlaying():
            try:
                total_time = self.getTotalTime()
                self.seekTime(max(0, total_time - 5))
                logger.log('Skipped to last 5 seconds of playback', log_utils.LOGDEBUG)
            except Exception as e:
                logger.log(f'Skip to end failed: {str(e)}', log_utils.LOGERROR)

def show_next_up(last_label, sf_begin):
    token = kodi.get_setting('trakt_oauth_token')

    container_content = xbmc.getInfoLabel('Container.Content')
    logger.log(f'Service: Container Content: {container_content}', log_utils.LOGDEBUG)
    
    if token and xbmc.getInfoLabel('Container.PluginName') == kodi.get_id() and xbmc.getInfoLabel('Container.Content') == 'tvshows':
        if xbmc.getInfoLabel('ListItem.Title') != last_label:
            sf_begin = time.time()

        last_label = xbmc.getInfoLabel('ListItem.Title')
        if sf_begin and (time.time() - sf_begin) >= int(kodi.get_setting('next_up_delay')):
            liz_url = xbmc.getInfoLabel('ListItem.FileNameAndPath')
            queries = kodi.parse_query(liz_url[liz_url.find('?'):])
            if 'trakt_id' in queries:
                try: list_size = int(kodi.get_setting('list_size'))
                except: list_size = 30
                try: trakt_timeout = int(kodi.get_setting('trakt_timeout'))
                except: trakt_timeout = 20
                trakt_api = Trakt_API(token, kodi.get_setting('use_https') == 'true', list_size, trakt_timeout, kodi.get_setting('trakt_offline') == 'true')
                progress = trakt_api.get_show_progress(queries['trakt_id'], full=True)
                logger.log(f'Service: Progress: {progress}', log_utils.LOGDEBUG)
                if 'next_episode' in progress and progress['next_episode']:
                    if progress['completed'] or kodi.get_setting('next_unwatched') == 'true':
                        next_episode = progress['next_episode']
                        date = utils2.make_day(utils2.make_air_date(next_episode['first_aired']))
                        if kodi.get_setting('next_time') != '0':
                            date_time = '%s@%s' % (date, utils2.make_time(utils.iso_2_utc(next_episode['first_aired']), 'next_time'))
                        else:
                            date_time = date
                        msg = f'[[COLOR deeppink]{date_time}[/COLOR]] - {next_episode["season"]}x{next_episode["number"]}'
                        if next_episode['title']: msg += f' - {next_episode["title"]}'
                        duration = int(kodi.get_setting('next_up_duration')) * 1000
                        kodi.notify(header=i18n('next_episode'), msg=msg, duration=duration)
            sf_begin = 0
    else:
        last_label = ''
    
    return last_label, sf_begin

def main(argv=None):  # @UnusedVariable
    if sys.argv: argv = sys.argv  # @UnusedVariable

    MAX_ERRORS = 10
    errors = 0
    last_label = ''
    sf_begin = 0
    
    logger.log('Service: Installed Version: %s' % (kodi.get_version()), log_utils.LOGNOTICE)
    monitor = xbmc.Monitor()
    proxy = image_proxy.ImageProxy()
    service = Service()
    
    # Add port conflict check
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        if sock.connect_ex((proxy.host, proxy.port)) == 0:
            logger.log('Port %s in use, rotating port' % proxy.port, log_utils.LOGWARNING)
            proxy.port = image_proxy.ImageProxy._get_port()
    finally:
        sock.close()

    salts_utils.do_startup_task(MODES.UPDATE_SUBS)
    salts_utils.do_startup_task(MODES.PRUNE_CACHE)
    
    while not monitor.abortRequested():
        try:
            is_playing = service.isPlaying()
            salts_utils.do_scheduled_task(MODES.UPDATE_SUBS, is_playing)
            salts_utils.do_scheduled_task(MODES.PRUNE_CACHE, is_playing)
            if service.tracked and service.isPlayingVideo():
                service._lastPos = service.getTime()

            if not proxy.running: proxy.start_proxy()
            
            if kodi.get_setting('show_next_up') == 'true':
                last_label, sf_begin = show_next_up(last_label, sf_begin)
        except Exception as e:
            errors += 1
            if errors >= MAX_ERRORS:
                logger.log('Service: Error (%s) received..(%s/%s)...Ending Service...' % (e, errors, MAX_ERRORS), log_utils.LOGERROR)
                break
            else:
                logger.log('Service: Error (%s) received..(%s/%s)...Continuing Service...' % (e, errors, MAX_ERRORS), log_utils.LOGERROR)
        else:
            errors = 0

        if monitor.waitForAbort(.5):
            break

    proxy.stop_proxy()
    logger.log('Service: shutting down...', log_utils.LOGNOTICE)

if __name__ == '__main__':
    sys.exit(main())