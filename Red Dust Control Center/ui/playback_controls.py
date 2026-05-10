"""
Playback Controls widget for controlling waveform playback.
"""
import logging
import math
from typing import List, Optional, Tuple

from obspy import UTCDateTime
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

from settings import MAX_SELECTED_CHANNELS
from ui.channel_colors import FALLBACK_TRACE_COLOR, channel_color_map

logger = logging.getLogger(__name__)


def _elapsed_total_seconds_for_playback(
    current: Optional[UTCDateTime],
    start: Optional[UTCDateTime],
    end: Optional[UTCDateTime],
) -> Optional[Tuple[float, float]]:
    if current is None or start is None or end is None:
        return None
    elapsed_s = float(current - start)
    total_s = float(end - start)
    if total_s < 0:
        total_s = 0.0
    if elapsed_s < 0:
        elapsed_s = 0.0
    if elapsed_s > total_s:
        elapsed_s = total_s
    return (elapsed_s, total_s)

_LOG_TAG = "[multi_ch]"


class PlaybackControls(QWidget):
    """Widget for controlling playback."""

    play_clicked = Signal()
    pause_clicked = Signal()
    stop_clicked = Signal()
    speed_changed = Signal(float)
    loop_toggled = Signal(bool)
    channels_selection_changed = Signal(list)
    position_changed = Signal(UTCDateTime)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._position_slider_updating = False
        self._pending_slider_value = None
        self._time_range = None
        self._channel_ids: List[str] = []
        self._channel_checks: dict[str, QCheckBox] = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()

        row1 = QHBoxLayout()

        channel_layout = QHBoxLayout()
        channel_layout.setContentsMargins(0, 0, 0, 0)
        channel_layout.addWidget(QLabel("Channels:"))
        self.channels_button = QToolButton()
        self.channels_button.setText("(0)")
        self.channels_button.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        self.channels_menu = QMenu(self.channels_button)
        self.channels_button.setMenu(self.channels_menu)
        self.channels_button.setSizePolicy(
            QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed
        )
        channel_layout.addWidget(self.channels_button)
        self.clear_channels_button = QPushButton("X")
        self.clear_channels_button.setToolTip("Unselect all channels")
        self.clear_channels_button.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        _fm = self.clear_channels_button.fontMetrics()
        _x_w = _fm.horizontalAdvance("X") + 10
        self.clear_channels_button.setFixedWidth(_x_w)
        self.clear_channels_button.setStyleSheet("QPushButton { padding: 1px 4px; }")
        self.clear_channels_button.clicked.connect(self._on_clear_all_channels)
        channel_layout.addWidget(self.clear_channels_button)
        channel_layout.addStretch()
        # Stretch 0: channel strip keeps natural width; value/time labels absorb resize.
        row1.addLayout(channel_layout, 0)

        row1.addStretch()
        self.value_label = QLabel("--")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value_label.setTextFormat(Qt.TextFormat.PlainText)
        row1.addWidget(self.value_label, 1)

        row1.addStretch()
        self.time_label = QLabel("--:--:-- / --:--:--")
        self.time_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        row1.addWidget(self.time_label, 1)

        layout.addLayout(row1)

        row2 = QHBoxLayout()
        position_label = QLabel("Position:")
        row2.addWidget(position_label)
        self.position_slider = QSlider(Qt.Orientation.Horizontal)
        self.position_slider.setMinimum(0)
        self.position_slider.setMaximum(1000)
        self.position_slider.setValue(0)
        self.position_slider.valueChanged.connect(self._on_position_slider_changed)
        row2.addWidget(self.position_slider, 1)
        layout.addLayout(row2)

        row3 = QHBoxLayout()
        self.play_button = QPushButton("Play")
        self.play_button.clicked.connect(self.play_clicked.emit)
        row3.addWidget(self.play_button, 1)
        self.pause_button = QPushButton("Pause")
        self.pause_button.clicked.connect(self.pause_clicked.emit)
        row3.addWidget(self.pause_button, 1)
        self.stop_button = QPushButton("Stop")
        self.stop_button.clicked.connect(self.stop_clicked.emit)
        self.stop_button.setEnabled(False)
        row3.addWidget(self.stop_button, 1)
        layout.addLayout(row3)

        self._update_button_states("stopped")

        row4 = QHBoxLayout()
        speed_layout = QHBoxLayout()
        speed_layout.setContentsMargins(0, 0, 0, 0)
        speed_layout.addWidget(QLabel("Speed:"))
        self.speed_spinbox = QDoubleSpinBox()
        self.speed_spinbox.setRange(0.1, 1000.0)
        self.speed_spinbox.setSingleStep(0.1)
        self.speed_spinbox.setValue(1.0)
        self.speed_spinbox.setDecimals(1)
        self.speed_spinbox.valueChanged.connect(self._on_speed_changed)
        speed_layout.addWidget(self.speed_spinbox)
        speed_layout.addWidget(QLabel("x"))
        speed_layout.addStretch()
        row4.addLayout(speed_layout, 1)

        row4.addStretch()
        speed_button_layout = QHBoxLayout()
        btn_1x = QPushButton("1x")
        btn_1x.clicked.connect(lambda: self._set_speed_preset(1.0))
        speed_button_layout.addWidget(btn_1x)
        btn_10x = QPushButton("10x")
        btn_10x.clicked.connect(lambda: self._set_speed_preset(10.0))
        speed_button_layout.addWidget(btn_10x)
        btn_100x = QPushButton("100x")
        btn_100x.clicked.connect(lambda: self._set_speed_preset(100.0))
        speed_button_layout.addWidget(btn_100x)
        row4.addLayout(speed_button_layout, 1)

        row4.addStretch()
        self.loop_checkbox = QCheckBox("Enable Loop")
        self.loop_checkbox.toggled.connect(self.loop_toggled.emit)
        row4.addWidget(self.loop_checkbox, 1, Qt.AlignmentFlag.AlignRight)

        layout.addLayout(row4)
        layout.addStretch()
        self.setLayout(layout)

    def update_time_display(
        self,
        current: Optional[UTCDateTime],
        start: Optional[UTCDateTime],
        end: Optional[UTCDateTime],
    ) -> None:
        pair = _elapsed_total_seconds_for_playback(current, start, end)
        if pair is None:
            self.time_label.setText("--:--:-- / --:--:--")
            return
        elapsed_s, total_s = pair
        self.time_label.setText(
            f"{self._format_duration_seconds(elapsed_s)} / "
            f"{self._format_duration_seconds(total_s)}"
        )

    @staticmethod
    def _non_finite_placeholder(value: Optional[float]) -> bool:
        if value is None:
            return True
        return math.isnan(value) or math.isinf(value)

    def _format_raw_for_label(self, raw_value: Optional[float]) -> str:
        if self._non_finite_placeholder(raw_value):
            return "--"
        assert raw_value is not None
        try:
            if raw_value == int(raw_value):
                return str(int(raw_value))
            return f"{raw_value:.4f}".rstrip("0").rstrip(".")
        except (ValueError, OverflowError):
            return "--"

    def _format_norm_for_label(self, normalized_value: Optional[float]) -> str:
        if self._non_finite_placeholder(normalized_value):
            return "--"
        assert normalized_value is not None
        try:
            return f"{normalized_value:.3f}"
        except (ValueError, OverflowError):
            return "--"

    def update_value_display(
        self,
        entries: Optional[List[Tuple[str, Optional[float], Optional[float]]]] = None,
    ) -> None:
        if not entries:
            self.value_label.setTextFormat(Qt.TextFormat.PlainText)
            self.value_label.setText("--")
            return
        cmap = channel_color_map(sorted(self._channel_ids))
        parts: List[str] = []
        for ch, raw_value, normalized_value in entries:
            color = cmap.get(ch, FALLBACK_TRACE_COLOR)
            raw_str = self._format_raw_for_label(raw_value)
            norm_str = self._format_norm_for_label(normalized_value)
            parts.append(
                f'<span style="color:{color}">{raw_str}</span> '
                f'(<span style="color:{color}">{norm_str}</span>)'
            )
        self.value_label.setTextFormat(Qt.TextFormat.RichText)
        self.value_label.setText(", ".join(parts))

    def update_loop_display(
        self, start: UTCDateTime = None, end: UTCDateTime = None
    ) -> None:
        pass

    def set_loop_enabled(self, enabled: bool) -> None:
        self.loop_checkbox.setChecked(enabled)

    def set_speed(self, speed: float) -> None:
        self.speed_spinbox.setValue(speed)

    def _format_duration_seconds(self, seconds: float) -> str:
        if not (seconds >= 0) or seconds != seconds:  # NaN or negative
            return "--:--:--"
        total = int(round(seconds))
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def _on_speed_changed(self, value: float) -> None:
        self.speed_changed.emit(value)

    def _set_speed_preset(self, speed: float) -> None:
        self.speed_spinbox.setValue(speed)

    def _on_position_slider_changed(self, value: int) -> None:
        if self._position_slider_updating:
            return
        self._pending_slider_value = value

    def update_position_slider(
        self,
        current_time: UTCDateTime,
        start_time: UTCDateTime,
        end_time: UTCDateTime,
    ) -> None:
        if start_time is None or end_time is None or current_time is None:
            return
        self._time_range = (start_time, end_time)
        self._position_slider_updating = True
        self.position_slider.blockSignals(True)
        total_duration = end_time - start_time
        if total_duration > 0:
            elapsed = current_time - start_time
            percentage = elapsed / total_duration
            slider_value = int(percentage * 1000)
            slider_value = max(0, min(1000, slider_value))
            if slider_value != self.position_slider.value():
                self.position_slider.setValue(slider_value)
        self.position_slider.blockSignals(False)
        self._position_slider_updating = False

    def get_pending_position(self) -> Optional[UTCDateTime]:
        if self._pending_slider_value is None or self._time_range is None:
            return None
        start_time, end_time = self._time_range
        slider_value = self._pending_slider_value
        percentage = slider_value / 1000.0
        total_duration = end_time - start_time
        if total_duration <= 0:
            return None
        offset = total_duration * percentage
        timestamp = start_time + offset
        self._pending_slider_value = None
        return timestamp

    def _on_clear_all_channels(self) -> None:
        for cb in self._channel_checks.values():
            cb.blockSignals(True)
            cb.setChecked(False)
            cb.blockSignals(False)
        self._sync_channel_checkbox_colors([])
        self._update_channels_button_text([])
        logger.debug("%s clear all channels", _LOG_TAG)
        self.channels_selection_changed.emit([])

    def _emit_selection_from_menu(self) -> None:
        sender = self.sender()
        selected = [ch for ch in self._channel_ids if self._channel_checks[ch].isChecked()]
        if len(selected) > MAX_SELECTED_CHANNELS:
            if isinstance(sender, QCheckBox) and sender.isChecked():
                sender.blockSignals(True)
                sender.setChecked(False)
                sender.blockSignals(False)
                QMessageBox.information(
                    self,
                    "Channels",
                    f"At most {MAX_SELECTED_CHANNELS} channels can be selected.",
                )
            selected = [ch for ch in self._channel_ids if self._channel_checks[ch].isChecked()]
        self._sync_channel_checkbox_colors(selected)
        self._update_channels_button_text(selected)
        logger.debug("%s channels_selection_changed count=%s", _LOG_TAG, len(selected))
        self.channels_selection_changed.emit(selected)

    def _sync_channel_checkbox_colors(self, selected: List[str]) -> None:
        """Color label text only for checked channels; others use the default palette."""
        sel_set = set(selected)
        cmap = channel_color_map(sorted(self._channel_ids))
        for ch, cb in self._channel_checks.items():
            if ch in sel_set:
                color = cmap.get(ch, FALLBACK_TRACE_COLOR)
                cb.setStyleSheet(f"QCheckBox {{ color: {color}; }}")
            else:
                cb.setStyleSheet("")

    def _update_channels_button_text(self, selected: List[str]) -> None:
        cmap = channel_color_map(sorted(self._channel_ids))
        n = len(selected)
        if n == 0:
            self.channels_button.setText("Select a channel")
            self.channels_button.setStyleSheet("")
        else:
            first = selected[0]
            color = cmap.get(first, FALLBACK_TRACE_COLOR)
            self.channels_button.setStyleSheet(f"QToolButton {{ color: {color}; }}")
            if n == 1:
                self.channels_button.setText(first)
            else:
                self.channels_button.setText(f"{first} +{n - 1}")

    def set_channels(self, channels: list[str]) -> None:
        self.channels_menu.clear()
        self._channel_checks.clear()
        self._channel_ids = list(channels)
        for ch in channels:
            cb = QCheckBox(ch)
            wa = QWidgetAction(self.channels_menu)
            wa.setDefaultWidget(cb)
            self.channels_menu.addAction(wa)
            self._channel_checks[ch] = cb
            cb.toggled.connect(self._emit_selection_from_menu)
        logger.debug("%s channel menu rebuilt n=%s", _LOG_TAG, len(channels))
        self._sync_channel_checkbox_colors([])
        self._update_channels_button_text([])

    def set_selected_channels(self, selected: list[str]) -> None:
        sel_set = set(selected)
        for ch, cb in self._channel_checks.items():
            cb.blockSignals(True)
            cb.setChecked(ch in sel_set)
            cb.blockSignals(False)
        ordered = [ch for ch in self._channel_ids if ch in sel_set]
        self._sync_channel_checkbox_colors(ordered)
        self._update_channels_button_text(ordered)
        logger.debug(
            "%s set_selected_channels sync n=%s (blocked emit)", _LOG_TAG, len(ordered)
        )

    def _update_button_states(self, state: str) -> None:
        if state == "playing":
            self.play_button.setEnabled(False)
            self.pause_button.setEnabled(True)
            self.stop_button.setEnabled(True)
        elif state == "paused":
            self.play_button.setEnabled(True)
            self.pause_button.setEnabled(False)
            self.stop_button.setEnabled(True)
        else:
            self.play_button.setEnabled(True)
            self.pause_button.setEnabled(False)
            self.stop_button.setEnabled(False)

    def set_playback_state(self, state: str) -> None:
        self._update_button_states(state)
