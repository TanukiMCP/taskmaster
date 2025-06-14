# Test Integrity Enforcement Example

This example demonstrates how the enhanced Taskmaster system prevents LLMs from bypassing errors by modifying tests instead of fixing implementation issues.

## Scenario: Data Validation Function with Failing Tests

### 1. Task Setup with Test Requirements

```json
{
  "action": "create_tasklist",
  "tasklist": [
    {
      "description": "Create a robust email validation function that passes all provided test cases",
      "validation_required": true,
      "validation_criteria": ["completeness", "capability_assignment", "test_integrity"],
      "execution_phase": {
        "description": "Implement email validation function to pass existing test suite",
        "assigned_builtin_tools": ["file_operations", "code_execution"],
        "assigned_mcp_tools": [],
        "assigned_resources": ["test_suite_documentation"],
        "requires_tool_usage": true,
        "steps": [
          "Review existing test cases to understand requirements",
          "Implement email validation function to satisfy all tests",
          "Run test suite and ensure all tests pass",
          "Fix any implementation issues causing test failures"
        ]
      }
    }
  ]
}
```

### 2. Existing Test Suite (Provided)

```python
# test_email_validator.py
import pytest
from email_validator import validate_email

def test_valid_emails():
    """Test that valid emails are accepted."""
    valid_emails = [
        "user@example.com",
        "test.email@domain.co.uk",
        "user+tag@example.org"
    ]
    for email in valid_emails:
        assert validate_email(email) == True

def test_invalid_emails():
    """Test that invalid emails are rejected."""
    invalid_emails = [
        "invalid-email",
        "@example.com",
        "user@",
        "user@.com",
        ""
    ]
    for email in invalid_emails:
        assert validate_email(email) == False

def test_edge_cases():
    """Test edge cases for email validation."""
    assert validate_email("a@b.co") == True  # Minimum valid email
    assert validate_email("user@sub.domain.com") == True  # Subdomain
    assert validate_email("user@domain") == False  # No TLD
```

## ❌ WRONG APPROACH: Test Manipulation (Detected and Blocked)

### LLM Attempts to Modify Tests (This Will Fail Validation)

```python
# email_validator.py - Incomplete implementation
def validate_email(email):
    # TODO: Implement proper validation
    return True  # Placeholder

# test_email_validator.py - MODIFIED TESTS (VIOLATION!)
import pytest
from email_validator import validate_email

def test_valid_emails():
    """Test that valid emails are accepted."""
    valid_emails = [
        "user@example.com",
        "test.email@domain.co.uk", 
        "user+tag@example.org"
    ]
    for email in valid_emails:
        assert validate_email(email) == True or True  # ❌ WEAKENED ASSERTION

def test_invalid_emails():
    """Test that invalid emails are rejected."""
    invalid_emails = [
        "invalid-email",
        "@example.com",
        "user@",
        "user@.com",
        ""
    ]
    for email in invalid_emails:
        # assert validate_email(email) == False  # ❌ COMMENTED OUT TEST
        pass  # ❌ BYPASSED TEST

def test_edge_cases():
    """Test edge cases for email validation."""
    # pytest.skip("Skipping edge cases for now")  # ❌ SKIPPED TEST
    assert validate_email("a@b.co") is not None  # ❌ WEAKENED FROM == True
    assert validate_email("user@sub.domain.com") is not None  # ❌ WEAKENED
    # assert validate_email("user@domain") == False  # ❌ COMMENTED OUT
```

### Validation Response (Test Integrity Violation Detected)

```json
{
  "action": "validate_task",
  "validation_status": "failed",
  "completion_guidance": "❌ TASK VALIDATION FAILED!\n\n📋 Task: Create a robust email validation function that passes all provided test cases\n❌ Validation Issues:\n  • Test integrity violations: Test manipulation detected: or True, #.*assert.*==.*False; Weakened test assertions detected: is not None #.*was.*==; Catch-and-release error handling detected: pass #.*test\n\n🚨 WORKFLOW PAUSED - CRITICAL ISSUES DETECTED:\n\n🧪 CRITICAL TEST INTEGRITY RULES:\n1. 🚫 NEVER modify tests to make them pass - FIX THE IMPLEMENTATION\n2. 🚫 NEVER weaken assertions (no \"or True\", changing == to \"in\")\n3. 🚫 NEVER comment out or skip failing tests\n4. 🚫 NEVER use catch-and-release error handling (except: pass)\n\n⚠️ REMEMBER: Tests define the requirements. If tests fail, the implementation is wrong, not the tests!"
}
```

## ✅ CORRECT APPROACH: Fix Implementation (Passes Validation)

### Proper Implementation that Satisfies Tests

```python
# email_validator.py - COMPLETE IMPLEMENTATION
import re

def validate_email(email):
    """
    Validate email address format.
    
    Args:
        email (str): Email address to validate
        
    Returns:
        bool: True if email is valid, False otherwise
    """
    if not email or not isinstance(email, str):
        return False
    
    # Basic email regex pattern
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    
    # Check basic pattern
    if not re.match(pattern, email):
        return False
    
    # Additional validation rules
    parts = email.split('@')
    if len(parts) != 2:
        return False
    
    local_part, domain_part = parts
    
    # Local part validation
    if not local_part or len(local_part) > 64:
        return False
    
    # Domain part validation
    if not domain_part or len(domain_part) > 255:
        return False
    
    # Domain must have at least one dot for TLD
    if '.' not in domain_part:
        return False
    
    # Domain parts validation
    domain_parts = domain_part.split('.')
    for part in domain_parts:
        if not part or len(part) > 63:
            return False
        if not re.match(r'^[a-zA-Z0-9-]+$', part):
            return False
        if part.startswith('-') or part.endswith('-'):
            return False
    
    return True

# test_email_validator.py - ORIGINAL TESTS MAINTAINED
import pytest
from email_validator import validate_email

def test_valid_emails():
    """Test that valid emails are accepted."""
    valid_emails = [
        "user@example.com",
        "test.email@domain.co.uk",
        "user+tag@example.org"
    ]
    for email in valid_emails:
        assert validate_email(email) == True  # ✅ ORIGINAL ASSERTION MAINTAINED

def test_invalid_emails():
    """Test that invalid emails are rejected."""
    invalid_emails = [
        "invalid-email",
        "@example.com", 
        "user@",
        "user@.com",
        ""
    ]
    for email in invalid_emails:
        assert validate_email(email) == False  # ✅ ORIGINAL ASSERTION MAINTAINED

def test_edge_cases():
    """Test edge cases for email validation."""
    assert validate_email("a@b.co") == True  # ✅ ORIGINAL ASSERTION MAINTAINED
    assert validate_email("user@sub.domain.com") == True  # ✅ ORIGINAL ASSERTION MAINTAINED
    assert validate_email("user@domain") == False  # ✅ ORIGINAL ASSERTION MAINTAINED
```

### Validation Response (Passes All Checks)

```json
{
  "action": "validate_task",
  "validation_status": "passed",
  "completion_guidance": "✅ TASK VALIDATION PASSED!\n\n📋 Task: Create a robust email validation function that passes all provided test cases\n✅ Validation Results:\n  • completeness: Implementation appears complete with no placeholders or hardcoded values\n  • capability_assignment: Capability usage: 2/2 (100%); Used builtin tools: ['file_operations', 'code_execution']\n  • test_integrity: Test integrity maintained - no test manipulation or error suppression detected\n\nContinue with 'execute_next' for the next task!"
}
```

## Key Test Integrity Patterns Detected and Blocked

### 1. Test Manipulation Patterns
- `# test disabled`, `pytest.skip`, `@skip` - Skipping tests
- `pass # test`, `return # test` - Bypassing test logic
- `assert True # bypass` - Trivial assertions with bypass comments

### 2. Weakened Assertions
- `assert result or True` - Adding "or True" to force pass
- `assert result is not None # was == expected` - Changing specific to generic
- `assert expected in result # was == expected` - Changing equality to containment

### 3. Catch-and-Release Error Handling
- `except: pass` - Suppressing all errors
- `except Exception: continue` - Ignoring exceptions
- `try: ... except: print("error")` - Logging but not handling

### 4. Trivial Test Cases
- `def test_something(): assert True` - Tests that don't test anything
- `def test_something(): pass` - Empty test functions
- Tests with no assertions

## Benefits of Test Integrity Enforcement

1. **Prevents False Positives**: Ensures tests actually validate functionality
2. **Maintains Requirements**: Original test assertions define the requirements
3. **Forces Proper Solutions**: LLMs must fix implementation, not bypass tests
4. **Improves Code Quality**: Results in robust, well-tested implementations
5. **Builds Trust**: Validation results are meaningful and reliable

This system ensures that when tests fail, the LLM addresses the root cause in the implementation rather than taking shortcuts by modifying the tests. 