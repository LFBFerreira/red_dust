"""
OSC Manager for streaming normalized data to interactive objects.
"""
from typing import Dict, Optional
from obspy import UTCDateTime
from PySide6.QtCore import QObject, QTimer, Signal
from pythonosc.udp_client import UDPClient
import logging

logger = logging.getLogger(__name__)

# Fixed OSC output rate: 60 Hz
OSC_OUTPUT_RATE = 60
OSC_INTERVAL_MS = 1000 // OSC_OUTPUT_RATE  # ~16.67 ms


class OSCObject:
    """Configuration for a single OSC output object."""
    
    def __init__(self, name: str, address: str, host: str, port: int, scale: float = 1.0):
        """
        Initialize OSC object.
        
        Args:
            name: Unique identifier for the object
            address: OSC address (e.g., "/red_dust/object1")
            host: Target IP address
            port: Target UDP port
            scale: Output scaling factor (0..1, caps max value)
        """
        self.name = name
        self.address = address
        self.host = host
        self.port = port
        self.scale = max(0.0, min(1.0, scale))  # Clamp to 0..1
        self.enabled = True
        self._client = None
        
        # Create OSC client
        try:
            self._client = UDPClient(host, port)
            logger.info(f"Created OSC client for {name} at {host}:{port}")
        except Exception as e:
            logger.error(f"Failed to create OSC client for {name}: {e}")
    
    def send(self, value: float, timestamp: UTCDateTime) -> None:
        """
        Send OSC message.
        
        Args:
            value: Normalized value (0..1)
            timestamp: UTC timestamp
        """
        if not self.enabled or self._client is None:
            return
        
        # Apply scaling
        output_value = value * self.scale
        output_value = max(0.0, min(1.0, output_value))  # Ensure 0..1
        
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
        except Exception as e:
            logger.error(f"Failed to send OSC message for {self.name}: {e}")
    
    def close(self) -> None:
        """Close OSC client."""
        self._client = None


class OSCManager(QObject):
    """Manages OSC streaming to multiple interactive objects."""
    
    # Signal emitted when streaming state changes
    streaming_state_changed = Signal(bool)  # True when streaming starts
    
    def __init__(self, waveform_model=None, playback_controller=None):
        """
        Initialize OSCManager.
        
        Args:
            waveform_model: WaveformModel instance (can be set later)
            playback_controller: PlaybackController instance (can be set later)
        """
        super().__init__()
        self._waveform_model = waveform_model
        self._playback_controller = playback_controller
        self._objects: Dict[str, OSCObject] = {}
        self._streaming = False
        
        # Timer for 60 Hz output
        self._timer = QTimer()
        self._timer.timeout.connect(self._send_frame)
        self._timer.setInterval(OSC_INTERVAL_MS)
    
    def set_waveform_model(self, waveform_model) -> None:
        """
        Set waveform model.
        
        Args:
            waveform_model: WaveformModel instance
        """
        self._waveform_model = waveform_model
    
    def set_playback_controller(self, playback_controller) -> None:
        """
        Set playback controller.
        
        Args:
            playback_controller: PlaybackController instance
        """
        self._playback_controller = playback_controller
    
    def add_object(self, name: str, address: str, host: str, port: int, scale: float = 1.0) -> OSCObject:
        """
        Add a new OSC object.
        
        Args:
            name: Unique identifier
            address: OSC address
            host: Target IP address
            port: Target UDP port
            scale: Output scaling factor (0..1)
        
        Returns:
            OSCObject instance
        """
        if name in self._objects:
            logger.warning(f"Object {name} already exists, replacing it")
            self.remove_object(name)
        
        obj = OSCObject(name, address, host, port, scale)
        self._objects[name] = obj
        logger.info(f"Added OSC object: {name}")
        return obj
    
    def remove_object(self, name: str) -> None:
        """
        Remove an OSC object.
        
        Args:
            name: Object identifier
        """
        if name in self._objects:
            self._objects[name].close()
            del self._objects[name]
            logger.info(f"Removed OSC object: {name}")
    
    def get_object(self, name: str) -> Optional[OSCObject]:
        """
        Get OSC object by name.
        
        Args:
            name: Object identifier
        
        Returns:
            OSCObject or None if not found
        """
        return self._objects.get(name)
    
    def get_all_objects(self) -> Dict[str, OSCObject]:
        """
        Get all OSC objects.
        
        Returns:
            Dictionary of name -> OSCObject
        """
        return self._objects.copy()
    
    def update_object_scale(self, name: str, scale: float) -> None:
        """
        Update scaling factor for an object.
        
        Args:
            name: Object identifier
            scale: New scaling factor (0..1)
        """
        if name in self._objects:
            self._objects[name].scale = max(0.0, min(1.0, scale))
            logger.debug(f"Updated scale for {name}: {scale}")
    
    def set_object_enabled(self, name: str, enabled: bool) -> None:
        """
        Enable or disable an object.
        
        Args:
            name: Object identifier
            enabled: True to enable streaming
        """
        if name in self._objects:
            self._objects[name].enabled = enabled
            logger.debug(f"Set {name} enabled: {enabled}")
    
    def start_streaming(self) -> None:
        """Start OSC streaming at 60 Hz."""
        if self._streaming:
            return
        
        self._streaming = True
        self._timer.start()
        self.streaming_state_changed.emit(True)
        logger.info("OSC streaming started")
    
    def stop_streaming(self) -> None:
        """Stop OSC streaming and send zero values to all objects."""
        if not self._streaming:
            return
        
        self._timer.stop()
        
        # Send zero values to all objects (explicit silence)
        if self._playback_controller:
            current_time = self._playback_controller.get_current_timestamp()
            if current_time is None:
                current_time = UTCDateTime.now()
        else:
            current_time = UTCDateTime.now()
        
        for obj in self._objects.values():
            obj.send(0.0, current_time)
        
        self._streaming = False
        self.streaming_state_changed.emit(False)
        logger.info("OSC streaming stopped")
    
    def is_streaming(self) -> bool:
        """Check if streaming is active."""
        return self._streaming
    
    def _send_frame(self) -> None:
        """Send one frame of data to all enabled objects (called by timer at 60 Hz)."""
        if self._waveform_model is None or self._playback_controller is None:
            return
        
        # Get current timestamp from playback controller
        current_time = self._playback_controller.get_current_timestamp()
        if current_time is None:
            return
        
        # Get normalized value from waveform model
        normalized_value = self._waveform_model.get_normalized_value(current_time)
        
        # Send to all enabled objects
        for obj in self._objects.values():
            obj.send(normalized_value, current_time)

