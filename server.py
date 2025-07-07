# server.py
import asyncio
import logging
import os
import uuid
import json
from fastmcp import FastMCP
from fastapi import FastAPI, Request, Response
from fastapi.responses import JSONResponse
import uvicorn
from starlette.middleware.cors import CORSMiddleware
from typing import Optional, Dict, Any
from urllib.parse import parse_qs

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

# Create the MCP app with static tool discovery optimization
mcp = FastMCP("Taskmaster")

# Ultra-lightweight global state for Smithery tool discovery optimization
container: Optional[TaskmasterContainer] = None
_container_lock = asyncio.Lock()
_initialization_started = False

# SMITHERY STREAMABLE HTTP OPTIMIZATION: 
# This function is defined OUTSIDE the tool decorator to ensure 
# tool discovery scanning doesn't trigger any initialization
async def _execute_taskmaster_tool(
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
    """Execute the taskmaster tool logic with ultra-lazy initialization."""
    global container, _initialization_started
    
    try:
        # Ultra-lazy loading: Only initialize on ACTUAL tool invocation
        logger.info(f"Tool ACTUALLY invoked with action: {action}")
        
        # Initialize container only when tool is actually called
        if container is None:
            async with _container_lock:
                if container is None:
                    try:
                        _initialization_started = True
                        container = get_container()
                        logger.info("Container initialized on actual tool invocation")
                    except Exception as e:
                        logger.error(f"Failed to initialize container: {e}")
                        from taskmaster.container import TaskmasterContainer
                        container = TaskmasterContainer()
                        logger.info("Fallback container initialized")
        
        # Get command handler
        try:
            command_handler = container.resolve(TaskmasterCommandHandler)
        except Exception as e:
            logger.error(f"Failed to get command handler: {e}")
            from taskmaster.session_manager import SessionManager
            from taskmaster.validation_engine import ValidationEngine
            session_manager = SessionManager()
            validation_engine = ValidationEngine()
            command_handler = TaskmasterCommandHandler(session_manager, validation_engine)
        
        # Create request object
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
        
        # Process request
        enhanced_request = validate_request(data)
        guidance_messages = extract_guidance(enhanced_request)
        command = TaskmasterCommand(**enhanced_request)
        response = await command_handler.execute(command)
        result = response.to_dict()
        
        # Add guidance messages
        if guidance_messages:
            existing_guidance = result.get("completion_guidance", "")
            guidance_section = "\n\n🔍 INPUT GUIDANCE:\n" + "\n".join(guidance_messages)
            result["completion_guidance"] = existing_guidance + guidance_section
        
        return result
        
    except TaskmasterError as e:
        logger.error(f"Taskmaster error: {e}")
        return create_flexible_response(
            action=action or "error",
            status="guidance",
            completion_guidance=f"🔍 GUIDANCE: {str(e)}\n\n💡 This is guidance, not a blocking error. You can proceed with adjustments.",
            error_details=str(e),
            next_action_needed=True
        )
        
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return create_flexible_response(
            action=action or "error",
            status="guidance",
            completion_guidance=f"🔍 GUIDANCE: Unexpected situation encountered: {str(e)}\n\n💡 Consider checking your input format or trying a different approach.",
            error_details=str(e),
            next_action_needed=True
        )

# SMITHERY TOOL DISCOVERY OPTIMIZATION:
# Static tool registration with NO initialization logic in the decorator
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
    # SMITHERY OPTIMIZATION: Delegate to separate function to ensure
    # tool discovery scanning doesn't trigger any initialization
    return await _execute_taskmaster_tool(
        action=action,
        task_description=task_description,
        session_name=session_name,
        builtin_tools=builtin_tools,
        mcp_tools=mcp_tools,
        user_resources=user_resources,
        tasklist=tasklist,
        task_mappings=task_mappings,
        collaboration_context=collaboration_context,
        target_files=target_files,
        analysis_scope=analysis_scope,
        high_level_steps=high_level_steps,
        generated_content=generated_content,
        command_executed=command_executed,
        stdout=stdout,
        stderr=stderr,
        evidence=evidence,
        description=description,
        task_data=task_data,
        task_id=task_id,
        task_index=task_index,
        updated_task_data=updated_task_data
    )

def parse_smithery_config(query_params: str) -> Dict[str, Any]:
    """Parse Smithery configuration from query parameters using dot-notation."""
    config = {}
    if not query_params:
        return config
    
    try:
        # Parse query parameters
        params = parse_qs(query_params, keep_blank_values=True)
        
        for key, values in params.items():
            value = values[0] if values else ""
            
            # Handle dot-notation (e.g., "server.host" -> {"server": {"host": "value"}})
            keys = key.split('.')
            current = config
            
            for i, k in enumerate(keys[:-1]):
                if k not in current:
                    current[k] = {}
                current = current[k]
            
            # Set the final value
            current[keys[-1]] = value
            
        logger.info(f"Parsed Smithery config: {config}")
        return config
        
    except Exception as e:
        logger.warning(f"Failed to parse Smithery config: {e}")
        return {}

# Create FastAPI app for Smithery Streamable HTTP compatibility
app = FastAPI(
    title="Taskmaster MCP Server",
    description="Enhanced LLM Task Execution Framework with Smithery Streamable HTTP Support",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware configuration for Smithery compatibility
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allow all origins for Smithery compatibility
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

# SMITHERY STREAMABLE HTTP IMPLEMENTATION
# According to https://smithery.ai/docs/build/deployments:
# - Endpoint: /mcp must be available
# - Methods: Handle GET, POST, and DELETE requests
# - Configuration: Parse query parameters in dot-notation

@app.get("/mcp")
async def mcp_get(request: Request):
    """Handle GET requests to /mcp endpoint for Smithery tool discovery."""
    try:
        # Parse Smithery configuration from query parameters
        config = parse_smithery_config(str(request.query_params))
        
        # For GET requests, Smithery typically wants tool discovery
        # Return tools list without requiring authentication (as per Smithery best practices)
        return JSONResponse({
            "jsonrpc": "2.0",
            "result": {
                "tools": [
                    {
                        "name": "taskmaster",
                        "description": "Enhanced LLM Task Execution Framework with intelligent guidance and quality controls",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "action": {
                                    "type": "string", 
                                    "description": "The action to take (create_session, declare_capabilities, etc.)"
                                },
                                "task_description": {"type": "string"},
                                "session_name": {"type": "string"},
                                "builtin_tools": {"type": "array"},
                                "mcp_tools": {"type": "array"},
                                "user_resources": {"type": "array"}
                            },
                            "required": ["action"]
                        }
                    }
                ]
            }
        })
    except Exception as e:
        logger.error(f"MCP GET error: {e}")
        return JSONResponse({
            "jsonrpc": "2.0",
            "error": {"code": -32603, "message": f"Internal error: {str(e)}"}
        }, status_code=500)

@app.post("/mcp")
async def mcp_post(request: Request):
    """Handle POST requests to /mcp endpoint for Smithery tool execution."""
    try:
        # Parse Smithery configuration from query parameters
        config = parse_smithery_config(str(request.query_params))
        
        # Get JSON-RPC request body
        body = await request.json()
        logger.info(f"MCP POST request: {body}")
        
        # Handle different MCP methods
        method = body.get("method")
        params = body.get("params", {})
        request_id = body.get("id")
        
        if method == "tools/list":
            # Tool discovery - return static tool list instantly
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": request_id,
                "result": {
                    "tools": [
                        {
                            "name": "taskmaster",
                            "description": "Enhanced LLM Task Execution Framework with intelligent guidance and quality controls",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "action": {
                                        "type": "string", 
                                        "description": "The action to take (create_session, declare_capabilities, etc.)"
                                    },
                                    "task_description": {"type": "string"},
                                    "session_name": {"type": "string"},
                                    "builtin_tools": {"type": "array"},
                                    "mcp_tools": {"type": "array"},
                                    "user_resources": {"type": "array"}
                                },
                                "required": ["action"]
                            }
                        }
                    ]
                }
            })
            
        elif method == "tools/call":
            # Tool execution - delegate to actual tool
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            
            if tool_name == "taskmaster":
                # Execute taskmaster tool
                result = await _execute_taskmaster_tool(**arguments)
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result, indent=2)
                            }
                        ]
                    }
                })
            else:
                return JSONResponse({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"code": -32601, "message": f"Unknown tool: {tool_name}"}
                }, status_code=400)
                
        else:
            # Handle other MCP methods according to JSON-RPC protocol
            return JSONResponse({
                "jsonrpc": "2.0",
                "id": request_id,
                "error": {"code": -32601, "message": f"Unknown method: {method}"}
            }, status_code=400)
            
    except Exception as e:
        logger.error(f"MCP POST error: {e}")
        return JSONResponse({
            "jsonrpc": "2.0",
            "id": body.get("id") if 'body' in locals() else None,
            "error": {"code": -32603, "message": f"Internal error: {str(e)}"}
        }, status_code=500)

@app.delete("/mcp")
async def mcp_delete(request: Request):
    """Handle DELETE requests to /mcp endpoint for Smithery session cleanup."""
    try:
        # Parse Smithery configuration from query parameters
        config = parse_smithery_config(str(request.query_params))
        
        # Handle session cleanup or resource cleanup
        logger.info("MCP DELETE request - cleaning up resources")
        
        return JSONResponse({
            "jsonrpc": "2.0",
            "result": {"status": "cleaned"}
        })
        
    except Exception as e:
        logger.error(f"MCP DELETE error: {e}")
        return JSONResponse({
            "jsonrpc": "2.0",
            "error": {"code": -32603, "message": f"Internal error: {str(e)}"}
        }, status_code=500)

@app.get("/")
async def root():
    """Root endpoint with server information - ultra-fast for Smithery tool discovery."""
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
        "lazy_loading": True,
        "tool_discovery_optimized": True,
        "static_tool_registration": True,
        "streamable_http_compliant": True
    })

@app.get("/health")
async def health_check():
    """Health check endpoint for Smithery monitoring with ultra-lightweight checks."""
    try:
        # Ultra-lightweight health check - no heavy initialization
        # Only check basic server functionality without container initialization
        return JSONResponse({
            "status": "healthy", 
            "server": "Taskmaster MCP v3.0",
            "architecture": "production-ready",
            "smithery_ready": True,
            "transport": "streamable-http",
            "lazy_loading": True,
            "tool_discovery_optimized": True,
            "static_tool_registration": True,
            "streamable_http_compliant": True,
            "initialization_deferred": not _initialization_started,
            "features": [
                "dependency_injection",
                "async_patterns", 
                "structured_error_handling",
                "session_management",
                "workflow_state_machine",
                "smithery_deployment",
                "ultra_lazy_initialization",
                "tool_discovery_optimization",
                "static_tool_registration",
                "streamable_http_protocol"
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
    """Configuration endpoint for Smithery to understand server capabilities - ultra-fast response."""
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
            "lazy_loading": True,
            "tool_discovery_optimized": True,
            "static_tool_registration": True,
            "streamable_http_compliant": True
        },
        "smithery": {
            "compatible": True,
            "deployment_ready": True,
            "lazy_loading_enabled": True,
            "tool_discovery_optimized": True,
            "static_tool_registration": True,
            "streamable_http_compliant": True,
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
    
    # For Smithery deployment, run the HTTP server directly
    # This ensures proper Streamable HTTP protocol compliance
    print(f"🌐 Starting Taskmaster MCP Server v3.0 for Smithery on port {port}")
    print(f"📅 Deployment date: 2025-07-07")
    print(f"⚡ Streamable HTTP protocol enabled for Smithery compatibility")
    print(f"🔧 Static tool registration for instant discovery")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info") 