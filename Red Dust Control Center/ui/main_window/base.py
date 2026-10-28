"""Shared typing for MainWindow mixins (attributes provided by MainWindow.__init__)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from PySide6.QtWidgets import QLabel, QTextEdit, QWidget

from core.data_manager import DataManager
from core.osc_manager import OSCManager
from core.pin_cues import PinCueList
from core.playback_controller import PlaybackController
from core.session_manager import SessionManager
from core.speed_envelope import SpeedEnvelope
from core.story_clock import StoryClock
from core.waveform_model import WaveformModel
from ui.widgets.data_picker import DataPicker
from ui.widgets.fullscreen_preview import FullscreenPreviewWindow
from ui.widgets.object_cards import ObjectCardsContainer
from ui.widgets.playback_controls import PlaybackControls
from ui.widgets.story_timeline import StoryTimelinePanel
from ui.widgets.waveform_viewer import WaveformViewer


class _MainWindowBase:
    """Not instantiated; documents instance attributes for mixin type checking."""

    data_manager: DataManager
    waveform_model: WaveformModel
    playback_controller: PlaybackController
    osc_manager: OSCManager
    session_manager: SessionManager
    story_clock: StoryClock
    pin_cues: PinCueList
    speed_envelope: SpeedEnvelope

    current_session_path: Optional[Path]
    pending_session_state: Optional[dict[str, Any]]
    load_thread: Any
    metadata_thread: Any

    data_picker: DataPicker
    playback_controls: PlaybackControls
    waveform_viewer: WaveformViewer
    story_timeline: StoryTimelinePanel
    object_cards: ObjectCardsContainer
    metadata_widget: QWidget
    log_section: QWidget
    dataset_label: QLabel
    metadata_text: QTextEdit
    _fullscreen_window: FullscreenPreviewWindow | None
