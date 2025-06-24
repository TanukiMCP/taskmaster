# taskmaster/commands/add_task.py
import os
import json
import logging
import asyncio
from typing import Dict, Any
from pydantic import ValidationError
from .base_command import BaseCommand
from ..models import Session, Task
from ..config import get_config
from taskmaster.session_manager import SessionManager
from taskmaster.commands.schemas.add_task_schema import AddTaskPayload

class Command(BaseCommand):
    def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            validated_payload = AddTaskPayload(**payload)
        except ValidationError as e:
            logging.error(f"Validation error in AddTaskCommand: {e.errors()}")
            return {"status": "error", "message": "Invalid payload", "details": e.errors()}

        config = get_config()
        session_manager = SessionManager(state_dir=config.get_state_directory())

        try:
            session = asyncio.run(session_manager.get_session_async(validated_payload.session_id))
            if not session:
                return {"status": "error", "message": f"Session {validated_payload.session_id} not found"}

            task = Task(description=validated_payload.description)
            session.tasks.append(task)

            asyncio.run(session_manager.update_session(session))
            logging.info(f"Task '{task.description}' added to session {session.id}")

            return {"status": "success", "task_id": task.id}
        except Exception as e:
            logging.error(f"Error adding task to session {validated_payload.session_id}: {e}")
            return {"status": "error", "message": f"Failed to add task: {e}"}
