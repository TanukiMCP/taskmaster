import os
from typing import Tuple, Dict, Any
from .base_rule import BaseValidationRule
from ..models import Task

class FileExistsRule(BaseValidationRule):
 @property
 def rule_name(self) -> str:
 return "file_exists_rule"
 
 def check(self, task: Task, evidence: Dict[str, Any]) -> Tuple[bool, str]:
 """
 Check if specified files exist.
 
 Expected evidence format:
 {
 "files": ["path/to/file1.py", "path/to/file2.txt"] # list of file paths
 }
 or
 {
 "file": "path/to/single/file.py" # single file path
 }
 """
 files_to_check = []
 
 if "files" in evidence:
 if not isinstance(evidence["files"], list):
 return False, "Evidence 'files' must be a list of file paths"
 files_to_check = evidence["files"]
 elif "file" in evidence:
 files_to_check = [evidence["file"]]
 else:
 return False, "No 'file' or 'files' provided in evidence"
 
 if not files_to_check:
 return False, "No files specified for validation"
 
 missing_files = []
 existing_files = []
 
 for file_path in files_to_check:
 if not isinstance(file_path, str):
 return False, f"File path must be a string, got {type(file_path)}"
 
 if os.path.exists(file_path):
 existing_files.append(file_path)
 else:
 missing_files.append(file_path)
 
 if missing_files:
 return False, f"Missing files: {', '.join(missing_files)}"
 
 return True, f"All files exist: {', '.join(existing_files)}" 