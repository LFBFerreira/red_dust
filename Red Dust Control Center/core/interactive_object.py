"""
Abstract base class for interactive objects supporting different communication protocols.
"""
from abc import ABC, abstractmethod
from typing import Optional
from obspy import UTCDateTime
import logging

logger = logging.getLogger(__name__)


class InteractiveObject(ABC):
    """Abstract base class for interactive objects."""
    
    def __init__(self, name: str, remap_min: float = 0.0, remap_max: float = 1.0):
        """
        Initialize interactive object.
        
        Args:
            name: Unique identifier for the object
            remap_min: Minimum output value for remapping (default: 0.0)
            remap_max: Maximum output value for remapping (default: 1.0)
        """
        self.name = name
        self.remap_min = remap_min
        self.remap_max = remap_max
        self.streaming_enabled = False
    
    @property
    @abstractmethod
    def communication_type(self) -> str:
        """Return the communication type (e.g., 'OSC', 'Serial')."""
        pass
    
    def remap_value(self, normalized_value: float) -> float:
        """
        Remap normalized value (0-1) to output range.
        
        Args:
            normalized_value: Normalized input value (0..1)
        
        Returns:
            Remapped value in range [remap_min, remap_max]
        """
        # Clamp normalized value to 0..1
        normalized_value = max(0.0, min(1.0, normalized_value))
        
        # Handle edge case where min == max
        if self.remap_max == self.remap_min:
            return self.remap_min
        
        # Linear remapping: output = min + (normalized * (max - min))
        return self.remap_min + (normalized_value * (self.remap_max - self.remap_min))
    
    @abstractmethod
    def send(self, normalized_value: float, timestamp: UTCDateTime) -> Optional[float]:
        """
        Send data with remapped value.
        
        Args:
            normalized_value: Normalized value (0..1) from waveform model
            timestamp: UTC timestamp
        
        Returns:
            Remapped value that was sent (for UI updates), or None if failed
        """
        pass
    
    @abstractmethod
    def close(self) -> None:
        """Close the connection."""
        pass
    
    @abstractmethod
    def get_config_dict(self) -> dict:
        """
        Get configuration dictionary for serialization.
        
        Returns:
            Dictionary with all configuration parameters
        """
        pass
