"""
Abstract base class for interactive objects supporting different communication protocols.

Multi-pin streaming: each object has an ordered list of PinStreamRow entries.
Per tick, normalized values (0..1) per waveform channel are remapped and sent as
N floats (Pin_A .. in row order) plus one ISO8601 UTC timestamp string.

Firmware contract: OSC message at base address, typetag (f * N)(s); Serial line
v1,...,vN,timestamp\\n — see core/osc_object.py and core/serial_object.py.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional, Tuple

from obspy import UTCDateTime

from core.pin_stream import PinStreamRow, remap_normalized
from settings import MAX_PIN_SLOTS


class InteractiveObject(ABC):
    """Abstract base class for interactive objects."""

    def __init__(self, object_id: str):
        """
        Args:
            object_id: Stable unique id (e.g. UUID) for this object
        """
        self.object_id = object_id
        self.pin_rows: List[PinStreamRow] = []
        self.streaming_enabled = False

    @property
    def name(self) -> str:
        """Backward-compatible alias for session and logging."""
        return self.object_id

    @property
    @abstractmethod
    def communication_type(self) -> str:
        """Return the communication type (e.g., 'OSC', 'Serial')."""
        pass

    def set_pin_rows(self, rows: List[PinStreamRow]) -> None:
        self.pin_rows = list(rows[:MAX_PIN_SLOTS])

    @staticmethod
    def remap_for_row(normalized_value: float, row: PinStreamRow) -> float:
        return remap_normalized(normalized_value, row.remap_min, row.remap_max)

    @abstractmethod
    def send_pin_bundle(
        self,
        ordered_normalized: List[Tuple[str, float]],
        timestamp: UTCDateTime,
    ) -> Optional[Dict[str, float]]:
        """
        Send one frame: ordered_normalized is (row_id, 0..1) in pin slot order;
        length must match len(self.pin_rows).

        Returns:
            Map row_id -> normalized (0..1) for UI when send succeeds, else None.
        """
        pass

    @abstractmethod
    def close(self) -> None:
        """Close the connection."""
        pass

    @abstractmethod
    def get_config_dict(self) -> dict:
        """
        Get configuration dictionary for serialization.

        Returns:
            Dictionary with all configuration parameters
        """
        pass
