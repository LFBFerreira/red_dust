"""
Object Cards widget for managing interactive objects (OSC and Serial).
"""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                               QLineEdit, QDoubleSpinBox, QPushButton, 
                               QScrollArea, QFrame, QProgressBar, QSpinBox,
                               QComboBox)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QPalette
import logging
from settings import STREAMING_PORT, SERIAL_BAUDRATE, INTERACTIVE_OBJECTS_HEIGHT, OBJECT_CARD_WIDTH

logger = logging.getLogger(__name__)


class ObjectCard(QFrame):
    """Individual card widget for an interactive object (OSC or Serial)."""
    
    # Signals
    removed = Signal(str)  # Emits object name
    config_changed = Signal(str)  # Emits object name when config changes
    streaming_started = Signal(str)  # Emits object name when streaming starts
    streaming_stopped = Signal(str)  # Emits object name when streaming stops
    
    def __init__(self, name: str, communication_type: str = "OSC", parent=None):
        """
        Initialize ObjectCard.
        
        Args:
            name: Unique identifier for the object
            communication_type: "OSC" or "Serial"
            parent: Parent widget
        """
        super().__init__(parent)
        self._name = name
        self._communication_type = communication_type
        self._streaming = False
        self._active_channel = None
        self._channel_colors = {}  # Cache of channel to color mapping
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
        
        # Header with name, type, and remove button
        header_layout = QHBoxLayout()
        name_label = QLabel(f"<b>{self._name}</b>")
        name_label.setStyleSheet("font-size: 12pt;")
        header_layout.addWidget(name_label)
        
        type_label = QLabel(f"<i>({self._communication_type})</i>")
        type_label.setStyleSheet("font-size: 9pt; color: grey;")
        header_layout.addWidget(type_label)
        header_layout.addStretch()
        
        remove_button = QPushButton("✕")
        remove_button.setMaximumWidth(30)
        remove_button.setMaximumHeight(25)
        remove_button.clicked.connect(lambda: self.removed.emit(self._name))
        header_layout.addWidget(remove_button)
        layout.addLayout(header_layout)
        
        # Communication-specific fields
        if self._communication_type == "OSC":
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
        else:  # Serial
            # Serial Port (dropdown with available ports)
            port_layout = QVBoxLayout()
            port_layout.addWidget(QLabel("Serial Port:"))
            self.port_combo = QComboBox()
            self.port_combo.setEditable(True)  # Allow typing custom port names
            self._populate_serial_ports()
            self.port_combo.currentTextChanged.connect(self._on_serial_port_changed)
            port_layout.addWidget(self.port_combo)
            layout.addLayout(port_layout)
        
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
        # For Serial objects, Start button will be enabled/disabled based on connection state
        # For OSC objects, Start button is enabled by default
        if self._communication_type == "Serial":
            self.start_button.setEnabled(False)  # Will be enabled when connection is established
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
    
    def _populate_serial_ports(self) -> None:
        """Populate serial port dropdown with available ports."""
        try:
            import serial.tools.list_ports
            ports = serial.tools.list_ports.comports()
            available_ports = [port.device for port in ports]
            
            # Clear and add available ports
            self.port_combo.clear()
            self.port_combo.addItems(available_ports)
            
            # Add placeholder text - don't select any port by default
            if not available_ports:
                self.port_combo.addItem("Select port...")
                self.port_combo.setCurrentText("Select port...")
            else:
                # Add placeholder as first item
                self.port_combo.insertItem(0, "Select port...")
                self.port_combo.setCurrentIndex(0)  # Select placeholder
        except Exception as e:
            logger.error(f"Failed to list serial ports: {e}")
            # Fallback: just add placeholder
            self.port_combo.clear()
            self.port_combo.addItem("Select port...")
            self.port_combo.setCurrentText("Select port...")
    
    def _set_serial_port(self, port_name: str) -> None:
        """
        Set serial port, adding it to the list if it's not already there.
        This preserves saved port names even if they're not currently available.
        
        Args:
            port_name: Port name to set
        """
        # Check if port is already in the combo box
        current_items = [self.port_combo.itemText(i) for i in range(self.port_combo.count())]
        
        if port_name not in current_items:
            # Add the port to the list (preserves saved port names)
            self.port_combo.addItem(port_name)
        
        # Set the current text (but don't trigger port opening if it's a placeholder)
        if port_name and port_name != "Select port...":
            self.port_combo.setCurrentText(port_name)
        else:
            # If it's a placeholder or empty, just set it without triggering
            self.port_combo.blockSignals(True)
            self.port_combo.setCurrentText("Select port...")
            self.port_combo.blockSignals(False)
    
    def _on_serial_port_changed(self, port_name: str) -> None:
        """
        Handle serial port selection change.
        Attempts to open the port when user selects one.
        
        Args:
            port_name: Selected port name
        """
        if self._communication_type != "Serial":
            return
        
        # Ignore placeholder text
        if port_name == "Select port..." or not port_name or port_name.strip() == "":
            # Emit config changed but don't try to open port
            self.config_changed.emit(self._name)
            return
        
        # Emit config changed to update the SerialObject
        self.config_changed.emit(self._name)
    
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
    
    def set_connection_state(self, connected: bool) -> None:
        """
        Set connection state (for Serial objects).
        Updates button states based on connection availability.
        
        Args:
            connected: True if connected, False if disconnected
        """
        if self._communication_type == "Serial":
            # If not connected, disable Start button and enable Stop button only if streaming
            if not connected:
                self.start_button.setEnabled(False)
                # If streaming, stop it
                if self._streaming:
                    self._on_stop_clicked()
            else:
                # If connected, enable Start button if not streaming
                if not self._streaming:
                    self.start_button.setEnabled(True)
    
    def set_active_channel(self, channel: str) -> None:
        """
        Set the active channel for this object card.
        The progress bar color will be based on the channel.
        
        Args:
            channel: Active channel identifier (e.g., "03.BHU")
        """
        self._active_channel = channel
        # Update progress bar color immediately if we have a color for this channel
        if channel in self._channel_colors:
            self._update_progress_bar_color()
    
    def _get_channel_color(self, channel: str) -> str:
        """
        Get a consistent color for a channel.
        Uses the same color palette as the waveform viewer.
        
        Args:
            channel: Channel identifier
            
        Returns:
            Color hex code
        """
        # Use the same color palette as waveform viewer
        channel_colors = ['#00d4ff', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']
        
        # Create a hash-based index for consistent color assignment
        # This ensures the same channel always gets the same color
        if channel not in self._channel_colors:
            # Use hash of channel name to get consistent index
            channel_hash = hash(channel)
            color_idx = abs(channel_hash) % len(channel_colors)
            self._channel_colors[channel] = channel_colors[color_idx]
        
        return self._channel_colors[channel]
    
    def _update_progress_bar_color(self) -> None:
        """Update progress bar color based on active channel."""
        if self._active_channel:
            color = self._get_channel_color(self._active_channel)
            # Convert hex color to RGB for Qt
            # Remove # and convert to RGB
            hex_color = color.lstrip('#')
            r = int(hex_color[0:2], 16)
            g = int(hex_color[2:4], 16)
            b = int(hex_color[4:6], 16)
            
            # Use the channel color for the progress bar chunk
            self.value_progress.setStyleSheet(f"""
                QProgressBar {{
                    border: 1px solid grey;
                    border-radius: 3px;
                    text-align: center;
                }}
                QProgressBar::chunk {{
                    background-color: rgb({r}, {g}, {b});
                }}
            """)
        else:
            # Default grey if no channel
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
        
        # Update color based on active channel (not percentage)
        self._update_progress_bar_color()
    
    def get_name(self) -> str:
        """Get object name."""
        return self._name
    
    def get_config(self) -> dict:
        """
        Get current configuration.
        
        Returns:
            Dictionary with type-specific configuration, remap_min, remap_max, streaming_enabled
        """
        config = {
            'name': self._name,
            'type': self._communication_type,
            'remap_min': self.remap_min_spinbox.value(),
            'remap_max': self.remap_max_spinbox.value(),
            'streaming_enabled': self._streaming
        }
        
        if self._communication_type == "OSC":
            config['address'] = self.address_edit.text()
            config['host'] = self.host_edit.text()
            config['port'] = STREAMING_PORT  # Use default from settings
        else:  # Serial
            config['port'] = self.port_combo.currentText()
            config['baudrate'] = SERIAL_BAUDRATE  # Use default from settings
        
        return config
    
    def set_config(self, config: dict) -> None:
        """
        Set configuration from dictionary.
        
        Args:
            config: Configuration dictionary
        """
        # Update communication type if provided
        if 'type' in config and config['type'] != self._communication_type:
            logger.warning(f"Cannot change communication type from {self._communication_type} to {config['type']}")
        
        if self._communication_type == "OSC":
            if 'address' in config:
                self.address_edit.setText(config['address'])
            if 'host' in config:
                self.host_edit.setText(config['host'])
            # Port is always STREAMING_PORT from settings, no need to set it
        else:  # Serial
            if 'port' in config:
                self._set_serial_port(config['port'])
            # Baudrate is always SERIAL_BAUDRATE from settings, no need to set it
        
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
        
        add_osc_button = QPushButton("Add OSC Object")
        add_osc_button.clicked.connect(lambda: self._add_object("OSC"))  # Use lambda to ignore signal argument
        header_layout.addWidget(add_osc_button)
        
        add_serial_button = QPushButton("Add Serial Object")
        add_serial_button.clicked.connect(lambda: self._add_object("Serial"))  # Use lambda to ignore signal argument
        header_layout.addWidget(add_serial_button)
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
    
    def _add_object(self, communication_type: str = "OSC", name: str = None) -> ObjectCard:
        """
        Add a new object card.
        
        Args:
            communication_type: "OSC" or "Serial"
            name: Object name (auto-generated if None)
        
        Returns:
            ObjectCard instance
        """
        if name is None:
            # Generate unique name based on type
            counter = 1
            base_name = f"{communication_type} Object"
            while f"{base_name} {counter}" in self._cards:
                counter += 1
            name = f"{base_name} {counter}"
        
        card = ObjectCard(name, communication_type, self)
        card.removed.connect(self._remove_object)
        card.config_changed.connect(self.object_config_changed.emit)
        card.streaming_started.connect(self._on_streaming_started)
        card.streaming_stopped.connect(self._on_streaming_stopped)
        
        # Insert before stretch
        self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)
        self._cards[name] = card
        
        self.object_added.emit(name)
        logger.info(f"Added {communication_type} object card: {name}")
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

