"""
Workflow state machine for managing Taskmaster workflow states and transitions.

Provides explicit state management with validation, transition rules,
and event handling for robust workflow control.
"""

import logging
from typing import Dict, Any, Optional, List, Callable, Set
from enum import Enum
from dataclasses import dataclass, field
from .exceptions import TaskmasterError, ErrorCode

logger = logging.getLogger(__name__)


class WorkflowState(Enum):
    """Enumeration of workflow states."""
    
    # Initial states
    UNINITIALIZED = "uninitialized"
    INITIALIZING = "initializing"
    
    # Session states
    SESSION_CREATED = "session_created"
    CAPABILITIES_DECLARED = "capabilities_declared"
    TASKLIST_CREATED = "tasklist_created"
    
    # Execution states
    TASK_PLANNING = "task_planning"
    TASK_EXECUTING = "task_executing"
    TASK_VALIDATING = "task_validating"
    
    # Completion states
    TASK_COMPLETED = "task_completed"
    WORKFLOW_COMPLETED = "workflow_completed"
    
    # Error states
    VALIDATION_FAILED = "validation_failed"
    EXECUTION_FAILED = "execution_failed"
    
    # Special states
    PAUSED = "paused"
    COLLABORATION_REQUESTED = "collaboration_requested"


class WorkflowEvent(Enum):
    """Enumeration of workflow events that trigger state transitions."""
    
    # Initialization events
    INITIALIZE = "initialize"
    
    # Session events
    CREATE_SESSION = "create_session"
    DECLARE_CAPABILITIES = "declare_capabilities"
    CREATE_TASKLIST = "create_tasklist"
    
    # Task execution events
    START_TASK = "start_task"
    PLAN_TASK = "plan_task"
    EXECUTE_TASK = "execute_task"
    VALIDATE_TASK = "validate_task"
    COMPLETE_TASK = "complete_task"
    
    # Validation events
    VALIDATION_PASSED = "validation_passed"
    VALIDATION_FAILED = "validation_failed"
    
    # Error events
    EXECUTION_ERROR = "execution_error"
    VALIDATION_ERROR = "validation_error"
    
    # Control events
    PAUSE_WORKFLOW = "pause_workflow"
    RESUME_WORKFLOW = "resume_workflow"
    REQUEST_COLLABORATION = "request_collaboration"
    COLLABORATION_RESPONSE = "collaboration_response"
    
    # Completion events
    FINISH_WORKFLOW = "finish_workflow"


@dataclass
class StateTransition:
    """Represents a state transition with conditions and actions."""
    
    from_state: WorkflowState
    to_state: WorkflowState
    event: WorkflowEvent
    condition: Optional[Callable[[Dict[str, Any]], bool]] = None
    action: Optional[Callable[[Dict[str, Any]], None]] = None
    description: str = ""


@dataclass
class WorkflowContext:
    """Context information for the workflow state machine."""
    
    session_id: Optional[str] = None
    current_task_id: Optional[str] = None
    task_count: int = 0
    completed_tasks: int = 0
    validation_attempts: int = 0
    error_count: int = 0
    pause_reason: Optional[str] = None
    collaboration_context: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


class WorkflowStateMachine:
    """
    State machine for managing Taskmaster workflow states and transitions.
    
    Provides explicit state management with validation, transition rules,
    and event handling for robust workflow control.
    """
    
    def __init__(self, initial_state: WorkflowState = WorkflowState.UNINITIALIZED):
        """
        Initialize the workflow state machine.
        
        Args:
            initial_state: The initial state of the workflow
        """
        self.current_state = initial_state
        self.context = WorkflowContext()
        self.transitions: Dict[tuple, StateTransition] = {}
        self.state_handlers: Dict[WorkflowState, List[Callable]] = {}
        self.event_listeners: Dict[WorkflowEvent, List[Callable]] = {}
        
        # Initialize default transitions
        self._setup_default_transitions()
        
        logger.info(f"WorkflowStateMachine initialized with state: {initial_state.value}")
    
    def _setup_default_transitions(self) -> None:
        """Set up default state transitions."""
        
        # Initialization transitions
        self.add_transition(
            WorkflowState.UNINITIALIZED,
            WorkflowState.INITIALIZING,
            WorkflowEvent.INITIALIZE,
            description="Initialize workflow"
        )
        
        self.add_transition(
            WorkflowState.INITIALIZING,
            WorkflowState.SESSION_CREATED,
            WorkflowEvent.CREATE_SESSION,
            description="Create new session"
        )
        
        # Session setup transitions
        self.add_transition(
            WorkflowState.SESSION_CREATED,
            WorkflowState.CAPABILITIES_DECLARED,
            WorkflowEvent.DECLARE_CAPABILITIES,
            description="Declare capabilities"
        )
        
        self.add_transition(
            WorkflowState.CAPABILITIES_DECLARED,
            WorkflowState.TASKLIST_CREATED,
            WorkflowEvent.CREATE_TASKLIST,
            description="Create tasklist"
        )
        
        # Task execution transitions
        self.add_transition(
            WorkflowState.TASKLIST_CREATED,
            WorkflowState.TASK_PLANNING,
            WorkflowEvent.START_TASK,
            description="Start first task"
        )
        
        self.add_transition(
            WorkflowState.TASK_COMPLETED,
            WorkflowState.TASK_PLANNING,
            WorkflowEvent.START_TASK,
            condition=lambda ctx: ctx.completed_tasks < ctx.task_count,
            description="Start next task"
        )
        
        self.add_transition(
            WorkflowState.TASK_PLANNING,
            WorkflowState.TASK_EXECUTING,
            WorkflowEvent.PLAN_TASK,
            description="Plan task execution"
        )
        
        self.add_transition(
            WorkflowState.TASK_EXECUTING,
            WorkflowState.TASK_VALIDATING,
            WorkflowEvent.EXECUTE_TASK,
            description="Execute task"
        )
        
        self.add_transition(
            WorkflowState.TASK_VALIDATING,
            WorkflowState.TASK_COMPLETED,
            WorkflowEvent.VALIDATION_PASSED,
            description="Task validation passed"
        )
        
        # Error handling transitions
        self.add_transition(
            WorkflowState.TASK_VALIDATING,
            WorkflowState.VALIDATION_FAILED,
            WorkflowEvent.VALIDATION_FAILED,
            description="Task validation failed"
        )
        
        self.add_transition(
            WorkflowState.VALIDATION_FAILED,
            WorkflowState.TASK_EXECUTING,
            WorkflowEvent.EXECUTE_TASK,
            description="Retry task execution"
        )
        
        self.add_transition(
            WorkflowState.TASK_EXECUTING,
            WorkflowState.EXECUTION_FAILED,
            WorkflowEvent.EXECUTION_ERROR,
            description="Task execution failed"
        )
        
        # Collaboration transitions
        self.add_transition(
            WorkflowState.TASK_EXECUTING,
            WorkflowState.COLLABORATION_REQUESTED,
            WorkflowEvent.REQUEST_COLLABORATION,
            description="Request user collaboration"
        )
        
        self.add_transition(
            WorkflowState.COLLABORATION_REQUESTED,
            WorkflowState.TASK_EXECUTING,
            WorkflowEvent.COLLABORATION_RESPONSE,
            description="Resume after collaboration"
        )
        
        # Pause/resume transitions
        for state in [WorkflowState.TASK_PLANNING, WorkflowState.TASK_EXECUTING, WorkflowState.TASK_VALIDATING]:
            self.add_transition(
                state,
                WorkflowState.PAUSED,
                WorkflowEvent.PAUSE_WORKFLOW,
                description=f"Pause workflow from {state.value}"
            )
            
            self.add_transition(
                WorkflowState.PAUSED,
                state,
                WorkflowEvent.RESUME_WORKFLOW,
                description=f"Resume workflow to {state.value}"
            )
        
        # Completion transitions
        self.add_transition(
            WorkflowState.TASK_COMPLETED,
            WorkflowState.WORKFLOW_COMPLETED,
            WorkflowEvent.FINISH_WORKFLOW,
            condition=lambda ctx: ctx.completed_tasks >= ctx.task_count,
            description="Complete workflow"
        )
    
    def add_transition(
        self,
        from_state: WorkflowState,
        to_state: WorkflowState,
        event: WorkflowEvent,
        condition: Optional[Callable[[WorkflowContext], bool]] = None,
        action: Optional[Callable[[WorkflowContext], None]] = None,
        description: str = ""
    ) -> None:
        """
        Add a state transition.
        
        Args:
            from_state: Source state
            to_state: Target state
            event: Triggering event
            condition: Optional condition function
            action: Optional action function
            description: Description of the transition
        """
        key = (from_state, event)
        transition = StateTransition(
            from_state=from_state,
            to_state=to_state,
            event=event,
            condition=condition,
            action=action,
            description=description
        )
        self.transitions[key] = transition
        logger.debug(f"Added transition: {from_state.value} -> {to_state.value} on {event.value}")
    
    def trigger_event(self, event: WorkflowEvent, **kwargs) -> bool:
        """
        Trigger an event and potentially transition to a new state.
        
        Args:
            event: The event to trigger
            **kwargs: Additional context data
            
        Returns:
            bool: True if transition occurred, False otherwise
        """
        # Update context with provided data
        for key, value in kwargs.items():
            if hasattr(self.context, key):
                setattr(self.context, key, value)
            else:
                self.context.metadata[key] = value
        
        # Find matching transition
        key = (self.current_state, event)
        transition = self.transitions.get(key)
        
        if not transition:
            logger.warning(f"No transition found for {self.current_state.value} on {event.value}")
            return False
        
        # Check condition if present
        if transition.condition and not transition.condition(self.context):
            logger.debug(f"Transition condition not met for {self.current_state.value} -> {transition.to_state.value}")
            return False
        
        # Execute action if present
        if transition.action:
            try:
                transition.action(self.context)
            except Exception as e:
                logger.error(f"Error executing transition action: {e}")
                raise TaskmasterError(
                    message=f"Error executing transition action: {str(e)}",
                    error_code=ErrorCode.INTERNAL_ERROR,
                    details={"transition": transition.description, "event": event.value},
                    cause=e
                )
        
        # Perform transition
        old_state = self.current_state
        self.current_state = transition.to_state
        
        logger.info(f"State transition: {old_state.value} -> {self.current_state.value} (event: {event.value})")
        
        # Notify event listeners
        self._notify_event_listeners(event, old_state, self.current_state)
        
        # Execute state handlers
        self._execute_state_handlers(self.current_state)
        
        return True
    
    def can_trigger_event(self, event: WorkflowEvent) -> bool:
        """
        Check if an event can be triggered from the current state.
        
        Args:
            event: The event to check
            
        Returns:
            bool: True if event can be triggered, False otherwise
        """
        key = (self.current_state, event)
        transition = self.transitions.get(key)
        
        if not transition:
            return False
        
        if transition.condition:
            return transition.condition(self.context)
        
        return True
    
    def get_available_events(self) -> List[WorkflowEvent]:
        """
        Get list of events that can be triggered from the current state.
        
        Returns:
            List of available events
        """
        available_events = []
        
        for (state, event), transition in self.transitions.items():
            if state == self.current_state:
                if not transition.condition or transition.condition(self.context):
                    available_events.append(event)
        
        return available_events
    
    def add_state_handler(self, state: WorkflowState, handler: Callable[[WorkflowContext], None]) -> None:
        """
        Add a handler for when entering a specific state.
        
        Args:
            state: The state to handle
            handler: The handler function
        """
        if state not in self.state_handlers:
            self.state_handlers[state] = []
        self.state_handlers[state].append(handler)
        logger.debug(f"Added state handler for {state.value}")
    
    def add_event_listener(self, event: WorkflowEvent, listener: Callable[[WorkflowEvent, WorkflowState, WorkflowState], None]) -> None:
        """
        Add a listener for specific events.
        
        Args:
            event: The event to listen for
            listener: The listener function
        """
        if event not in self.event_listeners:
            self.event_listeners[event] = []
        self.event_listeners[event].append(listener)
        logger.debug(f"Added event listener for {event.value}")
    
    def _execute_state_handlers(self, state: WorkflowState) -> None:
        """Execute handlers for the given state."""
        handlers = self.state_handlers.get(state, [])
        for handler in handlers:
            try:
                handler(self.context)
            except Exception as e:
                logger.error(f"Error executing state handler for {state.value}: {e}")
    
    def _notify_event_listeners(self, event: WorkflowEvent, old_state: WorkflowState, new_state: WorkflowState) -> None:
        """Notify event listeners."""
        listeners = self.event_listeners.get(event, [])
        for listener in listeners:
            try:
                listener(event, old_state, new_state)
            except Exception as e:
                logger.error(f"Error notifying event listener for {event.value}: {e}")
    
    def get_state_info(self) -> Dict[str, Any]:
        """
        Get current state information.
        
        Returns:
            Dictionary containing state information
        """
        return {
            "current_state": self.current_state.value,
            "available_events": [event.value for event in self.get_available_events()],
            "context": {
                "session_id": self.context.session_id,
                "current_task_id": self.context.current_task_id,
                "task_count": self.context.task_count,
                "completed_tasks": self.context.completed_tasks,
                "validation_attempts": self.context.validation_attempts,
                "error_count": self.context.error_count,
                "pause_reason": self.context.pause_reason,
                "collaboration_context": self.context.collaboration_context,
                "metadata": self.context.metadata
            },
            "is_paused": self.current_state == WorkflowState.PAUSED,
            "is_completed": self.current_state == WorkflowState.WORKFLOW_COMPLETED,
            "is_error_state": self.current_state in [WorkflowState.VALIDATION_FAILED, WorkflowState.EXECUTION_FAILED],
            "can_progress": len(self.get_available_events()) > 0
        }
    
    def reset(self, initial_state: WorkflowState = WorkflowState.UNINITIALIZED) -> None:
        """
        Reset the state machine to initial state.
        
        Args:
            initial_state: The state to reset to
        """
        old_state = self.current_state
        self.current_state = initial_state
        self.context = WorkflowContext()
        
        logger.info(f"State machine reset: {old_state.value} -> {initial_state.value}")
    
    def export_state(self) -> Dict[str, Any]:
        """
        Export the current state for persistence.
        
        Returns:
            Dictionary containing exportable state data
        """
        return {
            "current_state": self.current_state.value,
            "context": {
                "session_id": self.context.session_id,
                "current_task_id": self.context.current_task_id,
                "task_count": self.context.task_count,
                "completed_tasks": self.context.completed_tasks,
                "validation_attempts": self.context.validation_attempts,
                "error_count": self.context.error_count,
                "pause_reason": self.context.pause_reason,
                "collaboration_context": self.context.collaboration_context,
                "metadata": self.context.metadata
            }
        }
    
    def import_state(self, state_data: Dict[str, Any]) -> None:
        """
        Import state from persistence data.
        
        Args:
            state_data: Dictionary containing state data
        """
        try:
            self.current_state = WorkflowState(state_data["current_state"])
            
            context_data = state_data.get("context", {})
            self.context = WorkflowContext(
                session_id=context_data.get("session_id"),
                current_task_id=context_data.get("current_task_id"),
                task_count=context_data.get("task_count", 0),
                completed_tasks=context_data.get("completed_tasks", 0),
                validation_attempts=context_data.get("validation_attempts", 0),
                error_count=context_data.get("error_count", 0),
                pause_reason=context_data.get("pause_reason"),
                collaboration_context=context_data.get("collaboration_context"),
                metadata=context_data.get("metadata", {})
            )
            
            logger.info(f"State machine imported with state: {self.current_state.value}")
            
        except Exception as e:
            logger.error(f"Error importing state: {e}")
            raise TaskmasterError(
                message=f"Error importing workflow state: {str(e)}",
                error_code=ErrorCode.INTERNAL_ERROR,
                details={"state_data": state_data},
                cause=e
            ) 