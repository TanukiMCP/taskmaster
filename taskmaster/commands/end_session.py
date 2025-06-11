# taskmaster/commands/end_session.py
import json
import os
from typing import Dict, Any
from datetime import datetime
from .base_command import BaseCommand
from ..models import Session

class Command(BaseCommand):
    def execute(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """
        End a session and provide comprehensive summary.
        
        Args:
            payload: Dict containing 'session_id' and optional 'archive' (bool)
            
        Returns:
            Dict with session summary and completion status
        """
        try:
            session_id = payload.get("session_id")
            archive = payload.get("archive", False)
            
            if not session_id:
                return {"error": "session_id is required"}
            
            # Load session
            session_file = f"taskmaster/state/{session_id}.json"
            if not os.path.exists(session_file):
                return {"error": f"Session '{session_id}' not found"}
            
            with open(session_file, 'r') as f:
                session_data = json.load(f)
            
            session = Session(**session_data)
            
            # Generate comprehensive summary
            completed_tasks = [task for task in session.tasks if task.status == "[X]"]
            incomplete_tasks = [task for task in session.tasks if task.status == "[ ]"]
            validated_tasks = [task for task in completed_tasks if task.validation_required and task.evidence]
            
            # Calculate statistics
            total_tasks = len(session.tasks)
            completion_rate = (len(completed_tasks) / total_tasks * 100) if total_tasks > 0 else 0
            validation_rate = (len(validated_tasks) / len(completed_tasks) * 100) if completed_tasks else 0
            
            summary = {
                "session_id": session_id,
                "ended_at": datetime.now().isoformat(),
                "statistics": {
                    "total_tasks": total_tasks,
                    "completed_tasks": len(completed_tasks),
                    "incomplete_tasks": len(incomplete_tasks),
                    "completion_rate": round(completion_rate, 2),
                    "validated_tasks": len(validated_tasks),
                    "validation_rate": round(validation_rate, 2)
                },
                "task_breakdown": {
                    "completed": [
                        {
                            "id": task.id,
                            "description": task.description,
                            "validated": task.validation_required and bool(task.evidence),
                            "evidence_count": len(task.evidence) if task.evidence else 0
                        }
                        for task in completed_tasks
                    ],
                    "incomplete": [
                        {
                            "id": task.id,
                            "description": task.description,
                            "validation_required": task.validation_required
                        }
                        for task in incomplete_tasks
                    ]
                },
                "environment_info": {
                    "scanned": bool(session.environment_map),
                    "tools_detected": len(session.environment_map.get("system_tools", {}).get("available_tools", [])) if session.environment_map else 0
                }
            }
            
            # Archive session if requested
            if archive:
                archive_dir = "taskmaster/state/archived"
                os.makedirs(archive_dir, exist_ok=True)
                
                archive_file = f"{archive_dir}/{session_id}_ended_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
                
                # Add end summary to session data
                session_data["session_summary"] = summary
                session_data["archived_at"] = summary["ended_at"]
                
                with open(archive_file, 'w') as f:
                    json.dump(session_data, f, indent=2)
                
                # Remove from active sessions
                os.remove(session_file)
                
                summary["archived"] = True
                summary["archive_file"] = archive_file
            else:
                summary["archived"] = False
            
            return {
                "status": "session_ended",
                "summary": summary,
                "message": f"Session ended. Completed {len(completed_tasks)}/{total_tasks} tasks ({completion_rate:.1f}%)"
            }
            
        except Exception as e:
            return {"error": f"Failed to end session: {str(e)}"} 