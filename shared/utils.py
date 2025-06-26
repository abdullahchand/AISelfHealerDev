import psutil
import socket
import subprocess
import os
import time
import uuid
import logging
from typing import List, Dict, Optional, Tuple
from pathlib import Path


def generate_id() -> str:
    """Generate a unique ID for agents, tasks, etc."""
    return str(uuid.uuid4())


def is_port_available(port: int, host: str = "localhost") -> bool:
    """Check if a port is available."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            result = s.connect_ex((host, port))
            return result != 0
    except Exception:
        return False


def find_available_port(start_port: int = 3000, end_port: int = 9000) -> Optional[int]:
    """Find an available port in the given range."""
    for port in range(start_port, end_port + 1):
        if is_port_available(port):
            return port
    return None


def get_process_info(pid: int) -> Optional[Dict]:
    """Get detailed information about a process."""
    try:
        process = psutil.Process(pid)
        return {
            "pid": pid,
            "name": process.name(),
            "status": process.status(),
            "cpu_percent": process.cpu_percent(),
            "memory_percent": process.memory_percent(),
            "memory_info": process.memory_info()._asdict(),
            "create_time": process.create_time(),
            "cmdline": process.cmdline(),
            "cwd": process.cwd(),
            "connections": [conn._asdict() for conn in process.connections()]
        }
    except psutil.NoSuchProcess:
        return None
    except Exception as e:
        logging.error(f"Error getting process info for PID {pid}: {e}")
        return None


def kill_process(pid: int, force: bool = False) -> bool:
    """Kill a process by PID."""
    try:
        process = psutil.Process(pid)
        if force:
            process.kill()
        else:
            process.terminate()
        
        # Wait for process to terminate
        try:
            process.wait(timeout=10)
        except psutil.TimeoutExpired:
            process.kill()
        
        return True
    except psutil.NoSuchProcess:
        return True  # Process already dead
    except Exception as e:
        logging.error(f"Error killing process {pid}: {e}")
        return False


def start_process(command: str, working_dir: Optional[str] = None, 
                 env_vars: Optional[Dict[str, str]] = None) -> Optional[subprocess.Popen]:
    """Start a new process."""
    try:
        # Prepare environment
        env = os.environ.copy()
        if env_vars:
            env.update(env_vars)
        
        # Start process
        process = subprocess.Popen(
            command,
            shell=True,
            cwd=working_dir,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        
        return process
    except Exception as e:
        logging.error(f"Error starting process '{command}': {e}")
        return None


def get_system_resources() -> Dict[str, float]:
    """Get current system resource usage."""
    try:
        cpu_percent = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "memory_available": memory.available,
            "memory_total": memory.total,
            "disk_percent": disk.percent,
            "disk_free": disk.free,
            "disk_total": disk.total
        }
    except Exception as e:
        logging.error(f"Error getting system resources: {e}")
        return {}


def parse_logs_for_errors(logs: List[str]) -> List[Dict]:
    """Parse logs to identify potential errors and issues."""
    errors = []
    error_patterns = [
        r"error|Error|ERROR",
        r"exception|Exception|EXCEPTION",
        r"failed|Failed|FAILED",
        r"timeout|Timeout|TIMEOUT",
        r"connection refused|Connection refused",
        r"port.*in use|Port.*in use",
        r"permission denied|Permission denied",
        r"file not found|File not found",
        r"module not found|Module not found"
    ]
    
    import re
    for i, log_line in enumerate(logs):
        for pattern in error_patterns:
            if re.search(pattern, log_line):
                errors.append({
                    "line_number": i,
                    "log_line": log_line,
                    "pattern": pattern,
                    "severity": "high" if "error" in pattern.lower() else "medium"
                })
                break
    
    return errors


def setup_logging(level: str = "INFO", log_file: Optional[str] = None) -> logging.Logger:
    """Setup logging configuration."""
    logger = logging.getLogger("ai_runtime")
    logger.setLevel(getattr(logging, level.upper()))
    
    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # File handler (optional)
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    
    return logger


def health_check_url(url: str, timeout: int = 5) -> bool:
    """Perform a health check on a URL."""
    try:
        import requests
        response = requests.get(url, timeout=timeout)
        return 200 <= response.status_code < 400
    except Exception:
        return False


def health_check_port(port: int, host: str = "localhost", timeout: int = 5) -> bool:
    """Perform a health check on a port."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            result = s.connect_ex((host, port))
            return result == 0
    except Exception:
        return False


def wait_for_condition(condition_func, timeout: int = 60, interval: float = 1.0) -> bool:
    """Wait for a condition to be true."""
    start_time = time.time()
    while time.time() - start_time < timeout:
        if condition_func():
            return True
        time.sleep(interval)
    return False


def create_data_directory(data_dir: str = "./data") -> Path:
    """Create data directory if it doesn't exist."""
    data_path = Path(data_dir)
    data_path.mkdir(parents=True, exist_ok=True)
    return data_path 