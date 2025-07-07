import importlib
import inspect
import os
import logging
from typing import Dict, List, Tuple, Optional
from .models import Task
from .validation_rules.base_rule import BaseValidationRule

logger = logging.getLogger(__name__)

class ValidationEngine:
    """
    Dynamic validation engine that loads all validation rules from the validation_rules directory
    and orchestrates validation checks for tasks.
    
    Supports both strict and advisory validation modes with configurable rule loading.
    Uses lazy loading for Smithery compatibility.
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self._rules: Dict[str, BaseValidationRule] = {}
        self._config = config or {}
        self._advisory_mode = self._config.get('advisory_mode', True)
        self._strict_rules = set(self._config.get('strict_rules', []))
        self._disabled_rules = set(self._config.get('disabled_rules', []))
        self._rules_loaded = False
        
        # Defer rule loading until actually needed for Smithery tool discovery optimization
        logger.info(f"ValidationEngine created with deferred rule loading")
        logger.info(f"Advisory mode: {self._advisory_mode}")
        if self._strict_rules:
            logger.info(f"Strict rules configured: {list(self._strict_rules)}")
        if self._disabled_rules:
            logger.info(f"Disabled rules configured: {list(self._disabled_rules)}")
    
    def _ensure_rules_loaded(self):
        """Ensure validation rules are loaded - called only when needed."""
        if not self._rules_loaded:
            self._load_validation_rules()
            self._rules_loaded = True
    
    def _load_validation_rules(self):
        """Dynamically load all validation rule classes from the validation_rules directory"""
        rules_dir = os.path.join(os.path.dirname(__file__), 'validation_rules')
        loaded_rules = []
        failed_rules = []
        
        # Get all Python files in the validation_rules directory
        for filename in os.listdir(rules_dir):
            if filename.endswith('.py') and not filename.startswith('__') and filename != 'base_rule.py':
                module_name = filename[:-3]  # Remove .py extension
                
                try:
                    # Import the module
                    module = importlib.import_module(f'.validation_rules.{module_name}', package=__package__)
                    
                    # Find all classes that inherit from BaseValidationRule
                    for name, obj in inspect.getmembers(module, inspect.isclass):
                        if (issubclass(obj, BaseValidationRule) and 
                            obj != BaseValidationRule and 
                            obj.__module__ == module.__name__):
                            
                            # Instantiate the rule and register it
                            rule_instance = obj()
                            rule_name = rule_instance.rule_name
                            
                            # Check if rule is disabled
                            if rule_name in self._disabled_rules:
                                logger.info(f"Skipping disabled validation rule: {rule_name}")
                                continue
                            
                            self._rules[rule_name] = rule_instance
                            loaded_rules.append(rule_name)
                            logger.debug(f"Loaded validation rule: {rule_name}")
                            
                except Exception as e:
                    error_msg = f"Could not load validation rule from {filename}: {e}"
                    logger.error(error_msg)
                    failed_rules.append((filename, str(e)))
        
        logger.info(f"Successfully loaded {len(loaded_rules)} validation rules: {loaded_rules}")
        if failed_rules:
            logger.warning(f"Failed to load {len(failed_rules)} validation rules: {[f[0] for f in failed_rules]}")
    
    def validate(self, task: Task, evidence: dict) -> Tuple[bool, List[str]]:
        """
        Enhanced validation with anti-hallucination safeguards and performance optimization.
        
        Args:
            task: The task to validate
            evidence: Evidence provided for validation
            
        Returns:
            Tuple of (all_passed, messages) where messages contains success/failure details
        """
        # Ensure rules are loaded when validation is actually needed
        self._ensure_rules_loaded()
        
        # Fast path: Check if task has a validation phase
        validation_phase = getattr(task, 'validation_phase', None)
        if not validation_phase:
            return True, ["✅ No validation phase defined - task auto-validated"]
        
        # Enhanced anti-hallucination checks
        anti_hallucination_passed, anti_hall_messages = self._validate_anti_hallucination(task, evidence)
        
        # Use default validation criteria if none specified
        validation_criteria = getattr(validation_phase, 'validation_criteria', [])
        if not validation_criteria:
            # Smart defaults based on task complexity
            if task.complexity_level == "architectural":
                validation_criteria = ["completeness_rule", "test_integrity_rule", "capability_assignment_rule"]
            elif task.complexity_level == "complex":
                validation_criteria = ["completeness_rule", "syntax_rule"]
            else:
                validation_criteria = ["completeness_rule"]
        
        # Optimized validation execution
        all_passed = anti_hallucination_passed
        messages = anti_hall_messages.copy()
        warnings = []
        failures = []
        
        # Batch process validation rules for efficiency
        valid_criteria = [c for c in validation_criteria if c in self._rules]
        invalid_criteria = [c for c in validation_criteria if c not in self._rules]
        
        # Handle invalid criteria efficiently
        if invalid_criteria:
            warnings.extend([f"⚠️ Unknown validation rule: {c}" for c in invalid_criteria])
        
        # Execute valid rules with error handling
        for criterion in valid_criteria:
            rule = self._rules[criterion]
            try:
                passed, message = rule.check(task, evidence)
                
                if passed:
                    messages.append(f"✅ {criterion}: {message}")
                else:
                    failure_msg = f"❌ {criterion}: {message}"
                    
                    # Optimized strictness check
                    if criterion in self._strict_rules or not self._advisory_mode:
                        failures.append(failure_msg)
                        all_passed = False
                    else:
                        warnings.append(failure_msg)
                        
            except Exception as e:
                error_msg = f"⚠️ {criterion}: Validation error - {str(e)}"
                failures.append(error_msg)
                all_passed = False
                logger.error(f"Validation error for {criterion}: {e}")
        
        # Compile optimized final messages
        if failures:
            messages.extend(["🚨 VALIDATION FAILURES:"] + failures)
        
        if warnings and self._advisory_mode:
            messages.extend(["⚠️ VALIDATION WARNINGS:"] + warnings)
        
        # Performance logging
        if failures:
            logger.warning(f"Task {task.id} validation failed: {len(failures)} failures")
        else:
            logger.info(f"Task {task.id} validation passed: {len(valid_criteria)} rules checked")
        
        return all_passed, messages
    
    def _validate_anti_hallucination(self, task: Task, evidence: dict) -> Tuple[bool, List[str]]:
        """Enhanced anti-hallucination validation with reality checking."""
        messages = []
        all_passed = True
        
        # Check for required evidence based on task complexity
        if task.complexity_level in ["complex", "architectural"]:
            required_evidence = self._get_required_evidence(task)
            missing_evidence = []
            
            for req in required_evidence:
                if req not in evidence or not evidence[req]:
                    missing_evidence.append(req)
            
            if missing_evidence:
                all_passed = False
                messages.append(f"🚨 ANTI-HALLUCINATION: Missing required evidence: {', '.join(missing_evidence)}")
            else:
                messages.append("✅ ANTI-HALLUCINATION: Required evidence provided")
        
        # Validate console output reality
        console_output = evidence.get("console_output", "")
        if console_output:
            if self._validate_console_output_reality(console_output):
                messages.append("✅ REALITY CHECK: Console output appears authentic")
            else:
                all_passed = False
                messages.append("🚨 REALITY CHECK: Console output appears fabricated or suspicious")
        
        # Validate file changes reality
        file_changes = evidence.get("file_changes", [])
        if file_changes:
            valid_changes = self._validate_file_changes_reality(file_changes)
            if valid_changes:
                messages.append(f"✅ REALITY CHECK: {len(file_changes)} file changes verified")
            else:
                all_passed = False
                messages.append("🚨 REALITY CHECK: File changes appear invalid or fabricated")
        
        # Check for hallucination indicators
        hallucination_indicators = self._detect_hallucination_indicators(evidence)
        if hallucination_indicators:
            all_passed = False
            messages.append(f"🚨 HALLUCINATION DETECTED: {', '.join(hallucination_indicators)}")
        
        return all_passed, messages
    
    def _get_required_evidence(self, task: Task) -> List[str]:
        """Get required evidence types based on task complexity and type."""
        base_evidence = ["evidence"]
        
        if task.complexity_level == "complex":
            base_evidence.extend(["console_output"])
        
        if task.complexity_level == "architectural":
            base_evidence.extend(["console_output", "file_changes"])
        
        # Check if task involves file operations
        task_desc = task.description.lower()
        if any(word in task_desc for word in ["file", "create", "write", "modify", "delete"]):
            base_evidence.append("file_changes")
        
        return base_evidence
    
    def _validate_console_output_reality(self, console_output: str) -> bool:
        """Validate that console output appears real and not fabricated."""
        if not console_output or len(console_output.strip()) < 10:
            return False
        
        # Check for common fabrication indicators
        fabrication_indicators = [
            "should work", "would output", "might show", "example output",
            "something like", "similar to", "pseudo-output", "mock result"
        ]
        
        lower_output = console_output.lower()
        if any(indicator in lower_output for indicator in fabrication_indicators):
            return False
        
        # Check for realistic console patterns
        realistic_patterns = [
            "error:", "warning:", "info:", "debug:", "success:",
            "failed", "completed", "processing", "loading",
            "file not found", "permission denied", "syntax error"
        ]
        
        return any(pattern in lower_output for pattern in realistic_patterns)
    
    def _validate_file_changes_reality(self, file_changes: List[str]) -> bool:
        """Validate that file changes appear real and specific."""
        if not file_changes:
            return False
        
        for change in file_changes:
            if not isinstance(change, str) or len(change.strip()) < 5:
                return False
            
            # Check for vague or fabricated descriptions
            vague_indicators = [
                "some file", "example file", "test file", "sample file",
                "would create", "should modify", "might update"
            ]
            
            if any(indicator in change.lower() for indicator in vague_indicators):
                return False
        
        return True
    
    def _detect_hallucination_indicators(self, evidence: dict) -> List[str]:
        """Detect common hallucination patterns in evidence."""
        indicators = []
        
        # Check evidence descriptions for hallucination patterns
        evidence_text = " ".join([str(v) for v in evidence.values() if isinstance(v, str)])
        lower_text = evidence_text.lower()
        
        hallucination_patterns = [
            ("assumption_language", ["i assume", "should work", "would probably", "likely to"]),
            ("vague_claims", ["successfully completed", "working as expected", "no issues found"]),
            ("future_tense", ["will create", "will modify", "will update", "will show"]),
            ("hypothetical", ["if this works", "assuming it", "provided that", "in case"]),
            ("generic_responses", ["task completed", "operation successful", "no errors"])
        ]
        
        for pattern_name, patterns in hallucination_patterns:
            if any(pattern in lower_text for pattern in patterns):
                indicators.append(pattern_name)
        
        return indicators
    
    def get_available_rules(self) -> List[str]:
        """Return a list of all available validation rule names"""
        self._ensure_rules_loaded()
        return list(self._rules.keys())
    
    def get_rule_info(self, rule_name: str) -> Optional[Dict]:
        """Get information about a specific validation rule"""
        self._ensure_rules_loaded()
        
        if rule_name not in self._rules:
            return None
        
        rule = self._rules[rule_name]
        return {
            "name": rule.rule_name,
            "description": getattr(rule, 'description', 'No description available'),
            "is_strict": rule_name in self._strict_rules,
            "is_disabled": rule_name in self._disabled_rules,
            "class_name": rule.__class__.__name__
        }
    
    def get_validation_stats(self) -> Dict:
        """Get statistics about the validation engine"""
        # Only load rules if they haven't been loaded yet and stats are requested
        if self._rules_loaded:
            available_rules = list(self._rules.keys())
            total_rules = len(self._rules)
        else:
            available_rules = ["Rules not loaded yet - will load on first validation"]
            total_rules = 0
        
        return {
            "total_rules": total_rules,
            "available_rules": available_rules,
            "strict_rules": list(self._strict_rules),
            "disabled_rules": list(self._disabled_rules),
            "advisory_mode": self._advisory_mode,
            "rules_loaded": self._rules_loaded,
            "config": self._config
        }
    
    def set_advisory_mode(self, advisory: bool) -> None:
        """Set the validation engine to advisory or strict mode"""
        self._advisory_mode = advisory
        logger.info(f"Validation engine advisory mode set to: {advisory}")
    
    def add_strict_rule(self, rule_name: str) -> bool:
        """Add a rule to the strict rules list"""
        self._ensure_rules_loaded()
        
        if rule_name in self._rules:
            self._strict_rules.add(rule_name)
            logger.info(f"Added {rule_name} to strict rules")
            return True
        return False
    
    def remove_strict_rule(self, rule_name: str) -> bool:
        """Remove a rule from the strict rules list"""
        if rule_name in self._strict_rules:
            self._strict_rules.remove(rule_name)
            logger.info(f"Removed {rule_name} from strict rules")
            return True
        return False
    
    def reload_rules(self) -> Dict:
        """Reload all validation rules and return statistics"""
        old_count = len(self._rules)
        self._rules.clear()
        self._rules_loaded = False
        self._ensure_rules_loaded()
        new_count = len(self._rules)
        
        stats = {
            "old_rule_count": old_count,
            "new_rule_count": new_count,
            "reloaded_rules": list(self._rules.keys())
        }
        
        logger.info(f"Reloaded validation rules: {old_count} -> {new_count}")
        return stats 