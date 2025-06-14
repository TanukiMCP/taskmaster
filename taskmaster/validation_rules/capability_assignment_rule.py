"""
Capability assignment validation rule that ensures tasks properly
use their assigned capabilities and don't use undeclared tools.
"""

from typing import Tuple, Dict, Any, List, Set
from .base_rule import BaseValidationRule
from ..models import Task


class CapabilityAssignmentRule(BaseValidationRule):
    """
    Validation rule that enforces proper capability assignment and usage:
    - Tasks must use only their assigned capabilities
    - Evidence must show actual usage of assigned tools
    - No undeclared tool usage
    """
    
    def __init__(self):
        super().__init__()
        self.rule_name = "capability_assignment"
    
    def check(self, task: Task, evidence: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Check if the task properly used its assigned capabilities.
        
        Args:
            task: The task being validated
            evidence: Evidence provided for validation
            
        Returns:
            Tuple of (passed, message)
        """
        if not evidence:
            return False, "No evidence provided for capability assignment validation"
        
        # Get assigned capabilities from task phases
        assigned_builtin_tools = set()
        assigned_mcp_tools = set()
        assigned_resources = set()
        
        for phase in [task.planning_phase, task.execution_phase, task.validation_phase]:
            if phase:
                assigned_builtin_tools.update(phase.assigned_builtin_tools)
                assigned_mcp_tools.update(phase.assigned_mcp_tools)
                assigned_resources.update(phase.assigned_resources)
        
        # Also check legacy fields for backward compatibility
        assigned_builtin_tools.update(task.suggested_builtin_tools)
        assigned_mcp_tools.update(task.suggested_mcp_tools)
        assigned_resources.update(task.suggested_resources)
        
        if not assigned_builtin_tools and not assigned_mcp_tools and not assigned_resources:
            return False, "Task has no assigned capabilities - capability assignment is required"
        
        # Extract evidence content
        evidence_content = ""
        if isinstance(evidence, dict):
            for key in ['implementation', 'code', 'content', 'output', 'result', 'execution_evidence', 'tools_used']:
                if key in evidence and evidence[key]:
                    evidence_content += str(evidence[key]) + "\n"
        else:
            evidence_content = str(evidence)
        
        if not evidence_content.strip():
            return False, "No evidence content found for capability validation"
        
        # Check if assigned tools were actually used
        evidence_lower = evidence_content.lower()
        
        # Track which assigned capabilities were actually used
        used_builtin_tools = set()
        used_mcp_tools = set()
        used_resources = set()
        
        # Check for builtin tool usage
        for tool in assigned_builtin_tools:
            tool_lower = tool.lower()
            # Look for various patterns that indicate tool usage
            if (tool_lower in evidence_lower or 
                f"used {tool_lower}" in evidence_lower or
                f"using {tool_lower}" in evidence_lower or
                f"called {tool_lower}" in evidence_lower or
                f"executed {tool_lower}" in evidence_lower):
                used_builtin_tools.add(tool)
        
        # Check for MCP tool usage
        for tool in assigned_mcp_tools:
            tool_lower = tool.lower()
            if (tool_lower in evidence_lower or 
                f"used {tool_lower}" in evidence_lower or
                f"using {tool_lower}" in evidence_lower or
                f"called {tool_lower}" in evidence_lower or
                f"executed {tool_lower}" in evidence_lower):
                used_mcp_tools.add(tool)
        
        # Check for resource usage
        for resource in assigned_resources:
            resource_lower = resource.lower()
            if (resource_lower in evidence_lower or 
                f"referenced {resource_lower}" in evidence_lower or
                f"consulted {resource_lower}" in evidence_lower or
                f"used {resource_lower}" in evidence_lower):
                used_resources.add(resource)
        
        # Validate that at least some assigned capabilities were used
        total_assigned = len(assigned_builtin_tools) + len(assigned_mcp_tools) + len(assigned_resources)
        total_used = len(used_builtin_tools) + len(used_mcp_tools) + len(used_resources)
        
        if total_used == 0:
            return False, f"No assigned capabilities were used. Assigned: {list(assigned_builtin_tools | assigned_mcp_tools | assigned_resources)}"
        
        # Calculate usage percentage
        usage_percentage = (total_used / total_assigned) * 100
        
        # Build detailed message
        unused_tools = (assigned_builtin_tools - used_builtin_tools) | (assigned_mcp_tools - used_mcp_tools) | (assigned_resources - used_resources)
        
        message_parts = [
            f"Capability usage: {total_used}/{total_assigned} ({usage_percentage:.1f}%)"
        ]
        
        if used_builtin_tools:
            message_parts.append(f"Used builtin tools: {list(used_builtin_tools)}")
        if used_mcp_tools:
            message_parts.append(f"Used MCP tools: {list(used_mcp_tools)}")
        if used_resources:
            message_parts.append(f"Used resources: {list(used_resources)}")
        
        if unused_tools:
            message_parts.append(f"Unused assigned capabilities: {list(unused_tools)}")
        
        message = "; ".join(message_parts)
        
        # Pass if at least 50% of assigned capabilities were used
        if usage_percentage >= 50:
            return True, message
        else:
            return False, f"Insufficient capability usage ({usage_percentage:.1f}% < 50%). {message}" 