# Tanuki MCP: Taskmaster

A production-grade MCP (Model Context Protocol) server that provides intelligent task management with advanced validation, environment scanning, and anti-hallucination capabilities.

## Overview

Taskmaster is an MCP server centered around a **single gateway tool (`taskmaster`)** that provides a clean, powerful interface for LLMs to manage tasks with strict validation and environment awareness. The server is designed to prevent hallucinated progress through dynamic validation rules and comprehensive evidence tracking.

## Features

### 🎯 **Single Gateway Tool Design**
- **`taskmaster`** - One unified tool that routes all operations through command-based API
- Clean, consistent interface for all functionality
- Dynamic command loading and execution

### 🔒 **Advanced Validation & Anti-Hallucination Engine**
- Pluggable validation rules system
- Strict evidence-based task completion
- Support for syntax validation, content checking, and file existence verification
- Prevents tasks from being marked complete without proper validation

### 🔍 **Smart Environment & Capability Scanner**
- Asynchronous environment scanning on session creation
- Detects available development tools and system capabilities
- Persistent caching of environment state per session
- Configurable and extensible scanner system

### 📊 **Comprehensive Session Management**
- Full lifecycle management from creation to archival
- Progress tracking and statistics
- Evidence storage with timestamps
- Session archiving with detailed summaries

## Installation

```bash
git clone https://github.com/TanukiMCP/taskmaster.git
cd taskmaster
pip install -r requirements.txt
```

## Usage

### Running Locally

1. **Start the server:**
   ```bash
   python server.py
   ```
   The server will start on `http://localhost:8080` by default.

2. **Test the server:**
   ```bash
   # Test basic connectivity
   curl http://localhost:8080/mcp
   
   # Test the taskmaster tool
   curl -X POST http://localhost:8080/call \
     -H "Content-Type: application/json" \
     -d '{"tool": "taskmaster", "arguments": {"command": "get_validation_rules", "payload": {}}}'
   ```

### Manual Configuration with AI Assistants

#### Cursor IDE

1. Open Cursor settings (Ctrl/Cmd + ,)
2. Go to "Features" → "Model Context Protocol"
3. Add a new MCP server configuration:

```json
{
  "mcpServers": {
    "taskmaster": {
      "command": "python",
      "args": ["path/to/taskmaster/server.py"],
      "cwd": "path/to/taskmaster"
    }
  }
}
```

#### Claude Desktop

1. Open Claude Desktop settings
2. Navigate to the MCP section
3. Add this configuration to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "taskmaster": {
      "command": "python", 
      "args": ["C:/path/to/taskmaster/server.py"],
      "cwd": "C:/path/to/taskmaster",
      "env": {
        "PYTHONPATH": "C:/path/to/taskmaster"
      }
    }
  }
}
```

#### Windsurf

1. Open Windsurf preferences
2. Go to Extensions → MCP Configuration  
3. Add server configuration:

```json
{
  "servers": {
    "taskmaster": {
      "command": "python",
      "args": ["./server.py"],
      "cwd": "/path/to/taskmaster",
      "description": "Taskmaster MCP Server for intelligent task management"
    }
  }
}
```

#### Generic MCP Client

For any MCP-compatible client, use these connection details:

- **Command**: `python`
- **Args**: `["server.py"]` 
- **Working Directory**: Path to your taskmaster folder
- **Environment**: Ensure Python path includes the taskmaster directory

#### HTTP Connection (Alternative)

If your client supports HTTP MCP connections:

- **URL**: `http://localhost:8080/mcp`
- **Method**: POST for tool calls
- **Headers**: `Content-Type: application/json`

Example tool call:
```json
{
  "tool": "taskmaster",
  "arguments": {
    "command": "create_session",
    "payload": {}
  }
}
```

### Available Commands

The `taskmaster` tool accepts the following commands:

#### Session Management

**`create_session`**
```json
{
  "command": "create_session",
  "payload": {}
}
```
*Returns:* `{"session_id": "session_xyz", "environment_scanned": true}`

**`end_session`**
```json
{
  "command": "end_session", 
  "payload": {
    "session_id": "session_xyz",
    "archive": false
  }
}
```
*Returns:* Session summary with statistics and completion rates

#### Task Management

**`add_task`**
```json
{
  "command": "add_task",
  "payload": {
    "session_id": "session_xyz",
    "description": "Write a Python function to parse JSON"
  }
}
```
*Returns:* `{"task_id": "task_abc"}`

**`get_tasklist`**
```json
{
  "command": "get_tasklist",
  "payload": {
    "session_id": "session_xyz"
  }
}
```
*Returns:* Complete list of tasks with status and validation info

**`progress_to_next`**
```json
{
  "command": "progress_to_next",
  "payload": {
    "session_id": "session_xyz"
  }
}
```
*Returns:* Next incomplete task with progress statistics

#### Validation System

**`define_validation_criteria`**
```json
{
  "command": "define_validation_criteria",
  "payload": {
    "session_id": "session_xyz",
    "task_id": "task_abc",
    "criteria": ["syntax_rule", "content_contains_rule"],
    "validation_required": true
  }
}
```

**`mark_task_complete`**
```json
{
  "command": "mark_task_complete",
  "payload": {
    "session_id": "session_xyz", 
    "task_id": "task_abc",
    "evidence": {
      "code": "def parse_json(data): return json.loads(data)",
      "test_results": "All tests passed"
    }
  }
}
```
*Returns:* Validation results and completion status

**`get_validation_rules`**
```json
{
  "command": "get_validation_rules",
  "payload": {}
}
```
*Returns:* List of available validation rules

#### Environment Scanning

**`scan_environment`**
```json
{
  "command": "scan_environment",
  "payload": {
    "session_id": "session_xyz"
  }
}
```

**`get_environment`**
```json
{
  "command": "get_environment",
  "payload": {
    "session_id": "session_xyz",
    "filter": "system_tools",
    "summary": true
  }
}
```

## Validation Rules

### Built-in Rules

- **`syntax_rule`** - Validates Python/JavaScript code syntax
- **`content_contains_rule`** - Checks if content contains required strings
- **`file_exists_rule`** - Verifies that specified files exist

### Custom Rules

Create new validation rules by extending `BaseValidationRule` in `taskmaster/validation_rules/`:

```python
from taskmaster.validation_rules.base_rule import BaseValidationRule

class CustomRule(BaseValidationRule):
    @property
    def rule_name(self) -> str:
        return "custom_rule"
    
    def check(self, task, evidence) -> (bool, str):
        # Implementation
        return True, "Validation passed"
```

## Environment Scanners

### Built-in Scanners

- **`system_tool_scanner`** - Detects development tools (Python, Git, Node.js, etc.)

### Custom Scanners

Extend `BaseScanner` in `taskmaster/scanners/` to add new environment detection:

```python
from taskmaster.scanners.base_scanner import BaseScanner

class CustomScanner(BaseScanner):
    @property
    def scanner_name(self) -> str:
        return "custom_scanner"
    
    async def scan(self) -> dict:
        # Implementation
        return {"custom_data": "value"}
```

## Configuration

Edit `config.yaml` to customize:

```yaml
state_directory: 'taskmaster/state'
scanners:
  system_tool_scanner:
    timeout: 30
    tools_to_check:
      - python
      - git
      - node
      - npm
```

## Development

### Running Tests

```bash
pytest tests/ -v
```

### Test Coverage

```bash
pytest tests/ --cov=taskmaster --cov-report=html
```

## Deployment

### Smithery.ai Deployment

This server is configured for automatic deployment to Smithery.ai using the **Custom Deploy** method:

1. **Push to GitHub**: All required files (`smithery.yaml`, `Dockerfile`, source code) are included
2. **Connect Repository**: Link your GitHub repository to Smithery
3. **Deploy**: Navigate to the Deployments tab and click Deploy
4. **Configuration**: The server uses container runtime with HTTP endpoints as required by Smithery

**Technical Details:**
- **Runtime**: Container-based deployment 
- **Port**: Automatically configured via `$PORT` environment variable
- **Endpoints**: `/mcp` (GET, POST, DELETE) for Streamable HTTP connection
- **Health Check**: Built-in FastMCP health endpoint at `/health`

For deployment troubleshooting, ensure:
- Repository is public or properly connected to Smithery
- All dependencies are listed in `requirements.txt`
- `smithery.yaml` and `Dockerfile` are in the repository root

## Architecture

### Command Pattern
- All operations routed through command classes
- Lazy loading for fast cold starts
- Extensible command system

### State Management  
- JSON-based persistence in filesystem
- Session-scoped state with environment caching
- Automatic archival system

### Validation Engine
- Pluggable validation rules
- Evidence-based completion tracking
- Comprehensive audit logging

### Environment Scanner
- Async/parallel scanning
- Configurable tool detection
- Persistent environment state

## Error Handling

The server provides comprehensive error handling:
- Invalid commands return descriptive error messages
- Missing parameters are clearly identified
- Validation failures include specific feedback
- Environment scanning timeouts are handled gracefully

## License

MIT License - see LICENSE file for details

## Contributing

1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Ensure all tests pass
5. Submit a pull request
