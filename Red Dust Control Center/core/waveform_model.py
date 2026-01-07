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
        
        location, channel = self._active_channel.split('.')
        
        for trace in self._stream:
            if trace.stats.location == location and trace.stats.channel == channel:
                return trace
        
        return None
    
    def _recalculate_normalization(self) -> None:
        """Recalculate normalization parameters for active channel."""
        trace = self._get_active_trace()
        if trace is None:
            self._normalization_min = None
            self._normalization_max = None
            return
        
        # Get all data values
        data = trace.data
        
        if len(data) == 0:
            self._normalization_min = 0.0
            self._normalization_max = 1.0
            return
        
        # Calculate percentiles
        lo_val = np.percentile(data, self._lo_percentile)
        hi_val = np.percentile(data, self._hi_percentile)
        
        self._normalization_min = float(lo_val)
        self._normalization_max = float(hi_val)
        
        logger.debug(f"Normalization range: {self._normalization_min} to {self._normalization_max}")
    
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
        self._recalculate_normalization()
        logger.info(f"Scaling updated: P{lo_percentile}-P{hi_percentile}")
    
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
        
        # Get raw value
        raw_value = float(trace.data[sample_index])
        
        # Apply normalization
        if self._normalization_min is None or self._normalization_max is None:
            return 0.0
        
        # Clamp to percentile range
        clamped_value = max(self._normalization_min, min(raw_value, self._normalization_max))
        
        # Map to 0..1
        if self._normalization_max == self._normalization_min:
            normalized = 0.5  # Avoid division by zero
        else:
            normalized = (clamped_value - self._normalization_min) / (self._normalization_max - self._normalization_min)
        
        # Ensure output is 0..1 (handle any floating point issues)
        normalized = max(0.0, min(1.0, normalized))
        
        return normalized
    
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

