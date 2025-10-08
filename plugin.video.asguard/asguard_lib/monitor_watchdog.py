"""
    Asguard Addon
    Copyright (C) 2025 MrBlamo

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
import time
import threading
import log_utils
import xbmc

logger = log_utils.Logger.get_logger(__name__)

class MonitorWatchdog(object):
    """Watchdog to monitor and restart stuck monitors"""

    def __init__(self, check_interval=30, response_timeout=60):
        """
        Initialize the watchdog

        Args:
            check_interval (int): How often to check monitors (in seconds)
            response_timeout (int): How long a monitor can go without updating (in seconds)
        """
        self.check_interval = check_interval
        self.response_timeout = response_timeout
        self.monitors = {}
        self.lock = threading.Lock()
        self.running = False
        self.thread = None

    def register_monitor(self, name, monitor_obj):
        """Register a monitor to be watched

        Args:
            name (str): Name of the monitor
            monitor_obj (object): The monitor object to watch
        """
        with self.lock:
            self.monitors[name] = {
                'object': monitor_obj,
                'last_seen': time.time(),
                'restart_count': 0
            }
            logger.log(f"Registered monitor: {name}", log_utils.LOGDEBUG)

    def unregister_monitor(self, name):
        """Unregister a monitor

        Args:
            name (str): Name of the monitor
        """
        with self.lock:
            if name in self.monitors:
                del self.monitors[name]
                logger.log(f"Unregistered monitor: {name}", log_utils.LOGDEBUG)

    def update_monitor(self, name):
        """Update a monitor's last seen timestamp

        Args:
            name (str): Name of the monitor
        """
        with self.lock:
            if name in self.monitors:
                self.monitors[name]['last_seen'] = time.time()
                logger.log(f"Updated monitor: {name}", log_utils.LOGDEBUG)

    def start(self):
        """Start the watchdog thread"""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._run)
            self.thread.daemon = True
            self.thread.start()
            logger.log("Monitor watchdog started", log_utils.LOGNOTICE)

    def stop(self):
        """Stop the watchdog thread"""
        if self.running:
            self.running = False
            if self.thread:
                self.thread.join()
                self.thread = None
            logger.log("Monitor watchdog stopped", log_utils.LOGNOTICE)

    def _run(self):
        """Main watchdog loop"""
        while self.running:
            try:
                self._check_monitors()
                time.sleep(self.check_interval)
            except Exception as e:
                logger.log(f"Error in watchdog: {str(e)}", log_utils.LOGERROR)

    def _check_monitors(self):
        """Check all registered monitors and restart any that are stuck"""
        current_time = time.time()
        monitors_to_restart = []

        with self.lock:
            for name, info in self.monitors.items():
                monitor_obj = info['object']
                last_seen = info['last_seen']
                restart_count = info['restart_count']

                # Check if the monitor hasn't updated within the timeout
                if current_time - last_seen > self.response_timeout:
                    logger.log(f"Monitor {name} appears stuck (last seen {current_time - last_seen:.1f}s ago)", 
                              log_utils.LOGWARNING)
                    monitors_to_restart.append((name, monitor_obj, restart_count))

        # Restart stuck monitors (outside the lock to avoid deadlock)
        for name, monitor_obj, restart_count in monitors_to_restart:
            self._restart_monitor(name, monitor_obj, restart_count)

    def _restart_monitor(self, name, monitor_obj, restart_count):
        """Attempt to restart a stuck monitor

        Args:
            name (str): Name of the monitor
            monitor_obj (object): The monitor object to restart
            restart_count (int): Number of times this monitor has been restarted
        """
        try:
            # Try to gracefully stop the monitor
            if hasattr(monitor_obj, 'stop'):
                logger.log(f"Attempting to stop monitor {name}", log_utils.LOGDEBUG)
                monitor_obj.stop()

                # Give it a moment to stop
                time.sleep(1)

            # Try to restart the monitor
            if hasattr(monitor_obj, 'start'):
                logger.log(f"Restarting monitor {name} (restart #{restart_count + 1})", log_utils.LOGWARNING)
                monitor_obj.start()

                # Update the restart count
                with self.lock:
                    if name in self.monitors:
                        self.monitors[name]['restart_count'] = restart_count + 1
                        self.monitors[name]['last_seen'] = time.time()

                logger.log(f"Successfully restarted monitor {name}", log_utils.LOGNOTICE)
            else:
                logger.log(f"Monitor {name} does not have a start method, cannot restart", log_utils.LOGERROR)

        except Exception as e:
            logger.log(f"Failed to restart monitor {name}: {str(e)}", log_utils.LOGERROR)

    def get_monitor_status(self):
        """Get the status of all registered monitors

        Returns:
            dict: Status of all monitors
        """
        status = {}
        current_time = time.time()

        with self.lock:
            for name, info in self.monitors.items():
                last_seen = info['last_seen']
                restart_count = info['restart_count']

                status[name] = {
                    'last_seen_seconds_ago': current_time - last_seen,
                    'restart_count': restart_count,
                    'status': 'running' if current_time - last_seen <= self.response_timeout else 'stuck'
                }

        return status
