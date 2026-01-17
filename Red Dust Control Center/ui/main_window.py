"""
Main Window for Red Dust Control Center.
"""
from PySide6.QtWidgets import (QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                               QLabel, QTextEdit, QComboBox, QPushButton, QSplitter,
                               QMenuBar, QFileDialog, QMessageBox)
from PySide6.QtCore import Qt, QThread, Signal, QTimer
from pathlib import Path
from obspy import UTCDateTime
import logging

from core.data_manager import DataManager
from core.waveform_model import WaveformModel
from core.playback_controller import PlaybackController
from core.osc_manager import OSCManager
from core.session_manager import SessionManager
from core.serial_object import SerialObject
from ui.data_picker import DataPicker
from ui.waveform_viewer import WaveformViewer
from ui.playback_controls import PlaybackControls
from ui.object_cards import ObjectCardsContainer
from ui.log_viewer import LogViewer, LogHandler
from settings import LEFT_PANEL_WIDTH, WAVEFORM_VIEWER_DEFAULT_WIDTH, SERIAL_BAUDRATE

logger = logging.getLogger(__name__)


class DataLoadThread(QThread):
    """Thread for loading data in background."""
    data_loaded = Signal(object)  # Emits Stream
    error_occurred = Signal(str)  # Emits error message
    file_count_known = Signal(int)  # Emits total file count when known
    download_progress = Signal(int, int)  # Emits (downloaded, total) progress
    
    def __init__(self, data_manager, network, station, year, doy):
        super().__init__()
        self.data_manager = data_manager
        self.network = network
        self.station = station
        self.year = year
        self.doy = doy
    
    def run(self):
        import time
        thread_start = time.time()
        logger.info(f"DataLoadThread started for {self.network}/{self.station}/{self.year}/{self.doy:03d}")
        
        try:
            # Progress callback for downloads
            def progress_callback(downloaded: int, total: int):
                self.download_progress.emit(downloaded, total)
            
            # File count callback
            def file_count_callback(total: int):
                logger.info(f"Total files to download: {total}")
                self.file_count_known.emit(total)
            
            fetch_start = time.time()
            logger.info(f"Starting fetch_and_cache...")
            cache_path = self.data_manager.fetch_and_cache(
                self.network, self.station, self.year, self.doy,
                progress_callback=progress_callback,
                file_count_callback=file_count_callback
            )
            fetch_time = time.time() - fetch_start
            logger.info(f"fetch_and_cache completed in {fetch_time:.2f}s")
            
            load_start = time.time()
            logger.info(f"Starting load_from_cache...")
            stream = self.data_manager.load_from_cache(cache_path)
            load_time = time.time() - load_start
            logger.info(f"load_from_cache completed in {load_time:.2f}s")
            
            total_time = time.time() - thread_start
            logger.info(f"DataLoadThread complete in {total_time:.2f}s total")
            self.data_loaded.emit(stream)
        except Exception as e:
            logger.exception(f"Error in data load thread for {self.network}/{self.station}/{self.year}/{self.doy:03d}")
            self.error_occurred.emit(str(e))


class MainWindow(QMainWindow):
    """Main application window."""
    
    def __init__(self):
        """Initialize MainWindow."""
        super().__init__()
        self.setWindowTitle("Red Dust Control Center")
        # Calculate minimum window size based on component sizes
        min_width = LEFT_PANEL_WIDTH + WAVEFORM_VIEWER_DEFAULT_WIDTH
        self.setMinimumSize(min_width, 800)  # Allow window to be resized smaller
        
        # Initialize core components
        self.data_manager = DataManager()
        self.waveform_model = WaveformModel()
        self.playback_controller = PlaybackController(self.waveform_model)
        self.osc_manager = OSCManager(self.waveform_model, self.playback_controller)
        self.session_manager = SessionManager()
        
        # Current session file path (None if not saved yet)
        self.current_session_path = None
        
        # Pending session state to restore after data loads
        self.pending_session_state = None
        
        # Data loading thread
        self.load_thread = None
        
        # Setup UI
        self._setup_menu_bar()
        self._setup_ui()
        self._setup_logging()
        self._connect_signals()
        
        # Load cached metadata immediately (for fast UI response)
        logger.info("Loading cached metadata...")
        self.data_picker._load_available_years()
        
        # Refresh metadata in background
        self._load_metadata_async()
        
        logger.info("Red Dust Control Center initialized")
    
    def _setup_menu_bar(self):
        """Set up the menu bar with File and About menus."""
        menubar = self.menuBar()
        
        # File menu
        file_menu = menubar.addMenu("File")
        
        # Save action
        save_action = file_menu.addAction("Save")
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._on_save)
        
        # Save As action
        save_as_action = file_menu.addAction("Save As...")
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(self._on_save_as)
        
        # Load action
        load_action = file_menu.addAction("Load...")
        load_action.setShortcut("Ctrl+O")
        load_action.triggered.connect(self._on_load)
        
        # Load Recent action
        load_recent_action = file_menu.addAction("Load Recent")
        load_recent_action.triggered.connect(self._on_load_recent)
        
        # About menu
        about_menu = menubar.addMenu("About")
        
        # About action
        about_action = about_menu.addAction("About Red Dust Control Center")
        about_action.triggered.connect(self._on_about)
    
    def _get_recent_sessions(self, max_count: int = 10) -> list[Path]:
        """
        Get list of recent session files, sorted by modification time.
        
        Args:
            max_count: Maximum number of recent sessions to return
            
        Returns:
            List of Path objects to recent session files, most recent first
        """
        sessions_dir = self.session_manager.sessions_dir
        if not sessions_dir.exists():
            return []
        
        # Get all JSON files in sessions directory
        session_files = list(sessions_dir.glob("*.json"))
        
        # Sort by modification time (most recent first)
        session_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        
        # Return up to max_count most recent
        return session_files[:max_count]
    
    def _on_load_recent(self):
        """Handle Load Recent toolbar action - show menu with recent sessions."""
        recent_sessions = self._get_recent_sessions()
        
        if not recent_sessions:
            QMessageBox.information(
                self,
                "No Recent Sessions",
                "No recent session files found."
            )
            return
        
        # Create menu with recent sessions
        from PySide6.QtWidgets import QMenu
        from PySide6.QtGui import QCursor
        menu = QMenu(self)
        
        for session_path in recent_sessions:
            # Use filename as display name
            display_name = session_path.name
            action = menu.addAction(display_name)
            # Store full path as data
            action.setData(str(session_path))
            action.triggered.connect(lambda checked, path=session_path: self._load_session(path))
        
        # Show menu at cursor position
        menu.exec(QCursor.pos())
    
    def _setup_ui(self):
        """Set up the user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        main_layout = QVBoxLayout()
        main_layout.setSpacing(12)  # Increased spacing between main groups
        main_layout.setContentsMargins(6, 6, 6, 6)  # Add some margin around the entire layout
        central_widget.setLayout(main_layout)
        
        # Row 1: Data Overview (Metadata + Waveform)
        row1_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Metadata viewer
        metadata_widget = QWidget()
        metadata_widget.setMinimumWidth(LEFT_PANEL_WIDTH)
        metadata_widget.setMaximumWidth(LEFT_PANEL_WIDTH)
        metadata_layout = QVBoxLayout()
        metadata_layout.setContentsMargins(0, 0, 0, 0)
        
        # Dataset Information label at the top
        dataset_label = QLabel("<b>Dataset Information</b>")
        dataset_label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        metadata_layout.addWidget(dataset_label)
        
        # Metadata text box takes up the rest of the space
        self.metadata_text = QTextEdit()
        self.metadata_text.setReadOnly(True)
        metadata_layout.addWidget(self.metadata_text, 1)  # Stretch factor of 1 to fill remaining space
        metadata_widget.setLayout(metadata_layout)
        row1_splitter.addWidget(metadata_widget)
        
        # Waveform viewer
        self.waveform_viewer = WaveformViewer()
        row1_splitter.addWidget(self.waveform_viewer)
        row1_splitter.setStretchFactor(0, 1)
        row1_splitter.setStretchFactor(1, 3)
        
        # Set initial sizes: metadata panel (fixed) and waveform viewer (default width)
        row1_splitter.setSizes([LEFT_PANEL_WIDTH, WAVEFORM_VIEWER_DEFAULT_WIDTH])
        
        main_layout.addWidget(row1_splitter)
        
        # Row 2: Data Selection and Playback
        row2_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Data picker
        self.data_picker = DataPicker(data_manager=self.data_manager)
        self.data_picker.setMinimumWidth(LEFT_PANEL_WIDTH)
        self.data_picker.setMaximumWidth(LEFT_PANEL_WIDTH)
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
        
        # Clear any existing handlers to avoid duplicates
        # (e.g., from basicConfig or previous MainWindow instances)
        root_logger.handlers.clear()
        
        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('[%(levelname)s] %(message)s')
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
        
        # UI handler - use formatter without level prefix since LogViewer adds it
        ui_handler = LogHandler(self.log_viewer)
        ui_handler.setLevel(logging.INFO)
        ui_formatter = logging.Formatter('%(message)s')  # No level prefix, LogViewer adds it
        ui_handler.setFormatter(ui_formatter)
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
        self.playback_controls.channel_changed.connect(self._on_active_channel_changed)
        self.playback_controls.position_slider.valueChanged.connect(self._on_position_slider_changed)
        
        # Playback controller updates
        self.playback_controller.playhead_updated.connect(self._on_playhead_updated)
        self.playback_controller.state_changed.connect(self._on_playback_state_changed)
        
        # Waveform viewer
        self.waveform_viewer.loop_range_selected.connect(self._on_loop_range_selected)
        
        # OSC manager
        self.osc_manager.streaming_state_changed.connect(self._on_streaming_state_changed)
        self.osc_manager.object_streaming_state_changed.connect(self._on_object_streaming_state_changed)
        self.osc_manager.object_value_updated.connect(self._on_object_value_updated)
        self.osc_manager.object_connection_state_changed.connect(self._on_object_connection_state_changed)
        
        # Object cards
        self.object_cards.object_added.connect(self._on_object_added)
        self.object_cards.object_removed.connect(self._on_object_removed)
        self.object_cards.object_config_changed.connect(self._on_object_config_changed)
        
        # Connect card streaming signals
        for card in self.object_cards._cards.values():
            card.streaming_started.connect(self._on_card_streaming_started)
            card.streaming_stopped.connect(self._on_card_streaming_stopped)
        
        # Start OSC streaming when playback starts (global - kept for backward compatibility)
        self.playback_controller.state_changed.connect(self._on_playback_state_changed)
    
    def _reset_state_for_new_load(self):
        """Reset all state when loading new data (especially when station changes)."""
        logger.info(f"Resetting state for new data load...")
        
        # Stop any ongoing playback
        if self.playback_controller:
            logger.debug(f"Stopping playback controller...")
            self.playback_controller.stop()
        
        # Clear waveform viewer
        if self.waveform_viewer:
            logger.debug(f"Clearing waveform viewer...")
            self.waveform_viewer.plot_widget.clear()
        
        # Reset waveform model (clear old stream)
        if self.waveform_model:
            logger.debug(f"Resetting waveform model...")
            self.waveform_model.set_stream(None)
        
        # Stop any OSC streaming
        if self.osc_manager:
            logger.debug(f"Stopping OSC streaming...")
            # OSC manager will handle stopping when model is cleared
        
        # Clear any pending load thread
        if self.load_thread and self.load_thread.isRunning():
            logger.warning(f"Previous load thread still running, waiting for it...")
            self.load_thread.wait(1000)  # Wait up to 1 second
        
        logger.info(f"State reset complete")
    
    def _on_load_requested(self, selection: dict):
        """Handle data load request."""
        import time
        logger.info(f"===== Starting data load request =====")
        logger.info(f"Selection: {selection}")
        logger.info(f"Station: {selection.get('station', 'unknown')}")
        
        # Reset state when loading new data (especially when station changes)
        logger.info(f"Resetting state for new data load...")
        self._reset_state_for_new_load()
        
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
        self.load_thread.file_count_known.connect(self.data_picker.set_total_files)
        self.load_thread.download_progress.connect(self.data_picker.update_download_progress)
        self.load_thread.start()
        logger.info(f"Data load thread started")
    
    def _on_data_loaded(self, stream):
        """Handle successful data load."""
        import time
        process_start = time.time()
        
        logger.info(f"===== Data loaded callback started =====")
        logger.info(f"Stream contains {len(stream)} traces")
        
        # Log stream details for debugging
        if stream and len(stream) > 0:
            first_trace = stream[0]
            logger.info(f"First trace: {first_trace.id}, "
                       f"station: {first_trace.stats.station}, "
                       f"samples: {first_trace.stats.npts:,}, "
                       f"rate: {first_trace.stats.sampling_rate} Hz")
            total_samples = sum(t.stats.npts for t in stream)
            logger.info(f"Total samples across all traces: {total_samples:,}")
        
        self.data_picker.set_loading(False)
        
        # Update waveform model
        logger.info(f"Setting stream in waveform model...")
        model_start = time.time()
        self.waveform_model.set_stream(stream)
        model_time = time.time() - model_start
        logger.info(f"Waveform model updated in {model_time:.2f}s")
        
        # Update channel combo box in playback controls
        logger.info(f"Updating channel controls...")
        channels = self.waveform_model.get_all_channels()
        logger.info(f"Found {len(channels)} channels: {channels}")
        self.playback_controls.set_channels(channels)
        
        # Set active channel
        active_channel = self.waveform_model.get_active_channel()
        logger.info(f"Active channel: {active_channel}")
        if active_channel:
            self.playback_controls.set_active_channel(active_channel)
            # Update object cards with active channel
            self._update_object_card_channels()
        
        # Update waveform viewer
        logger.info(f"Updating waveform viewer...")
        viewer_start = time.time()
        self.waveform_viewer.update_waveform(stream, active_channel)
        viewer_time = time.time() - viewer_start
        logger.info(f"Waveform viewer updated in {viewer_time:.2f}s")
        
        # Update metadata display
        logger.info(f"Updating metadata display...")
        self._update_metadata()
        
        # Reset playback
        logger.info(f"Resetting playback controller...")
        self.playback_controller.stop()
        
        # Update playback controller
        self.playback_controller.set_waveform_model(self.waveform_model)
        
        # Update value display with initial values
        logger.info(f"Updating value display...")
        time_range = self.waveform_model.get_time_range()
        if time_range:
            initial_time = time_range[0]
            raw_value = self.waveform_model.get_raw_value(initial_time)
            normalized_value = self.waveform_model.get_normalized_value(initial_time)
            self.playback_controls.update_value_display(raw_value, normalized_value)
            # Initialize position slider
            self.playback_controls.update_position_slider(initial_time, time_range[0], time_range[1])
        
        # If we have pending session state, restore it now
        if self.pending_session_state:
            logger.info(f"Restoring pending session state...")
            self._restore_session_state_after_load(self.pending_session_state)
            self.pending_session_state = None
        
        process_time = time.time() - process_start
        logger.info(f"===== Data loaded callback complete in {process_time:.2f}s =====")
    
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
            # Update position slider
            self.playback_controls.update_position_slider(timestamp, time_range[0], time_range[1])
        
        # Update value display (raw and normalized)
        raw_value = self.waveform_model.get_raw_value(timestamp)
        normalized_value = self.waveform_model.get_normalized_value(timestamp)
        self.playback_controls.update_value_display(raw_value, normalized_value)
    
    def _on_position_slider_changed(self, value: int) -> None:
        """Handle position slider change."""
        # Ignore if slider is being updated programmatically
        if self.playback_controls._position_slider_updating:
            return
        
        # Get time range
        time_range = self.waveform_model.get_time_range()
        if not time_range:
            return
        
        start_time, end_time = time_range
        
        # Convert slider value to timestamp
        percentage = value / 1000.0  # 0.0 to 1.0
        total_duration = (end_time - start_time)  # This is already a float (seconds)
        if total_duration <= 0:
            return
        
        offset = total_duration * percentage
        target_timestamp = start_time + offset
        
        # Check if the target is significantly different from current position
        # This prevents oscillation from precision issues
        current_time = self.playback_controller.get_current_timestamp()
        if current_time is not None:
            # Subtracting two UTCDateTime objects returns a float (seconds)
            # If current_time is not a UTCDateTime, convert it first
            if not isinstance(current_time, UTCDateTime):
                current_time = UTCDateTime(current_time)
            # Calculate time difference in seconds (subtraction of UTCDateTime returns float)
            time_diff = abs((target_timestamp - current_time))
            # Only seek if the difference is more than 0.1% of the total duration
            # This prevents oscillation from rounding errors
            # total_duration is already in seconds (float), no need for .total_seconds()
            min_diff = total_duration * 0.001
            if time_diff < min_diff:
                return  # Too close, skip to avoid oscillation
        
        # Seek to the new position
        self.playback_controller.seek(target_timestamp)
    
    def _on_playback_state_changed(self, state: str):
        """Handle playback state change."""
        # Update button states in playback controls
        self.playback_controls.set_playback_state(state)
        
        # Handle OSC streaming
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
        card = self.object_cards.get_card(name)
        if not card:
            return
        
        # Connect streaming signals for new card
        card.streaming_started.connect(self._on_card_streaming_started)
        card.streaming_stopped.connect(self._on_card_streaming_stopped)
        
        config = card.get_config()
        comm_type = config.get('type', 'OSC')
        
        if comm_type == 'OSC':
            self.osc_manager.add_osc_object(
                config['name'],
                config['address'],
                config['host'],
                config['port'],
                config.get('remap_min', 0.0),
                config.get('remap_max', 1.0)
            )
        elif comm_type == 'Serial':
            port = config.get('port', '')
            # Only create Serial object if port is selected (not placeholder)
            if port and port != "Select port...":
                self.osc_manager.add_serial_object(
                    config['name'],
                    port,
                    config.get('baudrate', SERIAL_BAUDRATE),
                    config.get('remap_min', 0.0),
                    config.get('remap_max', 1.0)
                )
                # Try to open the port when user selects it
                obj = self.osc_manager.get_object(name)
                if obj and isinstance(obj, SerialObject):
                    if obj.open_port():
                        self.osc_manager.object_connection_state_changed.emit(name, True)
                        card.set_connection_state(True)
                    else:
                        self.osc_manager.object_connection_state_changed.emit(name, False)
                        card.set_connection_state(False)
            else:
                # Port not selected yet, create object but don't open port
                # Use a placeholder port name
                self.osc_manager.add_serial_object(
                    config['name'],
                    "Select port...",
                    config.get('baudrate', SERIAL_BAUDRATE),
                    config.get('remap_min', 0.0),
                    config.get('remap_max', 1.0)
                )
                # Connection state is False (no port selected)
                card.set_connection_state(False)
        else:
            logger.error(f"Unknown communication type: {comm_type}")
            return
        
        # Set streaming state if enabled
        if config.get('streaming_enabled', False):
            self.osc_manager.start_object_streaming(name)
        else:
            self.osc_manager.stop_object_streaming(name)
    
    def _on_object_removed(self, name: str):
        """Handle object removed."""
        self.osc_manager.remove_object(name)
    
    def _on_object_config_changed(self, name: str):
        """Handle object configuration change."""
        card = self.object_cards.get_card(name)
        if not card:
            return
        
        config = card.get_config()
        obj = self.osc_manager.get_object(name)
        if not obj:
            return
        
        comm_type = config.get('type', 'OSC')
        needs_recreate = False
        
        if comm_type == 'OSC':
            # Check if OSC-specific parameters changed
            if hasattr(obj, 'host') and hasattr(obj, 'port'):
                if obj.host != config.get('host') or obj.port != config.get('port'):
                    needs_recreate = True
        elif comm_type == 'Serial':
            # For Serial objects, check if port changed
            if hasattr(obj, 'port') and hasattr(obj, 'baudrate'):
                new_port = config.get('port', '')
                # Only recreate if port actually changed and is not placeholder
                if new_port and new_port != "Select port..." and obj.port != new_port:
                    needs_recreate = True
                elif new_port and new_port != "Select port..." and obj.port == new_port:
                    # Port is the same, but try to open it if not already open (retry scenario)
                    if isinstance(obj, SerialObject) and not obj.is_connected():
                        if obj.open_port():
                            # Port opened successfully
                            self.osc_manager.object_connection_state_changed.emit(name, True)
                            card.set_connection_state(True)
                        else:
                            # Port failed to open
                            self.osc_manager.object_connection_state_changed.emit(name, False)
                            card.set_connection_state(False)
                elif new_port and new_port == "Select port...":
                    # Placeholder selected, close port if open
                    if isinstance(obj, SerialObject) and obj.is_connected():
                        obj.close()
                        self.osc_manager.object_connection_state_changed.emit(name, False)
                        card.set_connection_state(False)
        
        if needs_recreate:
            # Store current streaming state
            was_streaming = obj.streaming_enabled
            
            self.osc_manager.remove_object(name)
            
            if comm_type == 'OSC':
                self.osc_manager.add_osc_object(
                    config['name'],
                    config['address'],
                    config['host'],
                    config['port'],
                    config.get('remap_min', 0.0),
                    config.get('remap_max', 1.0)
                )
            elif comm_type == 'Serial':
                new_port = config.get('port', '')
                # Only create if port is selected (not placeholder)
                if new_port and new_port != "Select port...":
                    self.osc_manager.add_serial_object(
                        config['name'],
                        new_port,
                        config.get('baudrate', SERIAL_BAUDRATE),
                        config.get('remap_min', 0.0),
                        config.get('remap_max', 1.0)
                    )
                    # Try to open the port
                    new_obj = self.osc_manager.get_object(name)
                    if new_obj and isinstance(new_obj, SerialObject):
                        if new_obj.open_port():
                            self.osc_manager.object_connection_state_changed.emit(name, True)
                            card.set_connection_state(True)
                        else:
                            self.osc_manager.object_connection_state_changed.emit(name, False)
                            card.set_connection_state(False)
            
            # Restore streaming state
            if was_streaming:
                self.osc_manager.start_object_streaming(name)
        else:
            # Update remapping parameters
            self.osc_manager.update_object_remapping(
                name,
                config.get('remap_min', 0.0),
                config.get('remap_max', 1.0)
            )
        
        # Update streaming state (handled by card buttons, but sync here for consistency)
        if config.get('streaming_enabled', False):
            if not self.osc_manager.is_object_streaming(name):
                self.osc_manager.start_object_streaming(name)
        else:
            if self.osc_manager.is_object_streaming(name):
                self.osc_manager.stop_object_streaming(name)
    
    def _on_streaming_state_changed(self, streaming: bool):
        """Handle OSC streaming state change (global)."""
        logger.debug(f"OSC streaming (global): {'started' if streaming else 'stopped'}")
    
    def _on_object_streaming_state_changed(self, name: str, streaming: bool):
        """Handle per-object streaming state change."""
        card = self.object_cards.get_card(name)
        if card:
            card.set_streaming_state(streaming)
        logger.debug(f"Object {name} streaming: {'started' if streaming else 'stopped'}")
    
    def _on_object_value_updated(self, name: str, normalized_value: float):
        """Handle object value update for UI display."""
        card = self.object_cards.get_card(name)
        if card:
            # Pass normalized value - card will remap it using its own min/max settings
            card.update_value(normalized_value)
    
    def _on_object_connection_state_changed(self, name: str, connected: bool):
        """Handle object connection state change (for Serial objects)."""
        card = self.object_cards.get_card(name)
        if card:
            card.set_connection_state(connected)
        logger.debug(f"Object {name} connection: {'connected' if connected else 'disconnected'}")
    
    def _update_object_card_channels(self):
        """Update active channel for all object cards."""
        active_channel = self.waveform_model.get_active_channel()
        if active_channel:
            for card in self.object_cards._cards.values():
                card.set_active_channel(active_channel)
    
    def _on_card_streaming_started(self, name: str):
        """Handle card start button clicked."""
        self.osc_manager.start_object_streaming(name)
    
    def _on_card_streaming_stopped(self, name: str):
        """Handle card stop button clicked."""
        self.osc_manager.stop_object_streaming(name)
    
    def _on_active_channel_changed(self, channel: str):
        """Handle active channel selection change."""
        if channel:
            self.waveform_model.set_active_channel(channel)
            stream = self.waveform_model.get_stream()
            if stream:
                self.waveform_viewer.update_waveform(stream, channel)
            self._update_metadata()
            logger.info(f"Active channel changed to: {channel}")
            
            # Update object cards with new active channel
            self._update_object_card_channels()
            
            # Update value display for new channel
            current_time = self.playback_controller.get_current_timestamp()
            if current_time:
                raw_value = self.waveform_model.get_raw_value(current_time)
                normalized_value = self.waveform_model.get_normalized_value(current_time)
                self.playback_controls.update_value_display(raw_value, normalized_value)
    
    def _load_metadata_async(self):
        """Load metadata (available years/days) in background."""
        from settings import DEFAULT_NETWORK, DEFAULT_STATION
        
        class MetadataLoadThread(QThread):
            metadata_loaded = Signal()
            
            def __init__(self, data_manager, network, station):
                super().__init__()
                self.data_manager = data_manager
                self.network = network
                self.station = station
            
            def run(self):
                try:
                    logger.info(f"Starting background metadata refresh for {self.network}/{self.station}...")
                    self.data_manager.refresh_metadata_cache(
                        self.network, 
                        self.station
                    )
                    logger.info("Background metadata refresh completed successfully")
                    self.metadata_loaded.emit()
                except Exception as e:
                    logger.error(f"Failed to refresh metadata in background: {e}", exc_info=True)
                    self.metadata_loaded.emit()  # Still emit to update UI with cached data
        
        # Start metadata loading thread
        logger.info("Starting background thread to refresh metadata from PDS...")
        self.metadata_thread = MetadataLoadThread(
            self.data_manager,
            DEFAULT_NETWORK,
            DEFAULT_STATION
        )
        def on_metadata_loaded():
            logger.info("Metadata refresh complete, updating UI...")
            if self.data_picker and self.data_picker.data_manager:
                self.data_picker._load_available_years()
            else:
                logger.warning("Cannot update UI: DataPicker or DataManager not available")
        
        self.metadata_thread.metadata_loaded.connect(on_metadata_loaded)
        self.metadata_thread.start()
        logger.info("Background metadata refresh thread started")
    
    def _restore_data_selection(self, selection: dict):
        """Restore data selection and trigger data load."""
        network = selection['network']
        station = selection['station']
        year = selection['year']
        doy = selection['doy']
        
        logger.info(f"Restoring data selection: {network}/{station}/{year}/{doy}")
        
        # Block signals to prevent automatic loading when we change combo boxes
        self.data_picker.station_combo.blockSignals(True)
        self.data_picker.year_combo.blockSignals(True)
        self.data_picker.day_combo.blockSignals(True)
        
        try:
            # Set network
            network_index = self.data_picker.network_combo.findText(network)
            if network_index >= 0:
                self.data_picker.network_combo.setCurrentIndex(network_index)
            
            # Set station (without triggering signal)
            station_index = self.data_picker.station_combo.findText(station)
            if station_index >= 0:
                self.data_picker.station_combo.setCurrentIndex(station_index)
            
            # Manually load years for the selected station (without triggering default selection)
            if self.data_picker.data_manager:
                try:
                    years = self.data_picker.data_manager.get_available_years(network, station)
                    self.data_picker._available_years = years
                    
                    # Update year combo box
                    self.data_picker.year_combo.clear()
                    if years:
                        self.data_picker.year_combo.addItems([str(y) for y in years])
                        # Set the year we want (not the default)
                        year_index = self.data_picker.year_combo.findText(str(year))
                        if year_index >= 0:
                            self.data_picker.year_combo.setCurrentIndex(year_index)
                        else:
                            logger.warning(f"Year {year} not found in available years")
                            self.data_picker.year_combo.setCurrentIndex(0)
                    else:
                        logger.warning(f"No years found for {network}/{station}")
                except Exception as e:
                    logger.error(f"Failed to load available years: {e}", exc_info=True)
            
            # Manually load days for the selected year (without triggering default selection)
            if self.data_picker.data_manager and self.data_picker.year_combo.count() > 0:
                try:
                    days = self.data_picker.data_manager.get_available_days(network, station, year)
                    self.data_picker._available_days = days
                    
                    # Update day combo box
                    self.data_picker.day_combo.clear()
                    if days:
                        self.data_picker.day_combo.addItems([str(d) for d in days])
                        # Set the day we want (not the default)
                        day_index = self.data_picker.day_combo.findText(str(doy))
                        if day_index >= 0:
                            self.data_picker.day_combo.setCurrentIndex(day_index)
                        else:
                            logger.warning(f"Day {doy} not found in available days")
                            self.data_picker.day_combo.setCurrentIndex(0)
                    else:
                        logger.warning(f"No days found for {network}/{station}/{year}")
                except Exception as e:
                    logger.error(f"Failed to load available days: {e}", exc_info=True)
            
            # Now trigger the load with the restored selection
            self.data_picker.load_requested.emit({
                'network': network,
                'station': station,
                'year': year,
                'doy': doy
            })
        finally:
            # Unblock signals
            self.data_picker.station_combo.blockSignals(False)
            self.data_picker.year_combo.blockSignals(False)
            self.data_picker.day_combo.blockSignals(False)
    
    def _on_save(self):
        """Handle Save menu action."""
        if self.current_session_path:
            self._save_session(self.current_session_path)
        else:
            self._on_save_as()
    
    def _on_save_as(self):
        """Handle Save As menu action."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Session",
            str(self.session_manager.sessions_dir / "session.json"),
            "JSON Files (*.json);;All Files (*)"
        )
        
        if file_path:
            self.current_session_path = Path(file_path)
            self._save_session(self.current_session_path)
    
    def _save_session(self, file_path: Path):
        """Save current application state to file."""
        try:
            # Get current state from all components
            state = self.session_manager.create_state_dict(
                self.data_manager,
                self.waveform_model,
                self.playback_controller,
                self.osc_manager,
                self.data_picker
            )
            
            # Save to file
            self.session_manager.save_session(file_path, state)
            
            QMessageBox.information(
                self,
                "Session Saved",
                f"Session saved successfully to:\n{file_path}"
            )
            logger.info(f"Session saved to {file_path}")
        except Exception as e:
            logger.error(f"Failed to save session: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Save Error",
                f"Failed to save session:\n{str(e)}"
            )
    
    def _on_load(self):
        """Handle Load menu action."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Session",
            str(self.session_manager.sessions_dir),
            "JSON Files (*.json);;All Files (*)"
        )
        
        if file_path:
            self._load_session(Path(file_path))
    
    def _load_session(self, file_path: Path):
        """Load application state from file."""
        try:
            # Load state from file
            state = self.session_manager.load_session(file_path)
            
            # Store state for restoration after data loads
            self.pending_session_state = state
            
            # Restore data selection first (this will trigger data load)
            selection = self.session_manager.get_data_selection(state)
            if selection:
                self._restore_data_selection(selection)
            
            # Restore OSC objects (doesn't depend on data)
            if 'objects' in state:
                self.session_manager.restore_objects(
                    state['objects'],
                    self.osc_manager,
                    self.object_cards
                )
            
            # If data is already loaded, restore the rest immediately
            if self.waveform_model.get_stream():
                self._restore_session_state_after_load(state)
                self.pending_session_state = None
            
            self.current_session_path = file_path
            
            QMessageBox.information(
                self,
                "Session Loaded",
                f"Session loaded successfully from:\n{file_path}"
            )
            logger.info(f"Session loaded from {file_path}")
        except FileNotFoundError:
            QMessageBox.warning(
                self,
                "Load Error",
                f"File not found:\n{file_path}"
            )
        except ValueError as e:
            QMessageBox.critical(
                self,
                "Load Error",
                f"Invalid session file:\n{str(e)}"
            )
        except Exception as e:
            logger.error(f"Failed to load session: {e}", exc_info=True)
            QMessageBox.critical(
                self,
                "Load Error",
                f"Failed to load session:\n{str(e)}"
            )
    
    def _restore_session_state_after_load(self, state: dict):
        """Restore session state that depends on data being loaded."""
        # Restore active channel
        if 'active_channel' in state and state['active_channel']:
            active_channel = state['active_channel']
            logger.info(f"Restoring active channel: {active_channel}")
            if self.waveform_model:
                self.waveform_model.set_active_channel(active_channel)
            if self.playback_controls:
                self.playback_controls.set_active_channel(active_channel)
            if self.waveform_viewer:
                stream = self.waveform_model.get_stream()
                if stream:
                    self.waveform_viewer.update_waveform(stream, active_channel)
            self._update_metadata()
        
        # Restore playback settings
        if 'playback' in state:
            playback_state = state['playback']
            
            # Restore speed
            if 'speed' in playback_state:
                speed = playback_state['speed']
                if self.playback_controls:
                    self.playback_controls.set_speed(speed)
                self.playback_controller.set_speed(speed)
            
            # Restore loop range
            if 'loop_start' in playback_state and 'loop_end' in playback_state:
                loop_start = playback_state['loop_start']
                loop_end = playback_state['loop_end']
                if loop_start and loop_end:
                    try:
                        self.playback_controller.set_loop_range(loop_start, loop_end)
                        loop_enabled = playback_state.get('loop_enabled', False)
                        self.playback_controller.enable_loop(loop_enabled)
                        if self.playback_controls:
                            self.playback_controls.set_loop_enabled(loop_enabled)
                            self.playback_controls.update_loop_display(loop_start, loop_end)
                        if self.waveform_viewer:
                            self.waveform_viewer.set_loop_range(loop_start, loop_end)
                    except Exception as e:
                        logger.warning(f"Failed to restore loop range: {e}")
            elif self.playback_controls:
                self.playback_controls.set_loop_enabled(False)
    
    def _on_about(self):
        """Handle About menu action."""
        QMessageBox.about(
            self,
            "About Red Dust Control Center",
            "Red Dust Control Center\n\n"
            "A tool for visualizing and controlling seismic waveform data.\n\n"
            "Features:\n"
            "- Load and visualize seismic data from PDS archive\n"
            "- Playback control with variable speed\n"
            "- Loop range selection\n"
            "- OSC output to interactive objects\n"
            "- Save and load session configurations"
        )

