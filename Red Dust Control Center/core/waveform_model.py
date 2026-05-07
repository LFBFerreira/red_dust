"""
Waveform Model for managing multi-channel seismic data and normalization.
"""
import numpy as np
from obspy import Stream, UTCDateTime
from typing import List, Tuple, Optional
import logging

logger = logging.getLogger(__name__)


class WaveformModel:
    """Manages waveform data, channel selection, and normalization."""
    
    def __init__(self, stream: Optional[Stream] = None):
        """
        Initialize WaveformModel.
        
        Args:
            stream: ObsPy Stream containing waveform data
        """
        self._stream = stream
        self._active_channel = None
        self._lo_percentile = 1.0
        self._hi_percentile = 99.0
        self._normalization_min = None
        self._normalization_max = None
        self._channel_normalization_ranges = {}
        
        if stream is not None:
            self._channels = self._extract_channels()
            if self._channels:
                self.set_active_channel(self._channels[0])
        else:
            self._channels = []
    
    def _extract_channels(self) -> List[str]:
        """Extract unique channel codes from stream."""
        if self._stream is None:
            return []
        
        channels = set()
        for trace in self._stream:
            # Format: network.station.location.channel
            # We want the full channel identifier
            channel_id = f"{trace.stats.location}.{trace.stats.channel}"
            channels.add(channel_id)
        
        return sorted(list(channels))
    
    def set_stream(self, stream: Stream) -> None:
        """
        Set new waveform stream.
        
        Args:
            stream: ObsPy Stream containing waveform data
        """
        self._stream = stream
        self._channels = self._extract_channels()
        self._channel_normalization_ranges = {}
        if self._channels:
            self.set_active_channel(self._channels[0])
        else:
            self._active_channel = None
            self._normalization_min = None
            self._normalization_max = None
    
    def get_all_channels(self) -> List[str]:
        """
        Get list of all available channel codes.
        
        Returns:
            List of channel identifiers (e.g., ["03.BHU", "03.BHV"])
        """
        return self._channels.copy()
    
    def get_active_channel(self) -> Optional[str]:
        """
        Get currently active channel code.
        
        Returns:
            Channel identifier or None if no channel selected
        """
        return self._active_channel
    
    def set_active_channel(self, channel: str) -> None:
        """
        Set active channel for playback and streaming.
        
        Args:
            channel: Channel identifier (e.g., "03.BHU")
        """
        if channel not in self._channels:
            logger.warning(f"Channel {channel} not found in stream")
            return
        
        self._active_channel = channel
        self._recalculate_normalization()
        logger.info(f"Active channel set to {channel}")
    
    def _get_active_trace(self):
        """Get ObsPy Trace for active channel."""
        if self._stream is None or self._active_channel is None:
            return None
        
        return self._get_trace_for_channel(self._active_channel)

    def _get_trace_for_channel(self, channel: str):
        """Get ObsPy Trace for a specific channel identifier."""
        if self._stream is None or not channel:
            return None
        if '.' not in channel:
            return None

        location, channel_code = channel.split('.')
        
        for trace in self._stream:
            if trace.stats.location == location and trace.stats.channel == channel_code:
                return trace
        
        return None

    def _calculate_normalization_range_for_trace(self, trace) -> tuple[float, float]:
        """Calculate normalization range (lo, hi) for a trace."""
        if trace is None or len(trace.data) == 0:
            return (0.0, 1.0)

        data = np.array(trace.data, copy=True)
        valid_mask = np.isfinite(data)

        SENTINEL_MIN = -2147483640
        SENTINEL_MAX = 2147483640
        valid_mask = valid_mask & (data > SENTINEL_MIN) & (data < SENTINEL_MAX)
        valid_data = data[valid_mask]

        if len(valid_data) == 0:
            return (0.0, 1.0)

        lo_val = float(np.percentile(valid_data, self._lo_percentile))
        hi_val = float(np.percentile(valid_data, self._hi_percentile))
        if lo_val > hi_val:
            lo_val, hi_val = hi_val, lo_val
        return (lo_val, hi_val)
    
    def _recalculate_normalization(self) -> None:
        """Recalculate normalization parameters for active channel."""
        import time
        calc_start = time.time()
        
        trace = self._get_active_trace()
        if trace is None:
            self._normalization_min = None
            self._normalization_max = None
            return
        
        # Get all data values - create a writable copy to avoid read-only array issues
        # ObsPy may return read-only arrays from memory-mapped files
        data = np.array(trace.data, copy=True)
        data_size = len(data)
        
        logger.info(f"Recalculating normalization for channel {self._active_channel}: "
                   f"{data_size:,} samples")
        
        if len(data) == 0:
            self._normalization_min = 0.0
            self._normalization_max = 1.0
            return
        
        # Filter out NaN, infinite values, and common sentinel/fill values
        # Common sentinel values: -2147483648 (32-bit int min), 2147483647 (32-bit int max)
        valid_mask = np.isfinite(data)
        # Also filter out extreme sentinel values that might indicate masked/invalid data
        # These are often used as fill values in seismic data
        SENTINEL_MIN = -2147483640  # Close to 32-bit int min
        SENTINEL_MAX = 2147483640   # Close to 32-bit int max
        valid_mask = valid_mask & (data > SENTINEL_MIN) & (data < SENTINEL_MAX)
        valid_data = data[valid_mask]
        
        if len(valid_data) == 0:
            logger.warning(f"No valid (finite) data points found for normalization")
            self._normalization_min = 0.0
            self._normalization_max = 1.0
            return
        
        # Log data range for debugging
        data_min = float(np.min(valid_data))
        data_max = float(np.max(valid_data))
        invalid_count = data_size - len(valid_data)
        if invalid_count > 0:
            logger.info(f"Filtered out {invalid_count:,} invalid/sentinel values from {data_size:,} total samples")
        logger.debug(f"Data range: min={data_min:.6f}, max={data_max:.6f}, "
                    f"valid samples={len(valid_data):,}/{data_size:,}")
        
        # Calculate percentiles - this can be slow for large datasets
        logger.debug(f"Computing percentiles P{self._lo_percentile} and P{self._hi_percentile}...")
        percentile_start = time.time()
        active_range = self._calculate_normalization_range_for_trace(trace)
        percentile_time = time.time() - percentile_start
        
        self._normalization_min, self._normalization_max = active_range
        if self._active_channel:
            self._channel_normalization_ranges[self._active_channel] = active_range
        
        # Ensure min <= max (should always be true for percentiles, but check anyway)
        if self._normalization_min > self._normalization_max:
            logger.warning(f"Percentiles produced min > max, swapping: min={self._normalization_min:.6f}, max={self._normalization_max:.6f}")
            self._normalization_min, self._normalization_max = self._normalization_max, self._normalization_min
        
        calc_time = time.time() - calc_start
        logger.info(f"Normalization calculated in {calc_time:.2f}s "
                   f"(percentile calc: {percentile_time:.2f}s): "
                   f"range {self._normalization_min:.6f} to {self._normalization_max:.6f}")
    
    def update_scaling(self, lo_percentile: float, hi_percentile: float) -> None:
        """
        Update normalization percentile range.
        
        Args:
            lo_percentile: Lower percentile (e.g., 1.0 for P1)
            hi_percentile: Upper percentile (e.g., 99.0 for P99)
        """
        if lo_percentile < 0 or hi_percentile > 100 or lo_percentile >= hi_percentile:
            logger.warning(f"Invalid percentile range: {lo_percentile}-{hi_percentile}")
            return
        
        self._lo_percentile = lo_percentile
        self._hi_percentile = hi_percentile
        self._channel_normalization_ranges = {}
        self._recalculate_normalization()
        logger.info(f"Scaling updated: P{lo_percentile}-P{hi_percentile}")

    def _get_or_calculate_channel_range(self, channel: str) -> tuple[float, float]:
        """Get cached normalization range for channel or calculate it lazily."""
        if channel in self._channel_normalization_ranges:
            return self._channel_normalization_ranges[channel]

        trace = self._get_trace_for_channel(channel)
        if trace is None:
            return (0.0, 1.0)

        value_range = self._calculate_normalization_range_for_trace(trace)
        self._channel_normalization_ranges[channel] = value_range
        return value_range
    
    def get_raw_value(self, timestamp: UTCDateTime) -> Optional[float]:
        """
        Get raw value for active channel at given timestamp.
        
        Args:
            timestamp: UTC timestamp
        
        Returns:
            Raw value or None if out of range or no active channel
        """
        trace = self._get_active_trace()
        if trace is None:
            return None
        
        # Check if timestamp is within trace bounds
        start_time = trace.stats.starttime
        end_time = trace.stats.endtime
        
        if timestamp < start_time or timestamp > end_time:
            return None
        
        # Calculate sample index
        sample_rate = trace.stats.sampling_rate
        time_offset = timestamp - start_time
        sample_index = int(time_offset * sample_rate)
        
        # Clamp to valid range
        sample_index = max(0, min(sample_index, len(trace.data) - 1))
        
        # Get raw value - handle masked arrays and NaN values.
        # Avoid float(np.ma.masked) which emits warnings and can flood logs.
        try:
            v = trace.data[sample_index]
            if np.ma.is_masked(v):
                return None
            raw_value = float(v)
            if not np.isfinite(raw_value):
                return None
            return raw_value
        except (ValueError, TypeError):
            return None
    
    def get_normalized_value(self, timestamp: UTCDateTime) -> float:
        """
        Get normalized value (0..1) for active channel at given timestamp.
        
        Args:
            timestamp: UTC timestamp
        
        Returns:
            Normalized value between 0.0 and 1.0, or 0.0 if out of range
        """
        trace = self._get_active_trace()
        if trace is None:
            return 0.0
        
        # Check if timestamp is within trace bounds
        start_time = trace.stats.starttime
        end_time = trace.stats.endtime
        
        if timestamp < start_time or timestamp > end_time:
            return 0.0
        
        # Calculate sample index
        sample_rate = trace.stats.sampling_rate
        time_offset = timestamp - start_time
        sample_index = int(time_offset * sample_rate)
        
        # Clamp to valid range
        sample_index = max(0, min(sample_index, len(trace.data) - 1))
        
        # Get raw value - handle masked arrays and NaN values (without warnings)
        try:
            v = trace.data[sample_index]
            if np.ma.is_masked(v):
                return 0.0
            raw_value = float(v)
            if not np.isfinite(raw_value):
                return 0.0
        except (ValueError, TypeError):
            return 0.0
        
        # Apply normalization
        if self._normalization_min is None or self._normalization_max is None:
            logger.warning(f"Normalization range not set: min={self._normalization_min}, max={self._normalization_max}")
            return 0.0
        
        # Check if min > max (shouldn't happen, but handle it)
        if self._normalization_min > self._normalization_max:
            logger.error(f"Invalid normalization range: min={self._normalization_min} > max={self._normalization_max}, swapping")
            self._normalization_min, self._normalization_max = self._normalization_max, self._normalization_min
        
        # Clamp to percentile range
        clamped_value = max(self._normalization_min, min(raw_value, self._normalization_max))
        
        # Map to 0..1
        if self._normalization_max == self._normalization_min:
            normalized = 0.5  # Avoid division by zero
            logger.warning(f"Normalization range is zero (min=max={self._normalization_min:.6f}), returning 0.5")
        else:
            normalized = (clamped_value - self._normalization_min) / (self._normalization_max - self._normalization_min)
            # Only log if normalized is at extremes and raw value was clamped (potential issue)
            if normalized >= 0.999 and clamped_value != raw_value:
                logger.debug(f"Normalization at upper limit: raw={raw_value:.6f}, clamped={clamped_value:.6f}, "
                            f"min={self._normalization_min:.6f}, max={self._normalization_max:.6f}, normalized={normalized:.6f}")
            elif normalized <= 0.001 and clamped_value != raw_value:
                logger.debug(f"Normalization at lower limit: raw={raw_value:.6f}, clamped={clamped_value:.6f}, "
                            f"min={self._normalization_min:.6f}, max={self._normalization_max:.6f}, normalized={normalized:.6f}")
        
        # Ensure output is 0..1 (handle any floating point issues)
        normalized = max(0.0, min(1.0, normalized))
        
        return normalized

    def get_normalized_value_for_channel(self, timestamp: UTCDateTime, channel: str) -> float:
        """
        Get normalized value (0..1) for a specific channel at given timestamp.

        Args:
            timestamp: UTC timestamp
            channel: Channel identifier (e.g., "03.BHU")

        Returns:
            Normalized value between 0.0 and 1.0, or 0.0 if out of range/invalid
        """
        trace = self._get_trace_for_channel(channel)
        if trace is None:
            return 0.0

        start_time = trace.stats.starttime
        end_time = trace.stats.endtime
        if timestamp < start_time or timestamp > end_time:
            return 0.0

        sample_rate = trace.stats.sampling_rate
        time_offset = timestamp - start_time
        sample_index = int(time_offset * sample_rate)
        sample_index = max(0, min(sample_index, len(trace.data) - 1))

        try:
            v = trace.data[sample_index]
            if np.ma.is_masked(v):
                return 0.0
            raw_value = float(v)
            if not np.isfinite(raw_value):
                return 0.0
        except (ValueError, TypeError):
            return 0.0

        norm_min, norm_max = self._get_or_calculate_channel_range(channel)
        if norm_max == norm_min:
            return 0.5

        clamped_value = max(norm_min, min(raw_value, norm_max))
        normalized = (clamped_value - norm_min) / (norm_max - norm_min)
        return max(0.0, min(1.0, normalized))
    
    def get_time_range(self) -> Optional[Tuple[UTCDateTime, UTCDateTime]]:
        """
        Get time range of active channel.
        
        Returns:
            Tuple of (start_time, end_time) or None if no active channel
        """
        trace = self._get_active_trace()
        if trace is None:
            return None
        
        return (trace.stats.starttime, trace.stats.endtime)
    
    def get_sample_rate(self) -> Optional[float]:
        """
        Get sample rate of active channel.
        
        Returns:
            Sample rate in Hz or None if no active channel
        """
        trace = self._get_active_trace()
        if trace is None:
            return None
        
        return trace.stats.sampling_rate
    
    def get_stream(self) -> Optional[Stream]:
        """
        Get the underlying ObsPy Stream.
        
        Returns:
            Stream or None if not set
        """
        return self._stream
    
    def get_channel_info(self, channel: Optional[str] = None) -> Optional[dict]:
        """
        Get metadata for a channel.
        
        Args:
            channel: Channel identifier (defaults to active channel)
        
        Returns:
            Dictionary with channel metadata or None
        """
        if channel is None:
            channel = self._active_channel
        
        if channel is None:
            return None
        
        location, channel_code = channel.split('.')
        
        for trace in self._stream:
            if trace.stats.location == location and trace.stats.channel == channel_code:
                return {
                    'network': trace.stats.network,
                    'station': trace.stats.station,
                    'location': trace.stats.location,
                    'channel': trace.stats.channel,
                    'starttime': trace.stats.starttime,
                    'endtime': trace.stats.endtime,
                    'sampling_rate': trace.stats.sampling_rate,
                    'npts': trace.stats.npts
                }
        
        return None

