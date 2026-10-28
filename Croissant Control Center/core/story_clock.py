"""Independent story clock for one Croissant station (0 .. duration seconds)."""

from __future__ import annotations

from time import time as wall_time

from PySide6.QtCore import QObject, QTimer, Signal

from settings import STORY_DURATION_SEC


class StoryClock(QObject):
    """Plays a linear story timeline, independent of seismic waveform playback."""

    time_changed = Signal(float)
    state_changed = Signal(str)
    finished = Signal()

    def __init__(self, duration_sec: float = STORY_DURATION_SEC, parent=None):
        super().__init__(parent)
        self._duration_sec = max(1.0, float(duration_sec))
        self._current_sec = 0.0
        self._state = "stopped"
        self._play_wall_start = None
        self._play_story_start = None

        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)
        self._timer.setInterval(16)

    @property
    def duration_sec(self) -> float:
        return self._duration_sec

    def get_current_sec(self) -> float:
        return self._current_sec

    def get_state(self) -> str:
        return self._state

    def set_duration(self, duration_sec: float) -> None:
        self._duration_sec = max(1.0, float(duration_sec))
        if self._current_sec > self._duration_sec:
            self.seek(self._duration_sec)

    def start(self) -> None:
        if self._current_sec >= self._duration_sec:
            self._current_sec = 0.0
            self.time_changed.emit(self._current_sec)
        self._play_wall_start = wall_time()
        self._play_story_start = self._current_sec
        self._state = "playing"
        self._timer.start()
        self.state_changed.emit(self._state)

    def pause(self) -> None:
        if self._state != "playing":
            return
        self._timer.stop()
        self._state = "paused"
        self._play_wall_start = None
        self._play_story_start = None
        self.state_changed.emit(self._state)

    def stop(self) -> None:
        self._timer.stop()
        self._current_sec = 0.0
        self._state = "stopped"
        self._play_wall_start = None
        self._play_story_start = None
        self.state_changed.emit(self._state)
        self.time_changed.emit(self._current_sec)

    def seek(self, time_sec: float) -> None:
        t = max(0.0, min(float(time_sec), self._duration_sec))
        self._current_sec = t
        if self._state == "playing":
            self._play_wall_start = wall_time()
            self._play_story_start = self._current_sec
        self.time_changed.emit(self._current_sec)

    def _tick(self) -> None:
        if self._play_wall_start is None or self._play_story_start is None:
            return
        elapsed = wall_time() - self._play_wall_start
        nxt = self._play_story_start + elapsed
        if nxt >= self._duration_sec:
            self._current_sec = self._duration_sec
            self._timer.stop()
            self._state = "stopped"
            self._play_wall_start = None
            self._play_story_start = None
            self.time_changed.emit(self._current_sec)
            self.state_changed.emit(self._state)
            self.finished.emit()
            return
        self._current_sec = nxt
        self.time_changed.emit(self._current_sec)
