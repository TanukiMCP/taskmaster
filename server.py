# server.py
import os
import json
import yaml
from fastmcp import FastMCP
from pydantic import BaseModel
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn
from taskmaster.models import Session, Task, BuiltInTool, MCPTool, UserResource, EnvironmentCapabilities
import uuid

# Create the MCP app
mcp = FastMCP("Taskmaster")

# Global session management (like SequentialThinking manages thoughts)
_current_session = None
_session_state_file = "taskmaster/state/current_session.json"

def _load_current_session():
    """Load the current session from disk, similar to how SequentialThinking maintains state"""
    global _current_session
    
    # Ensure state directory exists
    os.makedirs(os.path.dirname(_session_state_file), exist_ok=True)
    
    if os.path.exists(_session_state_file):
        try:
            with open(_session_state_file, 'r') as f:
                session_data = json.load(f)
            _current_session = Session(**session_data)
        except Exception as e:
            print(f"Warning: Could not load current session: {e}")
            _current_session = None
    
    return _current_session

def _save_current_session():
    """Save the current session to disk"""
    global _current_session
    if _current_session:
        os.makedirs(os.path.dirname(_session_state_file), exist_ok=True)
        with open(_session_state_file, 'w') as f:
            json.dump(_current_session.model_dump(), f, indent=2)

def _create_new_session(session_name: str = None):
    """Create a new session with LLM-provided context"""
    global _current_session
    
    _current_session = Session()
    if session_name:
        _current_session.session_name = session_name
    
    # Set basic environment context
    _current_session.environment_context = {
        "created_at": str(uuid.uuid4()),
        "capabilities_declared": False,
        "llm_environment": "agentic_coding_assistant"
    }
    
    _save_current_session()
    return _current_session

def _get_relevant_capabilities_for_task(task_description: str):
    """Get relevant tools and resources for the current task"""
    if not _current_session or not _current_session.capabilities:
        return {"builtin_tools": [], "mcp_tools": [], "resources": []}
    
    task_lower = task_description.lower()
    result = {"builtin_tools": [], "mcp_tools": [], "resources": []}
    
    # Check built-in tools
    for tool in _current_session.capabilities.built_in_tools:
        for relevance in tool.relevant_for:
            if relevance.lower() in task_lower:
                result["builtin_tools"].append({
                    "name": tool.name,
                    "description": tool.description,
                    "capabilities": tool.capabilities
                })
                break
    
    # Check MCP tools
    for tool in _current_session.capabilities.mcp_tools:
        for relevance in tool.relevant_for:
            if relevance.lower() in task_lower:
                result["mcp_tools"].append({
                    "name": tool.name,
                    "description": tool.description,
                    "server": tool.server_name,
                    "capabilities": tool.capabilities
                })
                break
    
    # Check user resources
    for resource in _current_session.capabilities.user_resources:
        for relevance in resource.relevant_for:
            if relevance.lower() in task_lower:
                result["resources"].append({
                    "name": resource.name,
                    "type": resource.type,
                    "description": resource.description,
                    "source": resource.source_url
                })
                break
    
    return result

def _get_next_incomplete_task():
    """Get the next incomplete task"""
    if not _current_session:
        return None
    
    for task in _current_session.tasks:
        if task.status == "[ ]":
            return task
    return None

def _auto_detect_completion(task: Task, evidence: str = None):
    """Auto-detect if a task should be marked complete based on evidence"""
    if evidence:
        task.execution_evidence.append(evidence)
    
    # Auto-complete if we have evidence and no validation required
    if task.execution_evidence and not task.validation_required:
        return True
    
    # Auto-complete if validation criteria are met
    if task.validation_required and task.evidence and task.execution_evidence:
        return True
    
    return False

def _suggest_next_actions():
    """Suggest what the LLM should do next"""
    if not _current_session:
        return ["create_session"]
    
    # If no capabilities declared yet, suggest declaring them
    if not _current_session.environment_context.get("capabilities_declared", False):
        return ["declare_capabilities"]
    
    # Check if all three categories are declared (mandatory)
    caps = _current_session.capabilities
    if not caps.built_in_tools or not caps.mcp_tools or not caps.user_resources:
        return ["declare_capabilities"]
    
    incomplete_task = _get_next_incomplete_task()
    if incomplete_task:
        if not incomplete_task.execution_started:
            return ["execute_next"]
        elif incomplete_task.validation_required and not incomplete_task.evidence:
            return ["validate_task"]
        elif incomplete_task.execution_evidence:
            return ["mark_complete"]
        else:
            return ["provide_execution_evidence", "mark_complete"]
    else:
        return ["add_task", "get_status"]

class TaskmasterRequest(BaseModel):
    command: str
    payload: dict = {}

@mcp.tool()
def taskmaster(
    action: str,
    task_description: str = None,
    session_name: str = None,
    validation_criteria: list = None,
    evidence: str = None,
    execution_evidence: str = None,
    builtin_tools: list = None,
    mcp_tools: list = None,
    user_resources: list = None,
    next_action_needed: bool = True
) -> dict:
    """
    Intelligent task management system that works like SequentialThinking.
    Supports built-in tools, MCP tools, and user-added resources.
    
    Args:
        action: The action to take ('create_session', 'declare_capabilities', 'add_task', 'execute_next', 'validate_task', 'mark_complete', 'get_status')
        task_description: Description of task to add (for 'add_task')
        session_name: Name for new session (for 'create_session')
        validation_criteria: List of criteria for task validation (for 'add_task')
        evidence: Evidence of task completion (for 'validate_task')
        execution_evidence: Evidence that execution was performed (for tracking completion)
        builtin_tools: List of built-in tools available (for 'declare_capabilities')
        mcp_tools: List of MCP server tools available (for 'declare_capabilities')
        user_resources: List of user-added resources available (for 'declare_capabilities')
        next_action_needed: Whether more actions are needed (like SequentialThinking)
    
    Returns:
        Dictionary with current state, suggested actions, and available capabilities
    """
    global _current_session
    
    # Load current session if not already loaded
    if not _current_session:
        _load_current_session()
    
    result = {
        "action": action,
        "session_id": _current_session.id if _current_session else None,
        "current_task": None,
        "relevant_capabilities": {"builtin_tools": [], "mcp_tools": [], "resources": []},
        "all_capabilities": {"builtin_tools": [], "mcp_tools": [], "resources": []},
        "suggested_next_actions": [],
        "next_action_needed": next_action_needed,
        "completion_guidance": "",
        "status": "success"
    }
    
    try:
        if action == "create_session":
            _create_new_session(session_name)
            result["session_id"] = _current_session.id
            result["session_name"] = getattr(_current_session, 'session_name', None)
            result["suggested_next_actions"] = ["declare_capabilities"]
            result["completion_guidance"] = """
🚀 Session created! MANDATORY NEXT STEP: Use 'declare_capabilities' action with ALL THREE categories:

1. builtin_tools: Your core environment tools (edit_file, run_terminal_cmd, web_search, etc.)
2. mcp_tools: Available MCP server tools (taskmaster, codebase_search, etc.)
3. user_resources: Available docs, codebases, APIs, knowledge bases

This is REQUIRED for intelligent task execution and tool guidance.
"""
            
        elif action == "declare_capabilities":
            if not _current_session:
                _create_new_session()
            
            # ALL THREE CATEGORIES ARE MANDATORY
            if not builtin_tools or not mcp_tools or not user_resources:
                result["error"] = "ALL THREE categories are required: builtin_tools, mcp_tools, AND user_resources"
                result["completion_guidance"] = """
MANDATORY: You must declare ALL THREE categories for effective task execution:

1. builtin_tools: Core tools available in your environment (edit_file, run_terminal_cmd, web_search, etc.)
2. mcp_tools: MCP server tools available (taskmaster, codebase_search, etc.)  
3. user_resources: Available documentation, codebases, APIs, knowledge bases

Example:
builtin_tools=["edit_file: Create and edit files", "run_terminal_cmd: Execute commands", "web_search: Search web"]
mcp_tools=["taskmaster.taskmaster: Task management", "codebase_search: Search codebase"]
user_resources=["documentation:React Docs: React documentation", "codebase:Current Project: Project files"]
"""
                return result
            
            # Process all three categories
            _current_session.capabilities.built_in_tools = []
            _current_session.capabilities.mcp_tools = []
            _current_session.capabilities.user_resources = []
            
            # Handle built-in tools (REQUIRED)
            for tool_data in builtin_tools:
                if isinstance(tool_data, dict):
                    tool = BuiltInTool(**tool_data)
                else:
                    # Handle string format: "tool_name: description"
                    parts = str(tool_data).split(":", 1)
                    tool = BuiltInTool(
                        name=parts[0].strip(),
                        description=parts[1].strip() if len(parts) > 1 else "Built-in tool",
                        relevant_for=["file", "code", "terminal"] if any(keyword in parts[0].lower() for keyword in ["file", "edit", "terminal", "run"]) else ["general"]
                    )
                _current_session.capabilities.built_in_tools.append(tool)
            
            # Handle MCP tools (REQUIRED)
            for tool_data in mcp_tools:
                if isinstance(tool_data, dict):
                    tool = MCPTool(**tool_data)
                else:
                    # Handle string format: "server_name.tool_name: description"
                    parts = str(tool_data).split(":", 1)
                    name_parts = parts[0].strip().split(".")
                    tool = MCPTool(
                        name=name_parts[-1] if len(name_parts) > 1 else parts[0].strip(),
                        server_name=name_parts[0] if len(name_parts) > 1 else "unknown",
                        description=parts[1].strip() if len(parts) > 1 else "MCP tool",
                        relevant_for=["integration", "external"] if "mcp" in parts[0].lower() else ["general"]
                    )
                _current_session.capabilities.mcp_tools.append(tool)
            
            # Handle user resources (REQUIRED)
            for resource_data in user_resources:
                if isinstance(resource_data, dict):
                    resource = UserResource(**resource_data)
                else:
                    # Handle string format: "type:name: description"
                    parts = str(resource_data).split(":", 2)
                    resource = UserResource(
                        type=parts[0].strip() if len(parts) > 2 else "documentation",
                        name=parts[1].strip() if len(parts) > 2 else parts[0].strip(),
                        description=parts[2].strip() if len(parts) > 2 else (parts[1].strip() if len(parts) > 1 else "User resource"),
                        relevant_for=["documentation", "reference"] if "doc" in parts[0].lower() else ["knowledge"]
                    )
                _current_session.capabilities.user_resources.append(resource)
            
            # Mark capabilities as fully declared
            _current_session.environment_context["capabilities_declared"] = True
            _save_current_session()
            
            result["capabilities_declared"] = {
                "builtin_tools": len(_current_session.capabilities.built_in_tools),
                "mcp_tools": len(_current_session.capabilities.mcp_tools),
                "user_resources": len(_current_session.capabilities.user_resources)
            }
            result["all_capabilities"] = {
                "builtin_tools": [{"name": t.name, "description": t.description} for t in _current_session.capabilities.built_in_tools],
                "mcp_tools": [{"name": t.name, "server": t.server_name, "description": t.description} for t in _current_session.capabilities.mcp_tools],
                "resources": [{"name": r.name, "type": r.type, "description": r.description} for r in _current_session.capabilities.user_resources]
            }
            result["suggested_next_actions"] = ["add_task"]
            result["completion_guidance"] = f"✅ ALL capabilities registered! ({len(_current_session.capabilities.built_in_tools)} built-in, {len(_current_session.capabilities.mcp_tools)} MCP, {len(_current_session.capabilities.user_resources)} resources) Now add tasks using 'add_task' action."
            
        elif action == "add_task":
            if not _current_session:
                _create_new_session()
            
            # Check if all capabilities are declared first
            if not _current_session.environment_context.get("capabilities_declared", False):
                result["error"] = "Must declare capabilities first using 'declare_capabilities' action"
                result["suggested_next_actions"] = ["declare_capabilities"]
                result["completion_guidance"] = "You must declare your available built-in tools, MCP tools, and resources before adding tasks."
                return result
            
            # Verify all three categories are declared
            caps = _current_session.capabilities
            if not caps.built_in_tools or not caps.mcp_tools or not caps.user_resources:
                result["error"] = "Incomplete capability declaration. All three categories required."
                result["suggested_next_actions"] = ["declare_capabilities"]
                result["completion_guidance"] = "You must declare ALL THREE: builtin_tools, mcp_tools, AND user_resources."
                return result
            
            if not task_description:
                result["error"] = "task_description is required for add_task"
                return result
            
            task = Task(description=task_description)
            if validation_criteria:
                task.validation_required = True
                task.validation_criteria = validation_criteria
            
            # Get relevant capabilities for this task
            relevant_caps = _get_relevant_capabilities_for_task(task_description)
            task.suggested_builtin_tools = [t["name"] for t in relevant_caps["builtin_tools"]]
            task.suggested_mcp_tools = [t["name"] for t in relevant_caps["mcp_tools"]]
            task.suggested_resources = [r["name"] for r in relevant_caps["resources"]]
            
            _current_session.tasks.append(task)
            _save_current_session()
            
            result["task_id"] = task.id
            result["task_added"] = task_description
            result["suggested_capabilities"] = {
                "builtin_tools": task.suggested_builtin_tools,
                "mcp_tools": task.suggested_mcp_tools,
                "resources": task.suggested_resources
            }
            result["relevant_capabilities"] = relevant_caps
            result["suggested_next_actions"] = ["execute_next", "add_task"]
            result["completion_guidance"] = f"Task added! Use 'execute_next' to get execution guidance for: {task_description}"
            
        elif action == "execute_next":
            if not _current_session:
                result["error"] = "No active session"
                return result
            
            # Ensure capabilities are fully declared before execution
            caps = _current_session.capabilities
            if not caps.built_in_tools or not caps.mcp_tools or not caps.user_resources:
                result["error"] = "Cannot execute tasks without complete capability declaration"
                result["suggested_next_actions"] = ["declare_capabilities"]
                result["completion_guidance"] = "You must declare ALL capabilities (built-in tools, MCP tools, user resources) before executing tasks."
                return result
            
            next_task = _get_next_incomplete_task()
            if not next_task:
                result["message"] = "No incomplete tasks found"
                result["suggested_next_actions"] = ["add_task", "get_status"]
                result["completion_guidance"] = "All tasks complete! Add more tasks or check status."
            else:
                next_task.execution_started = True
                _save_current_session()
                
                relevant_caps = _get_relevant_capabilities_for_task(next_task.description)
                
                result["current_task"] = {
                    "id": next_task.id,
                    "description": next_task.description,
                    "validation_required": next_task.validation_required,
                    "validation_criteria": next_task.validation_criteria
                }
                result["relevant_capabilities"] = relevant_caps
                result["execution_guidance"] = f"EXECUTE NOW: {next_task.description}"
                result["available_tools_summary"] = {
                    "builtin": [t["name"] for t in relevant_caps["builtin_tools"]],
                    "mcp": [t["name"] for t in relevant_caps["mcp_tools"]],
                    "resources": [r["name"] for r in relevant_caps["resources"]]
                }
                result["suggested_next_actions"] = ["mark_complete"] if not next_task.validation_required else ["validate_task", "mark_complete"]
                result["completion_guidance"] = f"Execute the task using available tools and resources, then call 'mark_complete' with execution_evidence parameter."
            
        elif action == "validate_task":
            if not _current_session:
                result["error"] = "No active session"
                return result
            
            next_task = _get_next_incomplete_task()
            if not next_task:
                result["error"] = "No task to validate"
                return result
            
            if evidence:
                next_task.evidence.append({"evidence": evidence, "timestamp": str(uuid.uuid4())})
                _save_current_session()
                result["validation_added"] = evidence
            
            result["current_task"] = {
                "id": next_task.id,
                "description": next_task.description,
                "validation_criteria": next_task.validation_criteria,
                "evidence": next_task.evidence
            }
            result["suggested_next_actions"] = ["mark_complete"]
            result["completion_guidance"] = "Validation evidence added. Use 'mark_complete' to finish this task."
            
        elif action == "mark_complete":
            if not _current_session:
                result["error"] = "No active session"
                return result
            
            next_task = _get_next_incomplete_task()
            if not next_task:
                result["error"] = "No task to complete"
                return result
            
            # Add execution evidence if provided
            if execution_evidence:
                next_task.execution_evidence.append(execution_evidence)
            
            # Auto-detect completion or force complete
            should_complete = _auto_detect_completion(next_task, execution_evidence)
            if should_complete or execution_evidence:
                next_task.status = "[X]"
                _save_current_session()
                
                result["completed_task"] = next_task.description
                result["completion_evidence"] = next_task.execution_evidence
                result["suggested_next_actions"] = _suggest_next_actions()
                result["completion_guidance"] = "Task marked complete! " + ("Ready for next task." if _get_next_incomplete_task() else "All tasks finished!")
            else:
                result["error"] = "Task cannot be auto-completed. Provide execution_evidence parameter."
                result["completion_guidance"] = "To mark complete, provide execution_evidence parameter showing what you did."
            
        elif action == "get_status":
            if not _current_session:
                result["message"] = "No active session"
                result["suggested_next_actions"] = ["create_session"]
                result["completion_guidance"] = "No session active. Use 'create_session' to start."
            else:
                result["session_id"] = _current_session.id
                result["session_name"] = _current_session.session_name
                result["total_tasks"] = len(_current_session.tasks)
                result["completed_tasks"] = len([t for t in _current_session.tasks if t.status == "[X]"])
                result["capabilities_declared"] = _current_session.environment_context.get("capabilities_declared", False)
                
                current_task = _get_next_incomplete_task()
                if current_task:
                    result["current_task"] = {
                        "id": current_task.id,
                        "description": current_task.description,
                        "execution_started": current_task.execution_started,
                        "status": current_task.status
                    }
                
                result["all_tasks"] = [
                    {
                        "id": t.id,
                        "description": t.description,
                        "status": t.status,
                        "execution_started": t.execution_started,
                        "validation_required": t.validation_required
                    }
                    for t in _current_session.tasks
                ]
                result["all_capabilities"] = {
                    "builtin_tools": [{"name": t.name, "description": t.description} for t in _current_session.capabilities.built_in_tools],
                    "mcp_tools": [{"name": t.name, "server": t.server_name, "description": t.description} for t in _current_session.capabilities.mcp_tools],
                    "resources": [{"name": r.name, "type": r.type, "description": r.description} for r in _current_session.capabilities.user_resources]
                }
                result["suggested_next_actions"] = _suggest_next_actions()
                result["completion_guidance"] = "Session active. " + ("Continue with current task." if current_task else "All tasks complete!")
        
        else:
            result["error"] = f"Unknown action: {action}"
            result["completion_guidance"] = "Valid actions: create_session, declare_capabilities, add_task, execute_next, validate_task, mark_complete, get_status"
            
    except Exception as e:
        result["error"] = f"Action failed: {str(e)}"
        result["status"] = "error"
        result["completion_guidance"] = "An error occurred. Check the error message and try again."
    
    return result

# Create FastAPI app for HTTP endpoints required by Smithery
app = FastAPI()

@app.get("/mcp")
@app.post("/mcp") 
@app.delete("/mcp")
async def mcp_endpoint(request: Request):
    """HTTP endpoint required by Smithery for Streamable HTTP connection."""
    # Parse configuration from query parameters (Smithery passes config this way)
    config = dict(request.query_params)
    
    # Return server info for discovery
    return JSONResponse({
        "jsonrpc": "2.0",
        "result": {
            "protocolVersion": "2024-11-05",
            "capabilities": {
                "tools": {}
            },
            "serverInfo": {
                "name": "Taskmaster",
                "version": "3.0.0"
            },
            "tools": [
                {
                    "name": "taskmaster",
                    "description": "Intelligent task management with comprehensive capability assessment (built-in tools, MCP tools, user resources)",
                    "inputSchema": {
                        "type": "object", 
                        "properties": {
                            "action": {
                                "type": "string",
                                "description": "The action to take",
                                "enum": ["create_session", "declare_capabilities", "add_task", "execute_next", "validate_task", "mark_complete", "get_status"]
                            },
                            "task_description": {
                                "type": "string",
                                "description": "Description of task to add (for add_task)"
                            },
                            "session_name": {
                                "type": "string", 
                                "description": "Name for new session (for create_session)"
                            },
                            "validation_criteria": {
                                "type": "array",
                                "description": "List of criteria for task validation"
                            },
                            "evidence": {
                                "type": "string",
                                "description": "Evidence of task completion (for validate_task)"
                            },
                            "execution_evidence": {
                                "type": "string", 
                                "description": "Evidence that execution was performed"
                            },
                            "builtin_tools": {
                                "type": "array",
                                "description": "List of built-in tools available (edit_file, run_terminal_cmd, etc.)"
                            },
                            "mcp_tools": {
                                "type": "array",
                                "description": "List of MCP server tools available"
                            },
                            "user_resources": {
                                "type": "array",
                                "description": "List of user-added resources (docs, codebases, etc.)"
                            },
                            "next_action_needed": {
                                "type": "boolean",
                                "description": "Whether more actions are needed"
                            }
                        },
                        "required": ["action"]
                    }
                }
            ]
        }
    })

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return JSONResponse({"status": "healthy", "server": "Taskmaster MCP v3.0"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    
    # For local development, run the MCP server directly
    if os.environ.get("SMITHERY_DEPLOY") != "true":
        print(f"Starting Taskmaster MCP Server v3.0 locally on port {port}")
        mcp.run(transport='streamable-http', port=port, host="0.0.0.0", path="/mcp")
    else:
        # For Smithery deployment, run the HTTP bridge
        print(f"Starting Taskmaster HTTP bridge for Smithery on port {port}")
        uvicorn.run(app, host="0.0.0.0", port=port) 