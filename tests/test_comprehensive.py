# tests/test_comprehensive.py
import pytest
import json
import os
import tempfile
import shutil
from unittest.mock import patch, MagicMock, mock_open
from server import taskmaster

class TestTaskmasterComprehensive:
    """Comprehensive tests for all taskmaster functionality."""
    
    @pytest.fixture
    def mock_config(self):
        """Mock config.yaml content."""
        return {"state_directory": "taskmaster/state"}
    
    @pytest.fixture
    def mock_session_data(self):
        """Mock session data for testing."""
        return {
            "id": "session_test123",
            "tasks": [
                {
                    "id": "task_1",
                    "description": "Test task 1",
                    "status": "[ ]",
                    "validation_required": False,
                    "validation_criteria": [],
                    "evidence": []
                },
                {
                    "id": "task_2", 
                    "description": "Test task 2",
                    "status": "[X]",
                    "validation_required": True,
                    "validation_criteria": ["syntax_rule"],
                    "evidence": [{"code": "print('hello')", "timestamp": "2024-01-01T12:00:00"}]
                }
            ],
            "environment_map": {
                "scanners": {
                    "system_tools": {
                        "available_tools": ["python", "git"],
                        "scan_successful": True
                    }
                },
                "metadata": {
                    "total_scanners": 1,
                    "successful_scans": 1,
                    "scanner_names": ["system_tools"]
                }
            }
        }

    def test_invalid_command(self):
        """Test handling of invalid commands."""
        result = taskmaster("nonexistent_command", {})
        assert "error" in result
        assert "Unknown command" in result["error"]

    def test_create_session_success(self, mock_config):
        """Test successful session creation."""
        mock_env_data = {"scanners": {"test": {"scan_successful": True}}, "metadata": {"scanner_names": []}}
        
        with patch('builtins.open', mock_open(read_data=json.dumps(mock_config))), \
             patch('yaml.safe_load', return_value=mock_config), \
             patch('os.makedirs'), \
             patch('taskmaster.environment_scanner.EnvironmentScanner') as mock_scanner_class:
            
            # Mock the scanner instance
            mock_scanner = MagicMock()
            mock_scanner.scan_environment.return_value = mock_env_data
            mock_scanner_class.return_value = mock_scanner
            
            result = taskmaster("create_session", {})
            
            assert "session_id" in result
            assert result["session_id"].startswith("session_")
            assert "environment_scan_completed" in result

    def test_add_task_success(self, mock_config, mock_session_data):
        """Test successful task addition."""
        session_id = "session_test123"
        
        with patch('builtins.open', mock_open(read_data=json.dumps(mock_config))), \
             patch('yaml.safe_load', return_value=mock_config), \
             patch('os.path.exists', return_value=True), \
             patch('json.load', return_value=mock_session_data):
            
            result = taskmaster("add_task", {
                "session_id": session_id,
                "description": "New test task"
            })
            
            assert "task_id" in result
            assert result["task_id"].startswith("task_")

    def test_add_task_missing_session_id(self):
        """Test add_task without session_id."""
        result = taskmaster("add_task", {"description": "Test task"})
        assert "error" in result
        assert "session_id is required" == result["error"]

    def test_add_task_missing_description(self):
        """Test add_task without description."""
        result = taskmaster("add_task", {"session_id": "test_session"})
        assert "error" in result
        assert "description is required" == result["error"]

    def test_add_task_session_not_found(self, mock_config):
        """Test add_task with non-existent session."""
        with patch('builtins.open', mock_open(read_data=json.dumps(mock_config))), \
             patch('yaml.safe_load', return_value=mock_config), \
             patch('os.path.exists', return_value=False):
            
            result = taskmaster("add_task", {
                "session_id": "nonexistent",
                "description": "Test task"
            })
            
            assert "error" in result
            assert "Session nonexistent not found" == result["error"]

    def test_get_tasklist_success(self, mock_config, mock_session_data):
        """Test successful task list retrieval."""
        session_id = "session_test123"
        
        with patch('builtins.open', mock_open(read_data=json.dumps(mock_config))), \
             patch('yaml.safe_load', return_value=mock_config), \
             patch('os.path.exists', return_value=True), \
             patch('json.load', return_value=mock_session_data):
            
            result = taskmaster("get_tasklist", {"session_id": session_id})
            
            assert "tasks" in result
            assert len(result["tasks"]) == 2
            assert result["tasks"][0]["description"] == "Test task 1"

    def test_get_tasklist_session_not_found(self, mock_config):
        """Test get_tasklist with non-existent session."""
        with patch('builtins.open', mock_open(read_data=json.dumps(mock_config))), \
             patch('yaml.safe_load', return_value=mock_config), \
             patch('os.path.exists', return_value=False):
            
            result = taskmaster("get_tasklist", {"session_id": "nonexistent"})
            
            assert "error" in result
            assert "Session nonexistent not found" == result["error"]

    def test_get_validation_rules_success(self):
        """Test getting available validation rules."""
        mock_rules = ["syntax_rule", "content_contains_rule", "file_exists_rule"]
        
        with patch('taskmaster.validation_engine.ValidationEngine') as mock_engine:
            mock_engine_instance = mock_engine.return_value
            mock_engine_instance.get_available_rules.return_value = mock_rules
            
            result = taskmaster("get_validation_rules", {})
            
            assert "available_rules" in result
            assert result["available_rules"] == mock_rules
            assert result["success"] is True
            assert result["count"] == 3

    def test_define_validation_criteria_success(self, mock_config, mock_session_data):
        """Test successful validation criteria definition."""
        session_id = "session_test123"
        task_id = "task_1"
        
        with patch('builtins.open', mock_open(read_data=json.dumps(mock_config))), \
             patch('yaml.safe_load', return_value=mock_config), \
             patch('os.path.exists', return_value=True), \
             patch('json.load', return_value=mock_session_data):
            
            result = taskmaster("define_validation_criteria", {
                "session_id": session_id,
                "task_id": task_id,
                "criteria": ["syntax_rule"],
                "validation_required": True
            })
            
            assert "success" in result
            assert result["success"] is True

    def test_mark_task_complete_without_validation(self, mock_config, mock_session_data):
        """Test marking task complete without validation requirement."""
        session_id = "session_test123"
        task_id = "task_1"
        
        with patch('builtins.open', mock_open(read_data=json.dumps(mock_config))), \
             patch('yaml.safe_load', return_value=mock_config), \
             patch('os.path.exists', return_value=True), \
             patch('json.load', return_value=mock_session_data):
            
            result = taskmaster("mark_task_complete", {
                "session_id": session_id,
                "task_id": task_id,
                "evidence": {"test": "evidence"}
            })
            
            assert "status" in result
            assert result["status"] == "complete"

    def test_mark_task_complete_with_validation_success(self, mock_config, mock_session_data):
        """Test marking task complete with successful validation."""
        session_id = "session_test123"
        task_id = "task_1"
        
        # Modify mock data to have validation required
        mock_session_data["tasks"][0]["validation_required"] = True
        mock_session_data["tasks"][0]["validation_criteria"] = ["syntax_rule"]
        
        with patch('builtins.open', mock_open(read_data=json.dumps(mock_config))), \
             patch('yaml.safe_load', return_value=mock_config), \
             patch('os.path.exists', return_value=True), \
             patch('json.load', return_value=mock_session_data), \
             patch('taskmaster.validation_engine.ValidationEngine') as mock_engine:
            
            # Mock validation success
            mock_engine_instance = mock_engine.return_value
            mock_engine_instance.validate.return_value = (True, ["Validation passed"])
            
            result = taskmaster("mark_task_complete", {
                "session_id": session_id,
                "task_id": task_id,
                "evidence": {"code": "print('hello')"}
            })
            
            assert "status" in result
            assert result["status"] == "complete"

    def test_mark_task_complete_with_validation_failure(self, mock_config, mock_session_data):
        """Test marking task complete with validation failure."""
        session_id = "session_test123"
        task_id = "task_1"
        
        # Modify mock data to have validation required
        mock_session_data["tasks"][0]["validation_required"] = True
        mock_session_data["tasks"][0]["validation_criteria"] = ["syntax_rule"]
        
        with patch('builtins.open', mock_open(read_data=json.dumps(mock_config))), \
             patch('yaml.safe_load', return_value=mock_config), \
             patch('os.path.exists', return_value=True), \
             patch('json.load', return_value=mock_session_data), \
             patch('taskmaster.validation_engine.ValidationEngine') as mock_engine:
            
            # Mock validation failure
            mock_engine_instance = mock_engine.return_value
            mock_engine_instance.validate.return_value = (False, ["Syntax error found"])
            
            result = taskmaster("mark_task_complete", {
                "session_id": session_id,
                "task_id": task_id,
                "evidence": {"code": "invalid syntax !!!"}
            })
            
            assert "status" in result
            assert result["status"] == "validation_failed"
            assert "validation_messages" in result

    def test_scan_environment_basic(self):
        """Test scan_environment with missing session_id."""
        result = taskmaster("scan_environment", {})
        assert "error" in result
        assert "session_id is required" == result["error"]

    def test_get_environment_success(self, mock_config, mock_session_data):
        """Test successful environment data retrieval."""
        session_id = "session_test123"
        
        with patch('builtins.open', mock_open(read_data=json.dumps(mock_config))), \
             patch('yaml.safe_load', return_value=mock_config), \
             patch('os.path.exists', return_value=True), \
             patch('json.load', return_value=mock_session_data):
            
            result = taskmaster("get_environment", {"session_id": session_id})
            
            assert "environment_map" in result
            assert "scanners" in result["environment_map"]

    def test_progress_to_next_success(self, mock_config, mock_session_data):
        """Test successful progression to next task."""
        session_id = "session_test123"
        
        with patch('builtins.open', mock_open(read_data=json.dumps(mock_config))), \
             patch('yaml.safe_load', return_value=mock_config), \
             patch('os.path.exists', return_value=True), \
             patch('json.load', return_value=mock_session_data):
            
            result = taskmaster("progress_to_next", {"session_id": session_id})
            
            assert "status" in result
            assert result["status"] == "next_task_found"
            assert result["next_task"]["id"] == "task_1"  # First incomplete task

    def test_progress_to_next_all_complete(self, mock_config, mock_session_data):
        """Test progression when all tasks are complete."""
        session_id = "session_test123"
        
        # Mark all tasks as complete
        for task in mock_session_data["tasks"]:
            task["status"] = "[X]"
        
        with patch('builtins.open', mock_open(read_data=json.dumps(mock_config))), \
             patch('yaml.safe_load', return_value=mock_config), \
             patch('os.path.exists', return_value=True), \
             patch('json.load', return_value=mock_session_data):
            
            result = taskmaster("progress_to_next", {"session_id": session_id})
            
            assert "status" in result
            assert result["status"] == "all_complete"

    def test_end_session_success(self, mock_config, mock_session_data):
        """Test successful session ending."""
        session_id = "session_test123"
        
        with patch('builtins.open', mock_open(read_data=json.dumps(mock_config))), \
             patch('yaml.safe_load', return_value=mock_config), \
             patch('os.path.exists', return_value=True), \
             patch('json.load', return_value=mock_session_data):
            
            result = taskmaster("end_session", {"session_id": session_id})
            
            assert "status" in result
            assert result["status"] == "session_ended"
            assert "summary" in result
            assert "statistics" in result["summary"]

    def test_end_session_with_archive(self, mock_config, mock_session_data):
        """Test session ending with archiving."""
        session_id = "session_test123"
        
        with patch('builtins.open', mock_open(read_data=json.dumps(mock_config))), \
             patch('yaml.safe_load', return_value=mock_config), \
             patch('os.path.exists', return_value=True), \
             patch('json.load', return_value=mock_session_data), \
             patch('os.makedirs'), \
             patch('os.remove'):
            
            result = taskmaster("end_session", {
                "session_id": session_id,
                "archive": True
            })
            
            assert "status" in result
            assert result["status"] == "session_ended"
            assert result["summary"]["archived"] is True

    def test_commands_requiring_session_id(self):
        """Test that commands requiring session_id fail appropriately."""
        commands_requiring_session = [
            "add_task",
            "get_tasklist",
            "define_validation_criteria", 
            "mark_task_complete",
            "scan_environment",
            "get_environment",
            "progress_to_next",
            "end_session"
        ]
        
        for command in commands_requiring_session:
            result = taskmaster(command, {})
            assert "error" in result, f"Command {command} should return error without session_id"
            assert "session_id" in result["error"].lower(), f"Command {command} error should mention session_id"

    def test_command_with_missing_required_fields(self):
        """Test commands with missing required fields."""
        # Test define_validation_criteria without task_id
        result = taskmaster("define_validation_criteria", {"session_id": "test"})
        assert "error" in result
        
        # Test mark_task_complete without task_id  
        result = taskmaster("mark_task_complete", {"session_id": "test"})
        assert "error" in result

    def test_error_handling_structure(self):
        """Test that all errors follow consistent structure."""
        test_cases = [
            ("invalid_command", {}),
            ("add_task", {}),
            ("get_tasklist", {}),
            ("add_task", {"session_id": "test"}),  # Missing description
        ]
        
        for command, payload in test_cases:
            result = taskmaster(command, payload)
            
            # Verify error structure
            assert isinstance(result, dict), f"Command {command} should return dict"
            assert "error" in result, f"Command {command} should return error"
            assert isinstance(result["error"], str), f"Command {command} error should be string"
            assert len(result["error"]) > 0, f"Command {command} error should not be empty" 