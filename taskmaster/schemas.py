"""
Flexible schemas for LLM guidance in the Taskmaster application.

Provides intelligent guidance and suggestions rather than rigid validation,
allowing LLMs to work effectively with the framework while receiving helpful feedback.
"""

from typing import Dict, Any, Optional, List, Union
from enum import Enum


class ActionType(str, Enum):
    """Enumeration of available action types - simplified."""
    CREATE_SESSION = "create_session"
    CREATE_TASKLIST = "create_tasklist"
    EXECUTE_NEXT = "execute_next"
    MARK_COMPLETE = "mark_complete"
    GET_STATUS = "get_status"
    END_SESSION = "end_session"


class ValidationResult(str, Enum):
    """Enumeration of validation results."""
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


class WorkflowState(str, Enum):
    """Enumeration of workflow states."""
    NONE = "none"
    VALIDATION_PENDING = "validation_pending"
    VALIDATION_FAILED = "validation_failed"
    COLLABORATION_REQUESTED = "collaboration_requested"
    PAUSED = "paused"


def create_flexible_request(data: Dict[str, Any]) -> Dict[str, Any]:
    """Create an optimized flexible request - simplified."""
    # Fast path for valid requests
    if "action" in data and data["action"] in [
        "create_session", "create_tasklist", "execute_next", 
        "mark_complete", "end_session", "get_status"
    ]:
        # Optimized defaults for common actions
        if data["action"] == "create_tasklist":
            data.setdefault("tasklist", [])
        
        return data
    
    # Fallback for unknown actions
    if "action" not in data:
        data["action"] = "get_status"
        data["_guidance"] = ["⚠️ No action specified, defaulting to 'get_status'"]
    
    return data


def create_flexible_response(action: str, **kwargs) -> Dict[str, Any]:
    """
    Create a flexible response structure with intelligent guidance.
    """
    response = {
        "action": action,
        "session_id": kwargs.get("session_id"),
        "status": kwargs.get("status", "success"),
        "completion_guidance": kwargs.get("completion_guidance", ""),
        "next_action_needed": kwargs.get("next_action_needed", True),
        "workflow_state": kwargs.get("workflow_state", {
            "paused": False,
            "validation_state": "none",
            "can_progress": True
        })
    }
    
    # Add any additional fields
    for key, value in kwargs.items():
        if key not in response:
            response[key] = value
    
    return response


def enhance_task_data(task_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enhance task data with helpful defaults and guidance - simplified.
    """
    enhanced = task_data.copy()
    guidance = []
    
    # Ensure description exists
    if "description" not in enhanced or not enhanced["description"]:
        enhanced["description"] = "Task description needed"
        guidance.append("💡 Consider providing a clear task description")
    
    if guidance:
        enhanced["_guidance"] = guidance
    
    return enhanced


# Legacy compatibility - these classes are kept for backward compatibility
# but they now use flexible validation that provides guidance instead of blocking

class BaseRequest:
    """Base class for request compatibility."""
    def __init__(self, **data):
        self.__dict__.update(create_flexible_request(data))


class BaseResponse:
    """Base class for response compatibility."""
    def __init__(self, action: str, **kwargs):
        self.__dict__.update(create_flexible_response(action, **kwargs))
    
    def dict(self) -> Dict[str, Any]:
        return self.__dict__.copy()


# Validation functions - now provide guidance instead of blocking
def validate_request(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """Validate and enhance request data with guidance instead of blocking."""
    return create_flexible_request(request_data)


def validate_tasklist(tasklist: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Validate and enhance tasklist with guidance instead of blocking validation.
    """
    return [enhance_task_data(task) for task in tasklist]


# Helper functions for common patterns
def extract_guidance(data: Dict[str, Any]) -> List[str]:
    """Extract guidance messages from data structure."""
    guidance = []
    
    if "_guidance" in data:
        guidance.extend(data["_guidance"])
    
    # Look for guidance in nested structures
    for key, value in data.items():
        if isinstance(value, dict) and "_guidance" in value:
            guidance.extend(value["_guidance"])
        elif isinstance(value, list):
            for item in value:
                if isinstance(item, dict) and "_guidance" in item:
                    guidance.extend(item["_guidance"])
    
    return guidance


def clean_guidance(data: Dict[str, Any]) -> Dict[str, Any]:
    """Remove guidance markers from data structure for clean output."""
    if isinstance(data, dict):
        cleaned = {}
        for key, value in data.items():
            if key != "_guidance":
                cleaned[key] = clean_guidance(value)
        return cleaned
    elif isinstance(data, list):
        return [clean_guidance(item) for item in data]
    else:
        return data 