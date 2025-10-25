from __future__ import annotations
import uuid
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field
from .workflow_state_machine import WorkflowState
from datetime import datetime


class Task(BaseModel):
    id: str = Field(default_factory=lambda: f"task_{uuid.uuid4()}")
    description: str
    status: str = "pending"  # "pending", "completed"


class Session(BaseModel):
    id: str = Field(default_factory=lambda: f"session_{uuid.uuid4()}")
    name: str = "Default Session"
    description: str = ""
    tasks: List[Task] = []
    current_task_index: int = 0
    workflow_state: str = Field(default=WorkflowState.SESSION_CREATED.value)

    class Config:
        arbitrary_types_allowed = True


class TaskmasterData(BaseModel):
    sessions: List[Session] = []
