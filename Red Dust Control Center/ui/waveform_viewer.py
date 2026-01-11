"""
Waveform Viewer widget for displaying seismic waveforms.
"""
from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
from PySide6.QtCore import Signal, Qt
from obspy import Stream, UTCDateTime
import pyqtgraph as pg
import numpy as np
import logging

logger = logging.getLogger(__name__)


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
        self.plot_widget.setLabel('left', 'Amplitude')
        self.plot_widget.setLabel('bottom', 'Time (UTC)')
        self.plot_widget.showGrid(x=True, y=True)
        self.plot_widget.setMouseEnabled(x=True, y=True)
        
        # Initial X limit (will be updated when data loads)
        self.plot_widget.plotItem.vb.setLimits(xMin=0)
        
        # Enable click-drag for loop selection
        self.plot_widget.scene().sigMouseClicked.connect(self._on_mouse_click)
        self.plot_widget.scene().sigMouseMoved.connect(self._on_mouse_move)
        
        self._drag_start = None
        self._is_dragging = False
        
        layout.addWidget(self.plot_widget, 1)  # Stretch factor to fill remaining space
        self.setLayout(layout)
    
    def update_waveform(self, stream: Stream, active_channel: str = None) -> None:
        """
        Update waveform display with new stream data.
        
        Args:
            stream: ObsPy Stream containing waveform data
            active_channel: Active channel identifier (e.g., "03.BHU")
        """
        import time
        update_start = time.time()
        
        logger.info(f"[DEBUG] WaveformViewer.update_waveform called with {len(stream) if stream else 0} traces, active_channel={active_channel}")
        
        self._stream = stream
        self._active_channel = active_channel
        
        # Clear existing plots
        logger.debug(f"[DEBUG] Clearing existing plots...")
        clear_start = time.time()
        self.plot_widget.clear()
        self._plot_items.clear()
        self._playhead_line = None
        self._loop_region = None
        clear_time = time.time() - clear_start
        logger.debug(f"[DEBUG] Plot clearing took {clear_time:.2f}s")
        
        if stream is None or len(stream) == 0:
            logger.warning(f"[DEBUG] No stream data to display")
            return
        
        # Group traces by channel
        logger.debug(f"[DEBUG] Grouping traces by channel...")
        group_start = time.time()
        channels = {}
        for trace in stream:
            channel_id = f"{trace.stats.location}.{trace.stats.channel}"
            if channel_id not in channels:
                channels[channel_id] = []
            channels[channel_id].append(trace)
        group_time = time.time() - group_start
        logger.info(f"[DEBUG] Grouped {len(stream)} traces into {len(channels)} channels in {group_time:.2f}s")
        
        # Plot each channel and collect Y values for limits
        active_colors = ['#00d4ff', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']  # Bright colors for active channel
        color_idx = 0
        all_y_values = []  # Collect all Y values to find min/max
        
        plot_start = time.time()
        for channel_id, traces in channels.items():
            channel_start = time.time()
            logger.debug(f"[DEBUG] Processing channel {channel_id} with {len(traces)} trace(s)...")
            
            # Merge traces if multiple (ObsPy handles this)
            if len(traces) > 1:
                merge_start = time.time()
                # Use ObsPy's merge method
                temp_stream = Stream(traces)
                temp_stream.merge(method=1)  # Fill gaps with NaN
                trace = temp_stream[0] if len(temp_stream) > 0 else traces[0]
                merge_time = time.time() - merge_start
                logger.debug(f"[DEBUG] Merged {len(traces)} traces for {channel_id} in {merge_time:.2f}s")
            else:
                trace = traces[0]
            
            # Prepare data
            data_prep_start = time.time()
            npts = len(trace.data)
            logger.debug(f"[DEBUG] Preparing data for {channel_id}: {npts:,} samples...")
            
            # Optimize time array creation - use vectorized operations
            start_timestamp = trace.stats.starttime.timestamp
            sample_rate = trace.stats.sampling_rate
            times = start_timestamp + np.arange(npts) / sample_rate
            
            data = trace.data
            data_prep_time = time.time() - data_prep_start
            logger.debug(f"[DEBUG] Data preparation for {channel_id} took {data_prep_time:.2f}s")
            
            # Collect Y values (filter out NaN values)
            valid_data = data[~np.isnan(data)]
            if len(valid_data) > 0:
                # Convert to list to avoid numpy array issues when extending
                all_y_values.extend(valid_data.tolist())
            
            # Choose color and pen width
            is_active = (channel_id == active_channel)
            if is_active:
                # Active channel: bright color and thicker line
                color = active_colors[color_idx % len(active_colors)]
                width = 4
            else:
                # Non-active channels: muted gray color and thin line
                color = '#666666'  # Muted gray
                width = 1
            
            # Plot
            plot_item_start = time.time()
            plot_item = self.plot_widget.plot(times, data, pen=pg.mkPen(color=color, width=width))
            self._plot_items[channel_id] = plot_item
            plot_item_time = time.time() - plot_item_start
            logger.debug(f"[DEBUG] Plotting {channel_id} took {plot_item_time:.2f}s")
            
            channel_time = time.time() - channel_start
            logger.info(f"[DEBUG] Channel {channel_id} complete in {channel_time:.2f}s total")
            
            color_idx += 1
        
        plot_time = time.time() - plot_start
        logger.info(f"[DEBUG] All channels plotted in {plot_time:.2f}s")
        
        # Add playhead line and set X/Y limits based on data
        limits_start = time.time()
        if len(stream) > 0:
            trace = stream[0]
            time_range = (trace.stats.starttime.timestamp, trace.stats.endtime.timestamp)
            
            # Set X limits to prevent panning beyond min and max X values
            # Use the start and end time of the data as the limits
            self.plot_widget.plotItem.vb.setLimits(
                xMin=time_range[0],
                xMax=time_range[1]
            )
            
            # Set Y limits based on dataset min/max values
            if len(all_y_values) > 0:
                y_calc_start = time.time()
                # Convert to numpy array for efficient min/max calculation
                y_array = np.array(all_y_values, dtype=np.float64)
                y_min = float(np.nanmin(y_array))  # Use nanmin to handle any remaining NaN values
                y_max = float(np.nanmax(y_array))  # Use nanmax to handle any remaining NaN values
                y_calc_time = time.time() - y_calc_start
                logger.debug(f"[DEBUG] Y limits calculation took {y_calc_time:.2f}s (min={y_min:.2f}, max={y_max:.2f})")
                
                # Add a small margin for better visualization
                y_margin = (y_max - y_min) * 0.05 if y_max != y_min else abs(y_max) * 0.05 if y_max != 0 else 1.0
                self.plot_widget.plotItem.vb.setLimits(
                    yMin=y_min - y_margin,
                    yMax=y_max + y_margin
                )
            
            self._playhead_line = pg.InfiniteLine(
                pos=time_range[0],
                angle=90,
                pen=pg.mkPen(color='r', width=2, style=Qt.PenStyle.DashLine)
            )
            self.plot_widget.addItem(self._playhead_line)
            
            # Update axis labels
            start_time = trace.stats.starttime
            self.plot_widget.setLabel('bottom', f'Time (UTC from {start_time.strftime("%Y-%m-%d %H:%M:%S")})')
        
        limits_time = time.time() - limits_start
        logger.debug(f"[DEBUG] Setting limits took {limits_time:.2f}s")
        
        total_time = time.time() - update_start
        logger.info(f"[DEBUG] WaveformViewer.update_waveform complete in {total_time:.2f}s total")
        logger.info(f"Updated waveform display with {len(channels)} channels")
    
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

