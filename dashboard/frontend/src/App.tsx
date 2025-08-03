import React, { useEffect, useState } from 'react';
import './App.css';

// API utility
async function fetchWorkers() {
  const res = await fetch('http://localhost:8081/api/workers');
  return res.json();
}
async function fetchWorkerDetail(workerId: string) {
  const res = await fetch(`http://localhost:8081/api/worker/${workerId}`);
  return res.json();
}
async function fetchWorkerProcesses(workerId: string) {
  const res = await fetch(`http://localhost:8081/api/worker/${workerId}/processes`);
  return res.json();
}
async function sendWorkerCommand(workerId: string, data: any) {
  const res = await fetch(`http://localhost:8081/api/worker/${workerId}/command`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  return res.json();
}

interface WorkerInfo {
  worker_id: string;
  status: string;
  last_heartbeat: number;
  apps: string[];
  load: number;
  healthy: boolean;
}

interface WorkerDetail {
  worker: WorkerInfo;
  llm_output: string | null;
  issues: any[];
}

function App() {
  const [workers, setWorkers] = useState<{ [id: string]: WorkerInfo }>({});
  const [selectedWorker, setSelectedWorker] = useState<string | null>(null);
  const [workerDetail, setWorkerDetail] = useState<WorkerDetail | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  // Add New Worker modal state
  const [addModalOpen, setAddModalOpen] = useState(false);
  const [newWorkerId, setNewWorkerId] = useState("");
  const [creatingWorker, setCreatingWorker] = useState(false);
  const [createdWorkerId, setCreatedWorkerId] = useState<string | null>(null);
  const [terminalLines, setTerminalLines] = useState<string[]>([]);
  const [terminalInput, setTerminalInput] = useState("");
  const [terminalSocket, setTerminalSocket] = useState<WebSocket | null>(null);

  const [processes, setProcesses] = useState<any[]>([]);
  const [processesLoading, setProcessesLoading] = useState(false);
  const [processActionMsg, setProcessActionMsg] = useState("");

  useEffect(() => {
    fetchWorkers().then((data) => {
      setWorkers(data.workers || {});
    });
    // Optionally, poll or use WebSocket for real-time updates
    const interval = setInterval(() => {
      fetchWorkers().then((data) => {
        setWorkers(data.workers || {});
      });
    }, 3000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (selectedWorker && modalOpen) {
      setProcessesLoading(true);
      fetchWorkerProcesses(selectedWorker).then((data) => {
        setProcesses(data.processes || []);
        setProcessesLoading(false);
      });
    }
  }, [selectedWorker, modalOpen]);

  const handleWorkerClick = async (workerId: string) => {
    setSelectedWorker(workerId);
    setModalOpen(true);
    const detail = await fetchWorkerDetail(workerId);
    setWorkerDetail(detail);
  };

  const closeModal = () => {
    setModalOpen(false);
    setWorkerDetail(null);
    setSelectedWorker(null);
  };

  // Add Worker logic
  const openAddModal = () => {
    setAddModalOpen(true);
    setNewWorkerId("");
    setCreatedWorkerId(null);
    setTerminalLines([]);
    setTerminalInput("");
    if (terminalSocket) {
      terminalSocket.close();
      setTerminalSocket(null);
    }
  };

  const closeAddModal = () => {
    setAddModalOpen(false);
    setCreatedWorkerId(null);
    setTerminalLines([]);
    setTerminalInput("");
    if (terminalSocket) {
      terminalSocket.close();
      setTerminalSocket(null);
    }
  };

  const handleAddWorker = async (e: React.FormEvent) => {
    e.preventDefault();
    setCreatingWorker(true);
    const res = await fetch('http://localhost:8081/api/workers', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ worker_id: newWorkerId }),
    });
    const data = await res.json();
    if (data.worker_id) {
      setCreatedWorkerId(data.worker_id);
      // Open terminal WebSocket
      const ws = new window.WebSocket(`ws://localhost:8081/ws/worker/${data.worker_id}/terminal`);
      ws.onopen = () => {
        setTerminalLines((lines) => [...lines, "WebSocket connection established."]);
      };
      ws.onmessage = (event) => {
        setTerminalLines((lines) => [...lines, event.data]);
      };
      ws.onerror = (event) => {
        console.error("WebSocket error:", event);
        setTerminalLines((lines) => [...lines, "WebSocket error. See console for details."]);
      };
      ws.onclose = (event) => {
        setTerminalLines((lines) => [...lines, `WebSocket connection closed: ${event.reason || "No reason given"}`]);
        setTerminalSocket(null);
      };
      setTerminalSocket(ws);
    }
    setCreatingWorker(false);
  };

  const handleTerminalInput = (e: React.FormEvent) => {
    e.preventDefault();
    if (terminalSocket && terminalInput.trim()) {
      terminalSocket.send(terminalInput);
      setTerminalInput("");
    }
  };

  // Process actions
  const handleProcessAction = async (action: string, pid?: number, command?: string) => {
    if (!selectedWorker) return;
    setProcessActionMsg("");
    const data: any = { action };
    if (pid) data.pid = pid;
    if (command) data.command = command;
    const res = await sendWorkerCommand(selectedWorker, data);
    setProcessActionMsg(res.message || res.error || "");
    // Refresh process list
    fetchWorkerProcesses(selectedWorker).then((data) => {
      setProcesses(data.processes || []);
    });
  };

  return (
    <div className="App">
      <h1>AI Runtime Environment Dashboard</h1>
      <button onClick={openAddModal} style={{marginBottom: '1rem', padding: '0.5rem 1.5rem', fontSize: '1.1rem'}}>Add New Worker</button>
      <div className="worker-list">
        {Object.values(workers).length === 0 && <p>No workers found.</p>}
        {Object.values(workers).map((worker) => (
          <div
            key={worker.worker_id}
            className={`worker-card ${worker.healthy ? 'healthy' : 'unhealthy'}`}
            onClick={() => handleWorkerClick(worker.worker_id)}
          >
            <h2>{worker.worker_id}</h2>
            <p>Status: <b>{worker.status}</b></p>
            <p>Apps: {(worker.apps || []).join(', ')}</p>
            <p>Load: {worker.load}</p>
            <p>Last heartbeat: {new Date(worker.last_heartbeat * 1000).toLocaleString()}</p>
          </div>
        ))}
      </div>
      {modalOpen && workerDetail && workerDetail.worker && (
        <div className="modal" onClick={closeModal}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <button className="close-btn" onClick={closeModal}>×</button>
            <h2>Worker: {workerDetail.worker.worker_id}</h2>
            <p>Status: <b>{workerDetail.worker.status}</b></p>
            <p>Apps: {(workerDetail.worker.apps || []).join(', ')}</p>
            <p>Load: {workerDetail.worker.load}</p>
            <h3>AI Assessment</h3>
            <pre className="llm-output">{workerDetail.llm_output || 'No AI output yet.'}</pre>
            <h4>Recent Issues</h4>
            <ul>
              {workerDetail.issues.map((issue, idx) => (
                <li key={idx}>
                  <b>{issue.issue_type}</b>: {issue.description}
                </li>
              ))}
            </ul>
            <h3 style={{marginTop: '2rem'}}>User Processes</h3>
            {processActionMsg && <div style={{color: '#1976d2', marginBottom: '0.5rem'}}>{processActionMsg}</div>}
            {processesLoading ? <p>Loading...</p> : (
              <div style={{maxHeight: 250, overflowY: 'auto'}}>
                {processes.length === 0 && <p>No user processes running.</p>}
                {processes.map((proc, idx) => (
                  <div key={proc.pid} style={{border: '1px solid #eee', borderRadius: 6, marginBottom: 10, padding: 10, background: '#fafbfc'}}>
                    <div><b>PID:</b> {proc.pid}</div>
                    <div><b>Command:</b> <span style={{fontFamily: 'monospace'}}>{proc.command}</span></div>
                    <div><b>Status:</b> {proc.status}</div>
                    <div><b>Output (last 10 lines):</b>
                      <pre style={{background: '#222', color: '#0f0', borderRadius: 4, padding: 6, fontSize: '0.95rem', maxHeight: 100, overflowY: 'auto'}}>
                        {proc.output_tail && proc.output_tail.length > 0 ? proc.output_tail.join('') : '(no output)'}
                      </pre>
                    </div>
                    <div style={{marginTop: 6, display: 'flex', gap: 8}}>
                      <button onClick={() => handleProcessAction('kill', proc.pid)} style={{background: '#f44336', color: '#fff', border: 'none', borderRadius: 4, padding: '0.3rem 1rem', cursor: 'pointer'}}>Kill</button>
                      <button onClick={() => handleProcessAction('restart', undefined, proc.command)} style={{background: '#1976d2', color: '#fff', border: 'none', borderRadius: 4, padding: '0.3rem 1rem', cursor: 'pointer'}}>Restart</button>
                      <button onClick={() => handleProcessAction('run', undefined, proc.command)} style={{background: '#4caf50', color: '#fff', border: 'none', borderRadius: 4, padding: '0.3rem 1rem', cursor: 'pointer'}}>Run Again</button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}
      {addModalOpen && (
        <div className="modal" onClick={closeAddModal}>
          <div className="modal-content" onClick={e => e.stopPropagation()}>
            <button className="close-btn" onClick={closeAddModal}>×</button>
            {!createdWorkerId ? (
              <form onSubmit={handleAddWorker}>
                <h2>Add New Worker</h2>
                <label>
                  Worker Name/ID:
                  <input
                    type="text"
                    value={newWorkerId}
                    onChange={e => setNewWorkerId(e.target.value)}
                    required
                    style={{marginLeft: '0.5rem'}}
                  />
                </label>
                <button type="submit" disabled={creatingWorker} style={{marginLeft: '1rem'}}>
                  {creatingWorker ? 'Creating...' : 'Create'}
                </button>
              </form>
            ) : (
              <div>
                <h2>Worker Terminal: {createdWorkerId}</h2>
                <div style={{background: '#222', color: '#0f0', padding: '1rem', borderRadius: 6, minHeight: 200, maxHeight: 300, overflowY: 'auto', fontFamily: 'monospace', fontSize: '1rem'}}>
                  {terminalLines.map((line, idx) => <div key={idx}>{line}</div>)}
                </div>
                <form onSubmit={handleTerminalInput} style={{marginTop: '1rem', display: 'flex'}}>
                  <input
                    type="text"
                    value={terminalInput}
                    onChange={e => setTerminalInput(e.target.value)}
                    style={{flex: 1, fontFamily: 'monospace', fontSize: '1rem', padding: '0.5rem'}}
                    placeholder="Type a command..."
                  />
                  <button type="submit" style={{marginLeft: '0.5rem'}}>Send</button>
                </form>
              </div>
            )}
          </div>
        </div>
      )}
      <style>{`
        .worker-list {
          display: flex;
          flex-wrap: wrap;
          gap: 1rem;
          justify-content: center;
        }
        .worker-card {
          background: #fff;
          border-radius: 8px;
          box-shadow: 0 2px 8px rgba(0,0,0,0.1);
          padding: 1rem 2rem;
          min-width: 220px;
          cursor: pointer;
          transition: box-shadow 0.2s;
        }
        .worker-card.healthy { border-left: 6px solid #4caf50; }
        .worker-card.unhealthy { border-left: 6px solid #f44336; }
        .worker-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.15); }
        .modal {
          position: fixed;
          top: 0; left: 0; right: 0; bottom: 0;
          background: rgba(0,0,0,0.4);
          display: flex;
          align-items: center;
          justify-content: center;
          z-index: 1000;
        }
        .modal-content {
          background: #fff;
          border-radius: 8px;
          padding: 2rem;
          min-width: 350px;
          max-width: 90vw;
          position: relative;
        }
        .close-btn {
          position: absolute;
          top: 1rem;
          right: 1rem;
          background: none;
          border: none;
          font-size: 1.5rem;
          cursor: pointer;
        }
        .llm-output {
          background: #f5f5f5;
          padding: 1rem;
          border-radius: 6px;
          font-size: 1rem;
          white-space: pre-wrap;
        }
        /* Modal form and input/button styles for visibility */
        .modal-content form {
          background: #f9f9f9;
          padding: 1.5rem;
          border-radius: 8px;
          display: flex;
          flex-direction: column;
          gap: 1rem;
        }
        .modal-content label {
          color: #222;
          font-weight: 500;
        }
        .modal-content input[type="text"] {
          background: #fff;
          color: #222;
          border: 1px solid #bbb;
          border-radius: 4px;
          padding: 0.5rem 0.75rem;
          font-size: 1rem;
          margin-top: 0.5rem;
        }
        .modal-content button[type="submit"] {
          background: #1976d2;
          color: #fff;
          border: none;
          border-radius: 4px;
          padding: 0.6rem 1.5rem;
          font-size: 1.1rem;
          font-weight: 600;
          cursor: pointer;
          margin-top: 0.5rem;
          transition: background 0.2s;
        }
        .modal-content button[type="submit"]:hover {
          background: #125ea2;
        }
      `}</style>
    </div>
  );
}

export default App;