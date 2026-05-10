"""
Object Manager for streaming normalized data to interactive objects (OSC and Serial).
"""
from typing import Dict, Optional, Union
from obspy import UTCDateTime
from PySide6.QtCore import QObject, QTimer, Signal
import logging

from core.interactive_object import InteractiveObject
from core.osc_object import OSCObject
from core.serial_object import SerialObject
from settings import SERIAL_BAUDRATE, OSC_OUTPUT_RATE, OSC_OUTPUT_INTERVAL_MS, SERIAL_OUTPUT_RATE, SERIAL_OUTPUT_INTERVAL_MS

logger = logging.getLogger(__name__)

# Backward compatibility: export OSCObject from here
__all__ = ['OSCManager', 'OSCObject', 'SerialObject']


class OSCManager(QObject):
    """Manages streaming to multiple interactive objects (OSC and Serial)."""
    
    # Signal emitted when streaming state changes (global)
    streaming_state_changed = Signal(bool)  # True when streaming starts
    
    # Signal emitted when object streaming state changes
    object_streaming_state_changed = Signal(str, bool)  # Emits (object_name, streaming)
    
    # Signal emitted when object value is updated (for UI display)
    object_value_updated = Signal(str, float)  # Emits (object_name, normalized_value)
    
    # Signal emitted when object connection state changes (for Serial objects)
    object_connection_state_changed = Signal(str, bool)  # Emits (object_name, connected)
    
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
        self._objects: Dict[str, InteractiveObject] = {}
        self._streaming = False
        
        # Separate timers for OSC and Serial objects
        self._osc_timer = QTimer()
        self._osc_timer.timeout.connect(self._send_osc_frame)
        self._osc_timer.setInterval(OSC_OUTPUT_INTERVAL_MS)
        
        self._serial_timer = QTimer()
        self._serial_timer.timeout.connect(self._send_serial_frame)
        self._serial_timer.setInterval(SERIAL_OUTPUT_INTERVAL_MS)
    
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
    
    def add_osc_object(self, name: str, address: str, host: str, port: int, remap_min: float = 0.0, remap_max: float = 1.0) -> OSCObject:
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
        
        # Start OSC timer if not already running (needed for per-object streaming)
        if not self._osc_timer.isActive():
            self._osc_timer.start()
        
        logger.info(f"Added OSC object: {name}")
        return obj
    
    def add_serial_object(self, name: str, port: str, baudrate: int = None, remap_min: float = 0.0, remap_max: float = 1.0) -> SerialObject:
        """
        Add a new Serial object.
        
        Args:
            name: Unique identifier
            port: Serial port (e.g., "COM3" on Windows, "/dev/ttyUSB0" on Linux)
            baudrate: Baud rate for serial communication (default: from settings)
            remap_min: Minimum output value for remapping (default: 0.0)
            remap_max: Maximum output value for remapping (default: 1.0)
        
        Returns:
            SerialObject instance
        """
        if name in self._objects:
            logger.warning(f"Object {name} already exists, replacing it")
            self.remove_object(name)
        
        if baudrate is None:
            baudrate = SERIAL_BAUDRATE
        
        obj = SerialObject(name, port, baudrate, remap_min, remap_max)
        self._objects[name] = obj
        
        # Emit connection state signal
        self.object_connection_state_changed.emit(name, obj.is_connected())
        
        # Start Serial timer if not already running (needed for per-object streaming)
        if not self._serial_timer.isActive():
            self._serial_timer.start()
        
        logger.info(f"Added Serial object: {name}")
        return obj
    
    def add_object(self, name: str, address: str, host: str, port: int, remap_min: float = 0.0, remap_max: float = 1.0) -> OSCObject:
        """
        Add a new OSC object (backward compatibility method).
        
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
        return self.add_osc_object(name, address, host, port, remap_min, remap_max)
    
    def remove_object(self, name: str) -> None:
        """
        Remove an object.
        
        Args:
            name: Object identifier
        """
        if name in self._objects:
            obj = self._objects[name]
            
            # Stop streaming if active
            if obj.streaming_enabled:
                self.stop_object_streaming(name)
            
            # Close connection properly
            obj.close()
            
            # Emit connection state change for Serial objects
            from core.serial_object import SerialObject
            if isinstance(obj, SerialObject):
                self.object_connection_state_changed.emit(name, False)
            
            del self._objects[name]
            logger.info(f"Removed object: {name}")
    
    def get_object(self, name: str) -> Optional[InteractiveObject]:
        """
        Get object by name.
        
        Args:
            name: Object identifier
        
        Returns:
            InteractiveObject or None if not found
        """
        return self._objects.get(name)
    
    def get_all_objects(self) -> Dict[str, InteractiveObject]:
        """
        Get all objects.
        
        Returns:
            Dictionary of name -> InteractiveObject
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
            obj = self._objects[name]
            
            # For Serial objects, check connection and try to reconnect if needed
            if isinstance(obj, SerialObject):
                if not obj.is_connected():
                    logger.warning(f"Serial object {name} is not connected, attempting to reconnect...")
                    if not obj.reconnect():
                        logger.error(f"Cannot start streaming for {name}: Serial connection failed")
                        # Emit connection state change
                        self.object_connection_state_changed.emit(name, False)
                        return
                    else:
                        # Connection restored
                        self.object_connection_state_changed.emit(name, True)
            
            if not obj.streaming_enabled:
                obj.streaming_enabled = True
                self.object_streaming_state_changed.emit(name, True)
                logger.info(f"Started streaming for object: {name}")
                
                # Ensure appropriate timer is running
                if isinstance(obj, SerialObject):
                    if not self._serial_timer.isActive():
                        self._serial_timer.start()
                else:  # OSC object
                    if not self._osc_timer.isActive():
                        self._osc_timer.start()
    
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
                remapped_zero = obj.send(normalized_zero, current_time)
                # Emit value update signal for UI (emit normalized value so card can remap using its own settings)
                if remapped_zero is not None:
                    self.object_value_updated.emit(name, normalized_zero)
                
                # Stop timers if no objects of that type are streaming
                if isinstance(obj, SerialObject):
                    if not any(o.streaming_enabled for o in self._objects.values() if isinstance(o, SerialObject)):
                        self._serial_timer.stop()
                else:  # OSC object
                    if not any(o.streaming_enabled for o in self._objects.values() if isinstance(o, OSCObject)):
                        self._osc_timer.stop()
    
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
        """Start streaming (global streaming - kept for backward compatibility)."""
        if self._streaming:
            return
        
        self._streaming = True
        # Timers are managed per-object now, but we ensure they're running if needed
        has_osc_objects = any(isinstance(obj, OSCObject) and obj.streaming_enabled for obj in self._objects.values())
        has_serial_objects = any(isinstance(obj, SerialObject) and obj.streaming_enabled for obj in self._objects.values())
        if has_osc_objects and not self._osc_timer.isActive():
            self._osc_timer.start()
        if has_serial_objects and not self._serial_timer.isActive():
            self._serial_timer.start()
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
                obj.send(normalized_zero, current_time)
        
        self._streaming = False
        self.streaming_state_changed.emit(False)
        logger.info("OSC streaming stopped (global)")
    
    def is_streaming(self) -> bool:
        """Check if streaming is active (global state)."""
        return self._streaming
    
    def _send_osc_frame(self) -> None:
        """Send one frame of data to all streaming OSC objects (called by OSC timer)."""
        if self._waveform_model is None or self._playback_controller is None:
            return
        
        # Get current timestamp from playback controller
        current_time = self._playback_controller.get_current_timestamp()
        if current_time is None:
            return
        
        # Get normalized value from waveform model
        normalized_value = self._waveform_model.get_normalized_value(current_time)
        
        # Send to all OSC objects that have streaming enabled
        for obj in self._objects.values():
            if isinstance(obj, OSCObject) and obj.streaming_enabled:
                remapped_value = obj.send(normalized_value, current_time)
                # Emit signal for UI updates (emit normalized value so card can remap using its own settings)
                if remapped_value is not None:
                    self.object_value_updated.emit(obj.name, normalized_value)
    
    def _send_serial_frame(self) -> None:
        """Send one frame of data to all streaming Serial objects (called by Serial timer)."""
        if self._waveform_model is None or self._playback_controller is None:
            return
        
        # Get current timestamp from playback controller
        current_time = self._playback_controller.get_current_timestamp()
        if current_time is None:
            return
        
        # Get normalized value from waveform model
        normalized_value = self._waveform_model.get_normalized_value(current_time)
        
        # Send to all Serial objects that have streaming enabled
        for obj in self._objects.values():
            if isinstance(obj, SerialObject) and obj.streaming_enabled:
                remapped_value = obj.send(normalized_value, current_time)
                # Emit signal for UI updates (emit normalized value so card can remap using its own settings)
                if remapped_value is not None:
                    self.object_value_updated.emit(obj.name, normalized_value)

