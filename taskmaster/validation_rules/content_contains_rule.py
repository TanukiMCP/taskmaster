from typing import Tuple, Dict, Any
from .base_rule import BaseValidationRule
from ..models import Task

class ContentContainsRule(BaseValidationRule):
 @property
 def rule_name(self) -> str:
 return "content_contains_rule"
 
 def check(self, task: Task, evidence: Dict[str, Any]) -> Tuple[bool, str]:
 """
 Check if content contains required strings/patterns.
 
 Expected evidence format:
 {
 "content": "the content to check",
 "required_strings": ["string1", "string2"], # all must be present
 "case_sensitive": false # optional, defaults to True
 }
 """
 if "content" not in evidence:
 return False, "No 'content' provided in evidence"
 
 if "required_strings" not in evidence:
 return False, "No 'required_strings' provided in evidence"
 
 content = evidence["content"]
 required_strings = evidence["required_strings"]
 case_sensitive = evidence.get("case_sensitive", True)
 
 if not isinstance(content, str):
 return False, "Content must be a string"
 
 if not isinstance(required_strings, list):
 return False, "Required strings must be a list"
 
 if not required_strings:
 return True, "No required strings specified"
 
 # Prepare content for comparison
 check_content = content if case_sensitive else content.lower()
 
 missing_strings = []
 found_strings = []
 
 for required_string in required_strings:
 if not isinstance(required_string, str):
 return False, f"Required string must be a string, got {type(required_string)}"
 
 check_string = required_string if case_sensitive else required_string.lower()
 
 if check_string in check_content:
 found_strings.append(required_string)
 else:
 missing_strings.append(required_string)
 
 if missing_strings:
 case_note = " (case-insensitive)" if not case_sensitive else ""
 return False, f"Missing required strings{case_note}: {', '.join(missing_strings)}"
 
 case_note = " (case-insensitive)" if not case_sensitive else ""
 return True, f"All required strings found{case_note}: {', '.join(found_strings)}" 