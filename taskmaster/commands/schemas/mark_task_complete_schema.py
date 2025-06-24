from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class MarkTaskCompletePayload(BaseModel):
    """
    Payload schema for marking a task as complete within a session.
    """
    session_id: str = Field(..., description="The ID of the session containing the task.")
    task_id: str = Field(..., description="The ID of the task to be marked as complete.")
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional metadata for the completion event."
    )
