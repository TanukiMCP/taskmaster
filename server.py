# server.py
import asyncio
import logging
import os
import uuid
from fastmcp import FastMCP
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn
from starlette.middleware.cors import CORSMiddleware
from typing import Optional

# Import new architecture components
from taskmaster.container import get_container, TaskmasterContainer
from taskmaster.command_handler import TaskmasterCommandHandler, TaskmasterCommand
from taskmaster.schemas import (
    ActionType, ValidationResult, WorkflowState,
    create_flexible_request, create_flexible_response,
    validate_request, extract_guidance
)
from taskmaster.exceptions import TaskmasterError, error_handler
from taskmaster.config import get_config
from taskmaster.models import Session, Task, BuiltInTool, MCPTool, UserResource, EnvironmentCapabilities, TaskPhase

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create the MCP app
mcp = FastMCP("Taskmaster")

# Initialize dependency injection container
container: Optional[TaskmasterContainer] = None

async def initialize_container() -> TaskmasterContainer:
    """Initialize the dependency injection container."""
    global container
    if container is None:
        container = get_container()
        logger.info("Dependency injection container initialized")
    return container

async def get_command_handler() -> TaskmasterCommandHandler:
    """Get the command handler from the container."""
    container = await initialize_container()
    return container.resolve(TaskmasterCommandHandler)

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
    exit_code: Optional[int] = None
) -> dict:
    """
    🚀 INTELLIGENT LLM GUIDANCE FRAMEWORK 🚀
    
    This is an MCP server that provides GUIDANCE TOOLS for LLMs, not rigid validation.
    The LLM drives, we guide! This framework helps LLMs self-direct their own 
    tasklist generation and execution for whatever users request.
    
    RECOMMENDED WORKFLOW:
    1. create_session - Create a new session
    2. declare_capabilities - Self-declare capabilities (builtin_tools, mcp_tools, user_resources)
    3. create_tasklist - Create a structured list of tasks with phases
    4. map_capabilities - Assign specific tools to each task phase (ENSURES ACTUAL USAGE)
    5. execute_next - Execute tasks with phase-specific guidance (auto-completes tasks)
    6. mark_complete - Mark session complete when all tasks are done
    
    🚨 INTELLIGENT GUIDANCE FEATURES:
       - Phase-based Task Structure: Tasks can have planning, execution, and validation phases
       - Mandatory Capability Mapping: Forces assignment of tools to task phases
       - Simplified Capabilities: Just name + description (no redundant fields)
       - Workflow Collaboration: Optional pausing for user input when needed
       - NEVER BLOCKS EXECUTION - Always provides helpful guidance instead
    
    🧠 ADVANCED ARCHITECTURAL PATTERNS:
       - initialize_world_model - Counter architectural blindness with dynamic context
       - create_hierarchical_plan - Counter brittle planning with iterative loops
       - initiate_adversarial_review - Counter poor self-correction with peer review
       - record_host_grounding - Counter hallucination with real execution results
       - update_world_model - Maintain live state-aware context
       - static_analysis - Populate world model with codebase understanding
    
    Args:
        action: The action to take (create_session, declare_capabilities, create_tasklist, map_capabilities, execute_next, mark_complete, get_status, collaboration_request, initialize_world_model, create_hierarchical_plan, initiate_adversarial_review, record_host_grounding, update_world_model, static_analysis, etc.)
        task_description: Description of the task (for create_session)
        session_name: Name of the session (for create_session)
        builtin_tools: List of built-in tools with name + description (for declare_capabilities)
        mcp_tools: List of MCP tools with name + description + server_name (for declare_capabilities)
        user_resources: List of user resources with name + description + type (for declare_capabilities)
        tasklist: List of tasks with phase structure (for create_tasklist)
        task_mappings: List of capability assignments per task phase (for map_capabilities)
        collaboration_context: Context for collaboration request (for collaboration_request)
        
        # Advanced Architectural Pattern Parameters:
        target_files: Files for static analysis or world model initialization
        analysis_scope: Scope of analysis (current_task, full_system, etc.)
        high_level_steps: Strategic plan steps for hierarchical planning
        generated_content: Content for adversarial review
        command_executed: Command for host grounding
        stdout/stderr/exit_code: Real execution results
        
    Returns:
        Dictionary with current state, capability mappings, and execution guidance
    """
    try:
        # Get command handler from dependency injection container
        command_handler = await get_command_handler()
        
        # Create request object with simplified parameters
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
            "exit_code": exit_code or 0
        }
        
        # Use flexible validation that provides guidance instead of blocking
        enhanced_request = validate_request(data)
        guidance_messages = extract_guidance(enhanced_request)
        
        # Create command object with flexible approach
        command = TaskmasterCommand(**enhanced_request)
        
        # Execute command through handler - this will never block, only guide
        response = await command_handler.execute(command)
        
        # Convert response to dictionary format expected by MCP
        result = response.to_dict()
        
        # Add any guidance messages from request validation
        if guidance_messages:
            existing_guidance = result.get("completion_guidance", "")
            guidance_section = "\n\n🔍 INPUT GUIDANCE:\n" + "\n".join(guidance_messages)
            result["completion_guidance"] = existing_guidance + guidance_section
        
        return result
        
    except TaskmasterError as e:
        # Even errors provide guidance instead of blocking
        logger.error(f"Taskmaster error: {e}")
        return create_flexible_response(
            action=action or "error",
            status="guidance",  # Changed from "error" to "guidance"
            completion_guidance=f"🔍 GUIDANCE: {str(e)}\n\n💡 This is guidance, not a blocking error. You can proceed with adjustments.",
            error_details=str(e),
            next_action_needed=True
        )
        
    except Exception as e:
        # Unexpected errors also provide guidance
        logger.error(f"Unexpected error: {e}")
        return create_flexible_response(
            action=action or "error",
            status="guidance",
            completion_guidance=f"🔍 GUIDANCE: Unexpected situation encountered: {str(e)}\n\n💡 Consider checking your input format or trying a different approach.",
            error_details=str(e),
            next_action_needed=True
        )

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

# Add global error handler
app.add_exception_handler(TaskmasterError, error_handler)

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    try:
        # Test dependency injection container
        container = await initialize_container()
        command_handler = container.resolve(TaskmasterCommandHandler)
        
        return JSONResponse({
            "status": "healthy", 
            "server": "Taskmaster MCP v3.0",
            "architecture": "production-ready",
            "features": [
                "dependency_injection",
                "async_patterns", 
                "structured_error_handling",
                "session_management",
                "workflow_state_machine"
            ]
        })
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            {"status": "unhealthy", "error": str(e)}, 
            status_code=500
        )

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