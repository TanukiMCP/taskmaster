from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class GetEnvironmentPayload(BaseModel):
    """
    Payload schema for retrieving environment information for a session.
    """
    session_id: str = Field(..., description="The ID of the session to retrieve environment from.")
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional metadata for the request."
    )
