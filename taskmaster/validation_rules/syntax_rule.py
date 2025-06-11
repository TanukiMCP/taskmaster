from .base_rule import BaseValidationRule
from ..models import Task

class SyntaxRule(BaseValidationRule):
    @property
    def rule_name(self) -> str:
        return "syntax_rule"
    
    def check(self, task: Task, evidence: dict) -> tuple[bool, str]:
        """
        Check if the provided code has valid syntax.
        
        Expected evidence format:
        {
            "code": "the code to validate",
            "language": "python|javascript|etc" (optional, defaults to python)
        }
        """
        if "code" not in evidence:
            return False, "No code provided in evidence for syntax validation"
        
        code = evidence["code"]
        language = evidence.get("language", "python").lower()
        
        if not code.strip():
            return False, "Empty code provided"
        
        # Validate Python syntax
        if language == "python":
            try:
                compile(code, '<string>', 'exec')
                return True, "Python syntax is valid"
            except SyntaxError as e:
                return False, f"Python syntax error: {e.msg} at line {e.lineno}"
        
        # For other languages, do basic checks
        elif language in ["javascript", "js"]:
            # Basic JavaScript syntax checks
            if code.count("{") != code.count("}"):
                return False, "Mismatched braces in JavaScript code"
            if code.count("(") != code.count(")"):
                return False, "Mismatched parentheses in JavaScript code"
            return True, "Basic JavaScript syntax checks passed"
        
        else:
            # Generic validation for unknown languages
            if len(code.strip()) > 0:
                return True, f"Code provided for {language} (basic validation passed)"
            else:
                return False, "No meaningful code content" 