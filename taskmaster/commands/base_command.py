from abc import ABC, abstractmethod
from ..models import Session

class BaseCommand(ABC):
    @abstractmethod
    def execute(self, payload: dict) -> dict:
        pass 