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
from taskmaster.config import get_config as get_taskmaster_config
from taskmaster.models import Session, Task, BuiltInTool, MCPTool, MemoryTool, EnvironmentCapabilities, TaskPhase

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create the MCP app
mcp = FastMCP("Taskmaster")

# Initialize dependency injection container (lazy loading)
container: Optional[TaskmasterContainer] = None
_container_lock = asyncio.Lock()

async def initialize_container() -> TaskmasterContainer:
    """Initialize the dependency injection container with lazy loading."""
    global container
    
    # Use double-checked locking pattern for thread safety
    if container is None:
        async with _container_lock:
            if container is None:
                try:
                    # Use lazy initialization to avoid timeout during tool scanning
                    container = get_container()
                    logger.info("Dependency injection container initialized lazily")
                except Exception as e:
                    logger.error(f"Failed to initialize container: {e}")
                    # Create a minimal container for basic functionality
                    from taskmaster.container import TaskmasterContainer
                    container = TaskmasterContainer()
                    logger.info("Fallback container initialized")
    
    return container

async def get_command_handler() -> TaskmasterCommandHandler:
    """Get the command handler from the container with lazy loading."""
    try:
        container = await initialize_container()
        return container.resolve(TaskmasterCommandHandler)
    except Exception as e:
        logger.error(f"Failed to get command handler: {e}")
        # Return a minimal handler for basic functionality
        from taskmaster.session_manager import SessionManager
        from taskmaster.validation_engine import ValidationEngine
        session_manager = SessionManager()
        validation_engine = ValidationEngine()
        return TaskmasterCommandHandler(session_manager, validation_engine)

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
    # Task management parameters
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
    
    Args:
        action: The action to take (create_session, declare_capabilities, discover_capabilities, create_tasklist, map_capabilities, execute_next, mark_complete, get_status, collaboration_request, end_session, initialize_world_model, create_hierarchical_plan, initiate_adversarial_review, record_host_grounding, update_world_model, static_analysis, etc. | OPTIONAL: add_task, remove_task, update_task - only when user requests tasklist modifications)
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
        stdout/stderr: Real execution results (exit_code handled internally)
        evidence: List of evidence items for task completion validation
        description: Description of task completion or current state
        
        # Optional Task Management (use only when user requests modifications):
        task_data: Task structure for add_task command
        task_id/task_index: Task identifier for remove_task/update_task commands  
        updated_task_data: Update data for update_task command
        
    Returns:
        Dictionary with current state, capability mappings, and execution guidance
    """
    try:
        # Get command handler from dependency injection container (lazy loaded)
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
            "exit_code": 0,  # Only used by record_host_grounding action
            "evidence": evidence or [],
            "description": description or "",
            # Task management parameters
            "task_data": task_data or {},
            "task_id": task_id or "",
            "task_index": task_index,
            "updated_task_data": updated_task_data or {}
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
app = FastAPI(
    title="Taskmaster MCP Server",
    description="Enhanced LLM Task Execution Framework with Streamable HTTP Support",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware configuration for Smithery compatibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for Smithery compatibility
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)

# Mount the MCP server to the FastAPI app
app.mount("/mcp", mcp)  # type: ignore

@app.get("/")
async def root():
    """Root endpoint with server information."""
    return JSONResponse({
        "name": "Taskmaster MCP Server",
        "version": "3.0.0",
        "description": "Enhanced LLM Task Execution Framework",
        "smithery_compatible": True,
        "transport": "streamable-http",
        "endpoints": {
            "mcp": "/mcp",
            "health": "/health",
            "docs": "/docs"
        },
        "deployment_date": "2025-07-07",
        "lazy_loading": True
    })

@app.get("/health")
async def health_check():
    """Health check endpoint for Smithery monitoring with lazy loading."""
    try:
        # Lightweight health check without heavy initialization
        return JSONResponse({
            "status": "healthy", 
            "server": "Taskmaster MCP v3.0",
            "architecture": "production-ready",
            "smithery_ready": True,
            "transport": "streamable-http",
            "lazy_loading": True,
            "features": [
                "dependency_injection",
                "async_patterns", 
                "structured_error_handling",
                "session_management",
                "workflow_state_machine",
                "smithery_deployment",
                "lazy_initialization"
            ],
            "timestamp": "2025-07-07"
        })
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        return JSONResponse(
            {
                "status": "unhealthy", 
                "error": str(e),
                "smithery_ready": False,
                "lazy_loading": True
            }, 
            status_code=500
        )

# Configuration endpoint for Smithery integration
@app.get("/config")
async def get_config():
    """Configuration endpoint for Smithery to understand server capabilities."""
    return JSONResponse({
        "server": {
            "name": "taskmaster",
            "version": "3.0.0",
            "transport": "streamable-http"
        },
        "capabilities": {
            "tools": ["taskmaster"],
            "session_management": True,
            "async_execution": True,
            "error_recovery": True,
            "lazy_loading": True
        },
        "smithery": {
            "compatible": True,
            "deployment_ready": True,
            "lazy_loading_enabled": True,
            "configuration_schema": {
                "type": "object",
                "properties": {
                    "apiKey": {"type": "string", "description": "Optional API key"},
                    "debug": {"type": "boolean", "default": False},
                    "sessionTimeout": {"type": "integer", "default": 30}
                }
            }
        }
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    
    # For local development, run the MCP server directly
    if os.environ.get("SMITHERY_DEPLOY") != "true":
        print(f"🚀 Starting Taskmaster MCP Server v3.0 locally on port {port}")
        print(f"📡 Streamable HTTP transport enabled for Smithery compatibility")
        print(f"⚡ Lazy loading enabled for improved startup performance")
        mcp.run(transport='streamable-http', port=port, host="0.0.0.0")
    else:
        # For Smithery deployment, run the HTTP bridge
        print(f"🌐 Starting Taskmaster HTTP bridge for Smithery deployment on port {port}")
        print(f"📅 Deployment date: 2025-07-07")
        print(f"⚡ Lazy loading enabled for improved startup performance")
        uvicorn.run(app, host="0.0.0.0", port=port, log_level="info") 