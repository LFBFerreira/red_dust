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
        
        # Title
        title = QLabel("<b>Waveform</b>")
        layout.addWidget(title)
        
        # PyQtGraph plot widget
        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel('left', 'Amplitude')
        self.plot_widget.setLabel('bottom', 'Time (UTC)')
        self.plot_widget.showGrid(x=True, y=True)
        self.plot_widget.setMouseEnabled(x=True, y=True)
        
        # Enable click-drag for loop selection
        self.plot_widget.scene().sigMouseClicked.connect(self._on_mouse_click)
        self.plot_widget.scene().sigMouseMoved.connect(self._on_mouse_move)
        
        self._drag_start = None
        self._is_dragging = False
        
        layout.addWidget(self.plot_widget)
        self.setLayout(layout)
    
    def update_waveform(self, stream: Stream, active_channel: str = None) -> None:
        """
        Update waveform display with new stream data.
        
        Args:
            stream: ObsPy Stream containing waveform data
            active_channel: Active channel identifier (e.g., "03.BHU")
        """
        self._stream = stream
        self._active_channel = active_channel
        
        # Clear existing plots
        self.plot_widget.clear()
        self._plot_items.clear()
        self._playhead_line = None
        self._loop_region = None
        
        if stream is None or len(stream) == 0:
            return
        
        # Group traces by channel
        channels = {}
        for trace in stream:
            channel_id = f"{trace.stats.location}.{trace.stats.channel}"
            if channel_id not in channels:
                channels[channel_id] = []
            channels[channel_id].append(trace)
        
        # Plot each channel
        colors = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd', '#8c564b']
        color_idx = 0
        
        for channel_id, traces in channels.items():
            # Merge traces if multiple (ObsPy handles this)
            if len(traces) > 1:
                # Use ObsPy's merge method
                temp_stream = Stream(traces)
                temp_stream.merge(method=1)  # Fill gaps with NaN
                trace = temp_stream[0] if len(temp_stream) > 0 else traces[0]
            else:
                trace = traces[0]
            
            # Prepare data
            times = np.array([(trace.stats.starttime + i / trace.stats.sampling_rate).timestamp 
                            for i in range(len(trace.data))])
            data = trace.data
            
            # Choose color and pen width
            is_active = (channel_id == active_channel)
            color = colors[color_idx % len(colors)]
            width = 3 if is_active else 1
            
            # Plot
            plot_item = self.plot_widget.plot(times, data, pen=pg.mkPen(color=color, width=width))
            self._plot_items[channel_id] = plot_item
            
            color_idx += 1
        
        # Add playhead line
        if len(stream) > 0:
            trace = stream[0]
            time_range = (trace.stats.starttime.timestamp, trace.stats.endtime.timestamp)
            self._playhead_line = pg.InfiniteLine(
                pos=time_range[0],
                angle=90,
                pen=pg.mkPen(color='r', width=2, style=Qt.PenStyle.DashLine)
            )
            self.plot_widget.addItem(self._playhead_line)
        
        # Update axis labels
        if len(stream) > 0:
            trace = stream[0]
            start_time = trace.stats.starttime
            self.plot_widget.setLabel('bottom', f'Time (UTC from {start_time.strftime("%Y-%m-%d %H:%M:%S")})')
        
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

