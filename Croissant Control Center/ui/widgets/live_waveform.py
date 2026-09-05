"""LilyGO-style live waveform strip: a paging time window drawn up to the playhead."""

from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Optional, Sequence

import numpy as np
import pyqtgraph as pg
from obspy import Stream, UTCDateTime
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

from settings import (
    FULLSCREEN_WAVEFORM_WINDOW_SEC,
    MAX_WAVEFORM_PLOT_POINTS_PER_CHANNEL,
)

from .channel_colors import FALLBACK_TRACE_COLOR, channel_color_map
from .waveform_viewer import _downsample_for_plot, configure_plot_widget

CHANNEL_LINE_WIDTH = 2
_SENTINEL_MIN = -2147483640
_SENTINEL_MAX = 2147483640
_MIN_REDRAW_INTERVAL_S = 1.0 / 20.0


def _channel_id(trace) -> str:
    return f"{trace.stats.location}.{trace.stats.channel}"


def _arrays_from_stream(
    stream: Stream, channels: Sequence[str]
) -> dict[str, dict]:
    wanted = set(channels)
    grouped: dict[str, list] = {}
    for trace in stream:
        cid = _channel_id(trace)
        if cid not in wanted:
            continue
        grouped.setdefault(cid, []).append(trace)

    cache: dict[str, dict] = {}
    for cid, traces in grouped.items():
        if len(traces) > 1:
            merged = Stream(traces)
            merged.merge(method=1)
            trace = merged[0] if len(merged) > 0 else traces[0]
        else:
            trace = traces[0]
        npts = int(len(trace.data))
        if npts < 1:
            continue
        times = trace.stats.starttime.timestamp + np.arange(npts) / float(
            trace.stats.sampling_rate
        )
        data = np.array(trace.data, copy=True, dtype=np.float64)
        sentinel = (data <= _SENTINEL_MIN) | (data >= _SENTINEL_MAX)
        data[sentinel] = np.nan
        data[~np.isfinite(data)] = np.nan
        cache[cid] = {"times": times, "data": data}
    return cache


class LiveWaveformStrip(QWidget):
    """Fixed-width paging plot: draw the current window from the left up to now."""

    def __init__(self, parent=None, window_sec: float = FULLSCREEN_WAVEFORM_WINDOW_SEC):
        super().__init__(parent)
        self._window_sec = float(window_sec)
        self._x_max = self._window_sec / 60.0
        self._cache: dict[str, dict] = {}
        self._channels: tuple[str, ...] = ()
        self._color_ids: tuple[str, ...] = ()
        self._span: Optional[tuple[float, float]] = None
        self._source_key = None
        self._page_index: Optional[int] = None
        self._plot_items: dict[str, object] = {}
        self._playhead_line = None
        self._last_curve_draw = 0.0
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        self._title_label = QLabel("<b>Waveform</b>")
        self._title_label.setStyleSheet("font-size: 18pt;")
        layout.addWidget(self._title_label)

        self.plot_widget = pg.PlotWidget()
        configure_plot_widget(self.plot_widget)
        self.plot_widget.setLabel("left", "Amplitude (Counts)")
        self.plot_widget.setLabel("bottom", "Time (min)")
        self.plot_widget.showGrid(x=True, y=True)
        self.plot_widget.setMouseEnabled(x=False, y=False)
        self.plot_widget.setMenuEnabled(False)
        self.plot_widget.hideButtons()
        vb = self.plot_widget.plotItem.vb
        vb.setLimits(xMin=0.0, xMax=self._x_max)
        vb.setRange(xRange=(0.0, self._x_max), padding=0)
        layout.addWidget(self.plot_widget, 1)

    def clear(self) -> None:
        self._cache = {}
        self._channels = ()
        self._color_ids = ()
        self._span = None
        self._source_key = None
        self._page_index = None
        self._plot_items.clear()
        self._playhead_line = None
        self.plot_widget.clear()
        self._title_label.setText("<b>Waveform</b>")

    def set_source(
        self,
        stream: Optional[Stream],
        channels: Sequence[str],
        time_span: Optional[tuple[UTCDateTime, UTCDateTime]],
        color_channel_ids: Optional[Sequence[str]] = None,
    ) -> bool:
        """Cache selected channels inside ``time_span``. Returns False if empty."""
        if stream is None or len(stream) == 0 or not channels or time_span is None:
            self.clear()
            return False

        start, end = time_span
        if start > end:
            start, end = end, start
        color_ids = tuple(color_channel_ids) if color_channel_ids else tuple(channels)
        key = (id(stream), tuple(channels), color_ids, float(start), float(end))
        if key == self._source_key and self._cache:
            return True

        window = stream.slice(start, end)
        cache = _arrays_from_stream(window, channels) if window is not None else {}
        if not cache:
            self.clear()
            return False

        self._source_key = key
        self._cache = cache
        self._channels = tuple(cid for cid in channels if cid in cache)
        self._color_ids = color_ids
        self._span = (float(start), float(end))
        self._page_index = None
        self._rebuild_plot_items()
        return True

    def update_playhead(self, timestamp: UTCDateTime) -> None:
        if not self._cache or self._span is None:
            return

        now_t = float(timestamp.timestamp)
        span0, span1 = self._span
        now_t = min(max(now_t, span0), span1)
        elapsed = now_t - span0
        page = int(elapsed // self._window_sec)
        page_start = span0 + page * self._window_sec
        page_end = min(page_start + self._window_sec, span1)
        rel = now_t - page_start

        page_changed = page != self._page_index
        if page_changed:
            self._page_index = page
            self._set_page_y_range(page_start, page_end)
            self._last_curve_draw = 0.0
            self._title_label.setText(
                "<b>Waveform</b>  ·  "
                f"{self._fmt_utc(page_start)}  –  {self._fmt_utc(page_end)}  "
                f"({self._x_max:.0f} min)"
            )

        if self._playhead_line is not None:
            self._playhead_line.setValue(rel / 60.0)

        now_mono = time.monotonic()
        if not page_changed and (now_mono - self._last_curve_draw) < _MIN_REDRAW_INTERVAL_S:
            return
        self._last_curve_draw = now_mono
        self._draw_traces(page_start, now_t)

    def _rebuild_plot_items(self) -> None:
        self.plot_widget.clear()
        self._plot_items.clear()
        self._playhead_line = None
        color_ids = self._color_ids or tuple(sorted(self._cache.keys()))
        colors = channel_color_map(sorted(color_ids))
        for cid in self._channels:
            color = colors.get(cid, FALLBACK_TRACE_COLOR)
            item = self.plot_widget.plot(
                [],
                [],
                pen=pg.mkPen(color=color, width=CHANNEL_LINE_WIDTH),
            )
            self._plot_items[cid] = item
        self._playhead_line = pg.InfiniteLine(
            pos=0.0,
            angle=90,
            pen=pg.mkPen(color="r", width=2, style=Qt.PenStyle.DashLine),
        )
        self.plot_widget.addItem(self._playhead_line)
        vb = self.plot_widget.plotItem.vb
        vb.setLimits(xMin=0.0, xMax=self._x_max)
        vb.setRange(xRange=(0.0, self._x_max), padding=0)

    def _set_page_y_range(self, page_start: float, page_end: float) -> None:
        y_min = None
        y_max = None
        for cid in self._channels:
            channel = self._cache[cid]
            times = channel["times"]
            data = channel["data"]
            i0 = int(np.searchsorted(times, page_start, side="left"))
            i1 = int(np.searchsorted(times, page_end, side="right"))
            if i1 <= i0:
                continue
            chunk = data[i0:i1]
            finite = chunk[np.isfinite(chunk)]
            if finite.size == 0:
                continue
            lo = float(np.min(finite))
            hi = float(np.max(finite))
            y_min = lo if y_min is None else min(y_min, lo)
            y_max = hi if y_max is None else max(y_max, hi)
        if y_min is None or y_max is None:
            y_min, y_max = -1.0, 1.0
        if y_min == y_max:
            pad = abs(y_min) * 0.05 if y_min != 0 else 1.0
            y_min -= pad
            y_max += pad
        else:
            pad = (y_max - y_min) * 0.08
            y_min -= pad
            y_max += pad
        vb = self.plot_widget.plotItem.vb
        vb.setLimits(xMin=0.0, xMax=self._x_max, yMin=y_min, yMax=y_max)
        vb.setRange(xRange=(0.0, self._x_max), yRange=(y_min, y_max), padding=0)

    def _draw_traces(self, page_start: float, now_t: float) -> None:
        for cid in self._channels:
            item = self._plot_items.get(cid)
            if item is None:
                continue
            channel = self._cache[cid]
            times = channel["times"]
            data = channel["data"]
            i0 = int(np.searchsorted(times, page_start, side="left"))
            i1 = int(np.searchsorted(times, now_t, side="right"))
            if i1 <= i0:
                item.setData([], [])
                continue
            x = (times[i0:i1] - page_start) / 60.0
            y = data[i0:i1]
            x, y = _downsample_for_plot(x, y, MAX_WAVEFORM_PLOT_POINTS_PER_CHANNEL)
            item.setData(x, y)

    @staticmethod
    def _fmt_utc(timestamp: float) -> str:
        try:
            dt = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            return dt.strftime("%H:%M:%S")
        except (ValueError, OSError, OverflowError):
            return "--:--:--"
