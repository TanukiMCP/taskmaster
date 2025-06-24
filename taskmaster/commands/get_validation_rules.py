import logging
from typing import Dict, Any
from pydantic import ValidationError
from .base_command import BaseCommand
from ..validation_engine import ValidationEngine
from taskmaster.commands.schemas.get_validation_rules_schema import GetValidationRulesPayload

class Command(BaseCommand):
    def execute(self, payload: dict) -> dict:
        try:
            validated_payload = GetValidationRulesPayload(**payload)
        except ValidationError as e:
            logging.error(f"Validation error in GetValidationRulesCommand: {e.errors()}")
            return {"status": "error", "message": "Invalid payload", "details": e.errors()}

        try:
            validation_engine = ValidationEngine()
            available_rules = validation_engine.get_available_rules()
            
            return {
                "status": "success",
                "available_rules": available_rules,
                "count": len(available_rules),
                "message": f"Found {len(available_rules)} available validation rules"
            }
        except Exception as e:
            logging.error(f"Error getting validation rules: {e}")
            return {"status": "error", "message": f"Failed to get validation rules: {e}"}
