"""
Object Cards widget for managing OSC output objects.
"""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                               QLineEdit, QDoubleSpinBox, QPushButton, 
                               QScrollArea, QFrame, QProgressBar)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QPalette
import logging
from settings import STREAMING_PORT, INTERACTIVE_OBJECTS_HEIGHT, OBJECT_CARD_WIDTH

logger = logging.getLogger(__name__)


class ObjectCard(QFrame):
    """Individual card widget for an OSC object."""
    
    # Signals
    removed = Signal(str)  # Emits object name
    config_changed = Signal(str)  # Emits object name when config changes
    streaming_started = Signal(str)  # Emits object name when streaming starts
    streaming_stopped = Signal(str)  # Emits object name when streaming stops
    
    def __init__(self, name: str, parent=None):
        """
        Initialize ObjectCard.
        
        Args:
            name: Unique identifier for the object
            parent: Parent widget
        """
        super().__init__(parent)
        self._name = name
        self._streaming = False
        self._setup_ui()
        self.setFrameStyle(QFrame.Shape.Box)
        self.setLineWidth(1)
        self.setFixedWidth(OBJECT_CARD_WIDTH)  # Fixed width, independent of window size
        # Set red background color based on theme
        self._update_background_color()
    
    def _setup_ui(self):
        """Set up the UI components."""
        layout = QVBoxLayout()
        layout.setSpacing(8)
        layout.setContentsMargins(10, 10, 10, 10)
        
        # Header with name and remove button
        header_layout = QHBoxLayout()
        name_label = QLabel(f"<b>{self._name}</b>")
        name_label.setStyleSheet("font-size: 12pt;")
        header_layout.addWidget(name_label)
        header_layout.addStretch()
        
        remove_button = QPushButton("✕")
        remove_button.setMaximumWidth(30)
        remove_button.setMaximumHeight(25)
        remove_button.clicked.connect(lambda: self.removed.emit(self._name))
        header_layout.addWidget(remove_button)
        layout.addLayout(header_layout)
        
        # OSC Address and IP Address side by side
        address_ip_layout = QHBoxLayout()
        
        # OSC Address (left)
        osc_address_layout = QVBoxLayout()
        osc_address_layout.addWidget(QLabel("OSC Address:"))
        self.address_edit = QLineEdit()
        self.address_edit.setText(f"/red_dust/{self._name.lower().replace(' ', '_')}")
        self.address_edit.textChanged.connect(lambda: self.config_changed.emit(self._name))
        osc_address_layout.addWidget(self.address_edit)
        address_ip_layout.addLayout(osc_address_layout)
        
        # IP Address (right)
        ip_address_layout = QVBoxLayout()
        ip_address_layout.addWidget(QLabel("IP Address:"))
        self.host_edit = QLineEdit()
        self.host_edit.setText("127.0.0.1")
        self.host_edit.textChanged.connect(lambda: self.config_changed.emit(self._name))
        ip_address_layout.addWidget(self.host_edit)
        address_ip_layout.addLayout(ip_address_layout)
        
        layout.addLayout(address_ip_layout)
        
        # Remap Min and Max side by side
        remap_layout = QHBoxLayout()
        
        # Remap Min (left)
        remap_min_layout = QVBoxLayout()
        remap_min_layout.addWidget(QLabel("Min:"))
        self.remap_min_spinbox = QDoubleSpinBox()
        self.remap_min_spinbox.setRange(-1000000.0, 1000000.0)
        self.remap_min_spinbox.setValue(0.0)
        self.remap_min_spinbox.setDecimals(3)
        self.remap_min_spinbox.valueChanged.connect(lambda: self._validate_remapping())
        self.remap_min_spinbox.valueChanged.connect(lambda: self.config_changed.emit(self._name))
        remap_min_layout.addWidget(self.remap_min_spinbox)
        remap_layout.addLayout(remap_min_layout)
        
        # Remap Max (right)
        remap_max_layout = QVBoxLayout()
        remap_max_layout.addWidget(QLabel("Max:"))
        self.remap_max_spinbox = QDoubleSpinBox()
        self.remap_max_spinbox.setRange(-1000000.0, 1000000.0)
        self.remap_max_spinbox.setValue(1.0)
        self.remap_max_spinbox.setDecimals(3)
        self.remap_max_spinbox.valueChanged.connect(lambda: self._validate_remapping())
        self.remap_max_spinbox.valueChanged.connect(lambda: self.config_changed.emit(self._name))
        remap_max_layout.addWidget(self.remap_max_spinbox)
        remap_layout.addLayout(remap_max_layout)
        
        layout.addLayout(remap_layout)
        
        # Streaming controls section
        streaming_controls_layout = QHBoxLayout()
        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self._on_start_clicked)
        streaming_controls_layout.addWidget(self.start_button, 1)  # Stretch factor to fill width
        
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self._on_stop_clicked)
        self.stop_button.setEnabled(False)  # Disabled when streaming is off
        streaming_controls_layout.addWidget(self.stop_button, 1)  # Stretch factor to fill width
        
        layout.addLayout(streaming_controls_layout)
        
        # Progress bar (shows remapped value)
        self.value_progress = QProgressBar()
        self.value_progress.setRange(0, 100)
        self.value_progress.setValue(0)
        self.value_progress.setFormat("0.000")  # Will be updated with actual value
        self.value_progress.setTextVisible(True)
        # Set initial consistent style (will be kept throughout)
        self.value_progress.setStyleSheet("""
            QProgressBar {
                border: 1px solid grey;
                border-radius: 3px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: grey;
            }
        """)
        layout.addWidget(self.value_progress)
        
        layout.addStretch()
        self.setLayout(layout)
    
    def _update_background_color(self) -> None:
        """Update background color based on system theme."""
        try:
            # Check if we're using a dark theme by examining the palette
            palette = self.palette()
            window_color = palette.color(palette.ColorRole.Window)
            # If window background is dark (lightness < 128), use dark theme colors
            is_dark_theme = window_color.lightness() < 128
            
            if is_dark_theme:
                # Dark red background for dark theme (less saturated)
                self.setStyleSheet("background-color: #3a2a2a;")  # Less saturated dark red
            else:
                # Light red background for light theme
                self.setStyleSheet("background-color: #ffe0e0;")  # Light red
        except Exception:
            # Fallback to light red if theme detection fails
            self.setStyleSheet("background-color: #ffe0e0;")  # Light red
    
    def showEvent(self, event) -> None:
        """Override showEvent to update background color when widget is shown."""
        super().showEvent(event)
        # Update background color when widget becomes visible (palette is fully initialized)
        self._update_background_color()
    
    def _validate_remapping(self) -> None:
        """Validate that remap_min < remap_max."""
        min_val = self.remap_min_spinbox.value()
        max_val = self.remap_max_spinbox.value()
        if min_val >= max_val:
            # Adjust max to be slightly above min
            self.remap_max_spinbox.setValue(min_val + 0.001)
    
    def _on_start_clicked(self) -> None:
        """Handle start button click."""
        self._streaming = True
        self.start_button.setEnabled(False)  # Disable start when streaming
        self.stop_button.setEnabled(True)   # Enable stop when streaming
        self.streaming_started.emit(self._name)
    
    def _on_stop_clicked(self) -> None:
        """Handle stop button click."""
        self._streaming = False
        self.start_button.setEnabled(True)   # Enable start when stopped
        self.stop_button.setEnabled(False)   # Disable stop when stopped
        self.streaming_stopped.emit(self._name)
    
    def set_streaming_state(self, streaming: bool) -> None:
        """
        Set streaming state (called externally).
        
        Args:
            streaming: True if streaming, False if stopped
        """
        if streaming != self._streaming:
            if streaming:
                self._on_start_clicked()
            else:
                self._on_stop_clicked()
    
    def update_value(self, remapped_value: float, remap_min: float, remap_max: float) -> None:
        """
        Update value display with remapped value.
        
        Args:
            remapped_value: The remapped value to display
            remap_min: Minimum remapping value
            remap_max: Maximum remapping value
        """
        # Calculate percentage for progress bar visual (0-100%)
        if remap_max == remap_min:
            percentage = 50.0  # Middle if range is zero
        else:
            # Normalize remapped value back to 0-1 range for display
            normalized = (remapped_value - remap_min) / (remap_max - remap_min)
            percentage = max(0.0, min(100.0, normalized * 100.0))
        
        # Update progress bar value (for visual bar)
        self.value_progress.setValue(int(percentage))
        
        # Update progress bar format to show actual remapped value
        self.value_progress.setFormat(f"{remapped_value:.3f}")
        
        # Update chunk color based on percentage (keep the same bar style)
        if percentage < 50:
            color = "green"
        elif percentage < 75:
            color = "orange"
        else:
            color = "red"
        
        # Only update the chunk color, keep the same bar style
        self.value_progress.setStyleSheet(f"""
            QProgressBar {{
                border: 1px solid grey;
                border-radius: 3px;
                text-align: center;
            }}
            QProgressBar::chunk {{
                background-color: {color};
            }}
        """)
    
    def get_name(self) -> str:
        """Get object name."""
        return self._name
    
    def get_config(self) -> dict:
        """
        Get current configuration.
        
        Returns:
            Dictionary with address, host, port, remap_min, remap_max, streaming_enabled
        """
        return {
            'name': self._name,
            'address': self.address_edit.text(),
            'host': self.host_edit.text(),
            'port': STREAMING_PORT,  # Use port from settings
            'remap_min': self.remap_min_spinbox.value(),
            'remap_max': self.remap_max_spinbox.value(),
            'streaming_enabled': self._streaming
        }
    
    def set_config(self, config: dict) -> None:
        """
        Set configuration from dictionary.
        
        Args:
            config: Configuration dictionary
        """
        if 'address' in config:
            self.address_edit.setText(config['address'])
        if 'host' in config:
            self.host_edit.setText(config['host'])
        # Port is always STREAMING_PORT from settings, no need to set it
        if 'remap_min' in config:
            self.remap_min_spinbox.setValue(config['remap_min'])
        elif 'scale' in config:
            # Backward compatibility: convert old scale to remap_max
            scale = config['scale']
            self.remap_max_spinbox.setValue(scale)
        if 'remap_max' in config:
            self.remap_max_spinbox.setValue(config['remap_max'])
        if 'streaming_enabled' in config:
            self.set_streaming_state(config['streaming_enabled'])
        elif 'enabled' in config:
            # Backward compatibility: convert old enabled to streaming_enabled
            self.set_streaming_state(config['enabled'])


class ObjectCardsContainer(QWidget):
    """Container widget for multiple object cards."""
    
    # Signals
    object_added = Signal(str)  # Emits object name
    object_removed = Signal(str)  # Emits object name
    object_config_changed = Signal(str)  # Emits object name
    
    def __init__(self, parent=None):
        """Initialize ObjectCardsContainer."""
        super().__init__(parent)
        self._cards = {}
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the UI components."""
        layout = QVBoxLayout()
        layout.setContentsMargins(5, 5, 5, 5)
        
        # Header
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("<b>Interactive Objects</b>"))
        header_layout.addStretch()
        
        add_button = QPushButton("Add Object")
        add_button.clicked.connect(lambda: self._add_object())  # Use lambda to ignore signal argument
        header_layout.addWidget(add_button)
        layout.addLayout(header_layout)
        
        # Scroll area for cards (horizontal scrolling)
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.cards_widget = QWidget()
        self.cards_layout = QHBoxLayout()  # Changed to horizontal layout
        self.cards_layout.setSpacing(10)
        self.cards_layout.setContentsMargins(5, 5, 5, 5)
        self.cards_layout.addStretch()
        self.cards_widget.setLayout(self.cards_layout)
        
        scroll_area.setWidget(self.cards_widget)
        layout.addWidget(scroll_area)
        
        # Set fixed height for the row (independent of window size)
        self.setFixedHeight(INTERACTIVE_OBJECTS_HEIGHT)
        
        self.setLayout(layout)
    
    def _add_object(self, name: str = None) -> ObjectCard:
        """
        Add a new object card.
        
        Args:
            name: Object name (auto-generated if None)
        
        Returns:
            ObjectCard instance
        """
        if name is None:
            # Generate unique name
            counter = 1
            while f"Object {counter}" in self._cards:
                counter += 1
            name = f"Object {counter}"
        
        card = ObjectCard(name, self)
        card.removed.connect(self._remove_object)
        card.config_changed.connect(self.object_config_changed.emit)
        card.streaming_started.connect(self._on_streaming_started)
        card.streaming_stopped.connect(self._on_streaming_stopped)
        
        # Insert before stretch
        self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)
        self._cards[name] = card
        
        self.object_added.emit(name)
        logger.info(f"Added object card: {name}")
        return card
    
    def _on_streaming_started(self, name: str) -> None:
        """Handle streaming started signal from card."""
        # Forward signal if needed, or handle here
        pass
    
    def _on_streaming_stopped(self, name: str) -> None:
        """Handle streaming stopped signal from card."""
        # Forward signal if needed, or handle here
        pass
    
    def _remove_object(self, name: str) -> None:
        """
        Remove an object card.
        
        Args:
            name: Object name
        """
        if name in self._cards:
            card = self._cards[name]
            self.cards_layout.removeWidget(card)
            card.deleteLater()
            del self._cards[name]
            self.object_removed.emit(name)
            logger.info(f"Removed object card: {name}")
    
    def get_card(self, name: str) -> ObjectCard:
        """
        Get object card by name.
        
        Args:
            name: Object name
        
        Returns:
            ObjectCard or None if not found
        """
        return self._cards.get(name)
    
    def get_all_configs(self) -> list[dict]:
        """
        Get configurations for all objects.
        
        Returns:
            List of configuration dictionaries
        """
        return [card.get_config() for card in self._cards.values()]

