# AI-based Developer Runtime Environment

An intelligent, self-healing system designed to autonomously manage, fix, and optimize developer runtime environments with AI-powered orchestration and a modern web dashboard.

## 🧠 Core Philosophy

Traditional development environments are fragile. Container issues, port conflicts, environment mismatches, and app startup bugs slow teams down. This system brings AI-assisted runtime repair with:

- **Zero manual debugging**
- **Modular per-application agents**
- **System-level intelligence**
- **Multi-agent collaboration**
- **Real-time web dashboard**
- **AI-powered issue analysis and resolution**

## 🏗️ System Architecture

### 1. Master AI Agent (Orchestrator)
- **Role**: Central coordinator and planner
- **Responsibilities**:
  - Maintain global environment state
  - Assign tasks to worker agents
  - Monitor health of workers via gRPC
  - Manage conflict resolution (e.g., port conflicts, memory allocation)
  - Oversee environment healing and agent upgrades
  - Provide REST API and WebSocket endpoints for dashboard

### 2. Worker AI Agents (Runtime Repair Bots)
- **Role**: Modular runtime managers for each component/service
- **Responsibilities**:
  - Auto-start assigned applications/services
  - Detect issues in startup logs, containers, ports, dependencies
  - Collaborate with other agents via gRPC
  - Provide confidence score and diagnosis per issue
  - Take autonomous actions (restart, rebuild, reassign resources)
  - Send heartbeats and issue reports to master

### 3. Web Dashboard
- **Role**: Real-time monitoring and control interface
- **Features**:
  - Live worker status monitoring
  - AI assessment visualization
  - Application health tracking
  - System resource monitoring
  - Interactive issue resolution

## 🚀 Quick Start

### Prerequisites

- Python 3.8+ (recommended: Python 3.12 with conda)
- Node.js 20+ (for dashboard frontend)
- Git

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd SRE_Auto

# Create and activate conda environment (recommended)
conda create -n ai-runtime python=3.12
conda activate ai-runtime

# Install Python dependencies
pip install -r requirements.txt

# Install the package in development mode
pip install -e .

# Generate gRPC code from protobuf definitions
python -m grpc_tools.protoc -I./protos --python_out=./shared --grpc_python_out=./shared ./protos/agent.proto

# Install frontend dependencies
cd dashboard/frontend
npm install
cd ../..
```

### Configuration

The system uses `agent.config.yaml` for configuration. Key sections:

- **Master Agent**: Central orchestrator settings
- **Worker Agents**: Individual worker configurations
- **Applications**: App-specific settings (commands, ports, health checks)
- **System**: Resource thresholds and logging
- **LLM**: AI model configuration (OpenAI or local models)

## 🎮 Usage

### CLI Commands

```bash
# Start the complete system (master + worker agents)
ai-runtime start

# Start only master agent
ai-runtime start --master

# Start only worker agent
ai-runtime start --worker --worker-id my-worker

# Diagnose current environment
ai-runtime diagnose

# Diagnose specific application
ai-runtime diagnose --app web-app

# Heal detected issues
ai-runtime heal

# Force healing without confirmation
ai-runtime heal --force

# View agent status
ai-runtime status

# Add new application
ai-runtime add-app "my-app" "python app.py" --port 8080 --working-dir ./my-app

# Remove application
ai-runtime remove-app "my-app"
```

### Web Dashboard

```bash
# Start the backend API server
cd dashboard/backend
python main.py

# In another terminal, start the frontend
cd dashboard/frontend
npm run dev
```

The dashboard will be available at:
- Frontend: http://localhost:5173
- Backend API: http://localhost:8000

## 🔧 Use Cases

| Scenario | Handled By |
|----------|------------|
| Process crash | Worker AI restarts, logs diagnosis |
| Port conflict on 3000 | Master reassigns port + updates all agents |
| Missing .env config | Worker AI regenerates using fallback template |
| Slow startup / health check timeout | Master reallocates resources |
| Shared resource lock | Master coordinates time-sliced access |
| Memory leaks | AI analysis suggests optimizations |

## 🧩 Modularity

Each Worker AI is modular and isolated:
- Specific to one app/module
- Configured via `agent.config.yaml`
- Can be trained or fine-tuned per stack (Node.js, Python, etc.)
- Can plug into various runtime environments
- Communicates via gRPC for reliability

## 🛠️ Tech Stack

### Backend
- **Language**: Python 3.12
- **AI/LLM**: OpenAI API / Local Transformers models
- **Communication**: gRPC for agent communication
- **API**: FastAPI for REST and WebSocket endpoints
- **State Management**: SQLite (local), Redis (optional)
- **CLI Tool**: Typer with Rich UI

### Frontend
- **Framework**: React 19 with Vite
- **UI**: Modern responsive design
- **Real-time**: WebSocket connections
- **Build**: Vite for fast development

### Infrastructure
- **Process Management**: Native Python multiprocessing
- **Health Checks**: Configurable HTTP/TCP checks
- **Logging**: Structured logging with rotation
- **Configuration**: YAML-based configuration

## 📁 Project Structure

```
SRE_Auto/
├── master_agent/              # Master AI Agent
│   ├── master.py             # Main orchestrator logic
│   ├── state_manager.py      # State persistence
│   ├── agent_registry.py     # Worker registration
│   └── http_api.py          # REST/WebSocket API
├── worker_agent/              # Worker AI Agents
│   ├── worker.py             # Worker agent implementation
│   ├── runtime_manager.py    # Process management
│   └── log_parser.py         # Log analysis
├── shared/                   # Shared utilities and models
│   ├── models.py             # Data models
│   ├── config.py             # Configuration management
│   ├── utils.py              # Utility functions
│   ├── llm_analyzer.py       # AI analysis engine
│   ├── agent_pb2.py          # gRPC generated code
│   └── agent_pb2_grpc.py     # gRPC service definitions
├── cli/                      # Command line interface
│   └── main.py              # CLI commands
├── dashboard/                # Web dashboard
│   ├── backend/             # FastAPI backend
│   │   └── main.py         # API server
│   └── frontend/            # React frontend
│       ├── src/            # React components
│       ├── package.json    # Node dependencies
│       └── vite.config.js  # Build configuration
├── protos/                  # gRPC protocol definitions
│   └── agent.proto         # Service definitions
├── data/                    # Runtime data storage
├── agent.config.yaml        # Main configuration
├── requirements.txt         # Python dependencies
├── setup.py                # Package installation
└── README.md               # This file
```

## 🔮 Features

### AI-Powered Analysis
- **Issue Detection**: Automatic problem identification from logs
- **Root Cause Analysis**: AI determines underlying causes
- **Resolution Suggestions**: Intelligent fix recommendations
- **Confidence Scoring**: AI confidence in diagnoses

### Real-time Monitoring
- **Live Status**: Real-time worker and app status
- **Resource Tracking**: CPU, memory, disk usage
- **Health Checks**: Configurable application health monitoring
- **Alert System**: Proactive issue notifications

### Self-Healing Capabilities
- **Auto-restart**: Failed applications restart automatically
- **Port Management**: Automatic port conflict resolution
- **Resource Optimization**: Dynamic resource allocation
- **Dependency Management**: Automatic dependency installation

## 🚀 Development

### Running in Development

```bash
# Start with development logging
ai-runtime start --config agent.config.yaml

# Run tests
python -m pytest tests/

# Format code
black .
isort .

# Type checking
mypy .
```

### Adding New Applications

1. **Update Configuration**:
   ```yaml
   apps:
     - name: "my-new-app"
       command: "python my_app.py"
       working_dir: "./my-app"
       port: 8080
       health_check_url: "http://localhost:8080/health"
   ```

2. **Register with CLI**:
   ```bash
   ai-runtime add-app "my-new-app" "python my_app.py" --port 8080
   ```

3. **Monitor via Dashboard**: View real-time status and AI assessments

## 📄 License

MIT License - see LICENSE file for details

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests
5. Submit a pull request

## 📞 Support

- **Issues**: GitHub Issues
- **Documentation**: This README and inline code comments
- **Community**: GitHub Discussions 