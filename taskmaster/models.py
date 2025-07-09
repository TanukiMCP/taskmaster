from __future__ import annotations
import uuid
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class SubTask(BaseModel):
    description: str
    completed: bool = False


class ToolAssignment(BaseModel):
    tool_name: str
    usage_purpose: str
    specific_actions: List[str] = []
    expected_outcome: str = ""
    priority: str = "normal"


class ArchitecturalTaskPhase(BaseModel):
    """Represents a phase within a task (e.g., planning, execution) with architectural pattern support."""
    phase_name: str
    description: str
    assigned_builtin_tools: List[ToolAssignment] = []
    assigned_mcp_tools: List[ToolAssignment] = []


class InitialToolThoughts(BaseModel):
    reasoning: str
    planning_tools_needed: List[str] = []
    execution_tools_needed: List[str] = []


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
 

class BuiltInTool(BaseModel):
    name: str
    description: str


class MCPTool(BaseModel):
    name: str
    description: str
    server_name: str


class MemoryTool(BaseModel):
    name: str
    description: str


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

    class Config:
        arbitrary_types_allowed = True
