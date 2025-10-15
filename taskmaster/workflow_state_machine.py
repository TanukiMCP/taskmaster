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
    """Enumeration of workflow states - simplified."""
    
    # Initial states
    UNINITIALIZED = "uninitialized"
    
    # Session states
    SESSION_CREATED = "session_created"
    TASKLIST_CREATED = "tasklist_created"
    
    # Execution states
    TASK_EXECUTING = "task_executing"
    
    # Completion states
    TASK_COMPLETED = "task_completed"
    WORKFLOW_COMPLETED = "workflow_completed"
    
    # Error states
    EXECUTION_FAILED = "execution_failed"
    
    # Special states
    PAUSED = "paused"


class WorkflowEvent(Enum):
    """Enumeration of workflow events - simplified."""
    
    # Session events
    CREATE_SESSION = "create_session"
    CREATE_TASKLIST = "create_tasklist"
    
    # Task events
    START_TASK = "start_task"
    COMPLETE_TASK = "complete_task"
    
    # Error events
    EXECUTION_ERROR = "execution_error"
    
    # Special events
    PAUSE = "pause"
    RESUME = "resume"
    END_SESSION = "end_session"


@dataclass
class StateTransition:
    """Represents a state transition with conditions and actions."""
    
    from_state: WorkflowState
    to_state: WorkflowState
    event: WorkflowEvent
    condition: Optional[Callable[['WorkflowContext'], bool]] = None
    action: Optional[Callable[['WorkflowContext'], None]] = None
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
        """Set up simplified default state transitions."""
        
        # Session creation transition
        self.add_transition(
            WorkflowState.UNINITIALIZED,
            WorkflowState.SESSION_CREATED,
            WorkflowEvent.CREATE_SESSION,
            description="Create new session"
        )
        
        # Tasklist creation
        self.add_transition(
            WorkflowState.SESSION_CREATED,
            WorkflowState.TASKLIST_CREATED,
            WorkflowEvent.CREATE_TASKLIST,
            description="Create tasklist"
        )
        
        # Start first task
        self.add_transition(
            WorkflowState.TASKLIST_CREATED,
            WorkflowState.TASK_EXECUTING,
            WorkflowEvent.START_TASK,
            description="Start first task"
        )
        
        # Complete current task
        self.add_transition(
            WorkflowState.TASK_EXECUTING,
            WorkflowState.TASK_COMPLETED,
            WorkflowEvent.COMPLETE_TASK,
            description="Complete current task"
        )
        
        # Start next task
        self.add_transition(
            WorkflowState.TASK_COMPLETED,
            WorkflowState.TASK_EXECUTING,
            WorkflowEvent.START_TASK,
            condition=lambda ctx: ctx.completed_tasks < ctx.task_count,
            description="Start next task"
        )
        
        # Complete workflow when all tasks done
        self.add_transition(
            WorkflowState.TASK_COMPLETED,
            WorkflowState.WORKFLOW_COMPLETED,
            WorkflowEvent.END_SESSION,
            condition=lambda ctx: ctx.completed_tasks >= ctx.task_count,
            description="Complete workflow when all tasks done"
        )
        
        # Error handling transitions
        self.add_transition(
            WorkflowState.TASK_EXECUTING,
            WorkflowState.EXECUTION_FAILED,
            WorkflowEvent.EXECUTION_ERROR,
            description="Task execution failed"
        )
        
        self.add_transition(
            WorkflowState.EXECUTION_FAILED,
            WorkflowState.TASK_EXECUTING,
            WorkflowEvent.START_TASK,
            description="Retry task execution"
        )
        
        # Pause/Resume transitions
        self.add_transition(
            WorkflowState.TASK_EXECUTING,
            WorkflowState.PAUSED,
            WorkflowEvent.PAUSE,
            description="Pause from task execution"
        )
        
        self.add_transition(
            WorkflowState.PAUSED,
            WorkflowState.TASK_EXECUTING,
            WorkflowEvent.RESUME,
            description="Resume to task execution"
        )
    
    def add_transition(
        self,
        from_state: WorkflowState,
        to_state: WorkflowState,
        event: WorkflowEvent,
        condition: Optional[Callable[['WorkflowContext'], bool]] = None,
        action: Optional[Callable[['WorkflowContext'], None]] = None,
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
            available_events = [t.event.value for t in self.get_possible_transitions(self.current_state)]
            logger.warning(f"No transition found for {self.current_state.value} on {event.value}. Available events: {available_events}")
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
    
    def get_possible_transitions(self, state: WorkflowState) -> List[StateTransition]:
        """Get list of possible transitions from a given state."""
        possible_transitions = []
        for (from_state, _), transition in self.transitions.items():
            if from_state == state:
                if not transition.condition or transition.condition(self.context):
                    possible_transitions.append(transition)
        return possible_transitions

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
    
    def add_state_handler(self, state: WorkflowState, handler: Callable[['WorkflowContext'], None]) -> None:
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
            "available_events": [t.event.value for t in self.get_possible_transitions(self.current_state)],
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
            "is_error_state": self.current_state == WorkflowState.EXECUTION_FAILED,
            "can_progress": len(self.get_possible_transitions(self.current_state)) > 0
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