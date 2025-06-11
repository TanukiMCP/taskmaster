# server.py
import importlib
import os
import json
from fastmcp import FastMCP
from pydantic import BaseModel
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn

# Create the MCP app
mcp = FastMCP("Taskmaster")

class TaskmasterRequest(BaseModel):
    command: str
    payload: dict = {}

@mcp.tool()
def taskmaster(command: str, payload: dict = {}) -> dict:
    """
    The single, unified entry point for all Taskmaster operations.
    
    Args:
        command: The command to execute (e.g., 'create_session', 'add_task', 'get_tasklist')
        payload: Dictionary containing command-specific parameters
    
    Returns:
        Dictionary containing the command result or error information
    """
    try:
        # Dynamically import and execute the command
        command_module = importlib.import_module(f"taskmaster.commands.{command}")
        command_class = getattr(command_module, "Command")
        instance = command_class()
        return instance.execute(payload)
    except ImportError as e:
        return {"error": f"Unknown command '{command}'", "details": str(e)}
    except AttributeError as e:
        return {"error": f"Invalid command implementation '{command}'", "details": str(e)}
    except Exception as e:
        return {"error": f"Command execution failed", "command": command, "details": str(e)}

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
                "version": "1.0.0"
            },
            "tools": [
                {
                    "name": "taskmaster",
                    "description": "The single, unified entry point for all Taskmaster operations",
                    "inputSchema": {
                        "type": "object", 
                        "properties": {
                            "command": {
                                "type": "string",
                                "description": "The command to execute"
                            },
                            "payload": {
                                "type": "object",
                                "description": "Command-specific parameters"
                            }
                        },
                        "required": ["command"]
                    }
                }
            ]
        }
    })

@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return JSONResponse({"status": "healthy", "server": "Taskmaster MCP"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    
    # For local development, run the MCP server directly
    if os.environ.get("SMITHERY_DEPLOY") != "true":
        print(f"Starting Taskmaster MCP Server locally on port {port}")
        mcp.run(transport='streamable-http', port=port, host="0.0.0.0", path="/mcp")
    else:
        # For Smithery deployment, run the HTTP bridge
        print(f"Starting Taskmaster HTTP bridge for Smithery on port {port}")
        uvicorn.run(app, host="0.0.0.0", port=port) 