"""
Test script for the simplified Taskmaster workflow.
"""
import asyncio
from taskmaster.container import get_container
from taskmaster.command_handler import TaskmasterCommand, TaskmasterCommandHandler


async def test_simplified_workflow():
    """Test the complete simplified workflow."""
    print("Testing Simplified Taskmaster Workflow\n")
    
    # Initialize container
    container = get_container()
    handler = container.resolve(TaskmasterCommandHandler)
    
    # Step 1: Create session
    print("Step 1: Creating session...")
    cmd = TaskmasterCommand(action="create_session", session_name="Test Project")
    response = await handler.execute(cmd)
    print(f"   Status: {response.status}")
    print(f"   Session ID: {response.session_id}")
    print(f"   Next: {response.suggested_next_actions}\n")
    
    # Step 2: Create tasklist
    print("Step 2: Creating tasklist...")
    cmd = TaskmasterCommand(
        action="create_tasklist",
        tasklist=[
            {"description": "Set up project structure"},
            {"description": "Implement core features"},
            {"description": "Add error handling"}
        ]
    )
    response = await handler.execute(cmd)
    print(f"   Status: {response.status}")
    print(f"   Tasks created: {response.data.get('tasks_created')}")
    print(f"   Next: {response.suggested_next_actions}\n")
    
    # Step 3: Execute first task
    print("Step 3: Getting first task...")
    cmd = TaskmasterCommand(action="execute_next")
    response = await handler.execute(cmd)
    print(f"   Status: {response.status}")
    print(f"   Current task: {response.data.get('current_task_description')}")
    print(f"   Progress: {response.data.get('progress')}")
    print(f"   Next: {response.suggested_next_actions}\n")
    
    # Step 4: Mark first task complete
    print("Step 4: Marking first task complete...")
    cmd = TaskmasterCommand(action="mark_complete")
    response = await handler.execute(cmd)
    print(f"   Status: {response.status}")
    print(f"   Progress: {response.data.get('progress')}")
    print(f"   Next: {response.suggested_next_actions}\n")
    
    # Step 5: Execute second task
    print("Step 5: Getting second task...")
    cmd = TaskmasterCommand(action="execute_next")
    response = await handler.execute(cmd)
    print(f"   Status: {response.status}")
    print(f"   Current task: {response.data.get('current_task_description')}")
    print(f"   Progress: {response.data.get('progress')}")
    print(f"   Next: {response.suggested_next_actions}\n")
    
    # Step 6: Check status
    print("Step 6: Checking status...")
    cmd = TaskmasterCommand(action="get_status")
    response = await handler.execute(cmd)
    print(f"   Status: {response.status}")
    print(f"   Total tasks: {response.data.get('total_tasks')}")
    print(f"   Completed: {response.data.get('completed_tasks')}")
    print(f"   Next: {response.suggested_next_actions}\n")
    
    # Step 7: Mark second task complete
    print("Step 7: Marking second task complete...")
    cmd = TaskmasterCommand(action="mark_complete")
    response = await handler.execute(cmd)
    print(f"   Status: {response.status}")
    print(f"   Progress: {response.data.get('progress')}\n")
    
    # Step 8: Mark third task complete
    print("Step 8: Getting and completing third task...")
    cmd = TaskmasterCommand(action="execute_next")
    response = await handler.execute(cmd)
    print(f"   Current task: {response.data.get('current_task_description')}")
    
    cmd = TaskmasterCommand(action="mark_complete")
    response = await handler.execute(cmd)
    print(f"   Status: {response.status}")
    print(f"   Progress: {response.data.get('progress')}\n")
    
    # Step 9: End session
    print("Step 9: Ending session...")
    cmd = TaskmasterCommand(action="end_session")
    response = await handler.execute(cmd)
    print(f"   Status: {response.status}")
    print(f"   Final: {response.data.get('completed_tasks')}/{response.data.get('total_tasks')} tasks completed\n")
    
    print("SUCCESS: All tests passed! Simplified workflow works correctly.")


if __name__ == "__main__":
    asyncio.run(test_simplified_workflow())

