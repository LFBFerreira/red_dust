"""On/off clips for the Dust Devil story timeline (Pin_A .. Pin_F)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from PySide6.QtCore import QObject, Signal

from settings import STORY_DURATION_SEC, STORY_MIN_CLIP_SEC, STORY_PIN_COUNT


@dataclass
class PinClip:
    clip_id: str
    pin_index: int
    start_sec: float
    end_sec: float


class PinCueList(QObject):
    """Clips that turn individual pin slots on during the story clock."""

    changed = Signal()

    def __init__(
        self,
        duration_sec: float = STORY_DURATION_SEC,
        pin_count: int = STORY_PIN_COUNT,
        parent=None,
    ):
        super().__init__(parent)
        self._duration_sec = max(1.0, float(duration_sec))
        self._pin_count = max(1, int(pin_count))
        self._clips: List[PinClip] = []

    @property
    def duration_sec(self) -> float:
        return self._duration_sec

    @property
    def pin_count(self) -> int:
        return self._pin_count

    @property
    def clips(self) -> List[PinClip]:
        return list(self._clips)

    def has_any_clips(self) -> bool:
        return bool(self._clips)

    def is_on(self, pin_index: int, time_sec: float) -> bool:
        """True if a clip on ``pin_index`` covers ``time_sec`` (end is exclusive)."""
        if pin_index < 0 or pin_index >= self._pin_count:
            return False
        t = float(time_sec)
        for clip in self._clips:
            if clip.pin_index != pin_index:
                continue
            if clip.start_sec <= t < clip.end_sec:
                return True
        return False

    def clip_by_id(self, clip_id: str) -> Optional[PinClip]:
        for clip in self._clips:
            if clip.clip_id == clip_id:
                return clip
        return None

    def set_duration(self, duration_sec: float) -> None:
        self._duration_sec = max(1.0, float(duration_sec))
        kept: List[PinClip] = []
        for clip in self._clips:
            start = max(0.0, min(clip.start_sec, self._duration_sec))
            end = max(0.0, min(clip.end_sec, self._duration_sec))
            if end - start < STORY_MIN_CLIP_SEC:
                continue
            kept.append(PinClip(clip.clip_id, clip.pin_index, start, end))
        self._clips = kept
        self.changed.emit()

    def add_clip(self, pin_index: int, start_sec: float, end_sec: float) -> Optional[PinClip]:
        clip = self._normalized_clip(str(uuid.uuid4()), pin_index, start_sec, end_sec)
        if clip is None:
            return None
        self._clips.append(clip)
        self._merge_overlaps(pin_index)
        self.changed.emit()
        return self._clip_covering(pin_index, clip.start_sec)

    def remove_clip(self, clip_id: str) -> bool:
        before = len(self._clips)
        self._clips = [c for c in self._clips if c.clip_id != clip_id]
        if len(self._clips) == before:
            return False
        self.changed.emit()
        return True

    def clear(self) -> None:
        if not self._clips:
            return
        self._clips = []
        self.changed.emit()

    def update_clip(
        self,
        clip_id: str,
        start_sec: float,
        end_sec: float,
        merge: bool = True,
    ) -> Optional[PinClip]:
        existing = self.clip_by_id(clip_id)
        if existing is None:
            return None
        clip = self._normalized_clip(clip_id, existing.pin_index, start_sec, end_sec)
        if clip is None:
            return existing
        self._clips = [clip if c.clip_id == clip_id else c for c in self._clips]
        if merge:
            self._merge_overlaps(existing.pin_index)
        self.changed.emit()
        return self.clip_by_id(clip_id) or self._clip_covering(existing.pin_index, clip.start_sec)

    def replace_all(self, clips: List[PinClip], duration_sec: Optional[float] = None) -> None:
        if duration_sec is not None:
            self._duration_sec = max(1.0, float(duration_sec))
        self._clips = []
        for raw in clips:
            clip = self._normalized_clip(
                raw.clip_id or str(uuid.uuid4()),
                raw.pin_index,
                raw.start_sec,
                raw.end_sec,
            )
            if clip is not None:
                self._clips.append(clip)
        for pin in range(self._pin_count):
            self._merge_overlaps(pin)
        self.changed.emit()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "duration_sec": self._duration_sec,
            "clips": [
                {
                    "clip_id": c.clip_id,
                    "pin_index": c.pin_index,
                    "start_sec": c.start_sec,
                    "end_sec": c.end_sec,
                }
                for c in self._clips
            ],
        }

    def load_dict(self, data: Dict[str, Any]) -> None:
        duration = float(data.get("duration_sec", STORY_DURATION_SEC))
        raw_clips: List[PinClip] = []
        for item in data.get("clips") or []:
            if not isinstance(item, dict):
                continue
            raw_clips.append(
                PinClip(
                    clip_id=str(item.get("clip_id") or uuid.uuid4()),
                    pin_index=int(item.get("pin_index", 0)),
                    start_sec=float(item.get("start_sec", 0.0)),
                    end_sec=float(item.get("end_sec", 0.0)),
                )
            )
        self.replace_all(raw_clips, duration_sec=duration)

    def _normalized_clip(
        self, clip_id: str, pin_index: int, start_sec: float, end_sec: float
    ) -> Optional[PinClip]:
        if pin_index < 0 or pin_index >= self._pin_count:
            return None
        start = float(start_sec)
        end = float(end_sec)
        if end < start:
            start, end = end, start
        start = max(0.0, min(start, self._duration_sec))
        end = max(0.0, min(end, self._duration_sec))
        if end - start < STORY_MIN_CLIP_SEC:
            return None
        return PinClip(clip_id, pin_index, start, end)

    def _clip_covering(self, pin_index: int, time_sec: float) -> Optional[PinClip]:
        for clip in self._clips:
            if clip.pin_index == pin_index and clip.start_sec <= time_sec < clip.end_sec:
                return clip
        return None

    def _merge_overlaps(self, pin_index: int) -> None:
        lane = sorted(
            [c for c in self._clips if c.pin_index == pin_index],
            key=lambda c: c.start_sec,
        )
        others = [c for c in self._clips if c.pin_index != pin_index]
        merged: List[PinClip] = []
        for clip in lane:
            if not merged or clip.start_sec > merged[-1].end_sec:
                merged.append(clip)
                continue
            prev = merged[-1]
            merged[-1] = PinClip(
                prev.clip_id,
                pin_index,
                prev.start_sec,
                max(prev.end_sec, clip.end_sec),
            )
        self._clips = others + merged
