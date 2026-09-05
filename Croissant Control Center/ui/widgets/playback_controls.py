"""
Playback Controls widget for controlling waveform playback.
"""
import logging
import math
from typing import List, Optional, Tuple

from obspy import UTCDateTime
from PySide6.QtCore import QEvent, Signal, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
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

from core.playback_controller import MIN_LOOP_LENGTH
from settings import MAX_SELECTED_CHANNELS
from .channel_colors import FALLBACK_TRACE_COLOR, channel_color_map

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
    loop_range_changed = Signal(UTCDateTime, UTCDateTime)
    loop_markers_changed = Signal()
    capture_loop_start_clicked = Signal()
    capture_loop_end_clicked = Signal()
    channels_selection_changed = Signal(list)
    position_changed = Signal(UTCDateTime)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._position_slider_updating = False
        self._pending_slider_value = None
        self._time_range = None
        self._loop_inputs_updating = False
        self._channel_ids: List[str] = []
        self._channel_checks: dict[str, QCheckBox] = {}
        self._channels_button_accent_color: Optional[str] = None
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
        self.clear_channels_button = QPushButton("Clear")
        self.clear_channels_button.setToolTip("Unselect all channels")
        self.clear_channels_button.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )
        _fm = self.clear_channels_button.fontMetrics()
        _x_w = _fm.horizontalAdvance("Clear") + 26
        self.clear_channels_button.setFixedWidth(_x_w)
        self.clear_channels_button.clicked.connect(self._on_clear_all_channels)
        channel_layout.addWidget(self.clear_channels_button)
        channel_layout.addStretch()
        self._refresh_channel_strip_theme()
        # Stretch 0: channel strip keeps natural width; value/time labels absorb resize.
        row1.addLayout(channel_layout, 0)

        row1.addStretch()
        self.value_label = QLabel("--")
        self.value_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.value_label.setTextFormat(Qt.TextFormat.PlainText)
        # Live values change width every tick; ignore sizeHint so splitters stay put.
        value_sp = self.value_label.sizePolicy()
        value_sp.setHorizontalPolicy(QSizePolicy.Policy.Ignored)
        value_sp.setHorizontalStretch(1)
        self.value_label.setSizePolicy(value_sp)
        self.value_label.setMinimumWidth(0)
        row1.addWidget(self.value_label, 1)

        row1.addStretch()
        self.time_label = QLabel("--:--:-- / --:--:--")
        self.time_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.time_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
            | Qt.TextInteractionFlag.TextSelectableByKeyboard
        )
        self.time_label.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.time_label.customContextMenuRequested.connect(
            self._show_time_label_context_menu
        )
        self.time_label.setToolTip("Select or right-click to copy playhead time")
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
        speed_cell = QHBoxLayout()
        speed_cell.setContentsMargins(0, 0, 0, 0)
        speed_cell.addWidget(QLabel("Speed:"))
        self.speed_spinbox = QDoubleSpinBox()
        self.speed_spinbox.setRange(0.1, 1000.0)
        self.speed_spinbox.setSingleStep(0.1)
        self.speed_spinbox.setValue(1.0)
        self.speed_spinbox.setDecimals(1)
        self.speed_spinbox.valueChanged.connect(self._on_speed_changed)
        speed_cell.addWidget(self.speed_spinbox)
        speed_cell.addWidget(QLabel("x"))
        btn_1x = QPushButton("1x")
        btn_1x.clicked.connect(lambda: self._set_speed_preset(1.0))
        speed_cell.addWidget(btn_1x)
        btn_10x = QPushButton("10x")
        btn_10x.clicked.connect(lambda: self._set_speed_preset(10.0))
        speed_cell.addWidget(btn_10x)
        btn_100x = QPushButton("100x")
        btn_100x.clicked.connect(lambda: self._set_speed_preset(100.0))
        speed_cell.addWidget(btn_100x)
        speed_cell.addStretch()
        row4.addLayout(speed_cell, 1)

        loop_layout = QHBoxLayout()
        loop_layout.setContentsMargins(0, 0, 0, 0)
        self.loop_checkbox = QCheckBox("Loop")
        self.loop_checkbox.toggled.connect(self.loop_toggled.emit)
        loop_layout.addWidget(self.loop_checkbox)
        self.loop_start_button = QPushButton("Start")
        self.loop_start_button.setToolTip(
            "Set loop start to the current playhead position"
        )
        self.loop_start_button.clicked.connect(self.capture_loop_start_clicked.emit)
        loop_layout.addWidget(self.loop_start_button)
        self.loop_start_edit = QLineEdit()
        self.loop_start_edit.setPlaceholderText("00:00:00")
        self.loop_start_edit.setToolTip(
            "Loop start as elapsed time (HH:MM:SS) from the beginning of the loaded data"
        )
        self.loop_start_edit.editingFinished.connect(self._on_loop_inputs_edited)
        loop_layout.addWidget(self.loop_start_edit, 1)
        self.loop_end_button = QPushButton("End")
        self.loop_end_button.setToolTip(
            "Set loop end to the current playhead position"
        )
        self.loop_end_button.clicked.connect(self.capture_loop_end_clicked.emit)
        loop_layout.addWidget(self.loop_end_button)
        for loop_btn in (self.loop_start_button, self.loop_end_button):
            loop_btn.setSizePolicy(
                QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
            )
            _fm = loop_btn.fontMetrics()
            loop_btn.setFixedWidth(_fm.horizontalAdvance(loop_btn.text()) + 26)
        self.loop_end_edit = QLineEdit()
        self.loop_end_edit.setPlaceholderText("00:00:00")
        self.loop_end_edit.setToolTip(
            "Loop end as elapsed time (HH:MM:SS) from the beginning of the loaded data"
        )
        self.loop_end_edit.editingFinished.connect(self._on_loop_inputs_edited)
        loop_layout.addWidget(self.loop_end_edit, 1)
        row4.addLayout(loop_layout, 1)

        layout.addLayout(row4)
        self.setLayout(layout)

    @staticmethod
    def _channel_menu_stylesheet() -> str:
        return """
            QMenu {
                background-color: palette(window);
                color: palette(window-text);
                border: 1px solid palette(mid);
            }
        """

    @staticmethod
    def _clear_button_stylesheet() -> str:
        return """
            QPushButton {
                background-color: palette(button);
                color: palette(button-text);
                border: 1px solid palette(mid);
                padding: 1px 4px;
            }
        """

    @staticmethod
    def _channels_button_stylesheet(accent_color: Optional[str] = None) -> str:
        text_color = accent_color if accent_color else "palette(button-text)"
        return f"""
            QToolButton {{
                background-color: palette(button);
                color: {text_color};
                border: 1px solid palette(mid);
                padding: 2px 6px;
            }}
        """

    def _refresh_channel_strip_theme(self) -> None:
        """Reapply palette-based QSS after theme / palette changes."""
        if not hasattr(self, "channels_button"):
            return
        self.channels_menu.setStyleSheet(self._channel_menu_stylesheet())
        self.clear_channels_button.setStyleSheet(self._clear_button_stylesheet())
        self.channels_button.setStyleSheet(
            self._channels_button_stylesheet(self._channels_button_accent_color)
        )
        selected = [ch for ch in self._channel_ids if self._channel_checks[ch].isChecked()]
        self._sync_channel_checkbox_colors(selected)

    def changeEvent(self, event: QEvent) -> None:
        _refresh_types = {QEvent.Type.PaletteChange, QEvent.Type.StyleChange}
        if hasattr(QEvent.Type, "ApplicationPaletteChange"):
            _refresh_types.add(QEvent.Type.ApplicationPaletteChange)
        if event.type() in _refresh_types:
            self._refresh_channel_strip_theme()
        super().changeEvent(event)

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

    def _show_time_label_context_menu(self, pos) -> None:
        menu = QMenu(self)
        copy_action = QAction("Copy", self)
        selected = self.time_label.selectedText()
        text = selected if selected else self.time_label.text()
        copy_action.triggered.connect(lambda: QApplication.clipboard().setText(text))
        menu.addAction(copy_action)
        menu.exec(self.time_label.mapToGlobal(pos))

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

    def set_data_time_range(
        self, start: Optional[UTCDateTime], end: Optional[UTCDateTime]
    ) -> None:
        """Store waveform bounds used to convert loop fields to UTC timestamps."""
        if start is not None and end is not None:
            self._time_range = (start, end)
        else:
            self._time_range = None

    def update_loop_display(
        self, start: Optional[UTCDateTime] = None, end: Optional[UTCDateTime] = None
    ) -> None:
        """Show loop endpoints as elapsed HH:MM:SS from data start."""
        self._loop_inputs_updating = True
        self.loop_start_edit.blockSignals(True)
        self.loop_end_edit.blockSignals(True)
        if start is not None and end is not None and self._time_range is not None:
            if start > end:
                start, end = end, start
            data_start, _ = self._time_range
            start_s = float(start - data_start)
            end_s = float(end - data_start)
            self.loop_start_edit.setText(self._format_duration_seconds(start_s))
            self.loop_end_edit.setText(self._format_duration_seconds(end_s))
        else:
            self.loop_start_edit.clear()
            self.loop_end_edit.clear()
        self.loop_start_edit.blockSignals(False)
        self.loop_end_edit.blockSignals(False)
        self._loop_inputs_updating = False

    def clear_loop_display(self) -> None:
        """Clear loop time fields without emitting range changes."""
        self.update_loop_display(None, None)

    def set_loop_enabled(self, enabled: bool) -> None:
        self.loop_checkbox.blockSignals(True)
        self.loop_checkbox.setChecked(enabled)
        self.loop_checkbox.blockSignals(False)

    def get_loop_markers_from_inputs(
        self,
    ) -> Tuple[Optional[UTCDateTime], Optional[UTCDateTime], bool, bool]:
        """Parse loop fields into (start, end, start_set, end_set)."""
        if self._time_range is None:
            return None, None, False, False

        data_start, data_end = self._time_range
        total_s = float(data_end - data_start)
        start_text = self.loop_start_edit.text().strip()
        end_text = self.loop_end_edit.text().strip()
        start_set = bool(start_text)
        end_set = bool(end_text)
        start: Optional[UTCDateTime] = None
        end: Optional[UTCDateTime] = None

        if start_set:
            start_s = self._parse_duration_text(start_text)
            if start_s is None:
                start_set = False
            else:
                start_s = max(0.0, min(start_s, total_s))
                start = data_start + start_s

        if end_set:
            end_s = self._parse_duration_text(end_text)
            if end_s is None:
                end_set = False
            else:
                end_s = max(0.0, min(end_s, total_s))
                end = data_start + end_s

        return start, end, start_set, end_set

    def set_loop_endpoint_from_timestamp(
        self, endpoint: str, timestamp: UTCDateTime
    ) -> None:
        """Set loop start or end field from an absolute UTC timestamp."""
        if self._time_range is None:
            return
        data_start, data_end = self._time_range
        total_s = float(data_end - data_start)
        elapsed_s = float(timestamp - data_start)
        elapsed_s = max(0.0, min(elapsed_s, total_s))
        text = self._format_duration_seconds(elapsed_s)
        self._loop_inputs_updating = True
        if endpoint == "start":
            self.loop_start_edit.setText(text)
        elif endpoint == "end":
            self.loop_end_edit.setText(text)
        self._loop_inputs_updating = False
        self._normalize_loop_fields()
        self._emit_loop_changes()

    def _normalize_loop_fields(self) -> None:
        """Swap start/end field values when start is after end."""
        start_s = self._parse_duration_text(self.loop_start_edit.text())
        end_s = self._parse_duration_text(self.loop_end_edit.text())
        if start_s is None or end_s is None or start_s <= end_s:
            return
        self._loop_inputs_updating = True
        start_text = self.loop_start_edit.text()
        end_text = self.loop_end_edit.text()
        self.loop_start_edit.setText(end_text)
        self.loop_end_edit.setText(start_text)
        self._loop_inputs_updating = False

    def get_loop_range_from_inputs(
        self,
    ) -> Optional[Tuple[UTCDateTime, UTCDateTime]]:
        """Parse loop start/end fields into UTC timestamps, or None if invalid."""
        start, end, start_set, end_set = self.get_loop_markers_from_inputs()
        if not start_set or not end_set or start is None or end is None:
            return None
        if start > end:
            start, end = end, start
        if end <= start:
            return None
        return (start, end)

    def is_loop_range_valid(self) -> bool:
        """True when both loop fields form a usable playback range."""
        loop_range = self.get_loop_range_from_inputs()
        if loop_range is None:
            return False
        start, end = loop_range
        return (end - start) >= MIN_LOOP_LENGTH

    @staticmethod
    def _parse_duration_text(text: str) -> Optional[float]:
        """Parse HH:MM:SS or MM:SS into elapsed seconds."""
        text = (text or "").strip()
        if not text:
            return None
        parts = text.split(":")
        try:
            if len(parts) == 1:
                return float(parts[0])
            if len(parts) == 2:
                minutes, seconds = int(parts[0]), float(parts[1])
                return minutes * 60.0 + seconds
            if len(parts) == 3:
                hours, minutes, seconds = int(parts[0]), int(parts[1]), float(parts[2])
                return hours * 3600.0 + minutes * 60.0 + seconds
        except (ValueError, TypeError):
            return None
        return None

    def _emit_loop_changes(self) -> None:
        self.loop_markers_changed.emit()
        loop_range = self.get_loop_range_from_inputs()
        if loop_range is None:
            return
        start, end = loop_range
        if (end - start) < MIN_LOOP_LENGTH:
            return
        self.loop_range_changed.emit(start, end)

    def _on_loop_inputs_edited(self) -> None:
        if self._loop_inputs_updating:
            return

        self._normalize_loop_fields()
        loop_range = self.get_loop_range_from_inputs()
        if loop_range is not None and (loop_range[1] - loop_range[0]) < MIN_LOOP_LENGTH:
            QMessageBox.warning(
                self,
                "Loop range",
                f"Loop range must be at least {MIN_LOOP_LENGTH:.0f} seconds.",
            )
        self._emit_loop_changes()

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
                cb.setStyleSheet(
                    f"QCheckBox {{ color: {color}; background: transparent; }}"
                )
            else:
                cb.setStyleSheet(
                    "QCheckBox { color: palette(window-text); background: transparent; }"
                )

    def _update_channels_button_text(self, selected: List[str]) -> None:
        cmap = channel_color_map(sorted(self._channel_ids))
        n = len(selected)
        if n == 0:
            self.channels_button.setText("Select a channel")
            self._channels_button_accent_color = None
        else:
            first = selected[0]
            self._channels_button_accent_color = cmap.get(first, FALLBACK_TRACE_COLOR)
            if n == 1:
                self.channels_button.setText(first)
            else:
                self.channels_button.setText(f"{first} +{n - 1}")
        self.channels_button.setStyleSheet(
            self._channels_button_stylesheet(self._channels_button_accent_color)
        )

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
