# server.py
import asyncio
import logging
import os
from fastmcp import FastMCP
from typing import Optional, List, Dict, Any

# Import project-specific components
from taskmaster.container import get_container, TaskmasterContainer
from taskmaster.command_handler import TaskmasterCommandHandler, TaskmasterCommand
from taskmaster.schemas import create_flexible_response, validate_request, extract_guidance
from taskmaster.exceptions import TaskmasterError

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create the FastMCP server
# CORS is enabled by default for streamable-http transport
mcp = FastMCP("Taskmaster")

# Global container - initialize once
container: Optional[TaskmasterContainer] = None

async def get_command_handler():
    """Get the command handler, initializing container if needed."""
    global container
    if container is None:
        logger.info("Initializing container...")
        container = get_container()
        logger.info("Container initialized.")
    return container.resolve(TaskmasterCommandHandler)

async def execute_taskmaster_logic(data: dict) -> dict:
    """Execute taskmaster command - simplified."""
    try:
        command_handler = await get_command_handler()
        
        # Process the request
        enhanced_request = validate_request(data)
        command = TaskmasterCommand(**enhanced_request)
        response = await command_handler.execute(command)
        
        return response.to_dict()
        
    except Exception as e:
        logger.error(f"Error during taskmaster execution: {e}", exc_info=True)
        return create_flexible_response(
            action=data.get("action", "error"),
            status="error",
            completion_guidance=f"Error: {str(e)}",
            error_details=str(e),
            next_action_needed=True
        )

@mcp.tool()
async def taskmaster(
    action: str,
    task_description: Optional[str] = None,
    session_name: Optional[str] = None,
    builtin_tools: Optional[List[Dict[str, Any]]] = None,
    mcp_tools: Optional[List[Dict[str, Any]]] = None,
    user_resources: Optional[List[Dict[str, Any]]] = None,
    tasklist: Optional[List[Dict[str, Any]]] = None,
    task_mappings: Optional[List[Dict[str, Any]]] = None,
    collaboration_context: Optional[str] = None,
    target_files: Optional[List[str]] = None,
    analysis_scope: Optional[str] = None,
    high_level_steps: Optional[List[str]] = None,
    generated_content: Optional[str] = None,
    command_executed: Optional[str] = None,
    stdout: Optional[str] = None,
    stderr: Optional[str] = None,
    evidence: Optional[List[str]] = None,
    description: Optional[str] = None,
    task_data: Optional[Dict[str, Any]] = None,
    task_id: Optional[str] = None,
    task_index: Optional[int] = None,
    updated_task_data: Optional[Dict[str, Any]] = None,
    six_hats: Optional[Dict[str, Any]] = None,
    denoised_plan: Optional[str] = None
) -> dict:
    """
    🚀 TASKMASTER - LLM TASK EXECUTION FRAMEWORK 🚀
    
    Simple workflow:
    1. create_session - Create a new session
    2. declare_capabilities - Tell me what tools you have available
    3. six_hat_thinking - Brainstorm from six perspectives
    4. denoise - Synthesize your analysis into a plan
    5. create_tasklist - Define your tasks
    6. map_capabilities - Assign tools to tasks  
    7. execute_next - Execute tasks
    8. mark_complete - Complete tasks
    9. end_session - End session
    """
    # Convert individual parameters back to the data dict format
    data = {
        "action": action,
        "task_description": task_description or "",
        "session_name": session_name or "",
        "builtin_tools": builtin_tools or [],
        "mcp_tools": mcp_tools or [],
        "user_resources": user_resources or [],
        "tasklist": tasklist or [],
        "task_mappings": task_mappings or [],
        "collaboration_context": collaboration_context or "",
        "target_files": target_files or [],
        "analysis_scope": analysis_scope or "",
        "high_level_steps": high_level_steps or [],
        "generated_content": generated_content or "",
        "command_executed": command_executed or "",
        "stdout": stdout or "",
        "stderr": stderr or "",
        "exit_code": 0,
        "evidence": evidence or [],
        "description": description or "",
        "task_data": task_data or {},
        "task_id": task_id or "",
        "task_index": task_index,
        "updated_task_data": updated_task_data or {},
        "six_hats": six_hats or {},
        "denoised_plan": denoised_plan or ""
    }
    
    return await execute_taskmaster_logic(data)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"🌐 Starting Taskmaster FastMCP Server on port {port}")
    print(f"🔧 Using streamable-http transport with /mcp endpoint")
    print(f"🌍 CORS is enabled by default for cross-origin requests")
    
    # Run the FastMCP server with streamable-http transport
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=port,
        log_level="info"
    ) 