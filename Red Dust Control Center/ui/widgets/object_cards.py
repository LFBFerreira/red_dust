"""
Object Cards widget for managing interactive objects (OSC and Serial).
"""
from PySide6.QtWidgets import (
    QWidget,
    QFrame,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QDoubleSpinBox,
    QPushButton,
    QProgressBar,
    QComboBox,
    QTabWidget,
    QGridLayout,
)
from PySide6.QtCore import Signal
import logging
from typing import Optional, Dict

from settings import STREAMING_PORT, SERIAL_BAUDRATE, INTERACTIVE_OBJECTS_HEIGHT

logger = logging.getLogger(__name__)


class ObjectCard(QWidget):
    """Tab page widget for an interactive object (OSC or Serial)."""

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
        self._refreshing_ports = False  # Guard flag to prevent recursive refresh
        self._setup_ui()

    def _setup_ui(self):
        """Set up the UI components."""
        layout = QVBoxLayout()
        layout.setSpacing(10)
        layout.setContentsMargins(12, 12, 12, 12)

        type_hint = QLabel(f"<i>{self._communication_type}</i>")
        layout.addWidget(type_hint)

        # Communication-specific fields
        if self._communication_type == "OSC":
            grid = QGridLayout()
            grid.setColumnStretch(1, 1)
            grid.setColumnStretch(3, 1)
            grid.addWidget(QLabel("OSC Address:"), 0, 0)
            self.address_edit = QLineEdit()
            self.address_edit.setText(f"/red_dust/{self._name.lower().replace(' ', '_')}")
            self.address_edit.textChanged.connect(lambda: self.config_changed.emit(self._name))
            grid.addWidget(self.address_edit, 0, 1)
            grid.addWidget(QLabel("IP Address:"), 0, 2)
            self.host_edit = QLineEdit()
            self.host_edit.setText("127.0.0.1")
            self.host_edit.textChanged.connect(lambda: self.config_changed.emit(self._name))
            grid.addWidget(self.host_edit, 0, 3)
            layout.addLayout(grid)
        else:  # Serial
            port_row = QHBoxLayout()
            port_row.addWidget(QLabel("Serial Port:"))
            self.port_combo = QComboBox()
            self.port_combo.setEditable(True)  # Allow typing custom port names
            self._populate_serial_ports()
            self.port_combo.currentTextChanged.connect(self._on_serial_port_changed)
            port_row.addWidget(self.port_combo, 1)
            self.retry_button = QPushButton("Retry")
            self.retry_button.setFixedWidth(72)
            self.retry_button.clicked.connect(self._on_retry_serial_connection)
            self.retry_button.setEnabled(False)  # Disabled by default, enabled when connection fails
            port_row.addWidget(self.retry_button)
            layout.addLayout(port_row)

        # Remap Min and Max side by side
        remap_layout = QHBoxLayout()
        remap_min_layout = QVBoxLayout()
        remap_min_layout.addWidget(QLabel("Min:"))
        self.remap_min_spinbox = QDoubleSpinBox()
        self.remap_min_spinbox.setRange(-1000000.0, 1000000.0)
        self.remap_min_spinbox.setValue(0.0)
        self.remap_min_spinbox.setDecimals(3)
        self.remap_min_spinbox.setSingleStep(0.05)
        self.remap_min_spinbox.editingFinished.connect(self._on_remap_min_finished)
        remap_min_layout.addWidget(self.remap_min_spinbox)
        remap_layout.addLayout(remap_min_layout, 1)

        remap_max_layout = QVBoxLayout()
        remap_max_layout.addWidget(QLabel("Max:"))
        self.remap_max_spinbox = QDoubleSpinBox()
        self.remap_max_spinbox.setRange(-1000000.0, 1000000.0)
        self.remap_max_spinbox.setValue(1.0)
        self.remap_max_spinbox.setDecimals(3)
        self.remap_max_spinbox.setSingleStep(0.05)
        self.remap_max_spinbox.editingFinished.connect(self._on_remap_max_finished)
        remap_max_layout.addWidget(self.remap_max_spinbox)
        remap_layout.addLayout(remap_max_layout, 1)

        self._last_valid_remap_min = 0.0
        self._last_valid_remap_max = 1.0

        layout.addLayout(remap_layout)

        streaming_outer = QHBoxLayout()
        streaming_outer.addStretch(1)
        streaming_inner = QHBoxLayout()
        self.start_button = QPushButton("Start")
        self.start_button.clicked.connect(self._on_start_clicked)
        if self._communication_type == "Serial":
            self.start_button.setEnabled(False)  # Will be enabled when connection is established
        streaming_inner.addWidget(self.start_button, 1)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self._on_stop_clicked)
        self.stop_button.setEnabled(False)  # Disabled when streaming is off
        streaming_inner.addWidget(self.stop_button, 1)
        streaming_outer.addLayout(streaming_inner, 1)
        streaming_outer.addStretch(1)
        layout.addLayout(streaming_outer)

        self.value_progress = QProgressBar()
        self.value_progress.setRange(0, 100)
        self.value_progress.setValue(0)
        self.value_progress.setFormat("0.000")
        self.value_progress.setTextVisible(True)
        self.value_progress.setMinimumHeight(24)
        layout.addWidget(self.value_progress)

        layout.addStretch()
        self.setLayout(layout)

    def _populate_serial_ports(self, excluded_ports: set = None) -> None:
        """
        Populate serial port dropdown with available ports.

        Args:
            excluded_ports: Set of port names to exclude from the dropdown
        """
        if self._refreshing_ports:
            return

        if excluded_ports is None:
            excluded_ports = set()

        self._refreshing_ports = True
        try:
            current_port = self.port_combo.currentText()
            is_current_port_valid = (
                current_port
                and current_port != "Select port..."
                and current_port.strip() != ""
            )

            try:
                import serial.tools.list_ports

                ports = serial.tools.list_ports.comports()
                available_ports = [port.device for port in ports]

                filtered_ports = [
                    port
                    for port in available_ports
                    if port not in excluded_ports or port == current_port
                ]

                self.port_combo.blockSignals(True)

                self.port_combo.clear()
                self.port_combo.addItems(filtered_ports)

                if not filtered_ports:
                    self.port_combo.addItem("Select port...")
                    if not is_current_port_valid:
                        self.port_combo.setCurrentText("Select port...")
                else:
                    self.port_combo.insertItem(0, "Select port...")
                    if is_current_port_valid and current_port in filtered_ports:
                        self.port_combo.setCurrentText(current_port)
                    else:
                        self.port_combo.setCurrentIndex(0)

                self.port_combo.blockSignals(False)
            except RecursionError:
                print(
                    "Warning: RecursionError while listing serial ports (problematic device detected)"
                )
                self.port_combo.blockSignals(True)
                self.port_combo.clear()
                self.port_combo.addItem("Select port...")
                if not is_current_port_valid:
                    self.port_combo.setCurrentText("Select port...")
                self.port_combo.blockSignals(False)
            except Exception as e:
                print(f"Error: Failed to list serial ports: {type(e).__name__}: {e}")
                self.port_combo.blockSignals(True)
                self.port_combo.clear()
                self.port_combo.addItem("Select port...")
                if not is_current_port_valid:
                    self.port_combo.setCurrentText("Select port...")
                self.port_combo.blockSignals(False)
        finally:
            self._refreshing_ports = False

    def _set_serial_port(self, port_name: str) -> None:
        """
        Set serial port, adding it to the list if it's not already there.
        This preserves saved port names even if they're not currently available.

        Args:
            port_name: Port name to set
        """
        current_items = [self.port_combo.itemText(i) for i in range(self.port_combo.count())]

        if port_name not in current_items:
            self.port_combo.addItem(port_name)

        if port_name and port_name != "Select port...":
            self.port_combo.setCurrentText(port_name)
        else:
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

        self.config_changed.emit(self._name)

        if not self._refreshing_ports:
            self._request_port_refresh()

    def _request_port_refresh(self) -> None:
        """Request refresh of all serial port dropdowns in the container."""
        parent = self.parent()
        while parent:
            if isinstance(parent, ObjectCardsContainer):
                parent._refresh_all_serial_ports()
                break
            parent = parent.parent()

    def _on_remap_min_finished(self) -> None:
        """Handle remap min field editing finished (Enter or focus loss)."""
        min_val = self.remap_min_spinbox.value()
        max_val = self.remap_max_spinbox.value()

        if min_val >= max_val:
            self.remap_min_spinbox.setValue(self._last_valid_remap_min)
        else:
            self._last_valid_remap_min = min_val
            self.config_changed.emit(self._name)

    def _on_remap_max_finished(self) -> None:
        """Handle remap max field editing finished (Enter or focus loss)."""
        min_val = self.remap_min_spinbox.value()
        max_val = self.remap_max_spinbox.value()

        if min_val >= max_val:
            self.remap_max_spinbox.setValue(self._last_valid_remap_max)
        else:
            self._last_valid_remap_max = max_val
            self.config_changed.emit(self._name)

    def _on_start_clicked(self) -> None:
        """Handle start button click."""
        self._streaming = True
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.streaming_started.emit(self._name)

    def _on_stop_clicked(self) -> None:
        """Handle stop button click."""
        self._streaming = False
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
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
            if not connected:
                self.start_button.setEnabled(False)
                port_name = self.port_combo.currentText()
                if port_name and port_name != "Select port...":
                    self.retry_button.setEnabled(True)
                else:
                    self.retry_button.setEnabled(False)
                if self._streaming:
                    self._on_stop_clicked()
            else:
                self.retry_button.setEnabled(False)
                if not self._streaming:
                    self.start_button.setEnabled(True)

    def _on_retry_serial_connection(self) -> None:
        """Handle retry button click for Serial connection."""
        if self._communication_type != "Serial":
            return

        port_name = self.port_combo.currentText()
        if port_name and port_name != "Select port...":
            self.config_changed.emit(self._name)

    def set_active_channel(self, channel: Optional[str]) -> None:
        """Reserved for API compatibility; value bar uses the default style."""

    def update_value(
        self, normalized_value: float, remap_min: float = None, remap_max: float = None
    ) -> None:
        """
        Update value display with remapped value.

        Args:
            normalized_value: The normalized value (0-1) from the waveform
            remap_min: Minimum remapping value (uses card's own if None)
            remap_max: Maximum remapping value (uses card's own if None)
        """
        if remap_min is None:
            remap_min = self.remap_min_spinbox.value()
        if remap_max is None:
            remap_max = self.remap_max_spinbox.value()

        normalized_value = max(0.0, min(1.0, normalized_value))

        if remap_max == remap_min:
            remapped_value = remap_min
            percentage = 50.0
        else:
            remapped_value = remap_min + (normalized_value * (remap_max - remap_min))
            percentage = max(0.0, min(100.0, normalized_value * 100.0))

        self.value_progress.setValue(int(percentage))
        self.value_progress.setFormat(f"{remapped_value:.3f}")

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
            "name": self._name,
            "type": self._communication_type,
            "remap_min": self.remap_min_spinbox.value(),
            "remap_max": self.remap_max_spinbox.value(),
            "streaming_enabled": self._streaming,
        }

        if self._communication_type == "OSC":
            config["address"] = self.address_edit.text()
            config["host"] = self.host_edit.text()
            config["port"] = STREAMING_PORT
        else:
            config["port"] = self.port_combo.currentText()
            config["baudrate"] = SERIAL_BAUDRATE

        return config

    def set_config(self, config: dict) -> None:
        """
        Set configuration from dictionary.

        Args:
            config: Configuration dictionary
        """
        if "type" in config and config["type"] != self._communication_type:
            logger.warning(
                "Cannot change communication type from %s to %s",
                self._communication_type,
                config["type"],
            )

        if self._communication_type == "OSC":
            if "address" in config:
                self.address_edit.setText(config["address"])
            if "host" in config:
                self.host_edit.setText(config["host"])
        else:
            if "port" in config:
                self._set_serial_port(config["port"])

        if "remap_min" in config:
            min_val = config["remap_min"]
            self.remap_min_spinbox.setValue(min_val)
            self._last_valid_remap_min = min_val
        elif "scale" in config:
            scale = config["scale"]
            self.remap_max_spinbox.setValue(scale)
            self._last_valid_remap_max = scale
        if "remap_max" in config:
            max_val = config["remap_max"]
            self.remap_max_spinbox.setValue(max_val)
            self._last_valid_remap_max = max_val
        if "streaming_enabled" in config:
            self.set_streaming_state(config["streaming_enabled"])
        elif "enabled" in config:
            self.set_streaming_state(config["enabled"])


class ObjectCardsContainer(QFrame):
    """Container widget for multiple interactive objects (tabbed)."""

    object_added = Signal(str)
    object_removed = Signal(str)
    object_config_changed = Signal(str)

    def __init__(self, parent=None):
        """Initialize ObjectCardsContainer."""
        super().__init__(parent)
        self._cards: Dict[str, ObjectCard] = {}
        self._refreshing_ports = False
        self._setup_ui()

    def _setup_ui(self):
        """Set up the UI components."""
        self.setFrameShape(QFrame.Shape.StyledPanel)
        self.setFrameShadow(QFrame.Shadow.Sunken)
        self.setLineWidth(1)

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)

        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("<b>Interactive Objects</b>"))
        header_layout.addStretch()

        add_osc_button = QPushButton("Add OSC")
        add_osc_button.clicked.connect(lambda: self._add_object("OSC"))
        header_layout.addWidget(add_osc_button)

        add_serial_button = QPushButton("Add Serial")
        add_serial_button.clicked.connect(lambda: self._add_object("Serial"))
        header_layout.addWidget(add_serial_button)
        layout.addLayout(header_layout)

        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self._on_tab_close_requested)
        # Font only — avoids breaking native tab borders (see prior full QTabBar styles).
        self.tab_widget.setStyleSheet(
            """
            QTabBar::tab:selected {
                font-weight: bold;
                font-size: 1.09em;
            }
        """
        )
        layout.addWidget(self.tab_widget)

        self.setFixedHeight(INTERACTIVE_OBJECTS_HEIGHT)
        self.setLayout(layout)

    def _on_tab_close_requested(self, index: int) -> None:
        card = self.tab_widget.widget(index)
        if not isinstance(card, ObjectCard):
            return
        self._remove_object(card.get_name())

    def _add_object(self, communication_type: str = "OSC", name: str = None) -> ObjectCard:
        """
        Add a new object tab.

        Args:
            communication_type: "OSC" or "Serial"
            name: Object name (auto-generated if None)

        Returns:
            ObjectCard instance
        """
        if name is None:
            counter = 1
            base_name = f"{communication_type} Object"
            while f"{base_name} {counter}" in self._cards:
                counter += 1
            name = f"{base_name} {counter}"

        card = ObjectCard(name, communication_type, self)
        card.config_changed.connect(self.object_config_changed.emit)
        card.streaming_started.connect(self._on_streaming_started)
        card.streaming_stopped.connect(self._on_streaming_stopped)

        self.tab_widget.addTab(card, name)
        self.tab_widget.setCurrentWidget(card)
        self._cards[name] = card

        if communication_type == "Serial":
            excluded_ports = self._get_used_serial_ports(exclude_card_name=name)
            card._populate_serial_ports(excluded_ports=excluded_ports)

        self.object_added.emit(name)
        logger.info("Added %s object tab: %s", communication_type, name)
        return card

    def _on_streaming_started(self, name: str) -> None:
        pass

    def _on_streaming_stopped(self, name: str) -> None:
        pass

    def _remove_object(self, name: str) -> None:
        """
        Remove an object tab.

        Args:
            name: Object name
        """
        if name not in self._cards:
            return

        card = self._cards[name]
        was_serial = card._communication_type == "Serial"

        idx = self.tab_widget.indexOf(card)
        if idx >= 0:
            self.tab_widget.removeTab(idx)

        card.deleteLater()
        del self._cards[name]

        if was_serial:
            self._refresh_all_serial_ports()
        self.object_removed.emit(name)
        logger.info("Removed object tab: %s", name)

    def get_card(self, name: str) -> Optional[ObjectCard]:
        """Get object card by name."""
        return self._cards.get(name)

    def get_all_configs(self) -> list[dict]:
        """Get configurations for all objects."""
        return [card.get_config() for card in self._cards.values()]

    def _get_used_serial_ports(self, exclude_card_name: str = None) -> set:
        """Get set of serial ports currently in use by other object cards."""
        used_ports = set()
        for name, card in self._cards.items():
            if name == exclude_card_name:
                continue
            if card._communication_type == "Serial":
                port = card.port_combo.currentText()
                if port and port != "Select port..." and port.strip() != "":
                    used_ports.add(port)
        return used_ports

    def _refresh_all_serial_ports(self) -> None:
        """Refresh serial port dropdowns for all Serial object cards."""
        if self._refreshing_ports:
            return

        self._refreshing_ports = True
        try:
            for name, card in self._cards.items():
                if card._communication_type == "Serial":
                    excluded_ports = self._get_used_serial_ports(exclude_card_name=name)
                    card._populate_serial_ports(excluded_ports=excluded_ports)
        finally:
            self._refreshing_ports = False
