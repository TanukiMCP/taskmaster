"""
Pydantic schemas for request/response models in the Taskmaster application.

Provides type-safe data validation, serialization, and clear API contracts
with comprehensive validation rules and error handling.
"""

from typing import Dict, Any, Optional, List, Union
from pydantic import BaseModel, Field, validator, root_validator
from enum import Enum


class ActionType(str, Enum):
    """Enumeration of available action types."""
    CREATE_SESSION = "create_session"
    DECLARE_CAPABILITIES = "declare_capabilities"
    CREATE_TASKLIST = "create_tasklist"
    ADD_TASK = "add_task"
    EDIT_TASK = "edit_task"
    DELETE_TASK = "delete_task"
    EXECUTE_NEXT = "execute_next"
    VALIDATE_TASK = "validate_task"
    VALIDATION_ERROR = "validation_error"
    COLLABORATION_REQUEST = "collaboration_request"
    UPDATE_MEMORY_PALACE = "update_memory_palace"
    MARK_COMPLETE = "mark_complete"
    GET_STATUS = "get_status"


class ValidationResult(str, Enum):
    """Enumeration of validation results."""
    PASSED = "passed"
    FAILED = "failed"
    INCONCLUSIVE = "inconclusive"


class WorkflowState(str, Enum):
    """Enumeration of workflow states."""
    NONE = "none"
    PENDING = "pending"
    PASSED = "passed"
    FAILED = "failed"


# Base schemas
class BaseRequest(BaseModel):
    """Base class for all request models."""
    
    class Config:
        extra = "forbid"  # Prevent unknown fields
        validate_assignment = True


class BaseResponse(BaseModel):
    """Base class for all response models."""
    
    action: str
    session_id: Optional[str] = None
    status: str = "success"
    completion_guidance: str = ""
    next_action_needed: bool = True
    
    class Config:
        extra = "allow"  # Allow additional fields for flexibility


# Capability schemas
class CapabilityDeclaration(BaseModel):
    """Schema for capability declarations."""
    
    name: str = Field(..., min_length=1, description="Name of the capability")
    description: str = Field(..., min_length=1, description="Brief description of the capability")
    what_it_is: str = Field(..., min_length=1, description="What the capability is")
    what_it_does: str = Field(..., min_length=1, description="What the capability does")
    how_to_use: str = Field(..., min_length=1, description="How to use the capability")
    relevant_for: List[str] = Field(..., min_items=1, description="List of relevant use cases")
    
    @validator('relevant_for')
    def validate_relevant_for(cls, v):
        if not v or not all(item.strip() for item in v):
            raise ValueError("relevant_for must contain non-empty strings")
        return v


class BuiltInToolDeclaration(CapabilityDeclaration):
    """Schema for built-in tool declarations."""
    
    always_available: bool = Field(default=True, description="Whether the tool is always available")
    capabilities: List[str] = Field(default_factory=list, description="List of tool capabilities")


class MCPToolDeclaration(CapabilityDeclaration):
    """Schema for MCP tool declarations."""
    
    server_name: str = Field(..., min_length=1, description="Name of the MCP server")


class UserResourceDeclaration(CapabilityDeclaration):
    """Schema for user resource declarations."""
    
    type: str = Field(..., min_length=1, description="Type of resource (documentation, codebase, etc.)")
    indexed_content: Optional[str] = Field(None, description="Indexed content of the resource")
    source_url: Optional[str] = Field(None, description="Source URL of the resource")


# Task schemas
class TaskData(BaseModel):
    """Schema for task data."""
    
    description: str = Field(..., min_length=1, description="Task description")
    validation_required: bool = Field(default=False, description="Whether validation is required")
    validation_criteria: List[str] = Field(default_factory=list, description="Validation criteria")
    
    # MANDATORY capability assignments for each phase
    planning_phase: Dict[str, Any] = Field(..., description="Planning phase with capability assignments")
    execution_phase: Dict[str, Any] = Field(..., description="Execution phase with capability assignments")
    validation_phase: Dict[str, Any] = Field(..., description="Validation phase with capability assignments")
    
    # Memory palace integration
    memory_palace_enabled: bool = Field(default=False, description="Whether to update memory palace after completion")
    
    @validator('planning_phase', 'execution_phase', 'validation_phase')
    def validate_phase_structure(cls, v):
        required_fields = ['description', 'assigned_builtin_tools', 'assigned_mcp_tools', 'assigned_resources', 'requires_tool_usage', 'steps']
        for field in required_fields:
            if field not in v:
                raise ValueError(f"Phase must contain required field: {field}")
        
        # Validate that at least one capability is assigned if requires_tool_usage is True
        if v.get('requires_tool_usage', False):
            has_tools = (
                len(v.get('assigned_builtin_tools', [])) > 0 or
                len(v.get('assigned_mcp_tools', [])) > 0 or
                len(v.get('assigned_resources', [])) > 0
            )
            if not has_tools:
                raise ValueError("Phase marked as requiring tool usage must have at least one capability assigned")
        
        # Validate steps are provided
        if not v.get('steps') or len(v.get('steps', [])) == 0:
            raise ValueError("Phase must contain specific steps")
        
        return v


class TaskUpdateData(BaseModel):
    """Schema for task update data."""
    
    description: Optional[str] = Field(None, min_length=1, description="Updated task description")
    validation_required: Optional[bool] = Field(None, description="Whether validation is required")
    validation_criteria: Optional[List[str]] = Field(None, description="Updated validation criteria")
    status: Optional[str] = Field(None, description="Updated task status")


# Request schemas
class CreateSessionRequest(BaseRequest):
    """Request schema for creating a session."""
    
    action: ActionType = Field(ActionType.CREATE_SESSION, description="Action type")
    session_name: Optional[str] = Field(None, description="Optional session name")


class DeclareCapabilitiesRequest(BaseRequest):
    """Request schema for declaring capabilities."""
    
    action: ActionType = Field(ActionType.DECLARE_CAPABILITIES, description="Action type")
    builtin_tools: List[BuiltInToolDeclaration] = Field(..., min_items=1, description="Built-in tool declarations")
    mcp_tools: List[MCPToolDeclaration] = Field(..., min_items=1, description="MCP tool declarations")
    user_resources: List[UserResourceDeclaration] = Field(..., min_items=1, description="User resource declarations")


class CreateTasklistRequest(BaseRequest):
    """Request schema for creating a tasklist."""
    
    action: ActionType = Field(ActionType.CREATE_TASKLIST, description="Action type")
    tasklist: List[TaskData] = Field(..., min_items=1, description="List of tasks to create")


class AddTaskRequest(BaseRequest):
    """Request schema for adding tasks."""
    
    action: ActionType = Field(ActionType.ADD_TASK, description="Action type")
    task_description: str = Field(..., min_length=1, description="Task description")
    validation_criteria: Optional[List[str]] = Field(None, description="Validation criteria")


class EditTaskRequest(BaseRequest):
    """Request schema for editing tasks."""
    
    action: ActionType = Field(ActionType.EDIT_TASK, description="Action type")
    task_ids: List[str] = Field(..., min_items=1, description="Task IDs to edit")
    updated_task_data: TaskUpdateData = Field(..., description="Updated task data")


class DeleteTaskRequest(BaseRequest):
    """Request schema for deleting tasks."""
    
    action: ActionType = Field(ActionType.DELETE_TASK, description="Action type")
    task_ids: List[str] = Field(..., min_items=1, description="Task IDs to delete")


class ExecuteNextRequest(BaseRequest):
    """Request schema for executing the next task."""
    
    action: ActionType = Field(ActionType.EXECUTE_NEXT, description="Action type")


class ValidateTaskRequest(BaseRequest):
    """Request schema for validating a task."""
    
    action: ActionType = Field(ActionType.VALIDATE_TASK, description="Action type")
    evidence: str = Field(..., min_length=1, description="Evidence for validation")
    validation_result: ValidationResult = Field(..., description="Validation result")
    execution_evidence: Optional[str] = Field(None, description="Execution evidence")


class ValidationErrorRequest(BaseRequest):
    """Request schema for handling validation errors."""
    
    action: ActionType = Field(ActionType.VALIDATION_ERROR, description="Action type")
    error_details: str = Field(..., min_length=1, description="Error details")
    validation_result: ValidationResult = Field(ValidationResult.FAILED, description="Validation result")


class CollaborationRequest(BaseRequest):
    """Request schema for collaboration requests."""
    
    action: ActionType = Field(ActionType.COLLABORATION_REQUEST, description="Action type")
    collaboration_context: str = Field(..., min_length=1, description="Collaboration context")


class UpdateMemoryPalaceRequest(BaseRequest):
    """Request schema for updating memory palace."""
    
    action: ActionType = Field(ActionType.UPDATE_MEMORY_PALACE, description="Action type")
    workspace_path: str = Field(..., min_length=1, description="Memory palace workspace path")
    task_id: str = Field(..., min_length=1, description="Task ID that was completed")
    learnings: List[str] = Field(..., min_items=1, description="Key learnings from task completion")
    what_worked: List[str] = Field(default_factory=list, description="What worked well")
    what_didnt_work: List[str] = Field(default_factory=list, description="What didn't work")
    insights: List[str] = Field(default_factory=list, description="Key insights gained")
    patterns: List[str] = Field(default_factory=list, description="Patterns discovered")
    execution_evidence: Optional[str] = Field(None, description="Evidence of task execution")


class MarkCompleteRequest(BaseRequest):
    """Request schema for marking tasks complete."""
    
    action: ActionType = Field(ActionType.MARK_COMPLETE, description="Action type")
    evidence: Optional[str] = Field(None, description="Evidence for completion")
    execution_evidence: Optional[str] = Field(None, description="Execution evidence")


class GetStatusRequest(BaseRequest):
    """Request schema for getting status."""
    
    action: ActionType = Field(ActionType.GET_STATUS, description="Action type")


# Response schemas
class WorkflowStateInfo(BaseModel):
    """Schema for workflow state information."""
    
    paused: bool = Field(default=False, description="Whether workflow is paused")
    validation_state: WorkflowState = Field(default=WorkflowState.NONE, description="Validation state")
    can_progress: bool = Field(default=True, description="Whether workflow can progress")


class CapabilityInfo(BaseModel):
    """Schema for capability information."""
    
    name: str
    description: str
    what_it_is: str
    what_it_does: str
    how_to_use: str


class MCPToolInfo(CapabilityInfo):
    """Schema for MCP tool information."""
    
    server: str


class UserResourceInfo(CapabilityInfo):
    """Schema for user resource information."""
    
    type: str
    source: Optional[str] = None


class CapabilitiesInfo(BaseModel):
    """Schema for capabilities information."""
    
    builtin_tools: List[CapabilityInfo] = Field(default_factory=list)
    mcp_tools: List[MCPToolInfo] = Field(default_factory=list)
    resources: List[UserResourceInfo] = Field(default_factory=list)


class TaskInfo(BaseModel):
    """Schema for task information."""
    
    id: str
    description: str
    status: str = "[ ]"
    validation_required: bool = False
    validation_criteria: List[str] = Field(default_factory=list)
    subtasks_count: int = 0


class PhaseInfo(BaseModel):
    """Schema for phase information."""
    
    description: str
    assigned_builtin_tools: List[str] = Field(default_factory=list)
    assigned_mcp_tools: List[str] = Field(default_factory=list)
    assigned_resources: List[str] = Field(default_factory=list)
    requires_tool_usage: bool = False
    steps: List[str] = Field(default_factory=list)


class TaskPhaseGuidance(BaseModel):
    """Schema for task phase guidance."""
    
    planning: PhaseInfo
    execution: PhaseInfo
    validation: PhaseInfo


class CreateSessionResponse(BaseResponse):
    """Response schema for session creation."""
    
    action: ActionType = ActionType.CREATE_SESSION
    session_name: Optional[str] = None
    suggested_next_actions: List[str] = Field(default_factory=lambda: ["declare_capabilities"])


class DeclareCapabilitiesResponse(BaseResponse):
    """Response schema for capability declaration."""
    
    action: ActionType = ActionType.DECLARE_CAPABILITIES
    all_capabilities: CapabilitiesInfo = Field(default_factory=CapabilitiesInfo)
    capabilities_declared: Dict[str, int] = Field(default_factory=dict)
    suggested_next_actions: List[str] = Field(default_factory=lambda: ["create_tasklist"])


class CreateTasklistResponse(BaseResponse):
    """Response schema for tasklist creation."""
    
    action: ActionType = ActionType.CREATE_TASKLIST
    tasklist_created: bool = True
    tasks_created: int = 0
    created_tasks: List[TaskInfo] = Field(default_factory=list)
    suggested_next_actions: List[str] = Field(default_factory=lambda: ["execute_next"])


class ExecuteNextResponse(BaseResponse):
    """Response schema for executing next task."""
    
    action: ActionType = ActionType.EXECUTE_NEXT
    current_task: Optional[TaskInfo] = None
    phase_guidance: Optional[TaskPhaseGuidance] = None
    execution_guidance: str = ""
    workflow_state: WorkflowStateInfo = Field(default_factory=WorkflowStateInfo)
    suggested_next_actions: List[str] = Field(default_factory=lambda: ["validate_task"])


class ValidateTaskResponse(BaseResponse):
    """Response schema for task validation."""
    
    action: ActionType = ActionType.VALIDATE_TASK
    current_task: Optional[TaskInfo] = None
    validation_status: ValidationResult = ValidationResult.PASSED
    workflow_state: WorkflowStateInfo = Field(default_factory=WorkflowStateInfo)
    suggested_next_actions: List[str] = Field(default_factory=lambda: ["execute_next"])


class UpdateMemoryPalaceResponse(BaseResponse):
    """Response schema for memory palace updates."""
    
    action: ActionType = ActionType.UPDATE_MEMORY_PALACE
    memory_palace_updated: bool = False
    concepts_added: int = 0
    relationships_created: int = 0
    update_summary: str = ""
    suggested_next_actions: List[str] = Field(default_factory=lambda: ["execute_next"])


class ErrorResponse(BaseResponse):
    """Response schema for errors."""
    
    status: str = "error"
    error: Dict[str, Any] = Field(default_factory=dict)
    error_code: Optional[str] = None
    error_details: Optional[Dict[str, Any]] = None


# Union type for all request types
TaskmasterRequest = Union[
    CreateSessionRequest,
    DeclareCapabilitiesRequest,
    CreateTasklistRequest,
    AddTaskRequest,
    EditTaskRequest,
    DeleteTaskRequest,
    ExecuteNextRequest,
    ValidateTaskRequest,
    ValidationErrorRequest,
    CollaborationRequest,
    UpdateMemoryPalaceRequest,
    MarkCompleteRequest,
    GetStatusRequest
]

# Union type for all response types
TaskmasterResponse = Union[
    CreateSessionResponse,
    DeclareCapabilitiesResponse,
    CreateTasklistResponse,
    ExecuteNextResponse,
    ValidateTaskResponse,
    UpdateMemoryPalaceResponse,
    ErrorResponse,
    BaseResponse
]


# Validation functions
def validate_request(request_data: Dict[str, Any]) -> TaskmasterRequest:
    """
    Validate and parse request data into appropriate request model.
    
    Args:
        request_data: Raw request data
        
    Returns:
        Parsed and validated request model
        
    Raises:
        ValueError: If request data is invalid
    """
    action = request_data.get("action")
    if not action:
        raise ValueError("Action is required")
    
    # Map actions to request models
    request_models = {
        ActionType.CREATE_SESSION: CreateSessionRequest,
        ActionType.DECLARE_CAPABILITIES: DeclareCapabilitiesRequest,
        ActionType.CREATE_TASKLIST: CreateTasklistRequest,
        ActionType.ADD_TASK: AddTaskRequest,
        ActionType.EDIT_TASK: EditTaskRequest,
        ActionType.DELETE_TASK: DeleteTaskRequest,
        ActionType.EXECUTE_NEXT: ExecuteNextRequest,
        ActionType.VALIDATE_TASK: ValidateTaskRequest,
        ActionType.VALIDATION_ERROR: ValidationErrorRequest,
        ActionType.COLLABORATION_REQUEST: CollaborationRequest,
        ActionType.UPDATE_MEMORY_PALACE: UpdateMemoryPalaceRequest,
        ActionType.MARK_COMPLETE: MarkCompleteRequest,
        ActionType.GET_STATUS: GetStatusRequest,
    }
    
    request_model = request_models.get(action)
    if not request_model:
        raise ValueError(f"Unknown action: {action}")
    
    return request_model(**request_data)


def create_error_response(
    action: str,
    error_message: str,
    error_code: Optional[str] = None,
    error_details: Optional[Dict[str, Any]] = None,
    session_id: Optional[str] = None
) -> ErrorResponse:
    """
    Create a standardized error response.
    
    Args:
        action: The action that caused the error
        error_message: Human-readable error message
        error_code: Optional error code
        error_details: Optional error details
        session_id: Optional session ID
        
    Returns:
        ErrorResponse instance
    """
    return ErrorResponse(
        action=action,
        session_id=session_id,
        error={"message": error_message},
        error_code=error_code,
        error_details=error_details,
        completion_guidance=f"Error occurred: {error_message}. Please check the error details and try again."
    ) 