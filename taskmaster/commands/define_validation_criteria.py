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
from taskmaster.commands.schemas.define_validation_criteria_schema import DefineValidationCriteriaPayload

class Command(BaseCommand):
    def execute(self, payload: dict) -> dict:
        try:
            validated_payload = DefineValidationCriteriaPayload(**payload)
        except ValidationError as e:
            logging.error(f"Validation error in DefineValidationCriteriaCommand: {e.errors()}")
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

            target_task.validation_criteria = validated_payload.criteria
            target_task.validation_required = True # Always set to True if criteria are defined

            asyncio.run(session_manager.update_session(session))
            logging.info(f"Validation criteria updated for task {validated_payload.task_id} in session {session.id}")

            return {
                "status": "success",
                "task_id": validated_payload.task_id,
                "validation_criteria": validated_payload.criteria,
                "validation_required": target_task.validation_required,
                "message": f"Validation criteria updated for task {validated_payload.task_id}"
            }
        except Exception as e:
            logging.error(f"Error defining validation criteria for task {validated_payload.task_id} in session {validated_payload.session_id}: {e}")
            return {"status": "error", "message": f"Failed to define validation criteria: {e}"}
