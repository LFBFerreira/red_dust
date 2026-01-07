"""
Playback Controls widget for controlling waveform playback.
"""
from PySide6.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QPushButton, 
                               QDoubleSpinBox, QCheckBox, QLabel, QSlider)
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
    
    def __init__(self, parent=None):
        """Initialize PlaybackControls."""
        super().__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the UI components."""
        layout = QVBoxLayout()
        
        # Playback buttons
        button_layout = QHBoxLayout()
        
        self.play_button = QPushButton("▶")
        self.play_button.clicked.connect(self.play_clicked.emit)
        button_layout.addWidget(self.play_button)
        
        self.pause_button = QPushButton("⏸")
        self.pause_button.clicked.connect(self.pause_clicked.emit)
        button_layout.addWidget(self.pause_button)
        
        self.stop_button = QPushButton("⏹")
        self.stop_button.clicked.connect(self.stop_clicked.emit)
        button_layout.addWidget(self.stop_button)
        
        button_layout.addStretch()
        layout.addLayout(button_layout)
        
        # Speed control
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
        speed_layout.addStretch()
        layout.addLayout(speed_layout)
        
        # Loop checkbox
        self.loop_checkbox = QCheckBox("Enable Loop")
        self.loop_checkbox.toggled.connect(self.loop_toggled.emit)
        layout.addWidget(self.loop_checkbox)
        
        # Time display
        self.time_label = QLabel("--:--:-- / --:--:--")
        layout.addWidget(self.time_label)
        
        # Loop range display
        self.loop_label = QLabel("No loop")
        layout.addWidget(self.loop_label)
        
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

