from typing import Dict, Any, Optional, List
import logging
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


class BaseCommandHandler:
    """Base class for command handlers."""
    
    def __init__(self, session_manager: SessionManager):
        self.session_manager = session_manager
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        """Handle the command and return a response."""
        raise NotImplementedError


class CreateSessionHandler(BaseCommandHandler):
    """Handler for create_session command."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.create_session(command.session_name)
        return TaskmasterResponse(
            action="create_session",
            session_id=session.id,
            suggested_next_actions=["create_tasklist"],
            completion_guidance=f"✅ Session created: {session.id}\n\nNext: Create your task list with 'create_tasklist'."
        )


class CreateTasklistHandler(BaseCommandHandler):
    """Handler for create_tasklist command."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(
                action="create_tasklist",
                status="error",
                completion_guidance="❌ No active session. Use 'create_session' first.",
                suggested_next_actions=["create_session"]
            )
        
        if not command.tasklist:
            return TaskmasterResponse(
                action="create_tasklist",
                session_id=session.id,
                status="template",
                completion_guidance="📝 Provide a list of tasks.\n\nExample:\ntasklist=[\n  {'description': 'Task 1'},\n  {'description': 'Task 2'}\n]",
                suggested_next_actions=["create_tasklist"]
            )
        
        # Create simple tasks
        session.tasks = [
            Task(description=task.get("description", f"Task {i+1}"))
            for i, task in enumerate(command.tasklist)
        ]
        await self.session_manager.update_session(session)
        
        return TaskmasterResponse(
            action="create_tasklist",
            session_id=session.id,
            tasks_created=len(session.tasks),
            suggested_next_actions=["execute_next"],
            completion_guidance=f"✅ Created {len(session.tasks)} tasks.\n\nNext: Use 'execute_next' to start working."
        )


class ExecuteNextHandler(BaseCommandHandler):
    """Handler for execute_next command."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(
                action="execute_next",
                status="error",
                completion_guidance="❌ No active session.",
                suggested_next_actions=["create_session"]
            )
        
        # Find next pending task
        next_task = next((task for task in session.tasks if task.status == "pending"), None)
        
        if not next_task:
            return TaskmasterResponse(
                action="execute_next",
                session_id=session.id,
                status="completed",
                completion_guidance="🎉 All tasks completed!\n\nUse 'end_session' to finish.",
                suggested_next_actions=["end_session"]
            )
        
        # Count progress
        completed = sum(1 for t in session.tasks if t.status == "completed")
        total = len(session.tasks)
        
        return TaskmasterResponse(
            action="execute_next",
            session_id=session.id,
            current_task_id=next_task.id,
            current_task_description=next_task.description,
            progress=f"{completed}/{total}",
            suggested_next_actions=["mark_complete"],
            completion_guidance=f"📋 Current task ({completed + 1}/{total}):\n{next_task.description}\n\nComplete this task, then call 'mark_complete'."
        )


class MarkCompleteHandler(BaseCommandHandler):
    """Handler for mark_complete command."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(
                action="mark_complete",
                status="error",
                completion_guidance="❌ No active session.",
                suggested_next_actions=["create_session"]
            )
        
        # Find current pending task
        current_task = next((task for task in session.tasks if task.status == "pending"), None)
        
        if not current_task:
            return TaskmasterResponse(
                action="mark_complete",
                session_id=session.id,
                status="completed",
                completion_guidance="🎉 All tasks already completed!\n\nUse 'end_session' to finish.",
                suggested_next_actions=["end_session"]
            )
        
        # Mark task as completed
        current_task.status = "completed"
        await self.session_manager.update_session(session)
        
        # Check if more tasks remain
        remaining = sum(1 for t in session.tasks if t.status == "pending")
        completed = sum(1 for t in session.tasks if t.status == "completed")
        total = len(session.tasks)
        
        if remaining > 0:
            return TaskmasterResponse(
                action="mark_complete",
                session_id=session.id,
                task_id=current_task.id,
                progress=f"{completed}/{total}",
                suggested_next_actions=["execute_next"],
                completion_guidance=f"✅ Task completed: {current_task.description}\n\nProgress: {completed}/{total}\n\nNext: Use 'execute_next' for the next task."
            )
        else:
            return TaskmasterResponse(
                action="mark_complete",
                session_id=session.id,
                task_id=current_task.id,
                progress=f"{completed}/{total}",
                suggested_next_actions=["end_session"],
                completion_guidance=f"✅ Task completed: {current_task.description}\n\n🎉 All tasks done! Use 'end_session' to finish."
            )


class GetStatusHandler(BaseCommandHandler):
    """Handler for get_status command."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(
                action="get_status",
                status="no_session",
                completion_guidance="❌ No active session.\n\nUse 'create_session' to start.",
                suggested_next_actions=["create_session"]
            )
        
        total_tasks = len(session.tasks)
        completed_tasks = sum(1 for t in session.tasks if t.status == "completed")
        current_task = next((t for t in session.tasks if t.status == "pending"), None)
        
        status_info = f"📊 **SESSION STATUS**\n\n"
        status_info += f"Session ID: {session.id}\n"
        status_info += f"Progress: {completed_tasks}/{total_tasks} tasks completed\n"
        status_info += f"State: {session.workflow_state}\n\n"
        
        if current_task:
            status_info += f"**Current Task:** {current_task.description}\n\n"
        
        if session.tasks:
            status_info += "**Tasks:**\n"
            for i, task in enumerate(session.tasks, 1):
                status_icon = "✅" if task.status == "completed" else "⏳"
                status_info += f"{i}. {status_icon} {task.description}\n"
        else:
            status_info += "**No tasks created yet.**\n"
        
        # Determine next actions
        next_actions = []
        if not session.tasks:
            next_actions = ["create_tasklist"]
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


class EndSessionHandler(BaseCommandHandler):
    """Handler for end_session command."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(
                action="end_session",
                status="error",
                completion_guidance="❌ No active session to end.",
                suggested_next_actions=["create_session"]
            )
        
        total_tasks = len(session.tasks)
        completed_tasks = sum(1 for t in session.tasks if t.status == "completed")
        
        guidance = f"🎉 **SESSION COMPLETED**\n\n"
        guidance += f"Session ID: {session.id}\n"
        guidance += f"Tasks Completed: {completed_tasks}/{total_tasks}\n"
        guidance += f"Ended at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        guidance += "**Thank you for using Taskmaster!**"
        
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
            "end_session": EndSessionHandler(session_manager),
        }
        
        # Map actions to workflow events for state machine integration
        self.action_to_event = {
            "create_session": "CREATE_SESSION",
            "create_tasklist": "CREATE_TASKLIST",
            "execute_next": "START_TASK",
            "mark_complete": "COMPLETE_TASK",
            "end_session": "END_SESSION"
        }
    
    async def execute(self, command: TaskmasterCommand) -> TaskmasterResponse:
        """Execute a command using the appropriate handler with workflow state enforcement."""
        handler = self.handlers.get(command.action)
        if not handler:
            return TaskmasterResponse(
                action=command.action,
                status="error",
                completion_guidance=f"❌ Unknown action: '{command.action}'\n\nAvailable: {', '.join(self.handlers.keys())}"
            )
        
        # Allow status checks and session creation without a session
        if command.action in ["get_status", "create_session"]:
            return await handler.handle(command)
        
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(
                action=command.action,
                status="error",
                completion_guidance="❌ No active session. Use 'create_session' first.",
                suggested_next_actions=["create_session"]
            )
        
        # Workflow state machine integration
        if self.workflow_state_machine:
            await self._synchronize_workflow_state(session)
            
            event_name = self.action_to_event.get(command.action)
            if event_name:
                from .workflow_state_machine import WorkflowEvent
                try:
                    event = WorkflowEvent[event_name]
                    
                    # Prepare context data
                    context_data = {
                        "task_count": len(session.tasks),
                        "completed_tasks": sum(1 for t in session.tasks if t.status == "completed"),
                        "session_id": session.id,
                        **command.data
                    }
                    
                    if not self.workflow_state_machine.trigger_event(event, **context_data):
                        possible_transitions = self.workflow_state_machine.get_possible_transitions(
                            self.workflow_state_machine.current_state
                        )
                        possible_events = [t.event.value for t in possible_transitions]
                        
                        return TaskmasterResponse(
                            action="workflow_gate",
                            status="error",
                            completion_guidance=f"🚦 Action '{command.action}' not allowed in state '{self.workflow_state_machine.current_state.value}'.\n\nTry: {', '.join(possible_events)}",
                            suggested_next_actions=possible_events
                        )
                    
                    # Persist the new state
                    session.workflow_state = self.workflow_state_machine.current_state.value
                    await self.session_manager.update_session(session)
                    
                except (KeyError, ValueError) as e:
                    logger.warning(f"Could not find WorkflowEvent for action '{command.action}': {e}")
        
        # Execute the handler
        return await handler.handle(command)
    
    async def _synchronize_workflow_state(self, session: Session) -> None:
        """Synchronize workflow state machine with session state."""
        if not self.workflow_state_machine:
            return
        
        try:
            from .workflow_state_machine import WorkflowState
            current_session_state = WorkflowState(session.workflow_state)
            
            if self.workflow_state_machine.current_state != current_session_state:
                self.workflow_state_machine.current_state = current_session_state
                
                # Update context
                self.workflow_state_machine.context.session_id = session.id
                self.workflow_state_machine.context.task_count = len(session.tasks)
                self.workflow_state_machine.context.completed_tasks = sum(
                    1 for t in session.tasks if t.status == "completed"
                )
                self.workflow_state_machine.context.metadata["session"] = session
                
                logger.info(f"Synchronized workflow state to {current_session_state.value}")
        
        except (ValueError, AttributeError) as e:
            logger.warning(f"Could not synchronize workflow state: {e}")
    
    def add_handler(self, action: str, handler: BaseCommandHandler) -> None:
        """Add a new command handler."""
        self.handlers[action] = handler
    
    def get_available_actions(self) -> List[str]:
        """Get list of available actions."""
        return list(self.handlers.keys())
