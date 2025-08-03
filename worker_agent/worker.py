import asyncio
import time
import logging
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../shared')))
from shared import agent_pb2, agent_pb2_grpc

from shared.models import AgentConfig, AppConfig, ProcessInfo, AppStatus, Task, Issue, IssueType
from shared.config import ConfigManager
from shared.utils import generate_id, setup_logging, start_process, kill_process, get_process_info
from worker_agent.runtime_manager import RuntimeManager
from worker_agent.log_parser import LogParser


class WorkerAgent:
    """Worker AI Agent - Modular runtime manager for individual applications."""
    
    def __init__(self, worker_id: str, config_path: str = "agent.config.yaml"):
        self.worker_id = worker_id
        self.config_manager = ConfigManager(config_path)
        
        # Setup logging
        self.logger = setup_logging()
        
        # Initialize components
        self.runtime_manager = RuntimeManager()
        self.log_parser = LogParser()
        
        # State
        self.running = False
        self.managed_apps: Dict[str, ProcessInfo] = {}
        self.active_tasks: Dict[str, Task] = {}
        self.detected_issues: List[Issue] = []
        
        # Master connection
        self.master_host = "localhost"
        self.master_port = 50051
        
        # Heartbeat
        self.last_heartbeat = time.time()
        self.heartbeat_interval = 30
        
        self.logger.info(f"Worker Agent {worker_id} initialized")
    
    async def start(self):
        print(f"[WorkerAgent] start() called for {self.worker_id}")
        try:
            self.logger.info(f"Starting Worker Agent {self.worker_id}...")
            
            # Start background tasks
            asyncio.create_task(self._heartbeat_sender())
            asyncio.create_task(self._app_monitor())
            asyncio.create_task(self._task_processor())
            asyncio.create_task(self._issue_detector())
            
            self.running = True
            self.logger.info(f"Worker Agent {self.worker_id} started successfully")
            
            # Keep running
            while self.running:
                await asyncio.sleep(1)
                
        except Exception as e:
            self.logger.error(f"Error starting Worker Agent {self.worker_id}: {e}")
            raise
    
    async def stop(self):
        """Stop the worker agent."""
        self.logger.info(f"Stopping Worker Agent {self.worker_id}...")
        self.running = False
        
        # Stop all managed apps
        for app_name, process_info in self.managed_apps.items():
            await self.stop_app(app_name)
        
        self.logger.info(f"Worker Agent {self.worker_id} stopped")
    
    async def connect_to_master(self):
        self.channel = grpc.aio.insecure_channel(f"{self.master_host}:{self.master_port}")
        self.stub = agent_pb2_grpc.AgentServiceStub(self.channel)
        self.logger.info(f"Connected to master at {self.master_host}:{self.master_port}")

    async def _heartbeat_sender(self):
        await self.connect_to_master()
        while self.running:
            try:
                request = agent_pb2.HeartbeatRequest(worker_id=self.worker_id, timestamp=int(time.time()), status="healthy")
                await self.stub.Heartbeat(request)
                self.last_heartbeat = time.time()
                self.logger.debug(f"Sent heartbeat to master")
                await asyncio.sleep(self.heartbeat_interval)
            except Exception as e:
                self.logger.error(f"Error sending heartbeat: {e}")
                await asyncio.sleep(5)
    
    async def _app_monitor(self):
        """Monitor managed applications."""
        while self.running:
            try:
                for app_name, process_info in list(self.managed_apps.items()):
                    # Check if process is still running
                    current_info = get_process_info(process_info.pid)
                    if not current_info:
                        # Process has died
                        self.logger.warning(f"Process for app {app_name} has died")
                        await self._handle_process_death(app_name)
                    else:
                        # Update process info
                        self.managed_apps[app_name] = ProcessInfo(
                            pid=current_info["pid"],
                            name=app_name,
                            status=AppStatus.RUNNING,
                            cpu_percent=current_info["cpu_percent"],
                            memory_percent=current_info["memory_percent"],
                            port=process_info.port,
                            start_time=process_info.start_time,
                            last_heartbeat=time.time()
                        )
                
                await asyncio.sleep(10)  # Check every 10 seconds
                
            except Exception as e:
                self.logger.error(f"Error in app monitor: {e}")
                await asyncio.sleep(30)
    
    async def _task_processor(self):
        """Process assigned tasks."""
        while self.running:
            try:
                # TODO: Check for new tasks from master via gRPC
                # For now, just log that we would process tasks
                await asyncio.sleep(5)
                
            except Exception as e:
                self.logger.error(f"Error in task processor: {e}")
                await asyncio.sleep(10)
    
    async def _issue_detector(self):
        """Detect issues in managed applications."""
        while self.running:
            try:
                for app_name, process_info in self.managed_apps.items():
                    # Get recent logs
                    logs = await self.runtime_manager.get_app_logs(app_name)
                    print(f"LOGS {logs}")
                    
                    # Parse logs for issues
                    issues = self.log_parser.parse_logs_for_issues(logs, app_name)
                    print(f"Issues in worker: {issues}")
                    
                    # Report new issues to master
                    for issue in issues:
                        if not self._is_issue_known(issue):
                            await self._report_issue_to_master(issue)
                            self.detected_issues.append(issue)
                
                await asyncio.sleep(30)  # Check every 30 seconds
                
            except Exception as e:
                self.logger.error(f"Error in issue detector: {e}")
                await asyncio.sleep(60)
    
    async def start_app(self, app_config: AppConfig) -> bool:
        """Start an application."""
        try:
            self.logger.info(f"Starting app: {app_config.name}")
            
            # Check if app is already running
            if app_config.name in self.managed_apps:
                self.logger.warning(f"App {app_config.name} is already running")
                return True
            
            # Start the process
            process = start_process(
                command=app_config.command,
                working_dir=app_config.working_dir,
                env_vars=app_config.env_vars
            )
            
            if not process:
                self.logger.error(f"Failed to start app {app_config.name}")
                return False
            
            # Create process info
            process_info = ProcessInfo(
                pid=process.pid,
                name=app_config.name,
                status=AppStatus.STARTING,
                port=app_config.port,
                start_time=time.time(),
                last_heartbeat=time.time()
            )
            
            # Store process info
            self.managed_apps[app_config.name] = process_info
            
            # Wait for app to start
            await asyncio.sleep(2)
            
            # Check if process is still running
            if get_process_info(process.pid):
                process_info.status = AppStatus.RUNNING
                self.logger.info(f"App {app_config.name} started successfully (PID: {process.pid})")
                return True
            else:
                self.logger.error(f"App {app_config.name} failed to start")
                del self.managed_apps[app_config.name]
                return False
                
        except Exception as e:
            self.logger.error(f"Error starting app {app_config.name}: {e}")
            return False
    
    async def stop_app(self, app_name: str) -> bool:
        """Stop an application."""
        try:
            self.logger.info(f"Stopping app: {app_name}")
            
            if app_name not in self.managed_apps:
                self.logger.warning(f"App {app_name} is not running")
                return True
            
            process_info = self.managed_apps[app_name]
            
            # Kill the process
            success = kill_process(process_info.pid)
            
            if success:
                del self.managed_apps[app_name]
                self.logger.info(f"App {app_name} stopped successfully")
                return True
            else:
                self.logger.error(f"Failed to stop app {app_name}")
                return False
                
        except Exception as e:
            self.logger.error(f"Error stopping app {app_name}: {e}")
            return False
    
    async def restart_app(self, app_name: str) -> bool:
        """Restart an application."""
        try:
            self.logger.info(f"Restarting app: {app_name}")
            
            # Stop the app
            await self.stop_app(app_name)
            
            # Get app config
            app_configs = self.config_manager.get_app_configs()
            app_config = next((app for app in app_configs if app.name == app_name), None)
            
            if not app_config:
                self.logger.error(f"App config not found for {app_name}")
                return False
            
            # Start the app
            return await self.start_app(app_config)
            
        except Exception as e:
            self.logger.error(f"Error restarting app {app_name}: {e}")
            return False
    
    async def _handle_process_death(self, app_name: str):
        """Handle the death of a managed process."""
        try:
            self.logger.warning(f"Handling process death for {app_name}")
            
            # Remove from managed apps
            if app_name in self.managed_apps:
                del self.managed_apps[app_name]
            
            # Get app config to check if we should restart
            app_configs = self.config_manager.get_app_configs()
            app_config = next((app for app in app_configs if app.name == app_name), None)
            
            if app_config and app_config.restart_on_failure:
                self.logger.info(f"Attempting to restart {app_name}")
                await self.restart_app(app_name)
            else:
                self.logger.info(f"Not restarting {app_name} (restart_on_failure=False)")
                
        except Exception as e:
            self.logger.error(f"Error handling process death for {app_name}: {e}")
    
    def _is_issue_known(self, issue: Issue) -> bool:
        """Check if an issue is already known."""
        return any(
            existing.issue_id == issue.issue_id or
            (existing.app_name == issue.app_name and 
             existing.issue_type == issue.issue_type and
             existing.description == issue.description)
            for existing in self.detected_issues
        )
    
    async def _report_issue_to_master(self, issue: Issue):
        """Report an issue to the master agent."""
        try:
            request = agent_pb2.IssueNotification(
                worker_id=self.worker_id,
                app_name=issue.app_name,
                issue_type=issue.issue_type.value,
                description=issue.description,
                confidence_score=issue.confidence_score,
                logs=issue.logs,
                context={str(k): str(v) for k, v in issue.context.items()},
                timestamp=int(issue.timestamp)
            )
            await self.stub.NotifyIssue(request)
            self.logger.info(f"Reported issue to master: {issue.issue_type.value} - {issue.description}")
        except Exception as e:
            self.logger.error(f"Error reporting issue to master: {e}")
    
    def get_status(self) -> Dict:
        """Get current status of the worker agent."""
        return {
            "worker_id": self.worker_id,
            "running": self.running,
            "managed_apps": len(self.managed_apps),
            "active_tasks": len(self.active_tasks),
            "detected_issues": len(self.detected_issues),
            "last_heartbeat": self.last_heartbeat,
            "apps": [
                {
                    "name": app_name,
                    "pid": info.pid,
                    "status": info.status.value,
                    "cpu_percent": info.cpu_percent,
                    "memory_percent": info.memory_percent,
                    "port": info.port
                }
                for app_name, info in self.managed_apps.items()
            ]
        } 

# if __name__ == "__main__":
#     import argparse
#     import asyncio
#     parser = argparse.ArgumentParser(description="Start a Worker Agent")
#     parser.add_argument('--worker_id', type=str, default='worker-001', help='Worker ID')
#     parser.add_argument('--config', type=str, default='agent.config.yaml', help='Config file path')
#     args = parser.parse_args()
#     print(f"[WorkerAgent] Starting worker agent with ID {args.worker_id}...")
#     try:
#         agent = WorkerAgent(worker_id=args.worker_id, config_path=args.config)
#         asyncio.run(agent.start())
#     except Exception as e:
#         print(f"[WorkerAgent] Exception: {e}")
#         import traceback
#         traceback.print_exc() 
