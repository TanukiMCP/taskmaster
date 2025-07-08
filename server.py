# server.py
import asyncio
import logging
import os
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.middleware.cors import CORSMiddleware
from typing import Optional

# Import the correct MCP library for FastAPI integration
from fastapi_mcp import FastApiMCP

# Import project-specific components
from taskmaster.container import get_container, TaskmasterContainer
from taskmaster.command_handler import TaskmasterCommandHandler, TaskmasterCommand
from taskmaster.schemas import create_flexible_response, validate_request, extract_guidance
from taskmaster.exceptions import TaskmasterError

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Create the FastAPI application
app = FastAPI(
    title="Taskmaster MCP Server",
    description="Enhanced LLM Task Execution Framework with Smithery Streamable HTTP Support",
    version="3.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# Add CORS middleware to allow cross-origin requests, which is crucial for Smithery.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Tool-specific logic ---
# This section contains the core business logic of the Taskmaster tool.

container: Optional[TaskmasterContainer] = None
_container_lock = asyncio.Lock()

async def execute_taskmaster_logic(data: dict) -> dict:
    """
    Handles the actual execution of the taskmaster command.
    This function is designed to be called by a standard FastAPI endpoint.
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

# --- FastAPI Endpoints ---
# These are the standard HTTP endpoints for the service.

@app.post("/taskmaster")
async def taskmaster_endpoint(request: Request) -> JSONResponse:
    """
    This is the primary endpoint for the Taskmaster tool.
    It accepts a JSON payload and executes the corresponding command.
    fastapi-mcp will automatically convert this endpoint into a discoverable MCP tool.
    """
    body = await request.json()
    result = await execute_taskmaster_logic(body)
    return JSONResponse(content=result)

# --- MCP Integration ---
# This section integrates the FastAPI app with the Model Context Protocol.

# Instantiate the MCP bridge with the FastAPI app
mcp_bridge = FastApiMCP(app)

# Mount the MCP server, making all FastAPI endpoints available as MCP tools
mcp_bridge.mount()

# --- Server Entrypoint ---

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    print(f"🌐 Starting Taskmaster FastAPI Server on port {port}")
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="info") 