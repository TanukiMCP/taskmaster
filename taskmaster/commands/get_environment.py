# taskmaster/commands/get_environment.py
import os
import json
import yaml
from .base_command import BaseCommand
from ..models import Session

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
        
        # Return environment map
        if session.environment_map is None:
            return {
                "session_id": session_id,
                "environment_available": False,
                "message": "No environment scan data available for this session"
            }
        
        # Optionally filter results based on payload parameters
        include_details = payload.get('include_details', True)
        scanner_filter = payload.get('scanner_filter', None)
        
        environment_data = session.environment_map.copy()
        
        # Apply scanner filter if specified
        if scanner_filter and isinstance(scanner_filter, list):
            filtered_scanners = {}
            for scanner_name in scanner_filter:
                if scanner_name in environment_data.get("scanners", {}):
                    filtered_scanners[scanner_name] = environment_data["scanners"][scanner_name]
            environment_data["scanners"] = filtered_scanners
        
        # Optionally exclude detailed scan data to provide just a summary
        if not include_details:
            # Provide summary information only
            summary_scanners = {}
            for scanner_name, scanner_data in environment_data.get("scanners", {}).items():
                summary_scanners[scanner_name] = {
                    "scan_successful": scanner_data.get("scan_successful", False),
                    "scanner_type": scanner_name
                }
                
                # Add specific summary fields based on scanner type
                if scanner_name == "system_tools":
                    summary_scanners[scanner_name]["available_tools_count"] = len(
                        scanner_data.get("available_tools", [])
                    )
                    summary_scanners[scanner_name]["total_tools_checked"] = scanner_data.get(
                        "total_tools_checked", 0
                    )
            
            environment_data["scanners"] = summary_scanners
        
        return {
            "session_id": session_id,
            "environment_available": True,
            "environment_map": environment_data,
            "query_parameters": {
                "include_details": include_details,
                "scanner_filter": scanner_filter
            }
        } 