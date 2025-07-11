# Taskmaster MCP Server

**A Production-Grade Model Context Protocol Server for Intelligent Task Management**

[![Smithery Compatible](https://img.shields.io/badge/Smithery-Compatible-green)](https://smithery.ai)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![MCP Protocol](https://img.shields.io/badge/MCP-v1.0-orange)](https://modelcontextprotocol.io)

Taskmaster is an advanced MCP server that provides AI agents with a comprehensive task management framework featuring intelligent workflow orchestration, anti-hallucination validation, smart environment scanning, and architectural pattern support for complex software development tasks.

## 🌟 Key Features

### **Unified Gateway Architecture**
- **Single `taskmaster` Tool**: All functionality accessible through one powerful, command-based interface
- **Dynamic Command Routing**: Extensible command system with lazy loading for optimal performance
- **Clean API Design**: Consistent request/response patterns across all operations

### **Advanced Workflow Management**
- **Structured Task Execution**: Guided planning → execution → completion workflow
- **Capability Mapping**: Rich tool assignment system with contextual guidance
- **Phase-Based Organization**: Tasks broken into planning, execution, and validation phases
- **Session Persistence**: Full lifecycle management with backup and recovery

### **Anti-Hallucination Engine**
- **Evidence-Based Validation**: Pluggable validation rules system
- **Real-World Grounding**: Command execution result verification
- **Adversarial Review**: Peer review processes for complex tasks
- **Structured Quality Gates**: Prevents task completion without proper evidence

### **Smart Environment Intelligence**
- **Asynchronous Environment Scanning**: Detects available tools and system capabilities
- **Persistent Capability Caching**: Session-aware tool availability
- **Dynamic Tool Discovery**: Automatically identifies development tools and resources
- **Memory Integration**: Cumulative learning and context management

### **Architectural Pattern Support**
- **World Model Maintenance**: Dynamic context tracking throughout execution
- **Hierarchical Planning**: Multi-level task decomposition for complex projects
- **Host Environment Grounding**: Real command execution tracking
- **Static Analysis Integration**: Codebase understanding and context

## 🚀 Quick Start

### Installation

```bash
git clone <repository-url>
cd taskmaster
pip install -r requirements.txt
```

### Running the Server

```bash
python server.py
```

The server starts on `http://localhost:8080/mcp` by default.

### MCP Client Configuration

#### Cursor IDE
Add to your `mcp.json` configuration:

```json
{
  "servers": {
    "taskmaster": {
      "url": "http://localhost:8080/mcp",
      "transport": "http"
    }
  }
}
```

#### Claude Desktop
Add to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "taskmaster": {
      "url": "http://localhost:8080/mcp",
      "transport": "http"
    }
  }
}
```

## 📋 Complete Workflow Guide

### 1. Session Creation & Setup

```python
# Create a new workflow session
taskmaster(
    action="create_session",
    session_name="My Development Project",
    task_description="Build a web application with authentication"
)
```

### 2. Capability Declaration

```python
# Declare your available tools and resources
taskmaster(
    action="declare_capabilities",
    builtin_tools=[
        {
            "name": "codebase_search",
            "description": "Semantic search to find code by meaning and understand behavior"
        },
        {
            "name": "edit_file", 
            "description": "Create new files or edit existing files with precise code changes"
        },
        {
            "name": "run_terminal_cmd",
            "description": "Execute terminal commands for builds, tests, and operations"
        }
    ],
    mcp_tools=[
        {
            "name": "sequential_thinking",
            "description": "Advanced problem-solving with structured reasoning",
            "server_name": "mcp_server-sequential-thinking_sequentialthinking"
        }
    ],
    memory_tools=[
        {
            "name": "memory_update",
            "description": "Store knowledge and learnings",
            "type": "memory_system"
        }
    ]
)
```

### 3. Task List Creation

```python
# Create structured tasks with phases
taskmaster(
    action="create_tasklist",
    tasklist=[
        {
            "description": "Set up project structure and dependencies",
            "complexity_level": "simple",
            "planning_phase": {
                "description": "Plan the project architecture and tech stack",
                "steps": [
                    "Research framework options",
                    "Define project structure",
                    "List required dependencies"
                ]
            },
            "execution_phase": {
                "description": "Implement the project setup",
                "steps": [
                    "Create directory structure",
                    "Initialize package.json",
                    "Install dependencies"
                ]
            }
        }
    ]
)
```

### 4. Capability Mapping

```python
# Map tools to specific task phases with rich context
taskmaster(
    action="map_capabilities",
    task_mappings=[
        {
            "task_id": "task_abc123",
            "planning_phase": {
                "assigned_builtin_tools": [
                    {
                        "tool_name": "codebase_search",
                        "usage_purpose": "Research existing patterns and best practices",
                        "specific_actions": [
                            "Search for similar project structures",
                            "Find authentication implementation examples"
                        ],
                        "expected_outcome": "Understanding of proven patterns to follow",
                        "priority": "critical"
                    }
                ],
                "assigned_memory_tools": [
                    {
                        "tool_name": "memory_query",
                        "usage_purpose": "Retrieve relevant past project learnings",
                        "specific_actions": ["Query for similar setup experiences"],
                        "expected_outcome": "Context from previous successful setups",
                        "priority": "normal"
                    }
                ]
            },
            "execution_phase": {
                "assigned_builtin_tools": [
                    {
                        "tool_name": "edit_file",
                        "usage_purpose": "Create project files and configuration",
                        "specific_actions": [
                            "Create package.json with dependencies",
                            "Set up directory structure"
                        ],
                        "expected_outcome": "Working project foundation",
                        "priority": "critical"
                    }
                ]
            }
        }
    ]
)
```

### 5. Task Execution

```python
# Get guided execution for current task phase
taskmaster(action="execute_next")

# Mark phase complete with evidence
taskmaster(
    action="mark_complete",
    evidence=[
        {
            "type": "file_created",
            "file_path": "package.json",
            "content_summary": "Project configuration with React and authentication deps"
        },
        {
            "type": "command_executed", 
            "command": "npm install",
            "exit_code": 0,
            "output": "Successfully installed 25 packages"
        }
    ],
    description="Project structure created with all dependencies installed"
)
```

## 🛠️ Available Actions

### Core Workflow Actions

| Action | Purpose | Key Parameters |
|--------|---------|----------------|
| `create_session` | Initialize new workflow session | `session_name`, `task_description` |
| `declare_capabilities` | Register available tools and resources | `builtin_tools`, `mcp_tools`, `memory_tools` |
| `create_tasklist` | Define structured task breakdown | `tasklist` with phase structure |
| `map_capabilities` | Assign tools to task phases | `task_mappings` with rich context |
| `execute_next` | Get guided execution for current phase | - |
| `mark_complete` | Progress through phases with evidence | `evidence`, `description` |
| `get_status` | Check current workflow state | - |
| `end_session` | Complete and archive session | `session_summary` |

### Advanced Architectural Actions

| Action | Purpose | Key Parameters |
|--------|---------|----------------|
| `initialize_world_model` | Set up dynamic context tracking | `target_files`, `analysis_scope` |
| `create_hierarchical_plan` | Multi-level task decomposition | `high_level_steps` |
| `initiate_adversarial_review` | Peer review for quality assurance | `generated_content` |
| `record_host_grounding` | Track real command execution | `command_executed`, `stdout`, `stderr` |
| `update_world_model` | Maintain live context state | `target_files`, `analysis_scope` |
| `static_analysis` | Populate world model with codebase understanding | `target_files` |

### Utility Actions

| Action | Purpose | Key Parameters |
|--------|---------|----------------|
| `discover_capabilities` | Auto-detect available environment tools | - |
| `add_task` | Add new task to existing session | `task_data` |
| `remove_task` | Remove task from session | `task_id` |
| `update_task` | Modify existing task | `task_id`, `updated_task_data` |
| `collaboration_request` | Request human input/guidance | `collaboration_context` |

## 🔧 Architecture & Design

### Core Components

- **Command Handler System**: Routes and processes all taskmaster actions with dependency injection
- **Session Manager**: Manages workflow sessions with persistent state and backup management
- **Validation Engine**: Provides advisory validation with pluggable rules system
- **Environment Scanner**: Detects and caches available tools and system capabilities
- **Workflow State Machine**: Manages task execution flow and state transitions
- **Async Persistence Layer**: High-performance file-based state management

### Design Principles

- **Dependency Injection**: Centralized service management with proper lifecycle control
- **Command Pattern**: Clean separation of concerns with individual command handlers
- **Async-First**: Built for high-performance async operations throughout
- **Lightweight Design**: Aligns with MCP's principle of lightweight server programs
- **Extensible Architecture**: Plugin system for validation rules, scanners, and commands

### Data Flow

1. MCP Client connects via HTTP transport
2. Commands routed through TaskmasterCommandHandler
3. Individual command handlers process specific actions
4. Session state persisted asynchronously
5. Validation engine provides advisory feedback
6. Environment scanner maintains capability cache

## 🧪 Validation System

### Built-in Validation Rules

- **`capability_assignment`** - Ensures tools are used as assigned to phases
- **`completeness`** - Detects placeholder implementations and incomplete code
- **`content_contains_rule`** - Verifies content contains required elements
- **`file_exists_rule`** - Confirms specified files exist on filesystem
- **`syntax_rule`** - Validates code syntax for multiple languages
- **`test_integrity`** - Prevents test manipulation and ensures quality

### Custom Validation Rules

Create new validation rules by extending `BaseValidationRule`:

```python
from taskmaster.validation_rules.base_rule import BaseValidationRule

class CustomRule(BaseValidationRule):
    @property
    def rule_name(self) -> str:
        return "custom_rule"
    
    def check(self, task, evidence) -> tuple[bool, str]:
        # Implementation logic
        return True, "Validation passed"
```

## 🔍 Environment Scanning

### Built-in Scanners

- **`system_tool_scanner`** - Detects development tools (Python, Git, Node.js, Docker, etc.)
- **`capability_scanner`** - Discovers available MCP servers and tools

### Custom Scanners

Extend `BaseScanner` to add new environment detection capabilities:

```python
from taskmaster.scanners.base_scanner import BaseScanner

class CustomScanner(BaseScanner):
    def __init__(self, config):
        super().__init__(config)
        self.scanner_name = "custom_scanner"
    
    async def scan(self) -> dict:
        # Implementation logic
        return {"detected_tools": []}
```

## ⚙️ Configuration

Customize server behavior by editing `config.yaml`:

```yaml
state_directory: 'taskmaster/state'
session_backup_count: 5

validation:
  advisory_mode: true
  rules:
    - capability_assignment
    - completeness
    - test_integrity

scanners:
  system_tool_scanner:
    enabled: true
    timeout: 30
```

## 🚀 Production Deployment

### Smithery.ai Deployment

The server is optimized for deployment on Smithery.ai:

1. **Repository Setup**: Ensure all files are committed to GitHub
2. **Smithery Configuration**: `smithery.yaml` is pre-configured for container deployment
3. **Automated Deployment**: GitHub Actions workflow handles testing and container building
4. **Health Monitoring**: Built-in health checks and monitoring endpoints

### Docker Deployment

```bash
docker build -t taskmaster-mcp .
docker run -p 8080:8080 taskmaster-mcp
```

### Environment Variables

- `PORT`: Server port (default: 8080)
- `SMITHERY_DEPLOY`: Set to "true" for Smithery deployment mode

## 📊 Monitoring & Health

### Health Endpoints

- **`/health`** - Server health and status
- **`/config`** - Server capabilities and configuration  
- **`/`** - Server information and version
- **`/docs`** - API documentation

### Logging

The server provides comprehensive logging with configurable levels:

```python
import logging
logging.basicConfig(level=logging.INFO)
```

## 🧠 Memory & Learning Integration

### Memory Gate Patterns

When memory tools are available, Taskmaster implements sophisticated memory patterns:

- **Planning Gates**: Retrieve relevant context and past learnings
- **Execution Gates**: Store insights and patterns discovered during execution
- **Validation Gates**: Consolidate successful approaches and strengthen patterns
- **Cross-Task Learning**: Build relationships between related tasks

### Memory Tool Types

- **Vector Search**: Semantic similarity-based retrieval
- **Knowledge Base**: Structured information storage
- **Context Window**: Session-scoped memory management
- **Pattern Recognition**: Learning from successful/failed approaches

## 🔄 Advanced Patterns

### Adversarial Review Process

For complex tasks, Taskmaster supports adversarial review:

1. **Generation Phase**: AI generates solution/code
2. **Review Phase**: Separate reviewer agent analyzes for issues
3. **Testing Phase**: Automated testing and validation
4. **Correction Cycles**: Iterative improvement until approval

### Hierarchical Planning

Break complex projects into manageable hierarchies:

```python
taskmaster(
    action="create_hierarchical_plan",
    high_level_steps=[
        {
            "step": "Architecture Design",
            "substeps": ["Database schema", "API design", "UI mockups"]
        },
        {
            "step": "Implementation",
            "substeps": ["Backend development", "Frontend development", "Integration"]
        }
    ]
)
```

### World Model Maintenance

Keep dynamic context throughout task execution:

- **Static Analysis**: Understand codebase structure and dependencies
- **Live Updates**: Track changes and their impacts
- **Error Tracking**: Maintain awareness of known issues
- **Verification Status**: Track what has been verified vs. assumed

## 🧪 Testing

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=taskmaster --cov-report=html

# Run specific test categories
pytest tests/test_comprehensive.py -v
```

### Test Coverage

The server maintains >95% test coverage across:

- Core workflow functionality
- Validation engine
- Environment scanning
- Error handling scenarios
- Integration patterns

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

For detailed development information, see the Developer Guide in the `docs/` directory.

## 📜 License

MIT License - see LICENSE file for details.

---

**Taskmaster MCP Server** - Intelligent task management for AI agents with production-grade reliability and advanced workflow orchestration.
