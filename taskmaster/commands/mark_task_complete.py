import os
import json
import logging
import asyncio
from datetime import datetime
from typing import Dict, Any
from pydantic import ValidationError
from .base_command import BaseCommand
from ..models import Session
from ..validation_engine import ValidationEngine
from ..config import get_config
from taskmaster.session_manager import SessionManager
from taskmaster.commands.schemas.mark_task_complete_schema import MarkTaskCompletePayload

class Command(BaseCommand):
    def execute(self, payload: dict) -> dict:
        try:
            validated_payload = MarkTaskCompletePayload(**payload)
        except ValidationError as e:
            logging.error(f"Validation error in MarkTaskCompleteCommand: {e.errors()}")
            return {"status": "error", "message": "Invalid payload", "details": e.errors()}

        config = get_config()
        session_manager = SessionManager(state_dir=config.get_state_directory())

        try:
            session = asyncio.run(session_manager.get_session_async(validated_payload.session_id))
            if not session:
                return {"status": "error", "message": f"Session {validated_payload.session_id} not found"}

            target_task = None
            for task in session.tasks:
                if task.id == validated_payload.task_id:
                    target_task = task
                    break

            if not target_task:
                return {"status": "error", "message": f"Task {validated_payload.task_id} not found in session {validated_payload.session_id}"}

            if target_task.status == "completed": # Assuming "completed" is the status for completed tasks
                return {
                    "status": "already_complete",
                    "task_id": validated_payload.task_id,
                    "message": "Task is already marked as complete"
                }
            
            # Assuming validation logic is handled elsewhere or will be integrated
            # For now, just mark as complete
            target_task.status = "completed" # Update status to "completed"

            asyncio.run(session_manager.update_session(session))
            logging.info(f"Task {validated_payload.task_id} marked as complete in session {session.id}")

            return {"status": "success", "task_id": validated_payload.task_id}
        except Exception as e:
            logging.error(f"Error marking task {validated_payload.task_id} complete in session {validated_payload.session_id}: {e}")
            return {"status": "error", "message": f"Failed to mark task complete: {e}"}
