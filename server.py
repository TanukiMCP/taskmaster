# server.py
import importlib
from fastmcp import FastMCP
from pydantic import BaseModel

# Create the MCP app
app = FastMCP("Taskmaster")

class TaskmasterRequest(BaseModel):
    command: str
    payload: dict = {}

@app.tool()
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

if __name__ == "__main__":
    app.run() 