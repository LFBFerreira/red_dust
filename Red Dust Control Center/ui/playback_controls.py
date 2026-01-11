"""
Playback Controls widget for controlling waveform playback.
"""
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QPushButton, 
                               QDoubleSpinBox, QCheckBox, QLabel, QSlider, QComboBox)
from PySide6.QtCore import Signal, Qt
from obspy import UTCDateTime
from typing import Optional
import logging

logger = logging.getLogger(__name__)


class PlaybackControls(QWidget):
    """Widget for controlling playback."""
    
    # Signals
    play_clicked = Signal()
    pause_clicked = Signal()
    stop_clicked = Signal()
    speed_changed = Signal(float)  # Emits speed multiplier
    loop_toggled = Signal(bool)  # Emits loop enabled state
    channel_changed = Signal(str)  # Emits active channel name
    position_changed = Signal(UTCDateTime)  # Emits playhead position timestamp
    
    def __init__(self, parent=None):
        """Initialize PlaybackControls."""
        super().__init__(parent)
        self._position_slider_updating = False
        self._pending_slider_value = None
        self._time_range = None  # Store time range for slider conversion
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the UI components."""
        layout = QVBoxLayout()
        
        # Row 1: Active Channel (left) | Loop label (center) | Time information (right)
        row1 = QHBoxLayout()
        
        # Active Channel (left) - align left, combo box right next to label
        channel_layout = QHBoxLayout()
        channel_layout.setContentsMargins(0, 0, 0, 0)
        channel_layout.addWidget(QLabel("Active Channel:"))
        self.channel_combo = QComboBox()
        self.channel_combo.currentTextChanged.connect(self._on_channel_changed)
        channel_layout.addWidget(self.channel_combo)
        channel_layout.addStretch()  # Push to left
        row1.addLayout(channel_layout, 1)  # Stretch factor for equal columns
        
        # Value display (center) - shows raw and normalized values
        row1.addStretch()
        self.value_label = QLabel("Raw: -- | Norm: --")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        row1.addWidget(self.value_label, 1)  # Stretch factor for equal columns
        
        # Time information (right) - align right
        row1.addStretch()
        self.time_label = QLabel("--:--:-- / --:--:--")
        self.time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row1.addWidget(self.time_label, 1)  # Stretch factor for equal columns
        
        layout.addLayout(row1)
        
        # Row 2: Playhead position slider
        row2 = QHBoxLayout()
        
        # Position label (left)
        position_label = QLabel("Position:")
        row2.addWidget(position_label)
        
        # Position slider (center) - stretches to fill space
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setMinimum(0)
        self.position_slider.setMaximum(1000)  # Will be updated based on time range
        self.position_slider.setValue(0)
        self.position_slider.valueChanged.connect(self._on_position_slider_changed)
        row2.addWidget(self.position_slider, 1)  # Stretch to fill
        
        # Position time display (right)
        self.position_time_label = QLabel("--:--:--")
        self.position_time_label.setMinimumWidth(80)
        self.position_time_label.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        row2.addWidget(self.position_time_label)
        
        layout.addLayout(row2)
        
        # Row 3: Play | Pause | Stop buttons stretched to full width
        row3 = QHBoxLayout()
        
        # Play button - stretch to full width
        self.play_button = QPushButton("Play")
        self.play_button.clicked.connect(self.play_clicked.emit)
        row3.addWidget(self.play_button, 1)  # Stretch factor of 1 to fill space
        
        # Pause button - stretch to full width
        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self.pause_clicked.emit)
        row3.addWidget(self.pause_button, 1)  # Stretch factor of 1 to fill space
        
        # Stop button - stretch to full width
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_clicked.emit)
        self.stop_button.setEnabled(False)  # Disabled when stopped
        row3.addWidget(self.stop_button, 1)  # Stretch factor of 1 to fill space
        
        layout.addLayout(row3)
        
        # Set initial state (stopped)
        self._update_button_states("stopped")
        
        # Row 4: Speed manual adjust (left) | 3 speed buttons (middle) | Enable Loop checkbox (right)
        row4 = QHBoxLayout()
        
        # Speed manual adjust (left) - align left, input box right next to label
        speed_layout = QHBoxLayout()
        speed_layout.setContentsMargins(0, 0, 0, 0)
        speed_layout.addWidget(QLabel("Speed:"))
        self.speed_spinbox = QDoubleSpinBox()
        self.speed_spinbox.setRange(0.1, 1000.0)
        self.speed_spinbox.setSingleStep(0.1)
        self.speed_spinbox.setValue(1.0)
        self.speed_spinbox.setDecimals(1)
        self.speed_spinbox.valueChanged.connect(self._on_speed_changed)
        speed_layout.addWidget(self.speed_spinbox)
        speed_layout.addWidget(QLabel("x"))
        speed_layout.addStretch()  # Push to left
        row4.addLayout(speed_layout, 1)  # Stretch factor for equal columns
        
        # 3 speed buttons (middle) - align center
        row4.addStretch()
        speed_button_layout = QHBoxLayout()
        
        btn_1x = QPushButton("1x")
        btn_1x.clicked.connect(lambda: self._set_speed_preset(1.0))
        speed_button_layout.addWidget(btn_1x)
        
        btn_100x = QPushButton("100x")
        btn_100x.clicked.connect(lambda: self._set_speed_preset(100.0))
        speed_button_layout.addWidget(btn_100x)
        
        btn_1000x = QPushButton("1000x")
        btn_1000x.clicked.connect(lambda: self._set_speed_preset(1000.0))
        speed_button_layout.addWidget(btn_1000x)
        
        row4.addLayout(speed_button_layout, 1)  # Stretch factor for equal columns
        
        # Enable Loop checkbox (right) - align right
        row4.addStretch()
        self.loop_checkbox = QCheckBox("Enable Loop")
        self.loop_checkbox.toggled.connect(self.loop_toggled.emit)
        row4.addWidget(self.loop_checkbox, 1, Qt.AlignmentFlag.AlignRight)  # Align right
        
        layout.addLayout(row4)
        
        layout.addStretch()
        self.setLayout(layout)
    
    def update_time_display(self, current: UTCDateTime, total: UTCDateTime) -> None:
        """
        Update time display.
        
        Args:
            current: Current playhead timestamp
            total: Total duration timestamp
        """
        if current is None or total is None:
            self.time_label.setText("--:--:-- / --:--:--")
            return
        
        # Format as HH:MM:SS
        current_str = self._format_time(current)
        total_str = self._format_time(total)
        self.time_label.setText(f"{current_str} / {total_str}")
    
    def update_value_display(self, raw_value: float = None, normalized_value: float = None) -> None:
        """
        Update value display showing raw and normalized values.
        
        Args:
            raw_value: Raw waveform value (before remapping)
            normalized_value: Normalized value (after remapping, 0-1)
        """
        if raw_value is None or normalized_value is None:
            self.value_label.setText("Raw: -- | Norm: --")
        else:
            # Format raw value with appropriate precision
            raw_str = f"{raw_value:.6f}" if abs(raw_value) < 1000 else f"{raw_value:.2f}"
            # Format normalized value to 3 decimal places
            norm_str = f"{normalized_value:.3f}"
            self.value_label.setText(f"Raw: {raw_str} | Norm: {norm_str}")
    
    def update_loop_display(self, start: UTCDateTime = None, end: UTCDateTime = None) -> None:
        """
        Update loop range display (kept for compatibility but not used in UI).
        
        Args:
            start: Loop start timestamp
            end: Loop end timestamp
        """
        # This method is kept for compatibility but the loop display is now replaced
        # by the value display. Loop info can be shown elsewhere if needed.
        pass
    
    def set_loop_enabled(self, enabled: bool) -> None:
        """
        Set loop checkbox state.
        
        Args:
            enabled: True to enable loop
        """
        self.loop_checkbox.setChecked(enabled)
    
    def set_speed(self, speed: float) -> None:
        """
        Set speed value.
        
        Args:
            speed: Speed multiplier
        """
        self.speed_spinbox.setValue(speed)
    
    def _format_time(self, timestamp: UTCDateTime) -> str:
        """
        Format UTC timestamp as HH:MM:SS.
        
        Args:
            timestamp: UTC timestamp
        
        Returns:
            Formatted time string
        """
        hours = timestamp.hour
        minutes = timestamp.minute
        seconds = timestamp.second
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    
    def _on_speed_changed(self, value: float) -> None:
        """Handle speed value change."""
        self.speed_changed.emit(value)
    
    def _set_speed_preset(self, speed: float) -> None:
        """Set speed to a preset value."""
        self.speed_spinbox.setValue(speed)
    
    def _on_channel_changed(self, channel: str) -> None:
        """Handle channel selection change."""
        if channel:
            self.channel_changed.emit(channel)
    
    def _on_position_slider_changed(self, value: int) -> None:
        """Handle position slider change."""
        if self._position_slider_updating:
            return
        
        # Store slider value - main window will convert it to timestamp using time range
        self._pending_slider_value = value
        # Signal will be emitted by main window after conversion
    
    def update_position_slider(self, current_time: UTCDateTime, start_time: UTCDateTime, end_time: UTCDateTime) -> None:
        """
        Update position slider based on current playhead position.
        
        Args:
            current_time: Current playhead timestamp
            start_time: Start of time range
            end_time: End of time range
        """
        if start_time is None or end_time is None or current_time is None:
            return
        
        # Store time range for slider value conversion
        self._time_range = (start_time, end_time)
        
        # Prevent feedback loop
        self._position_slider_updating = True
        
        # Calculate position as percentage
        total_duration = (end_time - start_time)
        if total_duration > 0:
            elapsed = (current_time - start_time)
            percentage = elapsed / total_duration
            slider_value = int(percentage * 1000)  # 0-1000 range
            slider_value = max(0, min(1000, slider_value))  # Clamp
            self.position_slider.setValue(slider_value)
        
        # Update position time label
        self.position_time_label.setText(self._format_time(current_time))
        
        self._position_slider_updating = False
    
    def get_pending_position(self) -> Optional[UTCDateTime]:
        """
        Get pending position from slider if user is dragging.
        
        Returns:
            Timestamp corresponding to slider position, or None if no pending change
        """
        if self._pending_slider_value is None or self._time_range is None:
            return None
        
        start_time, end_time = self._time_range
        slider_value = self._pending_slider_value
        percentage = slider_value / 1000.0  # 0.0 to 1.0
        
        total_duration = (end_time - start_time)
        if total_duration <= 0:
            return None
        
        offset = total_duration * percentage
        timestamp = start_time + offset
        
        # Clear pending value after reading
        self._pending_slider_value = None
        
        return timestamp
    
    def set_channels(self, channels: list[str]) -> None:
        """
        Set available channels in the combo box.
        
        Args:
            channels: List of channel identifiers
        """
        self.channel_combo.clear()
        if channels:
            self.channel_combo.addItems(channels)
    
    def set_active_channel(self, channel: str) -> None:
        """
        Set the active channel in the combo box.
        
        Args:
            channel: Channel identifier to select
        """
        index = self.channel_combo.findText(channel)
        if index >= 0:
            self.channel_combo.setCurrentIndex(index)
    
    def _update_button_states(self, state: str) -> None:
        """
        Update button states based on playback state.
        
        Args:
            state: Playback state ("stopped", "playing", "paused")
        """
        if state == "playing":
            self.play_button.setEnabled(False)   # Disable play when playing
            self.pause_button.setEnabled(True)   # Enable pause when playing
            self.stop_button.setEnabled(True)    # Enable stop when playing
        elif state == "paused":
            self.play_button.setEnabled(True)    # Enable play when paused
            self.pause_button.setEnabled(False)  # Disable pause when paused
            self.stop_button.setEnabled(True)    # Enable stop when paused
        else:  # stopped
            self.play_button.setEnabled(True)    # Enable play when stopped
            self.pause_button.setEnabled(False)  # Disable pause when stopped
            self.stop_button.setEnabled(False)   # Disable stop when stopped
    
    def set_playback_state(self, state: str) -> None:
        """
        Set playback state and update button states.
        
        Args:
            state: Playback state ("stopped", "playing", "paused")
        """
        self._update_button_states(state)

