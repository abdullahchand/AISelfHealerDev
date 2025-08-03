import yaml
import os
from typing import Dict, List, Optional
from pathlib import Path
from shared.models import AgentConfig, AppConfig


class ConfigManager:
    """Manages configuration for the AI runtime environment."""
    
    def __init__(self, config_path: str = "agent.config.yaml"):
        self.config_path = Path(config_path)
        self.config = self._load_config()
    
    def _load_config(self) -> Dict:
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            return self._get_default_config()
        
        try:
            with open(self.config_path, 'r') as f:
                return yaml.safe_load(f)
        except Exception as e:
            print(f"Warning: Could not load config from {self.config_path}: {e}")
            return self._get_default_config()
    
    def _get_default_config(self) -> Dict:
        """Get default configuration."""
        return {
            "master": {
                "agent_id": "master-001",
                "host": "localhost",
                "port": 50051,
                "heartbeat_interval": 30,
                "max_retries": 3,
                "timeout": 60
            },
            "workers": [],
            "apps": [],
            "system": {
                "port_range": [3000, 9000],
                "max_concurrent_apps": 10,
                "log_level": "INFO",
                "data_dir": "./data"
            }
        }
    
    def get_master_config(self) -> AgentConfig:
        """Get master agent configuration."""
        master_config = self.config.get("master", {})
        return AgentConfig(
            agent_id=master_config.get("agent_id", "master-001"),
            agent_type="master",
            host=master_config.get("host", "localhost"),
            port=master_config.get("port", 50051),
            heartbeat_interval=master_config.get("heartbeat_interval", 30),
            max_retries=master_config.get("max_retries", 3),
            timeout=master_config.get("timeout", 60)
        )
    
    def get_worker_configs(self) -> List[AgentConfig]:
        """Get worker agent configurations."""
        workers = []
        for worker_config in self.config.get("workers", []):
            workers.append(AgentConfig(
                agent_id=worker_config.get("agent_id"),
                agent_type="worker",
                host=worker_config.get("host", "localhost"),
                port=worker_config.get("port", 50052),
                heartbeat_interval=worker_config.get("heartbeat_interval", 30),
                max_retries=worker_config.get("max_retries", 3),
                timeout=worker_config.get("timeout", 60)
            ))
        return workers
    
    def get_app_configs(self) -> List[AppConfig]:
        """Get application configurations."""
        apps = []
        for app_config in self.config.get("apps", []):
            apps.append(AppConfig(
                name=app_config.get("name"),
                command=app_config.get("command"),
                working_dir=app_config.get("working_dir"),
                port=app_config.get("port"),
                env_vars=app_config.get("env_vars", {}),
                dependencies=app_config.get("dependencies", []),
                health_check_url=app_config.get("health_check_url"),
                health_check_interval=app_config.get("health_check_interval", 30),
                restart_on_failure=app_config.get("restart_on_failure", True),
                max_restarts=app_config.get("max_restarts", 3)
            ))
        return apps
    
    def get_system_config(self) -> Dict:
        """Get system configuration."""
        return self.config.get("system", {})
    
    def save_config(self):
        """Save current configuration to file."""
        try:
            with open(self.config_path, 'w') as f:
                yaml.dump(self.config, f, default_flow_style=False)
        except Exception as e:
            print(f"Error saving config: {e}")
    
    def add_app(self, app_config: AppConfig):
        """Add a new application configuration."""
        app_dict = app_config.dict()
        self.config.setdefault("apps", []).append(app_dict)
        self.save_config()
    
    def remove_app(self, app_name: str):
        """Remove an application configuration."""
        apps = self.config.get("apps", [])
        self.config["apps"] = [app for app in apps if app.get("name") != app_name]
        self.save_config() 
