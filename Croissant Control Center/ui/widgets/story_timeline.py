"""Croissant story timeline: two pin lanes with on/off clips per station."""

from __future__ import annotations

from typing import Optional, Sequence, Tuple

from PySide6.QtCore import QPointF, QRectF, QSize, Qt, QTime, Signal
from PySide6.QtGui import (
    QColor,
    QFont,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPaintEvent,
    QPalette,
    QPen,
    QPolygonF,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QTimeEdit,
    QVBoxLayout,
    QWidget,
)

from core.pin_cues import PinClip, PinCueList
from core.speed_envelope import SpeedEnvelope, SpeedPoint, clamp_speed
from core.story_clock import StoryClock
from settings import (
    PIN_SLOT_LABELS,
    STORY_MIN_CLIP_SEC,
    STORY_SPEED_DEFAULT,
    STORY_SPEED_MAX,
    STORY_SPEED_MIN,
)
from ui.layout_helpers import panel_title
from ui.widgets.channel_colors import CHANNEL_TRACE_COLORS

LANE_H = 22
# Tall enough for tick marks plus the time labels under them.
RULER_H = 28
LABEL_W = 54
HANDLE_PX = 6
DEFAULT_CLICK_CLIP_SEC = 10.0
# Comfortable speed-graph height. Extra panel space still goes to this lane;
# the splitter may shrink it down to SPEED_LANE_MIN_H.
SPEED_LANE_H = 72
SPEED_LANE_MIN_H = 24
SPEED_POINT_R = 5
SPEED_HIT_PX = 8


def format_story_time(sec: float) -> str:
    sec = max(0.0, float(sec))
    minutes = int(sec) // 60
    seconds = int(sec) % 60
    return f"{minutes}:{seconds:02d}"


def seconds_to_qtime(sec: float) -> QTime:
    total = max(0, int(round(sec)))
    minutes, seconds = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    return QTime(min(hours, 23), minutes, seconds)


def qtime_to_seconds(value: QTime) -> float:
    return float(value.hour() * 3600 + value.minute() * 60 + value.second())


class StoryTimelineCanvas(QWidget):
    seek_requested = Signal(float)
    clips_edited = Signal()

    def __init__(
        self,
        cues: PinCueList,
        clock: StoryClock,
        envelope: SpeedEnvelope,
        parent=None,
        pin_labels: Optional[Sequence[str]] = None,
        lane_color_offset: int = 0,
    ):
        super().__init__(parent)
        self._cues = cues
        self._clock = clock
        self._envelope = envelope
        self._pin_labels = list(pin_labels) if pin_labels else []
        self._lane_color_offset = int(lane_color_offset)
        self._selected_id: Optional[str] = None
        self._selected_speed_id: Optional[str] = None
        self._drag_mode: Optional[str] = None
        self._drag_clip_id: Optional[str] = None
        self._drag_speed_id: Optional[str] = None
        self._drag_origin_sec = 0.0
        self._drag_clip_start = 0.0
        self._drag_clip_end = 0.0
        self._create_pin: Optional[int] = None
        self._create_start = 0.0
        self._create_end = 0.0
        # Floor is the pin lanes, a thin speed strip, and the ruler. Reserving
        # the full speed lane pinned the splitter above the stations.
        self.setMinimumHeight(
            max(1, cues.pin_count) * LANE_H + SPEED_LANE_MIN_H + RULER_H
        )
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)

    def sizeHint(self) -> QSize:
        """Preferred graph height. The splitter may shrink down to the minimum."""
        width = super().sizeHint().width()
        return QSize(
            width if width > 0 else 0,
            max(1, self._cues.pin_count) * LANE_H + SPEED_LANE_H + RULER_H,
        )

    def _lane_color(self, pin_index: int) -> QColor:
        idx = (self._lane_color_offset + pin_index) % len(CHANNEL_TRACE_COLORS)
        return QColor(CHANNEL_TRACE_COLORS[idx])

    def _pin_label(self, pin_index: int) -> str:
        if 0 <= pin_index < len(self._pin_labels):
            return self._pin_labels[pin_index]
        if pin_index < len(PIN_SLOT_LABELS):
            return PIN_SLOT_LABELS[pin_index]
        return f"Pin_{pin_index}"

    def selected_clip_id(self) -> Optional[str]:
        return self._selected_id

    def set_selected_clip_id(self, clip_id: Optional[str]) -> None:
        if self._selected_id != clip_id:
            self._selected_id = clip_id
            if clip_id is not None:
                self._selected_speed_id = None
            self.update()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if self._selected_speed_id and self._envelope.remove_point(self._selected_speed_id):
                self._selected_speed_id = None
                self.clips_edited.emit()
                self.update()
                event.accept()
                return
            if self._selected_id and self._cues.remove_clip(self._selected_id):
                self._selected_id = None
                self.clips_edited.emit()
                self.update()
                event.accept()
                return
        super().keyPressEvent(event)

    def paintEvent(self, event: QPaintEvent) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        pal = self.palette()
        painter.fillRect(self.rect(), pal.color(QPalette.ColorRole.Base))

        track = self._track_rect()
        duration = max(1.0, self._cues.duration_sec)

        text_color = pal.color(QPalette.ColorRole.Text)
        muted = QColor(text_color)
        muted.setAlpha(140)
        grid = QColor(text_color)
        grid.setAlpha(40)

        painter.fillRect(QRectF(0, 0, LABEL_W, self.height()), pal.color(QPalette.ColorRole.Window))
        painter.setPen(QPen(grid, 1))
        painter.drawLine(LABEL_W, 0, LABEL_W, self.height())

        for pin in range(self._cues.pin_count):
            y = pin * LANE_H
            lane_bg = pal.color(QPalette.ColorRole.AlternateBase) if pin % 2 else pal.color(QPalette.ColorRole.Base)
            painter.fillRect(QRectF(LABEL_W, y, track.width(), LANE_H), lane_bg)
            color = self._lane_color(pin)
            painter.setPen(color)
            label = self._pin_label(pin).replace("Pin_", "Pin ")
            painter.drawText(QRectF(4, y, LABEL_W - 8, LANE_H), Qt.AlignmentFlag.AlignVCenter, label)
            painter.setPen(QPen(grid, 1))
            painter.drawLine(LABEL_W, y + LANE_H, self.width(), y + LANE_H)

        for clip in self._cues.clips:
            rect = self._clip_rect(clip, track, duration)
            color = self._lane_color(clip.pin_index)
            fill = QColor(color)
            fill.setAlpha(200 if clip.clip_id == self._selected_id else 150)
            painter.setPen(QPen(color.darker(115), 1))
            painter.setBrush(fill)
            painter.drawRoundedRect(rect, 3, 3)
            if clip.clip_id == self._selected_id:
                painter.setPen(QPen(pal.color(QPalette.ColorRole.HighlightedText), 1))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 2, 2)

        if self._drag_mode == "create" and self._create_pin is not None:
            preview = PinClip(
                "preview",
                self._create_pin,
                min(self._create_start, self._create_end),
                max(self._create_start, self._create_end),
            )
            rect = self._clip_rect(preview, track, duration)
            color = self._lane_color(self._create_pin)
            color.setAlpha(90)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(rect, 3, 3)

        self._paint_speed_lane(painter, track, duration, pal, muted, grid)
        self._paint_ruler(painter, track, duration, muted, grid, text_color)

        play_x = self._sec_to_x(self._clock.get_current_sec(), track, duration)
        painter.setPen(QPen(QColor("#e11d48"), 2))
        painter.drawLine(int(play_x), 0, int(play_x), self.height())

    def _paint_speed_lane(
        self,
        painter: QPainter,
        track: QRectF,
        duration: float,
        pal: QPalette,
        muted: QColor,
        grid: QColor,
    ) -> None:
        lane = self._speed_lane_rect()
        painter.fillRect(lane, pal.color(QPalette.ColorRole.Base))
        painter.setPen(QPen(grid, 1))
        painter.drawLine(int(lane.left()), int(lane.top()), self.width(), int(lane.top()))
        painter.setPen(QColor("#ff7f0e"))
        painter.drawText(
            QRectF(4, lane.top(), LABEL_W - 8, lane.height()),
            Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
            "Speed",
        )
        painter.setPen(muted)
        for mark in (1.0, 30.0, 50.0, 100.0):
            if mark < STORY_SPEED_MIN or mark > STORY_SPEED_MAX:
                continue
            y = self._speed_to_y(mark, lane)
            painter.setPen(QPen(grid, 1))
            painter.drawLine(int(lane.left()), int(y), int(lane.right()), int(y))
            painter.setPen(muted)
            painter.drawText(int(lane.left()) + 2, int(y) - 2, f"{mark:.0f}x")

        pts = self._envelope.sorted_points()
        color = QColor("#ff7f0e")
        if pts:
            poly = QPolygonF()
            first = pts[0]
            last = pts[-1]
            poly.append(QPointF(self._sec_to_x(0.0, track, duration), self._speed_to_y(first.speed, lane)))
            for point in pts:
                poly.append(
                    QPointF(
                        self._sec_to_x(point.time_sec, track, duration),
                        self._speed_to_y(point.speed, lane),
                    )
                )
            poly.append(
                QPointF(
                    self._sec_to_x(duration, track, duration),
                    self._speed_to_y(last.speed, lane),
                )
            )
            painter.setPen(QPen(color, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawPolyline(poly)
            for point in pts:
                cx = self._sec_to_x(point.time_sec, track, duration)
                cy = self._speed_to_y(point.speed, lane)
                r = SPEED_POINT_R + (2 if point.point_id == self._selected_speed_id else 0)
                painter.setBrush(color if point.point_id != self._selected_speed_id else QColor("#fff7ed"))
                painter.setPen(QPen(color.darker(120), 1))
                painter.drawEllipse(QPointF(cx, cy), r, r)
        else:
            y = self._speed_to_y(STORY_SPEED_DEFAULT, lane)
            painter.setPen(QPen(color, 1, Qt.PenStyle.DashLine))
            painter.drawLine(int(lane.left()), int(y), int(lane.right()), int(y))

    def _paint_ruler(
        self,
        painter: QPainter,
        track: QRectF,
        duration: float,
        muted: QColor,
        grid: QColor,
        text_color: QColor,
    ) -> None:
        """Time axis under the pin lanes and speed graph, so labels don't cover the clips."""
        top = self._ruler_top()
        painter.setPen(QPen(grid, 1))
        painter.drawLine(LABEL_W, top, self.width(), top)
        painter.setFont(QFont(self.font().family(), 9))
        for mark_sec, major in self._ruler_marks(duration):
            x = int(self._sec_to_x(mark_sec, track, duration))
            tick_len = 8 if major else 4
            painter.setPen(
                QPen(
                    grid if not major else QColor(text_color.red(), text_color.green(), text_color.blue(), 70),
                    1,
                )
            )
            painter.drawLine(x, top, x, top + tick_len)
            if major:
                painter.setPen(muted)
                painter.drawText(x + 2, top + tick_len + 12, format_story_time(mark_sec))

    def mousePressEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self.setFocus()
        x, y = event.position().x(), event.position().y()
        if x < LABEL_W:
            return
        if self._y_on_ruler(y):
            self.seek_requested.emit(self._x_to_sec(x))
            self._drag_mode = "seek"
            return

        if self._speed_lane_rect().contains(x, y):
            hit = self._hit_speed_point(x, y)
            if hit is not None:
                self._selected_speed_id = hit.point_id
                self._selected_id = None
                self._drag_mode = "speed"
                self._drag_speed_id = hit.point_id
                self.update()
                return
            point = self._envelope.add_point(self._x_to_sec(x), self._y_to_speed(y))
            self._selected_speed_id = point.point_id
            self._selected_id = None
            self._drag_mode = "speed"
            self._drag_speed_id = point.point_id
            self.clips_edited.emit()
            self.update()
            return

        pin = self._pin_at_y(y)
        if pin is None:
            return
        hit = self._hit_clip(x, pin)
        if hit is not None:
            clip, zone = hit
            self._selected_id = clip.clip_id
            self._selected_speed_id = None
            self._drag_clip_id = clip.clip_id
            self._drag_origin_sec = self._x_to_sec(x)
            self._drag_clip_start = clip.start_sec
            self._drag_clip_end = clip.end_sec
            self._drag_mode = zone
            self.update()
            return

        self._selected_id = None
        self._selected_speed_id = None
        self._drag_mode = "create"
        self._create_pin = pin
        t = self._x_to_sec(x)
        self._create_start = t
        self._create_end = t
        self.update()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        x = event.position().x()
        if self._drag_mode == "seek":
            self.seek_requested.emit(self._x_to_sec(x))
            return
        if self._drag_mode == "speed" and self._drag_speed_id:
            y = event.position().y()
            self._envelope.update_point(self._drag_speed_id, self._x_to_sec(x), self._y_to_speed(y))
            self.update()
            return
        if self._drag_mode == "create" and self._create_pin is not None:
            self._create_end = self._x_to_sec(x)
            self.update()
            return
        if self._drag_mode in ("move", "left", "right") and self._drag_clip_id:
            now = self._x_to_sec(x)
            delta = now - self._drag_origin_sec
            start, end = self._drag_clip_start, self._drag_clip_end
            if self._drag_mode == "move":
                length = end - start
                start = max(0.0, min(start + delta, self._cues.duration_sec - length))
                end = start + length
            elif self._drag_mode == "left":
                start = min(end - STORY_MIN_CLIP_SEC, max(0.0, start + delta))
            else:
                end = max(start + STORY_MIN_CLIP_SEC, min(self._cues.duration_sec, end + delta))
            self._cues.update_clip(self._drag_clip_id, start, end, merge=False)
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._drag_mode == "create" and self._create_pin is not None:
            start = min(self._create_start, self._create_end)
            end = max(self._create_start, self._create_end)
            if end - start < STORY_MIN_CLIP_SEC:
                end = min(self._cues.duration_sec, start + DEFAULT_CLICK_CLIP_SEC)
            clip = self._cues.add_clip(self._create_pin, start, end)
            self._selected_id = clip.clip_id if clip else None
            self.clips_edited.emit()
        elif self._drag_mode in ("move", "left", "right") and self._drag_clip_id:
            clip = self._cues.clip_by_id(self._drag_clip_id)
            if clip is not None:
                self._cues.update_clip(clip.clip_id, clip.start_sec, clip.end_sec, merge=True)
            self.clips_edited.emit()
        elif self._drag_mode == "speed":
            self.clips_edited.emit()
        self._drag_mode = None
        self._drag_clip_id = None
        self._drag_speed_id = None
        self._create_pin = None
        self.update()

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        x, y = event.position().x(), event.position().y()
        if x < LABEL_W or self._y_on_ruler(y):
            return
        hit = self._hit_speed_point(x, y)
        if hit is not None:
            self._envelope.remove_point(hit.point_id)
            if self._selected_speed_id == hit.point_id:
                self._selected_speed_id = None
            self.clips_edited.emit()
            self.update()
            return
        pin = self._pin_at_y(y)
        if pin is None:
            return
        start = self._x_to_sec(x)
        end = min(self._cues.duration_sec, start + DEFAULT_CLICK_CLIP_SEC)
        clip = self._cues.add_clip(pin, start, end)
        self._selected_id = clip.clip_id if clip else None
        self.clips_edited.emit()
        self.update()

    def _plot_width(self) -> float:
        return max(1.0, self.width() - LABEL_W - 4)

    def _ruler_top(self) -> int:
        return max(0, self.height() - RULER_H)

    def _y_on_ruler(self, y: float) -> bool:
        return y >= self._ruler_top()

    def _track_rect(self) -> QRectF:
        return QRectF(LABEL_W, 0, self._plot_width(), self._cues.pin_count * LANE_H)

    def _speed_lane_rect(self) -> QRectF:
        y = self._cues.pin_count * LANE_H
        # Leftover height belongs to the speed graph. Forcing SPEED_LANE_H here
        # draws that lane over the ruler once the splitter shrinks the panel.
        height = max(0.0, float(self._ruler_top() - y))
        return QRectF(LABEL_W, y, self._plot_width(), height)

    def _speed_to_y(self, speed: float, lane: QRectF) -> float:
        lo, hi = STORY_SPEED_MIN, STORY_SPEED_MAX
        t = (clamp_speed(speed) - lo) / max(1e-6, hi - lo)
        pad = 8.0
        return lane.bottom() - pad - t * max(1.0, lane.height() - 2 * pad)

    def _y_to_speed(self, y: float) -> float:
        lane = self._speed_lane_rect()
        lo, hi = STORY_SPEED_MIN, STORY_SPEED_MAX
        pad = 8.0
        inner = max(1.0, lane.height() - 2 * pad)
        t = (lane.bottom() - pad - y) / inner
        return lo + max(0.0, min(1.0, t)) * (hi - lo)

    def _hit_speed_point(self, x: float, y: float) -> Optional[SpeedPoint]:
        track = self._track_rect()
        lane = self._speed_lane_rect()
        duration = max(1.0, self._cues.duration_sec)
        best: Optional[SpeedPoint] = None
        best_d = SPEED_HIT_PX
        for point in self._envelope.points:
            px = self._sec_to_x(point.time_sec, track, duration)
            py = self._speed_to_y(point.speed, lane)
            dist = ((x - px) ** 2 + (y - py) ** 2) ** 0.5
            if dist <= best_d:
                best_d = dist
                best = point
        return best

    def _sec_to_x(self, sec: float, track: QRectF, duration: float) -> float:
        return track.left() + (max(0.0, min(sec, duration)) / duration) * track.width()

    def _x_to_sec(self, x: float) -> float:
        track = self._track_rect()
        duration = max(1.0, self._cues.duration_sec)
        ratio = (x - track.left()) / track.width()
        return max(0.0, min(duration, ratio * duration))

    def _pin_at_y(self, y: float) -> Optional[int]:
        if y < 0 or self._y_on_ruler(y):
            return None
        pin = int(y / LANE_H)
        if 0 <= pin < self._cues.pin_count:
            return pin
        return None

    def _clip_rect(self, clip: PinClip, track: QRectF, duration: float) -> QRectF:
        x0 = self._sec_to_x(clip.start_sec, track, duration)
        x1 = self._sec_to_x(clip.end_sec, track, duration)
        y = clip.pin_index * LANE_H + 3
        return QRectF(x0, y, max(4.0, x1 - x0), LANE_H - 6)

    def _hit_clip(self, x: float, pin: int) -> Optional[Tuple[PinClip, str]]:
        track = self._track_rect()
        duration = max(1.0, self._cues.duration_sec)
        for clip in reversed(self._cues.clips):
            if clip.pin_index != pin:
                continue
            rect = self._clip_rect(clip, track, duration)
            if not (rect.left() - HANDLE_PX <= x <= rect.right() + HANDLE_PX):
                continue
            if x <= rect.left() + HANDLE_PX:
                return clip, "left"
            if x >= rect.right() - HANDLE_PX:
                return clip, "right"
            return clip, "move"
        return None

    def _ruler_marks(self, duration: float) -> list[Tuple[float, bool]]:
        if duration <= 60:
            step = 10.0
            major_every = 30.0
        elif duration <= 300:
            step = 15.0
            major_every = 60.0
        elif duration <= 1200:
            step = 30.0
            major_every = 60.0
        else:
            step = 60.0
            major_every = 300.0
        marks = []
        t = 0.0
        while t <= duration + 0.001:
            marks.append((t, t % major_every < 0.001 or abs((t % major_every) - major_every) < 0.001))
            t += step
        return marks


def _toolbar_button(
    text: str,
    on_click,
    tooltip: str | None = None,
) -> QPushButton:
    """Compact toolbar button; section stretches absorb spare width."""
    button = QPushButton(text)
    button.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
    if tooltip:
        button.setToolTip(tooltip)
    button.clicked.connect(on_click)
    return button


def _toolbar_section(alignment: Qt.AlignmentFlag) -> tuple[QWidget, QHBoxLayout]:
    """Equal-width toolbar zone; widgets pack to the given edge or center."""
    host = QWidget()
    row = QHBoxLayout(host)
    row.setContentsMargins(0, 0, 0, 0)
    row.setSpacing(6)
    row.setAlignment(alignment)
    return host, row


class StoryTimelinePanel(QWidget):
    """Toolbar + two-lane editor and speed envelope for one Croissant station."""

    play_clicked = Signal()
    pause_clicked = Signal()
    stop_clicked = Signal()
    seek_requested = Signal(float)
    duration_changed = Signal(float)
    clips_changed = Signal()
    sync_dy_toggled = Signal(bool)
    speed_edited = Signal(float)
    speed_edit_finished = Signal()

    def __init__(
        self,
        cues: PinCueList,
        clock: StoryClock,
        envelope: SpeedEnvelope,
        parent=None,
        *,
        title: str = "Croissant",
        pin_labels: Optional[Sequence[str]] = None,
        lane_color_offset: int = 0,
    ):
        super().__init__(parent)
        self._cues = cues
        self._clock = clock
        self._envelope = envelope
        self._title = title
        self._pin_labels = pin_labels
        self._lane_color_offset = lane_color_offset
        self._duration_updating = False
        self._speed_updating = False
        self._speed_anchor_id: Optional[str] = None
        # Fills the station cell; wrap_panel only adds the outer margin.
        # Height floor comes from the canvas so the splitter above can move.
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self._setup_ui()
        self._sync_duration_edit()
        self.update_time_display(clock.get_current_sec())
        self.update_button_states(clock.get_state())
        self.update_speed_display(envelope.speed_at(clock.get_current_sec()))

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        layout.addWidget(panel_title(f"<b>{self._title}</b>"))

        controls = QHBoxLayout()
        controls.setContentsMargins(0, 0, 0, 0)
        controls.setSpacing(8)

        transport, transport_row = _toolbar_section(
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
        )
        self.play_button = _toolbar_button("Play", self.play_clicked.emit)
        self.pause_button = _toolbar_button("Pause", self.pause_clicked.emit)
        self.stop_button = _toolbar_button("Stop", self.stop_clicked.emit)
        transport_row.addWidget(self.play_button)
        transport_row.addWidget(self.pause_button)
        transport_row.addWidget(self.stop_button)
        controls.addWidget(transport, 1)

        middle, middle_row = _toolbar_section(
            Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter
        )
        self.time_label = QLabel("0:00 / 14:30")
        self.time_label.setMinimumWidth(90)
        middle_row.addWidget(self.time_label)
        self.speed_spin = QDoubleSpinBox()
        self.speed_spin.setRange(STORY_SPEED_MIN, STORY_SPEED_MAX)
        self.speed_spin.setDecimals(0)
        self.speed_spin.setSingleStep(2)
        self.speed_spin.setSuffix("x")
        self.speed_spin.setKeyboardTracking(True)
        self.speed_spin.setMinimumWidth(88)
        self.speed_spin.setToolTip(
            "Playback speed at this playhead. Applied as you type or click the arrows."
        )
        self.speed_spin.valueChanged.connect(self._on_speed_spin_changed)
        self.speed_spin.editingFinished.connect(self.speed_edit_finished.emit)
        middle_row.addWidget(self.speed_spin)
        middle_row.addWidget(QLabel("Duration:"))
        self.duration_edit = QTimeEdit()
        self.duration_edit.setDisplayFormat("mm:ss")
        self.duration_edit.setTime(seconds_to_qtime(self._cues.duration_sec))
        self.duration_edit.timeChanged.connect(self._on_duration_changed)
        middle_row.addWidget(self.duration_edit)
        self.sync_dy_checkbox = QCheckBox("Sync DY Play/Stop")
        self.sync_dy_checkbox.setChecked(True)
        self.sync_dy_checkbox.setToolTip(
            "Link this station's clock to its DY: Play/Stop sends DY,PLAY / DY,STOP "
            "to that LilyGO only, and the physical buttons start or stop only this timeline."
        )
        self.sync_dy_checkbox.toggled.connect(self.sync_dy_toggled.emit)
        middle_row.addWidget(self.sync_dy_checkbox)
        controls.addWidget(middle, 1)

        clears, clears_row = _toolbar_section(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.clear_button = _toolbar_button("Clear clips", self._on_clear_clips)
        self.clear_speed_button = _toolbar_button(
            "Clear speed",
            self._on_clear_speed,
            "Remove this station's speed breakpoints; waveform Speed box takes over",
        )
        clears_row.addWidget(self.clear_button)
        clears_row.addWidget(self.clear_speed_button)
        controls.addWidget(clears, 1)

        layout.addLayout(controls)

        self.canvas = StoryTimelineCanvas(
            self._cues,
            self._clock,
            self._envelope,
            pin_labels=self._pin_labels,
            lane_color_offset=self._lane_color_offset,
        )
        self.canvas.seek_requested.connect(self.seek_requested.emit)
        self.canvas.clips_edited.connect(self.clips_changed.emit)
        layout.addWidget(self.canvas, 1)

    def sync_dy_enabled(self) -> bool:
        return self.sync_dy_checkbox.isChecked()

    def set_sync_dy(self, enabled: bool) -> None:
        self.sync_dy_checkbox.setChecked(bool(enabled))

    def update_time_display(self, current_sec: float) -> None:
        self.time_label.setText(
            f"{format_story_time(current_sec)} / {format_story_time(self._cues.duration_sec)}"
        )
        self.canvas.update()

    def update_button_states(self, state: str) -> None:
        playing = state == "playing"
        self.play_button.setEnabled(not playing)
        self.pause_button.setEnabled(playing)
        self.stop_button.setEnabled(state != "stopped")

    def _sync_duration_edit(self) -> None:
        self._duration_updating = True
        self.duration_edit.setTime(seconds_to_qtime(self._cues.duration_sec))
        self._duration_updating = False

    def _on_duration_changed(self, value: QTime) -> None:
        if self._duration_updating:
            return
        sec = max(1.0, qtime_to_seconds(value))
        self.duration_changed.emit(sec)

    def speed_input_active(self) -> bool:
        return self.speed_spin.hasFocus()

    def speed_input_value(self) -> float:
        return float(self.speed_spin.value())

    def speed_anchor_id(self) -> Optional[str]:
        return self._speed_anchor_id

    def set_speed_anchor_id(self, point_id: Optional[str]) -> None:
        self._speed_anchor_id = point_id

    def _on_speed_spin_changed(self, value: float) -> None:
        if self._speed_updating:
            return
        self.speed_edited.emit(float(value))

    def update_speed_display(self, speed: float) -> None:
        # Leave the field alone while it is being edited, or the playhead tick
        # overwrites the digits before Enter.
        if self.speed_spin.hasFocus():
            self.canvas.update()
            return
        self._speed_updating = True
        self.speed_spin.setValue(round(float(speed)))
        self._speed_updating = False
        self.canvas.update()

    def _on_clear_clips(self) -> None:
        self.canvas.set_selected_clip_id(None)
        self._cues.clear()
        self.clips_changed.emit()
        self.canvas.update()

    def _on_clear_speed(self) -> None:
        self._speed_anchor_id = None
        self._envelope.clear()
        self.clips_changed.emit()
        self.update_speed_display(STORY_SPEED_DEFAULT)
        self.canvas.update()

    def reload_from_cues(self) -> None:
        self._sync_duration_edit()
        self.update_time_display(self._clock.get_current_sec())
        self.canvas.update()
