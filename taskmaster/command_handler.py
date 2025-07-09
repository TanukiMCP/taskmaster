from typing import Dict, Any, Optional, List
import logging
import json
from abc import ABC, abstractmethod
from datetime import datetime
from .models import Session, Task, BuiltInTool, MCPTool, MemoryTool, EnvironmentCapabilities, InitialToolThoughts, ToolAssignment
from .session_manager import SessionManager
from .validation_engine import ValidationEngine
from .schemas import (
    ActionType,
    create_flexible_request, create_flexible_response,
    extract_guidance, clean_guidance
)

logger = logging.getLogger(__name__)


class TaskmasterCommand:
    """Represents a command to be executed by the TaskmasterCommandHandler."""
    
    def __init__(self, **kwargs):
        if "data" in kwargs:
            merged_data = kwargs["data"].copy()
            merged_data.update({k: v for k, v in kwargs.items() if k != "data"})
            self.data = create_flexible_request(merged_data)
        else:
            self.data = create_flexible_request(kwargs)
        
        self.action = self.data.get("action", "get_status")
        self.task_description = self.data.get("task_description")
        self.session_name = self.data.get("session_name")
        self.builtin_tools = self.data.get("builtin_tools", [])
        self.mcp_tools = self.data.get("mcp_tools", [])
        self.user_resources = self.data.get("user_resources", [])
        self.tasklist = self.data.get("tasklist", [])
        self.task_mappings = self.data.get("task_mappings", [])
        self.collaboration_context = self.data.get("collaboration_context")
        self.task_id = self.data.get("task_id")
        self.six_hats = self.data.get("six_hats", {})
        self.denoised_plan = self.data.get("denoised_plan", "")
        self.updated_task_data = self.data.get("updated_task_data", {})


class TaskmasterResponse:
    """Represents a response from the TaskmasterCommandHandler."""
    
    def __init__(self, action: str, **kwargs):
        self.data = create_flexible_response(action, **kwargs)
        self.action = self.data["action"]
        self.session_id = self.data.get("session_id")
        self.status = self.data.get("status", "success")
        self.suggested_next_actions = self.data.get("suggested_next_actions", [])
        self.completion_guidance = self.data.get("completion_guidance", "")
        
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


class CreateSessionHandler(BaseCommandHandler):
    """Handler for create_session command."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.create_session(command.session_name)
        guidance = """
✅ **Session created successfully!**

🎯 **NEXT STEP**: Use 'declare_capabilities' to inform Taskmaster of the tools you can use.

**CRITICAL**: Taskmaster does not scan your environment automatically. You must declare what tools and resources you have access to. This information is essential for creating an effective plan.

## What to Declare:

**Built-in Tools**: Functions you can call directly (like file operations, terminal commands, web searches)
**MCP Tools**: Tools from MCP servers (like this taskmaster tool itself)  
**User Resources**: Information, files, or knowledge you have access to

## Template Structure:

Each tool needs:
- `name`: The exact function/tool name
- `description`: What it does and when to use it

MCP tools also need:
- `server_name`: Which MCP server provides the tool

User resources need:
- `name`: Resource identifier  
- `description`: What information/capability it provides

**COMPLETE EXAMPLE - Copy and adapt this template:**

```json
{{
  "action": "declare_capabilities",
  "builtin_tools": [
    {{"name": "codebase_search", "description": "Semantic search through code to understand project structure and find relevant files"}},
    {{"name": "read_file", "description": "Read the contents of files to understand existing code and configuration"}},
    {{"name": "edit_file", "description": "Create new files or modify existing files with precise changes"}},
    {{"name": "run_terminal_cmd", "description": "Execute terminal commands for building, testing, and running applications"}},
    {{"name": "grep_search", "description": "Search for specific text patterns or code across files"}},
    {{"name": "web_search", "description": "Search the internet for documentation, examples, and current information"}}
  ],
  "mcp_tools": [
    {{"name": "mcp_taskmaster_taskmaster", "description": "The task execution framework itself for managing workflow", "server_name": "taskmaster"}},
    {{"name": "mcp_context7_get_library_docs", "description": "Get documentation for libraries and frameworks", "server_name": "context7"}}
  ],
  "user_resources": [
    {{"name": "project_codebase", "description": "Complete source code for the current project including all files and directories"}},
    {{"name": "project_requirements", "description": "Detailed specifications and requirements for what needs to be built"}},
    {{"name": "domain_knowledge", "description": "Understanding of the business domain and technical context"}}
  ]
}}
```

**CUSTOMIZATION TIPS:**
- Replace example tools with the actual tools you have access to
- Be specific about what each tool does - this helps with planning
- Include all relevant resources you can leverage
- Don't declare tools you cannot actually use

**COMMON BUILT-IN TOOLS:**
- File operations: `read_file`, `edit_file`, `delete_file`, `list_dir`
- Code analysis: `codebase_search`, `grep_search`, `file_search`
- Development: `run_terminal_cmd`, `create_diagram`
- Research: `web_search`, `fetch_pull_request`

After declaring capabilities, you'll move to the planning phase with 'six_hat_thinking'.
"""
        return TaskmasterResponse(
            action="create_session",
            session_id=session.id,
            suggested_next_actions=["declare_capabilities"],
            completion_guidance=guidance,
        )


class DeclareCapabilitiesHandler(BaseCommandHandler):
    """Handler for declare_capabilities command."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(action="declare_capabilities", status="guidance", completion_guidance="No active session.")

        builtin_tools = command.builtin_tools or []
        mcp_tools = command.mcp_tools or []
        user_resources = command.user_resources or []
        
        if not any([builtin_tools, mcp_tools, user_resources]):
            guidance = """
🛠️ **DECLARE YOUR CAPABILITIES**

You must declare the tools you have access to. Taskmaster does not scan your environment; it relies on you to report what you can do.

**Required Fields:**
- Built-in tools: Each requires 'name' and 'description'
- MCP tools: Each requires 'name', 'description', and 'server_name'
- User resources: Each requires 'name' and 'description'

**Example declare_capabilities call:**
```json
{
  "action": "declare_capabilities",
  "builtin_tools": [
    {"name": "codebase_search", "description": "Semantic search through code"},
    {"name": "run_terminal_cmd", "description": "Execute terminal commands"}
  ],
  "mcp_tools": [
    {"name": "mcp_taskmaster_taskmaster", "description": "The task execution framework itself", "server_name": "taskmaster"}
  ],
  "user_resources": [
    {"name": "project_codebase", "description": "The full source code for the current project"}
  ]
}
```

**INSTRUCTIONS:**
1. **Inspect your environment**: Identify all tools you can call
2. **List them accurately**: Provide the required fields for each
3. **Be thorough**: The quality of the plan depends on this list
"""
            return TaskmasterResponse(
                action="declare_capabilities",
                session_id=session.id,
                status="template",
                completion_guidance=guidance,
                suggested_next_actions=["declare_capabilities"]
            )

        session.capabilities.built_in_tools = [BuiltInTool(**tool) for tool in builtin_tools]
        session.capabilities.mcp_tools = [MCPTool(**tool) for tool in mcp_tools]
        session.capabilities.user_resources = [MemoryTool(**res) for res in user_resources]
        
        await self.session_manager.update_session(session)
        
        guidance = f"""
✅ **Capabilities declared successfully!**

📊 **SUMMARY:**
- Built-in Tools: {len(session.capabilities.built_in_tools)}
- MCP Tools: {len(session.capabilities.mcp_tools)}
- User Resources: {len(session.capabilities.user_resources)}

🎯 **NEXT STEP**: Use 'six_hat_thinking' to begin the planning process.

The Six Hat Thinking method helps you analyze your project from six different perspectives to create a comprehensive plan. Each "hat" represents a different type of thinking:

- **White Hat**: Facts, data, and objective information
- **Red Hat**: Emotions, feelings, and intuitive responses  
- **Black Hat**: Critical thinking, risks, and potential problems
- **Yellow Hat**: Optimistic thinking, benefits, and opportunities
- **Green Hat**: Creative thinking, alternatives, and innovative ideas
- **Blue Hat**: Process thinking, organization, and meta-analysis

**FLEXIBLE KEY NAMING**: You can use any of these formats for the keys:
- Simple: "white", "red", "black", "yellow", "green", "blue"
- Descriptive: "white_hat", "red_hat_thinking", "yellow_hat_analysis", etc.
- The system will automatically recognize any key containing the color name.

**COMPLETE EXAMPLE - Copy and adapt this template:**

```json
{{
  "action": "six_hat_thinking",
  "six_hats": {{
    "white": "Factual analysis: List the concrete requirements, technical constraints, available resources, and known information about your project. What tools do you have? What are the specific deliverables?",
    "red": "Emotional/intuitive analysis: What are your gut feelings about this project? What might excite or concern the end users? What's the emotional motivation behind this work?",
    "black": "Critical analysis: What could go wrong? What are the technical risks, potential roadblocks, resource limitations, or implementation challenges you foresee?",
    "yellow": "Optimistic analysis: What are the benefits and positive outcomes? Why will this project succeed? What opportunities does it create? What's the best-case scenario?",
    "green": "Creative analysis: What are alternative approaches? Are there innovative solutions, different technologies, or creative ways to tackle the challenges?",
    "blue": "Process analysis: How should the work be organized? What's the overall strategy? How will you manage the development process and ensure quality?"
  }}
}}
```

**TIPS FOR SUCCESS:**
- Replace the example content with analysis specific to your project
- Each perspective should be 2-4 sentences of thoughtful analysis
- Don't just list items - provide reasoning and context
- Consider your project from each angle genuinely

After completing six_hat_thinking, you'll move to the 'denoise' step to synthesize your analysis into a unified plan.
"""
        return TaskmasterResponse(
            action="declare_capabilities",
            session_id=session.id,
            suggested_next_actions=["six_hat_thinking"],
            completion_guidance=guidance
        )


class SixHatThinkingHandler(BaseCommandHandler):
    """Guides the LLM through a structured brainstorming process for task planning."""

    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(action="six_hat_thinking", status="guidance", completion_guidance="No active session.")

        raw_six_hats = command.data.get("six_hats", {})
        
        if raw_six_hats and isinstance(raw_six_hats, dict):
            required_hats = ['white', 'red', 'black', 'yellow', 'green', 'blue']
            
            # Normalize keys to be more forgiving
            normalized_hats = {}
            for key, value in raw_six_hats.items():
                for color in required_hats:
                    if color in key.lower():
                        normalized_hats[color] = value
                        break
            
            # Validate that all required hat perspectives are present
            missing_hats = [hat for hat in required_hats if hat not in normalized_hats or not normalized_hats[hat]]
            
            if missing_hats:
                return TaskmasterResponse(
                    action="six_hat_thinking",
                    status="validation_error",
                    completion_guidance=f"❌ **VALIDATION ERROR**: Missing or empty perspectives: {', '.join(missing_hats)}.\n\n"
                    f"Please provide analysis for all six hat perspectives: {', '.join(required_hats)}.\n\n"
                    f"**Example six_hat_thinking call:**\n"
                    f"```json\n"
                    f"{{\n"
                    f'  "action": "six_hat_thinking",\n'
                    f'  "six_hats": {{\n'
                    f'    "white": "Factual analysis here...",\n'
                    f'    "red": "Emotional analysis here...",\n'
                    f'    "black": "Risk analysis here...",\n'
                    f'    "yellow": "Optimistic analysis here...",\n'
                    f'    "green": "Creative analysis here...",\n'
                    f'    "blue": "Process analysis here..."\n'
                    f'  }}\n'
                    f'}}\n'
                    f"```",
                    suggested_next_actions=["six_hat_thinking"]
                )
            
            # Store the analysis in session data
            session.data["six_hat_analysis"] = normalized_hats
            await self.session_manager.update_session(session)
            
            return TaskmasterResponse(
                action="six_hat_thinking",
                session_id=session.id,
                status="success",
                completion_guidance="✅ **Six Hat Thinking completed successfully!**\n\n"
                "Your analysis has been recorded. Now proceed to synthesize your insights.\n\n"
                "🎯 **NEXT STEP**: Call `denoise` with your six_hats analysis to create a unified plan.\n\n"
                "**Example denoise call:**\n"
                "```json\n"
                "{\n"
                '  "action": "denoise",\n'
                f'  "six_hats": {json.dumps(normalized_hats, indent=2)}\n'
                "}\n"
                "```",
                suggested_next_actions=["denoise"]
            )

        # If no six_hats data provided, return template guidance
        guidance = """
🎩 **SIX HAT THINKING: Tasklist Ideation**

Before creating a tasklist, you will engage in a structured brainstorming exercise to ensure a robust and comprehensive plan. Consider the user's request from six different perspectives.

**Your Goal**: Generate six distinct "future state imaginings" of what the final tasklist and workflow should look like.

**IMPORTANT RULE**: Taskmaster is a `plan -> execute` tool. Your tasklists must focus **only on implementation**. Do **NOT** include tasks for testing, validation, or documentation writing. These are the user's responsibility after the implementation is complete.

**The Six Hats:**

1. ⚪ **White Hat (The Factual)**: What are the pure facts and data? What information do I have, and what do I need? Detail the knowns and unknowns objectively.
2. 🔴 **Red Hat (The Emotional)**: What are my gut reactions and intuitions? What are the potential feelings of the user? What are the exciting possibilities or potential pitfalls from an emotional standpoint?
3. ⚫ **Black Hat (The Cautious)**: What could go wrong? What are the risks, weaknesses, and potential failure points in the plan? Be critical and identify obstacles.
4. 🟡 **Yellow Hat (The Optimist)**: What are the benefits and opportunities? Why will this work? What is the best-case scenario? Focus on the positive outcomes.
5. 🟢 **Green Hat (The Creative)**: What are the alternative ideas? Can I approach this differently? Are there novel solutions or creative ways to tackle the tasks?
6. 🔵 **Blue Hat (The Conductor)**: How should I organize the thinking process itself? What is the meta-view of this plan? How do the other hats fit together to form a strategy?

**ACTION REQUIRED**:
Provide your analysis for all six perspectives in the `six_hats` parameter.

**Example six_hat_thinking call:**
```json
{
  "action": "six_hat_thinking",
  "six_hats": {
    "white": "The user wants a Python script. It needs to read a CSV and output a JSON. The required libraries are pandas and json...",
    "red": "My gut feeling is that the user will be impressed with a clean, efficient script. A potential frustration point is if the CSV format is inconsistent...",
    "black": "Potential risks include file format incompatibilities, memory issues with large files, and error handling for malformed data...",
    "yellow": "This will provide the user with a reusable, efficient tool. Success means clean data transformation and easy integration...",
    "green": "Alternative approaches could include streaming processing, configuration files for field mapping, or a GUI interface...",
    "blue": "The process should be: validate input → read data → transform → validate output → write results. Error handling at each step..."
  }
}
```

🎯 **NEXT STEP**: Complete the analysis above and call this command with your six_hats data.
"""
        return TaskmasterResponse(
            action="six_hat_thinking",
            session_id=session.id,
            status="template",
            completion_guidance=guidance,
            suggested_next_actions=["six_hat_thinking"]
        )


class DenoiseHandler(BaseCommandHandler):
    """Guides the LLM to synthesize its brainstorming into a single, optimal plan."""

    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(action="denoise", status="guidance", completion_guidance="No active session.")

        six_hats = command.data.get("six_hats")
        if not six_hats or not all(k in six_hats for k in ['white', 'red', 'black', 'yellow', 'green', 'blue']):
            return TaskmasterResponse(
                action="denoise",
                status="guidance",
                completion_guidance="❌ **ERROR**: You must provide the `six_hats` parameter with all six perspectives.\n\n"
                "**Example denoise call:**\n"
                "```json\n"
                "{\n"
                '  "action": "denoise",\n'
                '  "six_hats": {\n'
                '    "white": "Your factual analysis...",\n'
                '    "red": "Your emotional analysis...",\n'
                '    "black": "Your risk analysis...",\n'
                '    "yellow": "Your optimistic analysis...",\n'
                '    "green": "Your creative analysis...",\n'
                '    "blue": "Your process analysis..."\n'
                '  }\n'
                "}\n"
                "```",
                suggested_next_actions=["denoise"]
            )
        
        # Store the six_hats analysis and create denoised plan
        session.data["six_hat_analysis"] = six_hats
        session.data["denoised_plan"] = "Plan synthesized from six hat analysis"
        await self.session_manager.update_session(session)

        guidance = """
✅ **DENOISE: Synthesize Your Plan**

You have analyzed the request from six different perspectives. Now, your task is to consolidate these viewpoints into a single, optimal, and highly-detailed plan.

**Your Goal**: Create the final blueprint for your tasklist.

**Process**:
1. **Review Your Hats**: Re-read your White, Black, and Yellow Hat analyses to ground your plan in facts, risks, and benefits.
2. **Incorporate Creativity**: Blend in the innovative ideas from your Green Hat.
3. **Manage the Process**: Use your Blue Hat thinking to structure the final plan logically.
4. **Synthesize**: Write a new, single, coherent plan that combines the best elements and discards suboptimal ideas. This plan should be an exhaustive, step-by-step description of the entire implementation process.

**ACTION REQUIRED**:
Call the `create_tasklist` command next. In the `denoised_plan` parameter, provide the final, synthesized plan as a detailed string of text.

**Example create_tasklist call:**
```json
{
  "action": "create_tasklist",
  "denoised_plan": "Your synthesized implementation plan here...",
  "tasklist": [
    {"description": "Set up project structure and initial files"},
    {"description": "Implement core data processing logic"},
    {"description": "Implement output generation"}
  ]
}
```

🎯 **NEXT STEP**: Use `create_tasklist` with your `denoised_plan` and `tasklist`.
"""
        return TaskmasterResponse(
            action="denoise",
            session_id=session.id,
            status="template",
            completion_guidance=guidance,
            suggested_next_actions=["create_tasklist"],
        )


class CreateTasklistHandler(BaseCommandHandler):
    """Handler for create_tasklist command, now enhanced to process a 'denoised_plan'."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(action="create_tasklist", status="guidance", completion_guidance="No active session.")

        raw_tasklist = command.tasklist
        denoised_plan = command.data.get("denoised_plan")

        if not raw_tasklist:
            guidance = """
📝 **CREATE TASKLIST**

You have completed the thinking and denoising process. Now, formalize your plan into a structured tasklist.

**Reminder**: Your tasklist must focus **only on implementation**. Do **NOT** include tasks for testing, validation, or documentation writing.

**Example create_tasklist call:**
```json
{
  "action": "create_tasklist",
  "denoised_plan": "Your synthesized plan from denoise step...",
  "tasklist": [
    {"description": "Set up project structure and initial files"},
    {"description": "Implement CSV reading logic using pandas"},
    {"description": "Implement core data transformation logic"},
    {"description": "Implement JSON output generation"}
  ]
}
```

🎯 **NEXT STEP**: Provide both the `denoised_plan` and `tasklist` parameters.
"""
            return TaskmasterResponse(
                action="create_tasklist",
                session_id=session.id,
                status="template",
                completion_guidance=guidance,
                suggested_next_actions=["create_tasklist"]
            )

        enhanced_tasks, validation_issues = self._validate_and_enhance_tasklist(raw_tasklist)
        
        session.tasks = [Task(**task_data) for task_data in enhanced_tasks]
        if denoised_plan:
            session.data["denoised_plan"] = denoised_plan
        await self.session_manager.update_session(session)
        
        guidance = self._build_tasklist_completion_guidance(session.tasks, validation_issues)
        
        return TaskmasterResponse(
            action="create_tasklist",
            session_id=session.id,
            tasks_created=len(session.tasks),
            suggested_next_actions=["map_capabilities"],
            completion_guidance=guidance
        )

    def _validate_and_enhance_tasklist(self, raw_tasklist: List[Dict]) -> tuple[List[Dict], List[str]]:
        """Validates the tasklist and enhances it with default structures."""
        enhanced_tasks = []
        validation_issues = []
        forbidden_keywords = ["test", "validate", "verify", "document", "docs"]

        for i, task_data in enumerate(raw_tasklist):
            description = task_data.get("description", f"Unnamed Task {i+1}")
            
            # Scrub for forbidden keywords
            if any(keyword in description.lower() for keyword in forbidden_keywords):
                validation_issues.append(f"Task {i+1} ('{description}') was removed because it related to testing, validation, or documentation, which is not part of the core implementation workflow.")
                continue

            # Enhance task with default phase structure
            planning_phase = (task_data.get("planning_phase") or {}).copy()
            planning_phase.setdefault("phase_name", "planning")
            planning_phase.setdefault("description", f"Plan for: {description}")

            execution_phase = (task_data.get("execution_phase") or {}).copy()
            execution_phase.setdefault("phase_name", "execution")
            execution_phase.setdefault("description", f"Execution of: {description}")

            enhanced_task = {
                "description": description,
                "planning_phase": planning_phase,
                "execution_phase": execution_phase,
                "initial_tool_thoughts": task_data.get("initial_tool_thoughts", {"reasoning": "No initial thoughts provided."}),
                "complexity_level": self._assess_task_complexity(description),
            }
            enhanced_tasks.append(enhanced_task)
            
        return enhanced_tasks, validation_issues

    def _assess_task_complexity(self, description: str) -> str:
        """Assess task complexity based on its description."""
        desc_lower = description.lower()
        if any(word in desc_lower for word in ["system", "architecture", "framework", "integrate", "refactor"]):
            return "architectural"
        if any(word in desc_lower for word in ["implement", "create", "build", "develop", "add", "modify"]):
            return "complex"
        return "simple"

    def _build_tasklist_completion_guidance(self, tasks: List[Task], issues: List[str]) -> str:
        """Builds the final guidance message after creating a tasklist."""
        message = f"✅ **Tasklist created with {len(tasks)} tasks.**"
        if issues:
            message += "\n\n⚠️ **IMPORTANT NOTICES:**\n" + "\n".join(f"- {issue}" for issue in issues)
        
        message += "\n\n🎯 **NEXT STEP**: Use `map_capabilities` to assign your declared tools to these tasks.\n\n"
        
        message += "## Understanding Tool Mapping\n\n"
        message += "Each task has two phases that need tool assignments:\n"
        message += "- **Planning Phase**: Tools for research, analysis, and understanding\n"
        message += "- **Execution Phase**: Tools for implementation and building\n\n"
        
        message += "## Your Tasks:\n"
        for task in tasks:
            message += f"- **{task.description}** (ID: `{task.id}`)\n"
        message += "\n"
        
        message += "## Tool Assignment Structure:\n\n"
        message += "Each tool assignment needs:\n"
        message += "- `tool_name`: Exact name from your declared capabilities\n"
        message += "- `usage_purpose`: Why this tool is needed for this phase\n"
        message += "- `specific_actions`: (Optional) List of specific actions\n"
        message += "- `expected_outcome`: (Optional) What should be achieved\n"
        message += "- `priority`: (Optional) critical/normal/low\n\n"
        
        message += "**COMPLETE EXAMPLE - Copy and adapt this template:**\n\n"
        message += "```json\n"
        message += "{\n"
        message += '  "action": "map_capabilities",\n'
        message += '  "task_mappings": [\n'
        
        # Generate example for first task
        if tasks:
            task = tasks[0]
            message += '    {\n'
            message += f'      "task_id": "{task.id}",\n'
            message += '      "planning_phase": {\n'
            message += '        "assigned_builtin_tools": [\n'
            message += '          {\n'
            message += '            "tool_name": "codebase_search",\n'
            message += '            "usage_purpose": "Understand existing project structure and identify relevant files",\n'
            message += '            "specific_actions": ["Search for related components", "Understand current architecture"],\n'
            message += '            "expected_outcome": "Clear understanding of how to implement this task",\n'
            message += '            "priority": "critical"\n'
            message += '          },\n'
            message += '          {\n'
            message += '            "tool_name": "read_file",\n'
            message += '            "usage_purpose": "Read configuration files and existing code",\n'
            message += '            "priority": "normal"\n'
            message += '          }\n'
            message += '        ],\n'
            message += '        "assigned_mcp_tools": []\n'
            message += '      },\n'
            message += '      "execution_phase": {\n'
            message += '        "assigned_builtin_tools": [\n'
            message += '          {\n'
            message += '            "tool_name": "edit_file",\n'
            message += '            "usage_purpose": "Create and modify files to implement the functionality",\n'
            message += '            "specific_actions": ["Create new files", "Modify existing code"],\n'
            message += '            "expected_outcome": "Working implementation",\n'
            message += '            "priority": "critical"\n'
            message += '          },\n'
            message += '          {\n'
            message += '            "tool_name": "run_terminal_cmd",\n'
            message += '            "usage_purpose": "Test the implementation and run build commands",\n'
            message += '            "priority": "normal"\n'
            message += '          }\n'
            message += '        ],\n'
            message += '        "assigned_mcp_tools": []\n'
            message += '      }\n'
            message += '    }'
            
            # Add comma and placeholder for additional tasks
            if len(tasks) > 1:
                message += ',\n'
                message += '    {\n'
                message += f'      "task_id": "{tasks[1].id}",\n'
                message += '      "planning_phase": { "assigned_builtin_tools": [...] },\n'
                message += '      "execution_phase": { "assigned_builtin_tools": [...] }\n'
                message += '    }\n'
                message += '    // ... repeat for all tasks\n'
            else:
                message += '\n'
        
        message += '  ]\n'
        message += '}\n'
        message += "```\n\n"
        
        message += "**MAPPING TIPS:**\n"
        message += "- Use planning phase for research and understanding\n"
        message += "- Use execution phase for building and implementation\n"
        message += "- Only assign tools you actually declared in capabilities\n"
        message += "- Be specific about why each tool is needed\n"
        message += "- Critical tools should have priority: 'critical'\n\n"
        
        message += "After mapping capabilities, you'll use 'execute_next' to begin working on tasks."
        
        return message


class MapCapabilitiesHandler(BaseCommandHandler):
    """Handler for map_capabilities command."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session: 
            return TaskmasterResponse(action="map_capabilities", status="guidance", completion_guidance="No active session.")
        if not session.tasks: 
            return TaskmasterResponse(action="map_capabilities", status="guidance", completion_guidance="No tasks exist. Use `create_tasklist` first.", suggested_next_actions=["create_tasklist"])
        if not session.capabilities.built_in_tools and not session.capabilities.mcp_tools: 
            return TaskmasterResponse(action="map_capabilities", status="guidance", completion_guidance="No capabilities declared. Use `declare_capabilities` first.", suggested_next_actions=["declare_capabilities"])

        task_mappings = command.task_mappings
        if not task_mappings:
            available_tools = {
                "builtin_tools": [(tool.name, tool.description) for tool in session.capabilities.built_in_tools],
                "mcp_tools": [(tool.name, tool.description) for tool in session.capabilities.mcp_tools],
                "user_resources": [(res.name, res.description) for res in session.capabilities.user_resources],
            }
            guidance = f"""
🗺️ **MAP CAPABILITIES TO TASKS**

Assign your available tools to the planning and execution phases of each task. This provides essential context for execution.

**Your Tasks:**
{chr(10).join([f'- {task.description} (ID: {task.id})' for task in session.tasks])}

**Your Tools:**
- **Built-in:** {', '.join([t[0] for t in available_tools['builtin_tools']])}
- **MCP:** {', '.join([t[0] for t in available_tools['mcp_tools']])}
- **Resources:** {', '.join([t[0] for t in available_tools['user_resources']])}

**Example map_capabilities call:**
```json
{{
  "action": "map_capabilities",
  "task_mappings": [
    {{
      "task_id": "{session.tasks[0].id if session.tasks else 'task_id'}",
      "planning_phase": {{
        "assigned_builtin_tools": [
          {{"tool_name": "codebase_search", "usage_purpose": "To understand existing project structure."}}
        ]
      }},
      "execution_phase": {{
        "assigned_builtin_tools": [
          {{"tool_name": "edit_file", "usage_purpose": "To create and modify the script files."}},
          {{"tool_name": "run_terminal_cmd", "usage_purpose": "To run the script and check its output."}}
        ]
      }}
    }}
  ]
}}
```

🎯 **NEXT STEP**: Provide the task_mappings as shown above.
"""
            return TaskmasterResponse(
                action="map_capabilities",
                session_id=session.id,
                status="template",
                completion_guidance=guidance,
                suggested_next_actions=["map_capabilities"]
            )

        for mapping in task_mappings:
            task = next((t for t in session.tasks if t.id == mapping.get("task_id")), None)
            if not task: 
                continue

            if "planning_phase" in mapping and task.planning_phase:
                tools = mapping["planning_phase"].get("assigned_builtin_tools", [])
                setattr(task.planning_phase, 'assigned_builtin_tools', [ToolAssignment(**t) for t in tools])
                tools_mcp = mapping["planning_phase"].get("assigned_mcp_tools", [])
                setattr(task.planning_phase, 'assigned_mcp_tools', [ToolAssignment(**t) for t in tools_mcp])
            
            if "execution_phase" in mapping and task.execution_phase:
                tools = mapping["execution_phase"].get("assigned_builtin_tools", [])
                setattr(task.execution_phase, 'assigned_builtin_tools', [ToolAssignment(**t) for t in tools])
                tools_mcp = mapping["execution_phase"].get("assigned_mcp_tools", [])
                setattr(task.execution_phase, 'assigned_mcp_tools', [ToolAssignment(**t) for t in tools_mcp])

        await self.session_manager.update_session(session)
        
        return TaskmasterResponse(
            action="map_capabilities",
            session_id=session.id,
            mapping_completed=True,
            suggested_next_actions=["execute_next"],
            completion_guidance="""✅ **Capabilities mapped successfully!** You are ready to begin execution.

## What Happens Next

The workflow now enters the execution phase. You'll work through each task in sequence, with each task having two phases:

1. **Planning Phase**: Use your assigned tools to research, analyze, and understand what needs to be done
2. **Execution Phase**: Use your assigned tools to implement and build the solution

## How to Proceed

**NEXT STEP**: Use `execute_next` to get detailed guidance for your first task.

```json
{
  "action": "execute_next"
}
```

This will provide you with:
- Current task and phase information
- Detailed guidance on which tools to use
- Specific actions to take
- Expected outcomes
- Context about the task's objectives

## Execution Flow

1. **Call `execute_next`** - Get guidance for current task/phase
2. **Perform the work** - Use the assigned tools as guided
3. **Call `mark_complete`** - Progress to next phase or task
4. **Repeat** until all tasks are finished

## When You're Stuck

If you encounter issues, need clarification, or require user input:

```json
{
  "action": "collaboration_request",
  "collaboration_context": "Describe what you need help with..."
}
```

This will pause the workflow and request user assistance.

🎯 **Ready to begin!** Call `execute_next` to start working on your first task."""
        )


class ExecuteNextHandler(BaseCommandHandler):
    """Handler for execute_next command."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session: 
            return TaskmasterResponse(action="execute_next", status="guidance", completion_guidance="No active session.")
            
        next_task = next((task for task in session.tasks if task.status == "pending"), None)
        
        if not next_task:
            guidance = "🎉 **All tasks completed!** Use `end_session` to finalize."
            return TaskmasterResponse(
                action="execute_next",
                status="completed",
                completion_guidance=guidance,
                suggested_next_actions=["end_session"]
            )

        current_phase_name = next_task.current_phase or "planning"
        phase_obj = getattr(next_task, f"{current_phase_name}_phase", None)
        
        tool_guidance = self._build_tool_guidance(phase_obj) if phase_obj else "No tools assigned for this phase."

        guidance = f"""
⚡ **EXECUTE TASK: {next_task.description}**

**Phase**: {current_phase_name.upper()}
**Objective**: {phase_obj.description if phase_obj else 'No objective defined.'}

{tool_guidance}

💡 **Stuck? Need Help?**
If you cannot proceed, are stuck in a loop, or need more information from the user, you can pause the workflow at any time by calling the `collaboration_request` command. Provide context on why you are stuck.

**Example collaboration_request call:**
```json
{{
  "action": "collaboration_request",
  "collaboration_context": "I am unable to proceed because the API key for service X is missing. Please provide it."
}}
```

🎯 **NEXT STEP**: Perform the work for this phase and then call `mark_complete`.
"""
        
        return TaskmasterResponse(
            action="execute_next",
            session_id=session.id,
            current_task_id=next_task.id,
            current_task_description=next_task.description,
            current_phase=current_phase_name,
            suggested_next_actions=["mark_complete", "collaboration_request"],
            completion_guidance=guidance
        )

    def _build_tool_guidance(self, phase_obj) -> str:
        """Builds a formatted string of tool guidance for the current phase."""
        if not phase_obj: 
            return ""
        
        sections = []
        if hasattr(phase_obj, 'assigned_builtin_tools') and phase_obj.assigned_builtin_tools:
            tools = [f"- `{t.tool_name}`: {t.usage_purpose}" for t in phase_obj.assigned_builtin_tools]
            sections.append(f"**Tools for this phase:**\n" + "\n".join(tools))
        
        if hasattr(phase_obj, 'assigned_mcp_tools') and phase_obj.assigned_mcp_tools:
            tools = [f"- `{t.tool_name}`: {t.usage_purpose}" for t in phase_obj.assigned_mcp_tools]
            sections.append(f"**MCP Tools for this phase:**\n" + "\n".join(tools))

        return "\n\n".join(sections)


class MarkCompleteHandler(BaseCommandHandler):
    """Handler for mark_complete command."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session: 
            return TaskmasterResponse(action="mark_complete", status="guidance", completion_guidance="No active session.")
            
        task = next((t for t in session.tasks if t.status == "pending"), None)
        if not task:
            return TaskmasterResponse(action="mark_complete", status="completed", completion_guidance="All tasks already completed!")

        current_phase = task.current_phase or "planning"
        
        if current_phase == "planning" and task.execution_phase:
            task.current_phase = "execution"
            await self.session_manager.update_session(session)
            guidance = f"✅ **Planning phase for '{task.description}' completed.** Now progressing to EXECUTION phase. Use `execute_next` to get the details for execution."
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
            task.status = "completed"
            task.current_phase = "completed"
            await self.session_manager.update_session(session)
            
            remaining_tasks = [t for t in session.tasks if t.status == "pending"]
            if remaining_tasks:
                guidance = f"✅ **Task '{task.description}' completed!** Use `execute_next` to begin the next task."
                next_actions = ["execute_next"]
            else:
                guidance = "🎉 **All tasks completed!** Use `end_session` to finalize the workflow."
                next_actions = ["end_session"]
            
            return TaskmasterResponse(
                action="mark_complete",
                session_id=session.id,
                task_id=task.id,
                task_completed=True,
                all_tasks_completed=not remaining_tasks,
                suggested_next_actions=next_actions,
                completion_guidance=guidance
            )


class GetStatusHandler(BaseCommandHandler):
    """Handler for get_status command."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(action="get_status", status="no_session", completion_guidance="No active session. Use 'create_session' to begin.")
        
        total = len(session.tasks)
        completed = len([t for t in session.tasks if t.status == "completed"])
        pending = total - completed
        
        return TaskmasterResponse(
            action="get_status",
            session_id=session.id,
            task_summary={"total": total, "completed": completed, "pending": pending},
            tasks=[t.dict() for t in session.tasks]
        )


class CollaborationRequestHandler(BaseCommandHandler):
    """Handler for collaboration_request command."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(action="collaboration_request", status="guidance", completion_guidance="No active session.")

        session.data["paused_for_collaboration"] = True
        await self.session_manager.update_session(session)

        context = command.collaboration_context or "No context provided."
        guidance = f"""
🤝 **WORKFLOW PAUSED FOR USER COLLABORATION**

The agent has requested help with the following context:
> {context}

**To Resume Workflow**:
The user must provide feedback. The agent should then use the `edit_task` command to update the plan based on the user's response and then continue with `execute_next`.
"""
        return TaskmasterResponse(
            action="collaboration_request",
            session_id=session.id,
            status="paused",
            completion_guidance=guidance,
            suggested_next_actions=["edit_task"]
        )


class EditTaskHandler(BaseCommandHandler):
    """Handler for edit_task command, allowing in-flight task modifications."""

    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(action="edit_task", status="guidance", completion_guidance="No active session.")

        task_id = command.task_id
        updated_data = command.updated_task_data

        if not task_id or not updated_data:
            return TaskmasterResponse(
                action="edit_task",
                status="guidance",
                completion_guidance="You must provide a `task_id` and `updated_task_data`.",
                suggested_next_actions=["get_status"]
            )
        
        task_to_edit = next((t for t in session.tasks if t.id == task_id), None)
        if not task_to_edit:
            return TaskmasterResponse(action="edit_task", status="error", completion_guidance=f"Task with ID '{task_id}' not found.")
        
        # Apply updates
        if "description" in updated_data:
            task_to_edit.description = updated_data["description"]
        if "status" in updated_data:
            task_to_edit.status = updated_data["status"]
        
        # Unpause workflow after edit from collaboration
        if session.data.get("paused_for_collaboration"):
            session.data["paused_for_collaboration"] = False

        await self.session_manager.update_session(session)

        return TaskmasterResponse(
            action="edit_task",
            session_id=session.id,
            status="success",
            completion_guidance=f"✅ **Task '{task_id}' has been updated.** You can now proceed.",
            suggested_next_actions=["execute_next"]
        )


class EndSessionHandler(BaseCommandHandler):
    """Handler for end_session command."""
    
    async def handle(self, command: TaskmasterCommand) -> TaskmasterResponse:
        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(action="end_session", status="guidance", completion_guidance="No active session.")

        await self.session_manager.end_session(session.id)
        
        guidance = """
🎉 **SESSION ENDED**

The implementation work via Taskmaster is complete.

**IMPORTANT NEXT STEPS FOR THE USER:**
1. **Validation & Testing**: You must now thoroughly test the implementation to ensure it meets all requirements and is free of bugs.
2. **Documentation**: Write any necessary user or developer documentation for the new features.
3. **Deployment**: Follow your standard procedures to deploy the new code to production.

Taskmaster has completed the `plan -> execute` cycle. The responsibility for validation and documentation now rests with you.
"""
        return TaskmasterResponse(
            action="end_session",
            session_id=session.id,
            session_ended=True,
            completion_guidance=guidance,
            suggested_next_actions=["create_session"]
        )


class TaskmasterCommandHandler:
    """Main command handler that orchestrates all taskmaster operations."""
    
    def __init__(self, session_manager: SessionManager, validation_engine: ValidationEngine):
        self.session_manager = session_manager
        self.validation_engine = validation_engine
        
        # Get workflow state machine from session manager
        self.workflow_state_machine = getattr(session_manager, 'workflow_state_machine', None)
        
        self.handlers = {
            "create_session": CreateSessionHandler(session_manager, validation_engine),
            "declare_capabilities": DeclareCapabilitiesHandler(session_manager, validation_engine),
            "six_hat_thinking": SixHatThinkingHandler(session_manager, validation_engine),
            "denoise": DenoiseHandler(session_manager, validation_engine),
            "create_tasklist": CreateTasklistHandler(session_manager, validation_engine),
            "map_capabilities": MapCapabilitiesHandler(session_manager, validation_engine),
            "execute_next": ExecuteNextHandler(session_manager, validation_engine),
            "mark_complete": MarkCompleteHandler(session_manager, validation_engine),
            "get_status": GetStatusHandler(session_manager, validation_engine),
            "collaboration_request": CollaborationRequestHandler(session_manager, validation_engine),
            "edit_task": EditTaskHandler(session_manager, validation_engine),
            "end_session": EndSessionHandler(session_manager, validation_engine),
        }
        
        # Map actions to workflow events for state machine integration
        self.action_to_event = {
            "create_session": "CREATE_SESSION",
            "declare_capabilities": "DECLARE_CAPABILITIES", 
            "six_hat_thinking": "SIX_HAT_THINKING",
            "denoise": "DENOISE",
            "create_tasklist": "CREATE_TASKLIST",
            "map_capabilities": "MAP_CAPABILITIES",
            "execute_next": "EXECUTE_TASK",
            "mark_complete": "COMPLETE_TASK",
            "collaboration_request": "REQUEST_COLLABORATION",
            "edit_task": "EDIT_TASK",
            "end_session": "END_SESSION"
        }
    
    async def execute(self, command: TaskmasterCommand) -> TaskmasterResponse:
        """Execute a command using the appropriate handler with workflow state enforcement."""
        handler = self.handlers.get(command.action)
        if not handler:
            return TaskmasterResponse(
                action=command.action,
                status="guidance",
                completion_guidance=f"❌ **ERROR**: Action '{command.action}' is not recognized.\n\nAvailable actions: {', '.join(self.handlers.keys())}"
            )

        # Allow status checks and session creation without a session
        if command.action in ["get_status", "create_session"]:
            return await handler.handle(command)

        session = await self.session_manager.get_current_session()
        if not session:
            return TaskmasterResponse(action=command.action, status="guidance", completion_guidance="❌ **ERROR**: No active session. Please start with 'create_session'.")

        # --- Workflow Gating Logic ---
        
        # 1. Declare Capabilities
        if command.action == "declare_capabilities":
            if session.capabilities and (session.capabilities.built_in_tools or session.capabilities.mcp_tools):
                return self._gate_response("Capabilities already declared.", "six_hat_thinking")
        
        # 2. Six Hat Thinking (requires capabilities)
        elif command.action == "six_hat_thinking":
            if not session.capabilities or not (session.capabilities.built_in_tools or session.capabilities.mcp_tools):
                return self._gate_response("You must declare capabilities before planning.", "declare_capabilities")
            if session.data.get("six_hat_analysis"):
                return self._gate_response("Six hat thinking already completed.", "denoise")

        # 3. Denoise (requires six hat analysis)
        elif command.action == "denoise":
            if not session.data.get("six_hat_analysis"):
                return self._gate_response("You must complete the 'six_hat_thinking' step first.", "six_hat_thinking")
            if session.data.get("denoised_plan"):
                return self._gate_response("Denoising already completed.", "create_tasklist")

        # 4. Create Tasklist (requires denoised plan)
        elif command.action == "create_tasklist":
            if not session.data.get("denoised_plan"):
                return self._gate_response("You must complete the 'denoise' step to synthesize your plan first.", "denoise")
            if session.tasks:
                return self._gate_response("Tasklist has already been created.", "map_capabilities")

        # 5. Map Capabilities (requires tasklist)
        elif command.action == "map_capabilities":
            if not session.tasks:
                return self._gate_response("You must create a tasklist first.", "create_tasklist")
            # Check if any task has at least one tool assigned
            if any(t.planning_phase and getattr(t.planning_phase, 'assigned_builtin_tools', []) for t in session.tasks):
                return self._gate_response("Capabilities have already been mapped.", "execute_next")

        # 6. Execute Next (requires mapped capabilities)
        elif command.action == "execute_next":
            if not session.tasks:
                return self._gate_response("You must create a tasklist first.", "create_tasklist")
            if not any(t.planning_phase and getattr(t.planning_phase, 'assigned_builtin_tools', []) for t in session.tasks):
                return self._gate_response("You must map capabilities to tasks before execution.", "map_capabilities")

        try:
            return await handler.handle(command)
        except Exception as e:
            logger.error(f"Error executing {command.action}: {e}", exc_info=True)
            return TaskmasterResponse(
                action=command.action,
                status="error",
                completion_guidance=f"❌ **UNEXPECTED ERROR**: {str(e)}",
                error_details=str(e)
            )

    def _gate_response(self, guidance: str, next_action: str) -> TaskmasterResponse:
        """Creates a standardized workflow gate response."""
        return TaskmasterResponse(
            action="workflow_gate",
            status="guidance",
            completion_guidance=f"🚦 **WORKFLOW ALERT**: {guidance}\n\n🎯 Please use the '{next_action}' command to proceed.",
            suggested_next_actions=[next_action]
        )
    
    def add_handler(self, action: str, handler: BaseCommandHandler) -> None:
        """Add a new command handler."""
        self.handlers[action] = handler
    
    def get_available_actions(self) -> List[str]:
        """Get list of available actions."""
        return list(self.handlers.keys()) 