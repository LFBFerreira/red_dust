"""
Playback Controller for time-based waveform playback.
"""
from obspy import UTCDateTime
from typing import Optional, Tuple
from PySide6.QtCore import QObject, QTimer, Signal
import logging

logger = logging.getLogger(__name__)

# Minimum loop length in seconds
MIN_LOOP_LENGTH = 2.0


class PlaybackController(QObject):
    """Manages time-based playback of waveform data."""
    
    # Signals
    playhead_updated = Signal(UTCDateTime)  # Emitted when playhead position changes
    state_changed = Signal(str)  # Emitted when playback state changes ("stopped", "playing", "paused")
    
    def __init__(self, waveform_model=None):
        """
        Initialize PlaybackController.
        
        Args:
            waveform_model: WaveformModel instance (can be set later)
        """
        super().__init__()
        self._waveform_model = waveform_model
        self._state = "stopped"  # "stopped", "playing", "paused"
        self._speed = 1.0
        self._current_time = None
        self._loop_enabled = False
        self._loop_start = None
        self._loop_end = None
        
        # Timer for playhead updates (60 Hz for smooth UI)
        self._timer = QTimer()
        self._timer.timeout.connect(self._update_playhead)
        self._timer.setInterval(16)  # ~60 Hz
        
        # Track when playback started (for speed calculation)
        self._playback_start_time = None
        self._playback_start_position = None
    
    def set_waveform_model(self, waveform_model) -> None:
        """
        Set waveform model.
        
        Args:
            waveform_model: WaveformModel instance
        """
        self._waveform_model = waveform_model
        if waveform_model:
            time_range = waveform_model.get_time_range()
            if time_range:
                self._current_time = time_range[0]
    
    def start(self) -> None:
        """Start or resume playback."""
        if self._waveform_model is None:
            logger.warning("Cannot start playback: no waveform model set")
            return
        
        time_range = self._waveform_model.get_time_range()
        if not time_range:
            logger.warning("Cannot start playback: no time range available")
            return
        
        start_time, end_time = time_range
        
        # Initialize current time if not set
        if self._current_time is None:
            if self._loop_enabled and self._loop_start:
                self._current_time = self._loop_start
            else:
                self._current_time = start_time
        
        # Record playback start for speed calculation
        from time import time as current_time
        self._playback_start_time = current_time()
        self._playback_start_position = self._current_time
        
        self._state = "playing"
        self._timer.start()
        self.state_changed.emit(self._state)
        logger.info(f"Playback started at {self._current_time}")
    
    def pause(self) -> None:
        """Pause playback."""
        if self._state == "playing":
            self._timer.stop()
            self._state = "paused"
            self.state_changed.emit(self._state)
            logger.info("Playback paused")
    
    def stop(self) -> None:
        """Stop playback and reset to start."""
        self._timer.stop()
        
        if self._waveform_model:
            time_range = self._waveform_model.get_time_range()
            if time_range:
                if self._loop_enabled and self._loop_start:
                    self._current_time = self._loop_start
                else:
                    self._current_time = time_range[0]
        
        self._state = "stopped"
        self._playback_start_time = None
        self._playback_start_position = None
        self.state_changed.emit(self._state)
        self.playhead_updated.emit(self._current_time)
        logger.info("Playback stopped")
    
    def set_speed(self, multiplier: float) -> None:
        """
        Set playback speed multiplier.
        
        Args:
            multiplier: Speed multiplier (0.1 to 1000.0)
        """
        multiplier = max(0.1, min(1000.0, multiplier))
        
        # If currently playing, adjust start position to maintain continuity
        # This ensures playback continues from current position without restarting
        if self._state == "playing" and self._playback_start_time is not None and self._current_time is not None:
            from time import time as current_time
            # Simply update the start position to current position and reset the timer
            # This way playback continues from where it is, just at a different speed
            self._playback_start_position = self._current_time
            self._playback_start_time = current_time()
            self._speed = multiplier
        else:
            self._speed = multiplier
        
        logger.info(f"Playback speed set to {multiplier}x")
    
    def get_speed(self) -> float:
        """Get current playback speed."""
        return self._speed
    
    def set_loop_range(self, start_time: UTCDateTime, end_time: UTCDateTime) -> None:
        """
        Set loop range.
        
        Args:
            start_time: Loop start timestamp
            end_time: Loop end timestamp
        
        Raises:
            ValueError: If loop range is less than minimum length
        """
        loop_length = (end_time - start_time) / 86400.0 * 86400.0  # Convert to seconds
        if loop_length < MIN_LOOP_LENGTH:
            raise ValueError(f"Loop range must be at least {MIN_LOOP_LENGTH} seconds")
        
        self._loop_start = start_time
        self._loop_end = end_time
        logger.info(f"Loop range set: {start_time} to {end_time}")
    
    def enable_loop(self, enabled: bool) -> None:
        """
        Enable or disable looping.
        
        Args:
            enabled: True to enable looping
        """
        self._loop_enabled = enabled
        logger.info(f"Loop {'enabled' if enabled else 'disabled'}")
    
    def get_loop_range(self) -> Optional[Tuple[UTCDateTime, UTCDateTime]]:
        """
        Get current loop range.
        
        Returns:
            Tuple of (start_time, end_time) or None if not set
        """
        if self._loop_start and self._loop_end:
            return (self._loop_start, self._loop_end)
        return None
    
    def is_loop_enabled(self) -> bool:
        """Check if looping is enabled."""
        return self._loop_enabled
    
    def get_current_timestamp(self) -> Optional[UTCDateTime]:
        """
        Get current playhead timestamp.
        
        Returns:
            Current UTC timestamp or None
        """
        return self._current_time
    
    def get_playback_state(self) -> str:
        """
        Get current playback state.
        
        Returns:
            "stopped", "playing", or "paused"
        """
        return self._state
    
    def _update_playhead(self) -> None:
        """Update playhead position (called by timer)."""
        if self._waveform_model is None or self._current_time is None:
            return
        
        if self._playback_start_time is None:
            return
        
        from time import time as current_time
        elapsed = current_time() - self._playback_start_time
        time_delta = elapsed * self._speed
        
        # Calculate new position (add seconds directly to UTCDateTime)
        new_time = self._playback_start_position + time_delta
        
        # Get time range
        time_range = self._waveform_model.get_time_range()
        if not time_range:
            return
        
        start_time, end_time = time_range
        
        # Handle loop or end of data
        if self._loop_enabled and self._loop_start and self._loop_end:
            if new_time > self._loop_end:
                # Loop back to start
                self._current_time = self._loop_start
                self._playback_start_position = self._loop_start
                self._playback_start_time = current_time()
            else:
                self._current_time = new_time
        else:
            if new_time > end_time:
                # Reached end, stop playback
                self._current_time = end_time
                self.stop()
            else:
                self._current_time = new_time
        
        # Emit signal for UI updates
        self.playhead_updated.emit(self._current_time)

