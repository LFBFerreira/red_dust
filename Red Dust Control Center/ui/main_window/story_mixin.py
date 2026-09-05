"""Dust Devil story clock, pin cues, speed envelope, and DY Play/Stop sync."""

from __future__ import annotations

import logging
from typing import Any

from .base import _MainWindowBase

logger = logging.getLogger(__name__)


class MainWindowStoryMixin(_MainWindowBase):
    def _connect_story_signals(self) -> None:
        self.story_timeline.play_clicked.connect(self._on_story_play)
        self.story_timeline.pause_clicked.connect(self._on_story_pause)
        self.story_timeline.stop_clicked.connect(self._on_story_stop)
        self.story_timeline.seek_requested.connect(self.story_clock.seek)
        self.story_timeline.duration_changed.connect(self._on_story_duration_changed)
        self.story_timeline.clips_changed.connect(self._on_story_clips_changed)
        self.story_clock.time_changed.connect(self._on_story_time_changed)
        self.story_clock.state_changed.connect(self.story_timeline.update_button_states)
        self.story_clock.finished.connect(self._on_story_finished)
        self.pin_cues.changed.connect(self._on_story_cues_model_changed)
        self.speed_envelope.changed.connect(self._on_story_speed_envelope_changed)
        self.osc_manager.dy_button_received.connect(self._on_dy_device_button)

    def _ensure_waveform_playing(self) -> None:
        if not self.waveform_model.get_selected_channels():
            return
        if self.playback_controller.get_playback_state() != "playing":
            self.playback_controller.start()

    def _apply_story_speed(self, time_sec: float) -> None:
        if self.speed_envelope.has_points():
            speed = self.speed_envelope.speed_at(time_sec)
            if abs(speed - self.playback_controller.get_speed()) >= 0.05:
                self.playback_controller.set_speed(speed, log=False)
            spin = self.playback_controls.speed_spinbox
            spin.blockSignals(True)
            self.playback_controls.set_speed(speed)
            spin.blockSignals(False)
        else:
            speed = self.playback_controller.get_speed()
        self.story_timeline.update_speed_display(speed)

    def _on_story_play(self) -> None:
        self._apply_story_speed(self.story_clock.get_current_sec())
        self._ensure_waveform_playing()
        self.story_clock.start()
        if self.story_timeline.sync_dy_enabled():
            sent = self.osc_manager.send_dy_command(True)
            if sent == 0:
                logger.info("Dust Devil Play: no open Serial port for DY,PLAY")

    def _on_story_pause(self) -> None:
        self.story_clock.pause()
        if self.playback_controller.get_playback_state() == "playing":
            self.playback_controller.pause()
        if self.story_timeline.sync_dy_enabled():
            self.osc_manager.send_dy_command(False)
        self.osc_manager.flush_all_frames()

    def _on_story_stop(self) -> None:
        self._skip_next_story_speed = True
        self.story_clock.stop()
        if self.story_timeline.sync_dy_enabled():
            self.osc_manager.send_dy_command(False)
        self.osc_manager.flush_all_frames()

    def _on_dy_device_button(self, command: str) -> None:
        """Physical DY Play/Stop starts or stops the story clock (does not echo DY)."""
        if not self.story_timeline.sync_dy_enabled():
            return
        cmd = (command or "").strip().upper()
        if cmd == "PLAY":
            if self.story_clock.get_state() != "playing":
                self._apply_story_speed(self.story_clock.get_current_sec())
                self._ensure_waveform_playing()
                self.story_clock.start()
        elif cmd == "STOP":
            if self.story_clock.get_state() != "stopped":
                self._skip_next_story_speed = True
                self.story_clock.stop()
                self.osc_manager.flush_all_frames()

    def _on_story_finished(self) -> None:
        sent = self.osc_manager.send_dy_command(False)
        self.osc_manager.flush_all_frames()
        logger.info(
            "Dust Devil story clock reached the end; DY,STOP sent to %s serial object(s)",
            sent,
        )

    def _on_story_duration_changed(self, duration_sec: float) -> None:
        self.pin_cues.set_duration(duration_sec)
        self.speed_envelope.set_duration(duration_sec)
        self.story_clock.set_duration(duration_sec)
        self.story_timeline.reload_from_cues()
        self._apply_story_speed(self.story_clock.get_current_sec())
        self.osc_manager.flush_all_frames()

    def _on_story_clips_changed(self) -> None:
        self._apply_story_speed(self.story_clock.get_current_sec())
        self.osc_manager.flush_all_frames()

    def _on_story_cues_model_changed(self) -> None:
        self.story_timeline.canvas.update()

    def _on_story_speed_envelope_changed(self) -> None:
        self.story_timeline.canvas.update()
        self._apply_story_speed(self.story_clock.get_current_sec())

    def _on_story_time_changed(self, time_sec: float) -> None:
        self.story_timeline.update_time_display(time_sec)
        if getattr(self, "_skip_next_story_speed", False):
            self._skip_next_story_speed = False
            self.story_timeline.update_speed_display(
                self.playback_controller.get_speed()
            )
        else:
            self._apply_story_speed(time_sec)
        if self.story_clock.get_state() != "playing":
            self.osc_manager.flush_all_frames()

    def _dust_devil_state_dict(self) -> dict[str, Any]:
        data = self.pin_cues.to_dict()
        data["current_sec"] = self.story_clock.get_current_sec()
        data["sync_dy"] = self.story_timeline.sync_dy_enabled()
        data.update(self.speed_envelope.to_dict())
        return data

    def _restore_dust_devil_state(self, state: dict[str, Any]) -> None:
        data = state.get("dust_devil")
        if not isinstance(data, dict):
            return
        self.pin_cues.load_dict(data)
        self.speed_envelope.set_duration(self.pin_cues.duration_sec)
        self.speed_envelope.load_dict(data)
        self.story_clock.set_duration(self.pin_cues.duration_sec)
        current = data.get("current_sec", 0.0)
        try:
            self.story_clock.seek(float(current))
        except (TypeError, ValueError):
            self.story_clock.seek(0.0)
        if "sync_dy" in data:
            self.story_timeline.set_sync_dy(bool(data["sync_dy"]))
        self.story_timeline.reload_from_cues()
        self.story_timeline.update_button_states(self.story_clock.get_state())
        self._apply_story_speed(self.story_clock.get_current_sec())
