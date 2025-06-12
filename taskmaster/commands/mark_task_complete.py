import json
import os
from datetime import datetime
from .base_command import BaseCommand
from ..models import Session
from ..validation_engine import ValidationEngine
from ..config import get_config

class Command(BaseCommand):
    def execute(self, payload: dict) -> dict:
        """
        Mark a task as complete, running validation if required.
        
        Expected payload:
        {
            "session_id": "session_...",
            "task_id": "task_...",
            "evidence": {...}  # Evidence for validation (if validation_required is True)
        }
        """
        try:
            session_id = payload.get("session_id")
            task_id = payload.get("task_id")
            evidence = payload.get("evidence", {})
            
            if not session_id:
                return {"error": "session_id is required"}
            
            if not task_id:
                return {"error": "task_id is required"}
            
            # Get config using the singleton
            config = get_config()
            
            # Load the session
            state_dir = config.get_state_directory()
            session_file = os.path.join(state_dir, f"{session_id}.json")
            
            if not os.path.exists(session_file):
                return {"error": f"Session {session_id} not found"}
            
            with open(session_file, 'r') as f:
                session_data = json.load(f)
            
            session = Session(**session_data)
            
            # Find the task
            target_task = None
            for task in session.tasks:
                if task.id == task_id:
                    target_task = task
                    break
            
            if not target_task:
                return {"error": f"Task {task_id} not found in session"}
            
            # Check if task is already complete
            if target_task.status == "[X]":
                return {
                    "status": "already_complete",
                    "task_id": task_id,
                    "message": "Task is already marked as complete"
                }
            
            # Run validation if required
            validation_messages = []
            if target_task.validation_required:
                validation_engine = ValidationEngine()
                validation_passed, messages = validation_engine.validate(target_task, evidence)
                validation_messages = messages
                
                if not validation_passed:
                    return {
                        "status": "validation_failed",
                        "task_id": task_id,
                        "validation_messages": validation_messages,
                        "message": "Task validation failed. Task remains incomplete."
                    }
                
                # Store the evidence if validation passed
                if evidence:
                    target_task.evidence.append({
                        "timestamp": datetime.now().isoformat(),
                        "evidence": evidence,
                        "validation_result": "passed"
                    })
            
            # Mark task as complete
            target_task.status = "[X]"
            
            # Save the updated session
            with open(session_file, 'w') as f:
                json.dump(session.model_dump(), f, indent=2)
            
            result = {
                "status": "complete",
                "task_id": task_id,
                "message": "Task marked as complete"
            }
            
            if validation_messages:
                result["validation_messages"] = validation_messages
            
            return result
            
        except Exception as e:
            return {"error": f"Failed to mark task complete: {str(e)}"} 