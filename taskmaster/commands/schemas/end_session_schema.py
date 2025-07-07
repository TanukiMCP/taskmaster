from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class EndSessionPayload(BaseModel):
 """
 Payload schema for ending a session.
 """
 session_id: str = Field(..., description="The ID of the session to end.")
 metadata: Optional[Dict[str, Any]] = Field(
 default_factory=dict,
 description="Additional metadata for the session end event."
 )
