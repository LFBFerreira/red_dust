"""
Shared channel → trace color mapping for waveform plots and playback UI.

Palette order is fixed: among sorted(all channel ids), index i maps to
CHANNEL_TRACE_COLORS[i % len(CHANNEL_TRACE_COLORS)], so the same channel name
always gets the same color across runs. At most MAX_SELECTED_CHANNELS (see
settings) may be selected at once.
"""
from __future__ import annotations

from typing import Dict, Sequence

from settings import MAX_SELECTED_CHANNELS

# Fixed ordered palette (must have at least MAX_SELECTED_CHANNELS entries; extra
# colors are still used via modulo when the max selection limit is raised).
CHANNEL_TRACE_COLORS = [
    "#00d4ff",
    "#ff7f0e",
    "#2ca02c",
    "#d62728",
    "#9467bd",
    "#8c564b",
    "#e377c2",
    "#7f7f7f",
    "#bcbd22",
    "#17becf",
    "#1f77b4",
    "#aec7e8",
    "#ff9896",
    "#98df8a",
    "#c5b0d5",
    "#c49c94",
    "#f7b6d2",
    "#dbdb8d",
    "#9edae5",
    "#ad494a",
]

assert len(CHANNEL_TRACE_COLORS) >= MAX_SELECTED_CHANNELS, (
    f"CHANNEL_TRACE_COLORS ({len(CHANNEL_TRACE_COLORS)}) must be at least "
    f"MAX_SELECTED_CHANNELS ({MAX_SELECTED_CHANNELS})"
)

FALLBACK_TRACE_COLOR = "#666666"


def channel_color_map(sorted_channel_ids: Sequence[str]) -> Dict[str, str]:
    """Map each channel id to a hex color; ids must be sorted for stable assignment."""
    palette = CHANNEL_TRACE_COLORS
    n = len(palette)
    return {cid: palette[i % n] for i, cid in enumerate(sorted_channel_ids)}


def color_for_channel(channel_id: str, sorted_channel_ids: Sequence[str]) -> str:
    """Resolve color for one channel given the full sorted channel list."""
    cmap = channel_color_map(sorted_channel_ids)
    return cmap.get(channel_id, FALLBACK_TRACE_COLOR)
