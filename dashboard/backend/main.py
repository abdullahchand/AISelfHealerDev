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

from shared.config import ConfigManager
from shared.utils import setup_logging

app = FastAPI()

# Allow CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Initialize master agent (singleton for dashboard)
config_manager = ConfigManager()
logger = setup_logging()

# Proxy endpoints to master agent HTTP API
MASTER_API = "http://localhost:9001/api/master"

@app.get("/api/workers")
async def get_workers():
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.get(f"{MASTER_API}/workers")
            resp.raise_for_status()  # Raise an exception for bad status codes (4xx or 5xx)
            return resp.json()
        except (httpx.RequestError, httpx.HTTPStatusError) as e:
            logger.error(f"Failed to connect to or get a valid response from master agent at {MASTER_API}: {e}")
            return JSONResponse(
                status_code=503, 
                content={"error": "Master agent is unavailable or returned an error."}
            )

@app.get("/api/worker/{worker_id}")
async def get_worker_detail(worker_id: str):
    async with httpx.AsyncClient() as client:
        try:
            # First, get all workers to find the one we want
            resp = await client.get(f"{MASTER_API}/workers")
            resp.raise_for_status()
            workers = resp.json().get("workers", [])
            
            # Find the specific worker
            worker_info = next((w for w in workers if w.get("worker_id") == worker_id), None)
            
            if not worker_info:
                return JSONResponse(status_code=404, content={"error": "Worker not found"})

            # For the demo, we combine info from a few sources
            # In a real app, you might have a dedicated endpoint like /api/master/worker/{worker_id}
            issues_resp = await client.get(f"{MASTER_API}/issues")
            issues_resp.raise_for_status()
            all_issues = issues_resp.json().get("issues", [])
            
            # Filter issues for this worker
            worker_issues = [i for i in all_issues if i.get("worker_id") == worker_id]

            # Placeholder for LLM output
            llm_output = "No specific LLM output for this worker yet."
            if worker_issues:
                llm_output = f"Found {len(worker_issues)} issues. Last issue: {worker_issues[-1].get('description')}"

            return {
                "worker": worker_info,
                "llm_output": llm_output,
                "issues": worker_issues
            }
        except httpx.RequestError as e:
            logger.error(f"Failed to get worker details from master: {e}")
            return JSONResponse(status_code=503, content={"error": "Master agent is unavailable"})

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
            if any(word in line.lower() for word in ['error', 'exception', 'fail', 'traceback', 'errno', 'port']):
                info['status'] = 'issue'
                # Report issue to master
                print("Reporting issue to master...")
                report_issue_to_master(worker_id, line.strip(), info['output'][-10:])
        info['status'] = 'exited'

    threading.Thread(target=read_output, daemon=True).start()
    return proc



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

async def execute_and_report_back(worker_id: str, issue_id: str, command: str, websocket: WebSocket):
    """Executes a command from the master, captures output, and reports back."""
    try:
        # Execute the command in a separate shell
        proc = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=worker_cwds.get(worker_id, os.getcwd()) # Use worker's CWD or default
        )

        stdout, stderr = await proc.communicate()
        output_lines = []

        if stdout:
            decoded_stdout = stdout.decode(errors='ignore').strip()
            output_lines.extend(decoded_stdout.splitlines())
            await websocket.send_text(f"\n[COMMAND OUTPUT]\n{decoded_stdout}\n")
        if stderr:
            decoded_stderr = stderr.decode(errors='ignore').strip()
            output_lines.extend(decoded_stderr.splitlines())
            await websocket.send_text(f"\n[COMMAND ERROR]\n{decoded_stderr}\n")

        # Report the output back to the master
        url = f"{MASTER_API}/issue/{issue_id}/update"
        update_data = {"logs": output_lines or ["Command executed with no output."]}
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=update_data)
            if resp.status_code == 200:
                await websocket.send_text(f"[INFO] Command output reported back to master for issue {issue_id}.\n")
            else:
                await websocket.send_text(f"[ERROR] Failed to report command output to master: {resp.text}\n")

    except Exception as e:
        error_message = f"Failed to execute command '{command}': {e}"
        await websocket.send_text(f"\n[ERROR] {error_message}\n")
        # Report the execution error back to the master
        url = f"{MASTER_API}/issue/{issue_id}/update"
        update_data = {"logs": [error_message]}
        async with httpx.AsyncClient() as client:
            await client.post(url, json=update_data)

async def poll_for_commands(worker_id, stdin, websocket):
    while True:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(f"http://localhost:9001/api/worker/{worker_id}/next_command")
                data = resp.json()
                if data.get("status") != "no_command":
                    cmd = data.get("command")
                    issue_id = data.get("issue_id")
                    if cmd and issue_id:
                        await websocket.send_text(f"\n[MASTER COMMAND] Executing: {cmd}\n")
                        # Execute in a separate process and report back
                        asyncio.create_task(execute_and_report_back(worker_id, issue_id, cmd, websocket))
        except Exception as e:
            await websocket.send_text(f"\n[MASTER COMMAND] Poll error: {e}\n")
        await asyncio.sleep(3)

@app.websocket("/ws/worker/{worker_id}/terminal")
async def worker_terminal(websocket: WebSocket, worker_id: str):
    try:
        await websocket.accept()
    except Exception as e:
        logger.error(f"WebSocket accept failed for worker {worker_id}: {e}")
        return

    if worker_id not in workers:
        logger.warning(f"WebSocket connection for unknown worker {worker_id}")
        await websocket.send_text("Worker not found.")
        await websocket.close(code=1011)
        return

    proc = workers[worker_id]
    queue = worker_queues[worker_id]

    if proc.stdout is None or proc.stdin is None:
        logger.error(f"Worker process {worker_id} missing stdin/stdout.")
        await websocket.send_text("Worker process is not available for interaction.")
        await websocket.close(code=1011)
        return

    # Initialize CWD for the worker
    if worker_id not in worker_cwds:
        worker_cwds[worker_id] = os.getcwd()

    output_queue = asyncio.Queue()

    async def read_stdout():
        # This function reads from the subprocess's stdout
        # and sends it to the WebSocket client.
        loop = asyncio.get_event_loop()
        try:
            while proc.poll() is None:
                line = await loop.run_in_executor(None, proc.stdout.readline)
                if not line:
                    break
                await websocket.send_text(line)
        except Exception as e:
            logger.error(f"Error reading stdout from worker {worker_id}: {e}")
        finally:
            logger.info(f"Stdout reader for {worker_id} finished.")

    async def read_user_process_output():
        # This function reads output from any user-started processes
        # and sends it to the WebSocket client.
        try:
            while True:
                line = await output_queue.get()
                await websocket.send_text(line)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error sending user process output for worker {worker_id}: {e}")

    async def write_stdin():
        # This function takes commands from the WebSocket client (via a queue)
        # and writes them to the subprocess's stdin.
        try:
            while proc.poll() is None:
                cmd = await queue.get()
                
                if cmd.strip().startswith('cd '):
                    path = cmd.strip()[3:].strip()
                    new_path = os.path.abspath(os.path.join(worker_cwds[worker_id], path))
                    if os.path.isdir(new_path):
                        worker_cwds[worker_id] = new_path
                        await websocket.send_text(f"Changed directory to {worker_cwds[worker_id]}\n")
                    else:
                        await websocket.send_text(f"cd: no such directory: {path}\n")
                    continue

                proc.stdin.write(cmd + "\n")
                proc.stdin.flush()

                if cmd.strip() and not cmd.strip().startswith('cd'):
                    # This is a user-initiated command, so we track it.
                    await start_user_process(
                        worker_id, 
                        cmd, 
                        lambda line: output_queue.put_nowait(line), 
                        cwd=worker_cwds[worker_id]
                    )
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Error writing to stdin for worker {worker_id}: {e}")

    # Start all the async tasks
    read_task = asyncio.create_task(read_stdout())
    write_task = asyncio.create_task(write_stdin())
    user_output_task = asyncio.create_task(read_user_process_output())
    poll_task = asyncio.create_task(poll_for_commands(worker_id, proc.stdin, websocket))

    try:
        # Main loop to receive commands from the client
        while True:
            data = await websocket.receive_text()
            await queue.put(data)
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for worker {worker_id}")
    except Exception as e:
        logger.error(f"An error occurred in the worker terminal for {worker_id}: {e}")
    finally:
        # Clean up all tasks
        for task in [read_task, write_task, user_output_task, poll_task]:
            task.cancel()
        
        if websocket.client_state.name != "DISCONNECTED":
            await websocket.close()
        
        logger.info(f"Terminal session for worker {worker_id} ended.")

# WebSocket for real-time updates
dashboard_clients: List[WebSocket] = []

@app.websocket("/ws/updates")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    dashboard_clients.append(websocket)
    try:
        while True:
            # Send current worker status every 2 seconds
            workers = await get_workers()
            await websocket.send_json(workers)
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
    url = f"{MASTER_API}/report_issue"
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