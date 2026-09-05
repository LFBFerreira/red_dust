"""Story-time → waveform playback-speed envelope (polyline breakpoints)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Signal

from settings import (
    STORY_DURATION_SEC,
    STORY_SPEED_DEFAULT,
    STORY_SPEED_MAX,
    STORY_SPEED_MIN,
)


@dataclass
class SpeedPoint:
    point_id: str
    time_sec: float
    speed: float


def clamp_speed(speed: float) -> float:
    return max(STORY_SPEED_MIN, min(STORY_SPEED_MAX, float(speed)))


class SpeedEnvelope(QObject):
    """Linear breakpoints: empty envelope leaves the manual Speed control alone."""

    changed = Signal()

    def __init__(self, duration_sec: float = STORY_DURATION_SEC, parent=None):
        super().__init__(parent)
        self._duration_sec = max(1.0, float(duration_sec))
        self._points: List[SpeedPoint] = []

    @property
    def duration_sec(self) -> float:
        return self._duration_sec

    @property
    def points(self) -> List[SpeedPoint]:
        return list(self._points)

    def has_points(self) -> bool:
        return bool(self._points)

    def sorted_points(self) -> List[SpeedPoint]:
        return sorted(self._points, key=lambda p: (p.time_sec, p.point_id))

    def point_by_id(self, point_id: str) -> Optional[SpeedPoint]:
        for point in self._points:
            if point.point_id == point_id:
                return point
        return None

    def speed_at(self, time_sec: float) -> float:
        """Interpolate speed at story time. Empty → default 1x. Hold before first / after last."""
        pts = self.sorted_points()
        if not pts:
            return STORY_SPEED_DEFAULT
        t = max(0.0, min(float(time_sec), self._duration_sec))
        if t <= pts[0].time_sec:
            return pts[0].speed
        if t >= pts[-1].time_sec:
            return pts[-1].speed
        for i in range(1, len(pts)):
            left, right = pts[i - 1], pts[i]
            if t > right.time_sec:
                continue
            dt = right.time_sec - left.time_sec
            if dt < 1e-4:
                return right.speed
            u = (t - left.time_sec) / dt
            return clamp_speed(left.speed + u * (right.speed - left.speed))
        return pts[-1].speed

    def set_duration(self, duration_sec: float) -> None:
        self._duration_sec = max(1.0, float(duration_sec))
        kept: List[SpeedPoint] = []
        for point in self._points:
            t = max(0.0, min(point.time_sec, self._duration_sec))
            kept.append(SpeedPoint(point.point_id, t, clamp_speed(point.speed)))
        self._points = kept
        self.changed.emit()

    def add_point(self, time_sec: float, speed: float) -> SpeedPoint:
        point = SpeedPoint(
            str(uuid.uuid4()),
            max(0.0, min(float(time_sec), self._duration_sec)),
            clamp_speed(round(float(speed), 1)),
        )
        self._points.append(point)
        self.changed.emit()
        return point

    def update_point(
        self, point_id: str, time_sec: float, speed: float
    ) -> Optional[SpeedPoint]:
        existing = self.point_by_id(point_id)
        if existing is None:
            return None
        updated = SpeedPoint(
            point_id,
            max(0.0, min(float(time_sec), self._duration_sec)),
            clamp_speed(round(float(speed), 1)),
        )
        self._points = [updated if p.point_id == point_id else p for p in self._points]
        self.changed.emit()
        return updated

    def remove_point(self, point_id: str) -> bool:
        before = len(self._points)
        self._points = [p for p in self._points if p.point_id != point_id]
        if len(self._points) == before:
            return False
        self.changed.emit()
        return True

    def clear(self) -> None:
        if not self._points:
            return
        self._points = []
        self.changed.emit()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "points": [
                {
                    "point_id": p.point_id,
                    "time_sec": p.time_sec,
                    "speed": p.speed,
                }
                for p in self.sorted_points()
            ]
        }

    def load_dict(self, data: Dict[str, Any]) -> None:
        raw = data.get("speed_points") or data.get("points") or []
        loaded: List[SpeedPoint] = []
        for item in raw:
            if not isinstance(item, dict):
                continue
            loaded.append(
                SpeedPoint(
                    point_id=str(item.get("point_id") or uuid.uuid4()),
                    time_sec=float(item.get("time_sec", 0.0)),
                    speed=clamp_speed(item.get("speed", STORY_SPEED_DEFAULT)),
                )
            )
        self._points = loaded
        self.changed.emit()
