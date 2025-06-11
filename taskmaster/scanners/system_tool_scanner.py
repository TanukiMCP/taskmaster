import asyncio
import shutil
import platform
import sys
from typing import Dict, Any, List
from .base_scanner import BaseScanner


class SystemToolScanner(BaseScanner):
    """Scanner for detecting available system tools and executables."""
    
    @property
    def scanner_name(self) -> str:
        return "system_tools"
    
    def __init__(self, tools_to_check: List[str] = None):
        """
        Initialize the scanner with tools to check for.
        
        Args:
            tools_to_check: List of executable names to check for. 
                          If None, uses a default comprehensive list.
        """
        if tools_to_check is None:
            # Default comprehensive list of common development tools
            self.tools_to_check = [
                # Version control
                "git", "svn", "hg",
                # Programming languages
                "python", "python3", "node", "npm", "npx", "java", "javac", 
                "go", "rust", "cargo", "gcc", "g++", "clang",
                # Web development
                "nginx", "apache2", "httpd",
                # Databases
                "mysql", "postgres", "psql", "sqlite3", "redis-cli", "mongo",
                # DevOps & Cloud
                "docker", "kubectl", "terraform", "ansible", "vagrant",
                "aws", "gcloud", "az",
                # Build tools
                "make", "cmake", "gradle", "maven", "yarn", "pip", "composer",
                # Text editors/IDEs
                "vim", "nano", "emacs", "code", "subl",
                # System tools
                "curl", "wget", "ssh", "scp", "rsync", "tar", "unzip", "zip"
            ]
        else:
            self.tools_to_check = tools_to_check
    
    async def _check_tool_availability(self, tool: str) -> bool:
        """
        Check if a tool is available in the system PATH.
        
        Args:
            tool: The executable name to check
            
        Returns:
            bool: True if the tool is available, False otherwise
        """
        try:
            # Use asyncio to run the blocking shutil.which call
            loop = asyncio.get_running_loop()
            result = await loop.run_in_executor(None, shutil.which, tool)
            return result is not None
        except Exception:
            return False
    
    async def scan(self) -> Dict[str, Any]:
        """
        Scan the system for available tools and system information.
        
        Returns:
            Dict[str, Any]: System scan results including available tools,
                          system info, and Python environment details
        """
        # Run tool checks concurrently for speed
        tool_tasks = [
            self._check_tool_availability(tool) 
            for tool in self.tools_to_check
        ]
        
        tool_results = await asyncio.gather(*tool_tasks)
        
        # Build available tools list
        available_tools = [
            tool for tool, available in zip(self.tools_to_check, tool_results)
            if available
        ]
        
        # Get system information
        system_info = {
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "version": platform.version(),
            "machine": platform.machine(),
            "processor": platform.processor(),
            "python_version": sys.version,
            "python_executable": sys.executable
        }
        
        # Get Python packages (basic check for common ones)
        python_packages = await self._check_python_packages()
        
        import time
        return {
            "available_tools": available_tools,
            "total_tools_checked": len(self.tools_to_check),
            "system_info": system_info,
            "python_environment": python_packages,
            "scan_timestamp": time.time()
        }
    
    async def _check_python_packages(self) -> Dict[str, Any]:
        """Check for common Python packages."""
        common_packages = [
            "requests", "numpy", "pandas", "flask", "django", "fastapi",
            "pytest", "black", "mypy", "flake8", "jupyter", "matplotlib",
            "scipy", "sklearn", "tensorflow", "torch", "pydantic"
        ]
        
        installed_packages = []
        
        for package in common_packages:
            try:
                __import__(package)
                installed_packages.append(package)
            except ImportError:
                pass
        
        return {
            "installed_packages": installed_packages,
            "packages_checked": common_packages
        }


# Command pattern factory function
def create_scanner(config: Dict[str, Any] = None) -> SystemToolScanner:
    """Factory function to create a SystemToolScanner instance."""
    tools_to_check = None
    if config and "tools_to_check" in config:
        tools_to_check = config["tools_to_check"]
    
    return SystemToolScanner(tools_to_check) 