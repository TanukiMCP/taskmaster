"""
Completeness validation rule that enforces actual implementation
and prevents placeholders, hardcoded values, and corner-cutting.
"""

import re
from typing import Tuple, Dict, Any
from .base_rule import BaseValidationRule
from ..models import Task


class CompletenessRule(BaseValidationRule):
    """
    Validation rule that enforces completeness and prevents:
    - Placeholder implementations (TODO, FIXME, etc.)
    - Hardcoded values that should be dynamic
    - Incomplete implementations
    - Corner-cutting patterns
    """
    
    def __init__(self):
        super().__init__()
        self.rule_name = "completeness"
        
        # Patterns that indicate incomplete implementation
        self.placeholder_patterns = [
            r'(?i)\btodo\b',
            r'(?i)\bfixme\b',
            r'(?i)\bplaceholder\b',
            r'(?i)\btemporary\b',
            r'(?i)\bhardcoded\b',
            r'(?i)\bmock\b(?!\s+test)',  # Mock but not mock test
            r'(?i)\bstub\b',
            r'(?i)\bdummy\b',
            r'(?i)\bfake\b',
            r'(?i)not\s+implemented',
            r'(?i)to\s+be\s+implemented',
            r'(?i)implement\s+later',
            r'(?i)add\s+later',
            r'(?i)fill\s+in',
            r'(?i)replace\s+with',
            r'(?i)example\s+value',
            r'(?i)sample\s+data',
            r'pass\s*$',  # Python pass statement at end of line
            r'return\s+None\s*$',  # Return None without context
            r'raise\s+NotImplementedError',
            r'\.\.\.(?!\s*\))',  # Ellipsis not in function signature
        ]
        
        # Patterns that indicate hardcoded values
        self.hardcoded_patterns = [
            r'localhost:\d+',
            r'127\.0\.0\.1',
            r'admin:password',
            r'test@example\.com',
            r'secret_key_123',
            r'api_key_here',
            r'your_token_here',
            r'replace_me',
            r'change_this',
        ]
    
    def check(self, task: Task, evidence: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Check if the task implementation is complete and doesn't contain placeholders.
        
        Args:
            task: The task being validated
            evidence: Evidence provided for validation (should contain implementation details)
            
        Returns:
            Tuple of (passed, message)
        """
        if not evidence:
            return False, "No evidence provided for completeness validation"
        
        # Get implementation content from evidence
        implementation_content = ""
        if isinstance(evidence, dict):
            # Look for various evidence fields
            for key in ['implementation', 'code', 'content', 'output', 'result', 'execution_evidence']:
                if key in evidence and evidence[key]:
                    implementation_content += str(evidence[key]) + "\n"
        else:
            implementation_content = str(evidence)
        
        if not implementation_content.strip():
            return False, "No implementation content found in evidence"
        
        # Check for placeholder patterns
        placeholder_issues = []
        for pattern in self.placeholder_patterns:
            matches = re.findall(pattern, implementation_content)
            if matches:
                placeholder_issues.extend(matches)
        
        if placeholder_issues:
            return False, f"Implementation contains placeholders/incomplete code: {', '.join(set(placeholder_issues))}"
        
        # Check for hardcoded values
        hardcoded_issues = []
        for pattern in self.hardcoded_patterns:
            matches = re.findall(pattern, implementation_content)
            if matches:
                hardcoded_issues.extend(matches)
        
        if hardcoded_issues:
            return False, f"Implementation contains hardcoded values that should be configurable: {', '.join(set(hardcoded_issues))}"
        
        # Check for minimum implementation length (prevents trivial implementations)
        if len(implementation_content.strip()) < 50:
            return False, "Implementation appears too minimal - provide more substantial evidence of completion"
        
        # Check for actual functionality indicators
        functionality_indicators = [
            r'def\s+\w+\s*\(',  # Function definitions
            r'class\s+\w+',     # Class definitions
            r'import\s+\w+',    # Import statements
            r'from\s+\w+',      # From imports
            r'if\s+\w+',        # Conditional logic
            r'for\s+\w+',       # Loops
            r'while\s+\w+',     # While loops
            r'try:',            # Error handling
            r'except\s+\w+',    # Exception handling
            r'return\s+\w+',    # Return statements with values
            r'print\s*\(',      # Output statements
            r'log\w*\s*\(',     # Logging statements
        ]
        
        functionality_count = 0
        for pattern in functionality_indicators:
            if re.search(pattern, implementation_content):
                functionality_count += 1
        
        if functionality_count < 2:
            return False, "Implementation lacks sufficient functional complexity - appears incomplete"
        
        return True, "Implementation appears complete with no placeholders or hardcoded values" 