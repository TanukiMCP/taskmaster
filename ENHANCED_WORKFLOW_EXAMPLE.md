# Enhanced Taskmaster Workflow Example

This example demonstrates the enhanced capability assignment, validation enforcement, and memory palace integration features.

## 1. Session Creation & Capability Declaration

```json
{
  "action": "create_session",
  "session_name": "enhanced_workflow_demo"
}
```

```json
{
  "action": "declare_capabilities",
  "builtin_tools": [
    {
      "name": "file_operations",
      "description": "Read, write, and manipulate files",
      "what_it_is": "Built-in file system operations",
      "what_it_does": "Allows reading file contents, writing new files, and modifying existing files",
      "how_to_use": "Use for any task requiring file manipulation, code creation, or content modification",
      "relevant_for": ["file_creation", "code_writing", "content_editing", "data_processing"]
    },
    {
      "name": "code_execution",
      "description": "Execute code and scripts",
      "what_it_is": "Built-in code execution environment",
      "what_it_does": "Runs Python, JavaScript, and shell commands with output capture",
      "how_to_use": "Use for testing implementations, running scripts, and validating functionality",
      "relevant_for": ["testing", "validation", "script_execution", "debugging"]
    }
  ],
  "mcp_tools": [
    {
      "name": "memory_update",
      "server_name": "memory_palace",
      "description": "Update memory palace with knowledge",
      "what_it_is": "MCP tool for persistent knowledge management",
      "what_it_does": "Stores concepts, relationships, and learnings in a persistent memory system",
      "how_to_use": "Use after task completion to capture learnings and insights",
      "relevant_for": ["knowledge_capture", "learning_storage", "pattern_recognition"]
    }
  ],
  "user_resources": [
    {
      "name": "project_documentation",
      "type": "documentation",
      "description": "Project requirements and specifications",
      "what_it_is": "Comprehensive project documentation and requirements",
      "what_it_does": "Provides context, requirements, and specifications for implementation",
      "how_to_use": "Reference for understanding requirements and making implementation decisions",
      "relevant_for": ["requirement_analysis", "implementation_guidance", "validation_criteria"]
    }
  ]
}
```

## 2. Enhanced Tasklist Creation with Capability Assignment

```json
{
  "action": "create_tasklist",
  "tasklist": [
    {
      "description": "Create a Python utility function for data validation",
      "validation_required": true,
      "validation_criteria": ["completeness", "capability_assignment"],
      "memory_palace_enabled": true,
      "planning_phase": {
        "description": "Plan the data validation utility implementation",
        "assigned_builtin_tools": ["file_operations"],
        "assigned_mcp_tools": [],
        "assigned_resources": ["project_documentation"],
        "requires_tool_usage": true,
        "steps": [
          "Review project documentation for validation requirements",
          "Design function signature and parameters",
          "Plan validation logic and error handling",
          "Determine test cases and edge cases"
        ]
      },
      "execution_phase": {
        "description": "Implement the data validation utility function",
        "assigned_builtin_tools": ["file_operations", "code_execution"],
        "assigned_mcp_tools": [],
        "assigned_resources": ["project_documentation"],
        "requires_tool_usage": true,
        "steps": [
          "Create the Python file with proper imports",
          "Implement the validation function with comprehensive logic",
          "Add proper error handling and logging",
          "Create unit tests for the function",
          "Test the implementation with various inputs"
        ]
      },
      "validation_phase": {
        "description": "Validate the implementation completeness and functionality",
        "assigned_builtin_tools": ["code_execution"],
        "assigned_mcp_tools": [],
        "assigned_resources": [],
        "requires_tool_usage": true,
        "steps": [
          "Run all unit tests and verify they pass",
          "Test with edge cases and invalid inputs",
          "Verify error handling works correctly",
          "Check code quality and completeness",
          "Document the implementation and usage"
        ]
      }
    }
  ]
}
```

## 3. Task Execution with Enforcement

```json
{
  "action": "execute_next"
}
```

**Response includes:**
- Detailed capability assignments for each phase
- Anti-hallucination enforcement rules
- Specific steps to follow
- Validation criteria requirements
- Collaboration guidance

## 4. Task Validation with Evidence

```json
{
  "action": "validate_task",
  "evidence": "Created data_validator.py with complete implementation:\n\n```python\nimport re\nfrom typing import Any, Dict, List, Optional\nimport logging\n\nlogger = logging.getLogger(__name__)\n\nclass DataValidator:\n    def __init__(self):\n        self.validation_rules = {\n            'email': r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$',\n            'phone': r'^\\+?1?\\d{9,15}$'\n        }\n    \n    def validate_data(self, data: Dict[str, Any], rules: Dict[str, str]) -> Dict[str, Any]:\n        \"\"\"Validate data against specified rules.\"\"\"\n        results = {'valid': True, 'errors': []}\n        \n        for field, rule in rules.items():\n            if field not in data:\n                results['valid'] = False\n                results['errors'].append(f'Missing required field: {field}')\n                continue\n            \n            if rule in self.validation_rules:\n                pattern = self.validation_rules[rule]\n                if not re.match(pattern, str(data[field])):\n                    results['valid'] = False\n                    results['errors'].append(f'Invalid {field}: {data[field]}')\n        \n        return results\n```\n\nImplementation includes:\n- Complete class with proper initialization\n- Comprehensive validation logic\n- Error handling and reporting\n- Type hints for better code quality\n- Logging integration\n- No placeholders or hardcoded values\n- Full unit test suite created and passing",
  "execution_evidence": "Used file_operations to create data_validator.py, code_execution to run tests, referenced project_documentation for requirements. All assigned capabilities utilized as planned."
}
```

## 5. Memory Palace Integration (if validation passes)

```json
{
  "action": "update_memory_palace",
  "workspace_path": "/c:/Users/ididi/memory_palace",
  "task_id": "task_12345",
  "learnings": [
    "Data validation requires comprehensive regex patterns for different data types",
    "Type hints improve code maintainability and IDE support",
    "Proper error reporting is crucial for debugging validation failures"
  ],
  "what_worked": [
    "Using a class-based approach for extensible validation rules",
    "Implementing comprehensive error collection rather than failing fast",
    "Creating reusable validation patterns"
  ],
  "what_didnt_work": [
    "Initial attempt at simple string matching was too basic",
    "Hardcoded validation rules would have been inflexible"
  ],
  "insights": [
    "Validation systems benefit from being both strict and informative",
    "Extensible design patterns pay off even for simple utilities"
  ],
  "patterns": [
    "Class-based validators with rule dictionaries provide good extensibility",
    "Collecting all validation errors before returning improves user experience"
  ]
}
```

## Key Enforcement Features Demonstrated

### 1. Capability Assignment Validation
- Tasks MUST declare specific capabilities for each phase
- Only declared capabilities can be used
- Validation fails if undeclared tools are referenced

### 2. Completeness Enforcement
- Prevents TODO, FIXME, placeholder implementations
- Detects hardcoded values that should be configurable
- Requires substantial implementation evidence
- Validates functional complexity

### 3. Anti-Hallucination Measures
- Strict capability boundary enforcement
- Evidence-based validation
- Workflow pausing on validation failures
- Collaboration requests for ambiguous situations

### 4. Memory Palace Integration
- Captures learnings after successful task completion
- Stores patterns, anti-patterns, and insights
- Builds persistent knowledge base
- Enables continuous improvement

### 5. Workflow Control
- Automatic pausing on validation failures
- Collaboration requests for clarification
- Evidence-based progression
- Structured phase execution

This enhanced system ensures high-quality, complete implementations while building a knowledge base for continuous improvement. 