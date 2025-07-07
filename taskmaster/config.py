import os
import yaml
from typing import Dict, Any, Optional

class Config:
    """
    Singleton class for managing configuration settings.
    Ensures a single instance of config is loaded and shared across the application.
    """
    _instance = None
    _config_data = None
    
    def __new__(cls):
        """Ensure only one instance of Config exists"""
        if cls._instance is None:
            cls._instance = super(Config, cls).__new__(cls)
            # SMITHERY LAZY LOADING: Defer config loading
            # cls._load_config() 
        return cls._instance
    
    @classmethod
    def _ensure_config_loaded(cls):
        """Ensure the configuration is loaded before access."""
        if cls._config_data is None:
            cls._load_config()

    @classmethod
    def _load_config(cls):
        """Load configuration from config.yaml file"""
        config_path = 'config.yaml'
        
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Configuration file {config_path} not found")
        
        try:
            with open(config_path, 'r') as f:
                cls._config_data = yaml.safe_load(f)
        except Exception as e:
            raise Exception(f"Failed to load configuration: {str(e)}")
    
    @classmethod
    def get(cls, key: Optional[str] = None, default: Any = None) -> Any:
        """
        Get configuration value by key.
        
        Args:
            key: The configuration key to retrieve (dot notation supported for nested keys)
            default: Default value to return if key not found
        
        Returns:
            The configuration value or default if not found
        """
        if cls._instance is None:
            cls._instance = Config()
        
        # SMITHERY LAZY LOADING: Ensure config is loaded before access
        cls._ensure_config_loaded()

        if key is None:
            return cls._config_data
        
        # Handle nested keys with dot notation (e.g., "scanners.system_tool_scanner")
        parts = key.split('.')
        value = cls._config_data
        
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return default
        
        return value
    
    @classmethod
    def get_state_directory(cls) -> str:
        """
        Get the configured state directory with fallback to default.
        
        Returns:
            str: Path to the state directory
        """
        # SMITHERY LAZY LOADING: Ensure config is loaded before access
        cls._ensure_config_loaded()
        state_dir = cls.get('state_directory', 'taskmaster/state')
        
        # Ensure directory exists
        os.makedirs(state_dir, exist_ok=True)
        
        return state_dir

# Convenience function to get config instance
def get_config() -> Config:
    """Get the singleton Config instance"""
    return Config() 