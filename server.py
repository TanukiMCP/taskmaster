# server.py
import asyncio
import logging
import os
import json
from fastmcp import FastMCP
from typing import Optional, List, Dict, Any, Union

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

def preprocess_mcp_parameters(**kwargs) -> Dict[str, Any]:
    """
    Preprocess MCP parameters to handle serialization issues.
    
    The MCP protocol sometimes serializes array parameters as JSON strings.
    This function detects and converts them back to proper data types.
    """
    processed = {}
    
    # List of parameters that should be arrays
    array_parameters = [
        'builtin_tools', 'mcp_tools', 'user_resources', 
        'tasklist', 'task_mappings'
    ]
    
    # Parameters that should be dictionaries
    dict_parameters = ['six_hats', 'updated_task_data']
    
    for key, value in kwargs.items():
        if value is None:
            processed[key] = value
            continue
            
        # Handle array parameters
        if key in array_parameters:
            if isinstance(value, str):
                try:
                    # Try to parse as JSON
                    parsed_value = json.loads(value)
                    if isinstance(parsed_value, list):
                        processed[key] = parsed_value
                        logger.info(f"Converted {key} from JSON string to array")
                    else:
                        processed[key] = value
                except (json.JSONDecodeError, TypeError):
                    # If parsing fails, keep original value
                    processed[key] = value
            else:
                processed[key] = value
                
        # Handle dictionary parameters
        elif key in dict_parameters:
            if isinstance(value, str):
                try:
                    # Try to parse as JSON
                    parsed_value = json.loads(value)
                    if isinstance(parsed_value, dict):
                        processed[key] = parsed_value
                        logger.info(f"Converted {key} from JSON string to dict")
                    else:
                        processed[key] = value
                except (json.JSONDecodeError, TypeError):
                    # If parsing fails, keep original value
                    processed[key] = value
            else:
                processed[key] = value
        else:
            processed[key] = value
    
    return processed

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
    builtin_tools: Optional[Union[List[Dict[str, Any]], str]] = None,
    mcp_tools: Optional[Union[List[Dict[str, Any]], str]] = None,
    user_resources: Optional[Union[List[Dict[str, Any]], str]] = None,
    tasklist: Optional[Union[List[Dict[str, Any]], str]] = None,
    task_mappings: Optional[Union[List[Dict[str, Any]], str]] = None,
    collaboration_context: Optional[str] = None,
    task_id: Optional[str] = None,
    updated_task_data: Optional[Union[Dict[str, Any], str]] = None,
    six_hats: Optional[Union[Dict[str, Any], str]] = None,
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
    # Preprocess parameters to handle MCP serialization issues
    raw_params = {
        "action": action,
        "task_description": task_description,
        "session_name": session_name,
        "builtin_tools": builtin_tools,
        "mcp_tools": mcp_tools,
        "user_resources": user_resources,
        "tasklist": tasklist,
        "task_mappings": task_mappings,
        "collaboration_context": collaboration_context,
        "task_id": task_id,
        "updated_task_data": updated_task_data,
        "six_hats": six_hats,
        "denoised_plan": denoised_plan
    }
    
    # Apply preprocessing to convert JSON strings back to proper types
    processed_params = preprocess_mcp_parameters(**raw_params)
    
    # Convert to the data dict format with proper defaults
    data = {
        "action": processed_params["action"],
        "task_description": processed_params["task_description"] or "",
        "session_name": processed_params["session_name"] or "",
        "builtin_tools": processed_params["builtin_tools"] or [],
        "mcp_tools": processed_params["mcp_tools"] or [],
        "user_resources": processed_params["user_resources"] or [],
        "tasklist": processed_params["tasklist"] or [],
        "task_mappings": processed_params["task_mappings"] or [],
        "collaboration_context": processed_params["collaboration_context"] or "",
        "task_id": processed_params["task_id"] or "",
        "updated_task_data": processed_params["updated_task_data"] or {},
        "six_hats": processed_params["six_hats"] or {},
        "denoised_plan": processed_params["denoised_plan"] or ""
    }
    
    return await execute_taskmaster_logic(data)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"🌐 Starting Taskmaster FastMCP Server on port {port}")
    print(f"🔧 Using streamable-http transport with /mcp endpoint")
    print(f"🌍 CORS is enabled by default for cross-origin requests")
    print(f"🛠️ Enhanced parameter preprocessing enabled")
    
    # Run the FastMCP server with streamable-http transport
    mcp.run(
        transport="streamable-http",
        host="0.0.0.0",
        port=port,
        log_level="info"
    ) 