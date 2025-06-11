# taskmaster/commands/get_tasklist.py
import os
import json
import yaml
from .base_command import BaseCommand
from ..models import Session

class Command(BaseCommand):
    def execute(self, payload: dict) -> dict:
        session_id = payload.get('session_id')
        
        if not session_id:
            return {"error": "session_id is required"}
        
        # Load config
        with open('config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        
        # Load session
        state_dir = config['state_directory']
        session_file = os.path.join(state_dir, f"{session_id}.json")
        
        if not os.path.exists(session_file):
            return {"error": f"Session {session_id} not found"}
        
        with open(session_file, 'r') as f:
            session_data = json.load(f)
        
        session = Session(**session_data)
        
        # Return tasks list
        return {
            "session_id": session_id,
            "tasks": [task.model_dump() for task in session.tasks]
        } 