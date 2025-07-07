from abc import ABC, abstractmethod
from typing import Dict, Any
from ..models import Session

class BaseCommand(ABC):
 @abstractmethod
 def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
 pass 