from typing import Dict, Any, Optional, List
import logging
from abc import ABC, abstractmethod
from .models import Session, Task, BuiltInTool, MCPTool, UserResource, EnvironmentCapabilities, TaskPhase
from .session_manager import SessionManager
from .validation_engine import ValidationEngine

logger = logging.getLogger(__name__)


class TaskmasterCommand:
    """Represents a command to be executed by the TaskmasterCommandHandler."""
    
    def __init__(
        self,
        action: str,
        task_description: Optional[str] = None,
        session_name: Optional[str] = None,
        validation_criteria: Optional[List[str]] = None,
        evidence: Optional[str] = None,
        execution_evidence: Optional[str] = None,
        builtin_tools: Optional[List[Dict[str, Any]]] = None,
        mcp_tools: Optional[List[Dict[str, Any]]] = None,
        user_resources: Optional[List[Dict[str, Any]]] = None,
        tasklist: Optional[List[Dict[str, Any]]] = None,
        task_ids: Optional[List[str]] = None,
        updated_task_data: Optional[Dict[str, Any]] = None,
        next_action_needed: bool = True,
        validation_result: Optional[str] = None,
        error_details: Optional[str] = None,
        collaboration_context: Optional[str] = None,
        user_response: Optional[str] = None,
        # Memory palace integration fields
        workspace_path: Optional[str] = None,
        task_id: Optional[str] = None,
        learnings: Optional[List[str]] = None,
        what_worked: Optional[List[str]] = None,
        what_didnt_work: Optional[List[str]] = None,
        insights: Optional[List[str]] = None,
        patterns: Optional[List[str]] = None
    ):
        self.action = action
        self.task_description = task_description
        self.session_name = session_name
        self.validation_criteria = validation_criteria or []
        self.evidence = evidence
        self.execution_evidence = execution_evidence
        self.builtin_tools = builtin_tools or []
        self.mcp_tools = mcp_tools or []
        self.user_resources = user_resources or []
        self.tasklist = tasklist or []
        self.task_ids = task_ids or []
        self.updated_task_data = updated_task_data or {}
        self.next_action_needed = next_action_needed
        self.validation_result = validation_result
        self.error_details = error_details
        self.collaboration_context = collaboration_context
        self.user_response = user_response
        # Memory palace integration
        self.workspace_path = workspace_path
        self.task_id = task_id
        self.learnings = learnings or []
        self.what_worked = what_worked or []
        self.what_didnt_work = what_didnt_work or []
        self.insights = insights or []
        self.patterns = patterns or []


class TaskmasterResponse:
    """Represents a response from the TaskmasterCommandHandler."""
    
    def __init__(
        self,
        action: str,
        session_id: Optional[str] = None,
        status: str = "success",
        current_task: Optional[Dict[str, Any]] = None,
        relevant_capabilities: Optional[Dict[str, List]] = None,
        all_capabilities: Optional[Dict[str, List]] = None,
        suggested_next_actions: Optional[List[str]] = None,
        completion_guidance: str = "",
        workflow_state: Optional[Dict[str, Any]] = None,
        **kwargs
    ):
        self.action = action
        self.session_id = session_id
        self.status = status
        self.current_task = current_task
        self.relevant_capabilities = relevant_capabilities or {"builtin_tools": [], "mcp_tools": [], "resources": []}
        self.all_capabilities = all_capabilities or {"builtin_tools": [], "mcp_tools": [], "resources": []}
        self.suggested_next_actions = suggested_next_actions or []
        self.completion_guidance = completion_guidance
        self.workflow_state = workflow_state or {
            "paused": False,
            "validation_state": "none",
            "can_progress": True
        }
        # Store additional response data
        for key, value in kwargs.items():
            setattr(self, key, value)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert response to dictionary format."""
        result = {
            "action": self.action,
            "session_id": self.session_id,
            "status": self.status,
            "current_task": self.current_task,
            "relevant_capabilities": self.relevant_capabilities,
            "all_capabilities": self.all_capabilities,
            "suggested_next_actions": self.suggested_next_actions,
            "completion_guidance": self.completion_guidance,
            "workflow_state": self.workflow_state,
            "next_action_needed": True  # Default value
        }
        
        # Add any additional attributes
        for key, value in self.__dict__.items():
            if key not in result:
                result[key] = value
        
        return result


class BaseCommandHandler(ABC):
    """Base class for command handlers."""
    
    def __init__(self, session_manager: SessionManager, validation_engine: ValidationEngine):
        self.session_manager = session_manager
        self.validation_engine = validation_engine
    
    @abstractmethod
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        """Handle the command and return a response."""
        pass
    
    def _validate_capability_format(self, cap_list: List[Dict[str, Any]], category_name: str) -> Optional[str]:
        """Validate capability format."""
        if not cap_list or not isinstance(cap_list, list):
            return f"{category_name} must be a non-empty list"
        
        for i, cap in enumerate(cap_list):
            if not isinstance(cap, dict):
                return f"{category_name}[{i}] must be a dictionary"
            
            required_fields = ["name", "description", "what_it_is", "what_it_does", "how_to_use", "relevant_for"]
            for field in required_fields:
                if field not in cap or not cap[field]:
                    return f"{category_name}[{i}] missing required field: {field}"
                if field == "relevant_for" and not isinstance(cap[field], list):
                    return f"{category_name}[{i}].relevant_for must be a list"
        
        return None


class CreateSessionHandler(BaseCommandHandler):
    """Handler for create_session command."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.create_session(command.session_name)
        
        return TaskmasterResponse(
            action="create_session",
            session_id=session.id,
            session_name=getattr(session, 'session_name', None),
            suggested_next_actions=["declare_capabilities"],
            completion_guidance="""
🚀 Session created! MANDATORY NEXT STEP: Use 'declare_capabilities' action with ALL THREE categories:

1. builtin_tools: Your core environment tools with DETAILED self-declarations
2. mcp_tools: Available MCP server tools with DETAILED self-declarations  
3. user_resources: Available docs, codebases, APIs with DETAILED self-declarations

Each capability MUST include: name, description, what_it_is, what_it_does, how_to_use, relevant_for

This is REQUIRED for intelligent task execution and capability mapping.
"""
        )


class DeclareCapabilitiesHandler(BaseCommandHandler):
    """Handler for declare_capabilities command."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = self.session_manager.get_current_session()
        if not session:
            session = await self.session_manager.create_session()
        
        # Validate all three categories are provided
        if not command.builtin_tools or not command.mcp_tools or not command.user_resources:
            return TaskmasterResponse(
                action="declare_capabilities",
                session_id=session.id,
                status="error",
                error="ALL THREE categories required: builtin_tools, mcp_tools, user_resources with detailed self-declarations",
                completion_guidance="You must provide ALL THREE capability categories with detailed self-declarations including: name, description, what_it_is, what_it_does, how_to_use, relevant_for"
            )
        
        # Validate format of each category
        for cap_list, category_name in [
            (command.builtin_tools, "builtin_tools"),
            (command.mcp_tools, "mcp_tools"),
            (command.user_resources, "user_resources")
        ]:
            validation_error = self._validate_capability_format(cap_list, category_name)
            if validation_error:
                return TaskmasterResponse(
                    action="declare_capabilities",
                    session_id=session.id,
                    status="error",
                    error=validation_error,
                    completion_guidance="Fix the capability declaration format. Each capability needs: name, description, what_it_is, what_it_does, how_to_use, relevant_for"
                )
        
        # Clear existing capabilities
        session.capabilities = EnvironmentCapabilities()
        
        # Handle built-in tools
        for tool_data in command.builtin_tools:
            tool = BuiltInTool(**tool_data)
            session.capabilities.built_in_tools.append(tool)
        
        # Handle MCP tools
        for tool_data in command.mcp_tools:
            if "server_name" not in tool_data:
                tool_data["server_name"] = "unknown"
            tool = MCPTool(**tool_data)
            session.capabilities.mcp_tools.append(tool)
        
        # Handle user resources
        for resource_data in command.user_resources:
            if "type" not in resource_data:
                resource_data["type"] = "documentation"
            resource = UserResource(**resource_data)
            session.capabilities.user_resources.append(resource)
        
        # Mark capabilities as declared
        session.environment_context["capabilities_declared"] = True
        await self.session_manager.update_session(session)
        
        # Build response
        all_capabilities = {
            "builtin_tools": [
                {
                    "name": t.name,
                    "description": t.description,
                    "what_it_is": t.what_it_is,
                    "what_it_does": t.what_it_does,
                    "how_to_use": t.how_to_use
                }
                for t in session.capabilities.built_in_tools
            ],
            "mcp_tools": [
                {
                    "name": t.name,
                    "server": t.server_name,
                    "description": t.description,
                    "what_it_is": t.what_it_is,
                    "what_it_does": t.what_it_does,
                    "how_to_use": t.how_to_use
                }
                for t in session.capabilities.mcp_tools
            ],
            "resources": [
                {
                    "name": r.name,
                    "type": r.type,
                    "description": r.description,
                    "what_it_is": r.what_it_is,
                    "what_it_does": r.what_it_does,
                    "how_to_use": r.how_to_use
                }
                for r in session.capabilities.user_resources
            ]
        }
        
        return TaskmasterResponse(
            action="declare_capabilities",
            session_id=session.id,
            all_capabilities=all_capabilities,
            suggested_next_actions=["create_tasklist"],
            completion_guidance=f"✅ ALL capabilities registered with detailed self-declarations! ({len(session.capabilities.built_in_tools)} built-in, {len(session.capabilities.mcp_tools)} MCP, {len(session.capabilities.user_resources)} resources) Now create a full tasklist using 'create_tasklist' action.",
            capabilities_declared={
                "builtin_tools": len(session.capabilities.built_in_tools),
                "mcp_tools": len(session.capabilities.mcp_tools),
                "user_resources": len(session.capabilities.user_resources)
            }
        )


class CreateTasklistHandler(BaseCommandHandler):
    """Handler for create_tasklist command."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = self.session_manager.get_current_session()
        if not session:
            session = await self.session_manager.create_session()
        
        # Check if capabilities are declared
        if not session.environment_context.get("capabilities_declared", False):
            return TaskmasterResponse(
                action="create_tasklist",
                session_id=session.id,
                status="error",
                error="Must declare capabilities first using 'declare_capabilities' action",
                suggested_next_actions=["declare_capabilities"],
                completion_guidance="You must declare your available built-in tools, MCP tools, and resources with detailed self-declarations before creating tasks."
            )
        
        # Validate that tasklist is provided and properly structured
        if not command.tasklist:
            return TaskmasterResponse(
                action="create_tasklist",
                session_id=session.id,
                status="error",
                error="Tasklist is required and cannot be empty",
                completion_guidance="Provide a tasklist with properly structured tasks including capability assignments for each phase."
            )
        
        # Get available capabilities for validation
        available_builtin_tools = {tool.name for tool in session.capabilities.built_in_tools}
        available_mcp_tools = {tool.name for tool in session.capabilities.mcp_tools}
        available_resources = {resource.name for resource in session.capabilities.user_resources}
        
        # Validate each task in the tasklist
        validation_errors = []
        for i, task_data in enumerate(command.tasklist):
            # Validate task structure
            if not isinstance(task_data, dict):
                validation_errors.append(f"Task {i+1}: Must be a dictionary")
                continue
            
            if 'description' not in task_data or not task_data['description']:
                validation_errors.append(f"Task {i+1}: Missing or empty description")
                continue
            
            # Validate phase structure and capability assignments
            required_phases = ['planning_phase', 'execution_phase', 'validation_phase']
            for phase_name in required_phases:
                if phase_name not in task_data:
                    validation_errors.append(f"Task {i+1}: Missing {phase_name}")
                    continue
                
                phase = task_data[phase_name]
                if not isinstance(phase, dict):
                    validation_errors.append(f"Task {i+1} {phase_name}: Must be a dictionary")
                    continue
                
                # Validate phase structure
                required_phase_fields = ['description', 'assigned_builtin_tools', 'assigned_mcp_tools', 'assigned_resources', 'requires_tool_usage', 'steps']
                for field in required_phase_fields:
                    if field not in phase:
                        validation_errors.append(f"Task {i+1} {phase_name}: Missing required field '{field}'")
                
                # Validate capability assignments against declared capabilities
                assigned_builtin = phase.get('assigned_builtin_tools', [])
                assigned_mcp = phase.get('assigned_mcp_tools', [])
                assigned_resources = phase.get('assigned_resources', [])
                
                # Check that assigned tools are actually available
                for tool in assigned_builtin:
                    if tool not in available_builtin_tools:
                        validation_errors.append(f"Task {i+1} {phase_name}: Assigned builtin tool '{tool}' not in declared capabilities")
                
                for tool in assigned_mcp:
                    if tool not in available_mcp_tools:
                        validation_errors.append(f"Task {i+1} {phase_name}: Assigned MCP tool '{tool}' not in declared capabilities")
                
                for resource in assigned_resources:
                    if resource not in available_resources:
                        validation_errors.append(f"Task {i+1} {phase_name}: Assigned resource '{resource}' not in declared capabilities")
                
                # Validate that if requires_tool_usage is True, at least one capability is assigned
                if phase.get('requires_tool_usage', False):
                    if not assigned_builtin and not assigned_mcp and not assigned_resources:
                        validation_errors.append(f"Task {i+1} {phase_name}: Marked as requiring tool usage but no capabilities assigned")
                
                # Validate that steps are provided and meaningful
                steps = phase.get('steps', [])
                if not steps or len(steps) == 0:
                    validation_errors.append(f"Task {i+1} {phase_name}: Must contain specific steps")
                elif any(len(step.strip()) < 10 for step in steps):
                    validation_errors.append(f"Task {i+1} {phase_name}: Steps must be detailed (at least 10 characters each)")
        
        # Return validation errors if any
        if validation_errors:
            return TaskmasterResponse(
                action="create_tasklist",
                session_id=session.id,
                status="error",
                error="Tasklist validation failed",
                validation_errors=validation_errors,
                completion_guidance=f"""
🚨 CAPABILITY ASSIGNMENT VALIDATION FAILED:

{chr(10).join(validation_errors)}

REQUIREMENTS:
1. Each task MUST have planning_phase, execution_phase, and validation_phase
2. Each phase MUST specify: description, assigned_builtin_tools, assigned_mcp_tools, assigned_resources, requires_tool_usage, steps
3. All assigned capabilities MUST be from your declared capabilities
4. If requires_tool_usage=true, at least one capability must be assigned
5. Steps must be detailed and specific (minimum 10 characters each)

This enforces LLM self-capability assignment and prevents hallucination!
"""
            )
        
        # Create tasks from validated tasklist
        created_tasks = []
        for task_data in command.tasklist:
            # Create task with enhanced structure
            task = Task(
                description=task_data['description'],
                validation_required=task_data.get('validation_required', True),  # Default to True for better validation
                validation_criteria=task_data.get('validation_criteria', ['completeness', 'capability_assignment', 'test_integrity']),  # Add test integrity rule
                planning_phase=TaskPhase(**task_data['planning_phase']),
                execution_phase=TaskPhase(**task_data['execution_phase']),
                validation_phase=TaskPhase(**task_data['validation_phase'])
            )
            
            session.tasks.append(task)
            created_tasks.append({
                "id": task.id,
                "description": task.description,
                "validation_required": task.validation_required,
                "validation_criteria": task.validation_criteria,
                "planning_phase": {
                    "description": task.planning_phase.description,
                    "assigned_builtin_tools": task.planning_phase.assigned_builtin_tools,
                    "assigned_mcp_tools": task.planning_phase.assigned_mcp_tools,
                    "assigned_resources": task.planning_phase.assigned_resources,
                    "requires_tool_usage": task.planning_phase.requires_tool_usage,
                    "steps": task.planning_phase.steps
                },
                "execution_phase": {
                    "description": task.execution_phase.description,
                    "assigned_builtin_tools": task.execution_phase.assigned_builtin_tools,
                    "assigned_mcp_tools": task.execution_phase.assigned_mcp_tools,
                    "assigned_resources": task.execution_phase.assigned_resources,
                    "requires_tool_usage": task.execution_phase.requires_tool_usage,
                    "steps": task.execution_phase.steps
                },
                "validation_phase": {
                    "description": task.validation_phase.description,
                    "assigned_builtin_tools": task.validation_phase.assigned_builtin_tools,
                    "assigned_mcp_tools": task.validation_phase.assigned_mcp_tools,
                    "assigned_resources": task.validation_phase.assigned_resources,
                    "requires_tool_usage": task.validation_phase.requires_tool_usage,
                    "steps": task.validation_phase.steps
                }
            })
        
        await self.session_manager.update_session(session)
        
        return TaskmasterResponse(
            action="create_tasklist",
            session_id=session.id,
            suggested_next_actions=["execute_next"],
            completion_guidance=f"""
✅ CAPABILITY-MAPPED TASKLIST CREATED! 

📊 Summary:
- {len(created_tasks)} tasks created with enforced capability assignments
- Each task has detailed planning, execution, and validation phases
- All capabilities validated against your declared capabilities
- Validation rules include 'completeness' and 'capability_assignment'

🎯 This ensures:
- No hallucinated tool usage
- Structured workflow execution  
- Proper capability utilization
- Prevention of placeholders/hardcoded values

Use 'execute_next' to begin guided execution with validation enforcement!
""",
            tasklist_created=True,
            tasks_created=len(created_tasks),
            created_tasks=created_tasks,
            capability_validation_enforced=True
        )


class UpdateMemoryPalaceHandler(BaseCommandHandler):
    """Handler for update_memory_palace command."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(
                action="update_memory_palace",
                status="error",
                error="No active session found",
                completion_guidance="Create a session first using 'create_session' action"
            )
        
        # Validate required fields
        if not hasattr(command, 'workspace_path') or not command.workspace_path:
            return TaskmasterResponse(
                action="update_memory_palace",
                session_id=session.id,
                status="error",
                error="workspace_path is required for memory palace updates",
                completion_guidance="Provide the memory palace workspace path"
            )
        
        if not hasattr(command, 'task_id') or not command.task_id:
            return TaskmasterResponse(
                action="update_memory_palace",
                session_id=session.id,
                status="error",
                error="task_id is required for memory palace updates",
                completion_guidance="Provide the task ID that was completed"
            )
        
        if not hasattr(command, 'learnings') or not command.learnings:
            return TaskmasterResponse(
                action="update_memory_palace",
                session_id=session.id,
                status="error",
                error="learnings are required for memory palace updates",
                completion_guidance="Provide key learnings from task completion"
            )
        
        # Find the completed task
        completed_task = None
        for task in session.tasks:
            if task.id == command.task_id:
                completed_task = task
                break
        
        if not completed_task:
            return TaskmasterResponse(
                action="update_memory_palace",
                session_id=session.id,
                status="error",
                error=f"Task with ID {command.task_id} not found in session",
                completion_guidance="Provide a valid task ID from the current session"
            )
        
        # Prepare memory palace updates
        updates = []
        
        # Add task completion concept
        task_concept = {
            "type": "concept",
            "content": f"Task completed: {completed_task.description}",
            "concept_type": "task_completion",
            "metadata": {
                "task_id": command.task_id,
                "session_id": session.id,
                "completion_timestamp": "2025-01-27T00:00:00Z",  # Would use actual timestamp
                "validation_required": completed_task.validation_required,
                "validation_criteria": completed_task.validation_criteria
            }
        }
        updates.append(task_concept)
        
        # Add learnings as concepts
        for learning in command.learnings:
            learning_concept = {
                "type": "concept",
                "content": f"Learning: {learning}",
                "concept_type": "learning",
                "metadata": {
                    "source_task_id": command.task_id,
                    "session_id": session.id,
                    "category": "task_learning"
                }
            }
            updates.append(learning_concept)
        
        # Add what worked as patterns
        for item in getattr(command, 'what_worked', []):
            pattern_concept = {
                "type": "concept",
                "content": f"Successful pattern: {item}",
                "concept_type": "pattern",
                "metadata": {
                    "source_task_id": command.task_id,
                    "session_id": session.id,
                    "category": "success_pattern",
                    "effectiveness": "high"
                }
            }
            updates.append(pattern_concept)
        
        # Add what didn't work as anti-patterns
        for item in getattr(command, 'what_didnt_work', []):
            antipattern_concept = {
                "type": "concept",
                "content": f"Anti-pattern to avoid: {item}",
                "concept_type": "antipattern",
                "metadata": {
                    "source_task_id": command.task_id,
                    "session_id": session.id,
                    "category": "failure_pattern",
                    "effectiveness": "low"
                }
            }
            updates.append(antipattern_concept)
        
        # Add insights
        for insight in getattr(command, 'insights', []):
            insight_concept = {
                "type": "concept",
                "content": f"Insight: {insight}",
                "concept_type": "insight",
                "metadata": {
                    "source_task_id": command.task_id,
                    "session_id": session.id,
                    "category": "task_insight"
                }
            }
            updates.append(insight_concept)
        
        # Add discovered patterns
        for pattern in getattr(command, 'patterns', []):
            discovered_pattern = {
                "type": "concept",
                "content": f"Discovered pattern: {pattern}",
                "concept_type": "pattern",
                "metadata": {
                    "source_task_id": command.task_id,
                    "session_id": session.id,
                    "category": "discovered_pattern"
                }
            }
            updates.append(discovered_pattern)
        
        # Store memory palace update request in session context for external processing
        # Since we can't directly call memory palace from here, we'll store the request
        if "memory_palace_updates" not in session.environment_context:
            session.environment_context["memory_palace_updates"] = []
        
        memory_update_request = {
            "workspace": command.workspace_path,
            "updates": updates,
            "task_id": command.task_id,
            "timestamp": "2025-01-27T00:00:00Z"  # Would use actual timestamp
        }
        
        session.environment_context["memory_palace_updates"].append(memory_update_request)
        await self.session_manager.update_session(session)
        
        return TaskmasterResponse(
            action="update_memory_palace",
            session_id=session.id,
            memory_palace_updated=True,  # Conceptually updated (stored for processing)
            concepts_added=len(updates),
            relationships_created=0,  # Would be determined by actual memory palace processing
            update_summary=f"Stored {len(updates)} concepts for memory palace update: {len(command.learnings)} learnings, {len(getattr(command, 'what_worked', []))} success patterns, {len(getattr(command, 'what_didnt_work', []))} anti-patterns, {len(getattr(command, 'insights', []))} insights, {len(getattr(command, 'patterns', []))} discovered patterns",
            suggested_next_actions=["execute_next"],
            completion_guidance=f"""
✅ MEMORY PALACE UPDATE PREPARED!

📝 Summary:
- Task: {completed_task.description}
- {len(updates)} concepts prepared for memory palace
- Learnings, patterns, insights, and anti-patterns captured
- Update request stored in session context

🧠 Memory Palace Integration:
- Workspace: {command.workspace_path}
- Task ID: {command.task_id}
- Ready for external memory_update tool call

This ensures continuous learning and knowledge accumulation!
""",
            memory_update_request=memory_update_request
        )


class ExecuteNextHandler(BaseCommandHandler):
    """Handler for execute_next command with enhanced validation enforcement."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(
                action="execute_next",
                status="error",
                error="No active session found",
                completion_guidance="Create a session first using 'create_session' action"
            )
        
        if not session.tasks:
            return TaskmasterResponse(
                action="execute_next",
                session_id=session.id,
                status="error",
                error="No tasks available for execution",
                suggested_next_actions=["create_tasklist"],
                completion_guidance="Create a tasklist first using 'create_tasklist' action"
            )
        
        # Find the next task to execute
        current_task = None
        for task in session.tasks:
            if task.status == "[ ]":  # Not completed
                current_task = task
                break
        
        if not current_task:
            return TaskmasterResponse(
                action="execute_next",
                session_id=session.id,
                status="success",
                completion_guidance="🎉 All tasks completed! Workflow finished successfully.",
                workflow_state={
                    "paused": False,
                    "validation_state": "completed",
                    "can_progress": False
                }
            )
        
        # Mark task as started
        current_task.execution_started = True
        await self.session_manager.update_session(session)
        
        # Build phase guidance with capability enforcement
        phase_guidance = {
            "planning": {
                "description": current_task.planning_phase.description if current_task.planning_phase else "Plan the task execution",
                "assigned_builtin_tools": current_task.planning_phase.assigned_builtin_tools if current_task.planning_phase else [],
                "assigned_mcp_tools": current_task.planning_phase.assigned_mcp_tools if current_task.planning_phase else [],
                "assigned_resources": current_task.planning_phase.assigned_resources if current_task.planning_phase else [],
                "requires_tool_usage": current_task.planning_phase.requires_tool_usage if current_task.planning_phase else False,
                "steps": current_task.planning_phase.steps if current_task.planning_phase else []
            },
            "execution": {
                "description": current_task.execution_phase.description if current_task.execution_phase else "Execute the task",
                "assigned_builtin_tools": current_task.execution_phase.assigned_builtin_tools if current_task.execution_phase else [],
                "assigned_mcp_tools": current_task.execution_phase.assigned_mcp_tools if current_task.execution_phase else [],
                "assigned_resources": current_task.execution_phase.assigned_resources if current_task.execution_phase else [],
                "requires_tool_usage": current_task.execution_phase.requires_tool_usage if current_task.execution_phase else False,
                "steps": current_task.execution_phase.steps if current_task.execution_phase else []
            },
            "validation": {
                "description": current_task.validation_phase.description if current_task.validation_phase else "Validate task completion",
                "assigned_builtin_tools": current_task.validation_phase.assigned_builtin_tools if current_task.validation_phase else [],
                "assigned_mcp_tools": current_task.validation_phase.assigned_mcp_tools if current_task.validation_phase else [],
                "assigned_resources": current_task.validation_phase.assigned_resources if current_task.validation_phase else [],
                "requires_tool_usage": current_task.validation_phase.requires_tool_usage if current_task.validation_phase else False,
                "steps": current_task.validation_phase.steps if current_task.validation_phase else []
            }
        }
        
        # Build execution guidance with anti-hallucination enforcement
        execution_guidance = f"""
🚀 EXECUTING TASK: {current_task.description}

⚠️  CRITICAL ENFORCEMENT RULES:
1. 🚫 NO PLACEHOLDERS: No TODO, FIXME, placeholder, temporary, hardcoded values
2. 🚫 NO CORNER-CUTTING: No incomplete implementations, stubs, or dummy code
3. 🚫 NO HALLUCINATED TOOLS: Use ONLY your assigned capabilities
4. ✅ COMPLETE IMPLEMENTATION: Provide full, working, production-ready code
5. ✅ EVIDENCE REQUIRED: Document exactly what you did and how

🧪 TEST INTEGRITY ENFORCEMENT:
⚠️  CRITICAL: If tests fail, FIX THE IMPLEMENTATION, NOT THE TESTS!
- 🚫 DO NOT modify tests to make them pass
- 🚫 DO NOT weaken assertions (no "or True", "is not None" replacements)
- 🚫 DO NOT comment out or skip failing tests
- 🚫 DO NOT use catch-and-release error handling (except: pass)
- ✅ FIX the actual underlying issue causing test failures
- ✅ Maintain original test assertions and requirements
- ✅ Add proper error handling that addresses root causes
- ✅ If tests are genuinely wrong, provide detailed justification

🔍 TEST VALIDATION WILL CHECK FOR:
- Test manipulation patterns (skipping, commenting out tests)
- Weakened assertions (changing == to "in" or "is not None")
- Catch-and-release error handling without proper resolution
- Trivial test cases that don't actually test functionality
- Suppressed errors that hide real issues

📋 ASSIGNED CAPABILITIES:
Planning Phase:
- Builtin Tools: {phase_guidance['planning']['assigned_builtin_tools']}
- MCP Tools: {phase_guidance['planning']['assigned_mcp_tools']}
- Resources: {phase_guidance['planning']['assigned_resources']}
- Steps: {phase_guidance['planning']['steps']}

Execution Phase:
- Builtin Tools: {phase_guidance['execution']['assigned_builtin_tools']}
- MCP Tools: {phase_guidance['execution']['assigned_mcp_tools']}
- Resources: {phase_guidance['execution']['assigned_resources']}
- Steps: {phase_guidance['execution']['steps']}

Validation Phase:
- Builtin Tools: {phase_guidance['validation']['assigned_builtin_tools']}
- MCP Tools: {phase_guidance['validation']['assigned_mcp_tools']}
- Resources: {phase_guidance['validation']['assigned_resources']}
- Steps: {phase_guidance['validation']['steps']}

🔍 VALIDATION CRITERIA: {current_task.validation_criteria}

⚡ COLLABORATION REQUIREMENT:
If you need additional context, clarification, or encounter ambiguity:
- PAUSE the workflow using 'collaboration_request' action
- Provide specific context about what you need
- DO NOT make assumptions or implement placeholders
- DO NOT modify tests to bypass issues

After completion, use 'validate_task' with comprehensive evidence!
"""
        
        return TaskmasterResponse(
            action="execute_next",
            session_id=session.id,
            current_task={
                "id": current_task.id,
                "description": current_task.description,
                "validation_required": current_task.validation_required,
                "validation_criteria": current_task.validation_criteria,
                "status": current_task.status
            },
            phase_guidance=phase_guidance,
            execution_guidance=execution_guidance,
            workflow_state={
                "paused": False,
                "validation_state": "pending",
                "can_progress": True
            },
            suggested_next_actions=["validate_task"],
            completion_guidance="Execute the task following the guidance above, then validate with evidence using 'validate_task' action."
        )


class ValidateTaskHandler(BaseCommandHandler):
    """Handler for validate_task command with enhanced completeness enforcement."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(
                action="validate_task",
                status="error",
                error="No active session found",
                completion_guidance="Create a session first using 'create_session' action"
            )
        
        # Find the current task being executed
        current_task = None
        for task in session.tasks:
            if task.execution_started and task.status == "[ ]":
                current_task = task
                break
        
        if not current_task:
            return TaskmasterResponse(
                action="validate_task",
                session_id=session.id,
                status="error",
                error="No task currently being executed",
                suggested_next_actions=["execute_next"],
                completion_guidance="Start task execution first using 'execute_next' action"
            )
        
        # Validate that evidence is provided
        if not command.evidence:
            return TaskmasterResponse(
                action="validate_task",
                session_id=session.id,
                status="error",
                error="Evidence is required for task validation",
                completion_guidance="Provide comprehensive evidence of task completion including implementation details, outputs, and tool usage"
            )
        
        # Prepare evidence for validation
        evidence_dict = {
            "implementation": command.evidence,
            "execution_evidence": command.execution_evidence or "",
            "task_description": current_task.description
        }
        
        # Run validation using the validation engine
        validation_passed, validation_messages = self.validation_engine.validate(current_task, evidence_dict)
        
        if validation_passed:
            # Mark task as completed
            current_task.status = "[X]"
            current_task.evidence.append({
                "validation_evidence": command.evidence,
                "execution_evidence": command.execution_evidence,
                "validation_messages": validation_messages,
                "timestamp": "2025-01-27T00:00:00Z"  # Would use actual timestamp
            })
            
            await self.session_manager.update_session(session)
            
            # Check if memory palace integration is enabled
            memory_palace_guidance = ""
            if hasattr(current_task, 'memory_palace_enabled') and current_task.memory_palace_enabled:
                memory_palace_guidance = f"""
🧠 MEMORY PALACE INTEGRATION AVAILABLE:
Use 'update_memory_palace' action to capture learnings from this task:
- What worked well
- What didn't work
- Key insights gained
- Patterns discovered
"""
            
            return TaskmasterResponse(
                action="validate_task",
                session_id=session.id,
                current_task={
                    "id": current_task.id,
                    "description": current_task.description,
                    "status": current_task.status,
                    "validation_messages": validation_messages
                },
                validation_status="passed",
                workflow_state={
                    "paused": False,
                    "validation_state": "passed",
                    "can_progress": True
                },
                suggested_next_actions=["execute_next", "update_memory_palace"] if memory_palace_guidance else ["execute_next"],
                completion_guidance=f"""
✅ TASK VALIDATION PASSED!

📋 Task: {current_task.description}
✅ Validation Results:
{chr(10).join(f"  • {msg}" for msg in validation_messages)}

{memory_palace_guidance}

Continue with 'execute_next' for the next task!
"""
            )
        else:
            # Validation failed - increment error count and provide guidance
            current_task.validation_errors.append({
                "evidence": command.evidence,
                "execution_evidence": command.execution_evidence,
                "validation_messages": validation_messages,
                "timestamp": "2025-01-27T00:00:00Z"  # Would use actual timestamp
            })
            
            await self.session_manager.update_session(session)
            
            return TaskmasterResponse(
                action="validate_task",
                session_id=session.id,
                current_task={
                    "id": current_task.id,
                    "description": current_task.description,
                    "status": current_task.status,
                    "validation_errors": len(current_task.validation_errors)
                },
                validation_status="failed",
                workflow_state={
                    "paused": True,  # Pause workflow on validation failure
                    "validation_state": "failed",
                    "can_progress": False
                },
                suggested_next_actions=["collaboration_request", "execute_next"],
                completion_guidance=f"""
❌ TASK VALIDATION FAILED!

📋 Task: {current_task.description}
❌ Validation Issues:
{chr(10).join(f"  • {msg}" for msg in validation_messages)}

🚨 WORKFLOW PAUSED - CRITICAL ISSUES DETECTED:

REQUIRED ACTIONS:
1. Review the validation failures above
2. Address each issue completely (no placeholders/shortcuts)
3. If you need clarification, use 'collaboration_request' action
4. Re-execute the task properly with 'execute_next'
5. Provide better evidence for validation

⚠️  DO NOT PROCEED until validation issues are resolved!
This prevents low-quality implementations and ensures completeness.
"""
            )


class ValidationErrorHandler(BaseCommandHandler):
    """Handler for validation_error command with specific guidance for different error types."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(
                action="validation_error",
                status="error",
                error="No active session found",
                completion_guidance="Create a session first using 'create_session' action"
            )
        
        # Find the current task
        current_task = None
        for task in session.tasks:
            if task.execution_started and task.status == "[ ]":
                current_task = task
                break
        
        if not current_task:
            return TaskmasterResponse(
                action="validation_error",
                session_id=session.id,
                status="error",
                error="No task currently being executed",
                completion_guidance="Start task execution first using 'execute_next' action"
            )
        
        error_details = command.error_details or "Validation error occurred"
        
        # Analyze error type and provide specific guidance
        guidance = self._get_error_specific_guidance(error_details)
        
        # Record the validation error
        current_task.validation_errors.append({
            "error_details": error_details,
            "timestamp": "2025-01-27T00:00:00Z",  # Would use actual timestamp
            "guidance_provided": guidance
        })
        
        await self.session_manager.update_session(session)
        
        return TaskmasterResponse(
            action="validation_error",
            session_id=session.id,
            current_task={
                "id": current_task.id,
                "description": current_task.description,
                "validation_errors": len(current_task.validation_errors)
            },
            workflow_state={
                "paused": True,
                "validation_state": "failed",
                "can_progress": False
            },
            suggested_next_actions=["collaboration_request", "execute_next"],
            completion_guidance=guidance
        )
    
    def _get_error_specific_guidance(self, error_details: str) -> str:
        """Provide specific guidance based on the type of validation error."""
        
        error_lower = error_details.lower()
        
        # Test integrity specific guidance
        if any(keyword in error_lower for keyword in ['test', 'assertion', 'skip', 'except', 'catch']):
            return f"""
🚨 TEST INTEGRITY VIOLATION DETECTED!

Error: {error_details}

🧪 CRITICAL TEST INTEGRITY RULES:
1. 🚫 NEVER modify tests to make them pass - FIX THE IMPLEMENTATION
2. 🚫 NEVER weaken assertions (no "or True", changing == to "in")
3. 🚫 NEVER comment out or skip failing tests
4. 🚫 NEVER use catch-and-release error handling (except: pass)

✅ REQUIRED ACTIONS:
1. Identify the ROOT CAUSE of the test failure
2. Fix the IMPLEMENTATION to satisfy the original test requirements
3. Maintain ALL original test assertions and requirements
4. Add proper error handling that addresses the actual issue
5. If a test is genuinely incorrect, provide detailed justification

⚠️  REMEMBER: Tests define the requirements. If tests fail, the implementation is wrong, not the tests!

Use 'collaboration_request' if you need clarification on requirements.
Re-execute with 'execute_next' after fixing the implementation.
"""
        
        # Completeness specific guidance
        elif any(keyword in error_lower for keyword in ['placeholder', 'todo', 'fixme', 'hardcoded', 'incomplete']):
            return f"""
🚨 COMPLETENESS VIOLATION DETECTED!

Error: {error_details}

🔧 COMPLETENESS REQUIREMENTS:
1. 🚫 NO placeholders (TODO, FIXME, placeholder, temporary)
2. 🚫 NO hardcoded values that should be configurable
3. 🚫 NO incomplete implementations or stubs
4. ✅ COMPLETE, production-ready implementation required

✅ REQUIRED ACTIONS:
1. Remove all placeholder code and implement proper functionality
2. Replace hardcoded values with configurable parameters
3. Complete all incomplete implementations
4. Provide substantial, working code

Use 'collaboration_request' if you need clarification on implementation details.
Re-execute with 'execute_next' after completing the implementation.
"""
        
        # Capability assignment specific guidance
        elif any(keyword in error_lower for keyword in ['capability', 'tool', 'assigned', 'declared']):
            return f"""
🚨 CAPABILITY ASSIGNMENT VIOLATION DETECTED!

Error: {error_details}

🎯 CAPABILITY ASSIGNMENT RULES:
1. 🚫 ONLY use capabilities assigned to your task phases
2. 🚫 NO hallucinated or undeclared tool usage
3. ✅ Evidence must show usage of assigned capabilities
4. ✅ At least 50% of assigned capabilities must be utilized

✅ REQUIRED ACTIONS:
1. Review your assigned capabilities for each phase
2. Use ONLY the tools and resources assigned to you
3. Provide evidence of how you used assigned capabilities
4. If you need additional capabilities, use 'collaboration_request'

Re-execute with 'execute_next' using only your assigned capabilities.
"""
        
        # Generic validation error guidance
        else:
            return f"""
🚨 VALIDATION ERROR DETECTED!

Error: {error_details}

⚠️  GENERAL VALIDATION REQUIREMENTS:
1. ✅ Complete, production-ready implementation
2. ✅ Use only assigned capabilities
3. ✅ Maintain test integrity (fix implementation, not tests)
4. ✅ Provide comprehensive evidence
5. ✅ No placeholders or shortcuts

✅ REQUIRED ACTIONS:
1. Review the specific error details above
2. Address the root cause of the validation failure
3. Ensure your implementation meets all requirements
4. Use 'collaboration_request' if you need clarification
5. Re-execute with 'execute_next' after fixing issues

Remember: Validation failures indicate quality issues that must be resolved!
"""


class TaskmasterCommandHandler:
    """
    Main command handler that routes commands to specific handlers.
    
    Replaces the monolithic taskmaster function with focused command handlers
    for better separation of concerns and maintainability.
    """
    
    def __init__(self, session_manager: SessionManager, validation_engine: ValidationEngine):
        self.session_manager = session_manager
        self.validation_engine = validation_engine
        
        # Initialize command handlers
        self.handlers: Dict[str, BaseCommandHandler] = {
            "create_session": CreateSessionHandler(session_manager, validation_engine),
            "declare_capabilities": DeclareCapabilitiesHandler(session_manager, validation_engine),
            "create_tasklist": CreateTasklistHandler(session_manager, validation_engine),
            "update_memory_palace": UpdateMemoryPalaceHandler(session_manager, validation_engine),
            "execute_next": ExecuteNextHandler(session_manager, validation_engine),
            "validate_task": ValidateTaskHandler(session_manager, validation_engine),
            "validation_error": ValidationErrorHandler(session_manager, validation_engine),
            # TODO: Add more handlers for other commands
        }
    
    async def execute(self, command: TaskmasterCommand) -> TaskmasterResponse:
        """
        Execute a command using the appropriate handler.
        
        Args:
            command: The command to execute
            
        Returns:
            TaskmasterResponse: The response from the command handler
        """
        try:
            # Handle user response to collaboration request first
            if command.user_response:
                await self._handle_user_response(command)
            
            # Get the appropriate handler
            handler = self.handlers.get(command.action)
            if not handler:
                return TaskmasterResponse(
                    action=command.action,
                    status="error",
                    error=f"Unknown action: {command.action}",
                    completion_guidance=f"Available actions: {', '.join(self.handlers.keys())}"
                )
            
            # Execute the command
            response = await handler.handle(command)
            logger.info(f"Executed command: {command.action}")
            return response
            
        except Exception as e:
            logger.error(f"Error executing command {command.action}: {e}")
            return TaskmasterResponse(
                action=command.action,
                status="error",
                error=str(e),
                completion_guidance="An error occurred while processing the command. Please check the logs for details."
            )
    
    async def _handle_user_response(self, command: TaskmasterCommand) -> None:
        """Handle user response to collaboration request."""
        session = self.session_manager.get_current_session()
        if session and session.environment_context.get("workflow_paused", False):
            # Add user response as a new task
            user_task = Task(description=f"User Response: {command.user_response}")
            session.tasks.append(user_task)
            
            # Resume workflow
            session.environment_context["workflow_paused"] = False
            session.environment_context["pause_reason"] = None
            await self.session_manager.update_session(session)
            
            logger.info("User response processed and workflow resumed")
    
    def add_handler(self, action: str, handler: BaseCommandHandler) -> None:
        """
        Add a new command handler.
        
        Args:
            action: The action name
            handler: The handler instance
        """
        self.handlers[action] = handler
        logger.info(f"Added handler for action: {action}")
    
    def get_available_actions(self) -> List[str]:
        """Get list of available actions."""
        return list(self.handlers.keys()) 