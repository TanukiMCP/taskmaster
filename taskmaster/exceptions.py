"""
Structured error handling system for the Taskmaster application.

Provides custom exception classes with error codes, context information,
and proper logging integration for better error tracking and debugging.
"""

import logging
from typing import Dict, Any, Optional, Union
from enum import Enum


class ErrorCode(Enum):
    """Enumeration of error codes for categorizing different types of errors."""
    
    # Session-related errors
    SESSION_NOT_FOUND = "SESSION_NOT_FOUND"
    SESSION_CREATION_FAILED = "SESSION_CREATION_FAILED"
    SESSION_PERSISTENCE_FAILED = "SESSION_PERSISTENCE_FAILED"
    
    # Task-related errors
    TASK_NOT_FOUND = "TASK_NOT_FOUND"
    TASK_VALIDATION_FAILED = "TASK_VALIDATION_FAILED"
    TASK_EXECUTION_FAILED = "TASK_EXECUTION_FAILED"
    
    # Capability-related errors
    CAPABILITIES_NOT_DECLARED = "CAPABILITIES_NOT_DECLARED"
    INVALID_CAPABILITY_FORMAT = "INVALID_CAPABILITY_FORMAT"
    CAPABILITY_ASSIGNMENT_FAILED = "CAPABILITY_ASSIGNMENT_FAILED"
    
    # Validation errors
    VALIDATION_RULE_NOT_FOUND = "VALIDATION_RULE_NOT_FOUND"
    VALIDATION_EVIDENCE_INVALID = "VALIDATION_EVIDENCE_INVALID"
    VALIDATION_EXECUTION_FAILED = "VALIDATION_EXECUTION_FAILED"
    
    # Command handling errors
    UNKNOWN_COMMAND = "UNKNOWN_COMMAND"
    COMMAND_EXECUTION_FAILED = "COMMAND_EXECUTION_FAILED"
    INVALID_COMMAND_PARAMETERS = "INVALID_COMMAND_PARAMETERS"
    
    # Configuration errors
    CONFIG_NOT_FOUND = "CONFIG_NOT_FOUND"
    CONFIG_INVALID = "CONFIG_INVALID"
    
    # File system errors
    FILE_NOT_FOUND = "FILE_NOT_FOUND"
    FILE_PERMISSION_DENIED = "FILE_PERMISSION_DENIED"
    DIRECTORY_CREATION_FAILED = "DIRECTORY_CREATION_FAILED"
    
    # General errors
    INTERNAL_ERROR = "INTERNAL_ERROR"
    INVALID_INPUT = "INVALID_INPUT"
    OPERATION_NOT_PERMITTED = "OPERATION_NOT_PERMITTED"


class TaskmasterError(Exception):
    """
    Base exception class for all Taskmaster-related errors.
    
    Provides structured error information including error codes,
    context details, and proper logging integration.
    """
    
    def __init__(
        self,
        message: str,
        error_code: Union[ErrorCode, str],
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None
    ):
        """
        Initialize a TaskmasterError.
        
        Args:
            message: Human-readable error message
            error_code: Error code for categorization
            details: Additional context information
            cause: The underlying exception that caused this error
        """
        super().__init__(message)
        self.message = message
        self.error_code = error_code if isinstance(error_code, ErrorCode) else ErrorCode(error_code)
        self.details = details or {}
        self.cause = cause
        
        # Log the error when created
        self._log_error()
    
    def _log_error(self) -> None:
        """Log the error with appropriate level and context."""
        logger = logging.getLogger(__name__)
        
        log_context = {
            "error_code": self.error_code.value,
            "message": self.message,
            "details": self.details
        }
        
        if self.cause:
            log_context["cause"] = str(self.cause)
        
        logger.error(f"TaskmasterError: {self.error_code.value} - {self.message}", extra=log_context)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert error to dictionary format for API responses."""
        return {
            "error_code": self.error_code.value,
            "message": self.message,
            "details": self.details,
            "cause": str(self.cause) if self.cause else None
        }
    
    def __str__(self) -> str:
        """String representation of the error."""
        return f"{self.error_code.value}: {self.message}"


class SessionError(TaskmasterError):
    """Exception for session-related errors."""
    
    def __init__(
        self,
        message: str,
        session_id: Optional[str] = None,
        error_code: Union[ErrorCode, str] = ErrorCode.SESSION_NOT_FOUND,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None
    ):
        details = details or {}
        if session_id:
            details["session_id"] = session_id
        
        super().__init__(message, error_code, details, cause)


class TaskError(TaskmasterError):
    """Exception for task-related errors."""
    
    def __init__(
        self,
        message: str,
        task_id: Optional[str] = None,
        session_id: Optional[str] = None,
        error_code: Union[ErrorCode, str] = ErrorCode.TASK_NOT_FOUND,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None
    ):
        details = details or {}
        if task_id:
            details["task_id"] = task_id
        if session_id:
            details["session_id"] = session_id
        
        super().__init__(message, error_code, details, cause)


class ValidationError(TaskmasterError):
    """Exception for validation-related errors."""
    
    def __init__(
        self,
        message: str,
        rule_name: Optional[str] = None,
        task_id: Optional[str] = None,
        error_code: Union[ErrorCode, str] = ErrorCode.VALIDATION_EXECUTION_FAILED,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None
    ):
        details = details or {}
        if rule_name:
            details["rule_name"] = rule_name
        if task_id:
            details["task_id"] = task_id
        
        super().__init__(message, error_code, details, cause)


class CapabilityError(TaskmasterError):
    """Exception for capability-related errors."""
    
    def __init__(
        self,
        message: str,
        capability_name: Optional[str] = None,
        capability_type: Optional[str] = None,
        error_code: Union[ErrorCode, str] = ErrorCode.INVALID_CAPABILITY_FORMAT,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None
    ):
        details = details or {}
        if capability_name:
            details["capability_name"] = capability_name
        if capability_type:
            details["capability_type"] = capability_type
        
        super().__init__(message, error_code, details, cause)


class CommandError(TaskmasterError):
    """Exception for command handling errors."""
    
    def __init__(
        self,
        message: str,
        command_action: Optional[str] = None,
        error_code: Union[ErrorCode, str] = ErrorCode.COMMAND_EXECUTION_FAILED,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None
    ):
        details = details or {}
        if command_action:
            details["command_action"] = command_action
        
        super().__init__(message, error_code, details, cause)


class ConfigurationError(TaskmasterError):
    """Exception for configuration-related errors."""
    
    def __init__(
        self,
        message: str,
        config_key: Optional[str] = None,
        error_code: Union[ErrorCode, str] = ErrorCode.CONFIG_INVALID,
        details: Optional[Dict[str, Any]] = None,
        cause: Optional[Exception] = None
    ):
        details = details or {}
        if config_key:
            details["config_key"] = config_key
        
        super().__init__(message, error_code, details, cause)


def handle_exception(func):
    """
    Decorator for handling exceptions and converting them to TaskmasterError.
    
    Usage:
        @handle_exception
        def some_function():
            # Function that might raise exceptions
            pass
    """
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except TaskmasterError:
            # Re-raise TaskmasterError as-is
            raise
        except Exception as e:
            # Convert other exceptions to TaskmasterError
            logger = logging.getLogger(__name__)
            logger.error(f"Unexpected error in {func.__name__}: {e}")
            raise TaskmasterError(
                message=f"Unexpected error in {func.__name__}: {str(e)}",
                error_code=ErrorCode.INTERNAL_ERROR,
                details={"function": func.__name__},
                cause=e
            )
    
    return wrapper


def safe_execute(func, *args, **kwargs) -> Union[Any, TaskmasterError]:
    """
    Safely execute a function and return either the result or a TaskmasterError.
    
    Args:
        func: The function to execute
        *args: Positional arguments for the function
        **kwargs: Keyword arguments for the function
        
    Returns:
        Either the function result or a TaskmasterError instance
    """
    try:
        return func(*args, **kwargs)
    except TaskmasterError as e:
        return e
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"Unexpected error in safe_execute: {e}")
        return TaskmasterError(
            message=f"Unexpected error: {str(e)}",
            error_code=ErrorCode.INTERNAL_ERROR,
            details={"function": func.__name__ if hasattr(func, '__name__') else str(func)},
            cause=e
        )


class ErrorHandler:
    """
    Centralized error handler for consistent error processing and logging.
    """
    
    def __init__(self, logger_name: str = __name__):
        self.logger = logging.getLogger(logger_name)
    
    def handle_error(
        self,
        error: Exception,
        context: Optional[Dict[str, Any]] = None,
        reraise: bool = True
    ) -> TaskmasterError:
        """
        Handle an error with proper logging and context.
        
        Args:
            error: The error to handle
            context: Additional context information
            reraise: Whether to re-raise the error after handling
            
        Returns:
            TaskmasterError: The processed error
        """
        if isinstance(error, TaskmasterError):
            # Already a TaskmasterError, just add context if provided
            if context:
                error.details.update(context)
            taskmaster_error = error
        else:
            # Convert to TaskmasterError
            taskmaster_error = TaskmasterError(
                message=str(error),
                error_code=ErrorCode.INTERNAL_ERROR,
                details=context or {},
                cause=error
            )
        
        # Log with context
        self.logger.error(
            f"Error handled: {taskmaster_error.error_code.value}",
            extra={
                "error_code": taskmaster_error.error_code.value,
                "message": taskmaster_error.message,
                "details": taskmaster_error.details,
                "context": context
            }
        )
        
        if reraise:
            raise taskmaster_error
        
        return taskmaster_error
    
    def create_error_response(self, error: TaskmasterError) -> Dict[str, Any]:
        """
        Create a standardized error response dictionary.
        
        Args:
            error: The TaskmasterError to convert
            
        Returns:
            Dict containing error response data
        """
        return {
            "status": "error",
            "error": error.to_dict(),
            "completion_guidance": f"Error occurred: {error.message}. Please check the error details and try again."
        }


# Global error handler instance
error_handler = ErrorHandler()


# Convenience functions for common error scenarios
def session_not_found(session_id: str) -> SessionError:
    """Create a session not found error."""
    return SessionError(
        message=f"Session not found: {session_id}",
        session_id=session_id,
        error_code=ErrorCode.SESSION_NOT_FOUND
    )


def task_not_found(task_id: str, session_id: Optional[str] = None) -> TaskError:
    """Create a task not found error."""
    return TaskError(
        message=f"Task not found: {task_id}",
        task_id=task_id,
        session_id=session_id,
        error_code=ErrorCode.TASK_NOT_FOUND
    )


def capabilities_not_declared(session_id: Optional[str] = None) -> CapabilityError:
    """Create a capabilities not declared error."""
    return CapabilityError(
        message="Capabilities must be declared before performing this operation",
        error_code=ErrorCode.CAPABILITIES_NOT_DECLARED,
        details={"session_id": session_id} if session_id else None
    )


def unknown_command(action: str) -> CommandError:
    """Create an unknown command error."""
    return CommandError(
        message=f"Unknown command action: {action}",
        command_action=action,
        error_code=ErrorCode.UNKNOWN_COMMAND
    ) 