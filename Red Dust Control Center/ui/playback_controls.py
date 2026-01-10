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
        
        # Row 2: Play | Pause | Stop buttons stretched to full width
        row2 = QHBoxLayout()
        
        # Play button - stretch to full width
        self.play_button = QPushButton("Play")
        self.play_button.clicked.connect(self.play_clicked.emit)
        row2.addWidget(self.play_button, 1)  # Stretch factor of 1 to fill space
        
        # Pause button - stretch to full width
        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self.pause_clicked.emit)
        row2.addWidget(self.pause_button, 1)  # Stretch factor of 1 to fill space
        
        # Stop button - stretch to full width
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_clicked.emit)
        row2.addWidget(self.stop_button, 1)  # Stretch factor of 1 to fill space
        
        layout.addLayout(row2)
        
        # Row 3: Speed manual adjust (left) | 3 speed buttons (middle) | Enable Loop checkbox (right)
        row3 = QHBoxLayout()
        
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
        row3.addLayout(speed_layout, 1)  # Stretch factor for equal columns
        
        # 3 speed buttons (middle) - align center
        row3.addStretch()
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
        
        row3.addLayout(speed_button_layout, 1)  # Stretch factor for equal columns
        
        # Enable Loop checkbox (right) - align right
        row3.addStretch()
        self.loop_checkbox = QCheckBox("Enable Loop")
        self.loop_checkbox.toggled.connect(self.loop_toggled.emit)
        row3.addWidget(self.loop_checkbox, 1, Qt.AlignmentFlag.AlignRight)  # Align right
        
        layout.addLayout(row3)
        
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

