from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any

class DefineValidationCriteriaPayload(BaseModel):
    """
    Payload schema for defining validation criteria for a task.
    """
    session_id: str = Field(..., description="The ID of the session containing the task.")
    task_id: str = Field(..., description="The ID of the task to define validation criteria for.")
    criteria: List[str] = Field(..., description="A list of strings defining the validation criteria.")
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="Additional metadata for the validation criteria."
    )
