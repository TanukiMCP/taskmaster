from abc import ABC, abstractmethod
from typing import Dict, Any


class BaseScanner(ABC):
    """Abstract base class for all environment scanners."""
    
    @property
    @abstractmethod
    def scanner_name(self) -> str:
        """Return the name of this scanner."""
        pass
    
    @abstractmethod
    async def scan(self) -> Dict[str, Any]:
        """
        Perform the environment scan.
        
        Returns:
            Dict[str, Any]: Scanner results in a structured format
        """
        pass 