"""
Waveform Model for managing multi-channel seismic data and normalization.
"""
import logging
import time
from typing import Dict, List, Optional, Tuple

import numpy as np
from obspy import Stream, UTCDateTime

from settings import MAX_SELECTED_CHANNELS

logger = logging.getLogger(__name__)

_LOG_TAG = "[multi_ch]"

# Int-ish sentinels in some seismic products; exclude from percentile normalization.
_NORM_SENTINEL_MIN = -2147483640
_NORM_SENTINEL_MAX = 2147483640


class WaveformModel:
    """Manages waveform data, channel selection, and normalization."""

    def __init__(self, stream: Optional[Stream] = None):
        self._stream = stream
        self._channels: List[str] = []
        self._selected_channels: List[str] = []
        self._lo_percentile = 1.0
        self._hi_percentile = 99.0
        self._normalization_min: Optional[float] = None
        self._normalization_max: Optional[float] = None
        self._per_channel_norm_bounds: Dict[str, Tuple[float, float]] = {}

        if stream is not None:
            self._channels = self._extract_channels()
            if self._channels:
                self._selected_channels = [self._channels[0]]
                self._recalculate_normalization()
            else:
                self._selected_channels = []
        else:
            self._channels = []
            self._selected_channels = []

    def _extract_channels(self) -> List[str]:
        if self._stream is None:
            return []
        channels = set()
        for trace in self._stream:
            channel_id = f"{trace.stats.location}.{trace.stats.channel}"
            channels.add(channel_id)
        return sorted(channels)

    def set_stream(self, stream: Optional[Stream]) -> None:
        self._stream = stream
        self._per_channel_norm_bounds = {}
        self._channels = self._extract_channels()
        if self._channels:
            self._selected_channels = [self._channels[0]]
            self._recalculate_normalization()
        else:
            self._selected_channels = []
            self._normalization_min = None
            self._normalization_max = None
        tr = self.get_time_range()
        logger.debug(
            "%s set_stream traces=%s channels=%s selected=%s time_range=%s",
            _LOG_TAG,
            len(stream) if stream else 0,
            len(self._channels),
            len(self._selected_channels),
            "None" if tr is None else f"{tr[0]}..{tr[1]}",
        )

    def get_all_channels(self) -> List[str]:
        return self._channels.copy()

    def get_selected_channels(self) -> List[str]:
        return list(self._selected_channels)

    def set_selected_channels(self, selected: List[str]) -> None:
        valid = set(self._channels)
        filtered = []
        seen = set()
        for ch in selected:
            if ch in valid and ch not in seen:
                seen.add(ch)
                filtered.append(ch)
        if len(filtered) > MAX_SELECTED_CHANNELS:
            logger.info(
                "%s selection truncated from %s to %s channels",
                _LOG_TAG,
                len(filtered),
                MAX_SELECTED_CHANNELS,
            )
            filtered = filtered[:MAX_SELECTED_CHANNELS]
        self._selected_channels = filtered
        self._recalculate_normalization()
        tr = self.get_time_range()
        logger.debug(
            "%s set_selected_channels count=%s ref=%s time_range=%s",
            _LOG_TAG,
            len(self._selected_channels),
            self.get_active_channel(),
            "None" if tr is None else "ok",
        )

    def get_active_channel(self) -> Optional[str]:
        sel = set(self._selected_channels)
        return next((c for c in self._channels if c in sel), None)

    def set_active_channel(self, channel: str) -> None:
        """Solo-select one channel (convenience for callers that only set a single id)."""
        if channel not in self._channels:
            logger.warning("Channel %s not found in stream", channel)
            return
        self.set_selected_channels([channel])

    def _get_active_trace(self):
        ref = self.get_active_channel()
        return self._get_trace_for_channel(ref)

    def _get_trace_for_channel(self, channel_id: Optional[str]):
        if self._stream is None or not channel_id:
            return None
        location, channel = channel_id.split(".")
        for trace in self._stream:
            if trace.stats.location == location and trace.stats.channel == channel:
                return trace
        return None

    def _compute_norm_bounds_from_trace(self, trace) -> Tuple[float, float]:
        data = np.array(trace.data, copy=True)
        if len(data) == 0:
            return (0.0, 1.0)
        valid_mask = np.isfinite(data)
        valid_mask = valid_mask & (data > _NORM_SENTINEL_MIN) & (data < _NORM_SENTINEL_MAX)
        valid_data = data[valid_mask]
        if len(valid_data) == 0:
            if len(data) > 0:
                logger.warning("No valid (finite) data points found for normalization")
            return (0.0, 1.0)
        lo_val = float(np.percentile(valid_data, self._lo_percentile))
        hi_val = float(np.percentile(valid_data, self._hi_percentile))
        if lo_val > hi_val:
            lo_val, hi_val = hi_val, lo_val
        return (lo_val, hi_val)

    def _norm_bounds_for_channel(self, channel_id: str) -> Optional[Tuple[float, float]]:
        if channel_id in self._per_channel_norm_bounds:
            return self._per_channel_norm_bounds[channel_id]
        trace = self._get_trace_for_channel(channel_id)
        if trace is None:
            return None
        bounds = self._compute_norm_bounds_from_trace(trace)
        self._per_channel_norm_bounds[channel_id] = bounds
        return bounds

    def _normalize_raw_with_bounds(
        self, raw_value: float, norm_min: float, norm_max: float
    ) -> float:
        if norm_min > norm_max:
            norm_min, norm_max = norm_max, norm_min
        clamped_value = max(norm_min, min(raw_value, norm_max))
        if norm_max == norm_min:
            return 0.5
        normalized = (clamped_value - norm_min) / (norm_max - norm_min)
        return max(0.0, min(1.0, normalized))

    def _recalculate_normalization(self) -> None:
        calc_start = time.time()
        trace = self._get_active_trace()
        ref = self.get_active_channel()
        if trace is None:
            self._normalization_min = None
            self._normalization_max = None
            logger.debug("%s normalization cleared (no reference trace)", _LOG_TAG)
            return

        data_size = len(trace.data)
        logger.info(
            "Recalculating normalization for channel %s: %s samples",
            ref,
            f"{data_size:,}",
        )

        lo_val, hi_val = self._compute_norm_bounds_from_trace(trace)
        self._normalization_min = lo_val
        self._normalization_max = hi_val

        calc_time = time.time() - calc_start
        logger.info(
            "Normalization calculated in %.2fs: range %.6f to %.6f",
            calc_time,
            self._normalization_min,
            self._normalization_max,
        )

    def update_scaling(self, lo_percentile: float, hi_percentile: float) -> None:
        if lo_percentile < 0 or hi_percentile > 100 or lo_percentile >= hi_percentile:
            logger.warning("Invalid percentile range: %s-%s", lo_percentile, hi_percentile)
            return
        self._lo_percentile = lo_percentile
        self._hi_percentile = hi_percentile
        self._per_channel_norm_bounds = {}
        self._recalculate_normalization()
        logger.info("Scaling updated: P%s-P%s", lo_percentile, hi_percentile)

    def get_raw_value_for_channel(
        self, channel_id: str, timestamp: UTCDateTime
    ) -> Optional[float]:
        trace = self._get_trace_for_channel(channel_id)
        if trace is None:
            return None
        start_time = trace.stats.starttime
        end_time = trace.stats.endtime
        if timestamp < start_time or timestamp > end_time:
            return None
        sample_rate = trace.stats.sampling_rate
        time_offset = timestamp - start_time
        sample_index = int(time_offset * sample_rate)
        sample_index = max(0, min(sample_index, len(trace.data) - 1))
        try:
            sample = trace.data[sample_index]
            if np.ma.is_masked(sample):
                return None
            raw_value = float(np.asarray(sample, dtype=np.float64).item())
            if not np.isfinite(raw_value):
                return None
            return raw_value
        except (ValueError, TypeError):
            return None

    def get_raw_value(self, timestamp: UTCDateTime) -> Optional[float]:
        ref = self.get_active_channel()
        if ref is None:
            return None
        return self.get_raw_value_for_channel(ref, timestamp)

    def get_normalized_value(self, timestamp: UTCDateTime) -> float:
        ref = self.get_active_channel()
        if ref is None:
            return 0.0
        raw_value = self.get_raw_value_for_channel(ref, timestamp)
        if raw_value is None:
            return 0.0
        if self._normalization_min is None or self._normalization_max is None:
            return 0.0
        return self._normalize_raw_with_bounds(
            raw_value, self._normalization_min, self._normalization_max
        )

    def get_normalized_value_for_channel(
        self, channel_id: str, timestamp: UTCDateTime
    ) -> float:
        """
        Normalized sample (0..1) for a channel using that trace's percentile bounds,
        independent of the active reference channel.
        """
        if channel_id not in self._channels:
            return 0.0
        raw_value = self.get_raw_value_for_channel(channel_id, timestamp)
        if raw_value is None:
            return 0.0
        bounds = self._norm_bounds_for_channel(channel_id)
        if bounds is None:
            return 0.0
        return self._normalize_raw_with_bounds(raw_value, bounds[0], bounds[1])

    def _raw_and_norm_for_channel(
        self, channel_id: str, timestamp: UTCDateTime
    ) -> Tuple[Optional[float], Optional[float]]:
        raw = self.get_raw_value_for_channel(channel_id, timestamp)
        if raw is None:
            return None, None
        bounds = self._norm_bounds_for_channel(channel_id)
        if bounds is None:
            return raw, None
        norm = self._normalize_raw_with_bounds(raw, bounds[0], bounds[1])
        return raw, norm

    def get_selected_channel_value_pairs(
        self, timestamp: UTCDateTime
    ) -> List[Tuple[str, Optional[float], Optional[float]]]:
        ordered = [c for c in self._selected_channels if c in self._channels]
        return [
            (ch, *self._raw_and_norm_for_channel(ch, timestamp)) for ch in ordered
        ]

    def get_time_range(self) -> Optional[Tuple[UTCDateTime, UTCDateTime]]:
        if self._stream is None or len(self._stream) == 0:
            return None
        if not self._selected_channels:
            return None
        start = min(tr.stats.starttime for tr in self._stream)
        end = max(tr.stats.endtime for tr in self._stream)
        return (start, end)

    def get_sample_rate(self) -> Optional[float]:
        trace = self._get_active_trace()
        if trace is None:
            return None
        return trace.stats.sampling_rate

    def get_stream(self) -> Optional[Stream]:
        return self._stream

    def get_channel_info(self, channel: Optional[str] = None) -> Optional[dict]:
        if channel is None:
            channel = self.get_active_channel()
        if channel is None:
            return None
        trace = self._get_trace_for_channel(channel)
        if trace is None:
            return None
        return {
            "network": trace.stats.network,
            "station": trace.stats.station,
            "location": trace.stats.location,
            "channel": trace.stats.channel,
            "starttime": trace.stats.starttime,
            "endtime": trace.stats.endtime,
            "sampling_rate": trace.stats.sampling_rate,
            "npts": trace.stats.npts,
        }
