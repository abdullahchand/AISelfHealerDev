from __future__ import annotations
from typing import TYPE_CHECKING, List
from fastapi import FastAPI, Request, HTTPException
from shared.llm_analyzer import LLMAnalyzer
from shared.models import Issue, IssueType
from shared.utils import generate_id
import asyncio
import time

from master_agent.master import MasterAgent

app = FastAPI()
master_agent_instance: "MasterAgent" = MasterAgent()

@app.on_event("startup")
async def startup_event():
    """Start the master agent's background tasks when the API server starts."""
    asyncio.create_task(master_agent_instance.start_background_tasks())

def set_master_agent(agent: "MasterAgent"):
    global master_agent_instance
    master_agent_instance = agent

def queue_command_for_worker(worker_id: str, command: dict):
    """Queue a command to be picked up by a worker."""
    if worker_id not in pending_commands:
        pending_commands[worker_id] = []
    pending_commands[worker_id].append(command)
    master_agent_instance.logger.info(f"Queued command for worker {worker_id}: {command}")

# Store pending commands for dashboard shell workers
pending_commands = {}

@app.get("/api/master/status")
def get_status():
    return master_agent_instance.get_status()

@app.get("/api/master/workers")
def get_workers():
    if not master_agent_instance:
        return {"workers": {}}
    return {"workers": master_agent_instance.agent_registry.get_all_workers_info()}

@app.get("/api/master/issues")
def get_issues():
    return {"issues": [i.dict() if hasattr(i, 'dict') else i for i in master_agent_instance.active_issues]}

@app.get("/api/master/tasks")
def get_tasks():
    return {"tasks": [t.dict() for t in master_agent_instance.active_tasks.values()]}

@app.post("/api/master/report_issue")
async def report_issue(request: Request):
    data = await request.json()
    worker_id = data["worker_id"]

    # Check for an existing active issue for this worker
    for issue in master_agent_instance.active_issues:
        if issue.worker_id == worker_id and issue.status != "resolved":
            master_agent_instance.logger.info(f"Updating existing issue {issue.issue_id} for worker {worker_id}.")
            issue.logs.extend(data.get("logs", []))
            issue.description += f"\nUPDATE: {data['description']}"
            # Ensure the issue is re-opened for processing
            issue.status = "open"
            return {"status": "ok", "message": "Existing issue updated.", "issue_id": issue.issue_id}

    # If no active issue exists, create a new one
    issue = Issue(
        issue_id=generate_id(),
        worker_id=worker_id,
        app_name=data.get("app_name", "shell-app"),
        issue_type=IssueType.PROCESS_CRASH,  # This could be inferred
        description=data["description"],
        confidence_score=0.8,
        logs=data.get("logs", []),
        context={},
        timestamp=data.get("timestamp", time.time()),
        status="open"
    )
    
    master_agent_instance.active_issues.append(issue)
    master_agent_instance.logger.info(f"New issue {issue.issue_id} reported from worker {worker_id}. It will be processed.")
    
    return {"status": "ok", "message": "Issue reported and queued for resolution.", "issue_id": issue.issue_id}

@app.post("/api/master/issue/{issue_id}/update")
async def update_issue_log(issue_id: str, request: Request):
    data = await request.json()
    logs = data.get("logs", [])
    
    issue_found = False
    for issue in master_agent_instance.active_issues:
        if issue.issue_id == issue_id:
            issue.logs.extend(logs)
            issue.status = "open"  # Re-open issue for resolver to pick it up
            issue_found = True
            break
            
    if not issue_found:
        raise HTTPException(status_code=404, detail="Issue not found")
        
    master_agent_instance.logger.info(f"Received update for issue {issue_id}. New logs added.")
    return {"status": "updated"}

@app.post("/api/worker/{worker_id}/command")
async def send_command(worker_id: str, request: Request):
    data = await request.json()
    if worker_id not in pending_commands:
        pending_commands[worker_id] = []
    pending_commands[worker_id].append(data)
    print(f"[MASTER] Queued command for {worker_id}: {data}")
    return {"status": "queued"}

@app.get("/api/worker/{worker_id}/next_command")
def get_next_command(worker_id: str):
    cmds = pending_commands.get(worker_id, [])
    if cmds:
        cmd = cmds.pop(0)
        print(f"[MASTER] Dispatching command to {worker_id}: {cmd}")
        return cmd
    return {"status": "no_command"}
