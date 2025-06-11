from pydantic import BaseModel, Field
from typing import List, Optional, Dict
import uuid

class BuiltInTool(BaseModel):
    name: str
    description: str
    always_available: bool = True
    capabilities: List[str] = []
    relevant_for: List[str] = []

class MCPTool(BaseModel):
    name: str
    description: str
    server_name: str
    capabilities: List[str] = []
    relevant_for: List[str] = []

class UserResource(BaseModel):
    name: str
    type: str  # "documentation", "codebase", "api", "knowledge_base", etc.
    description: str
    indexed_content: Optional[str] = None
    source_url: Optional[str] = None
    relevant_for: List[str] = []

class EnvironmentCapabilities(BaseModel):
    built_in_tools: List[BuiltInTool] = []
    mcp_tools: List[MCPTool] = []
    user_resources: List[UserResource] = []

class Task(BaseModel):
    id: str = Field(default_factory=lambda: f"task_{uuid.uuid4()}")
    description: str
    status: str = "[ ]" # Enforce "[ ]" or "[X]"
    # Fields for Phase 2
    validation_required: bool = False
    validation_criteria: List[str] = []
    evidence: List[dict] = []
    # Execution tracking
    execution_started: bool = False
    execution_evidence: List[str] = []
    # Tool and resource suggestions
    suggested_builtin_tools: List[str] = []
    suggested_mcp_tools: List[str] = []
    suggested_resources: List[str] = []

class Session(BaseModel):
    id: str = Field(default_factory=lambda: f"session_{uuid.uuid4()}")
    session_name: Optional[str] = None
    tasks: List[Task] = []
    # Environment capabilities (LLM-declared)
    capabilities: EnvironmentCapabilities = Field(default_factory=EnvironmentCapabilities)
    # Environment context
    environment_context: Optional[Dict] = None 