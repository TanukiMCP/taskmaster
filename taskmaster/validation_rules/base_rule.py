from abc import ABC, abstractmethod
from ..models import Task

class BaseValidationRule(ABC):
    @property
    @abstractmethod
    def rule_name(self) -> str:
        """Return the name of this validation rule"""
        pass

    @abstractmethod
    def check(self, task: Task, evidence: dict) -> tuple[bool, str]:
        """
        Check if the task satisfies this validation rule given the evidence.
        
        Args:
            task: The task to validate
            evidence: Evidence provided for validation
            
        Returns:
            Tuple of (is_valid, message)
        """
        pass 