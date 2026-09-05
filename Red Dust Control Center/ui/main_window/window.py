"""
Main Window for Red Dust Control Center.
"""

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QCloseEvent, QResizeEvent, QShowEvent
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
from core.pin_cues import PinCueList
from core.playback_controller import PlaybackController
from core.session_manager import SessionManager
from core.speed_envelope import SpeedEnvelope
from core.story_clock import StoryClock
from core.waveform_model import WaveformModel
from settings import (
    DEFAULT_WINDOW_HEIGHT,
    LEFT_PANEL_WIDTH,
    STATIONS_PANEL_WIDTH,
    WIDGET_PANEL_MARGIN,
)
from ui.layout_helpers import wrap_panel
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
from ui.widgets.fullscreen_preview import FullscreenPreviewWindow
from ui.widgets.log_viewer import LogHandler, LogViewer
from ui.widgets.object_cards import ObjectCardsContainer
from ui.widgets.playback_controls import PlaybackControls
from ui.widgets.story_timeline import StoryTimelinePanel
from ui.widgets.waveform_viewer import WaveformViewer

from .constants import DATASET_LABEL_TITLE_HTML, DATASET_METADATA_EMPTY_MESSAGE
from .data_mixin import MainWindowDataMixin
from .objects_mixin import MainWindowObjectsMixin
from .playback_mixin import MainWindowPlaybackMixin
from .session_mixin import MainWindowSessionMixin
from .story_mixin import MainWindowStoryMixin

logger = logging.getLogger(__name__)


class MainWindow(
    QMainWindow,
    # Mixin order matters: objects → playback → story → data → session so shared
    # helpers resolve before session (e.g. _update_object_card_channels).
    MainWindowObjectsMixin,
    MainWindowPlaybackMixin,
    MainWindowStoryMixin,
    MainWindowDataMixin,
    MainWindowSessionMixin,
):
    """Main application window."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Red Dust Control Center")
        self.setMinimumSize(1100, DEFAULT_WINDOW_HEIGHT)

        self.data_manager = DataManager()
        self.waveform_model = WaveformModel()
        self.playback_controller = PlaybackController(self.waveform_model)
        self.osc_manager = OSCManager(self.waveform_model, self.playback_controller)
        self.story_clock = StoryClock()
        self.pin_cues = PinCueList()
        self.speed_envelope = SpeedEnvelope()
        self.osc_manager.set_story_sources(self.story_clock, self.pin_cues)
        self.session_manager = SessionManager()

        self.current_session_path = None
        self.pending_session_state = None
        self.load_thread = None
        self._splits_initialized = False
        self._main_right_width: int | None = None
        self._fullscreen_window = None

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
            self._sync_left_row_split()
            self._sync_main_column_split()
            self._remember_main_right_width()
            self._splits_initialized = True

    def closeEvent(self, event: QCloseEvent) -> None:
        """Ensure playback, OSC, and Serial are stopped before exit."""
        write_window_geometry(self.saveGeometry())
        logger.info("Application close: cleaning up playback and I/O...")
        try:
            if getattr(self, "_fullscreen_window", None) is not None:
                self._fullscreen_window.close()
            if getattr(self, "playback_controller", None):
                self.playback_controller.stop()
            if getattr(self, "story_clock", None):
                if (
                    getattr(self, "story_timeline", None)
                    and self.story_timeline.sync_dy_enabled()
                    and getattr(self, "osc_manager", None)
                ):
                    self.osc_manager.send_dy_command(False)
                self.story_clock.stop()
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

        Layout (horizontal splitter; Serial / OSC sit to the right):

            ┌─ left ──────────────────────────────────┬─ objects ─┐
            │  Dataset Information │ Waveform Viewer  │ Serial /  │
            │  Data Picker         │ Playback         │ OSC cards │
            │  Pin timeline + Speed graph             │           │
            │  Log (optional)                         │           │
            └─────────────────────────────────────────┴───────────┘
        """
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QVBoxLayout()
        main_layout.setSpacing(0)
        m = WIDGET_PANEL_MARGIN
        main_layout.setContentsMargins(m, m, m, m)
        central_widget.setLayout(main_layout)

        # --- Left top: dataset column + waveform / playback ---
        self._top_column_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._top_column_splitter.setChildrenCollapsible(False)

        left_column = QWidget()
        left_column.setMinimumWidth(LEFT_PANEL_WIDTH)
        left_column_layout = QVBoxLayout(left_column)
        left_column_layout.setContentsMargins(0, 0, 0, 0)
        left_column_layout.setSpacing(0)

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
        left_column_layout.addWidget(wrap_panel(self.metadata_widget), 1)

        self.data_picker = DataPicker(data_manager=self.data_manager)
        picker_sp = self.data_picker.sizePolicy()
        picker_sp.setVerticalPolicy(QSizePolicy.Policy.Fixed)
        self.data_picker.setSizePolicy(picker_sp)
        left_column_layout.addWidget(wrap_panel(self.data_picker), 0)

        waveform_column = QWidget()
        waveform_column_layout = QVBoxLayout(waveform_column)
        waveform_column_layout.setContentsMargins(0, 0, 0, 0)
        waveform_column_layout.setSpacing(0)

        self.waveform_viewer = WaveformViewer()
        waveform_sp = self.waveform_viewer.sizePolicy()
        waveform_sp.setVerticalPolicy(QSizePolicy.Policy.Expanding)
        self.waveform_viewer.setSizePolicy(waveform_sp)
        waveform_column_layout.addWidget(wrap_panel(self.waveform_viewer), 1)

        self.playback_controls = PlaybackControls()
        playback_sp = self.playback_controls.sizePolicy()
        playback_sp.setVerticalPolicy(QSizePolicy.Policy.Fixed)
        self.playback_controls.setSizePolicy(playback_sp)
        waveform_column_layout.addWidget(wrap_panel(self.playback_controls), 0)

        self._top_column_splitter.addWidget(left_column)
        self._top_column_splitter.addWidget(waveform_column)
        self._top_column_splitter.setStretchFactor(0, 0)
        self._top_column_splitter.setStretchFactor(1, 1)

        # --- Left bottom: Dust Devil pin timeline + speed envelope + optional log ---
        self._bottom_splitter = QSplitter(Qt.Orientation.Vertical)
        self._bottom_splitter.setChildrenCollapsible(False)

        self.story_timeline = StoryTimelinePanel(
            self.pin_cues, self.story_clock, self.speed_envelope
        )
        self._story_timeline_panel = wrap_panel(self.story_timeline)
        self._bottom_splitter.addWidget(self._story_timeline_panel)

        self.log_section = QWidget()
        log_layout = QVBoxLayout()
        log_layout.setContentsMargins(0, 0, 0, 0)
        log_layout.setSpacing(WIDGET_PANEL_MARGIN // 2)
        log_title = QLabel("<b>Log</b>")
        log_title.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        log_layout.addWidget(log_title)
        self.log_viewer = LogViewer()
        log_layout.addWidget(self.log_viewer, 1)
        self.log_section.setLayout(log_layout)
        self._log_section_panel = wrap_panel(self.log_section)
        self._bottom_splitter.addWidget(self._log_section_panel)
        self._bottom_splitter.setStretchFactor(0, 3)
        self._bottom_splitter.setStretchFactor(1, 1)

        self._left_row_splitter = QSplitter(Qt.Orientation.Vertical)
        self._left_row_splitter.setChildrenCollapsible(False)
        self._left_row_splitter.addWidget(self._top_column_splitter)
        self._left_row_splitter.addWidget(self._bottom_splitter)
        self._left_row_splitter.setStretchFactor(0, 1)
        self._left_row_splitter.setStretchFactor(1, 1)

        # --- Right: Serial / OSC object cards, full height ---
        self.object_cards = ObjectCardsContainer(
            selected_channels_provider=lambda: self._valid_selected_channels_for_io(),
            sorted_stream_channels_provider=lambda: sorted(
                self.waveform_model.get_all_channels()
            ),
        )
        self.object_cards.setMinimumWidth(420)
        cards_sp = self.object_cards.sizePolicy()
        cards_sp.setHorizontalPolicy(QSizePolicy.Policy.Ignored)
        self.object_cards.setSizePolicy(cards_sp)
        self._object_cards_panel = wrap_panel(self.object_cards)

        self._main_column_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._main_column_splitter.setChildrenCollapsible(False)
        self._main_column_splitter.addWidget(self._left_row_splitter)
        self._main_column_splitter.addWidget(self._object_cards_panel)
        self._main_column_splitter.setStretchFactor(0, 1)
        self._main_column_splitter.setStretchFactor(1, 0)
        self._main_column_splitter.splitterMoved.connect(self._on_main_splitter_moved)

        main_layout.addWidget(self._main_column_splitter, 1)

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
        """Keep the dataset column at LEFT_PANEL_WIDTH; waveform uses the rest."""
        total = self._top_column_splitter.width()
        if total <= 0:
            return
        left = min(LEFT_PANEL_WIDTH, max(0, total - 1))
        self._top_column_splitter.setSizes([left, max(1, total - left)])

    def _sync_left_row_split(self) -> None:
        """Initial 50/50 split between waveform and the Dust Devil timeline on the left."""
        total = self._left_row_splitter.height()
        if total <= 0:
            return
        top = total // 2
        self._left_row_splitter.setSizes([top, total - top])

    def _sync_main_column_split(self) -> None:
        """Give Serial / OSC object cards a dedicated right column."""
        total = self._main_column_splitter.width()
        if total <= 0:
            return
        right = min(STATIONS_PANEL_WIDTH, max(420, total * 2 // 5))
        self._main_column_splitter.setSizes([max(1, total - right), right])
        self._main_right_width = right

    def _remember_main_right_width(self) -> None:
        sizes = self._main_column_splitter.sizes()
        if len(sizes) >= 2 and sizes[1] > 0:
            self._main_right_width = sizes[1]

    def _on_main_splitter_moved(self, _pos: int, _index: int) -> None:
        self._remember_main_right_width()

    def _keep_main_split_right_width(self) -> None:
        """Keep the right column width when the window is resized."""
        right = self._main_right_width
        if right is None:
            return
        total = self._main_column_splitter.width()
        if total <= 0:
            return
        right = min(max(420, right), max(420, total - 1))
        self._main_column_splitter.setSizes([max(1, total - right), right])

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        if self._splits_initialized:
            self._keep_main_split_right_width()

    def _apply_log_visibility(self, visible: bool) -> None:
        """Show or hide the log panel; the timeline fills the left bottom when hidden."""
        if visible:
            if self._bottom_splitter.indexOf(self._log_section_panel) < 0:
                self._bottom_splitter.addWidget(self._log_section_panel)
            self._bottom_splitter.setStretchFactor(0, 3)
            self._bottom_splitter.setStretchFactor(1, 1)
            self._log_section_panel.show()
        else:
            self._log_section_panel.hide()
            self._log_section_panel.setParent(None)

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
        self.data_picker.fullscreen_requested.connect(self._on_fullscreen_requested)

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

        self._connect_story_signals()

        self.object_cards.object_added.connect(self._on_object_added)
        self.object_cards.object_removed.connect(self._on_object_removed)
        self.object_cards.object_config_changed.connect(self._on_object_config_changed)

        for card in self.object_cards._cards.values():
            card.streaming_started.connect(self._on_card_streaming_started)
            card.streaming_stopped.connect(self._on_card_streaming_stopped)

        self.playback_controller.state_changed.connect(self._on_playback_state_changed)

    def _on_fullscreen_requested(self) -> None:
        """Open or close the full-screen dataset + loop waveform window."""
        win = self._fullscreen_window
        if win is not None and win.isVisible():
            win.close()
            return
        if win is None:
            win = FullscreenPreviewWindow(self)
            win.destroyed.connect(self._on_fullscreen_window_destroyed)
            self._fullscreen_window = win
        self._sync_fullscreen_preview()
        win.showFullScreen()
        win.raise_()
        win.activateWindow()

    def _on_fullscreen_window_destroyed(self, *_args) -> None:
        self._fullscreen_window = None

    def _sync_fullscreen_preview(self) -> None:
        """Push dataset info and the live 10 min paging waveform into the full-screen window."""
        win = self._fullscreen_window
        if win is None:
            return
        self._sync_fullscreen_metadata()
        loop_range = self.playback_controls.get_loop_range_from_inputs()
        if loop_range is None:
            loop_range = self.playback_controller.get_loop_range()
        time_span = loop_range or self.waveform_model.get_time_range()
        win.set_live_source(
            self.waveform_model.get_stream(),
            self.waveform_model.get_selected_channels(),
            time_span,
            color_channel_ids=self.waveform_model.get_all_channels(),
        )
        ts = self.playback_controller.get_current_timestamp()
        if ts is None and time_span is not None:
            ts = time_span[0]
        if ts is not None:
            win.update_playhead(ts)
