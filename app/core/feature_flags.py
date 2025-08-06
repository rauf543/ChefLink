import os
from typing import Dict, Any
import json
import logging

logger = logging.getLogger(__name__)


class FeatureFlags:
    """Simple feature flag system for gradual rollout."""
    
    def __init__(self):
        self._flags = self._load_flags()
    
    def _load_flags(self) -> Dict[str, Any]:
        """Load feature flags from environment or config file."""
        # First try environment variable
        use_agentic = os.environ.get("USE_AGENTIC_WORKFLOW", "false").lower() == "true"
        
        # Simple flags
        return {
            "agentic_workflow": use_agentic,
            "increased_context_window": use_agentic,  # Enabled together
            "debug_mode": os.environ.get("DEBUG_MODE", "false").lower() == "true"
        }
    
    def is_enabled(self, flag_name: str, user_id: str = None) -> bool:
        """Check if a feature flag is enabled."""
        return self._flags.get(flag_name, False)
    
    def get_config(self, flag_name: str) -> Dict[str, Any]:
        """Get full configuration for a feature flag."""
        return self._flags.get(flag_name, {})
    
    def update_flag(self, flag_name: str, config: Dict[str, Any]) -> None:
        """Update a feature flag configuration (for testing)."""
        self._flags[flag_name] = config
    
    def reload(self) -> None:
        """Reload flags from source."""
        self._flags = self._load_flags()


# Global instance
feature_flags = FeatureFlags()