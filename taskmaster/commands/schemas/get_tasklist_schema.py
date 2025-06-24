from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class GetTasklistPayload(BaseModel):
    """
    Payload schema for retrieving the task list for a session.
    """
    session_id: str = Field(..., description="The ID of the session to retrieve tasks from.")
    status: Optional[str] = Field(None, description="Filter tasks by status (e.g., 'pending', 'completed').")
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional metadata for the request."
    )
