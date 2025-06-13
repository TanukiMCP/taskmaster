from pydantic import BaseModel, Field
from typing import List, Optional, Dict
import uuid

class CapabilityDeclaration(BaseModel):
    """Enhanced capability declaration with self-description and usage context"""
    name: str
    description: str
    what_it_is: str  # Brief description of what the tool/resource is
    what_it_does: str  # What the tool/resource does
    how_to_use: str  # EXACTLY how it could be used within task context
    always_available: bool = True
    capabilities: List[str] = []
    relevant_for: List[str] = []

class BuiltInTool(CapabilityDeclaration):
    """Built-in tools available in the LLM environment"""
    pass

class MCPTool(CapabilityDeclaration):
    """MCP server tools"""
    server_name: str

class UserResource(CapabilityDeclaration):
    """User-provided resources like documentation, codebases, APIs"""
    type: str  # "documentation", "codebase", "api", "knowledge_base", etc.
    indexed_content: Optional[str] = None
    source_url: Optional[str] = None

class TaskPhase(BaseModel):
    """Represents a phase of task execution with assigned capabilities"""
    phase_name: str  # "planning", "execution", "validation"
    description: str
    assigned_builtin_tools: List[str] = []
    assigned_mcp_tools: List[str] = []
    assigned_resources: List[str] = []
    requires_tool_usage: bool = False  # Whether this phase actually needs tools vs atomic thinking
    steps: List[str] = []  # Specific steps for this phase

class SubTask(BaseModel):
    """Individual subtask within a task"""
    id: str = Field(default_factory=lambda: f"subtask_{uuid.uuid4()}")
    description: str
    status: str = "[ ]"  # "[ ]" or "[X]"
    planning_phase: Optional[TaskPhase] = None
    execution_phase: Optional[TaskPhase] = None
    validation_phase: Optional[TaskPhase] = None
    execution_evidence: List[str] = []
    validation_evidence: List[str] = []

class Task(BaseModel):
    id: str = Field(default_factory=lambda: f"task_{uuid.uuid4()}")
    description: str
    status: str = "[ ]"  # "[ ]" or "[X]"
    subtasks: List[SubTask] = []
    
    # Overall task phases (for tasks without subtasks)
    planning_phase: Optional[TaskPhase] = None
    execution_phase: Optional[TaskPhase] = None
    validation_phase: Optional[TaskPhase] = None
    
    # Legacy fields for backward compatibility
    validation_required: bool = False
    validation_criteria: List[str] = []
    evidence: List[dict] = []
    execution_started: bool = False
    execution_evidence: List[str] = []
    suggested_builtin_tools: List[str] = []
    suggested_mcp_tools: List[str] = []
    suggested_resources: List[str] = []
    
    # Enhanced workflow fields
    validation_errors: List[dict] = []  # Track validation errors and retry attempts

class EnvironmentCapabilities(BaseModel):
    built_in_tools: List[BuiltInTool] = []
    mcp_tools: List[MCPTool] = []
    user_resources: List[UserResource] = []

class Session(BaseModel):
    id: str = Field(default_factory=lambda: f"session_{uuid.uuid4()}")
    session_name: Optional[str] = None
    tasks: List[Task] = []
    # Environment capabilities (LLM-declared with enhanced descriptions)
    capabilities: EnvironmentCapabilities = Field(default_factory=EnvironmentCapabilities)
    # Environment context
    environment_context: Optional[Dict] = None 