import importlib
import inspect
import os
from typing import Dict, List, Tuple
from .models import Task
from .validation_rules.base_rule import BaseValidationRule

class ValidationEngine:
    """
    Dynamic validation engine that loads all validation rules from the validation_rules directory
    and orchestrates validation checks for tasks.
    """
    
    def __init__(self):
        self._rules: Dict[str, BaseValidationRule] = {}
        self._load_validation_rules()
    
    def _load_validation_rules(self):
        """Dynamically load all validation rule classes from the validation_rules directory"""
        rules_dir = os.path.join(os.path.dirname(__file__), 'validation_rules')
        
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
                            self._rules[rule_instance.rule_name] = rule_instance
                            
                except Exception as e:
                    print(f"Warning: Could not load validation rule from {filename}: {e}")
    
    def validate(self, task: Task, evidence: dict) -> Tuple[bool, List[str]]:
        """
        Validate a task against its validation criteria using the provided evidence.
        
        Args:
            task: The task to validate
            evidence: Evidence provided for validation
            
        Returns:
            Tuple of (all_passed, messages) where messages contains success/failure details
        """
        if not task.validation_required:
            return True, ["Validation not required for this task"]
        
        if not task.validation_criteria:
            return True, ["No validation criteria defined for this task"]
        
        all_passed = True
        messages = []
        
        for criterion in task.validation_criteria:
            if criterion not in self._rules:
                all_passed = False
                messages.append(f"Unknown validation rule: {criterion}")
                continue
            
            rule = self._rules[criterion]
            try:
                passed, message = rule.check(task, evidence)
                messages.append(f"{criterion}: {message}")
                if not passed:
                    all_passed = False
            except Exception as e:
                all_passed = False
                messages.append(f"{criterion}: Error during validation - {str(e)}")
        
        return all_passed, messages
    
    def get_available_rules(self) -> List[str]:
        """Return a list of all available validation rule names"""
        return list(self._rules.keys()) 