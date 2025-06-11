# taskmaster/commands/scan_environment.py
import os
import json
import yaml
import asyncio
from .base_command import BaseCommand
from ..models import Session
from ..environment_scanner import create_environment_scanner

class Command(BaseCommand):
    def execute(self, payload: dict) -> dict:
        # Validate payload
        if 'session_id' not in payload:
            return {"error": "session_id is required"}
        
        session_id = payload['session_id']
        
        # Load config
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        # Load session
        state_dir = config['state_directory']
        session_file = os.path.join(state_dir, f"{session_id}.json")
        
        if not os.path.exists(session_file):
            return {"error": f"Session {session_id} not found"}
        
        try:
            with open(session_file, 'r') as f:
                session_data = json.load(f)
            session = Session(**session_data)
        except (json.JSONDecodeError, Exception) as e:
            return {"error": f"Failed to load session: {str(e)}"}
        
        # Perform environment scan
        try:
            # Create environment scanner with config
            scanner_config = config.get('scanners', {})
            env_scanner = create_environment_scanner(scanner_config)
            
            # Run the scan asynchronously
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                environment_map = loop.run_until_complete(env_scanner.scan_environment())
            finally:
                loop.close()
            
            # Update session with new environment map
            session.environment_map = environment_map
            
            # Save updated session
            with open(session_file, 'w') as f:
                json.dump(session.model_dump(), f, indent=2)
            
            return {
                "session_id": session_id,
                "scan_completed": True,
                "scanners_executed": environment_map.get("metadata", {}).get("total_scanners", 0),
                "successful_scans": environment_map.get("metadata", {}).get("successful_scans", 0),
                "failed_scans": environment_map.get("metadata", {}).get("failed_scans", 0),
                "scan_duration": environment_map.get("metadata", {}).get("scan_duration", 0.0),
                "message": "Environment scan completed successfully"
            }
            
        except Exception as e:
            return {
                "session_id": session_id,
                "scan_completed": False,
                "error": str(e),
                "message": "Environment scan failed"
            } 