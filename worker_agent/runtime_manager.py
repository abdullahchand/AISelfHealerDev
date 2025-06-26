import asyncio
import subprocess
import time
import logging
from typing import Dict, List, Optional, Tuple
from pathlib import Path

from shared.models import AppConfig, ProcessInfo, AppStatus
from shared.utils import start_process, kill_process, get_process_info, health_check_port, health_check_url


class RuntimeManager:
    """Manages runtime operations for applications."""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.processes: Dict[str, subprocess.Popen] = {}
        self.app_logs: Dict[str, List[str]] = {}
        self.health_checks: Dict[str, Dict] = {}
    
    async def start_app(self, app_config: AppConfig) -> Tuple[bool, Optional[str]]:
        """Start an application and return success status and error message."""
        try:
            app_name = app_config.name
            
            # Check if app is already running
            if app_name in self.processes:
                return False, f"App {app_name} is already running"
            
            # Start the process
            process = start_process(
                command=app_config.command,
                working_dir=app_config.working_dir,
                env_vars=app_config.env_vars
            )
            
            if not process:
                return False, f"Failed to start process for {app_name}"
            
            # Store process
            self.processes[app_name] = process
            
            # Initialize logs
            self.app_logs[app_name] = []
            
            # Setup health check if configured
            if app_config.health_check_url:
                self.health_checks[app_name] = {
                    "type": "url",
                    "url": app_config.health_check_url,
                    "interval": app_config.health_check_interval
                }
            elif app_config.port:
                self.health_checks[app_name] = {
                    "type": "port",
                    "port": app_config.port,
                    "interval": app_config.health_check_interval
                }
            
            # Start log collection
            asyncio.create_task(self._collect_logs(app_name, process))
            
            # Start health monitoring if configured
            if app_name in self.health_checks:
                asyncio.create_task(self._health_monitor(app_name))
            
            return True, None
            
        except Exception as e:
            self.logger.error(f"Error starting app {app_config.name}: {e}")
            return False, str(e)
    
    async def stop_app(self, app_name: str) -> Tuple[bool, Optional[str]]:
        """Stop an application and return success status and error message."""
        try:
            if app_name not in self.processes:
                return False, f"App {app_name} is not running"
            
            process = self.processes[app_name]
            
            # Kill the process
            success = kill_process(process.pid)
            
            if success:
                # Clean up
                del self.processes[app_name]
                self.app_logs.pop(app_name, None)
                self.health_checks.pop(app_name, None)
                return True, None
            else:
                return False, f"Failed to kill process for {app_name}"
                
        except Exception as e:
            self.logger.error(f"Error stopping app {app_name}: {e}")
            return False, str(e)
    
    async def restart_app(self, app_name: str, app_config: AppConfig) -> Tuple[bool, Optional[str]]:
        """Restart an application."""
        try:
            # Stop the app
            success, error = await self.stop_app(app_name)
            if not success:
                return False, f"Failed to stop app: {error}"
            
            # Wait a moment
            await asyncio.sleep(2)
            
            # Start the app
            return await self.start_app(app_config)
            
        except Exception as e:
            self.logger.error(f"Error restarting app {app_name}: {e}")
            return False, str(e)
    
    async def _collect_logs(self, app_name: str, process: subprocess.Popen):
        """Collect logs from a running process."""
        try:
            # Read stdout
            if process.stdout:
                while True:
                    line = await asyncio.get_event_loop().run_in_executor(
                        None, process.stdout.readline
                    )
                    if not line:
                        break
                    
                    log_line = line.decode().strip()
                    self.app_logs[app_name].append(f"[{time.time()}] {log_line}")
                    
                    # Keep only last 1000 lines
                    if len(self.app_logs[app_name]) > 1000:
                        self.app_logs[app_name] = self.app_logs[app_name][-1000:]
            
            # Read stderr
            if process.stderr:
                while True:
                    line = await asyncio.get_event_loop().run_in_executor(
                        None, process.stderr.readline
                    )
                    if not line:
                        break
                    
                    log_line = line.decode().strip()
                    self.app_logs[app_name].append(f"[{time.time()}] ERROR: {log_line}")
                    
                    # Keep only last 1000 lines
                    if len(self.app_logs[app_name]) > 1000:
                        self.app_logs[app_name] = self.app_logs[app_name][-1000:]
                        
        except Exception as e:
            self.logger.error(f"Error collecting logs for {app_name}: {e}")
    
    async def _health_monitor(self, app_name: str):
        """Monitor health of an application."""
        try:
            health_config = self.health_checks[app_name]
            
            while app_name in self.processes:
                # Perform health check
                is_healthy = False
                
                if health_config["type"] == "url":
                    is_healthy = health_check_url(health_config["url"])
                elif health_config["type"] == "port":
                    is_healthy = health_check_port(health_config["port"])
                
                if not is_healthy:
                    self.logger.warning(f"Health check failed for {app_name}")
                
                # Wait for next check
                await asyncio.sleep(health_config["interval"])
                
        except Exception as e:
            self.logger.error(f"Error in health monitor for {app_name}: {e}")
    
    def get_app_logs(self, app_name: str, lines: int = 100) -> List[str]:
        """Get recent logs for an application."""
        logs = self.app_logs.get(app_name, [])
        return logs[-lines:] if logs else []
    
    def get_app_status(self, app_name: str) -> Optional[Dict]:
        """Get status information for an application."""
        if app_name not in self.processes:
            return None
        
        process = self.processes[app_name]
        process_info = get_process_info(process.pid)
        
        if not process_info:
            return None
        
        return {
            "app_name": app_name,
            "pid": process.pid,
            "status": "running" if process.poll() is None else "stopped",
            "cpu_percent": process_info["cpu_percent"],
            "memory_percent": process_info["memory_percent"],
            "memory_info": process_info["memory_info"],
            "cmdline": process_info["cmdline"],
            "cwd": process_info["cwd"],
            "connections": process_info["connections"]
        }
    
    def get_all_apps_status(self) -> Dict[str, Dict]:
        """Get status for all managed applications."""
        return {
            app_name: self.get_app_status(app_name)
            for app_name in self.processes.keys()
        }
    
    def is_app_running(self, app_name: str) -> bool:
        """Check if an application is running."""
        if app_name not in self.processes:
            return False
        
        process = self.processes[app_name]
        return process.poll() is None
    
    def get_app_pid(self, app_name: str) -> Optional[int]:
        """Get the PID of an application."""
        if app_name in self.processes:
            return self.processes[app_name].pid
        return None 