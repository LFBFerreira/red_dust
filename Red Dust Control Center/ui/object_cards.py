"""
Object Cards widget for managing OSC output objects.
"""
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                               QLineEdit, QSpinBox, QSlider, QCheckBox, 
                               QPushButton, QScrollArea, QFrame)
from PySide6.QtCore import Signal, Qt
import logging

logger = logging.getLogger(__name__)


class ObjectCard(QFrame):
    """Individual card widget for an OSC object."""
    
    # Signals
    removed = Signal(str)  # Emits object name
    config_changed = Signal(str)  # Emits object name when config changes
    
    def __init__(self, name: str, parent=None):
        """
        Initialize ObjectCard.
        
        Args:
            name: Unique identifier for the object
            parent: Parent widget
        """
        super().__init__(parent)
        self._name = name
        self._setup_ui()
        self.setFrameStyle(QFrame.Shape.Box)
        self.setLineWidth(1)
    
    def _setup_ui(self):
        """Set up the UI components."""
        layout = QVBoxLayout()
        
        # Header with name and remove button
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel(f"<b>{self._name}</b>"))
        header_layout.addStretch()
        
        remove_button = QPushButton("✕")
        remove_button.setMaximumWidth(30)
        remove_button.clicked.connect(lambda: self.removed.emit(self._name))
        header_layout.addWidget(remove_button)
        layout.addLayout(header_layout)
        
        # OSC Address
        address_layout = QHBoxLayout()
        address_layout.addWidget(QLabel("OSC Address:"))
        self.address_edit = QLineEdit()
        self.address_edit.setText(f"/red_dust/{self._name.lower().replace(' ', '_')}")
        self.address_edit.textChanged.connect(lambda: self.config_changed.emit(self._name))
        address_layout.addWidget(self.address_edit)
        layout.addLayout(address_layout)
        
        # Host
        host_layout = QHBoxLayout()
        host_layout.addWidget(QLabel("Host:"))
        self.host_edit = QLineEdit()
        self.host_edit.setText("127.0.0.1")
        self.host_edit.textChanged.connect(lambda: self.config_changed.emit(self._name))
        host_layout.addWidget(self.host_edit)
        layout.addLayout(host_layout)
        
        # Port
        port_layout = QHBoxLayout()
        port_layout.addWidget(QLabel("Port:"))
        self.port_spinbox = QSpinBox()
        self.port_spinbox.setRange(1, 65535)
        self.port_spinbox.setValue(8000)
        self.port_spinbox.valueChanged.connect(lambda: self.config_changed.emit(self._name))
        port_layout.addWidget(self.port_spinbox)
        port_layout.addStretch()
        layout.addLayout(port_layout)
        
        # Scale
        scale_layout = QHBoxLayout()
        scale_layout.addWidget(QLabel("Scale:"))
        self.scale_slider = QSlider(Qt.Orientation.Horizontal)
        self.scale_slider.setRange(0, 100)
        self.scale_slider.setValue(100)
        self.scale_slider.valueChanged.connect(lambda: self.config_changed.emit(self._name))
        scale_layout.addWidget(self.scale_slider)
        
        self.scale_label = QLabel("1.00")
        self.scale_slider.valueChanged.connect(self._update_scale_label)
        scale_layout.addWidget(self.scale_label)
        layout.addLayout(scale_layout)
        
        # Enable checkbox
        self.enable_checkbox = QCheckBox("Enabled")
        self.enable_checkbox.setChecked(True)
        self.enable_checkbox.toggled.connect(lambda: self.config_changed.emit(self._name))
        layout.addWidget(self.enable_checkbox)
        
        self.setLayout(layout)
    
    def _update_scale_label(self, value: int) -> None:
        """Update scale label when slider changes."""
        scale = value / 100.0
        self.scale_label.setText(f"{scale:.2f}")
    
    def get_name(self) -> str:
        """Get object name."""
        return self._name
    
    def get_config(self) -> dict:
        """
        Get current configuration.
        
        Returns:
            Dictionary with address, host, port, scale, enabled
        """
        return {
            'name': self._name,
            'address': self.address_edit.text(),
            'host': self.host_edit.text(),
            'port': self.port_spinbox.value(),
            'scale': self.scale_slider.value() / 100.0,
            'enabled': self.enable_checkbox.isChecked()
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
        if 'port' in config:
            self.port_spinbox.setValue(config['port'])
        if 'scale' in config:
            self.scale_slider.setValue(int(config['scale'] * 100))
        if 'enabled' in config:
            self.enable_checkbox.setChecked(config['enabled'])


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
        
        # Header
        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("<b>Interactive Objects</b>"))
        header_layout.addStretch()
        
        add_button = QPushButton("Add Object")
        add_button.clicked.connect(self._add_object)
        header_layout.addWidget(add_button)
        layout.addLayout(header_layout)
        
        # Scroll area for cards
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.cards_widget = QWidget()
        self.cards_layout = QVBoxLayout()
        self.cards_layout.addStretch()
        self.cards_widget.setLayout(self.cards_layout)
        
        scroll_area.setWidget(self.cards_widget)
        layout.addWidget(scroll_area)
        
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
        
        # Insert before stretch
        self.cards_layout.insertWidget(self.cards_layout.count() - 1, card)
        self._cards[name] = card
        
        self.object_added.emit(name)
        logger.info(f"Added object card: {name}")
        return card
    
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

