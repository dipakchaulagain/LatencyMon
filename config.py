import json
import os
from typing import Dict, Any

class Config:
    """Configuration management for the latency monitoring tool."""
    
    def __init__(self, config_file: str = 'config.json'):
        self.config_file = config_file
        self.config = self.load_config()
    
    def load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        if os.path.exists(self.config_file):
            try:
                with open(self.config_file, 'r') as f:
                    return json.load(f)
            except Exception as e:
                print(f"Error loading config: {e}")
                return self.get_default_config()
        else:
            return self.get_default_config()
    
    def get_default_config(self) -> Dict[str, Any]:
        """Return default configuration."""
        return {
            'destination_ip': '8.8.8.8',
            'latency_threshold_ms': 5,
            'ping_interval_seconds': 1,
            'max_graph_points': 60,
            'event_retention_days': 30
        }
    
    def save_config(self) -> bool:
        """Save current configuration to file."""
        try:
            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=4)
            return True
        except Exception as e:
            print(f"Error saving config: {e}")
            return False
    
    def update_config(self, updates: Dict[str, Any]) -> bool:
        """Update configuration with new values."""
        self.config.update(updates)
        return self.save_config()
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get configuration value by key."""
        return self.config.get(key, default)
    
    def get_all(self) -> Dict[str, Any]:
        """Get all configuration values."""
        return self.config.copy()
