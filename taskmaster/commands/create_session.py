# taskmaster/commands/create_session.py
import os
import json
import logging
import asyncio
from pydantic import ValidationError
from .base_command import BaseCommand
from ..models import Session
from taskmaster.config import get_config
from taskmaster.commands.schemas.create_session_schema import CreateSessionPayload
from taskmaster.session_manager import SessionManager

class Command(BaseCommand):
 def execute(self, payload: dict) -> dict:
 try:
 validated_payload = CreateSessionPayload(**payload)
 except ValidationError as e:
 logging.error(f"Validation error in CreateSessionCommand: {e.errors()}")
 return {"status": "error", "message": "Invalid payload", "details": e.errors()}

 config = get_config()
 session_manager = SessionManager(state_dir=config.get_state_directory())

 try:
 # Create a new session using the SessionManager
 session = asyncio.run(session_manager.create_session(
 session_name=validated_payload.session_name
 ))

 return {
 "status": "success",
 "session_id": session.id,
 "session_name": session.session_name
 }
 except Exception as e:
 logging.error(f"Error creating session: {e}")
 return {"status": "error", "message": f"Failed to create session: {e}"}
