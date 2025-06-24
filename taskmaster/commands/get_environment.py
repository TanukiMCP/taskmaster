# taskmaster/commands/get_environment.py
import logging
import asyncio
from typing import Dict, Any, List
from pydantic import ValidationError
from .base_command import BaseCommand
from ..models import Session
from ..config import get_config
from taskmaster.session_manager import SessionManager
from taskmaster.commands.schemas.get_environment_schema import GetEnvironmentPayload

class Command(BaseCommand):
    def execute(self, payload: dict) -> dict:
        try:
            validated_payload = GetEnvironmentPayload(**payload)
        except ValidationError as e:
            logging.error(f"Validation error in GetEnvironmentCommand: {e.errors()}")
            return {"status": "error", "message": "Invalid payload", "details": e.errors()}

        config = get_config()
        session_manager = SessionManager(state_dir=config.get_state_directory())

        try:
            session = asyncio.run(session_manager.get_session_async(validated_payload.session_id))
            if not session:
                return {"status": "error", "message": f"Session {validated_payload.session_id} not found"}

            if session.environment_map is None:
                return {
                    "status": "success",
                    "session_id": validated_payload.session_id,
                    "environment_available": False,
                    "message": "No environment scan data available for this session"
                }
            
            # For now, return the full environment map. Filtering logic can be added later.
            return {
                "status": "success",
                "session_id": validated_payload.session_id,
                "environment_available": True,
                "environment_map": session.environment_map
            }
        except Exception as e:
            logging.error(f"Error retrieving environment for session {validated_payload.session_id}: {e}")
            return {"status": "error", "message": f"Failed to retrieve environment: {e}"}
