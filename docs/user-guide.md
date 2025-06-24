# Taskmaster MCP Server User Guide

## Overview

The Taskmaster MCP Server is a powerful Model Context Protocol server that provides intelligent task management capabilities. It helps AI agents and users organize complex workflows through structured task lists, capability mapping, and validation-driven execution.

## Key Features

- **Structured Task Management**: Organize work into planning, execution, and validation phases
- **Capability Mapping**: Assign specific tools to task phases for guided execution
- **Advisory Validation**: Get helpful guidance without workflow blocking
- **Session Persistence**: Maintain state across interactions
- **Environment Scanning**: Automatically detect available tools and resources
- **Anti-Hallucination**: Validation engine helps ensure accurate task completion

## Installation

### Prerequisites

- Python 3.8 or higher
- pip package manager
- 2GB available disk space
- Network access for package installation

### Quick Start

1. **Download and Setup**
   ```bash
   git clone <repository-url>
   cd tanukimcp-taskmaster
   pip install -r requirements.txt
   ```

2. **Start the Server**
   ```bash
   python server.py
   ```

3. **Verify Installation**
   The server will start on `http://localhost:8080/mcp` and display:
   ```
   Starting Taskmaster MCP Server v3.0 locally on port 8080
   INFO: Uvicorn running on http://0.0.0.0:8080
   ```

## MCP Client Configuration

### Cursor IDE Setup

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

### Claude Desktop Setup

Add to your Claude Desktop configuration:

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

### Other MCP Clients

For other MCP-compatible clients, use these connection parameters:
- **URL**: `http://localhost:8080/mcp`
- **Transport**: HTTP
- **Protocol**: Model Context Protocol v1.0

## Basic Usage

### 1. Create a Session

Start by creating a new workflow session:

```
Action: create_session
Parameters:
- task_description: "Create a web application with user authentication"
- session_name: "webapp_project"
```

**Response:**
```json
{
  "action": "create_session",
  "session_id": "12345678-1234-1234-1234-123456789abc",
  "status": "success",
  "suggested_next_actions": ["declare_capabilities"]
}
```

### 2. Declare Your Capabilities

Tell Taskmaster what tools and resources you have available:

```
Action: declare_capabilities
Parameters:
builtin_tools:
- name: "edit_file"
  description: "Create and edit files with precise changes"
- name: "run_terminal_cmd"
  description: "Execute terminal commands"
- name: "read_file"
  description: "Read file contents"

mcp_tools:
- name: "taskmaster"
  server_name: "taskmaster"
  description: "Task management with validation"

user_resources:
- name: "project_codebase"
  type: "codebase"
  description: "Existing project source code"
```

### 3. Create Task List

Define your tasks with structured phases:

```
Action: create_tasklist
Parameters:
tasklist:
- description: "Set up project structure and dependencies"
  planning_phase:
    description: "Plan directory structure and choose dependencies"
  execution_phase:
    description: "Create directories and install packages"
  validation_phase:
    description: "Verify project setup is complete"

- description: "Implement user authentication system"
  planning_phase:
    description: "Design authentication flow and security requirements"
  execution_phase:
    description: "Code authentication endpoints and middleware"
  validation_phase:
    description: "Test authentication functionality"
```

### 4. Map Capabilities to Tasks

Assign specific tools to each task phase:

```
Action: map_capabilities
Parameters:
task_mappings:
- task_id: "task_abc123"
  planning_phase:
    assigned_builtin_tools:
    - tool_name: "read_file"
      usage_purpose: "Review existing code structure"
      specific_actions: ["Read package.json", "Review directory structure"]
      expected_outcome: "Understanding of current project state"
      priority: "critical"
  
  execution_phase:
    assigned_builtin_tools:
    - tool_name: "edit_file"
      usage_purpose: "Create new project files"
      specific_actions: ["Create package.json", "Set up directory structure"]
      expected_outcome: "Project structure established"
      priority: "critical"
    - tool_name: "run_terminal_cmd"
      usage_purpose: "Install dependencies"
      specific_actions: ["npm install", "pip install requirements"]
      expected_outcome: "Dependencies installed successfully"
      priority: "normal"
```

### 5. Execute Tasks

Get guided execution for each phase:

```
Action: execute_next
```

**Response provides:**
- Current task and phase information
- Assigned tools with detailed guidance
- Specific actions to take
- Expected outcomes
- Execution strategy

### 6. Mark Phases Complete

Progress through workflow phases:

```
Action: mark_complete
```

This automatically progresses from:
- Planning → Execution → Validation → Next Task

## Advanced Usage

### World Model Initialization

For complex projects, initialize a dynamic world model:

```
Action: initialize_world_model
Parameters:
target_files: ["src/", "docs/", "config/"]
analysis_scope: "full_system"
```

### Hierarchical Planning

Create multi-level planning for complex tasks:

```
Action: create_hierarchical_plan
Parameters:
high_level_steps:
- description: "Backend Development"
  sub_tasks: ["Database design", "API endpoints", "Authentication"]
- description: "Frontend Development"
  sub_tasks: ["UI components", "State management", "API integration"]
```

### Adversarial Review

Set up quality assurance loops:

```
Action: initiate_adversarial_review
Parameters:
generated_content: "Implementation code or documentation"
```

### Host Grounding

Record real execution results for accuracy:

```
Action: record_host_grounding
Parameters:
command_executed: "npm test"
stdout: "All tests passed"
stderr: ""
exit_code: 0
```

## Best Practices

### Task Organization

1. **Break Down Complex Tasks**
   - Split large tasks into manageable phases
   - Each task should have a clear, specific goal
   - Use descriptive task names

2. **Phase Structure**
   - **Planning**: Analysis, design, and preparation
   - **Execution**: Implementation and creation
   - **Validation**: Testing, review, and verification

3. **Tool Assignment**
   - Assign tools with specific purposes
   - Include expected outcomes
   - Set appropriate priorities

### Capability Declaration

1. **Be Comprehensive**
   - Declare all available tools
   - Include detailed descriptions
   - Specify tool capabilities accurately

2. **Resource Documentation**
   - Document available codebases
   - Specify resource types clearly
   - Include access information

### Workflow Management

1. **Session Organization**
   - Use descriptive session names
   - Group related tasks in single sessions
   - Clean up completed sessions

2. **Progress Tracking**
   - Mark phases complete promptly
   - Review validation feedback
   - Address advisory guidance

## Configuration

### Server Configuration

Edit `config.yaml` to customize behavior:

```yaml
# State management
state_directory: 'taskmaster/state'
session_backup_count: 5

# Validation settings
validation:
  advisory_mode: true
  rules:
    - capability_assignment
    - completeness
    - test_integrity

# Environment scanning
scanners:
  system_tool_scanner:
    enabled: true
    scan_interval: 300
```

### Environment Variables

- `PORT`: Server port (default: 8080)
- `LOG_LEVEL`: Logging verbosity (INFO, DEBUG, WARNING, ERROR)
- `SMITHERY_DEPLOY`: Deployment mode flag

## Troubleshooting

### Common Issues

#### Server Won't Start

**Problem**: Port already in use
```
Error: [Errno 48] Address already in use
```

**Solution**: Change port or stop conflicting process
```bash
# Change port
PORT=8081 python server.py

# Or kill existing process
lsof -ti:8080 | xargs kill
```

#### Connection Issues

**Problem**: MCP client can't connect
```
Error: Connection refused
```

**Solutions**:
1. Verify server is running
2. Check firewall settings
3. Confirm correct URL in client config
4. Restart both server and client

#### Session Persistence Errors

**Problem**: Session state not saving
```
Error: Permission denied writing to state directory
```

**Solutions**:
1. Check directory permissions
2. Verify disk space
3. Review state_directory configuration

### Validation Warnings

The advisory validation system provides helpful guidance:

- **Capability Assignment**: Tools not being used as assigned
- **Completeness**: Placeholder or incomplete implementations
- **Test Integrity**: Issues with test modifications

These are advisory only and won't block workflow progress.

### Performance Tips

1. **Session Management**
   - End sessions when complete
   - Use descriptive session names
   - Regular cleanup of old sessions

2. **Task Organization**
   - Keep tasks focused and specific
   - Use appropriate phase structure
   - Assign tools efficiently

3. **Resource Usage**
   - Declare only needed capabilities
   - Use appropriate tool priorities
   - Monitor system resources

## Examples

### Web Development Project

```
# 1. Create session
create_session:
  task_description: "Build e-commerce website"
  session_name: "ecommerce_project"

# 2. Declare capabilities
declare_capabilities:
  builtin_tools:
    - name: "edit_file"
      description: "Create and edit source files"
    - name: "run_terminal_cmd"
      description: "Execute build and test commands"
  
  user_resources:
    - name: "design_mockups"
      type: "documentation"
      description: "UI/UX design specifications"

# 3. Create structured tasks
create_tasklist:
  tasklist:
    - description: "Set up development environment"
      planning_phase:
        description: "Choose tech stack and tools"
      execution_phase:
        description: "Install and configure development tools"
      validation_phase:
        description: "Verify environment setup"
```

### Documentation Project

```
# 1. Session for documentation
create_session:
  task_description: "Create comprehensive API documentation"
  session_name: "api_docs"

# 2. Declare documentation tools
declare_capabilities:
  builtin_tools:
    - name: "read_file"
      description: "Read source code for API analysis"
    - name: "edit_file"
      description: "Create documentation files"
  
  user_resources:
    - name: "api_codebase"
      type: "codebase"
      description: "REST API implementation"

# 3. Documentation tasks
create_tasklist:
  tasklist:
    - description: "Analyze API endpoints"
      planning_phase:
        description: "Review code and identify all endpoints"
      execution_phase:
        description: "Document endpoint specifications"
      validation_phase:
        description: "Verify documentation accuracy"
```

## Support

For additional help:

1. **Check Logs**: Review server logs for detailed error information
2. **Configuration**: Verify all configuration files are correct
3. **Documentation**: Refer to architecture and developer guides
4. **Community**: Check project repository for updates and discussions

The Taskmaster MCP Server provides powerful workflow management capabilities while maintaining simplicity and reliability. Follow this guide to get the most out of your task management experience. 