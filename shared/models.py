from pydantic import BaseModel, Field
from typing import Dict, List, Optional, Any
from enum import Enum
import time


class AgentStatus(str, Enum):
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"


class AppStatus(str, Enum):
    RUNNING = "running"
    STOPPED = "stopped"
    ERROR = "error"
    STARTING = "starting"
    STOPPING = "stopping"


class IssueType(str, Enum):
    PORT_CONFLICT = "port_conflict"
    PROCESS_CRASH = "process_crash"
    DEPENDENCY_MISSING = "dependency_missing"
    TIMEOUT = "timeout"
    MEMORY_LOW = "memory_low"
    CPU_HIGH = "cpu_high"
    CONFIG_ERROR = "config_error"


class ActionType(str, Enum):
    START = "start"
    STOP = "stop"
    RESTART = "restart"
    DIAGNOSE = "diagnose"
    HEAL = "heal"
    CHANGE_PORT = "change_port"
    UPDATE_CONFIG = "update_config"
    INSTALL_DEPENDENCY = "install_dependency"
    RUN_COMMAND = "run_command"


class AgentConfig(BaseModel):
    agent_id: str
    agent_type: str  # "master" or "worker"
    host: str = "localhost"
    port: int = 50051
    heartbeat_interval: int = 30  # seconds
    max_retries: int = 3
    timeout: int = 60  # seconds


class AppConfig(BaseModel):
    name: str
    command: str
    working_dir: Optional[str] = None
    port: Optional[int] = None
    env_vars: Dict[str, str] = Field(default_factory=dict)
    dependencies: List[str] = Field(default_factory=list)
    health_check_url: Optional[str] = None
    health_check_interval: int = 30  # seconds
    restart_on_failure: bool = True
    max_restarts: int = 3


class ProcessInfo(BaseModel):
    pid: int
    name: str
    status: AppStatus
    cpu_percent: float = 0.0
    memory_percent: float = 0.0
    port: Optional[int] = None
    start_time: float = Field(default_factory=time.time)
    last_heartbeat: float = Field(default_factory=time.time)


class Issue(BaseModel):
    issue_id: str
    worker_id: str
    app_name: str
    issue_type: IssueType
    description: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    logs: List[str] = Field(default_factory=list)
    context: Dict[str, Any] = Field(default_factory=dict)
    timestamp: float = Field(default_factory=time.time)
    resolved: bool = False
    resolution: Optional[str] = None
    status: str = "open"  # "open", "in_progress", "resolved"


class Task(BaseModel):
    task_id: str
    issue_id: Optional[str] = None
    worker_id: str
    action: ActionType
    app_name: str
    parameters: Dict[str, str] = Field(default_factory=dict)
    priority: int = Field(default=1, ge=1, le=10)
    created_at: float = Field(default_factory=time.time)
    completed_at: Optional[float] = None
    status: str = "pending"  # "pending", "running", "completed", "failed"
    result: Optional[str] = None


class EnvironmentState(BaseModel):
    active_apps: Dict[str, ProcessInfo] = Field(default_factory=dict)
    port_allocations: Dict[str, int] = Field(default_factory=dict)
    available_ports: List[int] = Field(default_factory=list)
    system_resources: Dict[str, float] = Field(default_factory=dict)
    last_updated: float = Field(default_factory=time.time)


class AgentState(BaseModel):
    agent_id: str
    agent_type: str
    status: AgentStatus
    connected_workers: List[str] = Field(default_factory=list)
    environment_state: EnvironmentState = Field(default_factory=EnvironmentState)
    active_tasks: Dict[str, Task] = Field(default_factory=dict)
    resolved_issues: List[Issue] = Field(default_factory=list)
    last_heartbeat: float = Field(default_factory=time.time) 
