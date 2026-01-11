"""
OSC implementation of InteractiveObject.
"""
from typing import Optional
from obspy import UTCDateTime
from pythonosc.udp_client import UDPClient
import logging

from core.interactive_object import InteractiveObject

logger = logging.getLogger(__name__)


class OSCObject(InteractiveObject):
    """OSC implementation of interactive object."""
    
    def __init__(self, name: str, address: str, host: str, port: int, remap_min: float = 0.0, remap_max: float = 1.0):
        """
        Initialize OSC object.
        
        Args:
            name: Unique identifier for the object
            address: OSC address (e.g., "/red_dust/object1")
            host: Target IP address
            port: Target UDP port
            remap_min: Minimum output value for remapping (default: 0.0)
            remap_max: Maximum output value for remapping (default: 1.0)
        """
        super().__init__(name, remap_min, remap_max)
        self.address = address
        self.host = host
        self.port = port
        self._client = None
        
        # Create OSC client
        try:
            self._client = UDPClient(host, port)
            logger.info(f"Created OSC client for {name} at {host}:{port}")
        except Exception as e:
            logger.error(f"Failed to create OSC client for {name}: {e}")
    
    @property
    def communication_type(self) -> str:
        """Return the communication type."""
        return "OSC"
    
    def send(self, normalized_value: float, timestamp: UTCDateTime) -> Optional[float]:
        """
        Send OSC message with remapped value.
        
        Args:
            normalized_value: Normalized value (0..1) from waveform model
            timestamp: UTC timestamp
        
        Returns:
            Remapped value that was sent (for UI updates)
        """
        if not self.streaming_enabled or self._client is None:
            return None
        
        # Apply remapping
        output_value = self.remap_value(normalized_value)
        
        # Format timestamp as ISO8601 UTC string
        timestamp_str = timestamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        
        try:
            # Send message with two arguments: value (float) and timestamp (string)
            from pythonosc.osc_message_builder import OscMessageBuilder
            builder = OscMessageBuilder(self.address)
            builder.add_arg(output_value)
            builder.add_arg(timestamp_str)
            msg = builder.build()
            self._client.send(msg)
            return output_value
        except Exception as e:
            logger.error(f"Failed to send OSC message for {self.name}: {e}")
            return None
    
    def close(self) -> None:
        """Close OSC client."""
        self._client = None
    
    def get_config_dict(self) -> dict:
        """
        Get configuration dictionary for serialization.
        
        Returns:
            Dictionary with all configuration parameters
        """
        return {
            'type': 'OSC',
            'name': self.name,
            'address': self.address,
            'host': self.host,
            'port': self.port,
            'remap_min': self.remap_min,
            'remap_max': self.remap_max
        }
