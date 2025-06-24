# Taskmaster MCP Server Architecture

## Overview

The Taskmaster MCP Server is a production-ready Model Context Protocol server that provides intelligent task management capabilities with validation, environment scanning, and anti-hallucination features. Built on modern software architecture principles, it offers a robust foundation for AI-driven workflow management.

## Core Architecture

### Design Philosophy

The Taskmaster architecture follows several key principles:

- **Lightweight Design**: Aligns with MCP's principle that servers should be lightweight programs
- **Dependency Injection**: Centralized service management with proper lifecycle control
- **Command Pattern**: Clean separation of concerns with individual command handlers
- **Async-First**: Built for high-performance async operations
- **Validation-Driven**: Advisory validation system that guides without blocking

### System Components

```
┌─────────────────────────────────────────────────────────────┐
│                    MCP Client Interface                     │
├─────────────────────────────────────────────────────────────┤
│                    FastMCP Gateway                          │
│                   (server.py)                               │
├─────────────────────────────────────────────────────────────┤
│              TaskmasterCommandHandler                       │
│                 (Single Entry Point)                        │
├─────────────────────────────────────────────────────────────┤
│    Command Handlers Layer                                   │
│  ┌─────────────┬─────────────┬─────────────┬─────────────┐  │
│  │   Session   │Capabilities │  Tasklist   │  Execution  │  │
│  │   Handler   │   Handler   │   Handler   │   Handler   │  │
│  └─────────────┴─────────────┴─────────────┴─────────────┘  │
├─────────────────────────────────────────────────────────────┤
│              Core Services Layer                            │
│  ┌─────────────┬─────────────┬─────────────┬─────────────┐  │
│  │  Session    │ Validation  │  Workflow   │Environment  │  │
│  │  Manager    │   Engine    │   State     │  Scanner    │  │
│  └─────────────┴─────────────┴─────────────┴─────────────┘  │
├─────────────────────────────────────────────────────────────┤
│              Persistence Layer                              │
│  ┌─────────────┬─────────────┬─────────────┬─────────────┐  │
│  │   Async     │   Session   │   Config    │   State     │  │
│  │Persistence  │   Cleanup   │  Manager    │   Files     │  │
│  └─────────────┴─────────────┴─────────────┴─────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

## Key Components

### 1. Dependency Injection Container (`container.py`)

The `TaskmasterContainer` provides centralized service management with three lifecycle types:

- **Singleton**: Single instance per container (default for core services)
- **Transient**: New instance per resolution
- **Scoped**: Single instance per scope (useful for request-scoped services)

**Key Features:**
- Automatic dependency resolution
- Service registration with factory functions
- Lifecycle management
- Configuration injection

### 2. Command Handler System (`command_handler.py`)

Implements the Command Pattern with a centralized dispatcher:

- **TaskmasterCommandHandler**: Main entry point and command router
- **BaseCommandHandler**: Abstract base for all command handlers
- **Specific Handlers**: Individual handlers for each action type

**Supported Commands:**
- `create_session`: Initialize new workflow sessions
- `declare_capabilities`: Register available tools and resources
- `create_tasklist`: Define structured task lists with phases
- `map_capabilities`: Assign tools to specific task phases
- `execute_next`: Get contextual guidance for task execution
- `mark_complete`: Progress through phases and complete tasks

### 3. Session Management (`session_manager.py`)

Manages workflow sessions with persistent state:

- **Session Lifecycle**: Creation, updates, and cleanup
- **Task Management**: Structured task organization with phases
- **State Persistence**: Async file-based storage with atomic operations
- **Workflow Integration**: State machine integration for workflow control

### 4. Validation Engine (`validation_engine.py`)

Advisory validation system with pluggable rules:

- **Rule-Based Architecture**: Extensible validation rules
- **Advisory Mode**: Provides guidance without blocking execution
- **Built-in Rules**: Capability assignment, completeness, test integrity
- **Custom Rules**: Easy extension with new validation patterns

### 5. Async Session Persistence (`async_session_persistence.py`)

High-performance persistence layer:

- **Atomic Operations**: Safe concurrent access
- **Backup Management**: Automatic backup rotation
- **Windows Compatibility**: Simplified file operations for cross-platform support
- **Error Recovery**: Graceful handling of file system issues

## Design Patterns

### 1. Command Pattern
Each action is encapsulated in a dedicated command handler, providing:
- Clear separation of concerns
- Easy testing and maintenance
- Extensible command system

### 2. Dependency Injection
Services are injected rather than instantiated directly:
- Improved testability
- Loose coupling
- Configuration flexibility

### 3. Strategy Pattern
Validation rules and environment scanners use strategy pattern:
- Pluggable algorithms
- Runtime behavior modification
- Easy extension

### 4. State Machine
Workflow progression follows state machine principles:
- Predictable state transitions
- Clear workflow stages
- Robust error handling

## Data Models

### Session Model
```python
class Session:
    id: str                    # Unique session identifier
    session_name: str          # Human-readable name
    status: str               # active, ended
    tasks: List[Task]         # Ordered task list
    capabilities: EnvironmentCapabilities  # Declared tools/resources
    world_model: DynamicWorldModel        # Advanced patterns
```

### Task Model
```python
class Task:
    id: str                   # Unique task identifier
    description: str          # Task description
    status: str              # pending, completed
    current_phase: str       # planning, execution, validation
    planning_phase: ArchitecturalTaskPhase
    execution_phase: ArchitecturalTaskPhase
    validation_phase: ArchitecturalTaskPhase
```

### Phase Model
```python
class ArchitecturalTaskPhase:
    phase_name: str          # planning, execution, validation
    description: str         # Phase description
    assigned_builtin_tools: List[ToolAssignment]
    assigned_mcp_tools: List[ToolAssignment]
    assigned_resources: List[ToolAssignment]
    phase_guidance: str      # Contextual guidance
```

## Configuration

### Config System (`config.py`)
Singleton configuration management:
- YAML-based configuration
- Environment variable support
- Nested configuration access with dot notation
- Default value handling

### Key Configuration Options
```yaml
state_directory: 'taskmaster/state'
session_backup_count: 5
validation:
  advisory_mode: true
scanners:
  system_tool_scanner:
    enabled: true
```

## Error Handling

### Structured Exception System (`exceptions.py`)
- **TaskmasterError**: Base exception with error codes
- **Context Information**: Detailed error context
- **Logging Integration**: Automatic error logging
- **Error Categories**: Session, task, capability, validation errors

### Error Codes
- `SESSION_NOT_FOUND`: Session management errors
- `TASK_VALIDATION_FAILED`: Task validation issues
- `CAPABILITIES_NOT_DECLARED`: Missing capability declarations
- `CONFIG_INVALID`: Configuration problems

## Performance Considerations

### Async Architecture
- Non-blocking I/O operations
- Concurrent session handling
- Efficient resource utilization

### File System Optimization
- Atomic write operations
- Minimal file locking
- Backup rotation for data safety

### Memory Management
- Lazy loading of validation rules
- Efficient session state management
- Cleanup services for resource management

## Security

### Input Validation
- Pydantic model validation
- Type safety enforcement
- Sanitized user inputs

### File System Security
- Restricted file access patterns
- Safe path handling
- Error information sanitization

## Extensibility

### Adding New Commands
1. Create handler class extending `BaseCommandHandler`
2. Register in `TaskmasterContainer`
3. Add to command router

### Adding Validation Rules
1. Extend `BaseValidationRule`
2. Implement `rule_name` property and `check` method
3. Place in `validation_rules` directory

### Adding Environment Scanners
1. Extend `BaseScanner`
2. Implement scanning logic
3. Register in configuration

## Deployment

### MCP Server Deployment
- FastMCP integration for HTTP transport
- Uvicorn ASGI server
- CORS support for web clients
- Health check endpoints

### Connection Parameters
- **URL**: `http://localhost:8080/mcp`
- **Transport**: Streamable HTTP
- **Protocol**: Model Context Protocol v1.0

The Taskmaster MCP Server provides a robust, scalable foundation for AI-driven task management with professional-grade architecture and comprehensive validation capabilities. 