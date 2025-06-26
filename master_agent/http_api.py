from fastapi import FastAPI, Request
from master_agent.master import MasterAgent
from shared.llm_analyzer import LLMAnalyzer
from shared.models import Issue
import asyncio

app = FastAPI()
master = MasterAgent()
llm_analyzer = LLMAnalyzer()

# Store pending commands for dashboard shell workers
pending_commands = {}

@app.get("/api/master/status")
def get_status():
    return master.get_status()

@app.get("/api/master/workers")
def get_workers():
    return {"workers": list(master.agent_registry.workers)}

@app.get("/api/master/issues")
def get_issues():
    return {"issues": [i.dict() if hasattr(i, 'dict') else i for i in master.active_issues]}

@app.get("/api/master/tasks")
def get_tasks():
    return {"tasks": [t.dict() for t in master.active_tasks.values()]}

@app.post("/api/master/report_issue")
async def report_issue(request: Request):
    data = await request.json()
    # Store as dict for now
    master.active_issues.append({
        "worker_id": data["worker_id"],
        "description": data["description"],
        "logs": data["logs"],
        "timestamp": data["timestamp"]
    })
    print(f"[MASTER] Received issue from {data['worker_id']}: {data['description']}")
    # Use LLMAnalyzer to get a real suggestion
    issue = Issue(
        issue_id="dashboard-shell-issue",
        worker_id=data["worker_id"],
        app_name="shell-app",
        issue_type="process_crash",  # or infer from description
        description=data["description"],
        confidence_score=0.8,
        logs=data["logs"],
        context={},
        timestamp=data["timestamp"]
    )
    # For demo, pass empty worker_capabilities
    suggestion = await llm_analyzer.suggest_resolution(issue, {})
    print(f"[MASTER][LLM] Suggestion: {suggestion}")
    if suggestion and suggestion.get("action") and isinstance(suggestion["action"], str):
        # If the LLM suggests a shell command, queue it
        fix_cmd = suggestion["action"]
        if data["worker_id"] not in pending_commands:
            pending_commands[data["worker_id"]] = []
        pending_commands[data["worker_id"]].append({"command": fix_cmd})
        print(f"[MASTER] LLM-queued fix command for {data['worker_id']}: {fix_cmd}")
    return {"status": "ok", "llm_suggestion": suggestion}

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