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
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self._rules: Dict[str, BaseValidationRule] = {}
        self._config = config or {}
        self._advisory_mode = self._config.get('advisory_mode', True)
        self._strict_rules = set(self._config.get('strict_rules', []))
        self._disabled_rules = set(self._config.get('disabled_rules', []))
        
        self._load_validation_rules()
        
        logger.info(f"ValidationEngine initialized with {len(self._rules)} rules")
        logger.info(f"Advisory mode: {self._advisory_mode}")
        if self._strict_rules:
            logger.info(f"Strict rules: {list(self._strict_rules)}")
        if self._disabled_rules:
            logger.info(f"Disabled rules: {list(self._disabled_rules)}")
    
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
        Validate a task against its validation phase criteria using the provided evidence.
        
        Args:
            task: The task to validate
            evidence: Evidence provided for validation
            
        Returns:
            Tuple of (all_passed, messages) where messages contains success/failure details
            In advisory mode: all_passed will be True unless a critical error occurs
            In strict mode: all_passed reflects actual validation results
        """
        # Check if task has a validation phase
        if not task.validation_phase:
            return True, ["No validation phase defined for this task"]
        
        # Use default validation criteria if none specified
        validation_criteria = getattr(task.validation_phase, 'validation_criteria', [])
        if not validation_criteria:
            # Default validation criteria based on available rules
            validation_criteria = ["completeness_rule", "syntax_rule"]
        
        # Track validation results
        all_passed = True
        messages = []
        warnings = []
        failures = []
        
        for criterion in validation_criteria:
            if criterion not in self._rules:
                warning_msg = f"Unknown validation rule: {criterion}"
                warnings.append(warning_msg)
                logger.warning(warning_msg)
                continue
            
            rule = self._rules[criterion]
            try:
                passed, message = rule.check(task, evidence)
                
                if passed:
                    messages.append(f"✅ {criterion}: {message}")
                    logger.debug(f"Validation passed for {criterion}: {message}")
                else:
                    failure_msg = f"❌ {criterion}: {message}"
                    
                    # Check if this rule should be strict
                    is_strict_rule = criterion in self._strict_rules
                    is_strict_mode = not self._advisory_mode
                    
                    if is_strict_rule or is_strict_mode:
                        failures.append(failure_msg)
                        all_passed = False
                        logger.warning(f"Strict validation failed for {criterion}: {message}")
                    else:
                        warnings.append(failure_msg)
                        logger.info(f"Advisory validation warning for {criterion}: {message}")
                        
            except Exception as e:
                error_msg = f"⚠️ {criterion}: Error during validation - {str(e)}"
                logger.error(f"Validation error for {criterion}: {e}")
                
                # Validation errors are always treated as failures
                failures.append(error_msg)
                all_passed = False
        
        # Compile final messages
        if failures:
            messages.append("🚨 VALIDATION FAILURES:")
            messages.extend(failures)
        
        if warnings and self._advisory_mode:
            messages.append("⚠️ VALIDATION WARNINGS (advisory only):")
            messages.extend(warnings)
        
        # Log validation summary
        if failures:
            logger.warning(f"Task {task.id} validation failed with {len(failures)} failures")
        elif warnings:
            logger.info(f"Task {task.id} validation passed with {len(warnings)} warnings")
        else:
            logger.info(f"Task {task.id} validation passed completely")
        
        return all_passed, messages
    
    def get_available_rules(self) -> List[str]:
        """Return a list of all available validation rule names"""
        return list(self._rules.keys())
    
    def get_rule_info(self, rule_name: str) -> Optional[Dict]:
        """Get information about a specific validation rule"""
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
        return {
            "total_rules": len(self._rules),
            "available_rules": list(self._rules.keys()),
            "strict_rules": list(self._strict_rules),
            "disabled_rules": list(self._disabled_rules),
            "advisory_mode": self._advisory_mode,
            "config": self._config
        }
    
    def set_advisory_mode(self, advisory: bool) -> None:
        """Set the validation engine to advisory or strict mode"""
        self._advisory_mode = advisory
        logger.info(f"Validation engine advisory mode set to: {advisory}")
    
    def add_strict_rule(self, rule_name: str) -> bool:
        """Add a rule to the strict rules list"""
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
        self._load_validation_rules()
        new_count = len(self._rules)
        
        stats = {
            "old_rule_count": old_count,
            "new_rule_count": new_count,
            "reloaded_rules": list(self._rules.keys())
        }
        
        logger.info(f"Reloaded validation rules: {old_count} -> {new_count}")
        return stats 