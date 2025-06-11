# tests/test_integration.py
import pytest
import json
import os
import tempfile
import shutil
from unittest.mock import patch, MagicMock
from server import taskmaster

class TestTaskmasterIntegration:
    
    @pytest.fixture
    def temp_state_dir(self):
        """Create a temporary state directory for testing."""
        temp_dir = tempfile.mkdtemp()
        state_dir = os.path.join(temp_dir, "taskmaster", "state")
        os.makedirs(state_dir, exist_ok=True)
        yield state_dir
        shutil.rmtree(temp_dir)
    
    def test_full_workflow_success(self, temp_state_dir):
        """Test complete workflow from session creation to completion."""
        # Mock environment scanning for all tests
        with patch('taskmaster.environment_scanner.EnvironmentScanner') as mock_scanner_class, \
             patch('taskmaster.validation_engine.ValidationEngine.validate', return_value=(True, ["Validation passed"])):
            
            # Mock the scanner instance
            mock_scanner = MagicMock()
            mock_scanner.scan_environment.return_value = {"test": "data"}
            mock_scanner_class.return_value = mock_scanner
            
            # Step 1: Create session
            result = taskmaster("create_session", {})
            assert "session_id" in result
            session_id = result["session_id"]
            
            # Step 2: Add tasks
            task1_result = taskmaster("add_task", {
                "session_id": session_id,
                "description": "Write a Python function"
            })
            assert "task_id" in task1_result
            task1_id = task1_result["task_id"]
            
            task2_result = taskmaster("add_task", {
                "session_id": session_id,
                "description": "Write unit tests"
            })
            assert "task_id" in task2_result
            task2_id = task2_result["task_id"]
            
            # Step 3: Get task list
            tasklist_result = taskmaster("get_tasklist", {"session_id": session_id})
            assert "tasks" in tasklist_result
            assert len(tasklist_result["tasks"]) == 2
            
            # Step 4: Define validation criteria for first task
            validation_result = taskmaster("define_validation_criteria", {
                "session_id": session_id,
                "task_id": task1_id,
                "criteria": ["syntax_rule"],
                "validation_required": True
            })
            assert validation_result["success"] is True
            
            # Step 5: Mark first task complete with validation
            complete_result = taskmaster("mark_task_complete", {
                "session_id": session_id,
                "task_id": task1_id,
                "evidence": {"code": "def hello(): return 'world'"}
            })
            assert complete_result["status"] == "complete"
            
            # Step 6: Progress to next task
            progress_result = taskmaster("progress_to_next", {"session_id": session_id})
            assert progress_result["status"] == "next_task_found"
            assert progress_result["next_task"]["id"] == task2_id
            
            # Step 7: Mark second task complete without validation
            complete2_result = taskmaster("mark_task_complete", {
                "session_id": session_id,
                "task_id": task2_id,
                "evidence": {"test_file": "test_hello.py"}
            })
            assert complete2_result["status"] == "complete"
            
            # Step 8: Check progress (should be all complete)
            final_progress = taskmaster("progress_to_next", {"session_id": session_id})
            assert final_progress["status"] == "all_complete"
            
            # Step 9: End session
            end_result = taskmaster("end_session", {"session_id": session_id})
            assert end_result["status"] == "session_ended"
            assert end_result["summary"]["statistics"]["completion_rate"] == 100.0
    
    def test_validation_failure_workflow(self, temp_state_dir):
        """Test workflow with validation failure."""
        with patch('taskmaster.environment_scanner.EnvironmentScanner') as mock_scanner_class, \
             patch('taskmaster.validation_engine.ValidationEngine.validate', return_value=(False, ["Syntax error"])):
            
            # Mock the scanner instance
            mock_scanner = MagicMock()
            mock_scanner.scan_environment.return_value = {}
            mock_scanner_class.return_value = mock_scanner
            
            # Create session and add task
            session_result = taskmaster("create_session", {})
            session_id = session_result["session_id"]
            
            task_result = taskmaster("add_task", {
                "session_id": session_id,
                "description": "Write valid Python code"
            })
            task_id = task_result["task_id"]
            
            # Define validation criteria
            taskmaster("define_validation_criteria", {
                "session_id": session_id,
                "task_id": task_id,
                "criteria": ["syntax_rule"],
                "validation_required": True
            })
            
            # Attempt to mark complete with invalid code
            complete_result = taskmaster("mark_task_complete", {
                "session_id": session_id,
                "task_id": task_id,
                "evidence": {"code": "invalid python syntax !!!"}
            })
            
            assert complete_result["status"] == "validation_failed"
            assert "Syntax error" in complete_result["validation_messages"]
    
    def test_error_handling_workflow(self):
        """Test error handling in various scenarios."""
        # Test invalid command
        result = taskmaster("invalid_command", {})
        assert "error" in result
        assert "Unknown command" in result["error"]
        
        # Test missing session_id
        result = taskmaster("add_task", {"description": "Test"})
        assert "error" in result
        
        # Test non-existent session
        result = taskmaster("get_tasklist", {"session_id": "nonexistent"})
        assert "error" in result
        assert "not found" in result["error"]
    
    def test_environment_scanning_workflow(self, temp_state_dir):
        """Test environment scanning functionality."""
        mock_env_data = {
            "system_tools": {
                "available_tools": ["python", "git", "npm"],
                "scan_time": "2024-01-01T12:00:00"
            }
        }
        
        with patch('taskmaster.environment_scanner.EnvironmentScanner') as mock_scanner_class:
            # Mock the scanner instance
            mock_scanner = MagicMock()
            mock_scanner.scan_environment.return_value = mock_env_data
            mock_scanner_class.return_value = mock_scanner
            # Create session (triggers initial scan)
            session_result = taskmaster("create_session", {})
            session_id = session_result["session_id"]
            
            # Get environment data
            env_result = taskmaster("get_environment", {"session_id": session_id})
            assert "environment_map" in env_result
            assert env_result["environment_map"]["system_tools"]["available_tools"] == ["python", "git", "npm"]
            
            # Trigger manual rescan
            rescan_result = taskmaster("scan_environment", {"session_id": session_id})
            assert rescan_result["status"] == "environment_scanned"
    
    def test_validation_rules_workflow(self):
        """Test validation rules functionality."""
        with patch('taskmaster.validation_engine.ValidationEngine.get_available_rules', 
                   return_value=["syntax_rule", "content_contains_rule", "file_exists_rule"]):
            
            rules_result = taskmaster("get_validation_rules", {})
            assert "available_rules" in rules_result
            assert "syntax_rule" in rules_result["available_rules"]
            assert "content_contains_rule" in rules_result["available_rules"]
            assert "file_exists_rule" in rules_result["available_rules"]
    
    def test_session_archiving_workflow(self, temp_state_dir):
        """Test session archiving functionality."""
        with patch('taskmaster.environment_scanner.EnvironmentScanner') as mock_scanner_class, \
             patch('taskmaster.commands.end_session.os.makedirs'), \
             patch('taskmaster.commands.end_session.os.remove'):
            
            # Mock the scanner instance
            mock_scanner = MagicMock()
            mock_scanner.scan_environment.return_value = {}
            mock_scanner_class.return_value = mock_scanner
            
            # Create session with tasks
            session_result = taskmaster("create_session", {})
            session_id = session_result["session_id"]
            
            taskmaster("add_task", {
                "session_id": session_id,
                "description": "Test task"
            })
            
            # End session with archiving
            end_result = taskmaster("end_session", {
                "session_id": session_id,
                "archive": True
            })
            
            assert end_result["status"] == "session_ended"
            assert end_result["summary"]["archived"] is True
            assert "archive_file" in end_result["summary"] 