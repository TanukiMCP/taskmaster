# taskmaster/commands/scan_environment.py
import logging
import asyncio
from typing import Dict, Any
from pydantic import ValidationError
from .base_command import BaseCommand
from ..models import Session
from ..environment_scanner import create_environment_scanner
from taskmaster.config import get_config
from taskmaster.session_manager import SessionManager
from taskmaster.commands.schemas.scan_environment_schema import ScanEnvironmentPayload

class Command(BaseCommand):
    def execute(self, payload: dict) -> dict:
        try:
            validated_payload = ScanEnvironmentPayload(**payload)
        except ValidationError as e:
            logging.error(f"Validation error in ScanEnvironmentCommand: {e.errors()}")
            return {"status": "error", "message": "Invalid payload", "details": e.errors()}

        config = get_config()
        session_manager = SessionManager(state_dir=config.get_state_directory())

        try:
            session = asyncio.run(session_manager.get_session_async(validated_payload.session_id))
            if not session:
                return {"status": "error", "message": f"Session {validated_payload.session_id} not found"}

            scanner_config = config.get('scanners', {})
            env_scanner = create_environment_scanner(scanner_config)
            
            environment_map = asyncio.run(env_scanner.scan_environment())
            session.environment_map = environment_map
            
            asyncio.run(session_manager.update_session(session))
            logging.info(f"Environment scan completed for session {session.id}")

            return {
                "status": "success",
                "session_id": session.id,
                "scan_completed": True,
                "scanners_executed": environment_map.get("metadata", {}).get("total_scanners", 0),
                "successful_scans": environment_map.get("metadata", {}).get("successful_scans", 0),
                "failed_scans": environment_map.get("metadata", {}).get("failed_scans", 0),
                "scan_duration": environment_map.get("metadata", {}).get("scan_duration", 0.0),
                "message": "Environment scan completed successfully"
            }
        except Exception as e:
            logging.error(f"Error scanning environment for session {validated_payload.session_id}: {e}")
            return {"status": "error", "message": f"Failed to scan environment: {e}"}
