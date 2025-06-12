# taskmaster/commands/add_task.py
import os
import json
from .base_command import BaseCommand
from ..models import Session, Task
from ..config import get_config

class Command(BaseCommand):
    def execute(self, payload: dict) -> dict:
        session_id = payload.get('session_id')
        description = payload.get('description')
        
        if not session_id:
            return {"error": "session_id is required"}
        if not description:
            return {"error": "description is required"}
        
        # Get config using the singleton
        config = get_config()
        
        # Load session
        state_dir = config.get_state_directory()
        session_file = os.path.join(state_dir, f"{session_id}.json")
        
        if not os.path.exists(session_file):
            return {"error": f"Session {session_id} not found"}
        
        with open(session_file, 'r') as f:
            session_data = json.load(f)
        
        session = Session(**session_data)
        
        # Create new task
        task = Task(description=description)
        session.tasks.append(task)
        
        # Save updated session
        with open(session_file, 'w') as f:
            json.dump(session.model_dump(), f, indent=2)
        
        return {"task_id": task.id} 