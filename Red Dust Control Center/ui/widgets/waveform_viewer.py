"""
Waveform Viewer widget for displaying seismic waveforms.
"""
import logging
import time
from datetime import datetime, timezone
from typing import List, Optional, Sequence

import numpy as np
import pyqtgraph as pg
from obspy import Stream, UTCDateTime
from pyqtgraph import AxisItem
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from settings import MAX_WAVEFORM_PLOT_POINTS_PER_CHANNEL

from .channel_colors import FALLBACK_TRACE_COLOR, channel_color_map

logger = logging.getLogger(__name__)

_LOG_TAG = "[multi_ch]"
CHANNEL_LINE_WIDTH = 1


def _downsample_for_plot(
    times: np.ndarray, data: np.ndarray, max_points: int
) -> tuple[np.ndarray, np.ndarray]:
    """Reduce point count for drawing only using min/max per time bin (preserves spikes).

    Does not modify input arrays. Full-resolution data remains in the stream / precalc cache.
    """
    n = int(data.shape[0])
    if max_points < 4 or n <= max_points:
        return times, data

    n_bins = max(1, max_points // 2)
    edges = (np.arange(n_bins + 1, dtype=np.int64) * n // n_bins)
    edges[-1] = n

    idx_list: list[int] = []
    for b in range(n_bins):
        lo = int(edges[b])
        hi = int(edges[b + 1])
        if hi <= lo:
            continue
        if hi - lo == 1:
            idx_list.append(lo)
            continue
        chunk = data[lo:hi]
        if not np.any(np.isfinite(chunk)):
            continue
        rel_min = int(np.nanargmin(chunk))
        rel_max = int(np.nanargmax(chunk))
        i0 = lo + rel_min
        i1 = lo + rel_max
        if i0 == i1:
            idx_list.append(i0)
        elif i0 < i1:
            idx_list.extend((i0, i1))
        else:
            idx_list.extend((i1, i0))

    if not idx_list:
        return times, data

    idx = np.asarray(idx_list, dtype=np.int64)
    return times[idx], data[idx]


def _log_rss_note(where: str) -> None:
    try:
        import psutil
        import os

        rss = psutil.Process(os.getpid()).memory_info().rss
        logger.debug("%s RSS %s: %.1f MiB", _LOG_TAG, where, rss / (1024 * 1024))
    except Exception:
        logger.debug("%s RSS %s: (psutil unavailable)", _LOG_TAG, where)


class WaveformViewer(QWidget):
    """Widget for displaying multi-channel waveform data."""

    loop_range_selected = Signal(UTCDateTime, UTCDateTime)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._stream = None
        self._visible_channels: tuple[str, ...] = ()
        self._playhead_line = None
        self._loop_region = None
        self._plot_items: dict[str, object] = {}
        self._channel_data_cache: dict = {}
        self._overall_x_range = None
        self._overall_y_range = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)

        title = QLabel("<b>Waveform</b>")
        title.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(title)

        self.plot_widget = pg.PlotWidget()
        self.plot_widget.setLabel("left", "Amplitude")
        self.plot_widget.setLabel("bottom", "Time (UTC)")
        self.plot_widget.showGrid(x=True, y=True)
        self.plot_widget.setMouseEnabled(x=True, y=True)

        class TimeAxisItem(AxisItem):
            def tickStrings(self, values, scale, spacing):
                strings = []
                for v in values:
                    try:
                        dt = datetime.fromtimestamp(v, tz=timezone.utc)
                        strings.append(dt.strftime("%H:%M:%S"))
                    except (ValueError, OSError, OverflowError):
                        strings.append("")
                return strings

        self.plot_widget.plotItem.setAxisItems(
            {"bottom": TimeAxisItem(orientation="bottom")}
        )
        self.plot_widget.plotItem.vb.setLimits(xMin=0)

        self.plot_widget.scene().sigMouseClicked.connect(self._on_mouse_click)
        self.plot_widget.scene().sigMouseMoved.connect(self._on_mouse_move)

        self._drag_start = None
        self._is_dragging = False

        layout.addWidget(self.plot_widget, 1)
        self.setLayout(layout)

    def _precalculate_channel_data(self, stream: Stream) -> None:
        precalc_start = time.time()
        logger.info(
            "%s pre-calc traces=%s", _LOG_TAG, len(stream) if stream else 0
        )
        self._channel_data_cache.clear()

        if stream is None or len(stream) == 0:
            return

        channels: dict[str, list] = {}
        for trace in stream:
            channel_id = f"{trace.stats.location}.{trace.stats.channel}"
            channels.setdefault(channel_id, []).append(trace)

        all_x_mins: List[float] = []
        all_x_maxs: List[float] = []
        all_y_mins: List[float] = []
        all_y_maxs: List[float] = []

        for channel_id, traces in channels.items():
            if len(traces) > 1:
                temp_stream = Stream(traces)
                temp_stream.merge(method=1)
                trace = temp_stream[0] if len(temp_stream) > 0 else traces[0]
            else:
                trace = traces[0]

            npts_original = len(trace.data)
            start_timestamp = trace.stats.starttime.timestamp
            sample_rate = trace.stats.sampling_rate
            times_full = start_timestamp + np.arange(npts_original) / sample_rate
            data_full = np.array(trace.data, copy=True, dtype=np.float64)
            SENTINEL_MIN = -2147483640
            SENTINEL_MAX = 2147483640
            sentinel_mask = (data_full <= SENTINEL_MIN) | (data_full >= SENTINEL_MAX)
            data_full[sentinel_mask] = np.nan
            data_full[~np.isfinite(data_full)] = np.nan

            valid_data = data_full[np.isfinite(data_full)]
            if len(valid_data) > 0:
                channel_y_min = float(np.nanmin(valid_data))
                channel_y_max = float(np.nanmax(valid_data))
            else:
                channel_y_min = 0.0
                channel_y_max = 0.0

            channel_x_min = float(times_full[0])
            channel_x_max = float(times_full[-1])
            all_x_mins.append(channel_x_min)
            all_x_maxs.append(channel_x_max)
            all_y_mins.append(channel_y_min)
            all_y_maxs.append(channel_y_max)

            self._channel_data_cache[channel_id] = {
                "times_full": times_full,
                "data_full": data_full,
                "npts_original": npts_original,
                "x_min": channel_x_min,
                "x_max": channel_x_max,
                "y_min": channel_y_min,
                "y_max": channel_y_max,
            }

        if all_x_mins and all_x_maxs and all_y_mins and all_y_maxs:
            self._overall_x_range = (min(all_x_mins), max(all_x_maxs))
            self._overall_y_range = (min(all_y_mins), max(all_y_maxs))
        else:
            self._overall_x_range = None
            self._overall_y_range = None

        logger.info(
            "%s pre-calc done channels=%s in %.2fs cache_keys=%s",
            _LOG_TAG,
            len(self._channel_data_cache),
            time.time() - precalc_start,
            len(self._channel_data_cache),
        )
        _log_rss_note("after_precalc")

    def update_waveform(self, stream: Stream, visible_channels: Sequence[str]) -> None:
        update_start = time.time()
        visible_set = tuple(visible_channels)
        self._visible_channels = visible_set

        logger.info(
            "%s update_waveform traces=%s visible=%s",
            _LOG_TAG,
            len(stream) if stream else 0,
            len(visible_set),
        )

        stream_changed = False
        if stream is None:
            if len(self._channel_data_cache) > 0:
                stream_changed = True
        elif self._stream is None or stream is not self._stream:
            stream_changed = True
        else:
            current_channels = {
                f"{tr.stats.location}.{tr.stats.channel}" for tr in stream
            }
            if current_channels != set(self._channel_data_cache.keys()):
                stream_changed = True

        if stream_changed:
            logger.debug("%s stream_changed -> precalc", _LOG_TAG)
            self._precalculate_channel_data(stream)

        self._stream = stream

        t0 = time.time()
        self.plot_widget.clear()
        self._plot_items.clear()
        self._playhead_line = None
        self._loop_region = None
        logger.debug("%s plot clear %.3fs", _LOG_TAG, time.time() - t0)

        if stream is None or len(stream) == 0 or len(self._channel_data_cache) == 0:
            logger.warning("No stream data to display")
            return

        self.plot_widget.setLabel("left", "Amplitude (Counts)")

        sorted_ids = sorted(self._channel_data_cache.keys())
        colors_by_channel = channel_color_map(sorted_ids)

        visible_list = [cid for cid in visible_set if cid in self._channel_data_cache]
        total_points = 0
        plot_t0 = time.time()

        max_plot = MAX_WAVEFORM_PLOT_POINTS_PER_CHANNEL
        for channel_id in visible_list:
            channel_data = self._channel_data_cache[channel_id]
            times_full = channel_data["times_full"]
            data_full = channel_data["data_full"]
            npts = channel_data["npts_original"]
            times_plot, data_plot = _downsample_for_plot(
                times_full, data_full, max_plot
            )
            total_points += int(times_plot.shape[0])
            color = colors_by_channel.get(channel_id, FALLBACK_TRACE_COLOR)
            plot_item = self.plot_widget.plot(
                times_plot,
                data_plot,
                pen=pg.mkPen(color=color, width=CHANNEL_LINE_WIDTH),
            )
            self._plot_items[channel_id] = plot_item
            plot_n = int(times_plot.shape[0])
            if plot_n < npts:
                logger.debug(
                    "%s plotted %s npts=%s (display %s)",
                    _LOG_TAG,
                    channel_id,
                    f"{npts:,}",
                    f"{plot_n:,}",
                )
            else:
                logger.debug(
                    "%s plotted %s npts=%s", _LOG_TAG, channel_id, f"{npts:,}"
                )

        logger.info(
            "%s plotted %s channels total_pts=%s in %.2fs",
            _LOG_TAG,
            len(visible_list),
            f"{total_points:,}",
            time.time() - plot_t0,
        )
        _log_rss_note("after_plot")

        if visible_list:
            xs = [self._channel_data_cache[c]["x_min"] for c in visible_list]
            xs2 = [self._channel_data_cache[c]["x_max"] for c in visible_list]
            ys = [self._channel_data_cache[c]["y_min"] for c in visible_list]
            ys2 = [self._channel_data_cache[c]["y_max"] for c in visible_list]
            vx0, vx1 = min(xs), max(xs2)
            vy0, vy1 = min(ys), max(ys2)
            x_margin = (vx1 - vx0) * 0.01 if vx1 > vx0 else 1.0
            y_margin = (
                (vy1 - vy0) * 0.05
                if vy1 != vy0
                else (abs(vy1) * 0.05 if vy1 != 0 else 1.0)
            )
            self.plot_widget.plotItem.vb.setLimits(
                xMin=vx0 - x_margin,
                xMax=vx1 + x_margin,
                yMin=vy0 - y_margin,
                yMax=vy1 + y_margin,
            )
            self.plot_widget.plotItem.vb.setRange(
                xRange=(vx0 - x_margin, vx1 + x_margin),
                yRange=(vy0 - y_margin, vy1 + y_margin),
                padding=0,
            )
            playhead_pos = vx0
            self._playhead_line = pg.InfiniteLine(
                pos=playhead_pos,
                angle=90,
                pen=pg.mkPen(color="r", width=2, style=Qt.PenStyle.DashLine),
            )
            self.plot_widget.addItem(self._playhead_line)
        else:
            if self._overall_x_range is not None and self._overall_y_range is not None:
                x_margin = (self._overall_x_range[1] - self._overall_x_range[0]) * 0.01
                y_margin = (
                    (self._overall_y_range[1] - self._overall_y_range[0]) * 0.05
                    if self._overall_y_range[1] != self._overall_y_range[0]
                    else 1.0
                )
                ox0 = self._overall_x_range[0] - x_margin
                ox1 = self._overall_x_range[1] + x_margin
                oy0 = self._overall_y_range[0] - y_margin
                oy1 = self._overall_y_range[1] + y_margin
                self.plot_widget.plotItem.vb.setLimits(
                    xMin=ox0, xMax=ox1, yMin=oy0, yMax=oy1
                )
                self.plot_widget.plotItem.vb.setRange(
                    xRange=(ox0, ox1), yRange=(oy0, oy1), padding=0
                )

        logger.info(
            "%s update_waveform complete %.2fs plot_items=%s",
            _LOG_TAG,
            time.time() - update_start,
            len(self._plot_items),
        )

    def update_playhead(self, timestamp: UTCDateTime) -> None:
        if self._playhead_line is not None:
            self._playhead_line.setValue(timestamp.timestamp)

    def set_loop_range(
        self, start: Optional[UTCDateTime] = None, end: Optional[UTCDateTime] = None
    ) -> None:
        if self._loop_region is not None:
            self.plot_widget.removeItem(self._loop_region)
            self._loop_region = None
        if start is not None and end is not None:
            self._loop_region = pg.LinearRegionItem(
                values=[start.timestamp, end.timestamp],
                brush=pg.mkBrush(color=(255, 255, 0, 50)),
                pen=pg.mkPen(color="y", width=1),
            )
            self.plot_widget.addItem(self._loop_region)

    def _on_mouse_click(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = self.plot_widget.plotItem.vb.mapSceneToView(event.scenePos())
            if self.plot_widget.plotItem.vb.sceneBoundingRect().contains(
                event.scenePos()
            ):
                self._drag_start = pos.x()
                self._is_dragging = True

    def _on_mouse_move(self, event):
        if self._is_dragging and self._drag_start is not None:
            pass

    def mouseReleaseEvent(self, event):
        if self._is_dragging and self._drag_start is not None:
            pos = self.plot_widget.plotItem.vb.mapSceneToView(event.pos())
            if self._drag_start != pos.x():
                start_time = UTCDateTime(self._drag_start)
                end_time = UTCDateTime(pos.x())
                if start_time > end_time:
                    start_time, end_time = end_time, start_time
                self.loop_range_selected.emit(start_time, end_time)
            self._is_dragging = False
            self._drag_start = None
        super().mouseReleaseEvent(event)
