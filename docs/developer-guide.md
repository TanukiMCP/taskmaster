# Taskmaster MCP Server Developer Guide

## Getting Started

### Prerequisites

- Python 3.8+
- pip package manager
- Basic understanding of async/await patterns
- Familiarity with Model Context Protocol (MCP)

### Installation

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd tanukimcp-taskmaster
   ```

2. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure the server**
   ```bash
   # Edit config.yaml with your settings
   cp config.yaml.example config.yaml
   ```

4. **Run the server**
   ```bash
   python server.py
   ```

The server will start on `http://localhost:8080/mcp`

## Core Development Concepts

### 1. Command Handler Development

All functionality is implemented through command handlers that extend `BaseCommandHandler`:

```python
from taskmaster.command_handler import BaseCommandHandler, TaskmasterCommand, TaskmasterResponse

class MyCustomHandler(BaseCommandHandler):
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        # Implementation logic here
        return TaskmasterResponse(
            action="my_custom_action",
            status="success",
            completion_guidance="Action completed successfully"
        )
```

**Key Points:**
- All handlers are async
- Use dependency injection for services
- Return structured responses
- Provide helpful guidance messages

### 2. Service Registration

Register services in the dependency injection container:

```python
# In container.py
def _register_core_services(self) -> None:
    self.register(
        MyService,
        lambda: MyService(config=self._config),
        ServiceLifecycle.SINGLETON
    )
```

**Lifecycle Options:**
- `SINGLETON`: One instance per container
- `TRANSIENT`: New instance per resolution
- `SCOPED`: One instance per scope

### 3. Model Definition

Use Pydantic models for type safety and validation:

```python
from pydantic import BaseModel, Field
from typing import List, Optional

class MyModel(BaseModel):
    id: str = Field(..., description="Unique identifier")
    name: str = Field(..., description="Display name")
    optional_field: Optional[str] = None
```

## API Reference

### Core Commands

#### create_session
Creates a new workflow session.

**Parameters:**
- `task_description` (optional): Description of the main task
- `session_name` (optional): Human-readable session name

**Response:**
```json
{
  "action": "create_session",
  "session_id": "uuid-string",
  "status": "success",
  "suggested_next_actions": ["declare_capabilities"]
}
```

#### declare_capabilities
Declares available tools and resources.

**Parameters:**
- `builtin_tools`: List of built-in tools with name and description
- `mcp_tools`: List of MCP tools with server_name
- `user_resources`: List of user resources with type

**Example:**
```python
builtin_tools = [
    {
        "name": "edit_file",
        "description": "Create and edit files with precise changes"
    }
]

mcp_tools = [
    {
        "name": "taskmaster",
        "server_name": "taskmaster",
        "description": "Task management capabilities"
    }
]

user_resources = [
    {
        "name": "project_codebase",
        "type": "codebase",
        "description": "Complete project source code"
    }
]
```

#### create_tasklist
Creates structured task lists with phases.

**Parameters:**
- `tasklist`: List of task definitions

**Task Structure:**
```python
task = {
    "description": "Task description",
    "planning_phase": {
        "description": "Planning phase description"
    },
    "execution_phase": {
        "description": "Execution phase description"
    }
}
```

#### map_capabilities
Assigns tools to specific task phases.

**Parameters:**
- `task_mappings`: List of capability assignments

**Mapping Structure:**
```python
mapping = {
    "task_id": "task-uuid",
    "planning_phase": {
        "assigned_builtin_tools": [
            {
                "tool_name": "edit_file",
                "usage_purpose": "Why this tool is needed",
                "specific_actions": ["List of specific actions"],
                "expected_outcome": "What should be achieved",
                "priority": "critical|normal|low"
            }
        ]
    }
}
```

#### execute_next
Gets contextual guidance for the next task phase.

**Response includes:**
- Current task information
- Current phase details
- Assigned tools with detailed guidance
- Execution strategy

#### mark_complete
Marks current phase complete and progresses workflow.

**Behavior:**
- Progresses from planning → execution
- Completes task after execution phase
- Moves to next task if available

## Extension Guide

### Adding Custom Commands

1. **Create the handler class:**

```python
# taskmaster/command_handler.py
class MyCustomHandler(BaseCommandHandler):
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        
        # Your logic here
        
        return TaskmasterResponse(
            action="my_custom_action",
            session_id=session.id if session else None,
            status="success",
            completion_guidance="Custom action completed"
        )
```

2. **Register in the container:**

```python
# taskmaster/container.py
def _register_command_handlers(self) -> None:
    handlers = {
        # ... existing handlers ...
        "my_custom_action": MyCustomHandler(session_manager),
    }
```

3. **Update the main tool:**

```python
# server.py
@mcp.tool()
async def taskmaster(
    action: str,
    # ... existing parameters ...
    my_custom_param: Optional[str] = None,  # Add new parameters as needed
) -> dict:
```

### Adding Environment Scanners

1. **Create the scanner class:**

```python
# taskmaster/scanners/my_custom_scanner.py
from typing import Dict, Any, List
from .base_scanner import BaseScanner

class MyCustomScanner(BaseScanner):
    def __init__(self, config: Dict[str, Any]):
        super().__init__(config)
        self.scanner_name = "my_custom_scanner"
    
    async def scan(self) -> Dict[str, Any]:
        # Scanning logic here
        return {
            "scanner_type": "my_custom_scanner",
            "results": {},
            "timestamp": "2025-01-27T00:00:00Z"
        }
```

2. **Register in configuration:**

```yaml
# config.yaml
scanners:
  my_custom_scanner:
    enabled: true
    custom_setting: "value"
```

## Testing

### Unit Testing

```python
import pytest
from taskmaster.command_handler import MyCustomHandler
from taskmaster.session_manager import SessionManager

@pytest.mark.asyncio
async def test_my_custom_handler():
    # Setup
    session_manager = SessionManager("test_state")
    handler = MyCustomHandler(session_manager)
    
    # Test
    command = TaskmasterCommand(action="my_custom_action")
    response = await handler.handle(command)
    
    # Assert
    assert response.status == "success"
```

### Integration Testing

```python
@pytest.mark.asyncio
async def test_full_workflow():
    # Test complete workflow from session creation to completion
    container = get_container()
    command_handler = container.resolve(TaskmasterCommandHandler)
    
    # Create session
    response = await command_handler.execute(
        TaskmasterCommand(action="create_session")
    )
    assert response.status == "success"
    
    # Continue workflow...
```

## Configuration

### Environment Variables

- `PORT`: Server port (default: 8080)
- `SMITHERY_DEPLOY`: Deployment mode flag
- `LOG_LEVEL`: Logging level

### Configuration File

```yaml
# config.yaml
state_directory: 'taskmaster/state'
session_backup_count: 5

scanners:
  system_tool_scanner:
    enabled: true
    scan_interval: 300

logging:
  level: INFO
  format: "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
```

## Error Handling

### Custom Exceptions

```python
from taskmaster.exceptions import TaskmasterError, ErrorCode

class MyCustomError(TaskmasterError):
    def __init__(self, message: str, details: Dict[str, Any] = None):
        super().__init__(
            message=message,
            error_code=ErrorCode.CUSTOM_ERROR,
            details=details
        )
```

### Error Handling in Handlers

```python
async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
    try:
        # Handler logic
        pass
    except TaskmasterError as e:
        return TaskmasterResponse(
            action=command.action,
            status="error",
            error_details=str(e),
            completion_guidance=f"Error: {e.message}"
        )
    except Exception as e:
        # Log unexpected errors
        logger.error(f"Unexpected error in {self.__class__.__name__}: {e}")
        return TaskmasterResponse(
            action=command.action,
            status="error",
            completion_guidance="An unexpected error occurred"
        )
```

## Performance Optimization

### Async Best Practices

1. **Use async/await consistently**
2. **Avoid blocking operations in async functions**
3. **Use connection pooling for external services**
4. **Implement proper timeout handling**

### Memory Management

```python
# Use weak references for large objects
import weakref

class MyService:
    def __init__(self):
        self._cache = weakref.WeakValueDictionary()
    
    async def cleanup(self):
        # Implement cleanup logic
        self._cache.clear()
```

### File System Optimization

- Use atomic operations for critical data
- Implement backup rotation
- Handle concurrent access gracefully

## Deployment

### Local Development

```bash
python server.py
```

### Production Deployment

```bash
# Using uvicorn directly
uvicorn server:app --host 0.0.0.0 --port 8080

# Using Docker
docker build -t taskmaster-mcp .
docker run -p 8080:8080 taskmaster-mcp
```

### Health Monitoring

The server provides health check endpoints:

- `GET /health`: Basic health check
- `GET /metrics`: Performance metrics (if enabled)

## Troubleshooting

### Common Issues

1. **Session persistence errors**
   - Check file permissions
   - Verify state directory exists
   - Review disk space

2. **Command handler registration issues**
   - Verify handler is registered in container
   - Check for circular dependencies
   - Review import statements

### Debug Mode

Enable debug logging:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Log Analysis

Key log messages to monitor:

- `TaskmasterContainer initialized`: Successful startup
- `Session created`: Session management
- `Command executed`: Command processing

This developer guide provides comprehensive information for extending and maintaining the Taskmaster MCP Server. For additional support, refer to the architecture documentation and source code comments. 