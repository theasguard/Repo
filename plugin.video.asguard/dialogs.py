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
        self.run_in_background(self.update_progress)


    def run_in_background(self, task_function, *args, **kwargs):
        """Executes a function in a separate, non-blocking thread."""
        thread = Thread(target=task_function, args=args, kwargs=kwargs)
        thread.daemon = True  # Allows the main program to exit without waiting for this thread
        try:
            thread.start()
        except Exception as e:
            logger.log(f'Service: Failed to start background thread: {str(e)}', log_utils.LOGERROR)


    def update_progress(self):
        elapsed = time.time() - self.start_time
        progress = (elapsed / self.duration) * 100
        self.getControl(3014).setPercent(progress)
        
        if elapsed < self.duration and not self.result:
            xbmc.sleep(100)
            self.update_progress()
        else:
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
        # Clear properties when closing
        self.clearProperty('item.info.tvshowtitle')
        self.clearProperty('item.info.title')
        super(NextEpisodeDialog, self).close() 