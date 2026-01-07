"""
Main Window for Red Dust Control Center.
"""
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                               QLabel, QTextEdit, QComboBox, QPushButton, QSplitter)
from PySide6.QtCore import Qt, QThread, Signal
from pathlib import Path
import logging

from core.data_manager import DataManager
from core.waveform_model import WaveformModel
from core.playback_controller import PlaybackController
from core.osc_manager import OSCManager
from core.session_manager import SessionManager
from ui.data_picker import DataPicker
from ui.waveform_viewer import WaveformViewer
from ui.playback_controls import PlaybackControls
from ui.object_cards import ObjectCardsContainer
from ui.log_viewer import LogViewer, LogHandler

logger = logging.getLogger(__name__)


class DataLoadThread(QThread):
    """Thread for loading data in background."""
    data_loaded = Signal(object)  # Emits Stream
    error_occurred = Signal(str)  # Emits error message
    
    def __init__(self, data_manager, network, station, year, doy):
        super().__init__()
        self.data_manager = data_manager
        self.network = network
        self.station = station
        self.year = year
        self.doy = doy
    
    def run(self):
        try:
            cache_path = self.data_manager.fetch_and_cache(
                self.network, self.station, self.year, self.doy
            )
            stream = self.data_manager.load_from_cache(cache_path)
            self.data_loaded.emit(stream)
        except Exception as e:
            self.error_occurred.emit(str(e))


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        """Initialize MainWindow."""
        super().__init__()
        self.setWindowTitle("Red Dust Control Center")
        self.setMinimumSize(1200, 800)
        
        # Initialize core components
        self.data_manager = DataManager()
        self.waveform_model = WaveformModel()
        self.playback_controller = PlaybackController(self.waveform_model)
        self.osc_manager = OSCManager(self.waveform_model, self.playback_controller)
        self.session_manager = SessionManager()
        
        # Data loading thread
        self.load_thread = None
        
        # Setup UI
        self._setup_ui()
        self._setup_logging()
        self._connect_signals()
        
        logger.info("Red Dust Control Center initialized")
    
    def _setup_ui(self):
        """Set up the user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        
        # Row 1: Data Overview (Metadata + Waveform)
        row1_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Metadata viewer
        metadata_widget = QWidget()
        metadata_layout = QVBoxLayout()
        metadata_layout.addWidget(QLabel("<b>Dataset Information</b>"))
        
        # Active channel selection
        channel_layout = QHBoxLayout()
        channel_layout.addWidget(QLabel("Active Channel:"))
        self.channel_combo = QComboBox()
        self.channel_combo.currentTextChanged.connect(self._on_active_channel_changed)
        channel_layout.addWidget(self.channel_combo)
        metadata_layout.addLayout(channel_layout)
        
        self.metadata_text = QTextEdit()
        self.metadata_text.setReadOnly(True)
        self.metadata_text.setMaximumHeight(150)
        metadata_layout.addWidget(self.metadata_text)
        metadata_widget.setLayout(metadata_layout)
        row1_splitter.addWidget(metadata_widget)
        
        # Waveform viewer
        self.waveform_viewer = WaveformViewer()
        row1_splitter.addWidget(self.waveform_viewer)
        row1_splitter.setStretchFactor(0, 1)
        row1_splitter.setStretchFactor(1, 3)
        
        main_layout.addWidget(row1_splitter)
        
        # Row 2: Data Selection and Playback
        row2_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Data picker
        self.data_picker = DataPicker()
        row2_splitter.addWidget(self.data_picker)
        
        # Playback controls
        self.playback_controls = PlaybackControls()
        row2_splitter.addWidget(self.playback_controls)
        row2_splitter.setStretchFactor(0, 1)
        row2_splitter.setStretchFactor(1, 1)
        
        main_layout.addWidget(row2_splitter)
        
        # Row 3: Interactive Objects
        self.object_cards = ObjectCardsContainer()
        main_layout.addWidget(self.object_cards)
        
        # Row 4: System Log
        self.log_viewer = LogViewer()
        self.log_viewer.setMaximumHeight(150)
        main_layout.addWidget(self.log_viewer)
    
    def _setup_logging(self):
        """Set up logging to both console and UI."""
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('[%(levelname)s] %(message)s')
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        
        # UI handler
        ui_handler = LogHandler(self.log_viewer)
        ui_handler.setLevel(logging.INFO)
        ui_handler.setFormatter(formatter)
        root_logger.addHandler(ui_handler)
    
    def _connect_signals(self):
        """Connect signals and slots."""
        # Data picker
        self.data_picker.load_requested.connect(self._on_load_requested)
        
        # Playback controls
        self.playback_controls.play_clicked.connect(self.playback_controller.start)
        self.playback_controls.pause_clicked.connect(self.playback_controller.pause)
        self.playback_controls.stop_clicked.connect(self.playback_controller.stop)
        self.playback_controls.speed_changed.connect(self.playback_controller.set_speed)
        self.playback_controls.loop_toggled.connect(self.playback_controller.enable_loop)
        
        # Playback controller updates
        self.playback_controller.playhead_updated.connect(self._on_playhead_updated)
        self.playback_controller.state_changed.connect(self._on_playback_state_changed)
        
        # Waveform viewer
        self.waveform_viewer.loop_range_selected.connect(self._on_loop_range_selected)
        
        # OSC manager
        self.osc_manager.streaming_state_changed.connect(self._on_streaming_state_changed)
        
        # Object cards
        self.object_cards.object_added.connect(self._on_object_added)
        self.object_cards.object_removed.connect(self._on_object_removed)
        self.object_cards.object_config_changed.connect(self._on_object_config_changed)
        
        # Start OSC streaming when playback starts
        self.playback_controller.state_changed.connect(self._on_playback_state_changed)
    
    def _on_load_requested(self, selection: dict):
        """Handle data load request."""
        logger.info(f"Loading data: {selection}")
        self.data_picker.set_loading(True)
        
        # Start loading in background thread
        self.load_thread = DataLoadThread(
            self.data_manager,
            selection['network'],
            selection['station'],
            selection['year'],
            selection['doy']
        )
        self.load_thread.data_loaded.connect(self._on_data_loaded)
        self.load_thread.error_occurred.connect(self._on_load_error)
        self.load_thread.start()
    
    def _on_data_loaded(self, stream):
        """Handle successful data load."""
        logger.info(f"Data loaded: {len(stream)} traces")
        self.data_picker.set_loading(False)
        
        # Update waveform model
        self.waveform_model.set_stream(stream)
        
        # Update channel combo box
        self.channel_combo.clear()
        channels = self.waveform_model.get_all_channels()
        self.channel_combo.addItems(channels)
        
        # Set active channel
        active_channel = self.waveform_model.get_active_channel()
        if active_channel:
            index = self.channel_combo.findText(active_channel)
            if index >= 0:
                self.channel_combo.setCurrentIndex(index)
        
        # Update waveform viewer
        self.waveform_viewer.update_waveform(stream, active_channel)
        
        # Update metadata display
        self._update_metadata()
        
        # Reset playback
        self.playback_controller.stop()
        
        # Update playback controller
        self.playback_controller.set_waveform_model(self.waveform_model)
    
    def _on_load_error(self, error_message: str):
        """Handle data load error."""
        logger.error(f"Failed to load data: {error_message}")
        self.data_picker.set_loading(False)
    
    def _update_metadata(self):
        """Update metadata display."""
        if not self.waveform_model.get_stream():
            self.metadata_text.clear()
            return
        
        stream = self.waveform_model.get_stream()
        if len(stream) == 0:
            return
        
        trace = stream[0]
        active_channel = self.waveform_model.get_active_channel()
        channel_info = self.waveform_model.get_channel_info(active_channel)
        
        metadata = f"""Network: {trace.stats.network}
Station: {trace.stats.station}
Active Channel: {active_channel}
Sample Rate: {self.waveform_model.get_sample_rate():.2f} Hz"""
        
        if channel_info:
            time_range = self.waveform_model.get_time_range()
            if time_range:
                metadata += f"""
Time Range: {time_range[0]} to {time_range[1]}
Duration: {(time_range[1] - time_range[0]) / 3600:.2f} hours"""
        
        self.metadata_text.setText(metadata)
    
    def _on_playhead_updated(self, timestamp):
        """Handle playhead position update."""
        self.waveform_viewer.update_playhead(timestamp)
        
        # Update time display
        time_range = self.waveform_model.get_time_range()
        if time_range:
            self.playback_controls.update_time_display(timestamp, time_range[1])
    
    def _on_playback_state_changed(self, state: str):
        """Handle playback state change."""
        if state == "playing":
            self.osc_manager.start_streaming()
        elif state == "stopped":
            self.osc_manager.stop_streaming()
    
    def _on_loop_range_selected(self, start, end):
        """Handle loop range selection from waveform viewer."""
        try:
            self.playback_controller.set_loop_range(start, end)
            self.playback_controls.set_loop_enabled(True)
            self.playback_controls.update_loop_display(start, end)
            self.waveform_viewer.set_loop_range(start, end)
            logger.info(f"Loop range set: {start} to {end}")
        except ValueError as e:
            logger.warning(f"Invalid loop range: {e}")
    
    def _on_object_added(self, name: str):
        """Handle new object added."""
        config = self.object_cards.get_card(name).get_config()
        self.osc_manager.add_object(
            config['name'],
            config['address'],
            config['host'],
            config['port'],
            config['scale']
        )
        if not config['enabled']:
            self.osc_manager.set_object_enabled(name, False)
    
    def _on_object_removed(self, name: str):
        """Handle object removed."""
        self.osc_manager.remove_object(name)
    
    def _on_object_config_changed(self, name: str):
        """Handle object configuration change."""
        card = self.object_cards.get_card(name)
        if card:
            config = card.get_config()
            obj = self.osc_manager.get_object(name)
            if obj:
                # Update OSC object (recreate if host/port changed)
                if obj.host != config['host'] or obj.port != config['port']:
                    self.osc_manager.remove_object(name)
                    self.osc_manager.add_object(
                        config['name'],
                        config['address'],
                        config['host'],
                        config['port'],
                        config['scale']
                    )
                else:
                    self.osc_manager.update_object_scale(name, config['scale'])
                self.osc_manager.set_object_enabled(name, config['enabled'])
    
    def _on_streaming_state_changed(self, streaming: bool):
        """Handle OSC streaming state change."""
        logger.debug(f"OSC streaming: {'started' if streaming else 'stopped'}")
    
    def _on_active_channel_changed(self, channel: str):
        """Handle active channel selection change."""
        if channel:
            self.waveform_model.set_active_channel(channel)
            stream = self.waveform_model.get_stream()
            if stream:
                self.waveform_viewer.update_waveform(stream, channel)
            self._update_metadata()
            logger.info(f"Active channel changed to: {channel}")

