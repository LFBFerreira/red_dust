"""Pin-slot streaming rows for multi-channel interactive objects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, AbstractSet

from settings import MAX_PIN_SLOTS, PIN_SLOT_LABELS


@dataclass(frozen=True)
class PinStreamRow:
    """One waveform channel mapped to a physical pin slot (wire index ``slot_index``).

    ``remap_min``/``remap_max`` clamp the output after ``sample * remap_scale``.
    """

    row_id: str
    channel_id: str
    remap_min: float
    remap_max: float
    remap_scale: float
    slot_index: int


def slot_label_for_index(slot_index: int) -> str:
    if 0 <= slot_index < len(PIN_SLOT_LABELS):
        return PIN_SLOT_LABELS[slot_index]
    return f"Pin_?"


def remap_normalized(
    normalized_01: float, lo: float, hi: float, remap_scale: float = 1.0
) -> float:
    """
    ``normalized_01`` is clamped to [0, 1], multiplied by ``remap_scale``, then
    clamped to ``[lo, hi]`` (``lo``/``hi`` are output limits only, not a linear remap).
    OSC/Serial may clamp again to the wire range [0, 1].
    """
    normalized_01 = max(0.0, min(1.0, normalized_01))
    if lo > hi:
        lo, hi = hi, lo
    scaled = normalized_01 * remap_scale
    return max(lo, min(hi, scaled))


def filter_pin_rows_by_channels(
    rows: List[PinStreamRow], allowed_channel_ids: AbstractSet[str]
) -> List[PinStreamRow]:
    """Keep only rows whose ``channel_id`` is in ``allowed_channel_ids``; preserve ``slot_index``."""
    kept = [r for r in rows if r.channel_id in allowed_channel_ids]
    return [
        PinStreamRow(
            r.row_id,
            r.channel_id,
            r.remap_min,
            r.remap_max,
            r.remap_scale,
            r.slot_index,
        )
        for r in kept[:MAX_PIN_SLOTS]
    ]


def wire_bundle_width(rows: List[PinStreamRow]) -> int:
    """Number of floats on the wire: ``max(slot_index)+1``, capped (empty → 0)."""
    if not rows:
        return 0
    return min(MAX_PIN_SLOTS, max(int(r.slot_index) for r in rows) + 1)


def pin_rows_from_dicts(rows: List[Dict[str, Any]]) -> List[PinStreamRow]:
    out: List[PinStreamRow] = []
    for i, r in enumerate(rows[:MAX_PIN_SLOTS]):
        out.append(
            PinStreamRow(
                row_id=str(r["row_id"]),
                channel_id=str(r["channel_id"]),
                remap_min=float(r.get("remap_min", 0.0)),
                remap_max=float(r.get("remap_max", 1.0)),
                remap_scale=float(r.get("remap_scale", 1.0)),
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
            "remap_scale": r.remap_scale,
            "slot_index": r.slot_index,
        }
        for r in rows
    ]
