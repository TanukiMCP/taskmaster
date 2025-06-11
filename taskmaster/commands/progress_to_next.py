# taskmaster/commands/progress_to_next.py
import json
import os
from typing import Dict, Any
from .base_command import BaseCommand
from ..models import Session

class Command(BaseCommand):
    def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        Progress to the next incomplete task in the session.
        
        Args:
            payload: Dict containing 'session_id'
            
        Returns:
            Dict with next task info or error
        """
        try:
            session_id = payload.get("session_id")
            if not session_id:
                return {"error": "session_id is required"}
            
            # Load session
            session_file = f"taskmaster/state/{session_id}.json"
            if not os.path.exists(session_file):
                return {"error": f"Session '{session_id}' not found"}
            
            with open(session_file, 'r') as f:
                session_data = json.load(f)
            
            session = Session(**session_data)
            
            # Find next incomplete task
            incomplete_tasks = [task for task in session.tasks if task.status == "[ ]"]
            
            if not incomplete_tasks:
                return {
                    "status": "all_complete",
                    "message": "All tasks in session are complete",
                    "total_tasks": len(session.tasks),
                    "completed_tasks": len([t for t in session.tasks if t.status == "[X]"])
                }
            
            next_task = incomplete_tasks[0]
            current_index = session.tasks.index(next_task)
            
            return {
                "status": "next_task_found",
                "next_task": {
                    "id": next_task.id,
                    "description": next_task.description,
                    "status": next_task.status,
                    "validation_required": next_task.validation_required,
                    "validation_criteria": next_task.validation_criteria,
                    "index": current_index + 1,
                    "total": len(session.tasks)
                },
                "progress": {
                    "completed": len([t for t in session.tasks if t.status == "[X]"]),
                    "total": len(session.tasks),
                    "remaining": len(incomplete_tasks)
                }
            }
            
        except Exception as e:
            return {"error": f"Failed to progress to next task: {str(e)}"} 