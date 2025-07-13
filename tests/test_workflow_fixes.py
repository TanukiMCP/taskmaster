"""
Comprehensive test suite for workflow fixes verification.

Tests the fixes for:
1. MCPTool schema validation (server_name default)
2. Workflow state transition condition (map_capabilities)
3. Error handling in declare_capabilities
4. Workflow state synchronization
"""

import pytest
import asyncio
import json
from pathlib import Path
from taskmaster.container import TaskmasterContainer
from taskmaster.command_handler import TaskmasterCommandHandler, TaskmasterCommand
from taskmaster.models import Session, MCPTool
from taskmaster.workflow_state_machine import WorkflowState


class TestWorkflowFixes:
    """Test suite for workflow fixes."""
    
    @pytest.fixture
    def container(self):
        """Create a test container."""
        return TaskmasterContainer()
    
    @pytest.fixture
    def command_handler(self, container):
        """Create a command handler."""
        return container.resolve(TaskmasterCommandHandler)
    
    @pytest.mark.asyncio
    async def test_mcp_tool_schema_fix(self, command_handler):
        """Test that MCPTool schema allows missing server_name with default."""
        # Create session
        create_cmd = TaskmasterCommand(action="create_session", session_name="test_session")
        response = await command_handler.execute(create_cmd)
        assert response.status == "success"
        
        # Test declare_capabilities with MCP tool missing server_name
        declare_cmd = TaskmasterCommand(
            action="declare_capabilities",
            builtin_tools=[{"name": "read_file", "description": "Read files"}],
            mcp_tools=[{"name": "mcp_tool", "description": "Test MCP tool"}],  # Missing server_name
            user_resources=[]
        )
        response = await command_handler.execute(declare_cmd)
        
        # Should succeed with default server_name
        assert response.status == "success"
        assert "Capabilities declared successfully" in response.completion_guidance
        
        # Verify the MCP tool was created with default server_name
        session = await command_handler.session_manager.get_current_session()
        assert len(session.capabilities.mcp_tools) == 1
        assert session.capabilities.mcp_tools[0].server_name == "unknown"
    
    @pytest.mark.asyncio
    async def test_workflow_state_transition_fix(self, command_handler):
        """Test that tasklist_created -> map_capabilities transition works without condition."""
        # Create session and go through workflow
        create_cmd = TaskmasterCommand(action="create_session", session_name="test_session")
        await command_handler.execute(create_cmd)
        
        # Declare capabilities
        declare_cmd = TaskmasterCommand(
            action="declare_capabilities",
            builtin_tools=[{"name": "edit_file", "description": "Edit files"}],
            mcp_tools=[],
            user_resources=[]
        )
        await command_handler.execute(declare_cmd)
        
        # Six hat thinking
        six_hat_cmd = TaskmasterCommand(
            action="six_hat_thinking",
            six_hats={
                "white": "Test facts",
                "red": "Test feelings",
                "black": "Test risks",
                "yellow": "Test benefits",
                "green": "Test creativity",
                "blue": "Test process"
            }
        )
        await command_handler.execute(six_hat_cmd)
        
        # Denoise
        denoise_cmd = TaskmasterCommand(action="denoise")
        await command_handler.execute(denoise_cmd)
        
        # Create tasklist
        tasklist_cmd = TaskmasterCommand(
            action="create_tasklist",
            denoised_plan="Test plan",
            tasklist=[{"description": "Test task"}]
        )
        response = await command_handler.execute(tasklist_cmd)
        assert response.status == "success"
        
        # Map capabilities should now work without condition blocking
        map_cmd = TaskmasterCommand(
            action="map_capabilities",
            task_mappings=[{
                "task_id": response.data.get("tasks_created", [{}])[0].get("id", "test_id"),
                "planning_phase": {
                    "assigned_builtin_tools": [{"tool_name": "edit_file", "usage_purpose": "Test"}]
                },
                "execution_phase": {
                    "assigned_builtin_tools": [{"tool_name": "edit_file", "usage_purpose": "Test"}]
                }
            }]
        )
        
        # This should succeed now (previously would fail due to condition)
        response = await command_handler.execute(map_cmd)
        assert response.status == "success"
        assert "Capabilities mapped successfully" in response.completion_guidance
    
    @pytest.mark.asyncio
    async def test_error_handling_fix(self, command_handler):
        """Test that declare_capabilities errors don't advance workflow state."""
        # Create session
        create_cmd = TaskmasterCommand(action="create_session", session_name="test_session")
        await command_handler.execute(create_cmd)
        
        # Test with invalid tool data that should cause validation error
        declare_cmd = TaskmasterCommand(
            action="declare_capabilities",
            builtin_tools=[{"invalid": "data"}],  # Missing required fields
            mcp_tools=[],
            user_resources=[]
        )
        response = await command_handler.execute(declare_cmd)
        
        # Should return error status
        assert response.status == "error"
        assert "VALIDATION ERROR" in response.completion_guidance
        assert "declare_capabilities" in response.suggested_next_actions
        
        # Workflow state should not have advanced
        session = await command_handler.session_manager.get_current_session()
        assert session.workflow_state == WorkflowState.SESSION_CREATED.value
    
    @pytest.mark.asyncio
    async def test_workflow_state_synchronization(self, command_handler):
        """Test that workflow state synchronization works correctly."""
        # Create session
        create_cmd = TaskmasterCommand(action="create_session", session_name="test_session")
        response = await command_handler.execute(create_cmd)
        
        # Verify initial state
        session = await command_handler.session_manager.get_current_session()
        assert session.workflow_state == WorkflowState.SESSION_CREATED.value
        
        # Manually change session state to test synchronization
        session.workflow_state = WorkflowState.CAPABILITIES_DECLARED.value
        await command_handler.session_manager.update_session(session)
        
        # Execute a command that should synchronize state
        status_cmd = TaskmasterCommand(action="get_status")
        response = await command_handler.execute(status_cmd)
        
        # Verify state machine was synchronized
        if command_handler.workflow_state_machine:
            assert command_handler.workflow_state_machine.current_state == WorkflowState.CAPABILITIES_DECLARED
    
    @pytest.mark.asyncio
    async def test_complete_workflow_integration(self, command_handler):
        """Test complete workflow integration with all fixes."""
        # Create session
        create_cmd = TaskmasterCommand(action="create_session", session_name="integration_test")
        response = await command_handler.execute(create_cmd)
        assert response.status == "success"
        
        # Declare capabilities (with MCP tool missing server_name)
        declare_cmd = TaskmasterCommand(
            action="declare_capabilities",
            builtin_tools=[
                {"name": "read_file", "description": "Read files"},
                {"name": "edit_file", "description": "Edit files"}
            ],
            mcp_tools=[{"name": "mcp_tool", "description": "Test MCP tool"}],
            user_resources=[]
        )
        response = await command_handler.execute(declare_cmd)
        assert response.status == "success"
        
        # Six hat thinking
        six_hat_cmd = TaskmasterCommand(
            action="six_hat_thinking",
            six_hats={
                "white": "Integration test facts",
                "red": "Integration test feelings",
                "black": "Integration test risks",
                "yellow": "Integration test benefits",
                "green": "Integration test creativity",
                "blue": "Integration test process"
            }
        )
        response = await command_handler.execute(six_hat_cmd)
        assert response.status == "success"
        
        # Denoise
        denoise_cmd = TaskmasterCommand(action="denoise")
        response = await command_handler.execute(denoise_cmd)
        assert response.status == "template"
        
        # Create tasklist
        tasklist_cmd = TaskmasterCommand(
            action="create_tasklist",
            denoised_plan="Integration test plan",
            tasklist=[
                {"description": "Setup project structure"},
                {"description": "Implement core functionality"}
            ]
        )
        response = await command_handler.execute(tasklist_cmd)
        assert response.status == "success"
        
        # Get session to extract task IDs
        session = await command_handler.session_manager.get_current_session()
        task_ids = [task.id for task in session.tasks]
        
        # Map capabilities (should work without condition blocking)
        map_cmd = TaskmasterCommand(
            action="map_capabilities",
            task_mappings=[
                {
                    "task_id": task_ids[0],
                    "planning_phase": {
                        "assigned_builtin_tools": [{"tool_name": "read_file", "usage_purpose": "Research"}]
                    },
                    "execution_phase": {
                        "assigned_builtin_tools": [{"tool_name": "edit_file", "usage_purpose": "Implementation"}]
                    }
                },
                {
                    "task_id": task_ids[1],
                    "planning_phase": {
                        "assigned_builtin_tools": [{"tool_name": "read_file", "usage_purpose": "Research"}]
                    },
                    "execution_phase": {
                        "assigned_builtin_tools": [{"tool_name": "edit_file", "usage_purpose": "Implementation"}]
                    }
                }
            ]
        )
        response = await command_handler.execute(map_cmd)
        assert response.status == "success"
        assert "Capabilities mapped successfully" in response.completion_guidance
        
        # Execute next should work
        execute_cmd = TaskmasterCommand(action="execute_next")
        response = await command_handler.execute(execute_cmd)
        assert response.status == "success"
        assert "EXECUTE TASK" in response.completion_guidance
        
        # Verify final state
        final_session = await command_handler.session_manager.get_current_session()
        assert len(final_session.tasks) == 2
        assert final_session.capabilities.mcp_tools[0].server_name == "unknown"


if __name__ == "__main__":
    pytest.main([__file__, "-v"]) 