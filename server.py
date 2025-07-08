# server.py
import asyncio
import logging
import os
from fastmcp import FastMCP
from typing import Optional

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

# Ultra-lightweight global state for tool discovery optimization
container: Optional[TaskmasterContainer] = None
_container_lock = asyncio.Lock()

async def execute_taskmaster_logic(data: dict) -> dict:
    """
    Handles the actual execution of the taskmaster command.
    This function is designed to be called by the FastMCP tool.
    """
    global container
    try:
        # Lazy-load the container on first use
        if container is None:
            async with _container_lock:
                if container is None:
                    logger.info("Initializing container on first tool invocation...")
                    container = get_container()
                    logger.info("Container initialized.")

            command_handler = container.resolve(TaskmasterCommandHandler)

        # Process the request
        enhanced_request = validate_request(data)
        guidance_messages = extract_guidance(enhanced_request)
        command = TaskmasterCommand(**enhanced_request)
        response = await command_handler.execute(command)
        result = response.to_dict()
        
        # Add guidance messages if any were generated during validation
        if guidance_messages:
            existing_guidance = result.get("completion_guidance", "")
            guidance_section = "\n\n🔍 INPUT GUIDANCE:\n" + "\n".join(guidance_messages)
            result["completion_guidance"] = existing_guidance + guidance_section
        
        return result
        
    except TaskmasterError as e:
        logger.error(f"Taskmaster guidance error: {e}")
        return create_flexible_response(
            action=data.get("action", "error"),
            status="guidance",
            completion_guidance=f"🔍 GUIDANCE: {str(e)}\n\n💡 This is guidance, not a blocking error. You can proceed with adjustments.",
            error_details=str(e),
            next_action_needed=True
        )
    except Exception as e:
        logger.error(f"Unexpected error during taskmaster execution: {e}", exc_info=True)
        return create_flexible_response(
            action=data.get("action", "error"),
            status="guidance",
            completion_guidance=f"🔍 GUIDANCE: An unexpected situation occurred: {str(e)}\n\n💡 Consider checking your input format.",
            error_details=str(e),
            next_action_needed=True
        )

@mcp.tool()
async def taskmaster(
    action: str,
    task_description: Optional[str] = None,
    session_name: Optional[str] = None,
    builtin_tools: Optional[list] = None,
    mcp_tools: Optional[list] = None,
    user_resources: Optional[list] = None,
    tasklist: Optional[list] = None,
    task_mappings: Optional[list] = None,
    collaboration_context: Optional[str] = None,
    target_files: Optional[list] = None,
    analysis_scope: Optional[str] = None,
    high_level_steps: Optional[list] = None,
    generated_content: Optional[str] = None,
    command_executed: Optional[str] = None,
    stdout: Optional[str] = None,
    stderr: Optional[str] = None,
    evidence: Optional[list] = None,
    description: Optional[str] = None,
    task_data: Optional[dict] = None,
    task_id: Optional[str] = None,
    task_index: Optional[int] = None,
    updated_task_data: Optional[dict] = None
) -> dict:
    """
    🚀 ENHANCED LLM TASK EXECUTION FRAMEWORK 🚀
    
    This MCP server provides INTELLIGENT GUIDANCE for LLMs with enforced quality controls.
    The LLM drives, we guide with mandatory structure! This framework ensures consistent,
    high-quality task execution with built-in anti-hallucination safeguards.
    
    🔄 STREAMLINED WORKFLOW (MANDATORY SEQUENCE):
    1. create_session - Create a new session
    2. declare_capabilities - Self-declare capabilities (builtin_tools, mcp_tools, user_resources)
       OR discover_capabilities - Auto-discover available tools and get suggested declaration
    3. create_tasklist - Create structured tasks with streamlined plan→execute cycle
    4. map_capabilities - Assign specific tools to each task phase (ENSURES ACTUAL USAGE)
    5. execute_next - Execute with phase-specific guidance and enhanced placeholder guardrails
    6. mark_complete - Complete with evidence collection (STREAMLINED VALIDATION)
    7. end_session - Formally close session when all tasks completed
    
    ENHANCED QUALITY CONTROLS:
       - Streamlined Phase Structure: Every task follows planning -> execution -> complete
       - Enhanced Placeholder Guidance: Contextual guardrails prevent lazy implementations
       - Adversarial Review: Complex tasks require critical review with 3 suggestions
       - Anti-Hallucination: Console output verification, file existence checks
       - Complexity Assessment: Simple/Complex/Architectural task classification
       - Reality Checking: Actual execution results vs claimed results
    
    ADVANCED ARCHITECTURAL PATTERNS:
       - initialize_world_model - Counter architectural blindness with dynamic context
       - create_hierarchical_plan - Counter brittle planning with iterative loops
       - initiate_adversarial_review - Counter poor self-correction with peer review
       - record_host_grounding - Counter hallucination with real execution results
       - update_world_model - Maintain live state-aware context
       - static_analysis - Populate world model with codebase understanding
    
    This endpoint accepts a JSON payload and executes the corresponding command.
    fastapi-mcp will automatically convert this endpoint into a discoverable MCP tool.
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
        "updated_task_data": updated_task_data or {}
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