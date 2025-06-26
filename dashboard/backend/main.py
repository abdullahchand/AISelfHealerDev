import os
from dotenv import load_dotenv
load_dotenv()
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from typing import List, Dict
import asyncio
import sys
import subprocess
import uuid
import threading
import httpx
import requests
import time

# Add project root to path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '../../')))

from master_agent.master import MasterAgent
from shared.config import ConfigManager
from shared.utils import setup_logging

app = FastAPI()

# Allow CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize master agent (singleton for dashboard)
config_manager = ConfigManager()
master_agent = MasterAgent()
logger = setup_logging()

# Proxy endpoints to master agent HTTP API
MASTER_API = "http://localhost:9000/api/master"

@app.get("/api/workers")
async def get_workers():
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{MASTER_API}/workers")
        return resp.json()

@app.get("/api/worker/{worker_id}")
async def get_worker_detail(worker_id: str):
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{MASTER_API}/workers")
        workers = resp.json().get("workers", [])
        worker = next((w for w in workers if w == worker_id), None)
        # For demo, just return worker_id; you can expand this to fetch more details
        return {"worker": {"worker_id": worker_id}, "llm_output": None, "issues": []}

@app.get("/api/issues")
async def get_issues():
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{MASTER_API}/issues")
        return resp.json()

@app.get("/api/tasks")
async def get_tasks():
    async with httpx.AsyncClient() as client:
        resp = await client.get(f"{MASTER_API}/tasks")
        return resp.json()

# Track running workers (shell subprocesses)
workers: Dict[str, subprocess.Popen] = {}
worker_queues: Dict[str, asyncio.Queue] = {}
# Track user processes per worker
user_processes: Dict[str, List[dict]] = {}  # worker_id -> list of {pid, command, status, output}
# Track current working directory for each worker
worker_cwds: Dict[str, str] = {}

# Helper to start and track a user process
async def start_user_process(worker_id: str, command: str, on_output, cwd=None):
    proc = subprocess.Popen(
        command,
        shell=True,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        cwd=cwd or worker_cwds.get(worker_id, None)
    )
    info = {
        'pid': proc.pid,
        'command': command,
        'status': 'running',
        'output': []
    }
    if worker_id not in user_processes:
        user_processes[worker_id] = []
    user_processes[worker_id].append(info)

    def read_output():
        for line in proc.stdout:
            print(f"[WORKER OUTPUT] {command} (PID {proc.pid}): {line.strip()}")
            info['output'].append(line)
            on_output(line)
            print("Worker: ", line)
            # Simple error detection
            if any(word in line.lower() for word in ['error', 'exception', 'fail', 'traceback', 'errno']):
                info['status'] = 'issue'
                # Report issue to master
                print("Reporting issue to master...")
                report_issue_to_master(worker_id, line.strip(), info['output'][-10:])
        info['status'] = 'exited'

    threading.Thread(target=read_output, daemon=True).start()
    return proc

@app.on_event("startup")
async def startup_event():
    # Start the master agent in the background (if not already running)
    asyncio.create_task(master_agent.start())

@app.post("/api/workers")
async def create_worker(request: Request):
    data = await request.json()
    worker_id = data.get("worker_id") or f"worker-{uuid.uuid4().hex[:8]}"
    if worker_id in workers:
        return JSONResponse({"error": "Worker already exists"}, status_code=400)
    # Start a shell subprocess
    proc = subprocess.Popen(
        ["/bin/bash"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1
    )
    workers[worker_id] = proc
    worker_queues[worker_id] = asyncio.Queue()
    return {"worker_id": worker_id}

@app.get("/api/worker/{worker_id}/processes")
async def get_worker_processes(worker_id: str):
    """Return the list of user processes and their statuses for this worker."""
    procs = user_processes.get(worker_id, [])
    # Only return summary info for each process
    return {
        "worker_id": worker_id,
        "processes": [
            {
                "pid": p["pid"],
                "command": p["command"],
                "status": p["status"],
                "output_tail": p["output"][-10:]  # last 10 lines
            }
            for p in procs
        ]
    }

async def poll_for_commands(worker_id, stdin, websocket):
    import httpx
    while True:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"http://localhost:9000/api/worker/{worker_id}/next_command")
                data = resp.json()
                if data.get("status") != "no_command":
                    cmd = data.get("command") or data.get("action")
                    if cmd:
                        await websocket.send_text(f"[MASTER COMMAND] Executing: {cmd}\n")
                        stdin.write(cmd + "\n")
                        stdin.flush()
        except Exception as e:
            await websocket.send_text(f"[MASTER COMMAND] Poll error: {e}\n")
        await asyncio.sleep(3)

@app.websocket("/ws/worker/{worker_id}/terminal")
async def worker_terminal(websocket: WebSocket, worker_id: str):
    await websocket.accept()
    if worker_id not in workers:
        await websocket.send_text("Worker not found.")
        await websocket.close()
        return  # Do not raise after closing, just return
    proc = workers[worker_id]
    queue = worker_queues[worker_id]

    if proc.stdout is None or proc.stdin is None:
        await websocket.send_text("Worker process missing stdin/stdout.")
        await websocket.close()
        return  # Do not raise after closing, just return
    stdout = proc.stdout  # type: ignore
    stdin = proc.stdin    # type: ignore

    # Track current working directory for this worker
    if worker_id not in worker_cwds:
        worker_cwds[worker_id] = os.getcwd()

    # Queue for thread-safe output from user processes
    output_queue = asyncio.Queue()

    async def read_stdout():
        while True:
            line = await asyncio.get_event_loop().run_in_executor(None, stdout.readline)
            if not line:
                break
            await websocket.send_text(line)

    async def send_user_process_output():
        while True:
            line = await output_queue.get()
            await websocket.send_text(line)

    async def write_stdin():
        while True:
            cmd = await queue.get()
            if proc.poll() is not None:
                break
            # Handle 'cd' command to update working directory
            if cmd.strip().startswith('cd '):
                path = cmd.strip()[3:].strip()
                if path == '':
                    worker_cwds[worker_id] = os.path.expanduser('~')
                else:
                    new_path = os.path.abspath(os.path.join(worker_cwds[worker_id], path))
                    if os.path.isdir(new_path):
                        worker_cwds[worker_id] = new_path
                        await websocket.send_text(f"Changed directory to {worker_cwds[worker_id]}\n")
                    else:
                        await websocket.send_text(f"cd: no such directory: {path}\n")
                continue
            stdin.write(cmd + "\n")
            stdin.flush()
            # If user is starting a new process, track it
            if cmd.strip() and not cmd.strip().startswith('cd'):
                # Only track if it's not a shell builtin like 'cd'
                await start_user_process(worker_id, cmd, lambda line: output_queue.put_nowait(line), cwd=worker_cwds[worker_id])

    read_task = asyncio.create_task(read_stdout())
    write_task = asyncio.create_task(write_stdin())
    user_output_task = asyncio.create_task(send_user_process_output())
    poll_task = asyncio.create_task(poll_for_commands(worker_id, stdin, websocket))
    try:
        while True:
            data = await websocket.receive_text()
            await queue.put(data)
    except WebSocketDisconnect:
        pass
    finally:
        read_task.cancel()
        write_task.cancel()
        user_output_task.cancel()
        poll_task.cancel()
        if not websocket.client_state.name == "DISCONNECTED":
            await websocket.close()

# WebSocket for real-time updates
dashboard_clients: List[WebSocket] = []

@app.websocket("/ws/updates")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    dashboard_clients.append(websocket)
    try:
        while True:
            # Send current worker status every 2 seconds
            workers = master_agent.agent_registry.get_all_workers_info()
            await websocket.send_json({"workers": workers})
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        dashboard_clients.remove(websocket)

@app.post("/api/worker/{worker_id}/command")
async def worker_command(worker_id: str, data: dict = Body(...)):
    """Allow the master to send a command to a worker's process."""
    action = data.get("action")
    pid = data.get("pid")
    command = data.get("command")
    print(f"[MASTER->WORKER] Action: {action}, PID: {pid}, Command: {command}")
    result = {"success": False}
    if action == "kill" and pid:
        # Kill the process with the given pid
        for p in user_processes.get(worker_id, []):
            if p["pid"] == pid:
                try:
                    import signal
                    os.kill(pid, signal.SIGKILL)
                    p["status"] = "killed"
                    result = {"success": True, "message": f"Process {pid} killed."}
                except Exception as e:
                    result = {"success": False, "error": str(e)}
                break
    elif action == "restart" and command:
        # Run the command again
        await start_user_process(worker_id, command, lambda line: None)
        result = {"success": True, "message": f"Process restarted: {command}"}
    elif action == "run" and command:
        # Run a new command
        await start_user_process(worker_id, command, lambda line: None)
        result = {"success": True, "message": f"Command started: {command}"}
    else:
        result = {"success": False, "error": "Invalid action or missing parameters."}
    return result

def report_issue_to_master(worker_id, description, logs):
    url = "http://localhost:9000/api/master/report_issue"
    data = {
        "worker_id": worker_id,
        "description": description,
        "logs": logs,
        "timestamp": int(time.time())
    }
    try:
        resp = requests.post(url, json=data)
        print(f"[DASHBOARD SHELL] Reported issue to master: {resp.json()}")
    except Exception as e:
        print(f"[DASHBOARD SHELL] Failed to report issue: {e}") 