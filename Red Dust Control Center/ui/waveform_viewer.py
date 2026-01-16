"""
Waveform Viewer widget for displaying seismic waveforms.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Signal, Qt
from obspy import Stream, UTCDateTime
import pyqtgraph as pg
import numpy as np
import logging
import settings

logger = logging.getLogger(__name__)

# Waveform display constants
CHANNEL_LINE_WIDTH = 1  # Line width for all channels (in pixels)


class WaveformViewer(QWidget):
    """Widget for displaying multi-channel waveform data."""
    
    # Signal emitted when user selects a loop range
    loop_range_selected = Signal(UTCDateTime, UTCDateTime)  # Emits start, end
    
    def __init__(self, parent=None):
        """Initialize WaveformViewer."""
        super().__init__(parent)
        self._stream = None
        self._active_channel = None
        self._playhead_line = None
        self._loop_region = None
        self._plot_items = {}
        # Cache for pre-calculated channel data (full and downsampled)
        # Format: {channel_id: {'times_full': array, 'data_full': array, 
        #                        'times_downsampled': array, 'data_downsampled': array,
        #                        'npts_original': int, 'npts_downsampled': int,
        #                        'x_min': float, 'x_max': float,
        #                        'y_min': float, 'y_max': float}}
        self._channel_data_cache = {}
        # Overall min/max across all channels (for panning limits)
        self._overall_x_range = None  # (min, max)
        self._overall_y_range = None  # (min, max)
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the UI components."""
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Title aligned to top left
        title = QLabel("<b>Waveform</b>")
        title.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(title)
        
        # PyQtGraph plot widget - stretches vertically and horizontally
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel('left', 'Amplitude')  # Will be updated with units when data loads
        self.plot_widget.setLabel('bottom', 'Time (UTC)')
        self.plot_widget.showGrid(x=True, y=True)
        self.plot_widget.setMouseEnabled(x=True, y=True)
        
        # Set up X-axis to display time in HH:MM:SS format
        # Create a custom axis item that formats timestamps as time
        from pyqtgraph import AxisItem
        from datetime import datetime, timezone
        
        class TimeAxisItem(AxisItem):
            """Custom axis item that formats Unix timestamps as HH:MM:SS."""
            
            def tickStrings(self, values, scale, spacing):
                """Format tick values as time strings."""
                strings = []
                for v in values:
                    try:
                        # Convert Unix timestamp to UTC datetime
                        dt = datetime.fromtimestamp(v, tz=timezone.utc)
                        # Format as HH:MM:SS
                        strings.append(dt.strftime("%H:%M:%S"))
                    except (ValueError, OSError, OverflowError):
                        strings.append("")
                return strings
        
        # Replace the bottom axis with our custom time axis
        self.plot_widget.plotItem.setAxisItems({'bottom': TimeAxisItem(orientation='bottom')})
        
        # Initial X limit (will be updated when data loads)
        self.plot_widget.plotItem.vb.setLimits(xMin=0)
        
        # Enable click-drag for loop selection
        self.plot_widget.scene().sigMouseClicked.connect(self._on_mouse_click)
        self.plot_widget.scene().sigMouseMoved.connect(self._on_mouse_move)
        
        self._drag_start = None
        self._is_dragging = False
        
        layout.addWidget(self.plot_widget, 1)  # Stretch factor to fill remaining space
        self.setLayout(layout)
    
    def _precalculate_channel_data(self, stream: Stream) -> None:
        """
        Pre-calculate full and downsampled data for all channels.
        
        Args:
            stream: ObsPy Stream containing waveform data
        """
        import time
        precalc_start = time.time()
        
        logger.info(f"Pre-calculating channel data for {len(stream) if stream else 0} traces...")
        
        # Clear existing cache
        self._channel_data_cache.clear()
        
        if stream is None or len(stream) == 0:
            return
        
        # Group traces by channel
        channels = {}
        for trace in stream:
            channel_id = f"{trace.stats.location}.{trace.stats.channel}"
            if channel_id not in channels:
                channels[channel_id] = []
            channels[channel_id].append(trace)
        
        max_points = settings.WAVEFORM_INACTIVE_CHANNEL_MAX_POINTS
        
        # Collect overall min/max values across all channels
        all_x_mins = []
        all_x_maxs = []
        all_y_mins = []
        all_y_maxs = []
        
        for channel_id, traces in channels.items():
            channel_precalc_start = time.time()
            
            # Merge traces if multiple
            if len(traces) > 1:
                temp_stream = Stream(traces)
                temp_stream.merge(method=1)  # Fill gaps with NaN
                trace = temp_stream[0] if len(temp_stream) > 0 else traces[0]
            else:
                trace = traces[0]
            
            npts_original = len(trace.data)
            start_timestamp = trace.stats.starttime.timestamp
            sample_rate = trace.stats.sampling_rate
            
            # Calculate full resolution data
            times_full = start_timestamp + np.arange(npts_original) / sample_rate
            # Convert to float array to allow NaN assignment (data might be integer)
            data_full = np.array(trace.data, copy=True, dtype=np.float64)
            
            # Replace sentinel/fill values with NaN so they don't appear in the plot
            # Common sentinel values: -2147483648 (32-bit int min), 2147483647 (32-bit int max)
            SENTINEL_MIN = -2147483640  # Close to 32-bit int min
            SENTINEL_MAX = 2147483640   # Close to 32-bit int max
            sentinel_mask = (data_full <= SENTINEL_MIN) | (data_full >= SENTINEL_MAX)
            data_full[sentinel_mask] = np.nan
            
            # Also replace any non-finite values with NaN
            data_full[~np.isfinite(data_full)] = np.nan
            
            # Calculate channel-specific min/max (excluding NaN and sentinel values)
            valid_data = data_full[np.isfinite(data_full)]
            if len(valid_data) > 0:
                channel_y_min = float(np.nanmin(valid_data))
                channel_y_max = float(np.nanmax(valid_data))
            else:
                channel_y_min = 0.0
                channel_y_max = 0.0
            
            channel_x_min = float(times_full[0])
            channel_x_max = float(times_full[-1])
            
            # Collect for overall min/max
            all_x_mins.append(channel_x_min)
            all_x_maxs.append(channel_x_max)
            all_y_mins.append(channel_y_min)
            all_y_maxs.append(channel_y_max)
            
            # Calculate downsampled data if needed
            if npts_original > max_points:
                downsample_factor = int(np.ceil(npts_original / max_points))
                data_downsampled = data_full[::downsample_factor]
                times_downsampled = start_timestamp + np.arange(0, npts_original, downsample_factor) / sample_rate
                # Ensure arrays have same length
                min_len = min(len(times_downsampled), len(data_downsampled))
                times_downsampled = times_downsampled[:min_len]
                data_downsampled = data_downsampled[:min_len]
                npts_downsampled = min_len
            else:
                # No downsampling needed
                times_downsampled = times_full
                data_downsampled = data_full
                npts_downsampled = npts_original
            
            # Store in cache
            self._channel_data_cache[channel_id] = {
                'times_full': times_full,
                'data_full': data_full,
                'times_downsampled': times_downsampled,
                'data_downsampled': data_downsampled,
                'npts_original': npts_original,
                'npts_downsampled': npts_downsampled,
                'x_min': channel_x_min,
                'x_max': channel_x_max,
                'y_min': channel_y_min,
                'y_max': channel_y_max
            }
            
            channel_precalc_time = time.time() - channel_precalc_start
            if npts_downsampled < npts_original:
                logger.debug(f"Pre-calculated {channel_id}: {npts_original:,} -> {npts_downsampled:,} points in {channel_precalc_time:.2f}s")
            else:
                logger.debug(f"Pre-calculated {channel_id}: {npts_original:,} points (no downsampling) in {channel_precalc_time:.2f}s")
        
        # Calculate overall min/max across all channels
        if all_x_mins and all_x_maxs and all_y_mins and all_y_maxs:
            self._overall_x_range = (min(all_x_mins), max(all_x_maxs))
            self._overall_y_range = (min(all_y_mins), max(all_y_maxs))
            logger.debug(f"Overall ranges: X=[{self._overall_x_range[0]:.2f}, {self._overall_x_range[1]:.2f}], Y=[{self._overall_y_range[0]:.2f}, {self._overall_y_range[1]:.2f}]")
        else:
            self._overall_x_range = None
            self._overall_y_range = None
        
        precalc_time = time.time() - precalc_start
        logger.info(f"Pre-calculation complete for {len(self._channel_data_cache)} channels in {precalc_time:.2f}s")
    
    def update_waveform(self, stream: Stream, active_channel: str = None) -> None:
        """
        Update waveform display with new stream data.
        
        Args:
            stream: ObsPy Stream containing waveform data
            active_channel: Active channel identifier (e.g., "03.BHU")
        """
        import time
        update_start = time.time()
        
        logger.info(f"WaveformViewer.update_waveform called with {len(stream) if stream else 0} traces, active_channel={active_channel}")
        
        # Check if stream has changed (need to recalculate cache)
        # Compare by checking if channel IDs match cached channels
        stream_changed = False
        if stream is None:
            if len(self._channel_data_cache) > 0:
                stream_changed = True
        elif self._stream is None:
            stream_changed = True
        else:
            # Check if channels match by comparing channel IDs
            current_channels = set()
            for trace in stream:
                channel_id = f"{trace.stats.location}.{trace.stats.channel}"
                current_channels.add(channel_id)
            cached_channels = set(self._channel_data_cache.keys())
            if current_channels != cached_channels:
                stream_changed = True
        
        if stream_changed:
            logger.debug(f"Stream changed, pre-calculating channel data...")
            self._precalculate_channel_data(stream)
        
        self._stream = stream
        old_active_channel = self._active_channel
        self._active_channel = active_channel
        
        # Clear existing plots
        logger.debug(f"Clearing existing plots...")
        clear_start = time.time()
        self.plot_widget.clear()
        self._plot_items.clear()
        self._playhead_line = None
        self._loop_region = None
        clear_time = time.time() - clear_start
        logger.debug(f"Plot clearing took {clear_time:.2f}s")
        
        if stream is None or len(stream) == 0 or len(self._channel_data_cache) == 0:
            logger.warning(f"No stream data to display")
            return
        
        # Update amplitude label with units from active channel
        amplitude_label = 'Amplitude'
        if active_channel and stream:
            # Find the trace for the active channel to get units
            location, channel_code = active_channel.split('.')
            for trace in stream:
                if trace.stats.location == location and trace.stats.channel == channel_code:
                    # Try to get unit from trace stats (ObsPy may have 'units' attribute)
                    unit = getattr(trace.stats, 'units', None)
                    if unit:
                        amplitude_label = f'Amplitude ({unit})'
                    else:
                        # Default to "Counts" for seismic data if no unit specified
                        amplitude_label = 'Amplitude (Counts)'
                    break
        else:
            # No active channel, use default
            amplitude_label = 'Amplitude (Counts)'
        
        self.plot_widget.setLabel('left', amplitude_label)
        
        # Plot each channel using cached data
        channel_colors = ['#00d4ff', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']  # Colors for channels
        # Create consistent color mapping based on sorted channel IDs
        sorted_channel_ids = sorted(self._channel_data_cache.keys())
        channel_color_map = {channel_id: channel_colors[i % len(channel_colors)] for i, channel_id in enumerate(sorted_channel_ids)}
        
        total_data_points = 0  # Track total data points across all channels
        
        plot_start = time.time()
        for channel_id, channel_data in self._channel_data_cache.items():
            channel_start = time.time()
            
            is_active = (channel_id == active_channel)
            
            # Skip inactive channels if setting is enabled
            if settings.WAVEFORM_SHOW_ONLY_ACTIVE_CHANNEL and not is_active:
                continue
            
            # Select appropriate data version
            if is_active:
                times = channel_data['times_full']
                data = channel_data['data_full']
                npts = channel_data['npts_original']
            else:
                times = channel_data['times_downsampled']
                data = channel_data['data_downsampled']
                npts = channel_data['npts_downsampled']
            
            total_data_points += npts
            
            # Choose color - each channel gets a consistent color based on its ID
            color = channel_color_map.get(channel_id, '#666666')
            
            # All channels use the same line width
            width = CHANNEL_LINE_WIDTH
            
            # Plot
            plot_item_start = time.time()
            plot_item = self.plot_widget.plot(times, data, pen=pg.mkPen(color=color, width=width))
            self._plot_items[channel_id] = plot_item
            plot_item_time = time.time() - plot_item_start
            logger.debug(f"Plotting {channel_id} took {plot_item_time:.2f}s ({npts:,} points)")
            
            channel_time = time.time() - channel_start
            if is_active:
                logger.info(f"Channel {channel_id} (active) complete in {channel_time:.2f}s total ({npts:,} points, full resolution)")
            else:
                logger.info(f"Channel {channel_id} (inactive) complete in {channel_time:.2f}s total ({npts:,} points, downsampled)")
        
        plot_time = time.time() - plot_start
        logger.info(f"All channels plotted in {plot_time:.2f}s")
        logger.info(f"Total data points added to waveform viewer: {total_data_points:,} points across {len(self._channel_data_cache)} channels")
        
        # Add playhead line and set X/Y limits based on data
        limits_start = time.time()
        if len(stream) > 0 and len(self._channel_data_cache) > 0:
            trace = stream[0]
            
            # Set panning limits to overall min/max of all channels
            if self._overall_x_range is not None and self._overall_y_range is not None:
                # Add small margins for panning limits
                x_margin = (self._overall_x_range[1] - self._overall_x_range[0]) * 0.01
                y_margin = (self._overall_y_range[1] - self._overall_y_range[0]) * 0.05 if self._overall_y_range[1] != self._overall_y_range[0] else abs(self._overall_y_range[1]) * 0.05 if self._overall_y_range[1] != 0 else 1.0
                
                overall_x_min = self._overall_x_range[0] - x_margin
                overall_x_max = self._overall_x_range[1] + x_margin
                overall_y_min = self._overall_y_range[0] - y_margin
                overall_y_max = self._overall_y_range[1] + y_margin
                
                # Set panning limits (overall range)
                self.plot_widget.plotItem.vb.setLimits(
                    xMin=overall_x_min,
                    xMax=overall_x_max,
                    yMin=overall_y_min,
                    yMax=overall_y_max
                )
                logger.debug(f"Panning limits set to overall range: X=[{overall_x_min:.2f}, {overall_x_max:.2f}], Y=[{overall_y_min:.2f}, {overall_y_max:.2f}]")
            
            # Set view range to active channel's range
            if active_channel and active_channel in self._channel_data_cache:
                active_channel_data = self._channel_data_cache[active_channel]
                active_x_min = active_channel_data['x_min']
                active_x_max = active_channel_data['x_max']
                active_y_min = active_channel_data['y_min']
                active_y_max = active_channel_data['y_max']
                
                # Add small margins for view range
                active_x_margin = (active_x_max - active_x_min) * 0.01
                active_y_margin = (active_y_max - active_y_min) * 0.05 if active_y_max != active_y_min else abs(active_y_max) * 0.05 if active_y_max != 0 else 1.0
                
                view_x_min = active_x_min - active_x_margin
                view_x_max = active_x_max + active_x_margin
                view_y_min = active_y_min - active_y_margin
                view_y_max = active_y_max + active_y_margin
                
                # Set view range to active channel
                self.plot_widget.plotItem.vb.setRange(
                    xRange=(view_x_min, view_x_max),
                    yRange=(view_y_min, view_y_max),
                    padding=0
                )
                logger.debug(f"View range set to active channel {active_channel}: X=[{view_x_min:.2f}, {view_x_max:.2f}], Y=[{view_y_min:.2f}, {view_y_max:.2f}]")
            else:
                # No active channel or channel not found, use overall range
                if self._overall_x_range is not None and self._overall_y_range is not None:
                    x_margin = (self._overall_x_range[1] - self._overall_x_range[0]) * 0.01
                    y_margin = (self._overall_y_range[1] - self._overall_y_range[0]) * 0.05 if self._overall_y_range[1] != self._overall_y_range[0] else abs(self._overall_y_range[1]) * 0.05 if self._overall_y_range[1] != 0 else 1.0
                    
                    view_x_min = self._overall_x_range[0] - x_margin
                    view_x_max = self._overall_x_range[1] + x_margin
                    view_y_min = self._overall_y_range[0] - y_margin
                    view_y_max = self._overall_y_range[1] + y_margin
                    
                    self.plot_widget.plotItem.vb.setRange(
                        xRange=(view_x_min, view_x_max),
                        yRange=(view_y_min, view_y_max),
                        padding=0
                    )
                    logger.debug(f"View range set to overall range: X=[{view_x_min:.2f}, {view_x_max:.2f}], Y=[{view_y_min:.2f}, {view_y_max:.2f}]")
            
            # Set playhead to start of overall time range
            if self._overall_x_range is not None:
                playhead_pos = self._overall_x_range[0]
            else:
                playhead_pos = trace.stats.starttime.timestamp
            
            self._playhead_line = pg.InfiniteLine(
                pos=playhead_pos,
                angle=90,
                pen=pg.mkPen(color='r', width=2, style=Qt.PenStyle.DashLine)
            )
            self.plot_widget.addItem(self._playhead_line)
        
        limits_time = time.time() - limits_start
        logger.debug(f"Setting limits and resetting view took {limits_time:.2f}s")
        
        total_time = time.time() - update_start
        logger.info(f"WaveformViewer.update_waveform complete in {total_time:.2f}s total")
        logger.info(f"Updated waveform display with {len(self._channel_data_cache)} channels")
    
    def update_playhead(self, timestamp: UTCDateTime) -> None:
        """
        Update playhead position.
        
        Args:
            timestamp: Current playhead timestamp
        """
        if self._playhead_line is not None:
            self._playhead_line.setValue(timestamp.timestamp)
    
    def set_loop_range(self, start: UTCDateTime = None, end: UTCDateTime = None) -> None:
        """
        Set loop range visualization.
        
        Args:
            start: Loop start timestamp
            end: Loop end timestamp
        """
        # Remove existing region
        if self._loop_region is not None:
            self.plot_widget.removeItem(self._loop_region)
            self._loop_region = None
        
        # Add new region
        if start is not None and end is not None:
            self._loop_region = pg.LinearRegionItem(
                values=[start.timestamp, end.timestamp],
                brush=pg.mkBrush(color=(255, 255, 0, 50)),  # Yellow with transparency
                pen=pg.mkPen(color='y', width=1)
            )
            self.plot_widget.addItem(self._loop_region)
    
    def _on_mouse_click(self, event):
        """Handle mouse click for loop range selection."""
        if event.button() == Qt.MouseButton.LeftButton:
            pos = self.plot_widget.plotItem.vb.mapSceneToView(event.scenePos())
            if self.plot_widget.plotItem.vb.sceneBoundingRect().contains(event.scenePos()):
                self._drag_start = pos.x()
                self._is_dragging = True
    
    def _on_mouse_move(self, event):
        """Handle mouse move during drag."""
        if self._is_dragging and self._drag_start is not None:
            pos = self.plot_widget.plotItem.vb.mapSceneToView(event.scenePos())
            # Could show temporary selection here
            pass
    
    def mouseReleaseEvent(self, event):
        """Handle mouse release to complete loop selection."""
        if self._is_dragging and self._drag_start is not None:
            pos = self.plot_widget.plotItem.vb.mapSceneToView(event.pos())
            if self._drag_start != pos.x():
                start_time = UTCDateTime(self._drag_start)
                end_time = UTCDateTime(pos.x())
                # Ensure start < end
                if start_time > end_time:
                    start_time, end_time = end_time, start_time
                self.loop_range_selected.emit(start_time, end_time)
            self._is_dragging = False
            self._drag_start = None
        super().mouseReleaseEvent(event)

