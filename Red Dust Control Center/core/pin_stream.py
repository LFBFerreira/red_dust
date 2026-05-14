"""Pin-slot streaming rows for multi-channel interactive objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, AbstractSet

from settings import MAX_PIN_SLOTS, PIN_SLOT_LABELS


@dataclass(frozen=True)
class PinStreamRow:
    """One waveform channel mapped to a pin slot (wire order = list order)."""

    row_id: str
    channel_id: str
    remap_min: float
    remap_max: float
    slot_index: int


def slot_label_for_index(slot_index: int) -> str:
    if 0 <= slot_index < len(PIN_SLOT_LABELS):
        return PIN_SLOT_LABELS[slot_index]
    return f"Pin_?"


def remap_normalized(normalized_01: float, lo: float, hi: float) -> float:
    normalized_01 = max(0.0, min(1.0, normalized_01))
    if hi == lo:
        return lo
    return lo + (normalized_01 * (hi - lo))


def filter_pin_rows_by_channels(
    rows: List[PinStreamRow], allowed_channel_ids: AbstractSet[str]
) -> List[PinStreamRow]:
    """Keep only rows whose ``channel_id`` is in ``allowed_channel_ids``; renumber ``slot_index``."""
    kept = [r for r in rows if r.channel_id in allowed_channel_ids]
    return [
        PinStreamRow(r.row_id, r.channel_id, r.remap_min, r.remap_max, i)
        for i, r in enumerate(kept[:MAX_PIN_SLOTS])
    ]


def pin_rows_from_dicts(rows: List[Dict[str, Any]]) -> List[PinStreamRow]:
    out: List[PinStreamRow] = []
    for i, r in enumerate(rows[:MAX_PIN_SLOTS]):
        out.append(
            PinStreamRow(
                row_id=str(r["row_id"]),
                channel_id=str(r["channel_id"]),
                remap_min=float(r.get("remap_min", 0.0)),
                remap_max=float(r.get("remap_max", 1.0)),
                slot_index=int(r.get("slot_index", i)),
            )
        )
    return out


def pin_rows_to_dicts(rows: List[PinStreamRow]) -> List[Dict[str, Any]]:
    return [
        {
            "row_id": r.row_id,
            "channel_id": r.channel_id,
            "remap_min": r.remap_min,
            "remap_max": r.remap_max,
            "slot_index": r.slot_index,
        }
        for r in rows
    ]
