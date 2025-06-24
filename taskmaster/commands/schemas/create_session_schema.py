from pydantic import BaseModel, Field
from typing import Dict, Any, Optional

class CreateSessionPayload(BaseModel):
    """
    Payload schema for creating a new session
    """
    user_id: str = Field(..., description="Unique identifier for the user")
    session_name: str = Field(..., description="Name of the session")
    initial_environment_scan: bool = Field(
        default=True,
        description="Whether to perform an initial environment scan"
    )
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional metadata for the session"
    )
