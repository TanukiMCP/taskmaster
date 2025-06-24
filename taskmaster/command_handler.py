from typing import Dict, Any, Optional, List
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from .models import Session, Task, BuiltInTool, MCPTool, UserResource, EnvironmentCapabilities, TaskPhase, InitialToolThoughts, ToolAssignment
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
        
        guidance = """
🚀 Session created! NEXT STEP: Use 'declare_capabilities' action.

💡 GUIDANCE: Declare your available tools and resources:
- builtin_tools: Your core environment tools (file operations, search, etc.)
- mcp_tools: Available MCP server tools  
- user_resources: Available docs, codebases, APIs

Each capability needs: name and a complete description (what it is, does, and how to use it)

After declaring capabilities, you'll create tasks and then map which tools to use for each task phase.
"""
        
        return TaskmasterResponse(
            action="create_session",
            session_id=session.id,
            session_name=getattr(session, 'session_name', None),
            suggested_next_actions=["declare_capabilities"],
            completion_guidance=guidance
        )


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
        
        # Collect guidance instead of errors
        guidance_messages = []
        guidance_messages.extend(self._provide_capability_guidance(command.builtin_tools, "builtin_tools"))
        guidance_messages.extend(self._provide_capability_guidance(command.mcp_tools, "mcp_tools"))
        guidance_messages.extend(self._provide_capability_guidance(command.user_resources, "user_resources"))
        
        # Always proceed - provide guidance but don't block
        if not enhanced_builtin and not enhanced_mcp and not enhanced_resources:
            guidance_messages.append("💡 Consider declaring at least one capability category for better task guidance")
        
        # Store capabilities in session using the correct model structure
        session.capabilities.built_in_tools = [BuiltInTool(**tool) for tool in enhanced_builtin]
        session.capabilities.mcp_tools = [MCPTool(**tool) for tool in enhanced_mcp]
        session.capabilities.user_resources = [UserResource(**resource) for resource in enhanced_resources]
        
        await self.session_manager.update_session(session)
        
        guidance = """
✅ Capabilities declared! NEXT STEP: Use 'create_tasklist' action.

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
                "resources": [resource.dict() for resource in session.capabilities.user_resources]
            },
            capabilities_declared={
                "builtin_tools": len(session.capabilities.built_in_tools),
                "mcp_tools": len(session.capabilities.mcp_tools),
                "user_resources": len(session.capabilities.user_resources)
            },
            suggested_next_actions=["create_tasklist"],
            completion_guidance=guidance
        )


class CreateTasklistHandler(BaseCommandHandler):
    """Handler for create_tasklist command."""
    
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
        
        # Validate and enhance tasklist
        enhanced_tasklist = validate_tasklist(raw_tasklist)
        
        # Collect guidance messages
        guidance_messages = []
        if not raw_tasklist:
            guidance_messages.append("💡 Consider providing a comprehensive tasklist with clear task descriptions")
        
        # Convert to Task objects and store in session
        tasks = []
        for i, task_data in enumerate(enhanced_tasklist):
            # Create ArchitecturalTaskPhase objects with proper phase_name
            planning_phase = None
            if task_data.get('planning_phase'):
                phase_data = task_data['planning_phase'].copy()
                phase_data['phase_name'] = 'planning'
                from .models import ArchitecturalTaskPhase
                planning_phase = ArchitecturalTaskPhase(**phase_data)
            
            execution_phase = None
            if task_data.get('execution_phase'):
                phase_data = task_data['execution_phase'].copy()
                phase_data['phase_name'] = 'execution'
                from .models import ArchitecturalTaskPhase
                execution_phase = ArchitecturalTaskPhase(**phase_data)
            
            validation_phase = None
            if task_data.get('validation_phase'):
                phase_data = task_data['validation_phase'].copy()
                phase_data['phase_name'] = 'validation'
                from .models import ArchitecturalTaskPhase
                validation_phase = ArchitecturalTaskPhase(**phase_data)
            
            # Let the model generate the UUID
            task = Task(
                description=task_data.get("description", f"Task {i+1}"),
                status="pending",
                planning_phase=planning_phase,
                execution_phase=execution_phase,
                validation_phase=validation_phase,
                # Enhanced: Capture initial tool thinking
                initial_tool_thoughts=InitialToolThoughts(**task_data['initial_tool_thoughts']) if task_data.get('initial_tool_thoughts') else None
            )
            tasks.append(task)
        
        session.tasks = tasks
        await self.session_manager.update_session(session)
        
        # Enhanced guidance that mentions tool thinking
        has_tool_thoughts = any(task.initial_tool_thoughts for task in tasks)
        
        guidance = f"""
✅ Tasklist created with {len(tasks)} tasks! NEXT STEP: Use 'map_capabilities' action.

💡 GUIDANCE: Your tasklist is ready for capability mapping:
- {len(tasks)} tasks defined with phase structure
- {'Initial tool thoughts captured' if has_tool_thoughts else 'Consider adding initial_tool_thoughts to tasks for better mapping guidance'}
- Now you need to assign your declared tools to specific task phases with detailed context
- This ensures you actually use the capabilities you declared with clear guidance

💡 PRO TIP: For better mapping, include 'initial_tool_thoughts' in your tasks:
{{
  "description": "Your task description",
  "initial_tool_thoughts": {{
    "planning_tools_needed": ["tool1", "tool2"],
    "execution_tools_needed": ["tool3", "tool4"], 
    "validation_tools_needed": ["tool1"],
    "reasoning": "Why you think these tools will be needed"
  }},
  "planning_phase": {{ "description": "Planning phase description" }},
  "execution_phase": {{ "description": "Execution phase description" }},
  "validation_phase": {{ "description": "Validation phase description" }}
}}

Use 'map_capabilities' to assign tools to each task phase with rich context (why, how, expected outcomes).
"""
        
        if guidance_messages:
            guidance += "\n\n🔍 TASKLIST GUIDANCE:\n" + "\n".join(guidance_messages)
        
        return TaskmasterResponse(
            action="create_tasklist",
            session_id=session.id,
            tasklist_created=True,
            task_count=len(tasks),
            tasks=[{
                "id": task.id,
                "description": task.description,
                "planning_phase": task.planning_phase.dict() if task.planning_phase else None,
                "execution_phase": task.execution_phase.dict() if task.execution_phase else None,
                "validation_phase": task.validation_phase.dict() if task.validation_phase else None,
                "status": task.status
            } for task in tasks],
            suggested_next_actions=["map_capabilities"],
            completion_guidance=guidance
        )


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
        
        if not (session.capabilities.built_in_tools or session.capabilities.mcp_tools or session.capabilities.user_resources):
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
                "user_resources": [(resource.name, resource.description) for resource in session.capabilities.user_resources]
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
{chr(10).join([f"- {name}: {desc}" for name, desc in available_tools['builtin_tools']]) if available_tools['builtin_tools'] else '- No built-in tools declared'}

{chr(10).join([f"- {name}: {desc}" for name, desc in available_tools['mcp_tools']]) if available_tools['mcp_tools'] else '- No MCP tools declared'}

{chr(10).join([f"- {name}: {desc}" for name, desc in available_tools['user_resources']]) if available_tools['user_resources'] else '- No user resources declared'}

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
      "assigned_resources": [...]
    }},
    "execution_phase": {{
      "description": "Task-specific execution phase description", 
      "phase_guidance": "Key execution guidance for this task",
      "assigned_builtin_tools": [...],
      "assigned_mcp_tools": [...],
      "assigned_resources": [...]
    }},
    "validation_phase": {{
      "description": "How to validate this specific task",
      "phase_guidance": "Validation approach for this task",
      "assigned_builtin_tools": [...],
      "assigned_mcp_tools": [...], 
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


class ExecuteNextHandler(BaseCommandHandler):
    """Handler for execute_next command - provides rich contextual guidance for task execution."""
    
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
                suggested_next_actions=["create_session", "add_task"]
            )
        
        # Determine current phase and provide rich contextual guidance
        current_phase = self._determine_current_phase(next_task)
        phase_obj = getattr(next_task, f"{current_phase}_phase", None)
        
        if not phase_obj:
            # No phase defined - provide basic guidance
            guidance = f"""
🚀 EXECUTE TASK: {next_task.description}

⚠️ No {current_phase} phase defined for this task. Proceeding with basic guidance.

💡 SUGGESTED APPROACH:
1. Analyze the task requirements
2. Use available tools as needed
3. Complete the task objectives
4. Use 'mark_complete' when finished

Current Task ID: {next_task.id}
"""
            return TaskmasterResponse(
                action="execute_next",
                session_id=session.id,
                current_task_id=next_task.id,
                current_task_description=next_task.description,
                current_phase=current_phase,
                suggested_next_actions=["mark_complete"],
                completion_guidance=guidance
            )
        
        # Build rich contextual guidance from tool assignments
        tool_guidance = self._build_tool_guidance(phase_obj)
        
        # Get phase-specific context
        phase_context = f"""
📋 PHASE: {phase_obj.phase_name.upper()} - {phase_obj.description}
{f"🎯 PHASE GUIDANCE: {phase_obj.phase_guidance}" if phase_obj.phase_guidance else ""}
"""
        
        # Check if tools are actually assigned
        has_tools = (phase_obj.assigned_builtin_tools or 
                    phase_obj.assigned_mcp_tools or 
                    phase_obj.assigned_resources)
        
        if not has_tools:
            guidance = f"""
🚀 EXECUTE TASK: {next_task.description}

{phase_context}

⚠️ No tools assigned to this phase. This appears to be a thinking/analysis phase.

💡 APPROACH:
- Focus on analysis, planning, or conceptual work
- No tool usage required for this phase
- Use your reasoning capabilities to complete this phase
- Use 'mark_complete' when this phase is finished

Current Task ID: {next_task.id}
Current Phase: {current_phase}
"""
        else:
            guidance = f"""
🚀 EXECUTE TASK: {next_task.description}

{phase_context}

{tool_guidance}

🎯 EXECUTION STRATEGY:
1. Review the tool assignments and their purposes above
2. Start with CRITICAL priority tools if any are assigned
3. Follow the specific actions outlined for each tool
4. Achieve the expected outcomes described
5. Use 'mark_complete' when this phase is finished

Current Task ID: {next_task.id}
Current Phase: {current_phase}

💡 Remember: You are the brain - use these tools intelligently based on the context provided!
"""
        
        return TaskmasterResponse(
            action="execute_next",
            session_id=session.id,
            current_task_id=next_task.id,
            current_task_description=next_task.description,
            current_phase=current_phase,
            phase_description=phase_obj.description if phase_obj else None,
            phase_guidance=phase_obj.phase_guidance if phase_obj else None,
            assigned_tools={
                "builtin_tools": [tool.dict() for tool in phase_obj.assigned_builtin_tools] if phase_obj else [],
                "mcp_tools": [tool.dict() for tool in phase_obj.assigned_mcp_tools] if phase_obj else [],
                "resources": [tool.dict() for tool in phase_obj.assigned_resources] if phase_obj else []
            },
            suggested_next_actions=["mark_complete"],
            completion_guidance=guidance
        )
    
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
        
        # Determine next phase or completion
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
            
        elif current_phase == "execution" and has_validation:
            # Progress to validation phase
            task.current_phase = "validation"
            await self.session_manager.update_session(session)
        
            guidance = f"""
✅ Execution phase completed for: {task.description}

🔄 PROGRESSING TO VALIDATION PHASE

💡 NEXT STEP: Use 'execute_next' to get guidance for the validation phase.

Task ID: {task.id}
Current Phase: validation
"""
            return TaskmasterResponse(
                action="mark_complete",
                session_id=session.id,
                task_id=task.id,
                phase_completed="execution",
                next_phase="validation",
                suggested_next_actions=["execute_next"],
                completion_guidance=guidance
            )
            
        else:
            # Complete the entire task
            task.status = "completed"
            task.current_phase = "completed"
            await self.session_manager.update_session(session)
            
            # Check if there are more tasks
            remaining_tasks = [t for t in session.tasks if t.status == "pending"]
            
            if remaining_tasks:
                guidance = f"""
✅ Task completed: {task.description}

🎯 PROGRESS: {len(session.tasks) - len(remaining_tasks)}/{len(session.tasks)} tasks completed

💡 NEXT STEP: Use 'execute_next' to continue with the next task.

Remaining tasks: {len(remaining_tasks)}
"""
                next_actions = ["execute_next"]
            else:
                guidance = f"""
🎉 ALL TASKS COMPLETED! Outstanding work!

📊 SUMMARY:
- Session: {session.id}
- Tasks completed: {len(session.tasks)}
- Final task: {task.description}

💡 NEXT STEPS: You can create a new session or add more tasks to continue working.
"""
                next_actions = ["create_session", "add_task"]
        
            return TaskmasterResponse(
                action="mark_complete",
                session_id=session.id,
                task_id=task.id,
                task_completed=True,
                all_tasks_completed=len(remaining_tasks) == 0,
                tasks_remaining=len(remaining_tasks),
                suggested_next_actions=next_actions,
                completion_guidance=guidance
            )


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
            "create_tasklist": CreateTasklistHandler(session_manager, validation_engine),
            "map_capabilities": MapCapabilitiesHandler(session_manager, validation_engine),
            "execute_next": ExecuteNextHandler(session_manager, validation_engine),
            "mark_complete": MarkCompleteHandler(session_manager, validation_engine),
            "get_status": GetStatusHandler(session_manager, validation_engine),
            "collaboration_request": CollaborationRequestHandler(session_manager, validation_engine),
            
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
    """Handler for initiate_adversarial_review command - Implements Mandatory Adversarial Loop pattern."""
    
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
        
        if not generated_content:
            guidance = """
⚔️ ADVERSARIAL REVIEW LOOP REQUIRED

🎯 ARCHITECTURAL PATTERN: Countering Poor Self-Correction with Mandatory Adversarial Loop

📋 INITIATE ADVERSARIAL REVIEW:
Call taskmaster again with:
{
  "action": "initiate_adversarial_review",
  "generated_content": "The code/solution that was generated",
  "generator_agent": "tanuki-coder",  // or whichever agent generated it
  "content_type": "code"  // or "solution", "design", etc.
}

⚔️ ADVERSARIAL REVIEW PROCESS:
1. GENERATION: Content is generated by specialist agent
2. ADVERSARIAL REVIEW: tanuki-code-reviewer finds flaws and edge cases
3. TESTING: tanuki-tester generates comprehensive tests
4. CORRECTION CYCLE: Original agent fixes issues with peer feedback
5. REPEAT: Until code is approved by adversarial agents

💡 PATTERN PHILOSOPHY: Generated code is NEVER trusted as final without adversarial validation.
"""
            
            return TaskmasterResponse(
                action="initiate_adversarial_review",
                session_id=session.id,
                suggested_next_actions=["initiate_adversarial_review"],
                completion_guidance=guidance
            )
        
        # Create adversarial review process
        from .models import AdversarialReview
        adversarial_review = AdversarialReview(
            generation_phase="generated",
            generated_content=generated_content,
            generator_agent=generator_agent
        )
        
        # Find current task and update it
        if session.tasks:
            current_task = next((task for task in session.tasks if task.status == "pending"), None)
            if current_task:
                current_task.requires_adversarial_review = True
                current_task.complexity_level = "architectural"
                
                # Update current phase with adversarial review
                current_phase_name = current_task.current_phase or "execution"
                current_phase = getattr(current_task, f"{current_phase_name}_phase", None)
                if current_phase:
                    current_phase.adversarial_review = adversarial_review
                    current_phase.requires_adversarial_review = True
                    current_phase.verification_agents = ["tanuki-code-reviewer", "tanuki-tester"]
        
        await self.session_manager.update_session(session)
        
        guidance = f"""
⚔️ ADVERSARIAL REVIEW LOOP INITIATED

🎯 ARCHITECTURAL PATTERN: Mandatory Adversarial Loop Active

📝 GENERATED CONTENT:
   Generator: {generator_agent}
   Type: {content_type}
   Status: {adversarial_review.generation_phase}

⚔️ ADVERSARIAL REVIEW PROCESS:
   ✅ 1. GENERATION: Complete
   🔄 2. ADVERSARIAL REVIEW: Use tanuki-code-reviewer to find flaws
   ⏳ 3. TESTING: Use tanuki-tester to create comprehensive tests
   ⏳ 4. CORRECTION: Fix issues with peer feedback

🔍 NEXT ACTIONS:
1. Use tanuki-code-reviewer to analyze the generated content
2. Record findings with 'record_adversarial_findings'
3. Use tanuki-tester to create comprehensive tests
4. Record test results with 'record_test_results'

💡 PATTERN ENFORCEMENT: Content cannot be approved until adversarial review is complete.
"""
        
        return TaskmasterResponse(
            action="initiate_adversarial_review",
            session_id=session.id,
            adversarial_review_initiated=True,
            generator_agent=generator_agent,
            content_type=content_type,
            review_phase="adversarial_review",
            suggested_next_actions=["record_adversarial_findings", "record_test_results"],
            completion_guidance=guidance
        )


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
        exit_code = command.data.get("exit_code", 0)
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
