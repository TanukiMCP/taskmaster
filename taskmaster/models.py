from __future__ import annotations
import uuid
from typing import List, Optional
from pydantic import BaseModel, Field
from .workflow_state_machine import WorkflowState
from datetime import datetime


class Task(BaseModel):
    """Simplified task model - just description and status."""
    id: str = Field(default_factory=lambda: f"task_{uuid.uuid4()}")
    description: str
    status: str = "pending"  # "pending" or "completed"


class Session(BaseModel):
    """Simplified session model - just tasks and state."""
    id: str = Field(default_factory=lambda: f"session_{uuid.uuid4()}")
    name: Optional[str] = "Default Session"
    task_description: Optional[str] = None
    tasks: List[Task] = []
    workflow_state: str = Field(default=WorkflowState.SESSION_CREATED.value)
    created_at: datetime = Field(default_factory=datetime.now)

    class Config:
        arbitrary_types_allowed = True


class TaskmasterData(BaseModel):
    """Container for all sessions."""
    sessions: List[Session] = []
