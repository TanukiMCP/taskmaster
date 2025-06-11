from .base_command import BaseCommand
from ..validation_engine import ValidationEngine

class Command(BaseCommand):
    def execute(self, payload: dict) -> dict:
        """
        Get all available validation rules.
        
        Expected payload: {} (empty - no parameters required)
        """
        try:
            validation_engine = ValidationEngine()
            available_rules = validation_engine.get_available_rules()
            
            return {
                "success": True,
                "available_rules": available_rules,
                "count": len(available_rules),
                "message": f"Found {len(available_rules)} available validation rules"
            }
            
        except Exception as e:
            return {"error": f"Failed to get validation rules: {str(e)}"} 