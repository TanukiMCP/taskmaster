# server.py
import os
import json
import yaml
from fastmcp import FastMCP
from pydantic import BaseModel
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn
from taskmaster.models import Session, Task, SubTask, TaskPhase, BuiltInTool, MCPTool, UserResource, EnvironmentCapabilities
import uuid
from taskmaster.config import get_config
from starlette.middleware.cors import CORSMiddleware

# Create the MCP app
mcp = FastMCP("Taskmaster")

# Global session management (like SequentialThinking manages thoughts)
_current_session = None

def _get_session_file_path():
    """Lazily get the session file path from config"""
    config = get_config()
    state_dir = config.get_state_directory()
    return os.path.join(state_dir, "current_session.json")

def _load_current_session():
    """Load the current session from disk, similar to how SequentialThinking maintains state"""
    global _current_session
    session_file = _get_session_file_path()
    
    # Ensure state directory exists
    os.makedirs(os.path.dirname(session_file), exist_ok=True)
    
    if os.path.exists(session_file):
        try:
            with open(session_file, 'r') as f:
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
        session_file = _get_session_file_path()
        os.makedirs(os.path.dirname(session_file), exist_ok=True)
        with open(session_file, 'w') as f:
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
        "llm_environment": "agentic_coding_assistant",
        "workflow_paused": False,
        "pause_reason": None,
        "validation_state": "none"  # none, pending, passed, failed
    }
    
    _save_current_session()
    return _current_session

def _assign_capabilities_to_phases(task_description: str, subtasks: list = None):
    """Intelligently assign capabilities to task phases based on LLM analysis"""
    if not _current_session or not _current_session.capabilities:
        return None
    
    # This is where the LLM should make intelligent decisions about capability assignment
    # For now, we'll provide a framework that the LLM can use to make these decisions
    
    def create_phase_with_capabilities(phase_name: str, description: str, task_desc: str):
        phase = TaskPhase(
            phase_name=phase_name,
            description=description
        )
        
        # Analyze task description to determine relevant capabilities
        task_lower = task_desc.lower()
        
        # Assign built-in tools based on task content
        for tool in _current_session.capabilities.built_in_tools:
            if any(keyword in task_lower for keyword in tool.relevant_for):
                phase.assigned_builtin_tools.append(tool.name)
                phase.requires_tool_usage = True
        
        # Assign MCP tools based on task content
        for tool in _current_session.capabilities.mcp_tools:
            if any(keyword in task_lower for keyword in tool.relevant_for):
                phase.assigned_mcp_tools.append(tool.name)
                phase.requires_tool_usage = True
        
        # Assign resources based on task content
        for resource in _current_session.capabilities.user_resources:
            if any(keyword in task_lower for keyword in resource.relevant_for):
                phase.assigned_resources.append(resource.name)
        
        return phase
    
    # Create phases for the main task
    planning_phase = create_phase_with_capabilities(
        "planning", 
        f"Plan and analyze approach for: {task_description}",
        task_description
    )
    
    execution_phase = create_phase_with_capabilities(
        "execution",
        f"Execute the planned approach for: {task_description}",
        task_description
    )
    
    validation_phase = create_phase_with_capabilities(
        "validation",
        f"Validate completion and results for: {task_description}",
        task_description
    )
    
    return {
        "planning": planning_phase,
        "execution": execution_phase,
        "validation": validation_phase
    }

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
                    "what_it_is": tool.what_it_is,
                    "what_it_does": tool.what_it_does,
                    "how_to_use": tool.how_to_use,
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
                    "what_it_is": tool.what_it_is,
                    "what_it_does": tool.what_it_does,
                    "how_to_use": tool.how_to_use,
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
                    "what_it_is": resource.what_it_is,
                    "what_it_does": resource.what_it_does,
                    "how_to_use": resource.how_to_use,
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
    # Don't append evidence here, let mark_complete handle it
    
    # Auto-complete if we have evidence and no validation required
    if task.execution_evidence and not task.validation_required:
        return True
    
    # Auto-complete if validation criteria are met
    if task.validation_required and task.evidence and task.execution_evidence:
        return True
    
    # If evidence is provided and there's no validation required, suggest completion
    if evidence and not task.validation_required:
        return True
    
    return False

def _suggest_next_actions():
    """Suggest what the LLM should do next based on current workflow state"""
    if not _current_session:
        return ["create_session"]
    
    # Check if workflow is paused for collaboration
    if _current_session.environment_context.get("workflow_paused", False):
        return ["get_status"]  # Only allow status check when paused
    
    # If no capabilities declared yet, suggest declaring them
    if not _current_session.environment_context.get("capabilities_declared", False):
        return ["declare_capabilities"]
    
    # Check if all three categories are declared (mandatory)
    caps = _current_session.capabilities
    if not caps.built_in_tools or not caps.mcp_tools or not caps.user_resources:
        return ["declare_capabilities"]
    
    incomplete_task = _get_next_incomplete_task()
    if incomplete_task:
        validation_state = _current_session.environment_context.get("validation_state", "none")
        
        # If validation failed, suggest error handling or collaboration
        if validation_state == "failed":
            return ["validation_error", "collaboration_request"]
        
        # If validation is pending, only allow validation actions
        if validation_state == "pending":
            return ["validate_task", "validation_error"]
        
        # Normal workflow progression
        if not incomplete_task.execution_started:
            return ["execute_next"]
        elif incomplete_task.validation_required and validation_state == "none":
            return ["validate_task"]
        elif validation_state == "passed" or not incomplete_task.validation_required:
            return ["execute_next"]  # Move to next task
        else:
            return ["validate_task", "mark_complete"]
    else:
        return ["create_tasklist", "add_task", "get_status"]

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
    tasklist: list = None,  # New parameter for create_tasklist
    task_ids: list = None,  # For CRUD operations
    updated_task_data: dict = None,  # For edit operations
    next_action_needed: bool = True,
    # New parameters for enhanced workflow
    validation_result: str = None,  # "passed", "failed", "inconclusive"
    error_details: str = None,
    collaboration_context: str = None,
    user_response: str = None
) -> dict:
    """
    Enhanced intelligent task management system with sophisticated workflow control.
    
    MANDATORY WORKFLOW:
    1. create_session - Create a new session
    2. declare_capabilities - Self-declare ALL capabilities with detailed descriptions
    3. create_tasklist - Create a full tasklist with capability mapping in one call
    4. CRUD operations: add_task, edit_task, delete_task for individual task management
    5. ENHANCED WORKFLOW ACTIONS:
       - execute_next: Progress to next task only after validation success
       - validate_task: Validate current task completion with evidence
       - validation_error: Handle validation failures and errors
       - collaboration_request: Pause workflow and request user input
    
    Args:
        action: The action to take:
            - 'create_session': Create new session
            - 'declare_capabilities': Self-declare capabilities with detailed descriptions
            - 'create_tasklist': Create full tasklist with capability mapping
            - 'add_task': Add individual task(s) with capability mapping
            - 'edit_task': Edit existing task(s)
            - 'delete_task': Delete task(s)
            - 'execute_next': Progress workflow only after validation success
            - 'validate_task': Validate task completion with evidence
            - 'validation_error': Handle validation failures and provide error context
            - 'collaboration_request': Pause workflow and request user collaboration
            - 'mark_complete': Mark task as complete (legacy support)
            - 'get_status': Get current session status
        
        validation_result: Result of validation ("passed", "failed", "inconclusive")
        error_details: Details about validation errors or execution problems
        collaboration_context: Context for why user collaboration is needed
        user_response: User's response to collaboration request (auto-added to tasklist)
        
        [... existing parameters ...]
    
    Returns:
        Dictionary with current state, capability mappings, and execution guidance
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
        "workflow_state": {
            "paused": False,
            "validation_state": "none",
            "can_progress": True
        },
        "status": "success"
    }
    
    try:
        # Handle user response to collaboration request
        if user_response and _current_session and _current_session.environment_context.get("workflow_paused", False):
            # Add user response as a new task to keep tasklist updated
            user_task = Task(description=f"User Response: {user_response}")
            _current_session.tasks.append(user_task)
            
            # Resume workflow
            _current_session.environment_context["workflow_paused"] = False
            _current_session.environment_context["pause_reason"] = None
            _save_current_session()
            
            result["user_response_added"] = True
            result["completion_guidance"] = "User response added to tasklist. Workflow resumed."
        
        if action == "create_session":
            _create_new_session(session_name)
            result["session_id"] = _current_session.id
            result["session_name"] = getattr(_current_session, 'session_name', None)
            result["suggested_next_actions"] = ["declare_capabilities"]
            result["completion_guidance"] = """
🚀 Session created! MANDATORY NEXT STEP: Use 'declare_capabilities' action with ALL THREE categories:

1. builtin_tools: Your core environment tools with DETAILED self-declarations
2. mcp_tools: Available MCP server tools with DETAILED self-declarations  
3. user_resources: Available docs, codebases, APIs with DETAILED self-declarations

Each capability MUST include: name, description, what_it_is, what_it_does, how_to_use, relevant_for

This is REQUIRED for intelligent task execution and capability mapping.
"""

        elif action == "declare_capabilities":
            if not _current_session:
                _create_new_session()
            
            # Validation function for capability format
            def validate_capability_format(cap_list, category_name):
                if not cap_list or not isinstance(cap_list, list):
                    return f"{category_name} must be a non-empty list"
                
                for i, cap in enumerate(cap_list):
                    if not isinstance(cap, dict):
                        return f"{category_name}[{i}] must be a dictionary"
                    
                    required_fields = ["name", "description", "what_it_is", "what_it_does", "how_to_use", "relevant_for"]
                    for field in required_fields:
                        if field not in cap or not cap[field]:
                            return f"{category_name}[{i}] missing required field: {field}"
                        if field == "relevant_for" and not isinstance(cap[field], list):
                            return f"{category_name}[{i}].relevant_for must be a list"
                
                return None
            
            # Validate all three categories are provided with proper format
            if not builtin_tools or not mcp_tools or not user_resources:
                result["error"] = "ALL THREE categories required: builtin_tools, mcp_tools, user_resources with detailed self-declarations"
                result["completion_guidance"] = "You must provide ALL THREE capability categories with detailed self-declarations including: name, description, what_it_is, what_it_does, how_to_use, relevant_for"
                return result
            
            # Validate format of each category
            for cap_list, category_name in [(builtin_tools, "builtin_tools"), (mcp_tools, "mcp_tools"), (user_resources, "user_resources")]:
                validation_error = validate_capability_format(cap_list, category_name)
                if validation_error:
                    result["error"] = validation_error
                    result["completion_guidance"] = f"Fix the capability declaration format. Each capability needs: name, description, what_it_is, what_it_does, how_to_use, relevant_for"
                    return result
            
            # Clear existing capabilities
            _current_session.capabilities = EnvironmentCapabilities()
            
            # Handle built-in tools (REQUIRED with detailed declarations)
            for tool_data in builtin_tools:
                tool = BuiltInTool(**tool_data)
                _current_session.capabilities.built_in_tools.append(tool)
            
            # Handle MCP tools (REQUIRED with detailed declarations)
            for tool_data in mcp_tools:
                if "server_name" not in tool_data:
                    tool_data["server_name"] = "unknown"  # Default server name
                tool = MCPTool(**tool_data)
                _current_session.capabilities.mcp_tools.append(tool)
            
            # Handle user resources (REQUIRED with detailed declarations)
            for resource_data in user_resources:
                if "type" not in resource_data:
                    resource_data["type"] = "documentation"  # Default type
                resource = UserResource(**resource_data)
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
                "builtin_tools": [{"name": t.name, "description": t.description, "what_it_is": t.what_it_is, "what_it_does": t.what_it_does, "how_to_use": t.how_to_use} for t in _current_session.capabilities.built_in_tools],
                "mcp_tools": [{"name": t.name, "server": t.server_name, "description": t.description, "what_it_is": t.what_it_is, "what_it_does": t.what_it_does, "how_to_use": t.how_to_use} for t in _current_session.capabilities.mcp_tools],
                "resources": [{"name": r.name, "type": r.type, "description": r.description, "what_it_is": r.what_it_is, "what_it_does": r.what_it_does, "how_to_use": r.how_to_use} for r in _current_session.capabilities.user_resources]
            }
            result["suggested_next_actions"] = ["create_tasklist"]
            result["completion_guidance"] = f"✅ ALL capabilities registered with detailed self-declarations! ({len(_current_session.capabilities.built_in_tools)} built-in, {len(_current_session.capabilities.mcp_tools)} MCP, {len(_current_session.capabilities.user_resources)} resources) Now create a full tasklist using 'create_tasklist' action."

        elif action == "create_tasklist":
            if not _current_session:
                _create_new_session()
            
            # Check if all capabilities are declared first
            if not _current_session.environment_context.get("capabilities_declared", False):
                result["error"] = "Must declare capabilities first using 'declare_capabilities' action"
                result["suggested_next_actions"] = ["declare_capabilities"]
                result["completion_guidance"] = "You must declare your available built-in tools, MCP tools, and resources with detailed self-declarations before creating tasks."
                return result
            
            # Verify all three categories are declared
            caps = _current_session.capabilities
            if not caps.built_in_tools or not caps.mcp_tools or not caps.user_resources:
                result["error"] = "Incomplete capability declaration. All three categories required with detailed self-declarations."
                result["suggested_next_actions"] = ["declare_capabilities"]
                result["completion_guidance"] = "You must declare ALL THREE: builtin_tools, mcp_tools, AND user_resources with detailed self-declarations."
                return result
            
            if not tasklist or not isinstance(tasklist, list):
                result["error"] = "tasklist parameter is required and must be a list of task descriptions or task objects"
                result["completion_guidance"] = "Provide a tasklist parameter with an array of tasks to create. Each task will have capabilities automatically mapped to planning, execution, and validation phases."
                return result
            
            created_tasks = []
            for task_item in tasklist:
                if isinstance(task_item, str):
                    task_desc = task_item
                    task = Task(description=task_desc)
                elif isinstance(task_item, dict):
                    task_desc = task_item.get("description", "")
                    task = Task(description=task_desc)
                    if "validation_criteria" in task_item:
                        task.validation_required = True
                        task.validation_criteria = task_item["validation_criteria"]
                    if "subtasks" in task_item:
                        for subtask_desc in task_item["subtasks"]:
                            subtask = SubTask(description=subtask_desc)
                            # Assign capabilities to subtask phases
                            phases = _assign_capabilities_to_phases(subtask_desc)
                            if phases:
                                subtask.planning_phase = phases["planning"]
                                subtask.execution_phase = phases["execution"]
                                subtask.validation_phase = phases["validation"]
                            task.subtasks.append(subtask)
                else:
                    continue
                
                # Assign capabilities to main task phases (MANDATORY)
                phases = _assign_capabilities_to_phases(task_desc)
                if phases:
                    task.planning_phase = phases["planning"]
                    task.execution_phase = phases["execution"]
                    task.validation_phase = phases["validation"]
                
                # Get relevant capabilities for backward compatibility
                relevant_caps = _get_relevant_capabilities_for_task(task_desc)
                task.suggested_builtin_tools = [t["name"] for t in relevant_caps["builtin_tools"]]
                task.suggested_mcp_tools = [t["name"] for t in relevant_caps["mcp_tools"]]
                task.suggested_resources = [r["name"] for r in relevant_caps["resources"]]
                
                _current_session.tasks.append(task)
                created_tasks.append({
                    "id": task.id,
                    "description": task.description,
                    "planning_phase": {
                        "assigned_tools": task.planning_phase.assigned_builtin_tools + task.planning_phase.assigned_mcp_tools if task.planning_phase else [],
                        "assigned_resources": task.planning_phase.assigned_resources if task.planning_phase else [],
                        "requires_tools": task.planning_phase.requires_tool_usage if task.planning_phase else False
                    },
                    "execution_phase": {
                        "assigned_tools": task.execution_phase.assigned_builtin_tools + task.execution_phase.assigned_mcp_tools if task.execution_phase else [],
                        "assigned_resources": task.execution_phase.assigned_resources if task.execution_phase else [],
                        "requires_tools": task.execution_phase.requires_tool_usage if task.execution_phase else False
                    },
                    "validation_phase": {
                        "assigned_tools": task.validation_phase.assigned_builtin_tools + task.validation_phase.assigned_mcp_tools if task.validation_phase else [],
                        "assigned_resources": task.validation_phase.assigned_resources if task.validation_phase else [],
                        "requires_tools": task.validation_phase.requires_tool_usage if task.validation_phase else False
                    },
                    "subtasks_count": len(task.subtasks)
                })
            
            _save_current_session()
            
            result["tasklist_created"] = True
            result["tasks_created"] = len(created_tasks)
            result["created_tasks"] = created_tasks
            result["suggested_next_actions"] = ["execute_next"]
            result["completion_guidance"] = f"✅ Tasklist created with {len(created_tasks)} tasks! Each task has capabilities mapped to planning, execution, and validation phases. Use 'execute_next' to begin execution."

        elif action == "add_task":
            if not _current_session:
                _create_new_session()
            
            # Check if all capabilities are declared first
            if not _current_session.environment_context.get("capabilities_declared", False):
                result["error"] = "Must declare capabilities first using 'declare_capabilities' action"
                result["suggested_next_actions"] = ["declare_capabilities"]
                result["completion_guidance"] = "You must declare your available built-in tools, MCP tools, and resources with detailed self-declarations before adding tasks."
                return result
            
            # Verify all three categories are declared
            caps = _current_session.capabilities
            if not caps.built_in_tools or not caps.mcp_tools or not caps.user_resources:
                result["error"] = "Incomplete capability declaration. All three categories required with detailed self-declarations."
                result["suggested_next_actions"] = ["declare_capabilities"]
                result["completion_guidance"] = "You must declare ALL THREE: builtin_tools, mcp_tools, AND user_resources with detailed self-declarations."
                return result
            
            if not task_description:
                result["error"] = "task_description is required for add_task"
                return result
            
            task = Task(description=task_description)
            if validation_criteria:
                task.validation_required = True
                task.validation_criteria = validation_criteria
            
            # MANDATORY: Assign capabilities to task phases
            phases = _assign_capabilities_to_phases(task_description)
            if phases:
                task.planning_phase = phases["planning"]
                task.execution_phase = phases["execution"]
                task.validation_phase = phases["validation"]
            
            # Get relevant capabilities for backward compatibility
            relevant_caps = _get_relevant_capabilities_for_task(task_description)
            task.suggested_builtin_tools = [t["name"] for t in relevant_caps["builtin_tools"]]
            task.suggested_mcp_tools = [t["name"] for t in relevant_caps["mcp_tools"]]
            task.suggested_resources = [r["name"] for r in relevant_caps["resources"]]
            
            _current_session.tasks.append(task)
            _save_current_session()
            
            result["task_added"] = {
                "id": task.id,
                "description": task.description,
                "planning_phase": {
                    "assigned_builtin_tools": task.planning_phase.assigned_builtin_tools if task.planning_phase else [],
                    "assigned_mcp_tools": task.planning_phase.assigned_mcp_tools if task.planning_phase else [],
                    "assigned_resources": task.planning_phase.assigned_resources if task.planning_phase else [],
                    "requires_tool_usage": task.planning_phase.requires_tool_usage if task.planning_phase else False
                },
                "execution_phase": {
                    "assigned_builtin_tools": task.execution_phase.assigned_builtin_tools if task.execution_phase else [],
                    "assigned_mcp_tools": task.execution_phase.assigned_mcp_tools if task.execution_phase else [],
                    "assigned_resources": task.execution_phase.assigned_resources if task.execution_phase else [],
                    "requires_tool_usage": task.execution_phase.requires_tool_usage if task.execution_phase else False
                },
                "validation_phase": {
                    "assigned_builtin_tools": task.validation_phase.assigned_builtin_tools if task.validation_phase else [],
                    "assigned_mcp_tools": task.validation_phase.assigned_mcp_tools if task.validation_phase else [],
                    "assigned_resources": task.validation_phase.assigned_resources if task.validation_phase else [],
                    "requires_tool_usage": task.validation_phase.requires_tool_usage if task.validation_phase else False
                }
            }
            result["relevant_capabilities"] = relevant_caps
            result["suggested_next_actions"] = ["execute_next", "add_task"]
            result["completion_guidance"] = f"Task added with capability mapping! Use 'execute_next' to get execution guidance for: {task_description}"

        elif action == "edit_task":
            if not _current_session:
                result["error"] = "No active session"
                return result
            
            if not task_ids or not updated_task_data:
                result["error"] = "task_ids and updated_task_data are required for edit_task"
                return result
            
            edited_tasks = []
            for task_id in task_ids:
                task = next((t for t in _current_session.tasks if t.id == task_id), None)
                if task:
                    # Update task fields
                    if "description" in updated_task_data:
                        task.description = updated_task_data["description"]
                        # Re-assign capabilities if description changed
                        phases = _assign_capabilities_to_phases(task.description)
                        if phases:
                            task.planning_phase = phases["planning"]
                            task.execution_phase = phases["execution"]
                            task.validation_phase = phases["validation"]
                    
                    if "validation_criteria" in updated_task_data:
                        task.validation_criteria = updated_task_data["validation_criteria"]
                        task.validation_required = bool(updated_task_data["validation_criteria"])
                    
                    if "status" in updated_task_data:
                        task.status = updated_task_data["status"]
                    
                    edited_tasks.append(task.id)
            
            _save_current_session()
            
            result["edited_tasks"] = edited_tasks
            result["suggested_next_actions"] = ["execute_next", "get_status"]
            result["completion_guidance"] = f"Edited {len(edited_tasks)} task(s) with updated capability mappings."

        elif action == "delete_task":
            if not _current_session:
                result["error"] = "No active session"
                return result
            
            if not task_ids:
                result["error"] = "task_ids is required for delete_task"
                return result
            
            deleted_tasks = []
            for task_id in task_ids:
                task_index = next((i for i, t in enumerate(_current_session.tasks) if t.id == task_id), None)
                if task_index is not None:
                    deleted_task = _current_session.tasks.pop(task_index)
                    deleted_tasks.append(deleted_task.description)
            
            _save_current_session()
            
            result["deleted_tasks"] = deleted_tasks
            result["suggested_next_actions"] = ["execute_next", "get_status"]
            result["completion_guidance"] = f"Deleted {len(deleted_tasks)} task(s)."

        elif action == "execute_next":
            if not _current_session:
                result["error"] = "No active session"
                return result
            
            # Check if workflow is paused
            if _current_session.environment_context.get("workflow_paused", False):
                result["error"] = "Workflow is paused pending user collaboration"
                result["pause_reason"] = _current_session.environment_context.get("pause_reason", "Unknown")
                result["suggested_next_actions"] = ["get_status"]
                result["completion_guidance"] = "Workflow is paused. Check status for collaboration context."
                return result
            
            # Ensure capabilities are fully declared before execution
            caps = _current_session.capabilities
            if not caps.built_in_tools or not caps.mcp_tools or not caps.user_resources:
                result["error"] = "Cannot execute tasks without complete capability declaration with detailed self-declarations"
                result["suggested_next_actions"] = ["declare_capabilities"]
                result["completion_guidance"] = "You must declare ALL capabilities (built-in tools, MCP tools, user resources) with detailed self-declarations before executing tasks."
                return result
            
            # Check validation state before proceeding
            validation_state = _current_session.environment_context.get("validation_state", "none")
            if validation_state == "failed":
                result["error"] = "Cannot proceed: Previous validation failed"
                result["suggested_next_actions"] = ["validation_error", "collaboration_request"]
                result["completion_guidance"] = "Previous task validation failed. Handle the error or request collaboration before proceeding."
                return result
            
            if validation_state == "pending":
                result["error"] = "Cannot proceed: Validation is pending"
                result["suggested_next_actions"] = ["validate_task"]
                result["completion_guidance"] = "Complete current task validation before proceeding to next task."
                return result
            
            next_task = _get_next_incomplete_task()
            if not next_task:
                result["message"] = "No incomplete tasks found"
                result["suggested_next_actions"] = ["create_tasklist", "add_task", "get_status"]
                result["completion_guidance"] = "All tasks complete! Create a new tasklist or add more tasks."
            else:
                # If current task was validated, mark it complete and move to next
                if validation_state == "passed" and next_task.execution_started:
                    next_task.status = "[X]"
                    _current_session.environment_context["validation_state"] = "none"
                    _save_current_session()
                    
                    # Get the actual next task
                    next_task = _get_next_incomplete_task()
                    if not next_task:
                        result["message"] = "All tasks completed!"
                        result["suggested_next_actions"] = ["create_tasklist", "add_task", "get_status"]
                        result["completion_guidance"] = "All tasks complete! Create a new tasklist or add more tasks."
                        return result
                
                next_task.execution_started = True
                _save_current_session()
                
                relevant_caps = _get_relevant_capabilities_for_task(next_task.description)
                
                result["current_task"] = {
                    "id": next_task.id,
                    "description": next_task.description,
                    "validation_required": next_task.validation_required,
                    "validation_criteria": next_task.validation_criteria,
                    "subtasks_count": len(next_task.subtasks)
                }
                
                # Provide detailed phase-based execution guidance
                result["phase_guidance"] = {}
                if next_task.planning_phase:
                    result["phase_guidance"]["planning"] = {
                        "description": next_task.planning_phase.description,
                        "assigned_builtin_tools": next_task.planning_phase.assigned_builtin_tools,
                        "assigned_mcp_tools": next_task.planning_phase.assigned_mcp_tools,
                        "assigned_resources": next_task.planning_phase.assigned_resources,
                        "requires_tool_usage": next_task.planning_phase.requires_tool_usage,
                        "steps": next_task.planning_phase.steps
                    }
                
                if next_task.execution_phase:
                    result["phase_guidance"]["execution"] = {
                        "description": next_task.execution_phase.description,
                        "assigned_builtin_tools": next_task.execution_phase.assigned_builtin_tools,
                        "assigned_mcp_tools": next_task.execution_phase.assigned_mcp_tools,
                        "assigned_resources": next_task.execution_phase.assigned_resources,
                        "requires_tool_usage": next_task.execution_phase.requires_tool_usage,
                        "steps": next_task.execution_phase.steps
                    }
                
                if next_task.validation_phase:
                    result["phase_guidance"]["validation"] = {
                        "description": next_task.validation_phase.description,
                        "assigned_builtin_tools": next_task.validation_phase.assigned_builtin_tools,
                        "assigned_mcp_tools": next_task.validation_phase.assigned_mcp_tools,
                        "assigned_resources": next_task.validation_phase.assigned_resources,
                        "requires_tool_usage": next_task.validation_phase.requires_tool_usage,
                        "steps": next_task.validation_phase.steps
                    }
                
                result["relevant_capabilities"] = relevant_caps
                result["execution_guidance"] = f"EXECUTE NOW with phase-based approach: {next_task.description}"
                
                # Enhanced tool summarization with detailed usage guidance
                result["available_tools_summary"] = {
                    "builtin": [f"{t['name']}: {t['what_it_does']} - {t['how_to_use']}" for t in relevant_caps["builtin_tools"]],
                    "mcp": [f"{t['name']}: {t['what_it_does']} - {t['how_to_use']}" for t in relevant_caps["mcp_tools"]],
                    "resources": [f"{r['name']}: {r['what_it_does']} - {r['how_to_use']}" for r in relevant_caps["resources"]]
                }
                
                result["suggested_next_actions"] = ["validate_task"] if next_task.validation_required else ["execute_next"]
                result["completion_guidance"] = f"Execute the task using the assigned capabilities for each phase (planning, execution, validation). {'Then validate with validate_task action.' if next_task.validation_required else 'Then call execute_next to proceed.'}"

        elif action == "validate_task":
            if not _current_session:
                result["error"] = "No active session"
                return result
            
            next_task = _get_next_incomplete_task()
            if not next_task:
                result["error"] = "No task to validate"
                return result
            
            if not next_task.execution_started:
                result["error"] = "Task has not been executed yet"
                result["suggested_next_actions"] = ["execute_next"]
                result["completion_guidance"] = "Execute the task first before validating."
                return result
            
            # Handle validation result
            if validation_result:
                if validation_result == "passed":
                    _current_session.environment_context["validation_state"] = "passed"
                    if evidence:
                        next_task.evidence.append({"evidence": evidence, "timestamp": str(uuid.uuid4())})
                    result["validation_status"] = "passed"
                    result["suggested_next_actions"] = ["execute_next"]
                    result["completion_guidance"] = "✅ Validation passed! Use 'execute_next' to proceed to next task."
                    
                elif validation_result == "failed":
                    _current_session.environment_context["validation_state"] = "failed"
                    result["validation_status"] = "failed"
                    result["suggested_next_actions"] = ["validation_error", "collaboration_request"]
                    result["completion_guidance"] = "❌ Validation failed! Use 'validation_error' to handle the failure or 'collaboration_request' for help."
                    
                elif validation_result == "inconclusive":
                    _current_session.environment_context["validation_state"] = "pending"
                    result["validation_status"] = "inconclusive"
                    result["suggested_next_actions"] = ["collaboration_request", "validation_error"]
                    result["completion_guidance"] = "⚠️ Validation inconclusive! Request collaboration or report validation error."
                
                _save_current_session()
            else:
                # Set validation as pending if no result provided
                _current_session.environment_context["validation_state"] = "pending"
                _save_current_session()
                result["validation_status"] = "pending"
                result["suggested_next_actions"] = ["validate_task"]
                result["completion_guidance"] = "Provide validation_result parameter: 'passed', 'failed', or 'inconclusive'"
            
            result["current_task"] = {
                "id": next_task.id,
                "description": next_task.description,
                "validation_criteria": next_task.validation_criteria,
                "evidence": next_task.evidence
            }

        elif action == "validation_error":
            if not _current_session:
                result["error"] = "No active session"
                return result
            
            next_task = _get_next_incomplete_task()
            if not next_task:
                result["error"] = "No task with validation error"
                return result
            
            # Record the validation error
            error_record = {
                "task_id": next_task.id,
                "error_details": error_details or "Validation error occurred",
                "timestamp": str(uuid.uuid4())
            }
            
            if not hasattr(next_task, 'validation_errors'):
                next_task.validation_errors = []
            next_task.validation_errors.append(error_record)
            
            # Reset validation state to allow retry
            _current_session.environment_context["validation_state"] = "none"
            next_task.execution_started = False  # Allow re-execution
            
            _save_current_session()
            
            result["error_recorded"] = True
            result["error_details"] = error_details
            result["suggested_next_actions"] = ["execute_next", "collaboration_request"]
            result["completion_guidance"] = "Validation error recorded. You can retry execution or request collaboration for assistance."

        elif action == "collaboration_request":
            if not _current_session:
                result["error"] = "No active session"
                return result
            
            # Pause the workflow
            _current_session.environment_context["workflow_paused"] = True
            _current_session.environment_context["pause_reason"] = collaboration_context or "LLM requested user collaboration"
            _current_session.environment_context["validation_state"] = "none"  # Reset validation state
            
            _save_current_session()
            
            result["workflow_paused"] = True
            result["collaboration_context"] = collaboration_context
            result["suggested_next_actions"] = ["get_status"]
            result["completion_guidance"] = f"🤝 Workflow paused for collaboration. Context: {collaboration_context or 'User input needed'}. Workflow will resume when user provides response."
            result["workflow_state"] = {
                "paused": True,
                "validation_state": "none",
                "can_progress": False
            }

        elif action == "mark_complete":
            # Legacy support - redirect to execute_next workflow
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
            
            # Mark as passed validation and let execute_next handle completion
            _current_session.environment_context["validation_state"] = "passed"
            _save_current_session()
            
            result["legacy_complete"] = True
            result["suggested_next_actions"] = ["execute_next"]
            result["completion_guidance"] = "Task marked for completion. Use 'execute_next' to proceed with enhanced workflow."

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
                
                # Enhanced workflow state
                result["workflow_state"] = {
                    "paused": _current_session.environment_context.get("workflow_paused", False),
                    "pause_reason": _current_session.environment_context.get("pause_reason"),
                    "validation_state": _current_session.environment_context.get("validation_state", "none"),
                    "can_progress": not _current_session.environment_context.get("workflow_paused", False)
                }
                
                current_task = _get_next_incomplete_task()
                if current_task:
                    result["current_task"] = {
                        "id": current_task.id,
                        "description": current_task.description,
                        "execution_started": current_task.execution_started,
                        "status": current_task.status,
                        "has_capability_mapping": bool(current_task.planning_phase and current_task.execution_phase and current_task.validation_phase),
                        "validation_required": current_task.validation_required
                    }
                
                result["all_tasks"] = [
                    {
                        "id": t.id,
                        "description": t.description,
                        "status": t.status,
                        "execution_started": t.execution_started,
                        "validation_required": t.validation_required,
                        "subtasks_count": len(t.subtasks),
                        "has_capability_mapping": bool(t.planning_phase and t.execution_phase and t.validation_phase)
                    }
                    for t in _current_session.tasks
                ]
                result["all_capabilities"] = {
                    "builtin_tools": [{"name": t.name, "description": t.description, "what_it_is": t.what_it_is, "what_it_does": t.what_it_does, "how_to_use": t.how_to_use} for t in _current_session.capabilities.built_in_tools],
                    "mcp_tools": [{"name": t.name, "server": t.server_name, "description": t.description, "what_it_is": t.what_it_is, "what_it_does": t.what_it_does, "how_to_use": t.how_to_use} for t in _current_session.capabilities.mcp_tools],
                    "resources": [{"name": r.name, "type": r.type, "description": r.description, "what_it_is": r.what_it_is, "what_it_does": r.what_it_does, "how_to_use": r.how_to_use} for r in _current_session.capabilities.user_resources]
                }
                result["suggested_next_actions"] = _suggest_next_actions()
                
                if result["workflow_state"]["paused"]:
                    result["completion_guidance"] = f"🤝 Workflow PAUSED: {result['workflow_state']['pause_reason']}. Waiting for user response."
                else:
                    result["completion_guidance"] = "Session active. " + ("Continue with current task." if current_task else "All tasks complete!")
        
        else:
            result["error"] = f"Unknown action: {action}"
            result["completion_guidance"] = "Valid actions: create_session, declare_capabilities, create_tasklist, add_task, edit_task, delete_task, execute_next, validate_task, validation_error, collaboration_request, mark_complete, get_status"
        
        # Update workflow state in result
        if _current_session:
            result["workflow_state"] = {
                "paused": _current_session.environment_context.get("workflow_paused", False),
                "validation_state": _current_session.environment_context.get("validation_state", "none"),
                "can_progress": not _current_session.environment_context.get("workflow_paused", False)
            }
            
    except Exception as e:
        result["error"] = f"Action failed: {str(e)}"
        result["status"] = "error"
        result["completion_guidance"] = "An error occurred. Check the error message and try again."
    
    return result

# Create FastAPI app for HTTP endpoints required by Smithery
app = FastAPI()

# Mount the MCP tool to the app
app.mount("/mcp", mcp)

# Add CORS middleware configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins - adjust for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return JSONResponse({"status": "healthy", "server": "Taskmaster MCP v3.0"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    
    # For local development, run the MCP server directly
    if os.environ.get("SMITHERY_DEPLOY") != "true":
        print(f"Starting Taskmaster MCP Server v3.0 locally on port {port}")
        mcp.run(transport='streamable-http', port=port, host="0.0.0.0")
    else:
        # For Smithery deployment, run the HTTP bridge
        print(f"Starting Taskmaster HTTP bridge for Smithery on port {port}")
        uvicorn.run(app, host="0.0.0.0", port=port) 