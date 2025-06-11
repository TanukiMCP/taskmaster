import json
import os
from .base_command import BaseCommand
from ..models import Session

class Command(BaseCommand):
    def execute(self, payload: dict) -> dict:
        """
        Define validation criteria for a specific task.
        
        Expected payload:
        {
            "session_id": "session_...",
            "task_id": "task_...",
            "criteria": ["syntax_rule", "other_rule"],
            "validation_required": true (optional, defaults to True if criteria provided)
        }
        """
        try:
            session_id = payload.get("session_id")
            task_id = payload.get("task_id")
            criteria = payload.get("criteria", [])
            validation_required = payload.get("validation_required", True if criteria else False)
            
            if not session_id:
                return {"error": "session_id is required"}
            
            if not task_id:
                return {"error": "task_id is required"}
            
            if not isinstance(criteria, list):
                return {"error": "criteria must be a list"}
            
            # Load the session
            session_file = f"taskmaster/state/{session_id}.json"
            if not os.path.exists(session_file):
                return {"error": f"Session {session_id} not found"}
            
            with open(session_file, 'r') as f:
                session_data = json.load(f)
            
            session = Session(**session_data)
            
            # Find the task
            task_found = False
            for task in session.tasks:
                if task.id == task_id:
                    task.validation_criteria = criteria
                    task.validation_required = validation_required
                    task_found = True
                    break
            
            if not task_found:
                return {"error": f"Task {task_id} not found in session"}
            
            # Save the updated session
            with open(session_file, 'w') as f:
                json.dump(session.model_dump(), f, indent=2)
            
            return {
                "success": True,
                "task_id": task_id,
                "validation_criteria": criteria,
                "validation_required": validation_required,
                "message": f"Validation criteria updated for task {task_id}"
            }
            
        except Exception as e:
            return {"error": f"Failed to define validation criteria: {str(e)}"} 