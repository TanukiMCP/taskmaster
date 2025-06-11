import asyncio
import importlib
import os
import inspect
from typing import Dict, Any, List, Type
from .scanners.base_scanner import BaseScanner


class EnvironmentScanner:
    """
    Dynamic environment scanner that loads and executes all scanner modules
    from the scanners directory in parallel using asyncio.
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the environment scanner.
        
        Args:
            config: Configuration dictionary that can contain scanner-specific settings
        """
        self.config = config or {}
        self.scanners: List[BaseScanner] = []
        self._load_scanners()
    
    def _load_scanners(self):
        """
        Dynamically load all scanner classes from the scanners directory.
        """
        scanners_dir = os.path.join(os.path.dirname(__file__), 'scanners')
        
        # Get all Python files in the scanners directory
        scanner_files = [
            f[:-3] for f in os.listdir(scanners_dir)
            if f.endswith('.py') and f != '__init__.py' and f != 'base_scanner.py'
        ]
        
        for scanner_file in scanner_files:
            try:
                # Import the scanner module
                module_name = f"taskmaster.scanners.{scanner_file}"
                scanner_module = importlib.import_module(module_name)
                
                # Look for classes that inherit from BaseScanner
                for name, obj in inspect.getmembers(scanner_module):
                    if (inspect.isclass(obj) and 
                        issubclass(obj, BaseScanner) and 
                        obj != BaseScanner):
                        
                        # Check if the module has a factory function
                        if hasattr(scanner_module, 'create_scanner'):
                            # Use factory function to create instance
                            scanner_config = self.config.get(scanner_file, {})
                            scanner_instance = scanner_module.create_scanner(scanner_config)
                        else:
                            # Create instance directly
                            scanner_instance = obj()
                        
                        self.scanners.append(scanner_instance)
                        break
                        
            except Exception as e:
                # Log the error but continue loading other scanners
                print(f"Warning: Could not load scanner {scanner_file}: {e}")
                continue
    
    async def scan(self) -> Dict[str, Any]:
        """
        Execute all loaded scanners concurrently and return combined results.
        Convenience method that calls scan_environment().
        
        Returns:
            Dict[str, Any]: Combined results from all scanners with metadata
        """
        return await self.scan_environment()
    
    async def scan_environment(self) -> Dict[str, Any]:
        """
        Execute all loaded scanners concurrently and return combined results.
        
        Returns:
            Dict[str, Any]: Combined results from all scanners with metadata
        """
        if not self.scanners:
            return {
                "scanners": {},
                "metadata": {
                    "total_scanners": 0,
                    "successful_scans": 0,
                    "failed_scans": 0,
                    "scan_duration": 0.0
                }
            }
        
        import time
        start_time = time.time()
        
        # Create tasks for all scanners
        scanner_tasks = []
        scanner_names = []
        
        for scanner in self.scanners:
            task = asyncio.create_task(
                self._safe_scan(scanner),
                name=f"scan_{scanner.scanner_name}"
            )
            scanner_tasks.append(task)
            scanner_names.append(scanner.scanner_name)
        
        # Execute all scans concurrently with timeout
        try:
            scan_results = await asyncio.wait_for(
                asyncio.gather(*scanner_tasks, return_exceptions=True),
                timeout=30.0  # 30 second timeout
            )
        except asyncio.TimeoutError:
            # If timeout occurs, cancel all tasks and return partial results
            for task in scanner_tasks:
                if not task.done():
                    task.cancel()
            scan_results = [Exception("Scan timed out") for _ in scanner_tasks]
        
        import time
        end_time = time.time()
        scan_duration = end_time - start_time
        
        # Process results
        successful_scans = 0
        failed_scans = 0
        combined_results = {}
        
        for scanner_name, result in zip(scanner_names, scan_results):
            if isinstance(result, Exception):
                failed_scans += 1
                combined_results[scanner_name] = {
                    "error": str(result),
                    "scan_successful": False
                }
            else:
                successful_scans += 1
                combined_results[scanner_name] = {
                    **result,
                    "scan_successful": True
                }
        
        return {
            "scanners": combined_results,
            "metadata": {
                "total_scanners": len(self.scanners),
                "successful_scans": successful_scans,
                "failed_scans": failed_scans,
                "scan_duration": scan_duration,
                "scanner_names": scanner_names
            }
        }
    
    async def _safe_scan(self, scanner: BaseScanner) -> Dict[str, Any]:
        """
        Safely execute a scanner's scan method with error handling.
        
        Args:
            scanner: The scanner instance to execute
            
        Returns:
            Dict[str, Any]: Scanner results or error information
        """
        try:
            return await scanner.scan()
        except Exception as e:
            # Re-raise the exception to be caught by gather()
            raise Exception(f"Scanner {scanner.scanner_name} failed: {str(e)}")
    
    def get_loaded_scanners(self) -> List[str]:
        """
        Get a list of all loaded scanner names.
        
        Returns:
            List[str]: List of scanner names that were successfully loaded
        """
        return [scanner.scanner_name for scanner in self.scanners]
    
    async def scan_specific_scanner(self, scanner_name: str) -> Dict[str, Any]:
        """
        Execute a specific scanner by name.
        
        Args:
            scanner_name: Name of the scanner to execute
            
        Returns:
            Dict[str, Any]: Scanner results or error information
        """
        for scanner in self.scanners:
            if scanner.scanner_name == scanner_name:
                try:
                    result = await scanner.scan()
                    return {
                        "scanner_name": scanner_name,
                        "scan_successful": True,
                        **result
                    }
                except Exception as e:
                    return {
                        "scanner_name": scanner_name,
                        "scan_successful": False,
                        "error": str(e)
                    }
        
        return {
            "scanner_name": scanner_name,
            "scan_successful": False,
            "error": f"Scanner '{scanner_name}' not found"
        }


# Factory function for easy instantiation
def create_environment_scanner(config: Dict[str, Any] = None) -> EnvironmentScanner:
    """
    Factory function to create an EnvironmentScanner instance.
    
    Args:
        config: Configuration dictionary for scanner settings
        
    Returns:
        EnvironmentScanner: Configured scanner instance
    """
    return EnvironmentScanner(config) 