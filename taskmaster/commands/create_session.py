# taskmaster/commands/create_session.py
import os
import json
import yaml
import asyncio
from .base_command import BaseCommand
from ..models import Session
from ..environment_scanner import create_environment_scanner

class Command(BaseCommand):
    def execute(self, payload: dict) -> dict:
        # Load config
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        # Create new session
        session = Session()
        
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
            
            # Store environment map in session
            session.environment_map = environment_map
            
        except Exception as e:
            # If scanning fails, log the error but continue with session creation
            print(f"Warning: Environment scan failed during session creation: {e}")
            session.environment_map = {
                "scanners": {},
                "metadata": {
                    "scan_failed": True,
                    "error": str(e)
                }
            }
        
        # Ensure state directory exists
        state_dir = config['state_directory']
        os.makedirs(state_dir, exist_ok=True)
        
        # Save session to file
        session_file = os.path.join(state_dir, f"{session.id}.json")
        with open(session_file, 'w') as f:
            json.dump(session.model_dump(), f, indent=2)
        
        return {
            "session_id": session.id,
            "environment_scan_completed": session.environment_map is not None,
            "scanners_loaded": len(session.environment_map.get("metadata", {}).get("scanner_names", [])) if session.environment_map else 0
        } 