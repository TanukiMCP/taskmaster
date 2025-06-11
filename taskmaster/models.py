from pydantic import BaseModel, Field
from typing import List, Optional
import uuid

class Task(BaseModel):
    id: str = Field(default_factory=lambda: f"task_{uuid.uuid4()}")
    description: str
    status: str = "[ ]" # Enforce "[ ]" or "[X]"
    # Fields for Phase 2
    validation_required: bool = False
    validation_criteria: List[str] = []
    evidence: List[dict] = []

class Session(BaseModel):
    id: str = Field(default_factory=lambda: f"session_{uuid.uuid4()}")
    tasks: List[Task] = []
    # Field for Phase 3
    environment_map: Optional[dict] = None 