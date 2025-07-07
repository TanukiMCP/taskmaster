from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime

# Forward references - defined at end of file

class CapabilityDeclaration(BaseModel):
 """Simplified capability declaration with just essential fields"""
 name: str
 description: str # Complete description including what it is, does, and how to use it

class BuiltInTool(CapabilityDeclaration):
 """Built-in tools available in the LLM environment"""
 pass

class MCPTool(CapabilityDeclaration):
 """MCP server tools"""
 server_name: str

class MemoryTool(CapabilityDeclaration):
 """Memory and context management tools available to the LLM"""
 type: str # "vector_search", "knowledge_base", "context_window", "retrieval", etc.
 context_scope: str = "session" # "session", "global", "project", "conversation"
 retrieval_method: Optional[str] = None # How the memory tool retrieves information

class ToolAssignment(BaseModel):
 """Rich tool assignment with contextual guidance for the LLM"""
 tool_name: str
 usage_purpose: str # WHY this tool is needed for this specific task phase
 specific_actions: List[str] # HOW the tool should be used (specific steps/commands)
 expected_outcome: str # WHAT the LLM should achieve with this tool
 priority: str = "normal" # "critical", "normal", "optional" - helps LLM prioritize

class TaskPhase(BaseModel):
 """Represents a phase of task execution with assigned capabilities"""
 phase_name: str # "planning", "execution", "validation"
 description: str
 assigned_builtin_tools: List[ToolAssignment] = [] # Rich tool assignments
 assigned_mcp_tools: List[ToolAssignment] = [] # Rich tool assignments 
 assigned_memory_tools: List[ToolAssignment] = [] # Rich memory tool assignments
 assigned_resources: List[ToolAssignment] = [] # Additional resources assigned to this phase
 requires_tool_usage: bool = False # Whether this phase actually needs tools vs atomic thinking
 steps: List[str] = [] # Specific steps for this phase
 phase_guidance: str = "" # Additional contextual guidance for this phase

class SubTask(BaseModel):
 """Individual subtask within a task"""
 id: str = Field(default_factory=lambda: f"subtask_{uuid.uuid4()}")
 description: str
 status: str = "[ ]" # "[ ]" or "[X]"
 planning_phase: Optional[TaskPhase] = None
 execution_phase: Optional[TaskPhase] = None
 execution_evidence: List[str] = []

class InitialToolThoughts(BaseModel):
 """Captures LLM's initial thinking about tools needed during task creation"""
 planning_tools_needed: List[str] = [] # Tools the LLM thinks it might need for planning
 execution_tools_needed: List[str] = [] # Tools the LLM thinks it might need for execution 
 reasoning: str = "" # LLM's reasoning about why these tools are needed

# Enhanced Task model with architectural patterns
class ArchitecturalTaskPhase(TaskPhase):
 """Enhanced TaskPhase with architectural pattern support"""
 world_model_entries: List[str] = [] # References to world model entries for this phase
 hierarchical_plan: Optional["HierarchicalPlan"] = None
 adversarial_review: Optional["AdversarialReview"] = None
 host_grounding: Optional["HostEnvironmentGrounding"] = None
 requires_static_analysis: bool = False
 requires_adversarial_review: bool = False
 verification_agents: List[str] = [] # Which agents should verify this phase

class Task(BaseModel):
 id: str = Field(default_factory=lambda: f"task_{uuid.uuid4()}")
 description: str
 status: str = "pending" # "pending", "completed"
 subtasks: List[SubTask] = []
 
 # Enhanced: Initial tool thinking during task creation
 initial_tool_thoughts: Optional[InitialToolThoughts] = None
 
 # Phase tracking
 current_phase: Optional[str] = None  # "planning", "execution", "completed"
 
 # Enhanced phases with architectural pattern support (STREAMLINED - NO VALIDATION)
 planning_phase: Optional["ArchitecturalTaskPhase"] = None
 execution_phase: Optional["ArchitecturalTaskPhase"] = None
 
 # Architectural pattern tracking
 requires_world_model: bool = False
 requires_hierarchical_planning: bool = False
 requires_adversarial_review: bool = False
 complexity_level: str = "simple" # "simple", "complex", "architectural"
 
 # Adversarial review tracking
 adversarial_review: Optional["AdversarialReview"] = None
 
 # STREAMLINED WORKFLOW - NO VALIDATION FIELDS
 
 evidence: List[dict] = []
 execution_started: bool = False
 execution_evidence: List[str] = []
 suggested_builtin_tools: List[str] = []
 suggested_mcp_tools: List[str] = []
 suggested_memory_tools: List[str] = []
 suggested_resources: List[str] = []  # Additional resources suggested for this task
 
 # STREAMLINED WORKFLOW - NO VALIDATION ERRORS TRACKING

class EnvironmentCapabilities(BaseModel):
 built_in_tools: List[BuiltInTool] = []
 mcp_tools: List[MCPTool] = []
 memory_tools: List[MemoryTool] = []

class Session(BaseModel):
 id: str = Field(default_factory=lambda: f"session_{uuid.uuid4()}")
 name: str
 created_at: datetime = Field(default_factory=datetime.now)
 tasks: List[Task] = []
 
 # Enhanced capabilities tracking with rich context
 capabilities: EnvironmentCapabilities = Field(default_factory=EnvironmentCapabilities)
 
 # World model for advanced architectural patterns
 world_model_enabled: bool = False
 world_model_config: Optional[Dict[str, Any]] = None
 world_model: Optional["WorldModel"] = None
 
 # Hierarchical planning for complex tasks
 hierarchical_plan: Optional["HierarchicalPlan"] = None
 
 # Architectural mode flag
 architectural_mode: bool = False

class Config:
 """Pydantic model configuration."""
 from pydantic import Extra
 extra = Extra.allow # Allow extra fields for flexibility
 json_encoders = {
 datetime: lambda v: v.isoformat(),
 }

# Advanced Architectural Pattern Models

class WorldModelEntry(BaseModel):
 """Represents an entry in the Dynamic World Model"""
 timestamp: str = Field(default_factory=lambda: "2025-01-27T00:00:00Z")
 entry_type: str # "static_analysis", "tool_output", "error", "state_update", "verification"
 source: str # Which tool/agent generated this entry
 content: str # The actual information
 file_path: Optional[str] = None # For file-related entries
 verification_status: str = "unverified" # "unverified", "verified", "failed"
 criticality: str = "normal" # "critical", "normal", "low"

class DynamicWorldModel(BaseModel):
 """Maintains live, state-aware context throughout task execution"""
 entries: List[WorldModelEntry] = []
 static_analysis_complete: bool = False
 current_state_summary: str = ""
 critical_files: List[str] = []
 critical_functions: List[str] = []
 known_errors: List[str] = []
 verified_outputs: List[str] = []

class AdversarialReview(BaseModel):
 """Tracks the adversarial review loop for generated code/solutions"""
 generation_phase: str = "pending" # "pending", "generated", "reviewed", "tested", "approved"
 generated_content: str = ""
 generator_agent: str = "" # Which agent generated the content
 review_findings: List[Dict[str, str]] = [] # Findings from code reviewer with structured format
 test_results: List[str] = [] # Results from tester
 correction_cycles: int = 0
 max_correction_cycles: int = 3
 approved: bool = False

class HostEnvironmentGrounding(BaseModel):
 """Tracks real-world execution results to prevent hallucination"""
 command_history: List[Dict[str, Any]] = [] # All executed commands with real results
 last_stdout: str = ""
 last_stderr: str = ""
 last_exit_code: int = 0
 execution_context: Dict[str, Any] = {} # Current working directory, env vars, etc.
 reality_check_required: bool = False

# Define the forward-referenced models
class WorldModel(BaseModel):
    """Dynamic world model for maintaining context during task execution"""
    entries: List[WorldModelEntry] = []
    static_analysis_complete: bool = False
    current_state_summary: str = ""
    critical_files: List[str] = []
    critical_functions: List[str] = []
    known_errors: List[str] = []
    verified_outputs: List[str] = []
    
class HierarchicalPlan(BaseModel):
    """Hierarchical plan for complex multi-step tasks"""
    steps: List[Dict[str, Any]] = []
    current_step_index: int = 0
    total_steps: int = 0
