from threading import Thread
import xbmcgui
import time
import xbmc
import kodi
import log_utils
import os

logger = log_utils.Logger.get_logger()

class NextEpisodeDialog(xbmcgui.WindowXMLDialog):
    def __init__(self, *args, **kwargs):
        try:
            super(NextEpisodeDialog, self).__init__(*args, **kwargs)
        except:
            xbmcgui.WindowXMLDialog.__init__(self)
        self.title = kwargs.get('title', '')
        self.message = kwargs.get('message', '')
        logger.log(f'NextEpisodeDialog: Title: {self.title}, Message: {self.message}', log_utils.LOGDEBUG)
        self.start_time = time.time()
        self.closed = False
        self.result = False
        self.actioned = None
        self.player = xbmc.Player()
        self.duration = self.player.getTotalTime() - self.player.getTime()        
    def onInit(self):
        self.setProperty('item.info.tvshowtitle', self.title)
        self.setProperty('item.info.title', self.message)
        self.setProperty('settings.color', 'FF12A0C7')
        logger.log(f'Set properties - ShowTitle: {self.title} | Details: {self.message}', log_utils.LOGDEBUG)
        self.run_in_background(self.background_tasks)


    def run_in_background(self, task_function, *args, **kwargs):
        """Executes a function in a separate, non-blocking thread."""
        thread = Thread(target=task_function, args=args, kwargs=kwargs)
        thread.daemon = True  # Allows the main program to exit without waiting for this thread
        try:
            thread.start()
        except Exception as e:
            logger.log(f'Service: Failed to start background thread: {str(e)}', log_utils.LOGERROR)


    def background_tasks(self):
        elapsed = time.time() - self.start_time
        progress = (elapsed / self.duration) * 100
        self.getControl(3014).setPercent(progress)

        try:
            while not self.closed:  # <-- Changed: Removed self.player.isPlaying() from condition
                # Check if player is still playing
                if not self.player.isPlaying():  # <-- Added: Explicit check
                    logger.log('NextEpisodeDialog: Playback ended, closing dialog', log_utils.LOGDEBUG)
                    self.close()
                    break
                
                # Calculate remaining time and progress
                try:
                    total_time = self.player.getTotalTime()
                    current_time = self.player.getTime()
                    remaining = total_time - current_time

                    # Calculate progress based on remaining time vs initial duration
                    progress = (remaining / self.duration) * 100

                    # Update progress bar
                    try:
                        self.getControl(3014).setPercent(progress)
                    except:
                        pass

                    # Close if less than 1% remaining or user has taken action
                    if progress < 1 or self.result:
                        self.close()
                        break
                except Exception as e:
                    logger.log(f'NextEpisodeDialog: Error getting playback info: {e}', log_utils.LOGWARNING)

                xbmc.sleep(100)
        except Exception as e:
            logger.log(f'NextEpisodeDialog: Error in background_tasks: {e}', log_utils.LOGERROR)
            self.close()


    def onClick(self, controlId):
        self.handle_action(7, controlId)

    def doModal(self):
        try:
            super(NextEpisodeDialog, self).doModal()
        except:
            import traceback
            traceback.print_exc()

    def handle_action(self, action, controlId=None):
        if controlId is None:
            controlId = self.getFocusId()

        if controlId == 3001:
            self.actioned = True
            self.result = True
            self.player.seekTime(self.player.getTotalTime() - 5)
            self.close()
        if controlId == 3002:
            self.actioned = True
            self.result = False
            self.close()

    def onAction(self, action):
        action_id = action.getId()
        
        # Handle navigation keys
        if action_id in [92, 10, 100, 401]:
            # BACKSPACE / ESCAPE
            self.close()

        if action_id == 7:
            self.handle_action(action_id)
            return


    def close(self):
        self.closed = True
        try:
            # Clear properties when closing
            self.clearProperty('item.info.tvshowtitle')
            self.clearProperty('item.info.title')
            super(NextEpisodeDialog, self).close()
        except Exception as e:
            logger.log(f'NextEpisodeDialog: Error closing dialog: {e}', log_utils.LOGERROR)