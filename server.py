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

# Import new architecture components
from taskmaster.container import get_container, TaskmasterContainer
from taskmaster.command_handler import TaskmasterCommandHandler
from taskmaster.schemas import (
    TaskmasterRequest, TaskmasterResponse, ActionType,
    validate_request, create_error_response, create_success_response
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
container: TaskmasterContainer = None

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
    task_description: str = None,
    session_name: str = None,
    validation_criteria: list = None,
    evidence: str = None,
    execution_evidence: str = None,
    builtin_tools: list = None,
    mcp_tools: list = None,
    user_resources: list = None,
    tasklist: list = None,
    task_ids: list = None,
    updated_task_data: dict = None,
    next_action_needed: bool = True,
    validation_result: str = None,
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
       - update_memory_palace: Update memory palace with task learnings (requires memory_palace MCP server)
    
    🚨 CRITICAL ENFORCEMENT FEATURES:
       - Capability Assignment Validation: Tasks must declare and use only assigned capabilities
       - Completeness Validation: Prevents placeholders, hardcoded values, and incomplete implementations
       - Test Integrity Enforcement: Prevents test manipulation, ensures LLMs fix implementation not tests
       - Anti-Hallucination: Enforces use of only declared tools and resources
       - Memory Palace Integration: Captures learnings, patterns, and insights after task completion
       - Workflow Pausing: Automatically pauses on validation failures to prevent low-quality work
    
    Args:
        action: The action to take
        validation_result: Result of validation ("passed", "failed", "inconclusive")
        error_details: Details about validation errors or execution problems
        collaboration_context: Context for why user collaboration is needed
        user_response: User's response to collaboration request (auto-added to tasklist)
        
        [... existing parameters ...]
    
    Returns:
        Dictionary with current state, capability mappings, and execution guidance
    """
    try:
        # Get command handler from dependency injection container
        command_handler = await get_command_handler()
        
        # Create request object
        request_data = {
            "action": action,
            "task_description": task_description,
            "session_name": session_name,
            "validation_criteria": validation_criteria,
            "evidence": evidence,
            "execution_evidence": execution_evidence,
            "builtin_tools": builtin_tools,
            "mcp_tools": mcp_tools,
            "user_resources": user_resources,
            "tasklist": tasklist,
            "task_ids": task_ids,
            "updated_task_data": updated_task_data,
            "next_action_needed": next_action_needed,
            "validation_result": validation_result,
            "error_details": error_details,
            "collaboration_context": collaboration_context,
            "user_response": user_response
        }
        
        # Validate request
        try:
            request = validate_request(request_data)
        except ValueError as e:
            return create_error_response(str(e), "validation_error")
        
        # Execute command through handler
        response = await command_handler.handle_command(request)
        
        # Convert response to dictionary format expected by MCP
        return response.model_dump()
        
    except TaskmasterError as e:
        logger.error(f"Taskmaster error: {e}")
        return create_error_response(str(e), e.error_code.value if hasattr(e, 'error_code') else "taskmaster_error")
    except Exception as e:
        logger.error(f"Unexpected error in taskmaster: {e}")
        return create_error_response(f"Internal server error: {str(e)}", "internal_error")

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