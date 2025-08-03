import asyncio
from dotenv import load_dotenv
load_dotenv()
import grpc
import time
import logging
import json
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor
import sys
import os
import requests
import uvicorn
from master_agent import http_api
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../shared')))
from shared import agent_pb2, agent_pb2_grpc

from shared.models import AgentState, AgentStatus, EnvironmentState, Task, Issue, ActionType, IssueType
from shared.config import ConfigManager
from shared.utils import generate_id, setup_logging, get_system_resources
from master_agent.state_manager import StateManager
from master_agent.agent_registry import AgentRegistry
from shared.llm_analyzer import LLMAnalyzer


class MasterAgent:
    """Master AI Agent - Central coordinator and planner."""
    
    def __init__(self, config_path: str = "agent.config.yaml"):
        self.config_manager = ConfigManager(config_path)
        self.config = self.config_manager.get_master_config()
        
        # Setup logging
        self.logger = setup_logging()
        
        # Initialize components
        self.state_manager = StateManager()
        self.agent_registry = AgentRegistry()
        
        # State
        self.state = AgentState(
            agent_id=self.config.agent_id,
            agent_type="master",
            status=AgentStatus.HEALTHY
        )
        
        # gRPC server
        self.server = None
        self.running = False
        
        # Task queue
        self.task_queue: List[Task] = []
        self.active_tasks: Dict[str, Task] = {}
        
        # Issue tracking
        self.active_issues: List[Issue] = []
        self.resolved_issues: List[Issue] = []
        
        # Initialize LLM analyzer
        self.llm_analyzer = LLMAnalyzer()
        
        self.logger.info(f"Master Agent {self.config.agent_id} initialized with LLM capabilities")
    
    async def start_background_tasks(self):
        """Starts the background tasks of the master agent."""
        if self.running:
            return
        self.logger.info("Starting Master Agent background tasks...")
        
        # Start gRPC server
        asyncio.create_task(self._start_grpc_server())
        
        # Start background tasks
        asyncio.create_task(self._heartbeat_monitor())
        asyncio.create_task(self._task_scheduler())
        asyncio.create_task(self._issue_resolver())
        asyncio.create_task(self._resource_monitor())
        
        self.running = True
        self.logger.info("Master Agent background tasks started successfully.")

    async def start(self):
        """Start the master agent and run forever (blocking)."""
        try:
            # This method is intended to be called when running master.py directly.
            # It starts the background tasks and then starts the blocking HTTP server.
            await self.start_background_tasks()
            await self._start_http_api_server()
            
        except Exception as e:
            self.logger.error(f"Error starting Master Agent: {e}", exc_info=True)
            raise
    
    async def stop(self):
        """Stop the master agent."""
        self.logger.info("Stopping Master Agent...")
        self.running = False
        
        if self.server:
            await self.server.stop(grace=5)
        
        self.logger.info("Master Agent stopped")
    
    async def _start_grpc_server(self):
        """Start the gRPC server."""
        self.logger.info(f"Starting gRPC server on {self.config.host}:{self.config.port}")
        server = grpc.aio.server()
        agent_pb2_grpc.add_AgentServiceServicer_to_server(AgentServiceServicer(self), server)
        server.add_insecure_port(f"{self.config.host}:{self.config.port}")
        self.server = server
        await server.start()
        self.logger.info("gRPC server started")
        await server.wait_for_termination()

    async def _start_http_api_server(self):
        """Start the FastAPI HTTP API server."""
        self.logger.info(f"Starting HTTP API server on {self.config.host}:{9001}")
        http_api.set_master_agent(self)
        config = uvicorn.Config(http_api.app, host=self.config.host, port=9001, log_level="info")
        server = uvicorn.Server(config)
        await server.serve()
    
    async def _heartbeat_monitor(self):
        """Monitor worker heartbeats."""
        while self.running:
            try:
                current_time = time.time()
                
                # Check for stale workers
                stale_workers = []
                for worker_id, last_heartbeat in self.agent_registry.worker_heartbeats.items():
                    if current_time - last_heartbeat > self.config.heartbeat_interval * 2:
                        stale_workers.append(worker_id)
                
                # Remove stale workers
                for worker_id in stale_workers:
                    self.logger.warning(f"Removing stale worker: {worker_id}")
                    self.agent_registry.remove_worker(worker_id)
                
                # Update master heartbeat
                self.state.last_heartbeat = current_time
                
                await asyncio.sleep(self.config.heartbeat_interval)
                
            except Exception as e:
                self.logger.error(f"Error in heartbeat monitor: {e}")
                await asyncio.sleep(5)
    
    async def _task_scheduler(self):
        """Schedule and assign tasks to workers."""
        while self.running:
            try:
                # Process task queue
                if self.task_queue:
                    task = self.task_queue.pop(0)
                    
                    # Find available worker
                    available_worker = self._find_available_worker(task)
                    if available_worker:
                        await self._assign_task_to_worker(task, available_worker)
                    else:
                        # Put task back in queue
                        self.task_queue.insert(0, task)
                        self.logger.warning(f"No available worker for task {task.task_id}")
                
                await asyncio.sleep(1)
                
            except Exception as e:
                self.logger.error(f"Error in task scheduler: {e}")
                await asyncio.sleep(5)
    
    async def _issue_resolver(self):
        """Resolve detected issues."""
        self.logger.info("Issue resolver task started.")
        while self.running:
            try:
                self.logger.info(f"Issue resolver loop running. Found {len(self.active_issues)} active issues.")
                open_issues = [i for i in self.active_issues if i.status == "open"]
                if open_issues:
                    self.logger.info(f"Found {len(open_issues)} open issues to process.")
                    for issue in open_issues[:]:  # Iterate over a copy
                        await self._resolve_issue(issue)
                else:
                    self.logger.info("No open issues to process in this cycle.")
                
                await asyncio.sleep(5)
                
            except Exception as e:
                self.logger.error(f"Error in issue resolver: {e}", exc_info=True)
                await asyncio.sleep(10)
    
    async def _resource_monitor(self):
        """Monitor system resources."""
        while self.running:
            # Get system resources
            resources = get_system_resources()
            self.state.environment_state.system_resources = resources
            
            # Check for resource issues
            if resources.get("cpu_percent", 0) > 80:
                self.logger.warning("High CPU usage detected")
            
            if resources.get("memory_percent", 0) > 85:
                self.logger.warning("High memory usage detected")
            
            await asyncio.sleep(30)
    
    def _find_available_worker(self, task: Task) -> Optional[str]:
        """Find an available worker for a task."""
        available_workers = []
        
        for worker_id in self.agent_registry.workers:
            # Check if worker is healthy
            if self.agent_registry.is_worker_healthy(worker_id):
                # Check if worker can handle this app type
                if self._worker_can_handle_app(worker_id, task.app_name):
                    available_workers.append(worker_id)
        
        # Return worker with least load (simple round-robin for now)
        if available_workers:
            return available_workers[0]
        
        return None
    
    def _worker_can_handle_app(self, worker_id: str, app_name: str) -> bool:
        """Check if a worker can handle a specific app."""
        # TODO: Implement app capability checking
        # For now, assume all workers can handle all apps
        return True
    
    async def _assign_task_to_worker(self, task: Task, worker_id: str):
        """Assign a task to a specific worker using LLM decision making."""
        try:
            # Get available workers for LLM decision
            available_workers = []
            for w_id in self.agent_registry.workers:
                if self.agent_registry.is_worker_healthy(w_id):
                    worker_info = self.agent_registry.get_worker_info(w_id)
                    if worker_info:
                        available_workers.append(worker_info)
            
            # Use LLM to validate or override worker selection
            llm_selected_worker = await self.llm_analyzer.decide_worker_assignment(task, available_workers)
            
            if llm_selected_worker and llm_selected_worker != worker_id:
                self.logger.info(f"LLM overrode worker selection: {worker_id} -> {llm_selected_worker}")
                worker_id = llm_selected_worker
            
            task.worker_id = worker_id
            task.status = "assigned"
            self.active_tasks[task.task_id] = task
            
            self.logger.info(f"Assigned task {task.task_id} to worker {worker_id}")

            # Queue the command for the worker to pick up via HTTP
            if task.action == ActionType.RUN_COMMAND:
                command_to_send = {
                    "command": task.parameters.get("command"),
                    "issue_id": task.issue_id
                }
                if command_to_send["command"]:
                    http_api.queue_command_for_worker(worker_id, command_to_send)
                else:
                    self.logger.error(f"Task {task.task_id} is a RUN_COMMAND task but has no command in parameters.")
            
        except Exception as e:
            self.logger.error(f"Error assigning task {task.task_id} to worker {worker_id}: {e}")
    
    async def _resolve_issue(self, issue: Issue):
        """Resolve a detected issue using LLM analysis in a loop."""
        try:
            issue.status = "in_progress"
            self.logger.info(f"Attempting to resolve issue {issue.issue_id} for app {issue.app_name}")

            # Get worker capabilities
            worker_capabilities = self.agent_registry.get_worker_info(issue.worker_id) or {}
            
            # Get resolution suggestion from LLM
            resolution = await self.llm_analyzer.suggest_resolution(issue, issue.worker_id, worker_capabilities)
            self.logger.info(f"LLM resolution suggestion for issue {issue.issue_id}: {resolution}")

            if resolution.get("is_resolved"):
                issue.resolved = True
                issue.status = "resolved"
                issue.resolution = str(resolution)
                self.resolved_issues.append(issue)
                if issue in self.active_issues:
                    self.active_issues.remove(issue)
                self.logger.info(f"Issue {issue.issue_id} marked as resolved by LLM.")
                return

            if resolution.get("action"):
                # Create a task for tracking, then directly assign it.
                task = Task(
                    task_id=generate_id(),
                    issue_id=issue.issue_id,
                    worker_id=issue.worker_id,
                    action=ActionType.RUN_COMMAND,
                    app_name=issue.app_name,
                    parameters={"command": resolution["action"], "full_resolution": json.dumps(resolution)},
                    priority=1
                )
                # Directly assign the task to dispatch the command immediately.
                await self._assign_task_to_worker(task, issue.worker_id)
                self.logger.info(f"Created and dispatched task {task.task_id} for issue {issue.issue_id} with command: {resolution['action']}")
            else:
                # If no action, mark for manual review and stop iterating
                self.logger.warning(f"No action suggested for issue {issue.issue_id}. Marking for manual review.")
                issue.status = "open" # Or a new "manual_review" status

        except Exception as e:
            self.logger.error(f"Error resolving issue {issue.issue_id}: {e}")
            issue.status = "open"  # Re-open on error to allow retry
    
    async def _resolve_critical_issue(self, issue: Issue, analysis: Dict) -> str:
        """Resolve critical issues immediately."""
        try:
            if issue.issue_type == IssueType.PORT_CONFLICT:
                return await self._resolve_port_conflict(issue)
            elif issue.issue_type == IssueType.PROCESS_CRASH:
                return await self._resolve_process_crash(issue)
            elif issue.issue_type == IssueType.DEPENDENCY_MISSING:
                return await self._resolve_dependency_issue(issue)
            else:
                return f"Critical issue detected but no auto-resolution available: {issue.issue_type.value}"
        except Exception as e:
            self.logger.error(f"Error in critical issue resolution: {e}")
            return f"Failed to resolve critical issue: {e}"
    
    async def _resolve_port_conflict(self, issue: Issue) -> str:
        """Resolve port conflict by reassigning port."""
        # TODO: Implement port conflict resolution
        return f"Port conflict resolved for {issue.app_name}"
    
    async def _resolve_process_crash(self, issue: Issue) -> str:
        """Resolve process crash by restarting."""
        # TODO: Implement process crash resolution
        return f"Process crash resolved for {issue.app_name}"
    
    async def _resolve_dependency_issue(self, issue: Issue) -> str:
        """Resolve dependency issue by installing missing dependencies."""
        # TODO: Implement dependency resolution
        return f"Dependency issue resolved for {issue.app_name}"
    
    def add_task(self, task: Task):
        """Add a task to the queue."""
        self.task_queue.append(task)
        self.logger.info(f"Added task {task.task_id} to queue")
    
    def get_status(self) -> Dict:
        """Get current status of the master agent."""
        return {
            "agent_id": self.state.agent_id,
            "status": self.state.status.value,
            "connected_workers": len(self.agent_registry.workers),
            "active_tasks": len(self.active_tasks),
            "queued_tasks": len(self.task_queue),
            "active_issues": len(self.active_issues),
            "resolved_issues": len(self.resolved_issues),
            "system_resources": self.state.environment_state.system_resources
        }

    async def _handle_worker_issue_notification(self, issue_notification):
        """Handle issue notification from worker using LLM analysis."""
        try:
            # Convert gRPC notification to Issue model
            issue = Issue(
                issue_id=generate_id(),
                worker_id=issue_notification.worker_id,
                app_name=issue_notification.app_name,
                issue_type=IssueType(issue_notification.issue_type),
                description=issue_notification.description,
                confidence_score=issue_notification.confidence_score,
                logs=list(issue_notification.logs),
                context=dict(issue_notification.context),
                timestamp=issue_notification.timestamp
            )
            
            # Add to active issues
            self.active_issues.append(issue)
            
            # Get resolution suggestion from LLM
            worker_capabilities = self.agent_registry.get_worker_info(issue.worker_id) or {}
            resolution = await self.llm_analyzer.suggest_resolution(issue, issue.worker_id, worker_capabilities)
            
            self.logger.info(f"LLM resolution suggestion for issue {issue.issue_id}: {resolution}")
            
            # Create task based on resolution
            if resolution.get("action"):
                task = Task(
                    task_id=generate_id(),
                    issue_id=issue.issue_id,
                    worker_id=issue.worker_id,
                    action=ActionType(resolution["action"]),
                    app_name=issue.app_name,
                    parameters={"resolution": resolution},
                    priority=1
                )
                
                self.add_task(task)
                return f"Created {resolution['action']} task based on LLM analysis"
            
            return "Issue logged for manual review"
            
        except Exception as e:
            self.logger.error(f"Error handling worker issue notification: {e}")
            return "Error processing issue notification"

class AgentServiceServicer(agent_pb2_grpc.AgentServiceServicer):
    def __init__(self, master_agent):
        self.master_agent = master_agent

    async def Heartbeat(self, request, context):
        # Handle heartbeat from worker
        worker_id = request.worker_id
        self.master_agent.agent_registry.update_heartbeat(worker_id)
        return agent_pb2.HeartbeatResponse(acknowledged=True, message="Heartbeat received")

    async def ReportStatus(self, request, context):
        # Handle status report from worker
        return agent_pb2.StatusResponse(received=True, message="Status received")

    async def AssignTask(self, request, context):
        # Not used by master, only for completeness
        return agent_pb2.TaskResponse(accepted=False, message="Not implemented", task_id=request.task_id)

    async def NotifyIssue(self, request, context):
        # Handle issue notification from worker
        result = await self.master_agent._handle_worker_issue_notification(request)
        return agent_pb2.IssueResponse(acknowledged=True, action="auto_fix", message=result)

    async def ExecuteAction(self, request, context):
        # Handle action execution request
        return agent_pb2.ActionResponse(success=True, result="Action executed", error_message="", metadata={})

    async def SyncState(self, request, context):
        # Handle state sync
        return agent_pb2.StateResponse(synced=True, master_state={}, conflicts=[])

if __name__ == "__main__":
    import asyncio
    print("[MasterAgent] Starting master agent...")
    agent = MasterAgent()
    asyncio.run(agent.start())
 
