# taskmaster/commands/create_session.py
import os
import json
import logging
import asyncio
from pydantic import ValidationError
from .base_command import BaseCommand
from ..models import Session
from ..environment_scanner import create_environment_scanner
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
            
            # Perform environment scan if requested
            if validated_payload.initial_environment_scan:
                scanner_config = config.get('scanners', {})
                env_scanner = create_environment_scanner(scanner_config)
                
                environment_map = asyncio.run(env_scanner.scan_environment())
                session.environment_map = environment_map
                
                # Update the session with the environment map
                asyncio.run(session_manager.update_session(session))
                logging.info(f"Environment scan completed and session {session.id} updated.")

            return {
                "status": "success",
                "session_id": session.id,
                "environment_scan_completed": validated_payload.initial_environment_scan,
                "scanners_loaded": len(session.environment_map.get("metadata", {}).get("scanner_names", [])) if session.environment_map else 0
            }
        except Exception as e:
            logging.error(f"Error creating or scanning session: {e}")
            return {"status": "error", "message": f"Failed to create session: {e}"}
