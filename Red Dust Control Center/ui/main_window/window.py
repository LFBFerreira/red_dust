"""
Main Window for Red Dust Control Center.
"""

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QShowEvent
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
    DEFAULT_WINDOW_HEIGHT,
    LEFT_PANEL_WIDTH,
)
from ui.view_prefs import (
    default_window_size,
    read_show_log,
    read_window_geometry,
    write_window_geometry,
)
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
        self.setMinimumSize(LEFT_PANEL_WIDTH, DEFAULT_WINDOW_HEIGHT)

        self.data_manager = DataManager()
        self.waveform_model = WaveformModel()
        self.playback_controller = PlaybackController(self.waveform_model)
        self.osc_manager = OSCManager(self.waveform_model, self.playback_controller)
        self.session_manager = SessionManager()

        self.current_session_path = None
        self.pending_session_state = None
        self.load_thread = None
        self._splits_initialized = False

        self._setup_menu_bar()
        self._setup_ui()
        self._setup_logging()
        self._connect_signals()
        self._restore_window_geometry()
        self._apply_widget_debug_borders(read_show_widget_debug_borders())

        logger.info("Loading cached metadata...")
        self.data_picker._load_available_years()

        self._load_metadata_async()

        logger.info("Red Dust Control Center initialized")

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        if not self._splits_initialized:
            self._fix_top_row_compact_heights()
            self._sync_top_column_split()
            self._sync_main_row_split()
            self._splits_initialized = True

    def closeEvent(self, event: QCloseEvent) -> None:
        """Ensure playback, OSC, and Serial are stopped before exit."""
        write_window_geometry(self.saveGeometry())
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
        """Set up the user interface.

        Layout (vertical splitter between top / bottom, default 50/50):

            ┌─ top ───────────────────────────────────────────┐
            │  left column (LEFT_PANEL_WIDTH) │ right column │
            │  Dataset Information │ Waveform Viewer          │
            │  Data Picker         │ Playback Controls        │
            ╞══════════════════════╪══════════════════════════╡  ← drag handle
            │  Object Cards                                    │
            │  Log (optional)                                  │
            └──────────────────────────────────────────────────┘
        """
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(6, 6, 6, 6)
        central_widget.setLayout(main_layout)

        # --- Top half: left column at LEFT_PANEL_WIDTH, right column fills remainder ---
        self._top_column_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._top_column_splitter.setChildrenCollapsible(False)

        left_column = QWidget()
        left_column.setMinimumWidth(LEFT_PANEL_WIDTH)
        left_column_layout = QVBoxLayout(left_column)
        left_column_layout.setContentsMargins(0, 0, 0, 0)
        left_column_layout.setSpacing(6)

        self.metadata_widget = QWidget()
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
        self.metadata_widget.setLayout(metadata_layout)
        metadata_sp = self.metadata_widget.sizePolicy()
        metadata_sp.setVerticalPolicy(QSizePolicy.Policy.Expanding)
        self.metadata_widget.setSizePolicy(metadata_sp)
        left_column_layout.addWidget(self.metadata_widget, 1)

        self.data_picker = DataPicker(data_manager=self.data_manager)
        picker_sp = self.data_picker.sizePolicy()
        picker_sp.setVerticalPolicy(QSizePolicy.Policy.Fixed)
        self.data_picker.setSizePolicy(picker_sp)
        left_column_layout.addWidget(self.data_picker, 0)

        right_column = QWidget()
        right_column_layout = QVBoxLayout(right_column)
        right_column_layout.setContentsMargins(0, 0, 0, 0)
        right_column_layout.setSpacing(6)

        self.waveform_viewer = WaveformViewer()
        waveform_sp = self.waveform_viewer.sizePolicy()
        waveform_sp.setVerticalPolicy(QSizePolicy.Policy.Expanding)
        self.waveform_viewer.setSizePolicy(waveform_sp)
        right_column_layout.addWidget(self.waveform_viewer, 1)

        self.playback_controls = PlaybackControls()
        playback_sp = self.playback_controls.sizePolicy()
        playback_sp.setVerticalPolicy(QSizePolicy.Policy.Fixed)
        self.playback_controls.setSizePolicy(playback_sp)
        right_column_layout.addWidget(self.playback_controls, 0)

        self._top_column_splitter.addWidget(left_column)
        self._top_column_splitter.addWidget(right_column)
        self._top_column_splitter.setStretchFactor(0, 0)
        self._top_column_splitter.setStretchFactor(1, 1)

        # --- Bottom half ---
        bottom_panel = QWidget()
        bottom_layout = QVBoxLayout(bottom_panel)
        bottom_layout.setContentsMargins(0, 0, 0, 0)
        bottom_layout.setSpacing(0)

        self._bottom_splitter = QSplitter(Qt.Orientation.Vertical)
        self._bottom_splitter.setChildrenCollapsible(False)

        self.object_cards = ObjectCardsContainer(
            selected_channels_provider=lambda: self._valid_selected_channels_for_io(),
            sorted_stream_channels_provider=lambda: sorted(
                self.waveform_model.get_all_channels()
            ),
        )
        self._bottom_splitter.addWidget(self.object_cards)

        self.log_section = QWidget()
        log_layout = QVBoxLayout()
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(4)
        log_title = QLabel("<b>Log</b>")
        log_title.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        log_layout.addWidget(log_title)
        self.log_viewer = LogViewer()
        log_layout.addWidget(self.log_viewer, 1)
        self.log_section.setLayout(log_layout)
        self._bottom_splitter.addWidget(self.log_section)
        self._bottom_splitter.setStretchFactor(0, 3)
        self._bottom_splitter.setStretchFactor(1, 1)

        bottom_layout.addWidget(self._bottom_splitter)

        self._main_row_splitter = QSplitter(Qt.Orientation.Vertical)
        self._main_row_splitter.setChildrenCollapsible(False)
        self._main_row_splitter.addWidget(self._top_column_splitter)
        self._main_row_splitter.addWidget(bottom_panel)
        self._main_row_splitter.setStretchFactor(0, 1)
        self._main_row_splitter.setStretchFactor(1, 1)

        main_layout.addWidget(self._main_row_splitter, 1)

        self._apply_log_visibility(read_show_log())

    def _restore_window_geometry(self) -> None:
        geometry = read_window_geometry()
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            width, height = default_window_size()
            self.resize(width, height)

    def _fix_top_row_compact_heights(self) -> None:
        """Lock Data Picker and Playback Controls to their natural compact height."""
        for widget in (self.data_picker, self.playback_controls):
            widget.adjustSize()
            height = widget.sizeHint().height()
            if height > 0:
                widget.setFixedHeight(height)

    def _sync_top_column_split(self) -> None:
        """Keep the left column at LEFT_PANEL_WIDTH; right column uses the rest."""
        total = self._top_column_splitter.width()
        if total <= 0:
            return
        left = min(LEFT_PANEL_WIDTH, max(0, total - 1))
        self._top_column_splitter.setSizes([left, max(1, total - left)])

    def _sync_main_row_split(self) -> None:
        """Initial 50/50 split between top and bottom halves."""
        total = self._main_row_splitter.height()
        if total <= 0:
            return
        top = total // 2
        self._main_row_splitter.setSizes([top, total - top])

    def _apply_log_visibility(self, visible: bool) -> None:
        """Show or hide the log panel; ObjectCards fills the bottom half when hidden."""
        self.log_section.setVisible(visible)

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
