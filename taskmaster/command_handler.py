from typing import Dict, Any, Optional, List
import logging
import json
from abc import ABC, abstractmethod
from datetime import datetime
from .models import Session, Task
from .session_manager import SessionManager
from .schemas import (
    ActionType,
    create_flexible_request, create_flexible_response,
    extract_guidance, clean_guidance
)

logger = logging.getLogger(__name__)


class TaskmasterCommand:
    """Represents a command to be executed by the TaskmasterCommandHandler."""
    
    def __init__(self, **kwargs):
        if "data" in kwargs:
            merged_data = kwargs["data"].copy()
            merged_data.update({k: v for k, v in kwargs.items() if k != "data"})
            self.data = create_flexible_request(merged_data)
        else:
            self.data = create_flexible_request(kwargs)
        
        self.action = self.data.get("action", "get_status")
        self.task_description = self.data.get("task_description")
        self.session_name = self.data.get("session_name")
        self.tasklist = self.data.get("tasklist", [])
        self.collaboration_context = self.data.get("collaboration_context")
        self.task_id = self.data.get("task_id")
        self.updated_task_data = self.data.get("updated_task_data", {})


class TaskmasterResponse:
    """Represents a response from the TaskmasterCommandHandler."""
    
    def __init__(self, action: str, **kwargs):
        self.data = create_flexible_response(action, **kwargs)
        self.action = self.data["action"]
        self.session_id = self.data.get("session_id")
        self.status = self.data.get("status", "success")
        self.suggested_next_actions = self.data.get("suggested_next_actions", [])
        self.completion_guidance = self.data.get("completion_guidance", "")
        
        for key, value in kwargs.items():
            if not hasattr(self, key):
                setattr(self, key, value)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert response to dictionary format."""
        return clean_guidance(self.data)


class BaseCommandHandler(ABC):
    """Base class for command handlers."""
    
    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager
    
    @abstractmethod
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        """Handle the command and return a response."""
        pass


class CreateSessionHandler(BaseCommandHandler):
    """Handler for create_session command."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.create_session(command.session_name)
        session.description = command.task_description or ""
        await self.session_manager.update_session(session)
        
        guidance = """Session created. I've auto-assigned standard tools (read_file, edit_file, run_terminal_cmd, codebase_search).
Call 'create_tasklist' to define your tasks."""
        
        return TaskmasterResponse(
            action="create_session",
            session_id=session.id,
            suggested_next_actions=["create_tasklist"],
            completion_guidance=guidance,
        )






class CreateTasklistHandler(BaseCommandHandler):
    """Handler for create_tasklist command."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(action="create_tasklist", status="guidance", completion_guidance="No active session.")

        raw_tasklist = command.tasklist

        if not raw_tasklist:
            guidance = """📋 CREATE TASKLIST - Required Format:

✅ CORRECT FORMAT (JSON array with double quotes):
[{"description": "Task 1 description"}, {"description": "Task 2 description"}]

❌ AVOID THESE COMMON ERRORS:
- Single quotes: [{'description': 'task'}]  ← WRONG
- Missing quotes: [{description: "task"}]  ← WRONG  
- Extra characters: [{"description": "task"},]  ← WRONG
- Malformed JSON: [{"description": "task" "description": "task2"}]  ← WRONG

💡 EXAMPLE:
[{"description": "Set up project structure"}, {"description": "Implement authentication"}, {"description": "Add user management"}]"""
            return TaskmasterResponse(
                action="create_tasklist",
                session_id=session.id,
                status="template",
                completion_guidance=guidance,
                suggested_next_actions=["create_tasklist"]
            )

        # Create simple tasks - handle both dict and string formats
        logger.info(f"Raw tasklist type: {type(raw_tasklist)}, length: {len(raw_tasklist) if hasattr(raw_tasklist, '__len__') else 'no length'}")
        logger.info(f"Raw tasklist content: {raw_tasklist}")
        
        # Handle case where tasklist is a JSON string
        if isinstance(raw_tasklist, str):
            try:
                import json
                raw_tasklist = json.loads(raw_tasklist)
                logger.info(f"Parsed tasklist from JSON string: {raw_tasklist}")
            except (json.JSONDecodeError, TypeError) as e:
                logger.error(f"Failed to parse tasklist JSON: {e}")
                guidance = f"""❌ JSON PARSING ERROR: {e}

🔧 COMMON FIXES:
1. Use double quotes: "description" not 'description'
2. Remove trailing commas: [{"desc": "task"}] not [{"desc": "task"},]
3. Fix missing commas: [{"desc": "task"} {"desc": "task2"}] → [{"desc": "task"}, {"desc": "task2"}]
4. Check brackets: [{"desc": "task"}] not [{"desc": "task"}]

✅ CORRECT FORMAT:
[{"description": "Your task description"}]"""
                return TaskmasterResponse(
                    action="create_tasklist",
                    session_id=session.id,
                    status="error",
                    completion_guidance=guidance,
                    suggested_next_actions=["create_tasklist"]
                )
        
        tasks = []
        for i, task in enumerate(raw_tasklist):
            logger.info(f"Task {i}: type={type(task)}, content={task}")
            if isinstance(task, dict):
                description = task.get("description", f"Task {i+1}")
            else:
                description = str(task)
            tasks.append(Task(description=description))
        session.tasks = tasks
        await self.session_manager.update_session(session)
        
        guidance = f"""✅ Tasklist created with {len(session.tasks)} tasks.

📋 WORKFLOW STATUS:
- Session: {session.name}
- Tasks: {len(session.tasks)} total
- Current: Task 1 of {len(session.tasks)}

▶️ NEXT STEP: Call 'execute_next' to start working on the first task."""
        
        return TaskmasterResponse(
            action="create_tasklist",
            session_id=session.id,
            tasks_created=len(session.tasks),
            suggested_next_actions=["execute_next"],
            completion_guidance=guidance
        )




class ExecuteNextHandler(BaseCommandHandler):
    """Handler for execute_next command."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session: 
            return TaskmasterResponse(action="execute_next", status="guidance", completion_guidance="No active session.")
            
        # Get current task based on index
        if session.current_task_index >= len(session.tasks):
            guidance = "All tasks completed! Use 'end_session' to finish."
            return TaskmasterResponse(
                action="execute_next",
                status="completed",
                completion_guidance=guidance,
                suggested_next_actions=["end_session"]
            )

        current_task = session.tasks[session.current_task_index]
        
        guidance = f"""🎯 CURRENT TASK: {current_task.description}

📊 PROGRESS: Task {session.current_task_index + 1} of {len(session.tasks)}

🛠️ AVAILABLE TOOLS:
- read_file: Read and examine files
- edit_file: Modify code and files  
- run_terminal_cmd: Execute commands
- codebase_search: Find code patterns

✅ WHEN DONE: Call 'mark_complete' to finish this task and move to the next one."""
        
        return TaskmasterResponse(
            action="execute_next",
            session_id=session.id,
            current_task_id=current_task.id,
            current_task_description=current_task.description,
            suggested_next_actions=["mark_complete", "collaboration_request"],
            completion_guidance=guidance
        )


class MarkCompleteHandler(BaseCommandHandler):
    """Handler for mark_complete command."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(action="mark_complete", status="guidance", completion_guidance="No active session.")

        # Mark current task as completed and move to next
        if session.current_task_index < len(session.tasks):
            current_task = session.tasks[session.current_task_index]
            current_task.status = "completed"
            session.current_task_index += 1
            
            if session.current_task_index >= len(session.tasks):
                # Update workflow state to completed when all tasks are done
                session.workflow_state = "workflow_completed"
                guidance = f"""🎉 ALL TASKS COMPLETED!

📊 FINAL STATUS:
- Session: {session.name}
- Tasks completed: {len(session.tasks)}/{len(session.tasks)}
- Status: Ready to finish

🏁 FINAL STEP: Call 'end_session' to complete the workflow."""
                next_actions = ["end_session"]
            else:
                guidance = f"""✅ TASK COMPLETED: {current_task.description}

📊 PROGRESS: {session.current_task_index}/{len(session.tasks)} tasks done

▶️ NEXT STEP: Call 'execute_next' to start the next task."""
                next_actions = ["execute_next"]
        else:
            guidance = "All tasks completed! Use 'end_session' to finish."
            next_actions = ["end_session"]

        await self.session_manager.update_session(session)
        
        return TaskmasterResponse(
            action="mark_complete",
            session_id=session.id,
            suggested_next_actions=next_actions,
            completion_guidance=guidance
        )


class GetStatusHandler(BaseCommandHandler):
    """Handler for get_status command."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(
                action="get_status",
                status="no_session",
                completion_guidance="❌ **No active session.** Use `create_session` to start.",
                suggested_next_actions=["create_session"]
            )

        total_tasks = len(session.tasks)
        completed_tasks = len([t for t in session.tasks if t.status == "completed"])
        current_task = next((t for t in session.tasks if t.status == "pending"), None)
        
        status_info = f"""
📊 **SESSION STATUS**

**Session ID**: {session.id}
**Progress**: {completed_tasks}/{total_tasks} tasks completed
**Current State**: {session.workflow_state}

"""
        
        if current_task:
            status_info += f"""**Current Task**: {current_task.description}
**Status**: {current_task.status}

"""
        
        if session.tasks:
            status_info += "**Tasks:**\n"
            for i, task in enumerate(session.tasks, 1):
                status = "✅" if task.status == "completed" else "⏳"
                phase = ""
                status_info += f"{i}. {status} {task.description}{phase}\n"
        else:
            status_info += "**No tasks created yet.**\n"

        next_actions = []
        if not session.tasks:
            next_actions = ["six_hat_thinking"]
        elif current_task:
            next_actions = ["execute_next"]
        else:
            next_actions = ["end_session"]

        return TaskmasterResponse(
            action="get_status",
            session_id=session.id,
            total_tasks=total_tasks,
            completed_tasks=completed_tasks,
            current_task_id=current_task.id if current_task else None,
            suggested_next_actions=next_actions,
            completion_guidance=status_info
        )


class CollaborationRequestHandler(BaseCommandHandler):
    """Handler for collaboration_request command."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(action="collaboration_request", status="guidance", completion_guidance="No active session.")

        context = command.collaboration_context or "No context provided."
        guidance = f"""
🤝 **WORKFLOW PAUSED FOR USER COLLABORATION**

The agent has requested help with the following context:
> {context}

**To Resume Workflow**:
The user must provide feedback. The agent should then use the `edit_task` command to update the plan based on the user's response and then continue with `execute_next`.
"""
        return TaskmasterResponse(
            action="collaboration_request",
            session_id=session.id,
            status="paused",
            completion_guidance=guidance,
            suggested_next_actions=["edit_task"]
        )


class EditTaskHandler(BaseCommandHandler):
    """Handler for edit_task command."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(action="edit_task", status="guidance", completion_guidance="No active session.")

        task_id = command.task_id
        updated_data = command.updated_task_data

        if not task_id or not updated_data:
            return TaskmasterResponse(
                action="edit_task",
                status="template",
                completion_guidance="""
🛠️ **EDIT TASK**

Update a task based on user feedback or new requirements.

**Example edit_task call:**
```json
{
  "action": "edit_task",
  "task_id": "task_123",
  "updated_task_data": {
    "description": "Updated task description",
    "complexity_level": "complex"
  }
}
```
""",
                suggested_next_actions=["edit_task"]
            )

        # Find and update the task
        task = next((t for t in session.tasks if t.id == task_id), None)
        if not task:
            return TaskmasterResponse(
                action="edit_task",
                status="error",
                completion_guidance=f"❌ **Task not found**: {task_id}",
                suggested_next_actions=["get_status"]
            )

        # Update task fields
        for key, value in updated_data.items():
            if hasattr(task, key):
                setattr(task, key, value)

        await self.session_manager.update_session(session)

        return TaskmasterResponse(
            action="edit_task",
            session_id=session.id,
            task_id=task_id,
            completion_guidance=f"✅ **Task updated successfully**: {task.description}",
            suggested_next_actions=["execute_next"]
        )


class EndSessionHandler(BaseCommandHandler):
    """Handler for end_session command."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(action="end_session", status="guidance", completion_guidance="No active session to end.")

        total_tasks = len(session.tasks)
        completed_tasks = len([t for t in session.tasks if t.status == "completed"])
        
        guidance = f"""
🎉 **SESSION COMPLETED**

**Final Summary:**
- Session ID: {session.id}
- Tasks Completed: {completed_tasks}/{total_tasks}
- Session ended at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

**Thank you for using Taskmaster!**
"""
        
        # Session cleanup would happen here if needed
        
        return TaskmasterResponse(
            action="end_session",
            session_id=session.id,
            total_tasks=total_tasks,
            completed_tasks=completed_tasks,
            completion_guidance=guidance
        )


class TaskmasterCommandHandler:
    """Main command handler that orchestrates all taskmaster operations."""
    
    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager
        
        # Get workflow state machine from session manager
        self.workflow_state_machine = getattr(session_manager, 'workflow_state_machine', None)
        
        self.handlers = {
            "create_session": CreateSessionHandler(session_manager),
            "create_tasklist": CreateTasklistHandler(session_manager),
            "execute_next": ExecuteNextHandler(session_manager),
            "mark_complete": MarkCompleteHandler(session_manager),
            "get_status": GetStatusHandler(session_manager),
            "collaboration_request": CollaborationRequestHandler(session_manager),
            "edit_task": EditTaskHandler(session_manager),
            "end_session": EndSessionHandler(session_manager),
        }
        
        # Map actions to workflow events for state machine integration
        self.action_to_event = {
            "create_session": "CREATE_SESSION",
            "create_tasklist": "CREATE_TASKLIST",
            "execute_next": "EXECUTE_TASK",
            "mark_complete": "COMPLETE_TASK",
            "collaboration_request": "REQUEST_COLLABORATION",
            "edit_task": "EDIT_TASK",
            "end_session": "END_SESSION"
        }
    
    async def execute(self, command: TaskmasterCommand) -> TaskmasterResponse:
        """Execute a command using the appropriate handler with workflow state enforcement."""
        handler = self.handlers.get(command.action)
        if not handler:
            return TaskmasterResponse(
                action=command.action,
                status="guidance",
                completion_guidance=f"❌ **ERROR**: Action '{command.action}' is not recognized.\n\nAvailable actions: {', '.join(self.handlers.keys())}"
            )

        # Allow status checks and session creation without a session
        if command.action in ["get_status", "create_session"]:
            return await handler.handle(command)

        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(action=command.action, status="guidance", completion_guidance="❌ **ERROR**: No active session. Please start with 'create_session'.")

        # --- Enhanced Workflow State Machine Integration ---
        if self.workflow_state_machine:
            # Synchronize workflow state machine with session state
            await self._synchronize_workflow_state(session)
            
            # Special handling for execute_next command - context-aware event triggering
            if command.action == "execute_next":
                event_name = self._get_execute_next_event(self.workflow_state_machine.current_state, session)
                if not event_name:
                    # No state transition needed, just execute the handler
                    return await handler.handle(command)
            # Special handling for mark_complete command - context-aware event triggering
            elif command.action == "mark_complete":
                event_name = self._get_mark_complete_event(session)
            else:
                event_name = self.action_to_event.get(command.action)
            
            if event_name:
                from .workflow_state_machine import WorkflowEvent
                try:
                    event = WorkflowEvent[event_name]
                    
                    # Prepare context data for the workflow state machine
                    context_data = {
                        "task_count": len(session.tasks),
                        "completed_tasks": len([t for t in session.tasks if t.status == "completed"]),
                        "session_id": session.id,
                        **command.data
                    }
                    
                    if not self.workflow_state_machine.trigger_event(event, **context_data):
                        # Find the expected transition for the current state to provide better guidance
                        possible_transitions = self.workflow_state_machine.get_possible_transitions(self.workflow_state_machine.current_state)
                        possible_events = [t.event.value for t in possible_transitions]
                        
                        return TaskmasterResponse(
                            action="workflow_gate",
                            status="guidance",
                            completion_guidance=f"🚦 **WORKFLOW ALERT**: Action '{command.action}' is not allowed in the current state '{self.workflow_state_machine.current_state.value}'.\n\n"
                                               f"Possible next actions are: {', '.join(possible_events)}",
                            suggested_next_actions=possible_events
                        )
                    
                    # Persist the new state back to session
                    session.workflow_state = self.workflow_state_machine.current_state.value
                    await self.session_manager.update_session(session)
                    
                except (KeyError, ValueError) as e:
                    logger.warning(f"Could not find a corresponding WorkflowEvent for action '{command.action}': {e}")

        # Execute the handler
        return await handler.handle(command)

    def _get_execute_next_event(self, current_state, session: Session) -> Optional[str]:
        """Get the appropriate event for execute_next based on current workflow state."""
        from .workflow_state_machine import WorkflowState
        
        if current_state == WorkflowState.TASKLIST_CREATED:
            return "EXECUTE_TASK"  # Start first task
        elif current_state == WorkflowState.TASK_IN_PROGRESS:
            return "EXECUTE_TASK"  # Continue to next task
        else:
            return "EXECUTE_TASK"  # Default fallback

    def _get_mark_complete_event(self, session) -> Optional[str]:
        """Get the appropriate event for mark_complete based on current task phase."""
        # Find the current task
        current_task = next((task for task in session.tasks if task.status == "pending"), None)
        if not current_task:
            return None  # No current task, let handler deal with it
        
        # For simplified workflow, always trigger COMPLETE_TASK
        return "COMPLETE_TASK"

    async def _synchronize_workflow_state(self, session: Session) -> None:
        """Synchronize workflow state machine with session state."""
        if not self.workflow_state_machine:
            return
            
        try:
            from .workflow_state_machine import WorkflowState
            current_session_state = WorkflowState(session.workflow_state)
            
            # Only sync if states are different
            if self.workflow_state_machine.current_state != current_session_state:
                self.workflow_state_machine.current_state = current_session_state
                
                # Update context with session information
                self.workflow_state_machine.context.session_id = session.id
                self.workflow_state_machine.context.task_count = len(session.tasks)
                self.workflow_state_machine.context.completed_tasks = len([t for t in session.tasks if t.status == "completed"])
                self.workflow_state_machine.context.metadata["session"] = session
                
                logger.info(f"Synchronized workflow state machine to {current_session_state.value}")
                
        except (ValueError, AttributeError) as e:
            logger.warning(f"Could not synchronize workflow state: {e}")

    def add_handler(self, action: str, handler: BaseCommandHandler) -> None:
        """Add a new command handler."""
        self.handlers[action] = handler
    
    def get_available_actions(self) -> List[str]:
        """Get list of available actions."""
        return list(self.handlers.keys())