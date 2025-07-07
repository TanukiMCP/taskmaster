"""
Test integrity validation rule that provides guidance to LLMs
about potential test manipulation patterns.
"""

import re
from typing import Tuple, Dict, Any, List
from .base_rule import BaseValidationRule
from ..models import Task


class TestIntegrityRule(BaseValidationRule):
 """
 Validation rule that provides guidance on test integrity and flags:
 - Modifying tests to bypass failures instead of fixing issues
 - Weakening test assertions to make them pass
 - Removing or commenting out failing tests
 - Creating fake/superficial test solutions
 - Catch-and-release error handling without proper resolution
 
 This rule is advisory only and will not block workflow progress.
 """
 
 @property
 def rule_name(self) -> str:
 """Return the name of this validation rule."""
 return "test_integrity"
 
 def __init__(self):
 super().__init__()
 
 # Patterns that indicate test manipulation/weakening
 self.test_manipulation_patterns = [
 r'(?i)#.*test.*disabled?',
 r'(?i)#.*skip.*test',
 r'(?i)pytest\.skip',
 r'(?i)unittest\.skip',
 r'(?i)@skip',
 r'(?i)@pytest\.mark\.skip',
 r'(?i)pass\s*#.*test',
 r'(?i)return\s*#.*test',
 r'(?i)assert\s+True\s*#.*bypass',
 r'(?i)assert\s+True\s*#.*temp',
 r'(?i)assert\s+1\s*==\s*1', # Trivial assertions
 r'(?i)assert\s+True\s*$', # Bare assert True
 ]
 
 # Patterns that indicate weakened assertions
 self.weakened_assertion_patterns = [
 r'assert\s+.*\s+or\s+True', # Adding "or True" to make assertions pass
 r'assert\s+True\s+or\s+', # Leading with True
 r'assert\s+.*\s+is\s+not\s+None\s*#.*was.*==', # Changing specific checks to generic
 r'assert\s+len\([^)]+\)\s*>\s*0\s*#.*was.*==', # Changing exact checks to existence checks
 r'assert\s+.*\s+in\s+.*\s*#.*was.*==', # Changing equality to containment
 ]
 
 # Patterns that indicate catch-and-release error handling
 self.catch_release_patterns = [
 r'except.*:\s*pass\s*$',
 r'except.*:\s*continue\s*$',
 r'except.*:\s*return\s*$',
 r'except.*:\s*print\s*\(',
 r'except.*:\s*log\w*\s*\(',
 r'try:.*except.*pass',
 r'(?i)#.*ignore.*error',
 r'(?i)#.*suppress.*error',
 r'(?i)#.*todo.*fix.*error',
 ]
 
 # Patterns that indicate proper error handling
 self.proper_error_handling_patterns = [
 r'except.*:\s*raise',
 r'except.*as\s+\w+:.*raise.*from',
 r'except.*:\s*return.*error',
 r'except.*:\s*logger\.error',
 r'except.*:\s*sys\.exit',
 ]
 
 def check(self, task: Task, evidence: Dict[str, Any]) -> Tuple[bool, str]:
 """
 Check if the task implementation maintains test integrity and doesn't bypass issues.
 
 Args:
 task: The task being validated
 evidence: Evidence provided for validation
 
 Returns:
 Tuple of (passed, message) - always passes but provides guidance
 """
 if not evidence:
 return True, "No evidence provided for test integrity validation (advisory only)"
 
 # Get implementation content from evidence
 implementation_content = ""
 test_content = ""
 
 if isinstance(evidence, dict):
 # Look for implementation and test content
 for key in ['implementation', 'code', 'content', 'output', 'result', 'execution_evidence']:
 if key in evidence and evidence[key]:
 content = str(evidence[key])
 implementation_content += content + "\n"
 
 # Identify test content
 if any(test_indicator in content.lower() for test_indicator in 
 ['test_', 'def test', 'class test', 'unittest', 'pytest', 'assert']):
 test_content += content + "\n"
 else:
 implementation_content = str(evidence)
 if any(test_indicator in implementation_content.lower() for test_indicator in 
 ['test_', 'def test', 'class test', 'unittest', 'pytest', 'assert']):
 test_content = implementation_content
 
 if not implementation_content.strip():
 return True, "No implementation content found in evidence (advisory only)"
 
 issues = []
 
 # Check for test manipulation patterns
 test_manipulation_issues = []
 for pattern in self.test_manipulation_patterns:
 matches = re.findall(pattern, implementation_content, re.MULTILINE)
 if matches:
 test_manipulation_issues.extend(matches)
 
 if test_manipulation_issues:
 issues.append(f"Test manipulation detected: {', '.join(set(test_manipulation_issues))}")
 
 # Check for weakened assertions
 weakened_assertion_issues = []
 for pattern in self.weakened_assertion_patterns:
 matches = re.findall(pattern, implementation_content, re.MULTILINE)
 if matches:
 weakened_assertion_issues.extend(matches)
 
 if weakened_assertion_issues:
 issues.append(f"Weakened test assertions detected: {', '.join(set(weakened_assertion_issues))}")
 
 # Check for catch-and-release error handling
 catch_release_issues = []
 for pattern in self.catch_release_patterns:
 matches = re.findall(pattern, implementation_content, re.MULTILINE)
 if matches:
 catch_release_issues.extend(matches)
 
 if catch_release_issues:
 issues.append(f"Catch-and-release error handling detected: {', '.join(set(catch_release_issues))}")
 
 # If we have test content, perform additional validation
 if test_content:
 test_issues = self._validate_test_content(test_content)
 issues.extend(test_issues)
 
 # Check for proper error handling patterns
 proper_error_handling = False
 for pattern in self.proper_error_handling_patterns:
 if re.search(pattern, implementation_content, re.MULTILINE):
 proper_error_handling = True
 break
 
 # If there are try/except blocks but no proper error handling, flag it
 try_except_count = len(re.findall(r'try:', implementation_content))
 if try_except_count > 0 and not proper_error_handling:
 issues.append("Try/except blocks found but no proper error handling (errors may be suppressed)")
 
 if issues:
 return True, f"ADVISORY - Test integrity guidance: {'; '.join(issues)}"
 
 return True, "Test integrity appears good - no test manipulation or error suppression detected"
 
 def _validate_test_content(self, test_content: str) -> List[str]:
 """Validate specific test content for integrity issues."""
 issues = []
 
 # Check for trivial test cases
 trivial_patterns = [
 r'def test_\w+\([^)]*\):\s*assert True',
 r'def test_\w+\([^)]*\):\s*pass',
 r'def test_\w+\([^)]*\):\s*return',
 ]
 
 for pattern in trivial_patterns:
 if re.search(pattern, test_content, re.MULTILINE):
 issues.append("Trivial test cases detected (tests that don't actually test anything)")
 
 # Check for test count reduction (if we can detect it)
 commented_tests = len(re.findall(r'#.*def test_', test_content))
 if commented_tests > 0:
 issues.append(f"{commented_tests} test(s) appear to be commented out")
 
 # Check for assertion count - should have meaningful assertions
 assertion_count = len(re.findall(r'assert\s+', test_content))
 test_function_count = len(re.findall(r'def test_', test_content))
 
 if test_function_count > 0 and assertion_count == 0:
 issues.append("Test functions found but no assertions detected")
 elif test_function_count > 0 and assertion_count < test_function_count:
 issues.append(f"Some test functions may lack assertions ({assertion_count} assertions for {test_function_count} tests)")
 
 # Check for overly generic assertions
 generic_assertions = len(re.findall(r'assert\s+\w+\s+is\s+not\s+None', test_content))
 if generic_assertions > assertion_count * 0.5: # More than 50% are generic
 issues.append("Too many generic 'is not None' assertions - tests may be weakened")
 
 return issues 