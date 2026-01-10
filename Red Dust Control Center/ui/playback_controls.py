"""
Playback Controls widget for controlling waveform playback.
"""
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QPushButton, 
                               QDoubleSpinBox, QCheckBox, QLabel, QSlider, QComboBox)
from PySide6.QtCore import Signal, Qt
from obspy import UTCDateTime
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
    
    def __init__(self, parent=None):
        """Initialize PlaybackControls."""
        super().__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the UI components."""
        layout = QVBoxLayout()
        
        # Top row: Channel selector (left), Loop info (center), Time display (right)
        top_row = QHBoxLayout()
        
        # Channel selector (left)
        channel_layout = QHBoxLayout()
        channel_layout.addWidget(QLabel("Active Channel:"))
        self.channel_combo = QComboBox()
        self.channel_combo.currentTextChanged.connect(self._on_channel_changed)
        channel_layout.addWidget(self.channel_combo)
        top_row.addLayout(channel_layout)
        
        # Loop information (center)
        top_row.addStretch()
        self.loop_label = QLabel("No loop")
        top_row.addWidget(self.loop_label)
        
        # Time display (right)
        top_row.addStretch()
        self.time_label = QLabel("--:--:-- / --:--:--")
        top_row.addWidget(self.time_label)
        
        layout.addLayout(top_row)
        
        # Middle row: Play, Pause, Stop buttons equally spaced and stretched
        button_layout = QHBoxLayout()
        
        self.play_button = QPushButton("Play")
        self.play_button.clicked.connect(self.play_clicked.emit)
        button_layout.addWidget(self.play_button, 1)  # Stretch factor of 1
        
        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self.pause_clicked.emit)
        button_layout.addWidget(self.pause_button, 1)  # Stretch factor of 1
        
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_clicked.emit)
        button_layout.addWidget(self.stop_button, 1)  # Stretch factor of 1
        
        layout.addLayout(button_layout)
        
        # Bottom row: Speed (first column), Enable Loop (second column)
        bottom_row = QHBoxLayout()
        
        # Speed control (first column)
        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel("Speed:"))
        self.speed_spinbox = QDoubleSpinBox()
        self.speed_spinbox.setRange(0.1, 10.0)
        self.speed_spinbox.setSingleStep(0.1)
        self.speed_spinbox.setValue(1.0)
        self.speed_spinbox.setDecimals(1)
        self.speed_spinbox.valueChanged.connect(self._on_speed_changed)
        speed_layout.addWidget(self.speed_spinbox)
        speed_layout.addWidget(QLabel("x"))
        bottom_row.addLayout(speed_layout)
        
        # Enable Loop checkbox (second column)
        bottom_row.addStretch()
        self.loop_checkbox = QCheckBox("Enable Loop")
        self.loop_checkbox.toggled.connect(self.loop_toggled.emit)
        bottom_row.addWidget(self.loop_checkbox)
        
        layout.addLayout(bottom_row)
        
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
    
    def update_loop_display(self, start: UTCDateTime = None, end: UTCDateTime = None) -> None:
        """
        Update loop range display.
        
        Args:
            start: Loop start timestamp
            end: Loop end timestamp
        """
        if start is None or end is None:
            self.loop_label.setText("No loop")
        else:
            start_str = self._format_time(start)
            end_str = self._format_time(end)
            self.loop_label.setText(f"Loop: {start_str} - {end_str}")
    
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
    
    def _on_channel_changed(self, channel: str) -> None:
        """Handle channel selection change."""
        if channel:
            self.channel_changed.emit(channel)
    
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

