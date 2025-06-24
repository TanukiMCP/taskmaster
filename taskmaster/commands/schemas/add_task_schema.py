from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class AddTaskPayload(BaseModel):
    """
    Payload schema for adding a new task to a session.
    """
    session_id: str = Field(..., description="The ID of the session to add the task to.")
    description: str = Field(..., description="The description of the task to be added.")
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional metadata for the task."
    )
