# taskmaster/commands/get_tasklist.py
import logging
import asyncio
from typing import Dict, Any
from pydantic import ValidationError
from .base_command import BaseCommand
from ..models import Session
from ..config import get_config
from taskmaster.session_manager import SessionManager
from taskmaster.commands.schemas.get_tasklist_schema import GetTasklistPayload

class Command(BaseCommand):
    def execute(self, payload: dict) -> dict:
        try:
            validated_payload = GetTasklistPayload(**payload)
        except ValidationError as e:
            logging.error(f"Validation error in GetTasklistCommand: {e.errors()}")
            return {"status": "error", "message": "Invalid payload", "details": e.errors()}

        config = get_config()
        session_manager = SessionManager(state_dir=config.get_state_directory())

        try:
            session = asyncio.run(session_manager.get_session_async(validated_payload.session_id))
            if not session:
                return {"status": "error", "message": f"Session {validated_payload.session_id} not found"}

            tasks_list = []
            for task in session.tasks:
                if validated_payload.status is None or task.status == validated_payload.status:
                    tasks_list.append({
                        "id": task.id,
                        "description": task.description,
                        "status": task.status
                    })
            
            return {"status": "success", "session_id": session.id, "tasks": tasks_list}
        except Exception as e:
            logging.error(f"Error retrieving task list for session {validated_payload.session_id}: {e}")
            return {"status": "error", "message": f"Failed to retrieve task list: {e}"}
