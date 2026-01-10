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
        self.name = name
        self.address = address
        self.host = host
        self.port = port
        self.remap_min = remap_min
        self.remap_max = remap_max
        self.streaming_enabled = False  # Per-object streaming state
        self._client = None
        
        # Create OSC client
        try:
            self._client = UDPClient(host, port)
            logger.info(f"Created OSC client for {name} at {host}:{port}")
        except Exception as e:
            logger.error(f"Failed to create OSC client for {name}: {e}")
    
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
    
    def send(self, normalized_value: float, timestamp: UTCDateTime) -> float:
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


class OSCManager(QObject):
    """Manages OSC streaming to multiple interactive objects."""
    
    # Signal emitted when streaming state changes (global)
    streaming_state_changed = Signal(bool)  # True when streaming starts
    
    # Signal emitted when object streaming state changes
    object_streaming_state_changed = Signal(str, bool)  # Emits (object_name, streaming)
    
    # Signal emitted when object value is updated (for UI display)
    object_value_updated = Signal(str, float)  # Emits (object_name, remapped_value)
    
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
        
        # Timer for 60 Hz output (always running when objects are streaming)
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
    
    def add_object(self, name: str, address: str, host: str, port: int, remap_min: float = 0.0, remap_max: float = 1.0) -> OSCObject:
        """
        Add a new OSC object.
        
        Args:
            name: Unique identifier
            address: OSC address
            host: Target IP address
            port: Target UDP port
            remap_min: Minimum output value for remapping (default: 0.0)
            remap_max: Maximum output value for remapping (default: 1.0)
        
        Returns:
            OSCObject instance
        """
        if name in self._objects:
            logger.warning(f"Object {name} already exists, replacing it")
            self.remove_object(name)
        
        obj = OSCObject(name, address, host, port, remap_min, remap_max)
        self._objects[name] = obj
        
        # Start timer if not already running (needed for per-object streaming)
        if not self._timer.isActive():
            self._timer.start()
        
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
    
    def update_object_remapping(self, name: str, remap_min: float, remap_max: float) -> None:
        """
        Update remapping parameters for an object.
        
        Args:
            name: Object identifier
            remap_min: Minimum output value
            remap_max: Maximum output value
        """
        if name in self._objects:
            self._objects[name].remap_min = remap_min
            self._objects[name].remap_max = remap_max
            logger.debug(f"Updated remapping for {name}: {remap_min} to {remap_max}")
    
    def start_object_streaming(self, name: str) -> None:
        """
        Start streaming for a specific object.
        
        Args:
            name: Object identifier
        """
        if name in self._objects:
            if not self._objects[name].streaming_enabled:
                self._objects[name].streaming_enabled = True
                self.object_streaming_state_changed.emit(name, True)
                logger.info(f"Started streaming for object: {name}")
                
                # Ensure timer is running
                if not self._timer.isActive():
                    self._timer.start()
    
    def stop_object_streaming(self, name: str) -> None:
        """
        Stop streaming for a specific object.
        
        Args:
            name: Object identifier
        """
        if name in self._objects:
            if self._objects[name].streaming_enabled:
                self._objects[name].streaming_enabled = False
                self.object_streaming_state_changed.emit(name, False)
                logger.info(f"Stopped streaming for object: {name}")
                
                # Send zero value when stopping
                if self._playback_controller:
                    current_time = self._playback_controller.get_current_timestamp()
                    if current_time is None:
                        current_time = UTCDateTime.now()
                else:
                    current_time = UTCDateTime.now()
                
                # Send zero value
                obj = self._objects[name]
                normalized_zero = 0.0
                remapped_zero = obj.remap_value(normalized_zero)
                try:
                    from pythonosc.osc_message_builder import OscMessageBuilder
                    builder = OscMessageBuilder(obj.address)
                    builder.add_arg(remapped_zero)
                    builder.add_arg(current_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"))
                    msg = builder.build()
                    if obj._client:
                        obj._client.send(msg)
                    # Emit value update signal for UI
                    self.object_value_updated.emit(name, remapped_zero)
                except Exception as e:
                    logger.error(f"Failed to send stop message for {name}: {e}")
                
                # Stop timer if no objects are streaming
                if not any(obj.streaming_enabled for obj in self._objects.values()):
                    self._timer.stop()
    
    def is_object_streaming(self, name: str) -> bool:
        """
        Check if a specific object is streaming.
        
        Args:
            name: Object identifier
        
        Returns:
            True if object is streaming
        """
        if name in self._objects:
            return self._objects[name].streaming_enabled
        return False
    
    def set_object_enabled(self, name: str, enabled: bool) -> None:
        """
        Enable or disable an object (kept for backward compatibility).
        This now controls per-object streaming state.
        
        Args:
            name: Object identifier
            enabled: True to enable streaming
        """
        if enabled:
            self.start_object_streaming(name)
        else:
            self.stop_object_streaming(name)
    
    def start_streaming(self) -> None:
        """Start OSC streaming at 60 Hz (global streaming - kept for backward compatibility)."""
        if self._streaming:
            return
        
        self._streaming = True
        # Timer is managed per-object now, but we ensure it's running
        if not self._timer.isActive():
            self._timer.start()
        self.streaming_state_changed.emit(True)
        logger.info("OSC streaming started (global)")
    
    def stop_streaming(self) -> None:
        """Stop OSC streaming and send zero values to all streaming objects."""
        if not self._streaming:
            return
        
        # Send zero values to all streaming objects (explicit silence)
        if self._playback_controller:
            current_time = self._playback_controller.get_current_timestamp()
            if current_time is None:
                current_time = UTCDateTime.now()
        else:
            current_time = UTCDateTime.now()
        
        for obj in self._objects.values():
            if obj.streaming_enabled:
                normalized_zero = 0.0
                remapped_zero = obj.remap_value(normalized_zero)
                try:
                    from pythonosc.osc_message_builder import OscMessageBuilder
                    builder = OscMessageBuilder(obj.address)
                    builder.add_arg(remapped_zero)
                    builder.add_arg(current_time.strftime("%Y-%m-%dT%H:%M:%S.%fZ"))
                    msg = builder.build()
                    if obj._client:
                        obj._client.send(msg)
                except Exception as e:
                    logger.error(f"Failed to send stop message for {obj.name}: {e}")
        
        self._streaming = False
        self.streaming_state_changed.emit(False)
        logger.info("OSC streaming stopped (global)")
    
    def is_streaming(self) -> bool:
        """Check if streaming is active (global state)."""
        return self._streaming
    
    def _send_frame(self) -> None:
        """Send one frame of data to all streaming objects (called by timer at 60 Hz)."""
        if self._waveform_model is None or self._playback_controller is None:
            return
        
        # Get current timestamp from playback controller
        current_time = self._playback_controller.get_current_timestamp()
        if current_time is None:
            return
        
        # Get normalized value from waveform model
        normalized_value = self._waveform_model.get_normalized_value(current_time)
        
        # Send to all objects that have streaming enabled
        for obj in self._objects.values():
            if obj.streaming_enabled:
                remapped_value = obj.send(normalized_value, current_time)
                # Emit signal for UI updates
                if remapped_value is not None:
                    self.object_value_updated.emit(obj.name, remapped_value)

