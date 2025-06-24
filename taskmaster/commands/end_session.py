# taskmaster/commands/end_session.py
import logging
import asyncio
import os
import json
from typing import Dict, Any
from datetime import datetime
from pydantic import ValidationError
from .base_command import BaseCommand
from ..models import Session
from ..config import get_config
from taskmaster.session_manager import SessionManager
from taskmaster.commands.schemas.end_session_schema import EndSessionPayload

class Command(BaseCommand):
    def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            validated_payload = EndSessionPayload(**payload)
        except ValidationError as e:
            logging.error(f"Validation error in EndSessionCommand: {e.errors()}")
            return {"status": "error", "message": "Invalid payload", "details": e.errors()}

        config = get_config()
        session_manager = SessionManager(state_dir=config.get_state_directory())

        try:
            session = asyncio.run(session_manager.get_session_async(validated_payload.session_id))
            if not session:
                return {"status": "error", "message": f"Session {validated_payload.session_id} not found"}

            # End the session using SessionManager
            asyncio.run(session_manager.end_session(validated_payload.session_id))
            logging.info(f"Session {validated_payload.session_id} ended.")

            # Generate comprehensive summary (simplified for now, can be enhanced later)
            completed_tasks = [task for task in session.tasks if task.status == "completed"]
            total_tasks = len(session.tasks)
            completion_rate = (len(completed_tasks) / total_tasks * 100) if total_tasks > 0 else 0

            summary = {
                "session_id": session.id,
                "ended_at": datetime.now().isoformat(),
                "statistics": {
                    "total_tasks": total_tasks,
                    "completed_tasks": len(completed_tasks),
                    "completion_rate": round(completion_rate, 2),
                },
                "message": f"Session ended. Completed {len(completed_tasks)}/{total_tasks} tasks ({completion_rate:.1f}%)"
            }
            
            return {"status": "success", "summary": summary}
        except Exception as e:
            logging.error(f"Error ending session {validated_payload.session_id}: {e}")
            return {"status": "error", "message": f"Failed to end session: {e}"}
