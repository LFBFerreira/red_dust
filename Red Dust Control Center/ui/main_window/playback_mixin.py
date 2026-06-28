"""Playback controls, playhead, channels, and loop range."""

import logging
from typing import Optional

from obspy import UTCDateTime
from PySide6.QtWidgets import QMessageBox

from .base import _MainWindowBase
from .constants import (
    _LOG_TAG,
    _WARN_NO_CHANNELS_MSG,
    _WARN_NO_CHANNELS_TITLE,
)

logger = logging.getLogger(__name__)


class MainWindowPlaybackMixin(_MainWindowBase):
    """Connects playback UI to the waveform model and OSC streaming."""

    def _refresh_value_display(self, timestamp: Optional[UTCDateTime] = None) -> None:
        """Refresh raw/normalized value label for current (or given) playhead time."""
        if not self.waveform_model.get_selected_channels():
            self.playback_controls.update_value_display([])
            return
        ts = timestamp
        if ts is None:
            ts = self.playback_controller.get_current_timestamp()
        if ts is None:
            tr = self.waveform_model.get_time_range()
            if tr is not None:
                ts = tr[0]
        if ts is None:
            self.playback_controls.update_value_display([])
            return
        self.playback_controls.update_value_display(
            self.waveform_model.get_selected_channel_value_pairs(ts)
        )

    def _on_playhead_updated(self, timestamp):
        """Handle playhead position update."""
        self.waveform_viewer.update_playhead(timestamp)

        time_range = self.waveform_model.get_time_range()
        if time_range:
            self.playback_controls.set_data_time_range(time_range[0], time_range[1])
            self.playback_controls.update_time_display(
                timestamp, time_range[0], time_range[1]
            )
            self.playback_controls.update_position_slider(
                timestamp, time_range[0], time_range[1]
            )

        self._refresh_value_display(timestamp)

    def _on_play_requested(self) -> None:
        if not self.waveform_model.get_selected_channels():
            QMessageBox.warning(
                self, _WARN_NO_CHANNELS_TITLE, _WARN_NO_CHANNELS_MSG
            )
            return
        self.playback_controller.start()

    def _on_channels_selection_changed(self, selected: list) -> None:
        logger.debug(
            "%s _on_channels_selection_changed n=%s",
            _LOG_TAG,
            len(selected),
        )
        self.waveform_model.set_selected_channels(selected)
        synced = self.waveform_model.get_selected_channels()
        if len(synced) != len(selected):
            self.playback_controls.set_selected_channels(synced)
        stream = self.waveform_model.get_stream()
        if stream:
            self.waveform_viewer.update_waveform(stream, synced)
        if not synced:
            self.playback_controller.stop()
        self._sync_interactive_objects_to_playback_channels(set(synced))
        self._update_metadata()
        self._update_object_card_channels()
        self._refresh_value_display()

    def _on_position_slider_changed(self, value: int) -> None:
        """Handle position slider change."""
        if self.playback_controls._position_slider_updating:
            return

        if not self.waveform_model.get_selected_channels():
            QMessageBox.warning(
                self, _WARN_NO_CHANNELS_TITLE, _WARN_NO_CHANNELS_MSG
            )
            self.playback_controls._position_slider_updating = True
            self.playback_controls.position_slider.blockSignals(True)
            self.playback_controls.position_slider.setValue(0)
            self.playback_controls.position_slider.blockSignals(False)
            self.playback_controls._position_slider_updating = False
            return

        time_range = self.waveform_model.get_time_range()
        if not time_range:
            return

        start_time, end_time = time_range

        percentage = value / 1000.0
        total_duration = end_time - start_time
        if total_duration <= 0:
            return

        offset = total_duration * percentage
        target_timestamp = start_time + offset

        current_time = self.playback_controller.get_current_timestamp()
        if current_time is not None:
            if not isinstance(current_time, UTCDateTime):
                current_time = UTCDateTime(current_time)
            time_diff = abs((target_timestamp - current_time))
            min_diff = total_duration * 0.001
            if time_diff < min_diff:
                return

        self.playback_controller.seek(target_timestamp)

    def _on_playback_state_changed(self, state: str):
        """Handle playback state change."""
        self.playback_controls.set_playback_state(state)

        if state == "playing":
            self.osc_manager.start_streaming()
        elif state == "stopped":
            self.osc_manager.stop_streaming()

    def _sync_loop_visualization(self) -> None:
        """Push loop marker state from controls into the waveform viewer."""
        start, end, start_set, end_set = (
            self.playback_controls.get_loop_markers_from_inputs()
        )
        loop_enabled = self.playback_controller.is_loop_enabled()
        self.waveform_viewer.set_loop_markers(
            start=start,
            end=end,
            start_set=start_set,
            end_set=end_set,
            loop_enabled=loop_enabled,
        )

    def _on_loop_markers_changed(self) -> None:
        """Disable looping when start/end inputs no longer form a valid range."""
        if self.playback_controller.is_loop_enabled():
            if not self.playback_controls.is_loop_range_valid():
                self.playback_controller.clear_loop()
                self.playback_controls.set_loop_enabled(False)
        elif self.playback_controller.get_loop_range() is not None:
            if not self.playback_controls.is_loop_range_valid():
                self.playback_controller.clear_loop()
        self._sync_loop_visualization()

    def _apply_loop_range(self, start, end, enable_loop: bool = False) -> None:
        """Set loop range on controller and UI, then refresh viewer markers."""
        if start > end:
            start, end = end, start
        try:
            self.playback_controller.set_loop_range(start, end)
            if enable_loop:
                self.playback_controller.enable_loop(True)
                self.playback_controls.set_loop_enabled(True)
            self.playback_controls.update_loop_display(start, end)
            self._sync_loop_visualization()
            logger.info("Loop range set: %s to %s", start, end)
        except ValueError as e:
            logger.warning("Invalid loop range: %s", e)
            QMessageBox.warning(self, "Loop range", str(e))

    def _on_loop_range_selected(self, start, end):
        """Handle loop range selection from waveform viewer."""
        self._apply_loop_range(start, end, enable_loop=True)

    def _on_loop_range_changed(self, start, end):
        """Handle loop range entered in playback controls."""
        self._apply_loop_range(start, end, enable_loop=False)

    def _on_loop_toggled(self, enabled: bool) -> None:
        """Enable/disable looping; apply input range when turning on."""
        if enabled:
            loop_range = self.playback_controls.get_loop_range_from_inputs()
            if loop_range is None:
                time_range = self.waveform_model.get_time_range()
                if time_range:
                    loop_range = time_range
                    try:
                        self.playback_controller.set_loop_range(*loop_range)
                    except ValueError as e:
                        QMessageBox.warning(self, "Loop range", str(e))
                        self.playback_controls.set_loop_enabled(False)
                        return
            elif loop_range:
                try:
                    self.playback_controller.set_loop_range(*loop_range)
                except ValueError as e:
                    QMessageBox.warning(self, "Loop range", str(e))
                    self.playback_controls.set_loop_enabled(False)
                    return
        self.playback_controller.enable_loop(enabled)
        self._sync_loop_visualization()

    def _current_playhead_timestamp(self) -> Optional[UTCDateTime]:
        ts = self.playback_controller.get_current_timestamp()
        if ts is not None:
            return ts
        time_range = self.waveform_model.get_time_range()
        if time_range:
            return time_range[0]
        return None

    def _on_capture_loop_start(self) -> None:
        ts = self._current_playhead_timestamp()
        if ts is None:
            return
        self.playback_controls.set_loop_endpoint_from_timestamp("start", ts)

    def _on_capture_loop_end(self) -> None:
        ts = self._current_playhead_timestamp()
        if ts is None:
            return
        self.playback_controls.set_loop_endpoint_from_timestamp("end", ts)
