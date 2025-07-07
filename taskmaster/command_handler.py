from typing import Dict, Any, Optional, List
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from .models import Session, Task, BuiltInTool, MCPTool, MemoryTool, EnvironmentCapabilities, TaskPhase, InitialToolThoughts, ToolAssignment
from .session_manager import SessionManager
from .validation_engine import ValidationEngine
from .schemas import (
    ActionType, ValidationResult, WorkflowState,
    create_flexible_request, create_flexible_response,
    enhance_capability_data, enhance_task_data,
    validate_capabilities, validate_tasklist,
    extract_guidance, clean_guidance
)

logger = logging.getLogger(__name__)


class TaskmasterCommand:
    """Represents a command to be executed by the TaskmasterCommandHandler."""
    
    def __init__(self, **kwargs):
        if "data" in kwargs:
            # Merge data with top-level kwargs, with top-level taking precedence
            merged_data = kwargs["data"].copy()
            merged_data.update({k: v for k, v in kwargs.items() if k != "data"})
            self.data = create_flexible_request(merged_data)
        else:
            # Use flexible approach - accept any data and provide guidance
            self.data = create_flexible_request(kwargs)
        
        # Extract common fields with defaults
        self.action = self.data.get("action", "get_status")
        self.task_description = self.data.get("task_description")
        self.session_name = self.data.get("session_name")
        self.validation_criteria = self.data.get("validation_criteria", [])
        self.evidence = self.data.get("evidence")
        self.execution_evidence = self.data.get("execution_evidence")
        self.builtin_tools = self.data.get("builtin_tools", [])
        self.mcp_tools = self.data.get("mcp_tools", [])
        self.user_resources = self.data.get("user_resources", [])
        self.memory_tools = self.data.get("memory_tools", [])
        self.tasklist = self.data.get("tasklist", [])
        self.task_ids = self.data.get("task_ids", [])
        self.updated_task_data = self.data.get("updated_task_data", {})
        self.next_action_needed = self.data.get("next_action_needed", True)
        self.validation_result = self.data.get("validation_result")
        self.error_details = self.data.get("error_details")
        self.collaboration_context = self.data.get("collaboration_context")
        self.user_response = self.data.get("user_response")
        
        # Memory palace integration fields
        self.on_topic = self.data.get("on_topic")
        self.workspace_path = self.data.get("workspace_path")
        self.task_id = self.data.get("task_id")
        self.learnings = self.data.get("learnings", [])
        self.what_worked = self.data.get("what_worked", [])
        self.what_didnt_work = self.data.get("what_didnt_work", [])
        self.insights = self.data.get("insights", [])
        self.patterns = self.data.get("patterns", [])
        
        # Extract any guidance messages
        self.guidance = extract_guidance(self.data)


class TaskmasterResponse:
    """Represents a response from the TaskmasterCommandHandler."""
    
    def __init__(self, action: str, **kwargs):
        self.data = create_flexible_response(action, **kwargs)
        
        # Extract common fields
        self.action = self.data["action"]
        self.session_id = self.data.get("session_id")
        self.status = self.data.get("status", "success")
        self.current_task = self.data.get("current_task")
        self.relevant_capabilities = self.data.get("relevant_capabilities", {"builtin_tools": [], "mcp_tools": [], "resources": []})
        self.all_capabilities = self.data.get("all_capabilities", {"builtin_tools": [], "mcp_tools": [], "resources": []})
        self.suggested_next_actions = self.data.get("suggested_next_actions", [])
        self.completion_guidance = self.data.get("completion_guidance", "")
        self.workflow_state = self.data.get("workflow_state", {
            "paused": False,
            "validation_state": "none",
            "can_progress": True
        })
        
        # Store additional response data
        for key, value in kwargs.items():
            if not hasattr(self, key):
                setattr(self, key, value)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert response to dictionary format."""
        return clean_guidance(self.data)


class BaseCommandHandler(ABC):
    """Base class for command handlers."""
    
    def __init__(self, session_manager: SessionManager, validation_engine: ValidationEngine):
        self.session_manager = session_manager
        self.validation_engine = validation_engine
    
    @abstractmethod
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        """Handle the command and return a response."""
        pass
    
    def _provide_capability_guidance(self, cap_list: List[Dict[str, Any]], category_name: str) -> List[str]:
        """Provide guidance for capability format instead of blocking validation."""
        guidance = []
        
        if not isinstance(cap_list, list):
            guidance.append(f"💡 {category_name} should be a list of capability objects")
            return guidance
        
        for i, cap in enumerate(cap_list):
            if not isinstance(cap, dict):
                guidance.append(f"💡 {category_name}[{i}] should be a dictionary with capability details")
                continue
            
            # Provide helpful suggestions for the simplified structure
            if "name" not in cap or not cap["name"]:
                guidance.append(f"💡 {category_name}[{i}] needs a descriptive name")
            if "description" not in cap or not cap["description"]:
                guidance.append(f"💡 {category_name}[{i}] needs a complete description (what it is, does, and how to use it)")
        
        return guidance


class CreateSessionHandler(BaseCommandHandler):
    """Handler for create_session command."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.create_session(command.session_name)
        
        # Try to detect available MCP tools from the environment
        detected_mcp_tools = self._detect_available_mcp_tools()
        
        guidance = f"""
🚀 Session created! NEXT STEP: Use 'declare_capabilities' action.

💡 GUIDANCE: Declare your available tools and resources:
- builtin_tools: Your core environment tools (file operations, search, etc.)
- mcp_tools: Available MCP server tools  
- user_resources: Available docs, codebases, APIs

Each capability needs: name and a complete description (what it is, does, and how to use it)

🔍 **MCP TOOL DISCOVERY HELP:**
{detected_mcp_tools}

After declaring capabilities, you'll create tasks and then map which tools to use for each task phase.
"""
        
        return TaskmasterResponse(
            action="create_session",
            session_id=session.id,
            session_name=getattr(session, 'session_name', None),
            suggested_next_actions=["declare_capabilities"],
            completion_guidance=guidance,
            detected_mcp_tools=detected_mcp_tools
        )
    
    def _detect_available_mcp_tools(self) -> str:
        """Attempt to detect available MCP tools from the environment."""
        try:
            import inspect
            import sys
            
            # Get the current frame and look for MCP tool functions
            current_frame = inspect.currentframe()
            if current_frame and current_frame.f_back and current_frame.f_back.f_back:
                caller_globals = current_frame.f_back.f_back.f_globals
                
                # Look for MCP tool functions (functions that start with mcp_)
                mcp_functions = []
                for name, obj in caller_globals.items():
                    if (callable(obj) and 
                        hasattr(obj, '__name__') and 
                        obj.__name__.startswith('mcp_')):
                        mcp_functions.append(obj.__name__)
                
                if mcp_functions:
                    tools_list = '\n'.join([f"- {tool}" for tool in mcp_functions])
                    return f"""
Detected potential MCP tools in your environment:
{tools_list}

💡 **IMPORTANT**: You should declare these MCP tools in your `declare_capabilities` call.
Example format:
```
mcp_tools: [
  {{
    "name": "tool_name",
    "description": "Complete description of what this tool does",
    "server_name": "mcp_server_name"
  }}
]
```
"""
                else:
                    return """
No MCP tools automatically detected. If you have MCP tools available, make sure to:
1. Check what MCP tools are available in your environment
2. Manually declare them in the `declare_capabilities` action
3. Include name, description, and server_name for each MCP tool
"""
            
        except Exception as e:
            return f"""
Could not auto-detect MCP tools (this is normal). 
Manual declaration required in `declare_capabilities`:
- List all MCP tools you have access to
- Include name, description, and server_name for each
- Common MCP tools: memory_palace, sequential_thinking, context7, etc.
"""
        
        return """
Please manually declare any MCP tools you have access to in the `declare_capabilities` action.
Include name, description, and server_name for each MCP tool.
"""


class DeclareCapabilitiesHandler(BaseCommandHandler):
    """Handler for declare_capabilities command."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            session = await self.session_manager.create_session()
        
        # Enhance capabilities with helpful defaults instead of blocking
        enhanced_builtin = validate_capabilities(command.builtin_tools, "builtin_tools")
        enhanced_mcp = validate_capabilities(command.mcp_tools, "mcp_tools")
        enhanced_resources = validate_capabilities(command.user_resources, "user_resources")
        enhanced_memory_tools = validate_capabilities(command.memory_tools, "memory_tools")
        
        # Collect guidance instead of errors
        guidance_messages = []
        guidance_messages.extend(self._provide_capability_guidance(command.builtin_tools, "builtin_tools"))
        guidance_messages.extend(self._provide_capability_guidance(command.mcp_tools, "mcp_tools"))
        guidance_messages.extend(self._provide_capability_guidance(command.user_resources, "user_resources"))
        guidance_messages.extend(self._provide_capability_guidance(command.memory_tools, "memory_tools"))
        
        # Check for missing MCP tools and provide specific guidance
        if not enhanced_mcp:
            mcp_detection_help = self._provide_mcp_detection_guidance()
            guidance_messages.append(f"🔍 **MCP TOOLS MISSING**: {mcp_detection_help}")
        
        # Always proceed - provide guidance but don't block
        if not enhanced_builtin and not enhanced_mcp and not enhanced_resources and not enhanced_memory_tools:
            guidance_messages.append("💡 Consider declaring at least one capability category for better task guidance")
        
        # Store capabilities in session using the correct model structure
        session.capabilities.built_in_tools = [BuiltInTool(**tool) for tool in enhanced_builtin]
        session.capabilities.mcp_tools = [MCPTool(**tool) for tool in enhanced_mcp]
        session.capabilities.memory_tools = [MemoryTool(**memory_tool) for memory_tool in enhanced_memory_tools]
        
        await self.session_manager.update_session(session)
        
        guidance = f"""
✅ Capabilities declared! NEXT STEP: Use 'create_tasklist' action.

📊 **DECLARED CAPABILITIES SUMMARY:**
- Built-in Tools: {len(session.capabilities.built_in_tools)}
- MCP Tools: {len(session.capabilities.mcp_tools)}
- Memory Tools: {len(session.capabilities.memory_tools)}

💡 GUIDANCE: Create a comprehensive tasklist with:
- Clear task descriptions
- Logical task breakdown
- Phase structure (planning, execution, validation phases)

After creating your tasklist, you'll use 'map_capabilities' to assign specific tools to each task phase.
"""
        
        if guidance_messages:
            guidance += "\n\n🔍 CAPABILITY GUIDANCE:\n" + "\n".join(guidance_messages)
        
        return TaskmasterResponse(
            action="declare_capabilities",
            session_id=session.id,
            all_capabilities={
                "builtin_tools": [tool.dict() for tool in session.capabilities.built_in_tools],
                "mcp_tools": [tool.dict() for tool in session.capabilities.mcp_tools],
                "memory_tools": [memory_tool.dict() for memory_tool in session.capabilities.memory_tools]
            },
            capabilities_declared={
                "builtin_tools": len(session.capabilities.built_in_tools),
                "mcp_tools": len(session.capabilities.mcp_tools),
                "memory_tools": len(session.capabilities.memory_tools)
            },
            suggested_next_actions=["create_tasklist"],
            completion_guidance=guidance
        )
    
    def _provide_mcp_detection_guidance(self) -> str:
        """Provide specific guidance for detecting and declaring MCP tools."""
        return """
No MCP tools were declared. If you have MCP tools available, you should declare them!

🔍 **HOW TO FIND YOUR MCP TOOLS:**
1. Check your Cursor/IDE settings for installed MCP servers
2. Look for tools with names like: mcp_*, *_mcp, or server-specific prefixes
3. Common MCP tools include:
   - Memory Palace tools (mcp_memory_palace_*)
   - Sequential Thinking (mcp_server-sequential-thinking_*)
   - Context7 documentation tools (mcp_context7-mcp_*)
   - File system tools (mcp_filesystem_*)
   - Database tools (mcp_sqlite_*, mcp_postgres_*)

📝 **EXAMPLE MCP TOOL DECLARATION:**
```
mcp_tools: [
  {
    "name": "memory_palace_query",
    "description": "Query the memory palace for stored knowledge and context",
    "server_name": "mcp_memory_palace"
  },
  {
    "name": "sequential_thinking", 
    "description": "Advanced problem-solving with structured thinking steps",
    "server_name": "mcp_server-sequential-thinking"
  }
]
```

💡 **TIP**: Re-run `declare_capabilities` with your MCP tools included for better task execution!
"""



    
    def _provide_enhanced_tasklist_guidelines(self, session) -> TaskmasterResponse:
        """Provide comprehensive LLM guidelines for tasklist creation."""
        
        # Check what capabilities are available to inform guidance
        has_capabilities = (session.capabilities.built_in_tools or 
                          session.capabilities.mcp_tools or 
                          session.capabilities.memory_tools)
        
        # Analyze memory tools for memory gate guidance
        memory_tools_analysis = self._analyze_memory_tools(session.capabilities.memory_tools)
        
        capabilities_context = ""
        if has_capabilities:
            capabilities_context = f"""
🛠️ YOUR AVAILABLE CAPABILITIES:
Built-in Tools: {len(session.capabilities.built_in_tools)}
MCP Tools: {len(session.capabilities.mcp_tools)}  
Memory Tools: {len(session.capabilities.memory_tools)}
{memory_tools_analysis['summary'] if memory_tools_analysis else ''}
"""
        else:
            capabilities_context = "⚠️ No capabilities declared yet - consider declaring them first for better task planning."
        
        guidance = f"""
📋 **ENHANCED TASKLIST CREATION GUIDELINES**

{capabilities_context}

🎯 **MANDATORY TASK STRUCTURE**
Every task MUST follow the plan→execute→scan→review→validate cycle:

**Required Format:**
```json
{{
  "tasklist": [
    {{
      "description": "Clear, specific task description",
      "initial_tool_thoughts": {{
        "planning_tools_needed": ["tool1", "tool2"],
        "execution_tools_needed": ["tool3", "tool4"],
        "validation_tools_needed": ["tool1"],
        "reasoning": "Why these tools are needed for this specific task"
      }},
      "planning_phase": {{
        "description": "What planning is needed for this task",
        "steps": ["Analyze requirements", "Create execution plan", "Identify risks"],
        "phase_guidance": "Specific planning approach for this task"
      }},
      "execution_phase": {{
        "description": "How this task will be executed",
        "steps": ["Step 1", "Step 2", "Step 3"],
        "phase_guidance": "Key execution considerations",
        "requires_adversarial_review": true
      }},
      "validation_phase": {{
        "description": "How to validate task completion",
        "steps": ["Check output quality", "Verify requirements met", "Test functionality"],
        "phase_guidance": "Validation criteria and success metrics"
      }}
    }}
  ]
}}
```

🚨 **ANTI-HALLUCINATION REQUIREMENTS**
1. **Specific Descriptions**: No vague tasks like "implement feature" - be specific
2. **Tool Thinking**: Always include initial_tool_thoughts with reasoning
3. **Phase Details**: Each phase must have clear steps and guidance
4. **Validation Criteria**: Specify exactly how completion will be verified

🧠 **MEMORY GATE PATTERNS** (Apply if memory tools available)
{memory_tools_analysis.get('gate_patterns', '') if memory_tools_analysis else ''}

🔄 **COMPLEXITY ASSESSMENT**
- **Simple**: Single-step tasks, no code generation
- **Complex**: Multi-step tasks, code generation, file modifications
- **Architectural**: System-wide changes, multiple components

💡 **BEST PRACTICES**
- Break large tasks into smaller, focused tasks
- Include error handling and rollback considerations
- Specify exact validation criteria (console output, file existence, etc.)
- Consider dependencies between tasks
- Use memory gates to build and maintain mental models throughout execution

Create your tasklist following this structure for optimal LLM guidance and execution tracking.
"""
        
        return TaskmasterResponse(
            action="create_tasklist",
            session_id=session.id,
            tasklist_created=False,
            guidelines_provided=True,
            suggested_next_actions=["create_tasklist"],
            completion_guidance=guidance
        )
    
    def _validate_and_enhance_tasklist(self, raw_tasklist):
        """Validate tasklist structure and enhance with defaults."""
        enhanced_tasks = []
        validation_issues = []
        
        for i, task in enumerate(raw_tasklist):
            if not isinstance(task, dict):
                validation_issues.append(f"Task {i+1}: Must be a dictionary")
                continue
            
            # Validate required description
            if not task.get("description"):
                validation_issues.append(f"Task {i+1}: Missing description")
                task["description"] = f"Task {i+1} - Please provide description"
            
            # Ensure all phases exist with defaults
            if not task.get("planning_phase"):
                task["planning_phase"] = {
                    "description": f"Plan the execution of: {task.get('description', 'this task')}",
                    "steps": ["Analyze requirements", "Create execution plan"],
                    "phase_guidance": "Focus on understanding requirements and planning approach"
                }
                validation_issues.append(f"Task {i+1}: Added default planning phase")
            
            if not task.get("execution_phase"):
                task["execution_phase"] = {
                    "description": f"Execute: {task.get('description', 'this task')}",
                    "steps": ["Follow execution plan", "Implement solution"],
                    "phase_guidance": "Focus on careful implementation and testing"
                }
                validation_issues.append(f"Task {i+1}: Added default execution phase")
            
            # Validation phase is now optional - only add if explicitly requested
            if not task.get("validation_phase"):
                task["validation_phase"] = None  # Make it optional
                validation_issues.append(f"Task {i+1}: Validation phase not specified (optional in streamlined flow)")
            
            # Add initial tool thoughts if missing
            if not task.get("initial_tool_thoughts"):
                task["initial_tool_thoughts"] = {
                    "planning_tools_needed": [],
                    "execution_tools_needed": [],
                    "validation_tools_needed": [],
                    "reasoning": "No initial tool thoughts provided - consider which tools you'll need"
                }
                validation_issues.append(f"Task {i+1}: Added default tool thoughts")
            
            enhanced_tasks.append(task)
        
        return enhanced_tasks, validation_issues
    
    def _create_phase(self, phase_name, phase_data):
        """Create an ArchitecturalTaskPhase with defaults."""
        from .models import ArchitecturalTaskPhase
        
        defaults = {
            "phase_name": phase_name,
            "description": phase_data.get("description", f"{phase_name.title()} phase"),
            "steps": phase_data.get("steps", []),
            "phase_guidance": phase_data.get("phase_guidance", ""),
            "requires_adversarial_review": phase_data.get("requires_adversarial_review", phase_name == "execution")
        }
        
        return ArchitecturalTaskPhase(**defaults)
    
    def _assess_task_complexity(self, task_data):
        """Assess task complexity based on description and structure."""
        description = task_data.get("description", "").lower()
        
        # Architectural complexity indicators
        if any(word in description for word in ["system", "architecture", "framework", "multiple", "integration"]):
            return "architectural"
        
        # Complex task indicators
        if any(word in description for word in ["implement", "create", "build", "develop", "code", "file", "database"]):
            return "complex"
        
        # Default to simple
        return "simple"
    
    def _build_tasklist_completion_guidance(self, tasks, validation_issues):
        """Build comprehensive guidance for tasklist completion."""
        
        # Analyze task composition
        complexity_counts = {}
        for task in tasks:
            complexity_counts[task.complexity_level] = complexity_counts.get(task.complexity_level, 0) + 1
        
        adversarial_tasks = len([t for t in tasks if t.requires_adversarial_review])
        
        guidance = f"""
**STREAMLINED TASKLIST CREATED** - {len(tasks)} tasks with enhanced structure

**TASK ANALYSIS:**
- Simple tasks: {complexity_counts.get('simple', 0)}
- Complex tasks: {complexity_counts.get('complex', 0)}
- Architectural tasks: {complexity_counts.get('architectural', 0)}
- Requiring adversarial review: {adversarial_tasks}

**STREAMLINED WORKFLOW:**
Each task will follow: PLAN -> EXECUTE -> COMPLETE
- Planning: Analyze requirements and create execution plan with placeholder guidance.
- Execution: Implement with tool guidance and enhanced placeholder guardrails.
- Completion: Direct completion with evidence collection.

**PLACEHOLDER GUARDRAILS:**
- Context-aware guidance prevents lazy implementations.
- Task complexity determines appropriate placeholder usage.
- Clear guidelines for when placeholders are acceptable vs discouraged.
- Reality checking against actual execution results.
"""
        
        if validation_issues:
            guidance += f"""
**VALIDATION ISSUES RESOLVED:**
{chr(10).join([f"- {issue}" for issue in validation_issues[:5]])}
{"- ... and more" if len(validation_issues) > 5 else ""}
"""
        
        guidance += """
**NEXT STEP:** Use 'map_capabilities' to assign your declared tools to specific task phases.

This streamlined structure ensures efficient task execution with enhanced placeholder guardrails.
"""
        
        return guidance
    
    def _analyze_memory_tools(self, memory_tools):
        """Analyze available memory tools and generate memory gate patterns."""
        if not memory_tools:
            return None
        
        # Categorize memory tools by type
        crud_tools = []
        retrieval_tools = []
        context_tools = []
        
        for tool in memory_tools:
            tool_type = tool.type.lower()
            if any(crud_op in tool.name.lower() for crud_op in ['add', 'create', 'update', 'delete', 'store']):
                crud_tools.append(tool)
            elif any(retr_op in tool.name.lower() for retr_op in ['search', 'query', 'retrieve', 'recall', 'find']):
                retrieval_tools.append(tool)
            elif any(ctx_op in tool.name.lower() for ctx_op in ['context', 'window', 'scope']):
                context_tools.append(tool)
            else:
                # Default categorization based on type
                if 'database' in tool_type or 'storage' in tool_type:
                    crud_tools.append(tool)
                elif 'search' in tool_type or 'retrieval' in tool_type:
                    retrieval_tools.append(tool)
                else:
                    context_tools.append(tool)
        
        # Generate memory gate patterns
        gate_patterns = self._generate_memory_gate_patterns(crud_tools, retrieval_tools, context_tools)
        
        # Create summary
        summary = f"""
🧠 **MEMORY TOOLS DETECTED:**
- CRUD Operations: {len(crud_tools)} tools (store/update memories)
- Retrieval Operations: {len(retrieval_tools)} tools (access existing memories)  
- Context Management: {len(context_tools)} tools (manage memory scope)
"""
        
        return {
            'summary': summary,
            'gate_patterns': gate_patterns,
            'crud_tools': crud_tools,
            'retrieval_tools': retrieval_tools,
            'context_tools': context_tools
        }
    
    def _generate_memory_gate_patterns(self, crud_tools, retrieval_tools, context_tools):
        """Generate specific memory gate patterns based on available tools."""
        patterns = []
        
        if retrieval_tools and crud_tools:
            retrieval_names = [tool.name for tool in retrieval_tools]
            crud_names = [tool.name for tool in crud_tools]
            patterns.append(f"""
**MEMORY REFLECT → EXECUTE → MEMORY UPDATE PATTERN:**
1. **Start with Memory Retrieval** (Planning Phase):
   - Use your retrieval tools ({', '.join(retrieval_names)}) at task beginning
   - Access existing knowledge about the domain/codebase
   - Build initial mental model from stored memories
   
2. **Execute with Context** (Execution Phase):
   - Apply retrieved knowledge during task execution
   - Note new information discovered during execution
   - Track differences from existing mental model
   
3. **Update Mental Model** (Validation Phase):
   - Use your storage/update tools ({', '.join(crud_names)}) to store new learnings
   - Record insights, patterns, or changes discovered
   - Maintain cumulative knowledge for future tasks""")
        
        if retrieval_tools:
            retrieval_names = [tool.name for tool in retrieval_tools]
            patterns.append(f"""
**MEMORY-GUIDED EXECUTION:**
- Begin each task with memory retrieval ({', '.join(retrieval_names)}) to access relevant context
- Use your retrieval tools to avoid repeating previous mistakes
- Leverage stored patterns and solutions from past experiences""")
        
        if crud_tools:
            crud_names = [tool.name for tool in crud_tools]
            patterns.append(f"""
**PROGRESSIVE LEARNING:**
- Store new insights immediately when discovered using ({', '.join(crud_names)})
- Update existing memories when information changes
- Build cumulative knowledge base across task execution""")
        
        if context_tools:
            patterns.append("""
**CONTEXT SCOPING:**
- Manage memory scope (session vs global vs project)
- Maintain appropriate context boundaries
- Preserve relevant context across task transitions""")
        
        if not patterns:
            patterns.append("""
**BASIC MEMORY INTEGRATION:**
- Integrate memory tools into planning and validation phases
- Use memory capabilities to enhance task execution context
- Build mental models appropriate to your memory tool capabilities""")
        
        return '\n'.join(patterns)


class MapCapabilitiesHandler(BaseCommandHandler):
    """Handler for map_capabilities command - ensures LLM assigns tools to task phases with rich context."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(
                action="map_capabilities",
                status="guidance",
                completion_guidance="🔍 GUIDANCE: No active session found. Please create a session first using 'create_session'.",
                suggested_next_actions=["create_session"]
            )
        
        if not session.tasks:
            return TaskmasterResponse(
                action="map_capabilities",
                status="guidance",
                completion_guidance="🔍 GUIDANCE: No tasks found. Please create a tasklist first using 'create_tasklist'.",
                suggested_next_actions=["create_tasklist"]
            )
        
        if not (session.capabilities.built_in_tools or session.capabilities.mcp_tools or session.capabilities.memory_tools):
            return TaskmasterResponse(
                action="map_capabilities",
                status="guidance",
                completion_guidance="🔍 GUIDANCE: No capabilities declared. Please declare capabilities first using 'declare_capabilities'.",
                suggested_next_actions=["declare_capabilities"]
            )
        
        # Process capability mappings from the command
        task_mappings = command.data.get("task_mappings", [])
        
        if not task_mappings:
            # Provide comprehensive guidance on the enhanced mapping structure
            available_tools = {
                "builtin_tools": [(tool.name, tool.description) for tool in session.capabilities.built_in_tools],
                "mcp_tools": [(tool.name, tool.description) for tool in session.capabilities.mcp_tools],
                "memory_tools": [(memory_tool.name, memory_tool.description) for memory_tool in session.capabilities.memory_tools]
            }
            
            # Show initial tool thoughts if available
            initial_thoughts_display = ""
            for task in session.tasks:
                if task.initial_tool_thoughts:
                    initial_thoughts_display += f"""
📋 TASK: {task.description} (ID: {task.id})
   Initial Thoughts: {task.initial_tool_thoughts.reasoning}
   - Planning tools considered: {', '.join(task.initial_tool_thoughts.planning_tools_needed)}
   - Execution tools considered: {', '.join(task.initial_tool_thoughts.execution_tools_needed)}
   - Validation tools considered: {', '.join(task.initial_tool_thoughts.validation_tools_needed)}
"""
            
            guidance = f"""
🗺️ ENHANCED CAPABILITY MAPPING REQUIRED

You need to assign your available tools to specific phases of each task with RICH CONTEXT. This ensures you get detailed, actionable guidance during execution.

{initial_thoughts_display if initial_thoughts_display else '📋 YOUR TASKS:' + chr(10) + chr(10).join([f"- {task.description} (ID: {task.id})" for task in session.tasks])}

🛠️ YOUR AVAILABLE TOOLS:

📋 **BUILT-IN TOOLS:**
{chr(10).join([f"- {name}: {desc}" for name, desc in available_tools['builtin_tools']]) if available_tools['builtin_tools'] else '- No built-in tools declared'}

🔌 **MCP TOOLS:**
{chr(10).join([f"- {name}: {desc}" for name, desc in available_tools['mcp_tools']]) if available_tools['mcp_tools'] else '- No MCP tools declared'}

🧠 **MEMORY TOOLS:** {'⚠️ IMPORTANT: Memory tools provide cumulative learning and context!' if available_tools['memory_tools'] else ''}
{chr(10).join([f"- {name}: {desc}" for name, desc in available_tools['memory_tools']]) if available_tools['memory_tools'] else '- No memory tools declared'}

🧠 **MEMORY GATE PATTERNS** (Use if memory tools available):
{self._generate_memory_mapping_guidance(session.capabilities.memory_tools)}

💡 PROVIDE ENHANCED MAPPING LIKE THIS:
Call taskmaster again with task_mappings parameter containing:
[
  {{
    "task_id": "{session.tasks[0].id if session.tasks else 'task_id'}",
    "planning_phase": {{
      "description": "Task-specific planning phase description",
      "phase_guidance": "Additional context for this planning phase",
      "assigned_builtin_tools": [
        {{
          "tool_name": "tool1",
          "usage_purpose": "Why this tool is needed for planning this specific task",
          "specific_actions": ["Specific step 1", "Specific step 2"],
          "expected_outcome": "What you expect to achieve with this tool",
          "priority": "critical"  // critical, normal, or optional
        }}
      ],
      "assigned_mcp_tools": [...],
      "assigned_memory_tools": [
        {{
          "tool_name": "memory_query_tool",
          "usage_purpose": "Retrieve relevant context and past learnings for this task",
          "specific_actions": ["Query for similar past tasks", "Get domain knowledge", "Find relevant patterns"],
          "expected_outcome": "Contextual information to inform planning decisions",
          "priority": "normal"
        }}
      ],
      "assigned_resources": [...]
    }},
    "execution_phase": {{
      "description": "Task-specific execution phase description", 
      "phase_guidance": "Key execution guidance for this task",
      "assigned_builtin_tools": [...],
      "assigned_mcp_tools": [...],
      "assigned_memory_tools": [
        {{
          "tool_name": "memory_update_tool",
          "usage_purpose": "Store insights and learnings discovered during execution",
          "specific_actions": ["Record new patterns found", "Store successful approaches", "Note what worked/didn't work"],
          "expected_outcome": "Cumulative learning for future tasks",
          "priority": "normal"
        }}
      ],
      "assigned_resources": [...]
    }},
    "validation_phase": {{
      "description": "How to validate this specific task",
      "phase_guidance": "Validation approach for this task",
      "assigned_builtin_tools": [...],
      "assigned_mcp_tools": [...],
      "assigned_memory_tools": [
        {{
          "tool_name": "memory_consolidate_tool",
          "usage_purpose": "Consolidate task learnings and strengthen successful patterns",
          "specific_actions": ["Reinforce successful approaches", "Weaken failed patterns", "Build task relationships"],
          "expected_outcome": "Enhanced memory model for future task execution",
          "priority": "normal"
        }}
      ],
      "assigned_resources": [...]
    }}
  }}
]

🎯 GOALS:
1. Every available tool should be assigned where it makes sense
2. Each tool assignment must include WHY, HOW, and EXPECTED OUTCOME
3. Provide task-specific phase descriptions and guidance
4. Set appropriate priority levels (critical/normal/optional)

This rich context will provide you with detailed, actionable guidance during task execution.
"""
            
            return TaskmasterResponse(
                action="map_capabilities",
                session_id=session.id,
                available_capabilities=available_tools,
                tasks_to_map=[{
                    "id": task.id,
                    "description": task.description,
                    "initial_tool_thoughts": task.initial_tool_thoughts.dict() if task.initial_tool_thoughts else None
                } for task in session.tasks],
                suggested_next_actions=["map_capabilities"],
                completion_guidance=guidance
            )
        
        # Apply the enhanced mappings to tasks
        mapped_count = 0
        validation_errors = []
        
        for mapping in task_mappings:
            task_id = mapping.get("task_id")
            task = next((t for t in session.tasks if t.id == task_id), None)
            
            if not task:
                validation_errors.append(f"Task {task_id} not found")
                continue
                
            # Update task phases with enhanced capability assignments
            if mapping.get("planning_phase"):
                phase_data = mapping["planning_phase"]
                if not task.planning_phase:
                    from .models import ArchitecturalTaskPhase
                    task.planning_phase = ArchitecturalTaskPhase(
                        phase_name="planning",
                        description=phase_data.get("description", "Planning phase")
                    )
                
                # Update phase-level context
                task.planning_phase.description = phase_data.get("description", task.planning_phase.description)
                task.planning_phase.phase_guidance = phase_data.get("phase_guidance", "")
                
                # Process enhanced tool assignments
                task.planning_phase.assigned_builtin_tools = [
                    ToolAssignment(**tool_data) for tool_data in phase_data.get("assigned_builtin_tools", [])
                ]
                task.planning_phase.assigned_mcp_tools = [
                    ToolAssignment(**tool_data) for tool_data in phase_data.get("assigned_mcp_tools", [])
                ]
                task.planning_phase.assigned_memory_tools = [
                    ToolAssignment(**tool_data) for tool_data in phase_data.get("assigned_memory_tools", [])
                ]
                task.planning_phase.assigned_resources = [
                    ToolAssignment(**tool_data) for tool_data in phase_data.get("assigned_resources", [])
                ]
            
            if mapping.get("execution_phase"):
                phase_data = mapping["execution_phase"]
                if not task.execution_phase:
                    from .models import ArchitecturalTaskPhase
                    task.execution_phase = ArchitecturalTaskPhase(
                        phase_name="execution",
                        description=phase_data.get("description", "Execution phase")
                    )
                
                # Update phase-level context
                task.execution_phase.description = phase_data.get("description", task.execution_phase.description)
                task.execution_phase.phase_guidance = phase_data.get("phase_guidance", "")
                
                # Process enhanced tool assignments
                task.execution_phase.assigned_builtin_tools = [
                    ToolAssignment(**tool_data) for tool_data in phase_data.get("assigned_builtin_tools", [])
                ]
                task.execution_phase.assigned_mcp_tools = [
                    ToolAssignment(**tool_data) for tool_data in phase_data.get("assigned_mcp_tools", [])
                ]
                task.execution_phase.assigned_memory_tools = [
                    ToolAssignment(**tool_data) for tool_data in phase_data.get("assigned_memory_tools", [])
                ]
                task.execution_phase.assigned_resources = [
                    ToolAssignment(**tool_data) for tool_data in phase_data.get("assigned_resources", [])
                ]
                
            if mapping.get("validation_phase"):
                phase_data = mapping["validation_phase"]
                if not task.validation_phase:
                    from .models import ArchitecturalTaskPhase
                    task.validation_phase = ArchitecturalTaskPhase(
                        phase_name="validation",
                        description=phase_data.get("description", "Validation phase")
                    )
                
                # Update phase-level context
                task.validation_phase.description = phase_data.get("description", task.validation_phase.description)
                task.validation_phase.phase_guidance = phase_data.get("phase_guidance", "")
                
                # Process enhanced tool assignments
                task.validation_phase.assigned_builtin_tools = [
                    ToolAssignment(**tool_data) for tool_data in phase_data.get("assigned_builtin_tools", [])
                ]
                task.validation_phase.assigned_mcp_tools = [
                    ToolAssignment(**tool_data) for tool_data in phase_data.get("assigned_mcp_tools", [])
                ]
                task.validation_phase.assigned_memory_tools = [
                    ToolAssignment(**tool_data) for tool_data in phase_data.get("assigned_memory_tools", [])
                ]
                task.validation_phase.assigned_resources = [
                    ToolAssignment(**tool_data) for tool_data in phase_data.get("assigned_resources", [])
                ]
            
            mapped_count += 1
        
        await self.session_manager.update_session(session)
        
        if validation_errors:
            guidance = f"""
⚠️ Capability mapping completed with warnings: {mapped_count} tasks mapped.

🚨 VALIDATION WARNINGS:
{chr(10).join([f"- {error}" for error in validation_errors])}

🎯 NEXT STEP: Use 'execute_next' to begin task execution with your enhanced mapped capabilities.

Your tasks now have detailed tool assignments with rich context for intelligent execution guidance.
"""
        else:
            guidance = f"""
✅ Enhanced capability mapping completed! {mapped_count} tasks mapped with rich context.

🎯 NEXT STEP: Use 'execute_next' to begin task execution with your enhanced mapped capabilities.

Your tasks now have detailed tool assignments including:
- WHY each tool is needed (usage_purpose)
- HOW to use each tool (specific_actions)  
- WHAT to expect (expected_outcome)
- Priority levels for intelligent tool selection

This rich context will provide you with detailed, actionable guidance during task execution.
"""
        
        return TaskmasterResponse(
            action="map_capabilities",
            session_id=session.id,
            mapping_completed=True,
            tasks_mapped=mapped_count,
            validation_errors=validation_errors,
            suggested_next_actions=["execute_next"],
            completion_guidance=guidance
        )
    
    def _generate_memory_mapping_guidance(self, memory_tools):
        """Generate specific guidance for memory tool mapping based on available tools."""
        if not memory_tools:
            return "No memory tools available - consider declaring memory tools for enhanced context and learning."
        
        # Categorize memory tools by type for better guidance
        retrieval_tools = []
        storage_tools = []
        consolidation_tools = []
        
        for tool in memory_tools:
            tool_name_lower = tool.name.lower()
            tool_desc_lower = tool.description.lower()
            
            if any(keyword in tool_name_lower or keyword in tool_desc_lower 
                   for keyword in ['query', 'search', 'retrieve', 'recall', 'find', 'get']):
                retrieval_tools.append(tool)
            elif any(keyword in tool_name_lower or keyword in tool_desc_lower 
                     for keyword in ['update', 'store', 'save', 'add', 'create', 'record']):
                storage_tools.append(tool)
            elif any(keyword in tool_name_lower or keyword in tool_desc_lower 
                     for keyword in ['consolidate', 'reinforce', 'strengthen', 'weaken', 'reflect']):
                consolidation_tools.append(tool)
            else:
                # Default categorization
                retrieval_tools.append(tool)
        
        guidance_parts = []
        
        if retrieval_tools:
            tool_names = [tool.name for tool in retrieval_tools]
            guidance_parts.append(f"""
**MEMORY RETRIEVAL PATTERN** (Planning Phase Priority):
- Use retrieval tools ({', '.join(tool_names)}) at the START of tasks
- Query for: similar past tasks, domain knowledge, successful patterns
- Purpose: Build context and avoid repeating mistakes
- Example: "Retrieve any past experience with theme styling and UI consistency"
""")
        
        if storage_tools:
            tool_names = [tool.name for tool in storage_tools]
            guidance_parts.append(f"""
**MEMORY STORAGE PATTERN** (Execution Phase):
- Use storage tools ({', '.join(tool_names)}) DURING execution
- Store: new insights, successful approaches, what worked/didn't work
- Purpose: Capture learnings for future reference
- Example: "Store insight that Material-UI theme integration requires specific color token patterns"
""")
        
        if consolidation_tools:
            tool_names = [tool.name for tool in consolidation_tools]
            guidance_parts.append(f"""
**MEMORY CONSOLIDATION PATTERN** (Validation Phase):
- Use consolidation tools ({', '.join(tool_names)}) AFTER task completion
- Consolidate: reinforce successful patterns, weaken failed approaches
- Purpose: Strengthen memory model for future tasks
- Example: "Reinforce the pattern that grep searches provide effective completion evidence"
""")
        
        if not guidance_parts:
            guidance_parts.append(f"""
**BASIC MEMORY INTEGRATION:**
Available tools: {', '.join([tool.name for tool in memory_tools])}
- Integrate memory tools into all phases for enhanced context
- Use for storing and retrieving task-relevant information
- Build cumulative knowledge across task execution
""")
        
        return '\n'.join(guidance_parts) 


class ExecuteNextHandler(BaseCommandHandler):
    """Handler for execute_next command with integrated plan→execute→scan→review→validate cycle."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(
                action="execute_next",
                status="guidance",
                completion_guidance="🔍 GUIDANCE: No active session found. Please create a session first using 'create_session'.",
                suggested_next_actions=["create_session"]
            )
        
        if not session.tasks:
            return TaskmasterResponse(
                action="execute_next",
                status="guidance",
                completion_guidance="🔍 GUIDANCE: No tasks found. Please create a tasklist first using 'create_tasklist'.",
                suggested_next_actions=["create_tasklist"]
            )
            
        # Find the next pending task
        next_task = next((task for task in session.tasks if task.status == "pending"), None)
        
        if not next_task:
            return TaskmasterResponse(
                action="execute_next",
                status="completed",
                completion_guidance="🎉 All tasks completed! Great work! You can create a new session or add more tasks if needed.",
                suggested_next_actions=["create_session", "end_session"]
            )
        
        # Determine current phase and provide enhanced guidance
        current_phase = self._determine_current_phase(next_task)
        phase_obj = getattr(next_task, f"{current_phase}_phase", None)
        
        # Enhanced phase execution with mandatory cycle
        if current_phase == "execution" and next_task.requires_adversarial_review:
            return await self._handle_execution_with_adversarial_review(next_task, phase_obj, session)
        
        # Standard phase execution
        return await self._handle_standard_phase_execution(next_task, current_phase, phase_obj, session)
    
    async def _handle_execution_with_adversarial_review(self, task, phase_obj, session):
        """Handle execution phase with mandatory adversarial review cycle."""
        
        # Check if adversarial review is already initiated
        if not hasattr(task, 'adversarial_review') or not task.adversarial_review:
            # Initialize adversarial review for complex/architectural tasks
            guidance = await self._initiate_adversarial_review_guidance(task, phase_obj)
            return TaskmasterResponse(
                action="execute_next",
                session_id=session.id,
                current_task_id=task.id,
                current_task_description=task.description,
                current_phase="execution",
                adversarial_review_required=True,
                suggested_next_actions=["initiate_adversarial_review"],
                completion_guidance=guidance
            )
        
        # Continue with standard execution if review is already in progress
        return await self._handle_standard_phase_execution(task, "execution", phase_obj, session)
    
    async def _initiate_adversarial_review_guidance(self, task, phase_obj):
        """Provide guidance for initiating adversarial review."""
        
        tool_guidance = self._build_tool_guidance(phase_obj) if phase_obj else "No specific tools assigned."
        
        return f"""
🚀 **EXECUTION PHASE WITH ADVERSARIAL REVIEW**
Task: {task.description}

🔄 **MANDATORY CYCLE: PLAN → EXECUTE → SCAN → REVIEW → VALIDATE**

{f"📋 EXECUTION PLAN: {phase_obj.description}" if phase_obj else ""}
{f"🎯 GUIDANCE: {phase_obj.phase_guidance}" if phase_obj and phase_obj.phase_guidance else ""}

{tool_guidance}

🧠 **ADVERSARIAL REVIEW PROCESS:**
1. **Generate**: Implement your solution using the tools above
2. **Review**: Get 3 critical improvement suggestions  
3. **Test**: Verify functionality and catch bugs
4. **Iterate**: Apply improvements (max 3 cycles)
5. **Validate**: Confirm completion with evidence

🚨 **ANTI-HALLUCINATION REQUIREMENTS:**
- Record actual console output from tool usage
- Capture real file changes and results
- No completion claims without evidence
- Reality check all outputs

💡 **NEXT STEP:** Use 'initiate_adversarial_review' to begin the review cycle.

Task ID: {task.id}
Complexity: {task.complexity_level}
"""
    
    async def _handle_standard_phase_execution(self, task, current_phase, phase_obj, session):
        """Handle standard phase execution with rich guidance."""
        
        if not phase_obj:
            # No phase defined - provide basic guidance
            guidance = f"""
🚀 EXECUTE TASK: {task.description}

⚠️ No {current_phase} phase defined for this task. Proceeding with basic guidance.

💡 SUGGESTED APPROACH:
1. Analyze the task requirements
2. Use available tools as needed
3. Complete the task objectives
4. Use 'mark_complete' when finished

Current Task ID: {task.id}
"""
            return TaskmasterResponse(
                action="execute_next",
                session_id=session.id,
                current_task_id=task.id,
                current_task_description=task.description,
                current_phase=current_phase,
                suggested_next_actions=["mark_complete"],
                completion_guidance=guidance
            )
        
        # Build enhanced guidance based on phase type
        if current_phase == "planning":
            guidance = self._build_planning_guidance(task, phase_obj)
        elif current_phase == "execution":
            guidance = self._build_execution_guidance(task, phase_obj)
        else:
            guidance = self._build_generic_guidance(task, phase_obj, current_phase)
        
        return TaskmasterResponse(
            action="execute_next",
            session_id=session.id,
            current_task_id=task.id,
            current_task_description=task.description,
            current_phase=current_phase,
            suggested_next_actions=["mark_complete"],
            completion_guidance=guidance
        )
    
    def _build_planning_guidance(self, task, phase_obj):
        """Build guidance for planning phase."""
        tool_guidance = self._build_tool_guidance(phase_obj)
        
        return f"""
🧠 **PLANNING PHASE**
Task: {task.description}

📋 **PLANNING OBJECTIVE:** {phase_obj.description}
{f"🎯 GUIDANCE: {phase_obj.phase_guidance}" if phase_obj.phase_guidance else ""}

{tool_guidance}

📝 **PLANNING STEPS:**
{chr(10).join([f"{i+1}. {step}" for i, step in enumerate(phase_obj.steps)]) if phase_obj.steps else "1. Analyze requirements\n2. Create execution plan\n3. Identify potential issues"}

🎯 **PLANNING CHECKLIST:**
- [ ] Understand all requirements clearly
- [ ] Identify necessary tools and resources
- [ ] Plan step-by-step execution approach
- [ ] Consider potential challenges and solutions
- [ ] Define success criteria for validation

💡 **COMPLETION CRITERIA:**
You should have a clear, actionable plan before moving to execution.
Use 'mark_complete' when planning is thorough and ready for execution.

Task ID: {task.id} | Phase: Planning | Complexity: {task.complexity_level}
"""
    
    def _build_execution_guidance(self, task, phase_obj):
        """Build guidance for execution phase with enhanced placeholder guidance."""
        tool_guidance = self._build_tool_guidance(phase_obj)
        placeholder_guidance = self._build_placeholder_guidance(task)
        
        execution_requirements = ""
        if task.requires_adversarial_review:
            execution_requirements = """
🔄 **ADVERSARIAL REVIEW REQUIRED**
This task requires adversarial review due to its complexity.
After implementation, you'll need to get critical feedback and iterate.
"""
        
        return f"""
⚡ **EXECUTION PHASE**
Task: {task.description}

📋 **EXECUTION OBJECTIVE:** {phase_obj.description}
{f"🎯 GUIDANCE: {phase_obj.phase_guidance}" if phase_obj.phase_guidance else ""}

{execution_requirements}

{tool_guidance}

{placeholder_guidance}

🔨 **EXECUTION STEPS:**
{chr(10).join([f"{i+1}. {step}" for i, step in enumerate(phase_obj.steps)]) if phase_obj.steps else "1. Follow your planning\n2. Implement solution\n3. Test as you go"}

🚨 **EXECUTION REQUIREMENTS:**
- [ ] Follow the planned approach
- [ ] Use assigned tools effectively
- [ ] Record actual outputs and results
- [ ] Test functionality as you implement
- [ ] Document any issues or deviations

💡 **EVIDENCE COLLECTION:**
- Save console outputs from tool usage
- Record file changes and results
- Note any errors or unexpected behavior
- Capture proof of functionality

Use 'mark_complete' when implementation is finished and tested.

Task ID: {task.id} | Phase: Execution | Complexity: {task.complexity_level}
"""
    

    
    def _build_generic_guidance(self, task, phase_obj, current_phase):
        """Build guidance for any other phase."""
        tool_guidance = self._build_tool_guidance(phase_obj)
        
        return f"""
🚀 **{current_phase.upper()} PHASE**
Task: {task.description}

📋 **OBJECTIVE:** {phase_obj.description}
{f"🎯 GUIDANCE: {phase_obj.phase_guidance}" if phase_obj.phase_guidance else ""}

{tool_guidance}

💡 **APPROACH:**
- Follow the phase-specific guidance above
- Use assigned tools effectively
- Complete the phase objectives
- Use 'mark_complete' when finished

Task ID: {task.id} | Phase: {current_phase} | Complexity: {task.complexity_level}
"""
    
    def _determine_current_phase(self, task) -> str:
        """Determine which phase the task should be in based on completion status."""
        # Return the current phase that should be executed
        if not hasattr(task, 'current_phase') or not task.current_phase:
            return "planning"
        
        # Return the current phase as-is - mark_complete will handle progression
        return task.current_phase
    
    def _build_tool_guidance(self, phase_obj) -> str:
        """Build rich tool guidance from ToolAssignment objects."""
        guidance_sections = []
        
        if phase_obj.assigned_builtin_tools:
            builtin_guidance = "🛠️ BUILT-IN TOOLS TO USE:\n"
            for tool in phase_obj.assigned_builtin_tools:
                priority_icon = "🔥" if tool.priority == "critical" else "⭐" if tool.priority == "normal" else "💡"
                builtin_guidance += f"""
{priority_icon} {tool.tool_name.upper()} ({tool.priority} priority)
   WHY: {tool.usage_purpose}
   HOW: {chr(10).join([f'   - {action}' for action in tool.specific_actions])}
   EXPECTED: {tool.expected_outcome}
"""
            guidance_sections.append(builtin_guidance)
        
        if phase_obj.assigned_mcp_tools:
            mcp_guidance = "🔌 MCP TOOLS TO USE:\n"
            for tool in phase_obj.assigned_mcp_tools:
                priority_icon = "🔥" if tool.priority == "critical" else "⭐" if tool.priority == "normal" else "💡"
                mcp_guidance += f"""
{priority_icon} {tool.tool_name.upper()} ({tool.priority} priority)
   WHY: {tool.usage_purpose}
   HOW: {chr(10).join([f'   - {action}' for action in tool.specific_actions])}
   EXPECTED: {tool.expected_outcome}
"""
            guidance_sections.append(mcp_guidance)
        
        if phase_obj.assigned_memory_tools:
            memory_guidance = "🧠 MEMORY TOOLS TO USE:\n"
            for memory_tool in phase_obj.assigned_memory_tools:
                priority_icon = "🔥" if memory_tool.priority == "critical" else "⭐" if memory_tool.priority == "normal" else "💡"
                memory_guidance += f"""
{priority_icon} {memory_tool.tool_name.upper()} ({memory_tool.priority} priority)
   WHY: {memory_tool.usage_purpose}
   HOW: {chr(10).join([f'   - {action}' for action in memory_tool.specific_actions])}
   EXPECTED: {memory_tool.expected_outcome}
"""
            guidance_sections.append(memory_guidance)

        if phase_obj.assigned_resources:
            resource_guidance = "📚 RESOURCES TO USE:\n"
            for resource in phase_obj.assigned_resources:
                priority_icon = "🔥" if resource.priority == "critical" else "⭐" if resource.priority == "normal" else "💡"
                resource_guidance += f"""
{priority_icon} {resource.tool_name.upper()} ({resource.priority} priority)
   WHY: {resource.usage_purpose}
   HOW: {chr(10).join([f'   - {action}' for action in resource.specific_actions])}
   EXPECTED: {resource.expected_outcome}
"""
            guidance_sections.append(resource_guidance)
        
        return "\n".join(guidance_sections) if guidance_sections else "No tools assigned to this phase."
    
    def _build_placeholder_guidance(self, task) -> str:
        """Build contextual placeholder guidance based on task complexity and context."""
        
        if task.complexity_level == "simple":
            return """
**PLACEHOLDER GUIDANCE - SIMPLE TASK**
For simple tasks, avoid placeholders and implement complete solutions:

**IMPLEMENT FULLY:**
- Core functionality should be complete
- Error handling should be implemented
- Basic validation should be included
- No TODO comments or placeholder functions

**AVOID PLACEHOLDERS FOR:**
- Main business logic
- Error handling
- Input validation
- Basic functionality

**EXCEPTION:** Only use placeholders for truly out-of-scope features explicitly mentioned as future work.
"""
        elif task.complexity_level == "complex":
            return """
**PLACEHOLDER GUIDANCE - COMPLEX TASK**
For complex tasks, use placeholders strategically:

**STRATEGIC PLACEHOLDERS ARE OK FOR:**
- Future phases explicitly out of current scope
- Advanced features mentioned as "nice-to-have"
- Integration points with external systems not yet available
- Configuration values that will be provided later

**IMPLEMENT FULLY (NO PLACEHOLDERS):**
- Core business logic within current scope
- Error handling and validation
- Security-related functionality
- Data persistence and retrieval
- User interface elements

**PLACEHOLDER BEST PRACTICES:**
- Use descriptive TODO comments explaining what needs to be done
- Include interface definitions even if implementation is placeholder
- Document why the placeholder exists and when it should be implemented
"""
        else:  # architectural
            return """
**PLACEHOLDER GUIDANCE - ARCHITECTURAL TASK**
For architectural tasks, placeholders are acceptable for scaffolding:

**ACCEPTABLE PLACEHOLDERS:**
- Interface definitions with clear contracts
- Service stubs for future microservices
- Database schema placeholders with clear structure
- Configuration templates with example values
- Integration points for external services

**IMPLEMENT FULLY:**
- Core architectural patterns and structures
- Critical path functionality
- Security and authentication frameworks
- Data models and relationships
- API definitions and routing

**ARCHITECTURAL PLACEHOLDER STRATEGY:**
- Create complete interfaces even if implementations are stubs
- Document architectural decisions and rationale
- Provide clear implementation roadmap for placeholders
- Ensure placeholders don't break the overall system design
- Use dependency injection to make placeholder swapping easy

**TRACK PLACEHOLDERS:**
- Maintain a list of all placeholders and their purpose
- Set clear priorities for placeholder implementation
- Review placeholders regularly to prevent technical debt
"""


class MarkCompleteHandler(BaseCommandHandler):
    """Handler for mark_complete command - supports phase progression and task completion."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(
                action="mark_complete",
                status="guidance",
                completion_guidance="🔍 GUIDANCE: No active session found. Please create a session first using 'create_session'.",
                suggested_next_actions=["create_session"]
            )
        
        if not session.tasks:
            return TaskmasterResponse(
                action="mark_complete",
                status="guidance",
                completion_guidance="🔍 GUIDANCE: No tasks found. Please create a tasklist first using 'create_tasklist'.",
                suggested_next_actions=["create_tasklist"]
            )
        
        # Get task ID from command or find the current task
        task_id = command.data.get("task_id")
        if task_id:
            task = next((t for t in session.tasks if t.id == task_id), None)
            if not task:
                return TaskmasterResponse(
                    action="mark_complete",
                    status="error",
                    completion_guidance=f"🔍 GUIDANCE: Task {task_id} not found.",
                    suggested_next_actions=["execute_next"]
                )
        else:
            # Find the current task (first pending task)
            task = next((t for t in session.tasks if t.status == "pending"), None)
            if not task:
                return TaskmasterResponse(
                    action="mark_complete",
                    status="completed",
                    completion_guidance="🎉 All tasks already completed! Great work!",
                    suggested_next_actions=["create_session"]
                )
        
        # Determine current phase and check if we should progress to next phase
        current_phase = getattr(task, 'current_phase', None) or "planning"
        
        # Check if this task has multiple phases defined
        has_planning = task.planning_phase is not None
        has_execution = task.execution_phase is not None  
        has_validation = task.validation_phase is not None
        
        # Simplified phase progression: planning -> execution -> complete
        if current_phase == "planning" and has_execution:
            # Progress to execution phase
            task.current_phase = "execution"
            await self.session_manager.update_session(session)
            
            guidance = f"""
✅ Planning phase completed for: {task.description}

🔄 PROGRESSING TO EXECUTION PHASE

💡 NEXT STEP: Use 'execute_next' to get guidance for the execution phase.

Task ID: {task.id}
Current Phase: execution
"""
            return TaskmasterResponse(
                action="mark_complete",
                session_id=session.id,
                task_id=task.id,
                phase_completed="planning",
                next_phase="execution",
                suggested_next_actions=["execute_next"],
                completion_guidance=guidance
            )
        else:
            # Complete the entire task with enhanced validation
            completion_result = await self._validate_task_completion(task, command)
            
            if not completion_result["valid"]:
                # Completion validation failed
                return TaskmasterResponse(
                    action="mark_complete",
                    session_id=session.id,
                    task_id=task.id,
                    completion_valid=False,
                    validation_issues=completion_result["issues"],
                    suggested_next_actions=["execute_next"],
                    completion_guidance=completion_result["guidance"]
                )
            
            # Mark task as completed
            task.status = "completed"
            task.current_phase = "completed"
            
            # Record completion evidence
            if command.data.get("evidence"):
                task.execution_evidence.extend(command.data.get("evidence", []))
            
            await self.session_manager.update_session(session)
            
            # Check if there are more tasks
            remaining_tasks = [t for t in session.tasks if t.status == "pending"]
            
            if remaining_tasks:
                guidance = f"""
✅ **TASK COMPLETED WITH VALIDATION**
Task: {task.description}

🎯 **PROGRESS:** {len(session.tasks) - len(remaining_tasks)}/{len(session.tasks)} tasks completed

📊 **COMPLETION EVIDENCE:**
{chr(10).join([f"- {evidence}" for evidence in completion_result.get("evidence_summary", ["Task marked complete"])])}

💡 **NEXT STEP:** Use 'execute_next' to continue with the next task.

Remaining tasks: {len(remaining_tasks)}
"""
                next_actions = ["execute_next"]
            else:
                guidance = f"""
🎉 **ALL TASKS COMPLETED!** Outstanding work!

📊 **SESSION SUMMARY:**
- Session: {session.id}
- Tasks completed: {len(session.tasks)}
- Final task: {task.description}

✅ **VALIDATION CONFIRMED:**
All tasks completed with proper evidence and validation.

💡 **NEXT STEPS:** Use 'end_session' to formally close this session.
"""
                next_actions = ["end_session"]
        
            return TaskmasterResponse(
                action="mark_complete",
                session_id=session.id,
                task_id=task.id,
                task_completed=True,
                all_tasks_completed=len(remaining_tasks) == 0,
                tasks_remaining=len(remaining_tasks),
                completion_evidence=completion_result.get("evidence_summary", []),
                suggested_next_actions=next_actions,
                completion_guidance=guidance
            )
    
    async def _validate_task_completion(self, task, command):
        """Enhanced validation for task completion with anti-hallucination checks."""
        
        validation_issues = []
        evidence_summary = []
        
        # Check for evidence in command data
        provided_evidence = command.data.get("evidence", [])
        console_output = command.data.get("console_output", "")
        file_changes = command.data.get("file_changes", [])
        force_complete = command.data.get("force_complete", False)
        
        # If force_complete is set, bypass most validation
        if force_complete:
            return {
                "valid": True,
                "evidence_summary": [command.data.get("description", "Task force completed by user")],
                "issues": []
            }
        
        # More flexible validation based on task complexity
        if task.complexity_level in ["complex", "architectural"]:
            # Complex tasks require substantial evidence, but be flexible about format
            if not provided_evidence and not console_output and not file_changes:
                # Check if evidence is provided in other ways (like user description)
                user_description = command.data.get("description", "")
                execution_evidence = getattr(task, 'execution_evidence', [])
                
                if not user_description and not execution_evidence:
                    validation_issues.append("Complex tasks require completion evidence (console output, file changes, proof of functionality, or detailed description)")
            
            # Check for adversarial review completion - but allow bypass if evidence is strong
            if task.requires_adversarial_review:
                has_review = hasattr(task, 'adversarial_review') and task.adversarial_review
                review_approved = has_review and getattr(task.adversarial_review, 'approved', False)
                has_strong_evidence = len(provided_evidence) >= 3 or console_output or file_changes
                
                if not review_approved and not has_strong_evidence:
                    validation_issues.append("Complex task requires either adversarial review completion OR substantial evidence of completion")
        
        # More flexible phase validation - allow completion from any phase if evidence is strong
        current_phase = getattr(task, 'current_phase', 'planning')
        has_strong_evidence = len(provided_evidence) >= 2 or console_output or file_changes
        user_claims_complete = "complete" in command.data.get("description", "").lower() or "finished" in command.data.get("description", "").lower()
        
        if current_phase not in ["validation", "completed"] and not has_strong_evidence and not user_claims_complete:
            validation_issues.append(f"Task is in {current_phase} phase - provide evidence of completion or progress to validation phase")
        
        # Check validation phase requirements - but be flexible
        if task.validation_phase and task.validation_phase.steps and not has_strong_evidence:
            missing_validations = []
            all_evidence_text = " ".join(provided_evidence + [console_output] + [str(command.data)])
            
            for step in task.validation_phase.steps:
                step_keywords = step.lower().split()
                if not any(keyword in all_evidence_text.lower() for keyword in step_keywords):
                    missing_validations.append(step)
            
            # Only require validation steps if there's no other strong evidence
            if missing_validations and len(missing_validations) == len(task.validation_phase.steps):
                validation_issues.append(f"Consider providing evidence for validation steps: {', '.join(missing_validations[:2])}")
        
        # Build evidence summary
        if provided_evidence:
            evidence_summary.extend(provided_evidence)
        if console_output:
            evidence_summary.append(f"Console output captured: {console_output[:100]}...")
        if file_changes:
            evidence_summary.extend([f"File changed: {change}" for change in file_changes])
        
        # Generate guidance for failed validation
        if validation_issues:
            guidance = f"""
⚠️ **COMPLETION VALIDATION NEEDS ATTENTION**
Task: {task.description}

🔍 **VALIDATION FEEDBACK:**
{chr(10).join([f"- {issue}" for issue in validation_issues])}

💡 **EASY WAYS TO COMPLETE:**
1. **Provide Evidence**: Include completion proof in your mark_complete command:
   ```
   {{"action": "mark_complete", "evidence": ["Evidence item 1", "Evidence item 2"], "description": "Task completed because..."}}
   ```

2. **Alternative Completion**: If you have strong evidence of completion, you can:
   - Include detailed description of what was accomplished
   - Provide console outputs or file changes
   - Reference specific results achieved

3. **Force Completion**: If you're confident the task is done:
   ```
   {{"action": "mark_complete", "description": "Task completed - [your evidence here]", "force_complete": true}}
   ```

📊 **CURRENT STATUS:**
- Task ID: {task.id}
- Phase: {current_phase}
- Complexity: {task.complexity_level}
- Evidence provided: {len(provided_evidence)} items

🎯 **RECOMMENDATION:**
If you believe this task is actually complete, provide a brief description of what was accomplished and try again.
"""
            
            return {
                "valid": False,
                "issues": validation_issues,
                "guidance": guidance
            }
        
        # Validation passed
        return {
            "valid": True,
            "evidence_summary": evidence_summary or ["Task completed successfully"],
            "issues": []
        }


class GetStatusHandler(BaseCommandHandler):
    """Handler for get_status command."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        
        if not session:
            return TaskmasterResponse(
                action="get_status",
                status="no_session",
                completion_guidance="🔍 STATUS: No active session. Use 'create_session' to begin.",
                suggested_next_actions=["create_session"],
                session_exists=False
            )
        
        # Analyze session state
        total_tasks = len(session.tasks)
        completed_tasks = len([task for task in session.tasks if task.status == "completed"])
        pending_tasks = len([task for task in session.tasks if task.status == "pending"])
        in_progress_tasks = len([task for task in session.tasks if task.status == "in_progress"])
        
        # Determine next suggested action
        if not session.capabilities.built_in_tools and not session.capabilities.mcp_tools:
            next_action = "declare_capabilities"
            status_message = "Session created, capabilities not declared"
        elif not session.tasks:
            next_action = "create_tasklist"
            status_message = "Capabilities declared, tasklist not created"
        elif session.tasks and not any(task.execution_phase and (task.execution_phase.assigned_builtin_tools or task.execution_phase.assigned_mcp_tools or task.execution_phase.assigned_resources) for task in session.tasks):
            next_action = "map_capabilities"
            status_message = "Tasks created but capabilities not mapped to phases"
        elif in_progress_tasks > 0:
            next_action = "execute_next"
            status_message = f"Task in progress: {in_progress_tasks} active - call execute_next to complete and continue"
        elif pending_tasks > 0:
            next_action = "execute_next"
            status_message = f"Tasks pending: {pending_tasks} remaining"
        elif completed_tasks == total_tasks and total_tasks > 0:
            next_action = "mark_complete"
            status_message = "All tasks completed, ready to finish"
        else:
            next_action = "create_tasklist"
            status_message = "Session active, ready for tasks"
        
        guidance = f"""
📊 SESSION STATUS: {status_message}

🔍 Current State:
- Session ID: {session.id}
- Session Name: {session.session_name or 'Unnamed'}
- Status: {session.status}
- Total Tasks: {total_tasks}
- Completed: {completed_tasks}
- Pending: {pending_tasks}
- In Progress: {in_progress_tasks}

💡 NEXT RECOMMENDED ACTION: {next_action}
"""
        
        return TaskmasterResponse(
            action="get_status",
            session_id=session.id,
            session_name=session.session_name,
            session_status=session.status,
            task_summary={
                "total": total_tasks,
                "completed": completed_tasks,
                "pending": pending_tasks,
                "in_progress": in_progress_tasks
            },
            suggested_next_actions=[next_action],
            completion_guidance=guidance,
            current_state=status_message
        )


class CollaborationRequestHandler(BaseCommandHandler):
    """Handler for collaboration_request command."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(
                action="collaboration_request",
                status="guidance",
                completion_guidance="🔍 GUIDANCE: No active session found. Please create a session first using 'create_session'.",
                suggested_next_actions=["create_session"]
            )
        
        collaboration_context = command.collaboration_context or "General guidance needed"
        
        guidance = f"""
🤝 COLLABORATION REQUEST RECEIVED

📝 Context: {collaboration_context}

💡 GUIDANCE OPTIONS:
1. **Review Current State**: Use 'get_status' to understand where you are
2. **Seek Specific Help**: Describe what specific guidance you need
3. **Continue Execution**: Use 'execute_next' to proceed with current task

🔍 TROUBLESHOOTING TIPS:
- Check if you have the right capabilities declared
- Ensure you're following the recommended workflow
- Consider if you need to break down the current task further

What specific help do you need?
"""
        
        return TaskmasterResponse(
            action="collaboration_request",
            session_id=session.id,
            collaboration_context=collaboration_context,
            workflow_state={
                "paused": True,
                "validation_state": "collaboration_requested",
                "can_progress": True
            },
            suggested_next_actions=["get_status", "execute_next"],
            completion_guidance=guidance,
            next_action_needed=True
        ) 


class EndSessionHandler(BaseCommandHandler):
    """Handler for end_session command."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(
                action="end_session",
                status="guidance",
                completion_guidance="🔍 GUIDANCE: No active session found. Nothing to end.",
                suggested_next_actions=["create_session"]
            )
        
        # Get session statistics before ending
        total_tasks = len(session.tasks)
        completed_tasks = len([task for task in session.tasks if task.status == "completed"])
        pending_tasks = len([task for task in session.tasks if task.status == "pending"])
        completion_rate = (completed_tasks / total_tasks * 100) if total_tasks > 0 else 0
        
        # End the session using SessionManager
        try:
            await self.session_manager.end_session(session.id)
            
            # Generate session summary
            session_summary = {
                "session_id": session.id,
                "session_name": session.session_name or "Unnamed Session",
                "total_tasks": total_tasks,
                "completed_tasks": completed_tasks,
                "pending_tasks": pending_tasks,
                "completion_rate": round(completion_rate, 1),
                "ended_at": "2025-01-27T00:00:00Z"
            }
            
            if completed_tasks == total_tasks and total_tasks > 0:
                completion_message = f"🎉 **PERFECT SESSION!** All {total_tasks} tasks completed successfully!"
            elif completed_tasks > 0:
                completion_message = f"✅ **SESSION COMPLETED** with {completed_tasks}/{total_tasks} tasks finished ({completion_rate:.1f}%)"
            else:
                completion_message = f"📋 **SESSION ENDED** - No tasks were completed"
            
            guidance = f"""
{completion_message}

📊 **FINAL SESSION SUMMARY:**
- Session ID: {session.id}
- Session Name: {session.session_name or 'Unnamed Session'}
- Tasks Completed: {completed_tasks}/{total_tasks}
- Completion Rate: {completion_rate:.1f}%

🎯 **SESSION ACHIEVEMENTS:**
{chr(10).join([f"✅ {task.description}" for task in session.tasks if task.status == "completed"]) if completed_tasks > 0 else "- No tasks completed in this session"}

{"🔄 **REMAINING TASKS:**" + chr(10) + chr(10).join([f"⏳ {task.description}" for task in session.tasks if task.status == "pending"]) if pending_tasks > 0 else ""}

💡 **NEXT STEPS:**
- Use 'create_session' to start a new session
- All session data has been preserved for future reference

Thank you for using Taskmaster! 🚀
"""
            
            return TaskmasterResponse(
                action="end_session",
                session_id=session.id,
                session_ended=True,
                session_summary=session_summary,
                completion_rate=completion_rate,
                tasks_completed=completed_tasks,
                tasks_total=total_tasks,
                suggested_next_actions=["create_session"],
                completion_guidance=guidance
            )
            
        except Exception as e:
            return TaskmasterResponse(
                action="end_session",
                status="error",
                completion_guidance=f"🔍 GUIDANCE: Failed to end session: {str(e)}",
                error_details=str(e),
                suggested_next_actions=["get_status"]
            )


class AddTaskHandler(BaseCommandHandler):
    """Handler for add_task command - allows adding individual tasks to existing tasklist."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(
                action="add_task",
                status="guidance",
                completion_guidance="🔍 GUIDANCE: No active session found. Please create a session first using 'create_session'.",
                suggested_next_actions=["create_session"]
            )
        
        # Get task data
        task_description = command.data.get("task_description", "")
        task_data = command.data.get("task_data", {})
        
        if not task_description and not task_data.get("description"):
            guidance = """
➕ ADD TASK TO EXISTING TASKLIST

📋 PROVIDE TASK DETAILS:
Call taskmaster with:
{
  "action": "add_task",
  "task_description": "Clear description of the new task",
  "task_data": {
    "description": "Alternative way to provide description",
    "initial_tool_thoughts": {
      "planning_tools_needed": ["tool1", "tool2"],
      "execution_tools_needed": ["tool3", "tool4"],
      "validation_tools_needed": ["tool1"],
      "reasoning": "Why these tools are needed for this specific task"
    },
    "planning_phase": {
      "description": "What planning is needed for this task",
      "steps": ["Analyze requirements", "Create execution plan"],
      "phase_guidance": "Specific planning approach for this task"
    },
    "execution_phase": {
      "description": "How this task will be executed",
      "steps": ["Step 1", "Step 2", "Step 3"],
      "phase_guidance": "Key execution considerations"
    },
    "validation_phase": {
      "description": "How to validate task completion",
      "steps": ["Check output quality", "Verify requirements met"],
      "phase_guidance": "Validation criteria and success metrics"
    }
  }
}

💡 SIMPLIFIED ADDITION: You can also just provide task_description for a basic task.
"""
            
            return TaskmasterResponse(
                action="add_task",
                session_id=session.id,
                suggested_next_actions=["add_task"],
                completion_guidance=guidance
            )
        
        # Use task_description if provided, otherwise extract from task_data
        description = task_description or task_data.get("description", "")
        
        # Create enhanced task structure
        enhanced_task_data = {
            "description": description,
            "initial_tool_thoughts": task_data.get("initial_tool_thoughts", {
                "planning_tools_needed": [],
                "execution_tools_needed": [],
                "validation_tools_needed": [],
                "reasoning": "No initial tool thoughts provided - consider which tools you'll need"
            }),
            "planning_phase": task_data.get("planning_phase", {
                "description": f"Plan the execution of: {description}",
                "steps": ["Analyze requirements", "Create execution plan"],
                "phase_guidance": "Focus on understanding requirements and planning approach"
            }),
            "execution_phase": task_data.get("execution_phase", {
                "description": f"Execute: {description}",
                "steps": ["Follow execution plan", "Implement solution"],
                "phase_guidance": "Focus on careful implementation and testing"
            }),
            "validation_phase": task_data.get("validation_phase", None)  # Optional in streamlined flow
        }
        
        # Use existing CreateTasklistHandler logic to create the task
        from .models import Task, ArchitecturalTaskPhase, InitialToolThoughts
        
        # Create ArchitecturalTaskPhase objects
        planning_phase = ArchitecturalTaskPhase(
            phase_name="planning",
            description=enhanced_task_data["planning_phase"]["description"],
            steps=enhanced_task_data["planning_phase"].get("steps", []),
            phase_guidance=enhanced_task_data["planning_phase"].get("phase_guidance", "")
        )
        
        execution_phase = ArchitecturalTaskPhase(
            phase_name="execution",
            description=enhanced_task_data["execution_phase"]["description"],
            steps=enhanced_task_data["execution_phase"].get("steps", []),
            phase_guidance=enhanced_task_data["execution_phase"].get("phase_guidance", "")
        )
        
        # Validation phase is optional in streamlined flow
        validation_phase = None
        if enhanced_task_data.get("validation_phase"):
            validation_phase = ArchitecturalTaskPhase(
                phase_name="validation",
                description=enhanced_task_data["validation_phase"]["description"],
                steps=enhanced_task_data["validation_phase"].get("steps", []),
                phase_guidance=enhanced_task_data["validation_phase"].get("phase_guidance", "")
            )
        
        # Assess task complexity
        complexity = self._assess_task_complexity(enhanced_task_data)
        
        # Create new task
        new_task = Task(
            description=description,
            status="pending",
            current_phase="planning",
            planning_phase=planning_phase,
            execution_phase=execution_phase,
            validation_phase=validation_phase,
            complexity_level=complexity,
            requires_adversarial_review=complexity in ["complex", "architectural"],
            initial_tool_thoughts=InitialToolThoughts(**enhanced_task_data["initial_tool_thoughts"])
        )
        
        # Add to session
        session.tasks.append(new_task)
        await self.session_manager.update_session(session)
        
        guidance = f"""
✅ TASK ADDED TO TASKLIST

📋 NEW TASK DETAILS:
- ID: {new_task.id}
- Description: {description}
- Complexity: {complexity}
- Requires Adversarial Review: {new_task.requires_adversarial_review}
- Status: {new_task.status}

📊 UPDATED TASKLIST:
- Total Tasks: {len(session.tasks)}
- Pending Tasks: {len([t for t in session.tasks if t.status == 'pending'])}
- Completed Tasks: {len([t for t in session.tasks if t.status == 'completed'])}

💡 NEXT STEPS:
- Use 'map_capabilities' if you need to assign tools to this task's phases
- Use 'execute_next' to continue with task execution
- Use 'get_status' to see the full tasklist status
"""
        
        return TaskmasterResponse(
            action="add_task",
            session_id=session.id,
            task_added=True,
            new_task={
                "id": new_task.id,
                "description": new_task.description,
                "complexity_level": new_task.complexity_level,
                "status": new_task.status
            },
            total_tasks=len(session.tasks),
            suggested_next_actions=["map_capabilities", "execute_next", "get_status"],
            completion_guidance=guidance
        )
    
    def _assess_task_complexity(self, task_data):
        """Assess task complexity based on description and structure."""
        description = task_data.get("description", "").lower()
        
        # Architectural complexity indicators
        if any(word in description for word in ["system", "architecture", "framework", "multiple", "integration"]):
            return "architectural"
        
        # Complex task indicators
        if any(word in description for word in ["implement", "create", "build", "develop", "code", "file", "database"]):
            return "complex"
        
        # Default to simple
        return "simple"


class RemoveTaskHandler(BaseCommandHandler):
    """Handler for remove_task command - allows removing tasks from the tasklist."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(
                action="remove_task",
                status="guidance",
                completion_guidance="🔍 GUIDANCE: No active session found. Please create a session first using 'create_session'.",
                suggested_next_actions=["create_session"]
            )
        
        if not session.tasks:
            return TaskmasterResponse(
                action="remove_task",
                status="guidance",
                completion_guidance="🔍 GUIDANCE: No tasks found in the current session. Use 'create_tasklist' or 'add_task' to add tasks first.",
                suggested_next_actions=["create_tasklist", "add_task"]
            )
        
        # Get task identifier
        task_id = command.data.get("task_id", "")
        task_description = command.data.get("task_description", "")
        task_index = command.data.get("task_index")
        
        if not task_id and not task_description and task_index is None:
            # Show available tasks for removal
            tasks_list = "\n".join([
                f"   {i+1}. {task.description} (ID: {task.id}, Status: {task.status})"
                for i, task in enumerate(session.tasks)
            ])
            
            guidance = f"""
🗑️ REMOVE TASK FROM TASKLIST

📋 CURRENT TASKS:
{tasks_list}

🎯 SPECIFY TASK TO REMOVE:
Call taskmaster with ONE of these options:
{{
  "action": "remove_task",
  "task_id": "task_abc123"  // Exact task ID
}}

OR

{{
  "action": "remove_task", 
  "task_description": "partial description to match"  // Will match first task containing this text
}}

OR

{{
  "action": "remove_task",
  "task_index": 0  // Zero-based index (0 = first task, 1 = second task, etc.)
}}

⚠️ WARNING: Removing tasks will affect task execution order and may disrupt ongoing work.
"""
            
            return TaskmasterResponse(
                action="remove_task",
                session_id=session.id,
                available_tasks=[{
                    "id": task.id,
                    "description": task.description,
                    "status": task.status,
                    "index": i
                } for i, task in enumerate(session.tasks)],
                suggested_next_actions=["remove_task"],
                completion_guidance=guidance
            )
        
        # Find the task to remove
        task_to_remove = None
        removal_method = ""
        
        if task_id:
            task_to_remove = next((task for task in session.tasks if task.id == task_id), None)
            removal_method = f"ID '{task_id}'"
        elif task_description:
            task_to_remove = next((task for task in session.tasks if task_description.lower() in task.description.lower()), None)
            removal_method = f"description containing '{task_description}'"
        elif task_index is not None:
            if 0 <= task_index < len(session.tasks):
                task_to_remove = session.tasks[task_index]
                removal_method = f"index {task_index}"
            else:
                return TaskmasterResponse(
                    action="remove_task",
                    status="guidance",
                    completion_guidance=f"🔍 GUIDANCE: Task index {task_index} is out of range. Valid indices are 0 to {len(session.tasks)-1}.",
                    suggested_next_actions=["remove_task"]
                )
        
        if not task_to_remove:
            return TaskmasterResponse(
                action="remove_task",
                status="guidance",
                completion_guidance=f"🔍 GUIDANCE: No task found matching {removal_method}. Use 'get_status' to see available tasks.",
                suggested_next_actions=["get_status", "remove_task"]
            )
        
        # Check if task is currently being executed
        if task_to_remove.status == "in_progress" or (task_to_remove.status == "pending" and task_to_remove.current_phase and task_to_remove.current_phase != "planning"):
            return TaskmasterResponse(
                action="remove_task",
                status="guidance",
                completion_guidance=f"⚠️ GUIDANCE: Cannot remove task '{task_to_remove.description}' because it's currently being executed. Complete or reset the task first.",
                suggested_next_actions=["mark_complete", "get_status"]
            )
        
        # Remove the task
        removed_task_info = {
            "id": task_to_remove.id,
            "description": task_to_remove.description,
            "status": task_to_remove.status
        }
        
        session.tasks.remove(task_to_remove)
        await self.session_manager.update_session(session)
        
        guidance = f"""
✅ TASK REMOVED FROM TASKLIST

🗑️ REMOVED TASK:
- ID: {removed_task_info['id']}
- Description: {removed_task_info['description']}
- Status: {removed_task_info['status']}
- Removal Method: {removal_method}

📊 UPDATED TASKLIST:
- Total Tasks: {len(session.tasks)}
- Pending Tasks: {len([t for t in session.tasks if t.status == 'pending'])}
- Completed Tasks: {len([t for t in session.tasks if t.status == 'completed'])}

💡 NEXT STEPS:
- Use 'get_status' to see the updated tasklist
- Use 'execute_next' to continue with remaining tasks
- Use 'add_task' to add new tasks if needed
"""
        
        return TaskmasterResponse(
            action="remove_task",
            session_id=session.id,
            task_removed=True,
            removed_task=removed_task_info,
            removal_method=removal_method,
            total_tasks=len(session.tasks),
            suggested_next_actions=["get_status", "execute_next", "add_task"],
            completion_guidance=guidance
        )


class UpdateTaskHandler(BaseCommandHandler):
    """Handler for update_task command - allows updating existing tasks in the tasklist."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(
                action="update_task",
                status="guidance",
                completion_guidance="🔍 GUIDANCE: No active session found. Please create a session first using 'create_session'.",
                suggested_next_actions=["create_session"]
            )
        
        if not session.tasks:
            return TaskmasterResponse(
                action="update_task",
                status="guidance",
                completion_guidance="🔍 GUIDANCE: No tasks found in the current session. Use 'create_tasklist' or 'add_task' to add tasks first.",
                suggested_next_actions=["create_tasklist", "add_task"]
            )
        
        # Get task identifier and update data
        task_id = command.data.get("task_id", "")
        task_index = command.data.get("task_index")
        updated_task_data = command.data.get("updated_task_data", {})
        
        if not task_id and task_index is None:
            # Show available tasks for updating
            tasks_list = "\n".join([
                f"   {i+1}. {task.description} (ID: {task.id}, Status: {task.status})"
                for i, task in enumerate(session.tasks)
            ])
            
            guidance = f"""
✏️ UPDATE EXISTING TASK

📋 CURRENT TASKS:
{tasks_list}

🎯 SPECIFY TASK AND UPDATES:
Call taskmaster with:
{{
  "action": "update_task",
  "task_id": "task_abc123",  // OR "task_index": 0
  "updated_task_data": {{
    "description": "New task description",  // Optional
    "planning_phase": {{
      "description": "Updated planning description",
      "steps": ["New step 1", "New step 2"],
      "phase_guidance": "Updated planning guidance"
    }},
    "execution_phase": {{
      "description": "Updated execution description", 
      "steps": ["New execution step 1", "New execution step 2"],
      "phase_guidance": "Updated execution guidance"
    }},
    "validation_phase": {{
      "description": "Updated validation description",
      "steps": ["New validation step 1", "New validation step 2"],
      "phase_guidance": "Updated validation guidance"
    }}
  }}
}}

💡 PARTIAL UPDATES: You can update just the fields you want to change.
⚠️ WARNING: Updating tasks may affect ongoing execution.
"""
            
            return TaskmasterResponse(
                action="update_task",
                session_id=session.id,
                available_tasks=[{
                    "id": task.id,
                    "description": task.description,
                    "status": task.status,
                    "index": i
                } for i, task in enumerate(session.tasks)],
                suggested_next_actions=["update_task"],
                completion_guidance=guidance
            )
        
        if not updated_task_data:
            return TaskmasterResponse(
                action="update_task",
                status="guidance",
                completion_guidance="🔍 GUIDANCE: No update data provided. Include 'updated_task_data' with the fields you want to change.",
                suggested_next_actions=["update_task"]
            )
        
        # Find the task to update
        task_to_update = None
        update_method = ""
        
        if task_id:
            task_to_update = next((task for task in session.tasks if task.id == task_id), None)
            update_method = f"ID '{task_id}'"
        elif task_index is not None:
            if 0 <= task_index < len(session.tasks):
                task_to_update = session.tasks[task_index]
                update_method = f"index {task_index}"
            else:
                return TaskmasterResponse(
                    action="update_task",
                    status="guidance",
                    completion_guidance=f"🔍 GUIDANCE: Task index {task_index} is out of range. Valid indices are 0 to {len(session.tasks)-1}.",
                    suggested_next_actions=["update_task"]
                )
        
        if not task_to_update:
            return TaskmasterResponse(
                action="update_task",
                status="guidance",
                completion_guidance=f"🔍 GUIDANCE: No task found matching {update_method}. Use 'get_status' to see available tasks.",
                suggested_next_actions=["get_status", "update_task"]
            )
        
        # Track what was updated
        updates_made = []
        
        # Update description if provided
        if "description" in updated_task_data:
            old_description = task_to_update.description
            task_to_update.description = updated_task_data["description"]
            updates_made.append(f"Description: '{old_description}' → '{task_to_update.description}'")
        
        # Update phases if provided
        for phase_name in ["planning_phase", "execution_phase", "validation_phase"]:
            if phase_name in updated_task_data:
                phase_obj = getattr(task_to_update, phase_name, None)
                if phase_obj:
                    phase_updates = updated_task_data[phase_name]
                    
                    if "description" in phase_updates:
                        phase_obj.description = phase_updates["description"]
                        updates_made.append(f"{phase_name.replace('_', ' ').title()}: Description updated")
                    
                    if "steps" in phase_updates:
                        phase_obj.steps = phase_updates["steps"]
                        updates_made.append(f"{phase_name.replace('_', ' ').title()}: Steps updated")
                    
                    if "phase_guidance" in phase_updates:
                        phase_obj.phase_guidance = phase_updates["phase_guidance"]
                        updates_made.append(f"{phase_name.replace('_', ' ').title()}: Guidance updated")
        
        # Reassess complexity if description changed
        if "description" in updated_task_data:
            old_complexity = task_to_update.complexity_level
            new_complexity = self._assess_task_complexity({"description": task_to_update.description})
            if new_complexity != old_complexity:
                task_to_update.complexity_level = new_complexity
                task_to_update.requires_adversarial_review = new_complexity in ["complex", "architectural"]
                updates_made.append(f"Complexity: {old_complexity} → {new_complexity}")
        
        await self.session_manager.update_session(session)
        
        guidance = f"""
✅ TASK UPDATED SUCCESSFULLY

✏️ UPDATED TASK:
- ID: {task_to_update.id}
- Description: {task_to_update.description}
- Status: {task_to_update.status}
- Complexity: {task_to_update.complexity_level}

🔄 CHANGES MADE:
{chr(10).join([f"   - {update}" for update in updates_made]) if updates_made else "   - No changes detected"}

💡 NEXT STEPS:
- Use 'get_status' to see the updated tasklist
- Use 'map_capabilities' if phases were updated and need tool assignments
- Use 'execute_next' to continue with task execution
"""
        
        return TaskmasterResponse(
            action="update_task",
            session_id=session.id,
            task_updated=True,
            updated_task={
                "id": task_to_update.id,
                "description": task_to_update.description,
                "status": task_to_update.status,
                "complexity_level": task_to_update.complexity_level
            },
            updates_made=updates_made,
            update_method=update_method,
            suggested_next_actions=["get_status", "map_capabilities", "execute_next"],
            completion_guidance=guidance
        )
    
    def _assess_task_complexity(self, task_data):
        """Assess task complexity based on description and structure."""
        description = task_data.get("description", "").lower()
        
        # Architectural complexity indicators
        if any(word in description for word in ["system", "architecture", "framework", "multiple", "integration"]):
            return "architectural"
        
        # Complex task indicators
        if any(word in description for word in ["implement", "create", "build", "develop", "code", "file", "database"]):
            return "complex"
        
        # Default to simple
        return "simple"


class TaskmasterCommandHandler:
    """
    Main command handler that orchestrates all taskmaster operations.
    Uses flexible guidance approach instead of rigid validation.
    """
    
    def __init__(self, session_manager: SessionManager, validation_engine: ValidationEngine):
        self.session_manager = session_manager
        self.validation_engine = validation_engine
        
        # Register ALL command handlers for complete workflow support
        self.handlers = {
            "create_session": CreateSessionHandler(session_manager, validation_engine),
            "declare_capabilities": DeclareCapabilitiesHandler(session_manager, validation_engine),
            "discover_capabilities": DiscoverCapabilitiesHandler(session_manager, validation_engine),
            "create_tasklist": CreateTasklistHandler(session_manager, validation_engine),
            "add_task": AddTaskHandler(session_manager, validation_engine),
            "remove_task": RemoveTaskHandler(session_manager, validation_engine),
            "update_task": UpdateTaskHandler(session_manager, validation_engine),
            "map_capabilities": MapCapabilitiesHandler(session_manager, validation_engine),
            "execute_next": ExecuteNextHandler(session_manager, validation_engine),
            "mark_complete": MarkCompleteHandler(session_manager, validation_engine),
            "get_status": GetStatusHandler(session_manager, validation_engine),
            "collaboration_request": CollaborationRequestHandler(session_manager, validation_engine),
            "end_session": EndSessionHandler(session_manager, validation_engine),
            
            # Advanced Architectural Pattern Commands
            "initialize_world_model": InitializeWorldModelHandler(session_manager, validation_engine),
            "create_hierarchical_plan": CreateHierarchicalPlanHandler(session_manager, validation_engine),
            "initiate_adversarial_review": InitiateAdversarialReviewHandler(session_manager, validation_engine),
            "record_host_grounding": RecordHostGroundingHandler(session_manager, validation_engine),
            
            # Additional helper commands for architectural patterns
            "update_world_model": UpdateWorldModelHandler(session_manager, validation_engine),
            "record_adversarial_findings": RecordAdversarialFindingsHandler(session_manager, validation_engine),
            "record_test_results": RecordTestResultsHandler(session_manager, validation_engine),
            "static_analysis": StaticAnalysisHandler(session_manager, validation_engine),
            "advance_hierarchical_step": AdvanceHierarchicalStepHandler(session_manager, validation_engine),
        }
    
    async def execute(self, command: TaskmasterCommand) -> TaskmasterResponse:
        """Execute a command using the appropriate handler."""
        action = command.action
        
        # Get handler for the action
        handler = self.handlers.get(action)
        if not handler:
            # Provide guidance instead of blocking
            return TaskmasterResponse(
                action=action,
                status="guidance",
                completion_guidance=f"🔍 GUIDANCE: Action '{action}' not yet implemented. Available actions: {', '.join(self.handlers.keys())}",
                suggested_next_actions=list(self.handlers.keys())
            )
        
        # Execute the handler
        try:
            return await handler.handle(command)
        except Exception as e:
            # Convert errors to guidance
            logger.error(f"Error executing {action}: {e}")
            return TaskmasterResponse(
                action=action,
                status="guidance",
                completion_guidance=f"🔍 GUIDANCE: Issue encountered with {action}: {str(e)}\n\n💡 Consider checking your input or trying a different approach.",
                error_details=str(e)
            )
    
    def add_handler(self, action: str, handler: BaseCommandHandler) -> None:
        """Add a new command handler."""
        self.handlers[action] = handler
    
    def get_available_actions(self) -> List[str]:
        """Get list of available actions."""
        return list(self.handlers.keys())


# Advanced Architectural Pattern Handlers

class InitializeWorldModelHandler(BaseCommandHandler):
    """Handler for initialize_world_model command - Implements Dynamic World Model pattern."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(
                action="initialize_world_model",
                status="guidance",
                completion_guidance="🔍 GUIDANCE: No active session found. Please create a session first using 'create_session'.",
                suggested_next_actions=["create_session"]
            )
        
        # Enable architectural mode
        session.architectural_mode = True
        
        # Get initialization parameters
        target_files = command.data.get("target_files", [])
        analysis_scope = command.data.get("analysis_scope", "current_task")
        complexity_level = command.data.get("complexity_level", "complex")
        
        # Initialize or update world model
        if not session.world_model:
            from .models import DynamicWorldModel
            session.world_model = DynamicWorldModel()
        
        # Add initial static analysis entry
        from .models import WorldModelEntry
        initial_entry = WorldModelEntry(
            entry_type="static_analysis",
            source="tanuki-architect",
            content=f"World Model initialized for {analysis_scope} analysis. Target files: {', '.join(target_files)}",
            criticality="critical"
        )
        session.world_model.entries.append(initial_entry)
        
        await self.session_manager.update_session(session)
        
        guidance = f"""
🌍 DYNAMIC WORLD MODEL INITIALIZED

🎯 ARCHITECTURAL PATTERN: Countering Architectural Blindness
- World Model will maintain live, state-aware context throughout task execution
- All tool outputs will be recorded as ground truth, not hallucinated state
- Critical files and functions will be tracked dynamically

📊 WORLD MODEL CONFIGURATION:
- Analysis Scope: {analysis_scope}
- Target Files: {len(target_files)} files specified
- Complexity Level: {complexity_level}
- Static Analysis Required: {'Yes' if target_files else 'Pending'}

🔄 NEXT STEPS:
1. Use 'update_world_model' after each tool execution to record real outputs
2. Reference world model entries when making decisions
3. Use 'static_analysis' action to populate initial codebase understanding

💡 PATTERN ENFORCEMENT: Every tool execution should update the world model with real results.
"""
        
        return TaskmasterResponse(
            action="initialize_world_model",
            session_id=session.id,
            world_model_initialized=True,
            architectural_mode=True,
            target_files=target_files,
            analysis_scope=analysis_scope,
            suggested_next_actions=["static_analysis", "update_world_model"],
            completion_guidance=guidance
        )


class CreateHierarchicalPlanHandler(BaseCommandHandler):
    """Handler for create_hierarchical_plan command - Implements Hierarchical Planning pattern."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(
                action="create_hierarchical_plan",
                status="guidance",
                completion_guidance="🔍 GUIDANCE: No active session found. Please create a session first using 'create_session'.",
                suggested_next_actions=["create_session"]
            )
        
        # Get hierarchical plan data
        high_level_steps = command.data.get("high_level_steps", [])
        current_step_breakdown = command.data.get("current_step_breakdown", [])
        verification_required = command.data.get("verification_required", True)
        
        if not high_level_steps:
            guidance = """
🏗️ HIERARCHICAL PLANNING PATTERN REQUIRED

🎯 ARCHITECTURAL PATTERN: Countering Brittle Planning with Hierarchical, Iterative Loop

📋 PROVIDE HIGH-LEVEL STRATEGIC PLAN:
Call taskmaster again with:
{
  "action": "create_hierarchical_plan",
  "high_level_steps": [
    "1. High-level strategic step (e.g., 'Refactor auth service')",
    "2. Next strategic step (e.g., 'Write migration script')",
    "3. Final strategic step (e.g., 'Update web UI')"
  ],
  "current_step_breakdown": [
    "Sub-task 1 for first step",
    "Sub-task 2 for first step",
    "Sub-task 3 for first step"
  ],
  "verification_required": true
}

💡 PATTERN PHILOSOPHY:
- FORESIGHT: Create high-level strategic plan first
- FOCUS: Break down only the FIRST step into executable sub-tasks
- VERIFICATION: Complete and verify each step before moving to next
- ITERATION: System stays in known, good state at each transition
"""
            
            return TaskmasterResponse(
                action="create_hierarchical_plan",
                session_id=session.id,
                suggested_next_actions=["create_hierarchical_plan"],
                completion_guidance=guidance
            )
        
        # Create hierarchical plan
        from .models import HierarchicalPlan
        hierarchical_plan = HierarchicalPlan(
            high_level_steps=high_level_steps,
            current_step_index=0,
            current_step_breakdown=current_step_breakdown,
            current_subtask_index=0,
            verification_required=verification_required
        )
        
        session.current_hierarchical_plan = hierarchical_plan
        
        # Update current task if it exists
        if session.tasks:
            current_task = next((task for task in session.tasks if task.status == "pending"), None)
            if current_task:
                current_task.requires_hierarchical_planning = True
                current_task.complexity_level = "architectural"
                
                # Update current phase with hierarchical plan
                if current_task.current_phase == "planning" and current_task.planning_phase:
                    current_task.planning_phase.hierarchical_plan = hierarchical_plan
        
        await self.session_manager.update_session(session)
        
        guidance = f"""
🏗️ HIERARCHICAL PLAN CREATED

🎯 ARCHITECTURAL PATTERN: Hierarchical & Iterative Planning Loop Active

📋 HIGH-LEVEL STRATEGY ({len(high_level_steps)} steps):
{chr(10).join([f"   {i+1}. {step}" for i, step in enumerate(high_level_steps)])}

🔍 CURRENT FOCUS: Step {hierarchical_plan.current_step_index + 1}
   "{high_level_steps[0] if high_level_steps else 'No steps defined'}"

📝 SUB-TASKS FOR CURRENT STEP:
{chr(10).join([f"   - {task}" for task in current_step_breakdown]) if current_step_breakdown else '   No sub-tasks defined yet'}

🔄 EXECUTION PATTERN:
1. Execute ONLY the current step's sub-tasks
2. Verify completion before proceeding
3. Move to next high-level step only after verification
4. Break down next step when current step is complete

💡 NEXT ACTION: Use 'execute_next' to begin current step execution.
"""
        
        return TaskmasterResponse(
            action="create_hierarchical_plan",
            session_id=session.id,
            hierarchical_plan_created=True,
            high_level_steps=high_level_steps,
            current_step=high_level_steps[0] if high_level_steps else None,
            current_subtasks=current_step_breakdown,
            suggested_next_actions=["execute_next"],
            completion_guidance=guidance
        )


class InitiateAdversarialReviewHandler(BaseCommandHandler):
    """Handler for initiate_adversarial_review command - Implements Complete Adversarial Review Cycle."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(
                action="initiate_adversarial_review",
                status="guidance",
                completion_guidance="🔍 GUIDANCE: No active session found. Please create a session first using 'create_session'.",
                suggested_next_actions=["create_session"]
            )
        
        # Get adversarial review parameters
        generated_content = command.data.get("generated_content", "")
        generator_agent = command.data.get("generator_agent", "tanuki-coder")
        content_type = command.data.get("content_type", "code")
        task_id = command.data.get("task_id")
        
        if not generated_content:
            guidance = """
⚔️ **ADVERSARIAL REVIEW CYCLE REQUIRED**

🎯 **ARCHITECTURAL PATTERN**: Mandatory Adversarial Loop for Quality Assurance

📋 **INITIATE ADVERSARIAL REVIEW:**
Call taskmaster again with:
```json
{
  "action": "initiate_adversarial_review",
  "generated_content": "The actual code/solution that was generated",
  "generator_agent": "tanuki-coder",
  "content_type": "code",
  "task_id": "task_id_if_available"
}
```

🔄 **ADVERSARIAL REVIEW PROCESS:**
1. **Generate**: Submit your implementation
2. **Review**: Get 3 critical improvement suggestions
3. **Test**: Verify functionality and catch bugs  
4. **Iterate**: Apply improvements (max 3 cycles)
5. **Validate**: Confirm completion with evidence

💡 **CONTENT TYPES SUPPORTED:**
- "code" - Programming implementations
- "solution" - General problem solutions
- "design" - System designs or architectures
- "plan" - Strategic or execution plans

🚨 **QUALITY ENFORCEMENT**: Complex tasks require adversarial review before completion.
"""
            
            return TaskmasterResponse(
                action="initiate_adversarial_review",
                session_id=session.id,
                review_initiated=False,
                suggested_next_actions=["initiate_adversarial_review"],
                completion_guidance=guidance
            )
        
        # Find the target task
        target_task = None
        if task_id:
            target_task = next((task for task in session.tasks if task.id == task_id), None)
        else:
            # Use current pending task
            target_task = next((task for task in session.tasks if task.status == "pending"), None)
        
        if not target_task:
            return TaskmasterResponse(
                action="initiate_adversarial_review",
                status="guidance",
                completion_guidance="🔍 GUIDANCE: No target task found. Specify task_id or ensure you have a pending task.",
                suggested_next_actions=["execute_next"]
            )
        
        # Initialize adversarial review for the task
        from .models import AdversarialReview
        adversarial_review = AdversarialReview(
            generation_phase="generated",
            generated_content=generated_content,
            generator_agent=generator_agent,
            correction_cycles=0,
            max_correction_cycles=3,
            approved=False
        )
        
        # Attach to task
        target_task.adversarial_review = adversarial_review
        
        # Generate 3 critical improvement suggestions
        review_findings = self._generate_adversarial_findings(generated_content, content_type, target_task)
        adversarial_review.review_findings = review_findings
        adversarial_review.generation_phase = "reviewed"
        
        await self.session_manager.update_session(session)
        
        guidance = f"""
⚔️ **ADVERSARIAL REVIEW INITIATED**
Task: {target_task.description}

🎯 **GENERATED CONTENT UNDER REVIEW:**
Content Type: {content_type}
Generator: {generator_agent}
Length: {len(generated_content)} characters

🔍 **CRITICAL REVIEW FINDINGS** (3 Mandatory Improvements):

{chr(10).join([f"{i+1}. **{finding['category']}**: {finding['description']}" + 
               (f"\n   💡 *Suggestion*: {finding['suggestion']}" if finding.get('suggestion') else "")
               for i, finding in enumerate(review_findings)])}

🔄 **NEXT STEPS IN ADVERSARIAL CYCLE:**
1. **Address Findings**: Apply the critical improvements above
2. **Test Implementation**: Verify functionality works correctly
3. **Record Results**: Use 'record_test_results' with actual test outcomes
4. **Iterate if Needed**: Up to {adversarial_review.max_correction_cycles} cycles allowed

💡 **COMPLETION PATH:**
- Use 'record_test_results' to document testing outcomes
- System will auto-approve if all tests pass and improvements applied
- Use 'mark_complete' only after adversarial review approval

Task ID: {target_task.id} | Review Cycle: {adversarial_review.correction_cycles + 1}/{adversarial_review.max_correction_cycles}
"""
        
        return TaskmasterResponse(
            action="initiate_adversarial_review",
            session_id=session.id,
            task_id=target_task.id,
            review_initiated=True,
            adversarial_review={
                "phase": adversarial_review.generation_phase,
                "findings": review_findings,
                "correction_cycle": adversarial_review.correction_cycles,
                "max_cycles": adversarial_review.max_correction_cycles,
                "approved": adversarial_review.approved
            },
            suggested_next_actions=["record_test_results", "record_adversarial_findings"],
            completion_guidance=guidance
        )
    
    def _generate_adversarial_findings(self, content: str, content_type: str, task: Task) -> List[Dict[str, str]]:
        """Generate 3 critical improvement suggestions based on content analysis."""
        findings = []
        content_lower = content.lower()
        
        # Analysis based on content type
        if content_type == "code":
            findings.extend(self._analyze_code_quality(content, content_lower))
        elif content_type == "solution":
            findings.extend(self._analyze_solution_quality(content, content_lower))
        elif content_type == "design":
            findings.extend(self._analyze_design_quality(content, content_lower))
        else:
            findings.extend(self._analyze_general_quality(content, content_lower))
        
        # Task-specific analysis
        findings.extend(self._analyze_task_alignment(content, task))
        
        # Ensure we have exactly 3 findings (pad if needed, trim if too many)
        while len(findings) < 3:
            findings.append({
                "category": "General Improvement",
                "description": "Consider additional testing and validation of this implementation",
                "suggestion": "Add comprehensive testing and error handling to ensure robustness"
            })
        
        return findings[:3]  # Return exactly 3 findings
    
    def _analyze_code_quality(self, content: str, content_lower: str) -> List[Dict[str, str]]:
        """Analyze code quality and suggest improvements."""
        findings = []
        
        # Error handling analysis
        if "try" not in content_lower and "except" not in content_lower:
            findings.append({
                "category": "Error Handling",
                "description": "No exception handling detected in the implementation",
                "suggestion": "Add try-catch blocks for potential failure points and provide meaningful error messages"
            })
        
        # Testing analysis
        if "test" not in content_lower and "assert" not in content_lower:
            findings.append({
                "category": "Testing",
                "description": "No testing code or assertions found",
                "suggestion": "Add unit tests or assertions to verify functionality works as expected"
            })
        
        # Documentation analysis
        if '"""' not in content and "def " in content_lower:
            findings.append({
                "category": "Documentation",
                "description": "Functions lack proper docstrings or documentation",
                "suggestion": "Add comprehensive docstrings explaining parameters, return values, and usage examples"
            })
        
        # Security analysis
        if any(risky in content_lower for risky in ["eval(", "exec(", "input(", "raw_input("]):
            findings.append({
                "category": "Security",
                "description": "Potentially unsafe operations detected",
                "suggestion": "Review and secure any user input handling or dynamic code execution"
            })
        
        return findings
    
    def _analyze_solution_quality(self, content: str, content_lower: str) -> List[Dict[str, str]]:
        """Analyze general solution quality."""
        findings = []
        
        # Completeness analysis
        if len(content.strip()) < 100:
            findings.append({
                "category": "Completeness",
                "description": "Solution appears brief and may lack detail",
                "suggestion": "Expand the solution with more comprehensive details and implementation steps"
            })
        
        # Vagueness analysis
        vague_terms = ["somehow", "maybe", "probably", "should work", "might"]
        if any(term in content_lower for term in vague_terms):
            findings.append({
                "category": "Specificity",
                "description": "Solution contains vague or uncertain language",
                "suggestion": "Replace uncertain language with specific, actionable steps and concrete details"
            })
        
        return findings
    
    def _analyze_design_quality(self, content: str, content_lower: str) -> List[Dict[str, str]]:
        """Analyze design quality."""
        findings = []
        
        # Scalability analysis
        if "scale" not in content_lower and "performance" not in content_lower:
            findings.append({
                "category": "Scalability",
                "description": "Design does not address scalability or performance considerations",
                "suggestion": "Consider how the design will handle increased load and optimize for performance"
            })
        
        # Maintainability analysis
        if "maintain" not in content_lower and "modular" not in content_lower:
            findings.append({
                "category": "Maintainability",
                "description": "Design lacks consideration for long-term maintenance",
                "suggestion": "Ensure the design is modular and easy to maintain with clear separation of concerns"
            })
        
        return findings
    
    def _analyze_general_quality(self, content: str, content_lower: str) -> List[Dict[str, str]]:
        """Analyze general content quality."""
        return [{
            "category": "General Quality",
            "description": "Content requires additional review for completeness and accuracy",
            "suggestion": "Review the content thoroughly and add more specific details and examples"
        }]
    
    def _analyze_task_alignment(self, content: str, task: Task) -> List[Dict[str, str]]:
        """Analyze alignment with task requirements."""
        findings = []
        
        # Check if content addresses task description
        task_keywords = task.description.lower().split()
        content_lower = content.lower()
        
        missing_keywords = [word for word in task_keywords if len(word) > 3 and word not in content_lower]
        if len(missing_keywords) > len(task_keywords) * 0.3:  # More than 30% keywords missing
            findings.append({
                "category": "Task Alignment",
                "description": f"Implementation may not fully address task requirements",
                "suggestion": f"Ensure the solution addresses these key aspects: {', '.join(missing_keywords[:3])}"
            })
        
        return findings


class RecordHostGroundingHandler(BaseCommandHandler):
    """Handler for record_host_grounding command - Implements Host Environment Grounding pattern."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(
                action="record_host_grounding",
                status="guidance",
                completion_guidance="🔍 GUIDANCE: No active session found. Please create a session first using 'create_session'.",
                suggested_next_actions=["create_session"]
            )
        
        # Get host grounding data
        command_executed = command.data.get("command_executed", "")
        stdout_result = command.data.get("stdout", "")
        stderr_result = command.data.get("stderr", "")
        exit_code = command.data.get("exit_code")
        if exit_code is None:
            exit_code = 0
        execution_context = command.data.get("execution_context", {})
        
        if not command_executed:
            guidance = """
🖥️ HOST ENVIRONMENT GROUNDING REQUIRED

🎯 ARCHITECTURAL PATTERN: Countering Hallucination with Host Environment Grounding

📋 RECORD REAL EXECUTION RESULTS:
Call taskmaster after EVERY tool execution with:
{
  "action": "record_host_grounding",
  "command_executed": "the actual command that was run",
  "stdout": "real stdout from the command",
  "stderr": "real stderr from the command", 
  "exit_code": 0,  // actual exit code
  "execution_context": {
    "working_directory": "/path/to/dir",
    "environment_vars": {...}
  }
}

🖥️ GROUNDING PHILOSOPHY:
- HOST ENVIRONMENT is the ultimate source of truth
- REAL stdout/stderr/exit_code prevents hallucination
- FORCED REALITY CHECK after every tool execution
- ERROR PROPAGATION ensures agents confront real-world consequences

💡 PATTERN ENFORCEMENT: Never assume tool success - always record real results.
"""
            
            return TaskmasterResponse(
                action="record_host_grounding",
                session_id=session.id,
                suggested_next_actions=["record_host_grounding"],
                completion_guidance=guidance
            )
        
        # Create or update host grounding
        from .models import HostEnvironmentGrounding
        
        # Find current task and update host grounding
        if session.tasks:
            current_task = next((task for task in session.tasks if task.status == "pending"), None)
            if current_task:
                current_phase_name = current_task.current_phase or "execution"
                current_phase = getattr(current_task, f"{current_phase_name}_phase", None)
                
                if current_phase:
                    if not current_phase.host_grounding:
                        current_phase.host_grounding = HostEnvironmentGrounding()
                    
                    # Record the command execution
                    execution_record = {
                        "command": command_executed,
                        "stdout": stdout_result,
                        "stderr": stderr_result,
                        "exit_code": exit_code,
                        "timestamp": "2025-01-27T00:00:00Z",
                        "context": execution_context
                    }
                    
                    current_phase.host_grounding.command_history.append(execution_record)
                    current_phase.host_grounding.last_stdout = stdout_result
                    current_phase.host_grounding.last_stderr = stderr_result
                    current_phase.host_grounding.last_exit_code = exit_code
                    current_phase.host_grounding.execution_context = execution_context
                    
                    # Update reality check status
                    current_phase.host_grounding.reality_check_required = exit_code != 0 or stderr_result
        
        # Update world model with real execution results
        if session.world_model:
            from .models import WorldModelEntry
            grounding_entry = WorldModelEntry(
                entry_type="tool_output",
                source="host_environment",
                content=f"Command: {command_executed}\nExit Code: {exit_code}\nStdout: {stdout_result[:200]}...\nStderr: {stderr_result[:200]}...",
                verification_status="verified",
                criticality="critical" if exit_code != 0 else "normal"
            )
            session.world_model.entries.append(grounding_entry)
            
            # Track errors in world model
            if exit_code != 0 or stderr_result:
                error_msg = f"Command failed: {command_executed} (exit {exit_code})"
                if error_msg not in session.world_model.known_errors:
                    session.world_model.known_errors.append(error_msg)
        
        await self.session_manager.update_session(session)
        
        success_indicator = "✅" if exit_code == 0 and not stderr_result else "❌"
        
        guidance = f"""
🖥️ HOST ENVIRONMENT GROUNDING RECORDED

🎯 ARCHITECTURAL PATTERN: Host Environment Grounding Active

{success_indicator} EXECUTION RESULT:
   Command: {command_executed}
   Exit Code: {exit_code}
   Stdout Length: {len(stdout_result)} chars
   Stderr Length: {len(stderr_result)} chars

🔍 REALITY CHECK STATUS:
   Success: {'Yes' if exit_code == 0 and not stderr_result else 'No'}
   Error Recorded: {'Yes' if exit_code != 0 or stderr_result else 'No'}
   World Model Updated: {'Yes' if session.world_model else 'No'}

{"⚠️ ERROR DETECTED - Agent must address real-world failure before proceeding." if exit_code != 0 or stderr_result else ""}

🔄 NEXT ACTIONS:
{"1. Analyze the error and generate a solution" if exit_code != 0 or stderr_result else "1. Continue with next tool execution"}
2. Record all subsequent tool executions with this command
3. Update world model with learnings from real execution

💡 PATTERN ENFORCEMENT: Real execution results prevent hallucination and ensure ground truth.
"""
        
        return TaskmasterResponse(
            action="record_host_grounding",
            session_id=session.id,
            host_grounding_recorded=True,
            command_executed=command_executed,
            exit_code=exit_code,
            success=exit_code == 0 and not stderr_result,
            error_detected=exit_code != 0 or bool(stderr_result),
            suggested_next_actions=["update_world_model", "execute_next"],
            completion_guidance=guidance
        )


# Additional Helper Handlers for Architectural Patterns

class UpdateWorldModelHandler(BaseCommandHandler):
    """Handler for update_world_model command - Updates the Dynamic World Model with new information."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(
                action="update_world_model",
                status="guidance",
                completion_guidance="🔍 GUIDANCE: No active session found. Please create a session first using 'create_session'.",
                suggested_next_actions=["create_session"]
            )
        
        # Get update parameters
        entry_type = command.data.get("entry_type", "tool_output")
        source = command.data.get("source", "user")
        content = command.data.get("content", "")
        file_path = command.data.get("file_path")
        verification_status = command.data.get("verification_status", "unverified")
        criticality = command.data.get("criticality", "normal")
        
        if not content:
            guidance = """
🌍 UPDATE WORLD MODEL REQUIRED

📋 PROVIDE WORLD MODEL UPDATE:
Call taskmaster with:
{
  "action": "update_world_model",
  "entry_type": "tool_output",  // or "static_analysis", "error", "state_update", "verification"
  "source": "tool_name_or_agent",
  "content": "The actual information to record",
  "file_path": "/path/to/file",  // optional
  "verification_status": "verified",  // or "unverified", "failed"
  "criticality": "normal"  // or "critical", "low"
}

💡 PATTERN ENFORCEMENT: Update world model after every tool execution to maintain ground truth.
"""
            
            return TaskmasterResponse(
                action="update_world_model",
                session_id=session.id,
                suggested_next_actions=["update_world_model"],
                completion_guidance=guidance
            )
        
        # Initialize world model if needed
        if not session.world_model:
            from .models import DynamicWorldModel
            session.world_model = DynamicWorldModel()
        
        # Add new entry
        from .models import WorldModelEntry
        new_entry = WorldModelEntry(
            entry_type=entry_type,
            source=source,
            content=content,
            file_path=file_path,
            verification_status=verification_status,
            criticality=criticality
        )
        
        session.world_model.entries.append(new_entry)
        
        # Update critical tracking
        if criticality == "critical" and file_path and file_path not in session.world_model.critical_files:
            session.world_model.critical_files.append(file_path)
        
        # Track errors
        if entry_type == "error" and content not in session.world_model.known_errors:
            session.world_model.known_errors.append(content)
        
        # Track verified outputs
        if verification_status == "verified" and content not in session.world_model.verified_outputs:
            session.world_model.verified_outputs.append(content)
        
        await self.session_manager.update_session(session)
        
        guidance = f"""
🌍 WORLD MODEL UPDATED

📝 NEW ENTRY RECORDED:
   Type: {entry_type}
   Source: {source}
   Criticality: {criticality}
   Verification: {verification_status}
   {f'File: {file_path}' if file_path else ''}

📊 WORLD MODEL STATUS:
   Total Entries: {len(session.world_model.entries)}
   Critical Files: {len(session.world_model.critical_files)}
   Known Errors: {len(session.world_model.known_errors)}
   Verified Outputs: {len(session.world_model.verified_outputs)}

💡 NEXT ACTION: Continue with tool execution and update world model after each operation.
"""
        
        return TaskmasterResponse(
            action="update_world_model",
            session_id=session.id,
            world_model_updated=True,
            entry_type=entry_type,
            source=source,
            criticality=criticality,
            total_entries=len(session.world_model.entries),
            suggested_next_actions=["execute_next", "record_host_grounding"],
            completion_guidance=guidance
        )


class RecordAdversarialFindingsHandler(BaseCommandHandler):
    """Handler for record_adversarial_findings command - Records findings from adversarial review."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(
                action="record_adversarial_findings",
                status="guidance",
                completion_guidance="🔍 GUIDANCE: No active session found. Please create a session first using 'create_session'.",
                suggested_next_actions=["create_session"]
            )
        
        findings = command.data.get("findings", [])
        reviewer_agent = command.data.get("reviewer_agent", "tanuki-code-reviewer")
        
        if not findings:
            guidance = """
⚔️ RECORD ADVERSARIAL FINDINGS

📋 PROVIDE REVIEW FINDINGS:
Call taskmaster with:
{
  "action": "record_adversarial_findings",
  "findings": [
    "Finding 1: Potential race condition in line 42",
    "Finding 2: Missing error handling for edge case",
    "Finding 3: Logic flaw in validation method"
  ],
  "reviewer_agent": "tanuki-code-reviewer"
}

💡 ADVERSARIAL PATTERN: Record all findings from peer review to improve code quality.
"""
            
            return TaskmasterResponse(
                action="record_adversarial_findings",
                session_id=session.id,
                suggested_next_actions=["record_adversarial_findings"],
                completion_guidance=guidance
            )
        
        # Find current task with adversarial review
        current_task = next((task for task in session.tasks if task.status == "pending"), None)
        if current_task:
            current_phase_name = current_task.current_phase or "execution"
            current_phase = getattr(current_task, f"{current_phase_name}_phase", None)
            
            if current_phase and current_phase.adversarial_review:
                current_phase.adversarial_review.review_findings.extend(findings)
                current_phase.adversarial_review.generation_phase = "reviewed"
        
        await self.session_manager.update_session(session)
        
        guidance = f"""
⚔️ ADVERSARIAL FINDINGS RECORDED

🔍 REVIEW FINDINGS ({len(findings)} items):
{chr(10).join([f'   - {finding}' for finding in findings])}

👤 Reviewer: {reviewer_agent}

🔄 NEXT STEPS:
1. Address each finding in the generated content
2. Use 'record_test_results' to add testing findings
3. Implement corrections based on peer feedback

💡 ADVERSARIAL PATTERN: Use these findings to improve the generated content before approval.
"""
        
        return TaskmasterResponse(
            action="record_adversarial_findings",
            session_id=session.id,
            findings_recorded=True,
            findings_count=len(findings),
            reviewer_agent=reviewer_agent,
            suggested_next_actions=["record_test_results", "initiate_adversarial_review"],
            completion_guidance=guidance
        )


class RecordTestResultsHandler(BaseCommandHandler):
    """Handler for record_test_results command - Records test results from adversarial testing."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(
                action="record_test_results",
                status="guidance",
                completion_guidance="🔍 GUIDANCE: No active session found. Please create a session first using 'create_session'.",
                suggested_next_actions=["create_session"]
            )
        
        test_results = command.data.get("test_results", [])
        tester_agent = command.data.get("tester_agent", "tanuki-tester")
        
        if not test_results:
            guidance = """
🧪 RECORD TEST RESULTS

📋 PROVIDE TEST RESULTS:
Call taskmaster with:
{
  "action": "record_test_results",
  "test_results": [
    "PASS: Unit test for happy path",
    "FAIL: Edge case with null input throws exception",
    "PASS: Integration test with mock data",
    "FAIL: Performance test exceeds timeout"
  ],
  "tester_agent": "tanuki-tester"
}

💡 TESTING PATTERN: Record all test results to validate generated content thoroughly.
"""
            
            return TaskmasterResponse(
                action="record_test_results",
                session_id=session.id,
                suggested_next_actions=["record_test_results"],
                completion_guidance=guidance
            )
        
        # Find current task with adversarial review
        current_task = next((task for task in session.tasks if task.status == "pending"), None)
        if current_task:
            current_phase_name = current_task.current_phase or "execution"
            current_phase = getattr(current_task, f"{current_phase_name}_phase", None)
            
            if current_phase and current_phase.adversarial_review:
                current_phase.adversarial_review.test_results.extend(test_results)
                current_phase.adversarial_review.generation_phase = "tested"
                
                # Check if we should approve (all tests pass and no critical findings)
                failed_tests = [result for result in test_results if result.startswith("FAIL")]
                if not failed_tests and current_phase.adversarial_review.review_findings:
                    current_phase.adversarial_review.approved = True
                    current_phase.adversarial_review.generation_phase = "approved"
        
        await self.session_manager.update_session(session)
        
        failed_tests = [result for result in test_results if result.startswith("FAIL")]
        passed_tests = [result for result in test_results if result.startswith("PASS")]
        
        guidance = f"""
🧪 TEST RESULTS RECORDED

📊 TEST SUMMARY:
   ✅ Passed: {len(passed_tests)}
   ❌ Failed: {len(failed_tests)}
   📋 Total: {len(test_results)}

👤 Tester: {tester_agent}

{'🎉 ALL TESTS PASSED - Content ready for approval!' if not failed_tests else '⚠️ FAILED TESTS DETECTED - Corrections needed before approval.'}

🔄 NEXT STEPS:
{'1. Content is approved and ready to use' if not failed_tests else '1. Fix failing tests and re-run adversarial review'}
2. Continue with next task phase or completion

💡 TESTING PATTERN: All tests must pass for adversarial approval.
"""
        
        return TaskmasterResponse(
            action="record_test_results",
            session_id=session.id,
            test_results_recorded=True,
            tests_passed=len(passed_tests),
            tests_failed=len(failed_tests),
            all_tests_passed=len(failed_tests) == 0,
            tester_agent=tester_agent,
            suggested_next_actions=["mark_complete" if not failed_tests else "initiate_adversarial_review"],
            completion_guidance=guidance
        )


class StaticAnalysisHandler(BaseCommandHandler):
    """Handler for static_analysis command - Performs static analysis to populate world model."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(
                action="static_analysis",
                status="guidance",
                completion_guidance="🔍 GUIDANCE: No active session found. Please create a session first using 'create_session'.",
                suggested_next_actions=["create_session"]
            )
        
        target_files = command.data.get("target_files", [])
        analysis_type = command.data.get("analysis_type", "codebase_mapping")
        scope = command.data.get("scope", "current_task")
        
        if not target_files:
            guidance = """
🔍 STATIC ANALYSIS REQUIRED

📋 INITIATE STATIC ANALYSIS:
Call taskmaster with:
{
  "action": "static_analysis",
  "target_files": [
    "/path/to/critical/file1.py",
    "/path/to/critical/file2.py"
  ],
  "analysis_type": "codebase_mapping",  // or "dependency_analysis", "api_mapping"
  "scope": "current_task"  // or "full_system", "module_specific"
}

🎯 STATIC ANALYSIS PATTERN: Map critical codebase components before execution to prevent architectural blindness.
"""
            
            return TaskmasterResponse(
                action="static_analysis",
                session_id=session.id,
                suggested_next_actions=["static_analysis"],
                completion_guidance=guidance
            )
        
        # Initialize world model if needed
        if not session.world_model:
            from .models import DynamicWorldModel
            session.world_model = DynamicWorldModel()
        
        # Add static analysis entries
        from .models import WorldModelEntry
        for file_path in target_files:
            analysis_entry = WorldModelEntry(
                entry_type="static_analysis",
                source="tanuki-architect",
                content=f"Static analysis of {file_path} - {analysis_type} for {scope}",
                file_path=file_path,
                verification_status="unverified",
                criticality="critical"
            )
            session.world_model.entries.append(analysis_entry)
            
            # Add to critical files
            if file_path not in session.world_model.critical_files:
                session.world_model.critical_files.append(file_path)
        
        # Mark static analysis as complete
        session.world_model.static_analysis_complete = True
        session.world_model.current_state_summary = f"Static analysis completed for {len(target_files)} files using {analysis_type}"
        
        await self.session_manager.update_session(session)
        
        guidance = f"""
🔍 STATIC ANALYSIS COMPLETED

📊 ANALYSIS SUMMARY:
   Type: {analysis_type}
   Scope: {scope}
   Files Analyzed: {len(target_files)}
   Critical Files Tracked: {len(session.world_model.critical_files)}

📁 ANALYZED FILES:
{chr(10).join([f'   - {file}' for file in target_files])}

🌍 WORLD MODEL STATUS:
   Static Analysis: Complete
   Total Entries: {len(session.world_model.entries)}
   State Summary: {session.world_model.current_state_summary}

🔄 NEXT STEPS:
1. Use analyzed information to guide tool execution
2. Update world model with real tool outputs
3. Reference critical files during execution

💡 ARCHITECTURAL PATTERN: Static analysis provides foundation for informed execution decisions.
"""
        
        return TaskmasterResponse(
            action="static_analysis",
            session_id=session.id,
            static_analysis_complete=True,
            files_analyzed=target_files,
            analysis_type=analysis_type,
            scope=scope,
            critical_files_count=len(session.world_model.critical_files),
            suggested_next_actions=["execute_next", "update_world_model"],
            completion_guidance=guidance
        )


class AdvanceHierarchicalStepHandler(BaseCommandHandler):
    """Handler for advance_hierarchical_step command - Advances to next step in hierarchical plan."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(
                action="advance_hierarchical_step",
                status="guidance",
                completion_guidance="🔍 GUIDANCE: No active session found. Please create a session first using 'create_session'.",
                suggested_next_actions=["create_session"]
            )
        
        if not session.current_hierarchical_plan:
            return TaskmasterResponse(
                action="advance_hierarchical_step",
                status="guidance",
                completion_guidance="🔍 GUIDANCE: No hierarchical plan found. Use 'create_hierarchical_plan' first.",
                suggested_next_actions=["create_hierarchical_plan"]
            )
        
        plan = session.current_hierarchical_plan
        current_step_breakdown = command.data.get("current_step_breakdown", [])
        verification_complete = command.data.get("verification_complete", False)
        
        if not verification_complete:
            guidance = f"""
🏗️ HIERARCHICAL STEP VERIFICATION REQUIRED

🔍 CURRENT STEP: {plan.current_step_index + 1} of {len(plan.high_level_steps)}
   "{plan.high_level_steps[plan.current_step_index] if plan.current_step_index < len(plan.high_level_steps) else 'Unknown step'}"

⚠️ VERIFICATION NEEDED:
Before advancing to the next step, verify that the current step is completely finished.

📋 CONFIRM STEP COMPLETION:
Call taskmaster with:
{
  "action": "advance_hierarchical_step",
  "verification_complete": true,
  "current_step_breakdown": [
    "Sub-task 1 for NEXT step",
    "Sub-task 2 for NEXT step"
  ]
}

💡 HIERARCHICAL PATTERN: Each step must be verified before advancing to maintain known good state.
"""
            
            return TaskmasterResponse(
                action="advance_hierarchical_step",
                session_id=session.id,
                verification_required=True,
                current_step=plan.current_step_index + 1,
                current_step_description=plan.high_level_steps[plan.current_step_index] if plan.current_step_index < len(plan.high_level_steps) else None,
                suggested_next_actions=["advance_hierarchical_step"],
                completion_guidance=guidance
            )
        
        # Advance to next step
        if plan.current_step_index + 1 < len(plan.high_level_steps):
            plan.current_step_index += 1
            plan.current_step_breakdown = current_step_breakdown
            plan.current_subtask_index = 0
            
            await self.session_manager.update_session(session)
            
            guidance = f"""
🏗️ HIERARCHICAL STEP ADVANCED

✅ COMPLETED STEP: {plan.current_step_index} of {len(plan.high_level_steps)}

🔍 NEW CURRENT STEP: {plan.current_step_index + 1} of {len(plan.high_level_steps)}
   "{plan.high_level_steps[plan.current_step_index]}"

📝 SUB-TASKS FOR NEW STEP:
{chr(10).join([f'   - {task}' for task in current_step_breakdown]) if current_step_breakdown else '   No sub-tasks defined yet'}

🔄 EXECUTION PATTERN:
1. Execute ONLY the current step's sub-tasks
2. Verify completion before proceeding
3. Use 'advance_hierarchical_step' when step is complete

💡 NEXT ACTION: Use 'execute_next' to begin new step execution.
"""
            
            return TaskmasterResponse(
                action="advance_hierarchical_step",
                session_id=session.id,
                step_advanced=True,
                current_step=plan.current_step_index + 1,
                current_step_description=plan.high_level_steps[plan.current_step_index],
                current_subtasks=current_step_breakdown,
                remaining_steps=len(plan.high_level_steps) - plan.current_step_index - 1,
                suggested_next_actions=["execute_next"],
                completion_guidance=guidance
            )
        else:
            # All steps completed
            guidance = f"""
🎉 HIERARCHICAL PLAN COMPLETED!

✅ ALL STEPS FINISHED: {len(plan.high_level_steps)} steps completed

📋 COMPLETED STRATEGY:
{chr(10).join([f'   ✅ {i+1}. {step}' for i, step in enumerate(plan.high_level_steps)])}

🏗️ HIERARCHICAL PATTERN SUCCESS:
- Each step was verified before advancing
- System maintained known good state throughout
- Iterative approach prevented brittle planning failures

💡 NEXT ACTIONS: Use 'mark_complete' to finish the overall task or create new session.
"""
            
            return TaskmasterResponse(
                action="advance_hierarchical_step",
                session_id=session.id,
                plan_completed=True,
                total_steps_completed=len(plan.high_level_steps),
                suggested_next_actions=["mark_complete", "create_session"],
                completion_guidance=guidance
            ) 


class DiscoverCapabilitiesHandler(BaseCommandHandler):
    """Handler for discover_capabilities command - helps LLMs find available tools."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        """Discover and suggest available capabilities for the LLM."""
        
        # Try to detect available tools from various sources
        discovery_results = {
            "builtin_tools": self._discover_builtin_tools(),
            "mcp_tools": self._discover_mcp_tools(),
            "memory_tools": self._discover_memory_tools(),
            "user_resources": self._discover_user_resources()
        }
        
        # Generate suggested declaration
        suggested_declaration = self._generate_suggested_declaration(discovery_results)
        
        guidance = f"""
🔍 **CAPABILITY DISCOVERY RESULTS**

{self._format_discovery_results(discovery_results)}

📝 **SUGGESTED DECLARE_CAPABILITIES CALL:**
```
{suggested_declaration}
```

💡 **NEXT STEPS:**
1. Review the discovered capabilities above
2. Modify the suggested declaration as needed
3. Call `declare_capabilities` with your tools
4. Then proceed with `create_tasklist`

🚨 **IMPORTANT**: This is discovery only - you still need to call `declare_capabilities` to actually register your tools!
"""
        
        return TaskmasterResponse(
            action="discover_capabilities",
            discovery_results=discovery_results,
            suggested_declaration=suggested_declaration,
            completion_guidance=guidance,
            suggested_next_actions=["declare_capabilities"]
        )
    
    def _discover_builtin_tools(self) -> list:
        """Discover common built-in tools available to LLMs."""
        return [
            {
                "name": "codebase_search",
                "description": "Semantic search tool to find relevant code snippets from the codebase based on natural language queries"
            },
            {
                "name": "read_file", 
                "description": "Read contents of files with line range support to examine existing code and documentation"
            },
            {
                "name": "edit_file",
                "description": "Create new files or edit existing files with precise code changes and context preservation"
            },
            {
                "name": "search_replace",
                "description": "Search and replace specific text patterns in files for targeted edits"
            },
            {
                "name": "grep_search",
                "description": "Fast regex-based text search across files to find exact patterns and symbols"
            },
            {
                "name": "list_dir",
                "description": "List directory contents to explore file structure and organization"
            },
            {
                "name": "file_search",
                "description": "Fuzzy file path search to locate files when partial names are known"
            },
            {
                "name": "run_terminal_cmd",
                "description": "Execute terminal commands for testing, building, and system operations"
            },
            {
                "name": "delete_file",
                "description": "Remove files when cleanup or restructuring is needed"
            }
        ]
    
    def _discover_mcp_tools(self) -> list:
        """Attempt to discover available MCP tools."""
        discovered_tools = []
        
        # Try to detect from function names in the environment
        try:
            import inspect
            current_frame = inspect.currentframe()
            if current_frame and current_frame.f_back:
                # Look several frames back to find the caller's environment
                frame = current_frame
                for _ in range(5):  # Look up to 5 frames back
                    if frame.f_back:
                        frame = frame.f_back
                        caller_globals = frame.f_globals
                        
                        # Look for MCP tool functions
                        for name, obj in caller_globals.items():
                            if (callable(obj) and 
                                hasattr(obj, '__name__') and 
                                obj.__name__.startswith('mcp_')):
                                
                                # Extract server name and tool name
                                full_name = obj.__name__
                                parts = full_name.split('_')
                                if len(parts) >= 3:
                                    server_name = '_'.join(parts[:2])  # mcp_servername
                                    tool_name = '_'.join(parts[2:])    # toolname
                                    
                                    discovered_tools.append({
                                        "name": tool_name,
                                        "description": f"MCP tool from {server_name} server - please provide complete description",
                                        "server_name": server_name,
                                        "detected_function": full_name
                                    })
                    else:
                        break
        except Exception:
            pass
        
        # If no tools detected, provide common examples
        if not discovered_tools:
            discovered_tools = [
                {
                    "name": "memory_palace_query",
                    "description": "Query stored knowledge and context from memory palace",
                    "server_name": "mcp_memory_palace",
                    "status": "example - check if available"
                },
                {
                    "name": "sequential_thinking",
                    "description": "Advanced problem-solving with structured thinking steps",
                    "server_name": "mcp_server-sequential-thinking", 
                    "status": "example - check if available"
                },
                {
                    "name": "context7_get_docs",
                    "description": "Fetch up-to-date documentation for libraries and frameworks",
                    "server_name": "mcp_context7-mcp",
                    "status": "example - check if available"
                }
            ]
        
        return discovered_tools
    
    def _discover_memory_tools(self) -> list:
        """Discover memory-related tools."""
        return [
            {
                "name": "memory_palace",
                "description": "Advanced memory management system for storing and retrieving context",
                "type": "memory_system",
                "status": "check if mcp_memory_palace server is available"
            }
        ]
    
    def _discover_user_resources(self) -> list:
        """Discover user resources that might be available."""
        return [
            {
                "name": "project_documentation",
                "description": "Project-specific documentation and specifications",
                "type": "documentation",
                "status": "declare if available"
            },
            {
                "name": "existing_codebase",
                "description": "Current codebase and implementation files",
                "type": "codebase",
                "status": "declare if relevant"
            }
        ]
    
    def _format_discovery_results(self, results: dict) -> str:
        """Format discovery results for display."""
        output = []
        
        for category, tools in results.items():
            if tools:
                output.append(f"\n🛠️ **{category.upper().replace('_', ' ')}** ({len(tools)} found):")
                for tool in tools:
                    name = tool.get('name', 'unknown')
                    desc = tool.get('description', 'No description')
                    status = tool.get('status', 'detected')
                    output.append(f"  - {name}: {desc}")
                    if status != 'detected':
                        output.append(f"    Status: {status}")
        
        return '\n'.join(output)
    
    def _generate_suggested_declaration(self, results: dict) -> str:
        """Generate a suggested declare_capabilities call."""
        declaration_parts = []
        
        # Add builtin tools
        if results['builtin_tools']:
            builtin_str = ',\n    '.join([
                f'{{"name": "{tool["name"]}", "description": "{tool["description"]}"}}'
                for tool in results['builtin_tools']
            ])
            declaration_parts.append(f'"builtin_tools": [\n    {builtin_str}\n  ]')
        
        # Add MCP tools
        if results['mcp_tools']:
            mcp_str = ',\n    '.join([
                f'{{"name": "{tool["name"]}", "description": "{tool["description"]}", "server_name": "{tool["server_name"]}"}}'
                for tool in results['mcp_tools']
            ])
            declaration_parts.append(f'"mcp_tools": [\n    {mcp_str}\n  ]')
        
        # Add user resources
        if results['user_resources']:
            resources_str = ',\n    '.join([
                f'{{"name": "{tool["name"]}", "description": "{tool["description"]}", "type": "{tool["type"]}"}}'
                for tool in results['user_resources']
            ])
            declaration_parts.append(f'"user_resources": [\n    {resources_str}\n  ]')
        
        return f'{{\n  "action": "declare_capabilities",\n  {",\n  ".join(declaration_parts)}\n}}'


class CreateTasklistHandler(BaseCommandHandler):
    """Handler for create_tasklist command with enhanced LLM guidelines."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(
                action="create_tasklist",
                status="guidance",
                completion_guidance="🔍 GUIDANCE: No active session found. Please create a session first using 'create_session'.",
                suggested_next_actions=["create_session"]
            )
        
        # Get tasklist from either enhanced_tasklist or tasklist field
        raw_tasklist = command.data.get("enhanced_tasklist", command.tasklist or [])
        
        # Enhanced LLM guidelines for tasklist creation
        if not raw_tasklist:
            return self._provide_enhanced_tasklist_guidelines(session)
        
        # Validate and enhance tasklist with mandatory structure
        enhanced_tasklist, validation_issues = self._validate_and_enhance_tasklist(raw_tasklist)
        
        # Convert to Task objects and store in session
        tasks = []
        for i, task_data in enumerate(enhanced_tasklist):
            # Create ArchitecturalTaskPhase objects with streamlined phases
            planning_phase = self._create_phase("planning", task_data.get('planning_phase', {}))
            execution_phase = self._create_phase("execution", task_data.get('execution_phase', {}))
            # Validation phase is optional in streamlined flow
            validation_phase = None
            if task_data.get('validation_phase'):
                validation_phase = self._create_phase("validation", task_data.get('validation_phase', {}))
            
            # Assess task complexity
            complexity = self._assess_task_complexity(task_data)
            
            # Create task with enhanced structure
            task = Task(
                description=task_data.get("description", f"Task {i+1}"),
                status="pending",
                current_phase="planning",  # Always start with planning
                planning_phase=planning_phase,
                execution_phase=execution_phase,
                validation_phase=validation_phase,
                complexity_level=complexity,
                requires_adversarial_review=complexity in ["complex", "architectural"],
                initial_tool_thoughts=InitialToolThoughts(**task_data['initial_tool_thoughts']) if task_data.get('initial_tool_thoughts') else None
            )
            tasks.append(task)
        
        session.tasks = tasks
        await self.session_manager.update_session(session)
        
        # Provide comprehensive guidance with validation feedback
        guidance = self._build_tasklist_completion_guidance(tasks, validation_issues)
        
        return TaskmasterResponse(
            action="create_tasklist",
            session_id=session.id,
            tasklist_created=True,
            task_count=len(tasks),
            validation_issues=validation_issues,
            tasks=[{
                "id": task.id,
                "description": task.description,
                "complexity_level": task.complexity_level,
                "requires_adversarial_review": task.requires_adversarial_review,
                "planning_phase": task.planning_phase.dict() if task.planning_phase else None,
                "execution_phase": task.execution_phase.dict() if task.execution_phase else None,
                "validation_phase": task.validation_phase.dict() if task.validation_phase else None,
                "status": task.status
            } for task in tasks],
            suggested_next_actions=["map_capabilities"],
            completion_guidance=guidance
        )
    
    def _provide_enhanced_tasklist_guidelines(self, session) -> TaskmasterResponse:
        """Provide comprehensive LLM guidelines for tasklist creation."""
        
        # Check what capabilities are available to inform guidance
        has_capabilities = (session.capabilities.built_in_tools or 
                          session.capabilities.mcp_tools or 
                          session.capabilities.memory_tools)
        
        # Analyze memory tools for memory gate guidance
        memory_tools_analysis = self._analyze_memory_tools(session.capabilities.memory_tools)
        
        capabilities_context = ""
        if has_capabilities:
            capabilities_context = f"""
🛠️ YOUR AVAILABLE CAPABILITIES:
Built-in Tools: {len(session.capabilities.built_in_tools)}
MCP Tools: {len(session.capabilities.mcp_tools)}  
Memory Tools: {len(session.capabilities.memory_tools)}
{memory_tools_analysis['summary'] if memory_tools_analysis else ''}
"""
        else:
            capabilities_context = "⚠️ No capabilities declared yet - consider declaring them first for better task planning."
        
        guidance = f"""
📋 **ENHANCED TASKLIST CREATION GUIDELINES**

{capabilities_context}

🎯 **MANDATORY TASK STRUCTURE**
Every task MUST follow the plan→execute→scan→review→validate cycle:

**Required Format:**
```json
{{
  "tasklist": [
    {{
      "description": "Clear, specific task description",
      "initial_tool_thoughts": {{
        "planning_tools_needed": ["tool1", "tool2"],
        "execution_tools_needed": ["tool3", "tool4"],
        "validation_tools_needed": ["tool1"],
        "reasoning": "Why these tools are needed for this specific task"
      }},
      "planning_phase": {{
        "description": "What planning is needed for this task",
        "steps": ["Analyze requirements", "Create execution plan", "Identify risks"],
        "phase_guidance": "Specific planning approach for this task"
      }},
      "execution_phase": {{
        "description": "How this task will be executed",
        "steps": ["Step 1", "Step 2", "Step 3"],
        "phase_guidance": "Key execution considerations",
        "requires_adversarial_review": true
      }},
      "validation_phase": {{
        "description": "How to validate task completion",
        "steps": ["Check output quality", "Verify requirements met", "Test functionality"],
        "phase_guidance": "Validation criteria and success metrics"
      }}
    }}
  ]
}}
```

🚨 **ANTI-HALLUCINATION REQUIREMENTS**
1. **Specific Descriptions**: No vague tasks like "implement feature" - be specific
2. **Tool Thinking**: Always include initial_tool_thoughts with reasoning
3. **Phase Details**: Each phase must have clear steps and guidance
4. **Validation Criteria**: Specify exactly how completion will be verified

🧠 **MEMORY GATE PATTERNS** (Apply if memory tools available)
{memory_tools_analysis.get('gate_patterns', '') if memory_tools_analysis else ''}

🔄 **COMPLEXITY ASSESSMENT**
- **Simple**: Single-step tasks, no code generation
- **Complex**: Multi-step tasks, code generation, file modifications
- **Architectural**: System-wide changes, multiple components

💡 **BEST PRACTICES**
- Break large tasks into smaller, focused tasks
- Include error handling and rollback considerations
- Specify exact validation criteria (console output, file existence, etc.)
- Consider dependencies between tasks
- Use memory gates to build and maintain mental models throughout execution

Create your tasklist following this structure for optimal LLM guidance and execution tracking.
"""
        
        return TaskmasterResponse(
            action="create_tasklist",
            session_id=session.id,
            tasklist_created=False,
            guidelines_provided=True,
            suggested_next_actions=["create_tasklist"],
            completion_guidance=guidance
        )
    
    def _validate_and_enhance_tasklist(self, raw_tasklist):
        """Validate tasklist structure and enhance with defaults."""
        enhanced_tasks = []
        validation_issues = []
        
        for i, task in enumerate(raw_tasklist):
            if not isinstance(task, dict):
                validation_issues.append(f"Task {i+1}: Must be a dictionary")
                continue
            
            # Validate required description
            if not task.get("description"):
                validation_issues.append(f"Task {i+1}: Missing description")
                task["description"] = f"Task {i+1} - Please provide description"
            
            # Ensure all phases exist with defaults
            if not task.get("planning_phase"):
                task["planning_phase"] = {
                    "description": f"Plan the execution of: {task.get('description', 'this task')}",
                    "steps": ["Analyze requirements", "Create execution plan"],
                    "phase_guidance": "Focus on understanding requirements and planning approach"
                }
                validation_issues.append(f"Task {i+1}: Added default planning phase")
            
            if not task.get("execution_phase"):
                task["execution_phase"] = {
                    "description": f"Execute: {task.get('description', 'this task')}",
                    "steps": ["Follow execution plan", "Implement solution"],
                    "phase_guidance": "Focus on careful implementation and testing"
                }
                validation_issues.append(f"Task {i+1}: Added default execution phase")
            
            if not task.get("validation_phase"):
                task["validation_phase"] = {
                    "description": f"Validate completion of: {task.get('description', 'this task')}",
                    "steps": ["Verify output", "Check requirements met"],
                    "phase_guidance": "Ensure task is truly complete with evidence"
                }
                validation_issues.append(f"Task {i+1}: Added default validation phase")
            
            # Add initial tool thoughts if missing
            if not task.get("initial_tool_thoughts"):
                task["initial_tool_thoughts"] = {
                    "planning_tools_needed": [],
                    "execution_tools_needed": [],
                    "validation_tools_needed": [],
                    "reasoning": "No initial tool thoughts provided - consider which tools you'll need"
                }
                validation_issues.append(f"Task {i+1}: Added default tool thoughts")
            
            enhanced_tasks.append(task)
        
        return enhanced_tasks, validation_issues
    
    def _create_phase(self, phase_name, phase_data):
        """Create an ArchitecturalTaskPhase with defaults."""
        from .models import ArchitecturalTaskPhase
        
        defaults = {
            "phase_name": phase_name,
            "description": phase_data.get("description", f"{phase_name.title()} phase"),
            "steps": phase_data.get("steps", []),
            "phase_guidance": phase_data.get("phase_guidance", ""),
            "requires_adversarial_review": phase_data.get("requires_adversarial_review", phase_name == "execution")
        }
        
        return ArchitecturalTaskPhase(**defaults)
    
    def _assess_task_complexity(self, task_data):
        """Assess task complexity based on description and structure."""
        description = task_data.get("description", "").lower()
        
        # Architectural complexity indicators
        if any(word in description for word in ["system", "architecture", "framework", "multiple", "integration"]):
            return "architectural"
        
        # Complex task indicators
        if any(word in description for word in ["implement", "create", "build", "develop", "code", "file", "database"]):
            return "complex"
        
        # Default to simple
        return "simple"
    
    def _build_tasklist_completion_guidance(self, tasks, validation_issues):
        """Build comprehensive guidance for tasklist completion."""
        
        # Analyze task composition
        complexity_counts = {}
        for task in tasks:
            complexity_counts[task.complexity_level] = complexity_counts.get(task.complexity_level, 0) + 1
        
        adversarial_tasks = len([t for t in tasks if t.requires_adversarial_review])
        
        guidance = f"""
**STREAMLINED TASKLIST CREATED** - {len(tasks)} tasks with enhanced structure

**TASK ANALYSIS:**
- Simple tasks: {complexity_counts.get('simple', 0)}
- Complex tasks: {complexity_counts.get('complex', 0)}
- Architectural tasks: {complexity_counts.get('architectural', 0)}
- Requiring adversarial review: {adversarial_tasks}

**STREAMLINED WORKFLOW:**
Each task will follow: PLAN -> EXECUTE -> COMPLETE
- Planning: Analyze requirements and create execution plan with placeholder guidance.
- Execution: Implement with tool guidance and enhanced placeholder guardrails.
- Completion: Direct completion with evidence collection.

**PLACEHOLDER GUARDRAILS:**
- Context-aware guidance prevents lazy implementations.
- Task complexity determines appropriate placeholder usage.
- Clear guidelines for when placeholders are acceptable vs discouraged.
- Reality checking against actual execution results.
"""
        
        if validation_issues:
            guidance += f"""
**VALIDATION ISSUES RESOLVED:**
{chr(10).join([f"- {issue}" for issue in validation_issues[:5]])}
{"- ... and more" if len(validation_issues) > 5 else ""}
"""
        
        guidance += """
**NEXT STEP:** Use 'map_capabilities' to assign your declared tools to specific task phases.

This streamlined structure ensures efficient task execution with enhanced placeholder guardrails.
"""
        
        return guidance
    
    def _analyze_memory_tools(self, memory_tools):
        """Analyze available memory tools and generate memory gate patterns."""
        if not memory_tools:
            return None
        
        # Categorize memory tools by type
        crud_tools = []
        retrieval_tools = []
        context_tools = []
        
        for tool in memory_tools:
            tool_type = tool.type.lower()
            if any(crud_op in tool.name.lower() for crud_op in ['add', 'create', 'update', 'delete', 'store']):
                crud_tools.append(tool)
            elif any(retr_op in tool.name.lower() for retr_op in ['search', 'query', 'retrieve', 'recall', 'find']):
                retrieval_tools.append(tool)
            elif any(ctx_op in tool.name.lower() for ctx_op in ['context', 'window', 'scope']):
                context_tools.append(tool)
            else:
                # Default categorization based on type
                if 'database' in tool_type or 'storage' in tool_type:
                    crud_tools.append(tool)
                elif 'search' in tool_type or 'retrieval' in tool_type:
                    retrieval_tools.append(tool)
                else:
                    context_tools.append(tool)
        
        # Generate memory gate patterns
        gate_patterns = self._generate_memory_gate_patterns(crud_tools, retrieval_tools, context_tools)
        
        # Create summary
        summary = f"""
🧠 **MEMORY TOOLS DETECTED:**
- CRUD Operations: {len(crud_tools)} tools (store/update memories)
- Retrieval Operations: {len(retrieval_tools)} tools (access existing memories)  
- Context Management: {len(context_tools)} tools (manage memory scope)
"""
        
        return {
            'summary': summary,
            'gate_patterns': gate_patterns,
            'crud_tools': crud_tools,
            'retrieval_tools': retrieval_tools,
            'context_tools': context_tools
        }
    
    def _generate_memory_gate_patterns(self, crud_tools, retrieval_tools, context_tools):
        """Generate specific memory gate patterns based on available tools."""
        patterns = []
        
        if retrieval_tools and crud_tools:
            retrieval_names = [tool.name for tool in retrieval_tools]
            crud_names = [tool.name for tool in crud_tools]
            patterns.append(f"""
**MEMORY REFLECT → EXECUTE → MEMORY UPDATE PATTERN:**
1. **Start with Memory Retrieval** (Planning Phase):
   - Use your retrieval tools ({', '.join(retrieval_names)}) at task beginning
   - Access existing knowledge about the domain/codebase
   - Build initial mental model from stored memories
   
2. **Execute with Context** (Execution Phase):
   - Apply retrieved knowledge during task execution
   - Note new information discovered during execution
   - Track differences from existing mental model
   
3. **Update Mental Model** (Validation Phase):
   - Use your storage/update tools ({', '.join(crud_names)}) to store new learnings
   - Record insights, patterns, or changes discovered
   - Maintain cumulative knowledge for future tasks""")
        
        if retrieval_tools:
            retrieval_names = [tool.name for tool in retrieval_tools]
            patterns.append(f"""
**MEMORY-GUIDED EXECUTION:**
- Begin each task with memory retrieval ({', '.join(retrieval_names)}) to access relevant context
- Use your retrieval tools to avoid repeating previous mistakes
- Leverage stored patterns and solutions from past experiences""")
        
        if crud_tools:
            crud_names = [tool.name for tool in crud_tools]
            patterns.append(f"""
**PROGRESSIVE LEARNING:**
- Store new insights immediately when discovered using ({', '.join(crud_names)})
- Update existing memories when information changes
- Build cumulative knowledge base across task execution""")
        
        if context_tools:
            patterns.append("""
**CONTEXT SCOPING:**
- Manage memory scope (session vs global vs project)
- Maintain appropriate context boundaries
- Preserve relevant context across task transitions""")
        
        if not patterns:
            patterns.append("""
**BASIC MEMORY INTEGRATION:**
- Integrate memory tools into planning and validation phases
- Use memory capabilities to enhance task execution context
- Build mental models appropriate to your memory tool capabilities""")
        
        return '\n'.join(patterns)
