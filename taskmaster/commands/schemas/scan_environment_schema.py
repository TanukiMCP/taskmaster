from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class ScanEnvironmentPayload(BaseModel):
    """
    Payload schema for triggering an environment scan for a session.
    """
    session_id: str = Field(..., description="The ID of the session to scan the environment for.")
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional metadata for the scan request."
    )
