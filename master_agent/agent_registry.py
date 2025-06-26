import time
from typing import Dict, List, Set, Optional
from shared.models import AgentStatus


class AgentRegistry:
    """Registry for tracking connected worker agents."""
    
    def __init__(self):
        self.workers: Set[str] = set()
        self.worker_heartbeats: Dict[str, float] = {}
        self.worker_status: Dict[str, AgentStatus] = {}
        self.worker_apps: Dict[str, List[str]] = {}  # worker_id -> list of app names
        self.worker_load: Dict[str, int] = {}  # worker_id -> number of active tasks
    
    def register_worker(self, worker_id: str, apps: Optional[List[str]] = None):
        """Register a new worker agent."""
        self.workers.add(worker_id)
        self.worker_heartbeats[worker_id] = time.time()
        self.worker_status[worker_id] = AgentStatus.HEALTHY
        self.worker_apps[worker_id] = apps or []
        self.worker_load[worker_id] = 0
        
        print(f"Registered worker: {worker_id}")
    
    def remove_worker(self, worker_id: str):
        """Remove a worker agent from the registry."""
        self.workers.discard(worker_id)
        self.worker_heartbeats.pop(worker_id, None)
        self.worker_status.pop(worker_id, None)
        self.worker_apps.pop(worker_id, None)
        self.worker_load.pop(worker_id, None)
        
        print(f"Removed worker: {worker_id}")
    
    def update_heartbeat(self, worker_id: str):
        """Update the heartbeat timestamp for a worker."""
        if worker_id in self.workers:
            self.worker_heartbeats[worker_id] = time.time()
    
    def update_status(self, worker_id: str, status: AgentStatus):
        """Update the status of a worker."""
        if worker_id in self.workers:
            self.worker_status[worker_id] = status
    
    def is_worker_healthy(self, worker_id: str) -> bool:
        """Check if a worker is healthy based on heartbeat and status."""
        if worker_id not in self.workers:
            return False
        
        # Check if worker has recent heartbeat
        last_heartbeat = self.worker_heartbeats.get(worker_id, 0)
        if time.time() - last_heartbeat > 60:  # 60 seconds timeout
            return False
        
        # Check worker status
        status = self.worker_status.get(worker_id)
        return status == AgentStatus.HEALTHY
    
    def get_healthy_workers(self) -> List[str]:
        """Get list of healthy workers."""
        return [worker_id for worker_id in self.workers if self.is_worker_healthy(worker_id)]
    
    def get_worker_load(self, worker_id: str) -> int:
        """Get the current load (number of active tasks) for a worker."""
        return self.worker_load.get(worker_id, 0)
    
    def increment_worker_load(self, worker_id: str):
        """Increment the load for a worker."""
        if worker_id in self.worker_load:
            self.worker_load[worker_id] += 1
    
    def decrement_worker_load(self, worker_id: str):
        """Decrement the load for a worker."""
        if worker_id in self.worker_load:
            self.worker_load[worker_id] = max(0, self.worker_load[worker_id] - 1)
    
    def get_least_loaded_worker(self) -> Optional[str]:
        """Get the worker with the least load."""
        if not self.workers:
            return None
        
        healthy_workers = self.get_healthy_workers()
        if not healthy_workers:
            return None
        
        return min(healthy_workers, key=lambda w: self.get_worker_load(w))
    
    def get_worker_info(self, worker_id: str) -> Optional[Dict]:
        """Get detailed information about a worker."""
        if worker_id not in self.workers:
            return None
        
        return {
            "worker_id": worker_id,
            "status": self.worker_status.get(worker_id, AgentStatus.UNHEALTHY).value,
            "last_heartbeat": self.worker_heartbeats.get(worker_id, 0),
            "apps": self.worker_apps.get(worker_id, []),
            "load": self.get_worker_load(worker_id),
            "healthy": self.is_worker_healthy(worker_id)
        }
    
    def get_all_workers_info(self) -> Dict[str, Optional[Dict]]:
        """Get information about all workers."""
        return {
            worker_id: self.get_worker_info(worker_id)
            for worker_id in self.workers
        }
    
    def get_workers_by_app(self, app_name: str) -> List[str]:
        """Get workers that can handle a specific app."""
        return [
            worker_id for worker_id in self.workers
            if app_name in self.worker_apps.get(worker_id, [])
        ]
    
    def cleanup_stale_workers(self, timeout_seconds: int = 60):
        """Remove workers that haven't sent heartbeats recently."""
        current_time = time.time()
        stale_workers = []
        
        for worker_id, last_heartbeat in self.worker_heartbeats.items():
            if current_time - last_heartbeat > timeout_seconds:
                stale_workers.append(worker_id)
        
        for worker_id in stale_workers:
            self.remove_worker(worker_id)
        
        return stale_workers 