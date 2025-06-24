from pydantic import BaseModel, Field
from typing import Optional, Dict, Any

class GetValidationRulesPayload(BaseModel):
    """
    Payload schema for retrieving available validation rules.
    """
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional metadata for the request."
    )
