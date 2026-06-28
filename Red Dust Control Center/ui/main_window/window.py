"""
Main Window for Red Dust Control Center.
"""

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QSizePolicy,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.data_manager import DataManager
from core.osc_manager import OSCManager
from core.playback_controller import PlaybackController
from core.session_manager import SessionManager
from core.waveform_model import WaveformModel
from settings import (
    INTERACTIVE_OBJECTS_HEIGHT,
    LEFT_PANEL_WIDTH,
    WAVEFORM_VIEWER_DEFAULT_WIDTH,
)
from ui.view_prefs import read_show_log
from ui.widget_debug import (
    apply_widget_debug_borders,
    iter_widget_debug_targets,
    read_show_widget_debug_borders,
)
from ui.widgets.data_picker import DataPicker
from ui.widgets.log_viewer import LogHandler, LogViewer
from ui.widgets.object_cards import ObjectCardsContainer
from ui.widgets.playback_controls import PlaybackControls
from ui.widgets.waveform_viewer import WaveformViewer

from .constants import DATASET_LABEL_TITLE_HTML, DATASET_METADATA_EMPTY_MESSAGE
from .data_mixin import MainWindowDataMixin
from .objects_mixin import MainWindowObjectsMixin
from .playback_mixin import MainWindowPlaybackMixin
from .session_mixin import MainWindowSessionMixin

logger = logging.getLogger(__name__)


class MainWindow(
    QMainWindow,
    # Mixin order matters: objects → playback → data → session so shared
    # helpers resolve before session (e.g. _update_object_card_channels).
    MainWindowObjectsMixin,
    MainWindowPlaybackMixin,
    MainWindowDataMixin,
    MainWindowSessionMixin,
):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Red Dust Control Center")
        min_width = LEFT_PANEL_WIDTH + WAVEFORM_VIEWER_DEFAULT_WIDTH
        self.setMinimumSize(min_width, 800)

        self.data_manager = DataManager()
        self.waveform_model = WaveformModel()
        self.playback_controller = PlaybackController(self.waveform_model)
        self.osc_manager = OSCManager(self.waveform_model, self.playback_controller)
        self.session_manager = SessionManager()

        self.current_session_path = None
        self.pending_session_state = None
        self.load_thread = None

        self._setup_menu_bar()
        self._setup_ui()
        self._setup_logging()
        self._connect_signals()
        self._apply_widget_debug_borders(read_show_widget_debug_borders())

        logger.info("Loading cached metadata...")
        self.data_picker._load_available_years()

        self._load_metadata_async()

        logger.info("Red Dust Control Center initialized")

    def closeEvent(self, event: QCloseEvent) -> None:
        """Ensure playback, OSC, and Serial are stopped before exit."""
        logger.info("Application close: cleaning up playback and I/O...")
        try:
            if getattr(self, "playback_controller", None):
                self.playback_controller.stop()
            if getattr(self, "osc_manager", None):
                self.osc_manager.shutdown()
        except Exception as e:
            logger.warning("Error during application cleanup: %s", e, exc_info=True)
        mt = getattr(self, "metadata_thread", None)
        if mt is not None and mt.isRunning():
            mt.wait(2000)
        if self.load_thread is not None and self.load_thread.isRunning():
            self.load_thread.wait(2000)
        event.accept()

    def _setup_ui(self):
        """Set up the user interface."""
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()
        main_layout.setSpacing(12)
        main_layout.setContentsMargins(6, 6, 6, 6)
        central_widget.setLayout(main_layout)

        row1_splitter = QSplitter(Qt.Orientation.Horizontal)

        metadata_widget = QWidget()
        self.metadata_widget = metadata_widget
        metadata_widget.setMinimumWidth(LEFT_PANEL_WIDTH)
        metadata_widget.setMaximumWidth(LEFT_PANEL_WIDTH)
        metadata_layout = QVBoxLayout()
        metadata_layout.setContentsMargins(0, 0, 0, 0)

        self.dataset_label = QLabel(DATASET_LABEL_TITLE_HTML)
        self.dataset_label.setAlignment(
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft
        )
        metadata_layout.addWidget(self.dataset_label)

        self.metadata_text = QTextEdit()
        self.metadata_text.setReadOnly(True)
        self.metadata_text.setPlainText(DATASET_METADATA_EMPTY_MESSAGE)
        metadata_layout.addWidget(self.metadata_text, 1)
        metadata_widget.setLayout(metadata_layout)
        row1_splitter.addWidget(metadata_widget)

        self.waveform_viewer = WaveformViewer()
        row1_splitter.addWidget(self.waveform_viewer)
        row1_splitter.setStretchFactor(0, 1)
        row1_splitter.setStretchFactor(1, 3)

        row1_splitter.setSizes([LEFT_PANEL_WIDTH, WAVEFORM_VIEWER_DEFAULT_WIDTH])

        main_layout.addWidget(row1_splitter)

        row2_splitter = QSplitter(Qt.Orientation.Horizontal)

        self.data_picker = DataPicker(data_manager=self.data_manager)
        self.data_picker.setMinimumWidth(LEFT_PANEL_WIDTH)
        self.data_picker.setMaximumWidth(LEFT_PANEL_WIDTH)
        row2_splitter.addWidget(self.data_picker)

        self.playback_controls = PlaybackControls()
        row2_splitter.addWidget(self.playback_controls)
        row2_splitter.setStretchFactor(0, 1)
        row2_splitter.setStretchFactor(1, 1)

        main_layout.addWidget(row2_splitter)

        self.object_cards = ObjectCardsContainer(
            selected_channels_provider=lambda: self._valid_selected_channels_for_io(),
            sorted_stream_channels_provider=lambda: sorted(
                self.waveform_model.get_all_channels()
            ),
        )
        main_layout.addWidget(self.object_cards, 1)

        self.log_section = QWidget()
        log_layout = QVBoxLayout()
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(4)
        log_title = QLabel("<b>Log</b>")
        log_title.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        log_layout.addWidget(log_title)
        self.log_viewer = LogViewer()
        self.log_viewer.setMaximumHeight(150)
        log_layout.addWidget(self.log_viewer, 1)
        self.log_section.setLayout(log_layout)
        main_layout.addWidget(self.log_section, 0)

        self._apply_log_visibility(read_show_log())

    def _apply_log_visibility(self, visible: bool) -> None:
        """Show or hide the log panel; ObjectCards expands when log is hidden."""
        self.log_section.setVisible(visible)
        if visible:
            sp = self.object_cards.sizePolicy()
            sp.setVerticalPolicy(QSizePolicy.Policy.Fixed)
            self.object_cards.setSizePolicy(sp)
            self.object_cards.setFixedHeight(INTERACTIVE_OBJECTS_HEIGHT)
        else:
            self.object_cards.setMinimumHeight(INTERACTIVE_OBJECTS_HEIGHT)
            self.object_cards.setMaximumHeight(16777215)
            sp = self.object_cards.sizePolicy()
            sp.setVerticalPolicy(QSizePolicy.Policy.Expanding)
            sp.setVerticalStretch(1)
            self.object_cards.setSizePolicy(sp)

    def _widget_debug_targets(self) -> dict[str, QWidget]:
        return dict(iter_widget_debug_targets(self))

    def _apply_widget_debug_borders(self, enabled: bool) -> None:
        apply_widget_debug_borders(self._widget_debug_targets(), enabled=enabled)
        self._show_widget_debug_borders = enabled

    def _setup_logging(self):
        """Set up logging to both console and UI."""
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)

        root_logger.handlers.clear()

        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        formatter = logging.Formatter("[%(levelname)s] %(message)s")
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

        ui_handler = LogHandler(self.log_viewer)
        ui_handler.setLevel(logging.INFO)
        ui_formatter = logging.Formatter("%(message)s")
        ui_handler.setFormatter(ui_formatter)
        root_logger.addHandler(ui_handler)

    def _connect_signals(self):
        """Connect signals and slots."""
        self.data_picker.load_requested.connect(self._on_load_requested)

        self.playback_controls.play_clicked.connect(self._on_play_requested)
        self.playback_controls.pause_clicked.connect(self.playback_controller.pause)
        self.playback_controls.stop_clicked.connect(self.playback_controller.stop)
        self.playback_controls.speed_changed.connect(self.playback_controller.set_speed)
        self.playback_controls.loop_toggled.connect(self._on_loop_toggled)
        self.playback_controls.loop_range_changed.connect(self._on_loop_range_changed)
        self.playback_controls.loop_markers_changed.connect(
            self._on_loop_markers_changed
        )
        self.playback_controls.capture_loop_start_clicked.connect(
            self._on_capture_loop_start
        )
        self.playback_controls.capture_loop_end_clicked.connect(
            self._on_capture_loop_end
        )
        self.playback_controls.channels_selection_changed.connect(
            self._on_channels_selection_changed
        )
        self.playback_controls.position_slider.valueChanged.connect(
            self._on_position_slider_changed
        )

        self.playback_controller.playhead_updated.connect(self._on_playhead_updated)
        self.playback_controller.state_changed.connect(self._on_playback_state_changed)

        self.waveform_viewer.loop_range_selected.connect(self._on_loop_range_selected)

        self.osc_manager.streaming_state_changed.connect(
            self._on_streaming_state_changed
        )
        self.osc_manager.object_streaming_state_changed.connect(
            self._on_object_streaming_state_changed
        )
        self.osc_manager.object_value_updated.connect(self._on_object_value_updated)
        self.osc_manager.object_connection_state_changed.connect(
            self._on_object_connection_state_changed
        )

        self.object_cards.object_added.connect(self._on_object_added)
        self.object_cards.object_removed.connect(self._on_object_removed)
        self.object_cards.object_config_changed.connect(self._on_object_config_changed)

        for card in self.object_cards._cards.values():
            card.streaming_started.connect(self._on_card_streaming_started)
            card.streaming_stopped.connect(self._on_card_streaming_stopped)

        self.playback_controller.state_changed.connect(self._on_playback_state_changed)
