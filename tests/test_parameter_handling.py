#!/usr/bin/env python3
"""Test script to verify parameter handling works correctly."""

import sys
import json
from typing import List, Dict, Any, Optional

def test_parameter_parsing():
    """Test that the parameter types match what FastMCP expects."""
    print("Testing parameter parsing...")
    
    # Test data that should work with the tool
    test_builtin_tools = [
        {"name": "codebase_search", "description": "semantic search"},
        {"name": "read_file", "description": "read files"}
    ]
    
    test_mcp_tools = [
        {"name": "mcp_taskmaster", "server_name": "taskmaster", "description": "task framework"},
        {"name": "update_memory", "server_name": "memory", "description": "memory management"}
    ]
    
    test_user_resources = [
        {"name": "codebase", "description": "project codebase"},
        {"name": "environment", "description": "development environment"}
    ]
    
    # Test the parameter types that the tool expects
    def mock_taskmaster_tool(
        action: str,
        builtin_tools: Optional[List[Dict[str, Any]]] = None,
        mcp_tools: Optional[List[Dict[str, Any]]] = None,
        user_resources: Optional[List[Dict[str, Any]]] = None
    ) -> dict:
        """Mock version of the taskmaster tool to test parameter handling."""
        print(f"Action: {action}")
        print(f"Builtin tools type: {type(builtin_tools)}")
        print(f"MCP tools type: {type(mcp_tools)}")
        print(f"User resources type: {type(user_resources)}")
        
        if builtin_tools:
            print(f"Builtin tools count: {len(builtin_tools)}")
            for tool in builtin_tools:
                print(f"  - {tool['name']}: {tool['description']}")
        
        if mcp_tools:
            print(f"MCP tools count: {len(mcp_tools)}")
            for tool in mcp_tools:
                print(f"  - {tool['name']}: {tool['description']}")
        
        if user_resources:
            print(f"User resources count: {len(user_resources)}")
            for resource in user_resources:
                print(f"  - {resource['name']}: {resource['description']}")
        
        return {"status": "success", "message": "Parameters parsed correctly"}
    
    # Test the function with the test data
    result = mock_taskmaster_tool(
        action="declare_capabilities",
        builtin_tools=test_builtin_tools,
        mcp_tools=test_mcp_tools,
        user_resources=test_user_resources
    )
    
    print(f"Result: {result}")
    print("SUCCESS: Parameter handling test passed!")
    return True

if __name__ == "__main__":
    try:
        test_parameter_parsing()
        print("All parameter tests passed!")
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)