# Taskmaster MCP Server

A production-grade Model Context Protocol server that provides intelligent task management with advanced validation, environment scanning, and anti-hallucination capabilities.

## Overview

Taskmaster is an MCP server that provides a comprehensive task management interface for AI agents through a unified `taskmaster` tool. The server implements structured workflow management with phase-based execution, capability mapping, and advisory validation to ensure reliable task completion.

## Key Features

### **Unified Gateway Tool**
- Single `taskmaster` tool that routes all operations through a command-based API
- Clean, consistent interface for all functionality
- Dynamic command loading and execution

### **Advanced Validation Engine**
- Pluggable validation rules system with advisory guidance
- Evidence-based task completion tracking
- Support for syntax validation, content checking, and file existence verification
- Anti-hallucination capabilities through structured validation

### **Smart Environment Scanning**
- Asynchronous environment scanning on session creation
- Detects available development tools and system capabilities
- Persistent caching of environment state per session
- Configurable and extensible scanner system

### **Comprehensive Session Management**
- Full lifecycle management from creation to completion
- Structured task organization with planning, execution, and validation phases
- Capability mapping for tool assignment to specific phases
- Session persistence with backup management

## Installation

```bash
git clone <repository-url>
cd tanukimcp-taskmaster
pip install -r requirements.txt
```

## Usage

### Running the Server

1. **Start the server:**
   ```bash
   python server.py
   ```
   The server will start on `http://localhost:8080/mcp` by default.

2. **Verify server status:**
   ```bash
   # Test basic connectivity
   curl http://localhost:8080/mcp
   ```

### MCP Client Configuration

#### Cursor IDE

Add to your `mcp.json` configuration file:

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

#### Other MCP Clients

For any MCP-compatible client, use these connection parameters:

- **URL**: `http://localhost:8080/mcp`
- **Transport**: HTTP
- **Protocol**: Model Context Protocol v1.0

### Core Workflow

The Taskmaster follows a structured workflow pattern:

1. **Create Session** - Initialize a new workflow session
2. **Declare Capabilities** - Register available tools and resources
3. **Create Tasklist** - Define tasks with planning, execution, and validation phases
4. **Map Capabilities** - Assign tools to specific task phases
5. **Execute Tasks** - Get guided execution through each phase
6. **Mark Complete** - Progress through phases and complete tasks

### Available Actions

#### Session Management

**`create_session`**
- Creates a new workflow session
- Initializes environment scanning
- Returns session ID for subsequent operations

**`declare_capabilities`**
- Registers available builtin tools, MCP tools, and user resources
- Enables capability mapping for task phases
- Validates capability declarations

**`create_tasklist`**
- Defines structured task lists with phase organization
- Supports planning, execution, and validation phases
- Returns task IDs for capability mapping

#### Task Execution

**`map_capabilities`**
- Assigns specific tools to task phases
- Includes usage purpose, specific actions, and expected outcomes
- Enables guided execution with contextual guidance

**`execute_next`**
- Provides contextual guidance for the current task phase
- Returns assigned tools with detailed instructions
- Includes execution strategy and priority information

**`mark_complete`**
- Marks current phase as complete
- Automatically progresses through workflow phases
- Moves to next task when validation phase completes

#### Advanced Features

**`initialize_world_model`**
- Initializes dynamic world model for complex scenarios
- Supports static analysis and contextual understanding

**`create_hierarchical_plan`**
- Creates multi-level planning structures
- Supports complex task decomposition

**`initiate_adversarial_review`**
- Sets up quality assurance loops
- Enables peer review processes

**`record_host_grounding`**
- Records real command execution results
- Provides grounding for AI agent actions

## Validation System

### Built-in Validation Rules

- **`capability_assignment`** - Ensures tools are used as assigned
- **`completeness`** - Detects placeholder implementations and incomplete code
- **`content_contains_rule`** - Verifies content contains required elements
- **`file_exists_rule`** - Confirms specified files exist
- **`syntax_rule`** - Validates code syntax
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

## Environment Scanning

### Built-in Scanners

- **`system_tool_scanner`** - Detects development tools (Python, Git, Node.js, etc.)

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

## Configuration

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

## Architecture

### Design Principles

The Taskmaster architecture follows modern software engineering principles:

- **Dependency Injection**: Centralized service management with proper lifecycle control
- **Command Pattern**: Clean separation of concerns with individual command handlers
- **Async-First**: Built for high-performance async operations
- **Lightweight Design**: Aligns with MCP's principle of lightweight server programs

### Core Components

- **Command Handler System**: Routes and processes all taskmaster actions
- **Session Manager**: Manages workflow sessions with persistent state
- **Validation Engine**: Provides advisory validation with pluggable rules
- **Environment Scanner**: Detects and caches available tools and capabilities
- **Async Persistence**: High-performance file-based state management

### Data Flow

1. MCP Client connects via HTTP transport
2. Commands routed through TaskmasterCommandHandler
3. Individual command handlers process specific actions
4. Session state persisted asynchronously
5. Validation engine provides advisory feedback
6. Environment scanner maintains capability cache

## Development

### Running Tests

```bash
pytest tests/ -v
```

### Test Coverage

```bash
pytest tests/ --cov=taskmaster --cov-report=html
```

### Adding Custom Commands

1. Create handler class extending `BaseCommandHandler`
2. Register in `TaskmasterContainer`
3. Add to command router mapping

## Deployment

### Local Development

```bash
python server.py
```

### Production Deployment

The server is configured for deployment on various platforms:

- **Container Runtime**: Uses Docker for containerized deployment
- **HTTP Endpoints**: Provides `/mcp` endpoint for MCP protocol communication
- **Health Monitoring**: Built-in health check at `/health`
- **Environment Variables**: Configurable via `PORT` and other environment settings

### Connection Parameters

For production deployment, clients should connect using:

- **URL**: `http://localhost:8080/mcp` (or your deployed server URL)
- **Transport**: HTTP
- **Protocol**: Model Context Protocol v1.0

## Error Handling

The server provides comprehensive error handling:

- Invalid commands return descriptive error messages with guidance
- Missing parameters are clearly identified with suggestions
- Validation failures include specific feedback and recommendations
- Environment scanning timeouts are handled gracefully with fallbacks

## Documentation

Comprehensive documentation is available in the `docs/` directory:

- **Architecture Guide**: Detailed system architecture and design patterns
- **Developer Guide**: Implementation details and extension instructions
- **User Guide**: Complete usage documentation with examples

## License

MIT License - see LICENSE file for details

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request

For detailed development information, see the Developer Guide in the `docs/` directory.
