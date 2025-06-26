import sqlite3
import json
import time
from typing import Dict, List, Optional
from pathlib import Path

from shared.models import EnvironmentState, ProcessInfo, AgentState
from shared.utils import create_data_directory


class StateManager:
    """Manages persistent state for the master agent."""
    
    def __init__(self, data_dir: str = "./data"):
        self.data_dir = create_data_directory(data_dir)
        self.db_path = self.data_dir / "master_state.db"
        self._init_database()
    
    def _init_database(self):
        """Initialize the SQLite database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create tables
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS environment_state (
                id INTEGER PRIMARY KEY,
                timestamp REAL,
                state_data TEXT
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS process_info (
                app_name TEXT PRIMARY KEY,
                pid INTEGER,
                status TEXT,
                cpu_percent REAL,
                memory_percent REAL,
                port INTEGER,
                start_time REAL,
                last_heartbeat REAL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS port_allocations (
                app_name TEXT PRIMARY KEY,
                port INTEGER,
                allocated_at REAL
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS agent_heartbeats (
                agent_id TEXT PRIMARY KEY,
                last_heartbeat REAL,
                status TEXT
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def save_environment_state(self, state: EnvironmentState):
        """Save environment state to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        state_data = json.dumps(state.dict())
        cursor.execute('''
            INSERT OR REPLACE INTO environment_state (id, timestamp, state_data)
            VALUES (1, ?, ?)
        ''', (time.time(), state_data))
        
        conn.commit()
        conn.close()
    
    def load_environment_state(self) -> EnvironmentState:
        """Load environment state from database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT state_data FROM environment_state WHERE id = 1')
        result = cursor.fetchone()
        
        conn.close()
        
        if result:
            state_dict = json.loads(result[0])
            return EnvironmentState(**state_dict)
        else:
            return EnvironmentState()
    
    def save_process_info(self, app_name: str, process_info: ProcessInfo):
        """Save process information to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO process_info 
            (app_name, pid, status, cpu_percent, memory_percent, port, start_time, last_heartbeat)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            app_name,
            process_info.pid,
            process_info.status.value,
            process_info.cpu_percent,
            process_info.memory_percent,
            process_info.port,
            process_info.start_time,
            process_info.last_heartbeat
        ))
        
        conn.commit()
        conn.close()
    
    def get_process_info(self, app_name: str) -> Optional[ProcessInfo]:
        """Get process information from database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT pid, status, cpu_percent, memory_percent, port, start_time, last_heartbeat
            FROM process_info WHERE app_name = ?
        ''', (app_name,))
        
        result = cursor.fetchone()
        conn.close()
        
        if result:
            return ProcessInfo(
                pid=result[0],
                name=app_name,
                status=result[1],
                cpu_percent=result[2],
                memory_percent=result[3],
                port=result[4],
                start_time=result[5],
                last_heartbeat=result[6]
            )
        
        return None
    
    def save_port_allocation(self, app_name: str, port: int):
        """Save port allocation to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO port_allocations (app_name, port, allocated_at)
            VALUES (?, ?, ?)
        ''', (app_name, port, time.time()))
        
        conn.commit()
        conn.close()
    
    def get_port_allocation(self, app_name: str) -> Optional[int]:
        """Get port allocation from database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT port FROM port_allocations WHERE app_name = ?', (app_name,))
        result = cursor.fetchone()
        
        conn.close()
        
        return result[0] if result else None
    
    def save_agent_heartbeat(self, agent_id: str, status: str):
        """Save agent heartbeat to database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT OR REPLACE INTO agent_heartbeats (agent_id, last_heartbeat, status)
            VALUES (?, ?, ?)
        ''', (agent_id, time.time(), status))
        
        conn.commit()
        conn.close()
    
    def get_agent_heartbeat(self, agent_id: str) -> Optional[float]:
        """Get agent heartbeat from database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT last_heartbeat FROM agent_heartbeats WHERE agent_id = ?', (agent_id,))
        result = cursor.fetchone()
        
        conn.close()
        
        return result[0] if result else None
    
    def cleanup_old_data(self, max_age_hours: int = 24):
        """Clean up old data from database."""
        cutoff_time = time.time() - (max_age_hours * 3600)
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Clean up old environment states
        cursor.execute('DELETE FROM environment_state WHERE timestamp < ?', (cutoff_time,))
        
        # Clean up old agent heartbeats
        cursor.execute('DELETE FROM agent_heartbeats WHERE last_heartbeat < ?', (cutoff_time,))
        
        conn.commit()
        conn.close() 