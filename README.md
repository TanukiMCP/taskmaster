# Taskmaster MCP Server

**A Production-Grade Model Context Protocol Server for Intelligent Task Management**

[![Smithery Compatible](https://img.shields.io/badge/Smithery-Compatible-green)](https://smithery.ai)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://python.org)
[![MCP Protocol](https://img.shields.io/badge/MCP-v1.0-orange)](https://modelcontextprotocol.io)

Taskmaster is an advanced MCP server that provides AI agents with a comprehensive task management framework featuring intelligent workflow orchestration, structured planning with the Six Hat Thinking methodology, and architectural pattern support for complex software development tasks.

## 🌟 Key Features

### **Unified Gateway Architecture**
- **Single `taskmaster` Tool**: All functionality accessible through one powerful, command-based interface
- **Dynamic Command Routing**: Extensible command system with lazy loading for optimal performance
- **Clean API Design**: Consistent request/response patterns across all operations

### **Structured Planning Workflow**
- **Six Hat Thinking Method**: Comprehensive planning approach analyzing tasks from six different perspectives
- **Denoising Synthesis**: Intelligent consolidation of multi-perspective analysis into actionable plans
- **Phase-Based Execution**: Clear separation between planning and execution phases
- **Session Persistence**: Full lifecycle management with backup and recovery

### **Advanced Workflow Management**
- **Guided Task Execution**: Structured planning → analysis → synthesis → execution → completion workflow
- **Capability Mapping**: Rich tool assignment system with contextual guidance
- **Intelligent Command Handlers**: Focused, single-responsibility handlers for each action
- **Collaborative Execution**: Built-in support for human-AI collaboration

### **Smart Environment Intelligence**
- **Capability Declaration**: Explicit tool and resource registration for optimal planning
- **Dynamic Tool Discovery**: Automatically identifies development tools and resources
- **Persistent Session Management**: Thread-safe session handling with atomic operations
- **Comprehensive Error Handling**: Structured error management with detailed guidance

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
    user_resources=[
        {
            "name": "project_codebase",
            "description": "Complete source code for the current project"
        }
    ]
)
```

### 3. Six Hat Thinking Analysis

```python
# Analyze your project from six different perspectives
taskmaster(
    action="six_hat_thinking",
    six_hats={
        "white": "Factual analysis: The project requires a React frontend with Node.js backend, user authentication, and database integration. Available tools include file operations, terminal commands, and code search.",
        "red": "Emotional analysis: Users will appreciate clean, intuitive interfaces. Potential frustration points include slow loading times and complex authentication flows.",
        "black": "Risk analysis: Potential challenges include security vulnerabilities, scalability issues, database design complexity, and integration difficulties between frontend and backend.",
        "yellow": "Optimistic analysis: This architecture provides excellent scalability, maintainability, and user experience. Modern tools enable rapid development with best practices.",
        "green": "Creative analysis: Could implement microservices architecture, use GraphQL for efficient data fetching, or add real-time features with WebSockets.",
        "blue": "Process analysis: Break into phases: setup and configuration, backend API development, frontend implementation, authentication integration, and final testing."
    }
)
```

### 4. Plan Synthesis & Task Creation

```python
# Synthesize analysis into actionable tasks
taskmaster(
    action="create_tasklist",
    denoised_plan="Based on the six hat analysis, create a modern web application with clean architecture. Start with project setup, then build backend API with authentication, followed by React frontend with responsive design. Focus on security, performance, and maintainability.",
    tasklist=[
        {
            "description": "Set up project structure with Node.js backend and React frontend",
            "complexity_level": "simple"
        },
        {
            "description": "Implement backend API with Express.js and database integration",
            "complexity_level": "complex"
        },
        {
            "description": "Build React frontend with authentication and responsive design",
            "complexity_level": "complex"
        }
    ]
)
```

### 5. Capability Mapping

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

### 6. Task Execution

```python
# Get guided execution for current task phase
taskmaster(action="execute_next")

# Mark phase complete and progress to next
taskmaster(action="mark_complete")
```

## 🛠️ Available Actions

### Core Workflow Actions

| Action | Purpose | Key Parameters |
|--------|---------|----------------|
| `create_session` | Initialize new workflow session | `session_name`, `task_description` |
| `declare_capabilities` | Register available tools and resources | `builtin_tools`, `mcp_tools`, `user_resources` |
| `six_hat_thinking` | Analyze project from six perspectives | `six_hats` with all six perspectives |
| `create_tasklist` | Define structured task breakdown | `tasklist`, `denoised_plan` |
| `map_capabilities` | Assign tools to task phases | `task_mappings` with rich context |
| `execute_next` | Get guided execution for current phase | - |
| `mark_complete` | Progress through phases | - |
| `get_status` | Check current workflow state | - |
| `end_session` | Complete and archive session | - |

### Utility Actions

| Action | Purpose | Key Parameters |
|--------|---------|----------------|
| `collaboration_request` | Request human input/guidance | `collaboration_context` |
| `edit_task` | Modify existing task | `task_id`, `updated_task_data` |

## 🔧 Architecture & Design

### Core Components

- **TaskmasterCommandHandler**: Routes and processes all taskmaster actions with dependency injection
- **SessionManager**: Manages workflow sessions with persistent state and backup management
- **WorkflowStateMachine**: Manages task execution flow and state transitions
- **AsyncSessionPersistence**: High-performance file-based state management
- **Individual Command Handlers**: Focused handlers for each action type

### Design Principles

- **Dependency Injection**: Centralized service management with proper lifecycle control
- **Command Pattern**: Clean separation of concerns with individual command handlers
- **Async-First**: Built for high-performance async operations throughout
- **Lightweight Design**: Aligns with MCP's principle of lightweight server programs
- **Extensible Architecture**: Plugin system for commands and handlers

### Data Flow

1. MCP Client connects via HTTP transport
2. Commands routed through TaskmasterCommandHandler
3. Individual command handlers process specific actions
4. Session state persisted asynchronously
5. Response with guidance and next steps

## 🧠 Six Hat Thinking Method

### The Six Perspectives

Taskmaster uses Edward de Bono's Six Hat Thinking method for comprehensive project analysis:

- **🤍 White Hat (Facts)**: Objective information, data, and known requirements
- **❤️ Red Hat (Emotions)**: Intuitive responses, user feelings, and emotional considerations
- **🖤 Black Hat (Caution)**: Critical thinking, risks, and potential problems
- **💛 Yellow Hat (Optimism)**: Benefits, opportunities, and positive outcomes
- **💚 Green Hat (Creativity)**: Alternative approaches, innovation, and new ideas
- **💙 Blue Hat (Process)**: Meta-thinking, organization, and strategy

### Implementation Benefits

- **Comprehensive Analysis**: Ensures all aspects of a project are considered
- **Structured Thinking**: Provides a systematic approach to problem-solving
- **Risk Mitigation**: Identifies potential issues before implementation
- **Creative Solutions**: Encourages innovative approaches to challenges

## ⚙️ Configuration

Customize server behavior by editing `config.yaml`:

```yaml
state_directory: 'taskmaster/state'
session_backup_count: 5
```

## 🚀 Production Deployment

### Smithery.ai Deployment

The server is optimized for deployment on Smithery.ai:

1. **Repository Setup**: Ensure all files are committed to GitHub
2. **Smithery Configuration**: `smithery.yaml` is pre-configured for container deployment
3. **Automated Deployment**: GitHub Actions workflow handles testing and container building

### Docker Deployment

```bash
docker build -t taskmaster-mcp .
docker run -p 8080:8080 taskmaster-mcp
```

### Environment Variables

- `PORT`: Server port (default: 8080)
- `SMITHERY_DEPLOY`: Set to "true" for Smithery deployment mode

## 🧪 Testing

### Running Tests

```bash
# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=taskmaster --cov-report=html
```

### Test Coverage

The server maintains comprehensive test coverage across:

- Core workflow functionality
- Command handlers and routing
- Session management and persistence
- Error handling scenarios

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

**Taskmaster MCP Server** - Intelligent task management for AI agents with production-grade reliability, structured planning methodology, and advanced workflow orchestration.
