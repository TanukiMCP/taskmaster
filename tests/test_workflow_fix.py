#!/usr/bin/env python3
"""Test script to verify the workflow state machine fix."""

import sys
import os
sys.path.append('.')

from taskmaster.workflow_state_machine import WorkflowStateMachine, WorkflowEvent, WorkflowState

def test_workflow_fix():
    """Test that CREATE_SESSION works directly from UNINITIALIZED state."""
    print("Testing workflow state machine fix...")
    
    # Create a new workflow state machine
    workflow = WorkflowStateMachine()
    
    # Verify initial state
    print(f"Initial state: {workflow.current_state.value}")
    assert workflow.current_state == WorkflowState.UNINITIALIZED
    
    # Test CREATE_SESSION event directly from UNINITIALIZED
    success = workflow.trigger_event(WorkflowEvent.CREATE_SESSION)
    print(f"CREATE_SESSION event success: {success}")
    print(f"New state: {workflow.current_state.value}")
    
    # Verify state changed to SESSION_CREATED
    assert success == True
    assert workflow.current_state == WorkflowState.SESSION_CREATED
    
    print("SUCCESS: Workflow state machine fix verified!")
    return True

if __name__ == "__main__":
    try:
        test_workflow_fix()
        print("All tests passed!")
    except Exception as e:
        print(f"Test failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)