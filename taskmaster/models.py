from __future__ import annotations
import uuid
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from .workflow_state_machine import WorkflowState
from datetime import datetime


class SubTask(BaseModel):
    id: str = Field(default_factory=lambda: f"subtask_{uuid.uuid4()}")
    description: str
    status: str = "pending"

class ToolAssignment(BaseModel):
    tool_name: str
    usage_purpose: str
    specific_actions: List[str] = []
    expected_outcome: str = ""
    priority: str = "normal"

class ArchitecturalTaskPhase(BaseModel):
    phase_name: str
    description: str
    assigned_builtin_tools: List[ToolAssignment] = []
    assigned_mcp_tools: List[ToolAssignment] = []
    assigned_memory_tools: List[ToolAssignment] = []
    assigned_resources: List[ToolAssignment] = []

class InitialToolThoughts(BaseModel):
    reasoning: str
    thought_process: List[str] = []


class BuiltInTool(BaseModel):
    name: str
    description: str


class MCPTool(BaseModel):
    name: str
    server_name: str = "unknown"  # Make optional with default value
    description: str


class MemoryTool(BaseModel):
    name: str
    type: str = "resource"
    description: str


class Task(BaseModel):
    id: str = Field(default_factory=lambda: f"task_{uuid.uuid4()}")
    description: str
    status: str = "pending"  # "pending", "completed"
    current_phase: Optional[str] = "planning"
    complexity_level: str = "simple"
    initial_tool_thoughts: Optional[InitialToolThoughts] = None
    planning_phase: Optional[ArchitecturalTaskPhase] = None
    execution_phase: Optional[ArchitecturalTaskPhase] = None
    subtasks: List[SubTask] = []


class EnvironmentCapabilities(BaseModel):
    built_in_tools: List[BuiltInTool] = []
    mcp_tools: List[MCPTool] = []
    user_resources: List[MemoryTool] = [] # Re-using MemoryTool for generic resources


class Session(BaseModel):
    id: str = Field(default_factory=lambda: f"session_{uuid.uuid4()}")
    name: Optional[str] = "Default Session"
    task_description: Optional[str] = None
    tasks: List[Task] = []
    capabilities: EnvironmentCapabilities = Field(default_factory=EnvironmentCapabilities)
    data: Dict[str, Any] = Field(default_factory=dict) # For storing arbitrary data like six_hats
    workflow_state: str = Field(default=WorkflowState.SESSION_CREATED.value)

    class Config:
        arbitrary_types_allowed = True


class TaskmasterData(BaseModel):
    sessions: List[Session] = []
