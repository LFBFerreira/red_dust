"""
Serial implementation of InteractiveObject.
"""
from typing import Optional
from obspy import UTCDateTime
import serial
import logging

from core.interactive_object import InteractiveObject

logger = logging.getLogger(__name__)


class SerialObject(InteractiveObject):
    """Serial implementation of interactive object."""
    
    def __init__(self, name: str, port: str, baudrate: int = 9600, remap_min: float = 0.0, remap_max: float = 1.0):
        """
        Initialize Serial object.
        
        Args:
            name: Unique identifier for the object
            port: Serial port (e.g., "COM3" on Windows, "/dev/ttyUSB0" on Linux)
            baudrate: Baud rate for serial communication (default: 9600)
            remap_min: Minimum output value for remapping (default: 0.0)
            remap_max: Maximum output value for remapping (default: 1.0)
        """
        super().__init__(name, remap_min, remap_max)
        self.port = port
        self.baudrate = baudrate
        self._serial = None
        self._connection_failed = False
        self._port_opened = False  # Track if port has been explicitly opened
        
        # Don't open port automatically - wait for explicit user selection
    
    @property
    def communication_type(self) -> str:
        """Return the communication type."""
        return "Serial"
    
    def is_connected(self) -> bool:
        """
        Check if serial connection is available and open.
        
        Returns:
            True if connection is available and open, False otherwise
        """
        if self._connection_failed:
            return False
        return self._serial is not None and self._serial.is_open
    
    def open_port(self) -> bool:
        """
        Open the serial port connection.
        This should be called when the user explicitly selects a port.
        
        Returns:
            True if connection successful, False otherwise
        """
        # Close existing connection if any
        self.close()
        
        # Reset failure flag
        self._connection_failed = False
        
        # Try to create new connection
        try:
            self._serial = serial.Serial(self.port, self.baudrate, timeout=1)
            logger.info(f"Opened Serial connection for {self.name} on {self.port} at {self.baudrate} baud")
            self._port_opened = True
            return True
        except Exception as e:
            logger.error(f"Failed to open Serial connection for {self.name}: {e}")
            self._connection_failed = True
            self._port_opened = False
            return False
    
    def reconnect(self) -> bool:
        """
        Attempt to reconnect to the serial port.
        
        Returns:
            True if reconnection successful, False otherwise
        """
        return self.open_port()
    
    def update_port(self, port: str) -> bool:
        """
        Update the port and attempt to open it.
        
        Args:
            port: New port name
        
        Returns:
            True if port was opened successfully, False otherwise
        """
        self.port = port
        return self.open_port()
    
    def send(self, normalized_value: float, timestamp: UTCDateTime) -> Optional[float]:
        """
        Send serial data with remapped value.
        
        Args:
            normalized_value: Normalized value (0..1) from waveform model
            timestamp: UTC timestamp
        
        Returns:
            Remapped value that was sent (for UI updates)
        """
        if not self.streaming_enabled or self._serial is None or not self._serial.is_open:
            return None
        
        # Apply remapping
        output_value = self.remap_value(normalized_value)
        
        # Format timestamp as ISO8601 UTC string
        timestamp_str = timestamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        
        try:
            # Send as string: "value,timestamp\n"
            message = f"{output_value:.6f},{timestamp_str}\n"
            self._serial.write(message.encode('utf-8'))
            return output_value
        except Exception as e:
            logger.error(f"Failed to send Serial message for {self.name}: {e}")
            return None
    
    def close(self) -> None:
        """Close serial connection."""
        if self._serial is not None:
            try:
                if self._serial.is_open:
                    self._serial.close()
                    logger.info(f"Closed Serial connection for {self.name}")
            except Exception as e:
                logger.error(f"Error closing Serial connection for {self.name}: {e}")
            finally:
                self._serial = None
                self._connection_failed = False
                self._port_opened = False
    
    def get_config_dict(self) -> dict:
        """
        Get configuration dictionary for serialization.
        
        Returns:
            Dictionary with all configuration parameters
        """
        return {
            'type': 'Serial',
            'name': self.name,
            'port': self.port,
            'baudrate': self.baudrate,
            'remap_min': self.remap_min,
            'remap_max': self.remap_max
        }
