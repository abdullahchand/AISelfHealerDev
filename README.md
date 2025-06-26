# AI-based Developer Runtime Environment

An intelligent, self-healing system designed to autonomously manage, fix, and optimize developer runtime environments.

## 🧠 Core Philosophy

Traditional development environments are fragile. Container issues, port conflicts, environment mismatches, and app startup bugs slow teams down. This system brings AI-assisted runtime repair with:

- **Zero manual debugging**
- **Modular per-application agents**
- **System-level intelligence**
- **Multi-agent collaboration**

## 🏗️ System Architecture

### 1. Master AI Agent (Orchestrator)
- **Role**: Central coordinator and planner
- **Responsibilities**:
  - Maintain global environment state
  - Assign tasks to worker agents
  - Monitor health of workers
  - Manage conflict resolution (e.g., port conflicts, memory allocation)
  - Oversee environment healing and agent upgrades

### 2. Worker AI Agents (Runtime Repair Bots)
- **Role**: Modular runtime managers for each component/service
- **Responsibilities**:
  - Auto-start assigned applications/services
  - Detect issues in startup logs, containers, ports, dependencies
  - Collaborate with other agents via gRPC
  - Provide confidence score and diagnosis per issue
  - Take autonomous actions (restart, rebuild, reassign resources)

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
git clone <repository-url>
cd ai-runtime

# Install dependencies
pip install -r requirements.txt

# Generate gRPC code
python -m grpc_tools.protoc -I./protos --python_out=./shared --grpc_python_out=./shared ./protos/agent.proto
```

### Basic Usage

```bash
# Start the master agent
ai-runtime start

# Diagnose current environment
ai-runtime diagnose

# Heal detected issues
ai-runtime heal

# View agent status
ai-runtime status
```

## 🔧 Use Cases

| Scenario | Handled By |
|----------|------------|
| Process crash | Worker AI restarts, logs diagnosis |
| Port conflict on 3000 | Master reassigns port + updates all agents |
| Missing .env config | Worker AI regenerates using fallback template |
| Slow startup / health check timeout | Master reallocates resources |
| Shared resource lock | Master coordinates time-sliced access |

## 🧩 Modularity

Each Worker AI is modular and isolated:
- Specific to one app/module
- Configured via `agent.config.yaml`
- Can be trained or fine-tuned per stack (Node.js, Python, etc.)
- Can plug into various runtime environments

## 🛠️ Tech Stack

- **Language**: Python
- **AI/LLM**: OpenAI API / Local LLM
- **Communication**: gRPC
- **State DB**: SQLite (local), Redis (optional)
- **CLI Tool**: Typer

## 📁 Project Structure

```
ai_runtime/
├── master_agent/          # Master AI Agent
├── worker_agent/          # Worker AI Agents
├── shared/               # Shared utilities and models
├── cli/                  # Command line interface
├── protos/               # gRPC protocol definitions
├── tests/                # Test suite
├── agent.config.yaml     # Example configuration
└── requirements.txt      # Python dependencies
```

## 🔮 Future Enhancements

- Agent federation for multi-host environments
- Persistent state storage and rollback
- Training using company-specific logs
- Integration with GitHub Actions or CI pipelines
- AI-based testing and test case generation

## 📄 License

MIT License 