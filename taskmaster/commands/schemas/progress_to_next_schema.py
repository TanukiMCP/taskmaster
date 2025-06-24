from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class ProgressToNextPayload(BaseModel):
    """
    Payload schema for progressing a session to the next phase or task.
    """
    session_id: str = Field(..., description="The ID of the session to progress.")
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional metadata for the progress event."
    )
