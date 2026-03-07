
"""
    Asguard Addon - FlareSolverr Service
    Copyright (C) 2025

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
import os
import sys
import json
import time
import threading
import subprocess
import socket
import requests
import xbmc
import xbmcgui
import xbmcaddon
import log_utils
import kodi

logger = log_utils.Logger.get_logger()
addon = xbmcaddon.Addon('plugin.video.asguard')

"""
FlareSolverr Service Integration Documentation
=====================================

This module provides a self-contained FlareSolverr service that can be automatically
started and managed by the Asguard Kodi addon.

INTEGRATION STEPS:

1. Import the service in your service.py:
   ```python
   from asguard_lib.flaresolverr_service import get_flaresolverr_service
   ```

2. Initialize the service in main() function:
   ```python
   # Initialize FlareSolverr service
   flaresolverr_service = get_flaresolverr_service()
   if kodi.get_setting('flaresolverr_auto_start', 'true') == 'true':
       flaresolverr_service.start()
   ```

3. Add settings to settings.xml:
   
   **For Kodi 20+ (New Format):**
   ```xml
   <setting id="flaresolverr_auto_start" type="boolean" label="30177" default="true">
       <level>0</level>
       <default>true</default>
       <control type="toggle"/>
   </setting>
   <setting id="flaresolverr_auto_port" type="boolean" label="30178" default="true">
       <level>0</level>
       <default>true</default>
       <control type="toggle"/>
   </setting>
   <setting id="flaresolverr_port" type="number" label="30179" default="8191">
       <level>0</level>
       <default>8191</default>
       <control type="edit" format="integer"/>
   </setting>
   ```
   
   **For Older Kodi Versions (Legacy Format):**
   ```xml
   <setting id="flaresolverr_auto_start" type="boolean" label="Auto-start FlareSolverr" default="true"/>
   <setting id="flaresolverr_auto_port" type="boolean" label="Auto-select FlareSolverr port" default="true"/>
   <setting id="flaresolverr_port" type="number" label="FlareSolverr port" default="8191"/>
   ```
   
   **Note:** The new format provides better control over the appearance and behavior of settings, but the legacy format is still supported for backward compatibility with older Kodi versions.

4. Update scraper.py to use the service:
   - Modify FLARESOLVERR_URL to use the service URL:
     ```python
     flaresolverr_service = get_flaresolverr_service()
     FLARESOLVERR_URL = flaresolverr_service.get_url()
     ```

5. Clean up on addon shutdown:
   ```python
   # In service.py main loop, before exit:
   if flaresolverr_service.is_running():
       flaresolverr_service.stop()
   ```

FEATURES:

- Automatic download of FlareSolverr binary based on platform
- Port conflict detection and automatic port selection
- Process management (start/stop/restart)
- Connection testing
- Kodi notifications for status updates

USAGE:

The service can be used directly by scrapers that need FlareSolverr:

```python
from asguard_lib.flaresolverr_service import get_flaresolverr_service

# Get the service instance
flaresolverr_service = get_flaresolverr_service()

# Ensure it's running
if not flaresolverr_service.is_running():
    flaresolverr_service.start()

# Get the API URL for requests
api_url = flaresolverr_service.get_api_url()
```

"""


class FlareSolverrService:
    """
    Service to manage FlareSolverr process for the Asguard addon
    """

    def __init__(self):
        self.process = None
        self.host = '127.0.0.1'
        self.port = 8191
        self.flare_solverr_url = f'http://{self.host}:{self.port}'
        self.flare_solverr_api = f'{self.flare_solverr_url}/v1'
        self.running = False
        self.thread = None
        self.stop_event = threading.Event()

        # Path to store FlareSolverr files
        self.addon_path = addon.getAddonInfo('path')
        self.flaresolverr_path = os.path.join(self.addon_path, 'flaresolverr')
        self.flaresolverr_bin = self._get_flare_solverr_binary_path()

        # Settings
        self.auto_start = kodi.get_setting('flaresolverr_auto_start') == 'true'
        self.auto_port = kodi.get_setting('flaresolverr_auto_port') == 'true'
        self.custom_port = kodi.get_setting('flaresolverr_port') or '8191'

        if self.auto_port:
            try:
                self.port = int(self.custom_port)
                self.flare_solverr_url = f'http://{self.host}:{self.port}'
                self.flare_solverr_api = f'{self.flare_solverr_url}/v1'
            except ValueError:
                logger.log('Invalid FlareSolverr port setting, using default 8191', log_utils.LOGWARNING)

    def _get_flare_solverr_binary_path(self):
        """
        Get the path to the FlareSolverr binary based on the platform
        """
        platform = sys.platform
        binary_name = None

        if platform == 'win32' or platform == 'win64':
            binary_name = 'flaresolverr.exe'
        elif platform.startswith('linux'):
            binary_name = 'flaresolverr'
        elif platform == 'darwin':
            binary_name = 'flaresolverr'

        if binary_name:
            return os.path.join(self.flaresolverr_path, binary_name)

        return None

    def _is_port_in_use(self, port):
        """
        Check if a port is already in use
        """
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            return s.connect_ex((self.host, port)) == 0

    def _find_available_port(self, start_port=8191, max_attempts=10):
        """
        Find an available port starting from start_port
        """
        for i in range(max_attempts):
            port = start_port + i
            if not self._is_port_in_use(port):
                return port
        return start_port  # Fallback to start_port if all are in use

    def _download_flaresolverr(self):
        """
        Download FlareSolverr binary if not present
        """
        if os.path.exists(self.flaresolverr_bin):
            return True

        try:
            # Create the directory if it doesn't exist
            if not os.path.exists(self.flaresolverr_path):
                os.makedirs(self.flaresolverr_path)

            # Determine the platform and download URL
            platform = sys.platform
            download_url = None

            if platform == 'win32' or platform == 'win64':
                download_url = 'https://github.com/FlareSolverr/FlareSolverr/releases/latest/download/flaresolverr_windows_x64.exe'
            elif platform.startswith('linux'):
                download_url = 'https://github.com/FlareSolverr/FlareSolverr/releases/latest/download/flaresolverr_linux_x64'
            elif platform == 'darwin':
                download_url = 'https://github.com/FlareSolverr/FlareSolverr/releases/latest/download/flaresolverr_macos_x64'

            if not download_url:
                logger.log(f'Unsupported platform for FlareSolverr: {platform}', log_utils.LOGERROR)
                return False

            # Show a progress dialog
            progress = xbmcgui.DialogProgress()
            progress.create('Downloading FlareSolverr', 'Downloading required components...')
            progress.update(0)

            # Download the file
            logger.log(f'Downloading FlareSolverr from {download_url}', log_utils.LOGNOTICE)
            response = requests.get(download_url, stream=True)
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            bytes_downloaded = 0

            with open(self.flaresolverr_bin, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    if chunk:
                        f.write(chunk)
                        bytes_downloaded += len(chunk)

                        if total_size > 0:
                            percent = min(100, int(bytes_downloaded * 100 / total_size))
                            progress.update(percent)

            # Make the binary executable on Unix-like systems
            if not (platform == 'win32' or platform == 'win64'):
                os.chmod(self.flaresolverr_bin, 0o755)

            progress.close()
            logger.log('FlareSolverr downloaded successfully', log_utils.LOGNOTICE)
            return True

        except Exception as e:
            logger.log(f'Failed to download FlareSolverr: {str(e)}', log_utils.LOGERROR)
            if 'progress' in locals():
                progress.close()
            xbmcgui.Dialog().notification('Asguard', 
                                       f'Failed to download FlareSolverr: {str(e)}', 
                                       xbmcgui.NOTIFICATION_ERROR, 5000)
            return False

    def start(self):
        """
        Start the FlareSolverr service
        """
        if self.running:
            logger.log('FlareSolverr service is already running', log_utils.LOGDEBUG)
            return True

        # Check if FlareSolverr binary exists, download if needed
        if not os.path.exists(self.flaresolverr_bin):
            if not self._download_flaresolverr():
                logger.log('Failed to start FlareSolverr: binary not available', log_utils.LOGERROR)
                return False

        # Check if port is in use and find an available one if needed
        if self._is_port_in_use(self.port):
            if self.auto_port:
                self.port = self._find_available_port(self.port)
                self.flare_solverr_url = f'http://{self.host}:{self.port}'
                self.flare_solverr_api = f'{self.flare_solverr_url}/v1'
                logger.log(f'Port {self.port} in use, switching to port {self.port}', log_utils.LOGNOTICE)
            else:
                logger.log(f'Port {self.port} is already in use', log_utils.LOGWARNING)
                # Check if FlareSolverr is already running on this port
                if self._test_connection():
                    logger.log('FlareSolverr is already running on the configured port', log_utils.LOGNOTICE)
                    self.running = True
                    return True
                else:
                    logger.log('Port is in use by another application', log_utils.LOGERROR)
                    xbmcgui.Dialog().notification('Asguard', 
                                               'FlareSolverr port is in use by another application', 
                                               xbmcgui.NOTIFICATION_ERROR, 5000)
                    return False

        # Start the FlareSolverr process
        try:
            logger.log(f'Starting FlareSolverr on port {self.port}', log_utils.LOGNOTICE)

            # Prepare the command
            cmd = [self.flaresolverr_bin, '--port', str(self.port)]

            # Start the process
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self.flaresolverr_path
            )

            # Wait a moment for the process to start
            time.sleep(2)

            # Check if the process started successfully
            if self.process.poll() is not None:
                # Process has terminated
                stderr = self.process.stderr.read().decode('utf-8')
                logger.log(f'FlareSolverr process exited with error: {stderr}', log_utils.LOGERROR)
                xbmcgui.Dialog().notification('Asguard', 
                                           f'FlareSolverr failed to start: {stderr}', 
                                           xbmcgui.NOTIFICATION_ERROR, 5000)
                return False

            # Test connection to FlareSolverr
            if self._test_connection():
                self.running = True
                logger.log(f'FlareSolverr started successfully on port {self.port}', log_utils.LOGNOTICE)
                xbmcgui.Dialog().notification('Asguard', 
                                           f'FlareSolverr started on port {self.port}', 
                                           xbmcgui.NOTIFICATION_INFO, 3000)
                return True
            else:
                logger.log('Failed to connect to FlareSolverr after starting', log_utils.LOGERROR)
                xbmcgui.Dialog().notification('Asguard', 
                                           'Failed to connect to FlareSolverr', 
                                           xbmcgui.NOTIFICATION_ERROR, 5000)
                return False

        except Exception as e:
            logger.log(f'Failed to start FlareSolverr: {str(e)}', log_utils.LOGERROR)
            xbmcgui.Dialog().notification('Asguard', 
                                       f'Failed to start FlareSolverr: {str(e)}', 
                                       xbmcgui.NOTIFICATION_ERROR, 5000)
            return False

    def stop(self):
        """
        Stop the FlareSolverr service
        """
        if not self.running:
            logger.log('FlareSolverr service is not running', log_utils.LOGDEBUG)
            return True

        try:
            if self.process:
                # Try to terminate gracefully
                self.process.terminate()

                # Wait a moment for termination
                try:
                    self.process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    # Force kill if it doesn't terminate
                    self.process.kill()
                    self.process.wait()

                self.process = None

            self.running = False
            logger.log('FlareSolverr stopped', log_utils.LOGNOTICE)
            return True

        except Exception as e:
            logger.log(f'Error stopping FlareSolverr: {str(e)}', log_utils.LOGERROR)
            return False

    def _test_connection(self):
        """
        Test if FlareSolverr is responding
        """
        try:
            response = requests.get(self.flare_solverr_api, timeout=5)
            if response.status_code == 200:
                data = response.json()
                return data.get('status') == 'ready'
        except Exception as e:
            logger.log(f'FlareSolverr connection test failed: {str(e)}', log_utils.LOGDEBUG)

        return False

    def get_url(self):
        """
        Get the FlareSolverr URL
        """
        return self.flare_solverr_url

    def get_api_url(self):
        """
        Get the FlareSolverr API URL
        """
        return self.flare_solverr_api

    def is_running(self):
        """
        Check if FlareSolverr is running
        """
        return self.running

    def restart(self):
        """
        Restart the FlareSolverr service
        """
        self.stop()
        time.sleep(1)
        return self.start()

# Global instance
_flaresolverr_service = None

def get_flaresolverr_service():
    """
    Get the global FlareSolverr service instance
    """
    global _flaresolverr_service
    if _flaresolverr_service is None:
        _flaresolverr_service = FlareSolverrService()
    return _flaresolverr_service
