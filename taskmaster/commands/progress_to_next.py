# taskmaster/commands/progress_to_next.py
import os
import json
import logging
import asyncio
from typing import Dict, Any
from pydantic import ValidationError
from .base_command import BaseCommand
from ..models import Session
from ..config import get_config
from taskmaster.session_manager import SessionManager
from taskmaster.commands.schemas.progress_to_next_schema import ProgressToNextPayload

class Command(BaseCommand):
    def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            validated_payload = ProgressToNextPayload(**payload)
        except ValidationError as e:
            logging.error(f"Validation error in ProgressToNextCommand: {e.errors()}")
            return {"status": "error", "message": "Invalid payload", "details": e.errors()}

        config = get_config()
        session_manager = SessionManager(state_dir=config.get_state_directory())

        try:
            session = asyncio.run(session_manager.get_session_async(validated_payload.session_id))
            if not session:
                return {"status": "error", "message": f"Session {validated_payload.session_id} not found"}

            # Find next incomplete task
            incomplete_tasks = [task for task in session.tasks if task.status != "completed"]
            
            if not incomplete_tasks:
                return {
                    "status": "all_complete",
                    "message": "All tasks in session are complete",
                    "total_tasks": len(session.tasks),
                    "completed_tasks": len([t for t in session.tasks if t.status == "completed"])
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
                    "completed": len([t for t in session.tasks if t.status == "completed"]),
                    "total": len(session.tasks),
                    "remaining": len(incomplete_tasks)
                }
            }
        except Exception as e:
            logging.error(f"Error progressing session {validated_payload.session_id}: {e}")
            return {"status": "error", "message": f"Failed to progress session: {e}"}
