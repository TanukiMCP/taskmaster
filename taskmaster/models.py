from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
import uuid

class CapabilityDeclaration(BaseModel):
    """Simplified capability declaration with just essential fields"""
    name: str
    description: str  # Complete description including what it is, does, and how to use it

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

class ToolAssignment(BaseModel):
    """Rich tool assignment with contextual guidance for the LLM"""
    tool_name: str
    usage_purpose: str  # WHY this tool is needed for this specific task phase
    specific_actions: List[str]  # HOW the tool should be used (specific steps/commands)
    expected_outcome: str  # WHAT the LLM should achieve with this tool
    priority: str = "normal"  # "critical", "normal", "optional" - helps LLM prioritize

class TaskPhase(BaseModel):
    """Represents a phase of task execution with assigned capabilities"""
    phase_name: str  # "planning", "execution", "validation"
    description: str
    assigned_builtin_tools: List[ToolAssignment] = []  # Rich tool assignments
    assigned_mcp_tools: List[ToolAssignment] = []      # Rich tool assignments  
    assigned_resources: List[ToolAssignment] = []      # Rich tool assignments
    requires_tool_usage: bool = False  # Whether this phase actually needs tools vs atomic thinking
    steps: List[str] = []  # Specific steps for this phase
    phase_guidance: str = ""  # Additional contextual guidance for this phase

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

class InitialToolThoughts(BaseModel):
    """Captures LLM's initial thinking about tools needed during task creation"""
    planning_tools_needed: List[str] = []  # Tools the LLM thinks it might need for planning
    execution_tools_needed: List[str] = []  # Tools the LLM thinks it might need for execution  
    validation_tools_needed: List[str] = []  # Tools the LLM thinks it might need for validation
    reasoning: str = ""  # LLM's reasoning about why these tools are needed

# Enhanced Task model with architectural patterns
class ArchitecturalTaskPhase(TaskPhase):
    """Enhanced TaskPhase with architectural pattern support"""
    world_model_entries: List[str] = []  # References to world model entries for this phase
    hierarchical_plan: Optional["HierarchicalPlan"] = None
    adversarial_review: Optional["AdversarialReview"] = None
    host_grounding: Optional["HostEnvironmentGrounding"] = None
    requires_static_analysis: bool = False
    requires_adversarial_review: bool = False
    verification_agents: List[str] = []  # Which agents should verify this phase

class Task(BaseModel):
    id: str = Field(default_factory=lambda: f"task_{uuid.uuid4()}")
    description: str
    status: str = "pending"  # "pending", "completed"
    subtasks: List[SubTask] = []
    
    # Enhanced: Initial tool thinking during task creation
    initial_tool_thoughts: Optional[InitialToolThoughts] = None
    
    # Phase tracking
    current_phase: Optional[str] = None  # "planning", "execution", "validation", "completed"
    
    # Enhanced phases with architectural pattern support
    planning_phase: Optional["ArchitecturalTaskPhase"] = None
    execution_phase: Optional["ArchitecturalTaskPhase"] = None
    validation_phase: Optional["ArchitecturalTaskPhase"] = None
    
    # Architectural pattern tracking
    requires_world_model: bool = False
    requires_hierarchical_planning: bool = False
    requires_adversarial_review: bool = False
    complexity_level: str = "simple"  # "simple", "complex", "architectural"
    
    # Re-introducing validation fields
    validation_required: bool = False
    validation_criteria: List[str] = Field(default_factory=list)
    
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
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    session_name: Optional[str] = None
    status: str = "active"  # "active", "ended"
    created_at: str = Field(default_factory=lambda: "2025-01-27T00:00:00Z")  # Would use actual timestamp
    ended_at: Optional[str] = None  # When the session was ended
    tasks: List[Task] = []
    capabilities: EnvironmentCapabilities = Field(default_factory=EnvironmentCapabilities)
    environment_map: Optional[Dict[str, Any]] = None
    
    # Advanced Architectural Patterns
    world_model: "DynamicWorldModel" = Field(default_factory=lambda: DynamicWorldModel())
    current_hierarchical_plan: Optional["HierarchicalPlan"] = None
    architectural_mode: bool = False  # Whether to enforce architectural patterns
    
    # Environment context
    environment_context: Dict = Field(default_factory=dict)

# Advanced Architectural Pattern Models

class WorldModelEntry(BaseModel):
    """Represents an entry in the Dynamic World Model"""
    timestamp: str = Field(default_factory=lambda: "2025-01-27T00:00:00Z")
    entry_type: str  # "static_analysis", "tool_output", "error", "state_update", "verification"
    source: str  # Which tool/agent generated this entry
    content: str  # The actual information
    file_path: Optional[str] = None  # For file-related entries
    verification_status: str = "unverified"  # "unverified", "verified", "failed"
    criticality: str = "normal"  # "critical", "normal", "low"

class DynamicWorldModel(BaseModel):
    """Maintains live, state-aware context throughout task execution"""
    entries: List[WorldModelEntry] = []
    static_analysis_complete: bool = False
    current_state_summary: str = ""
    critical_files: List[str] = []
    critical_functions: List[str] = []
    known_errors: List[str] = []
    verified_outputs: List[str] = []

class HierarchicalPlan(BaseModel):
    """Represents a hierarchical plan with high-level strategy and sub-tasks"""
    high_level_steps: List[str] = []  # Strategic plan from planner-critic
    current_step_index: int = 0
    current_step_breakdown: List[str] = []  # Low-level sub-tasks for current step
    current_subtask_index: int = 0
    step_completion_criteria: List[str] = []
    verification_required: bool = True

class AdversarialReview(BaseModel):
    """Tracks the adversarial review loop for generated code/solutions"""
    generation_phase: str = "pending"  # "pending", "generated", "reviewed", "tested", "approved"
    generated_content: str = ""
    generator_agent: str = ""  # Which agent generated the content
    review_findings: List[str] = []  # Findings from code reviewer
    test_results: List[str] = []  # Results from tester
    correction_cycles: int = 0
    max_correction_cycles: int = 3
    approved: bool = False

class HostEnvironmentGrounding(BaseModel):
    """Tracks real-world execution results to prevent hallucination"""
    command_history: List[Dict[str, Any]] = []  # All executed commands with real results
    last_stdout: str = ""
    last_stderr: str = ""
    last_exit_code: int = 0
    execution_context: Dict[str, Any] = {}  # Current working directory, env vars, etc.
    reality_check_required: bool = False
