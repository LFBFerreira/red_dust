"""Croissant story clocks, pin cues, speed envelopes, and per-station DY Play/Stop sync."""

from __future__ import annotations

import logging
from typing import Any, List

from settings import STATION_COUNT

from .base import _MainWindowBase

logger = logging.getLogger(__name__)


class MainWindowStoryMixin(_MainWindowBase):
    def _connect_story_signals(self) -> None:
        for station, timeline in enumerate(self.story_timelines):
            timeline.play_clicked.connect(lambda s=station: self._on_story_play(s))
            timeline.pause_clicked.connect(lambda s=station: self._on_story_pause(s))
            timeline.stop_clicked.connect(lambda s=station: self._on_story_stop(s))
            timeline.seek_requested.connect(self.story_clocks[station].seek)
            timeline.duration_changed.connect(
                lambda duration_sec, s=station: self._on_story_duration_changed(s, duration_sec)
            )
            timeline.clips_changed.connect(
                lambda s=station: self._on_story_clips_changed(s)
            )
            clock = self.story_clocks[station]
            clock.time_changed.connect(lambda t, s=station: self._on_story_time_changed(s, t))
            clock.state_changed.connect(timeline.update_button_states)
            clock.finished.connect(lambda s=station: self._on_story_finished(s))
            self.pin_cues_list[station].changed.connect(timeline.canvas.update)
            self.speed_envelopes[station].changed.connect(
                lambda s=station: self._on_story_speed_envelope_changed(s)
            )
        self.osc_manager.dy_button_received.connect(self._on_dy_device_button)

    def _other_station_playing(self, station: int) -> bool:
        return any(
            i != station and self.story_clocks[i].get_state() == "playing"
            for i in range(STATION_COUNT)
        )

    def _apply_story_speed(self, station: int, time_sec: float) -> None:
        envelope = self.speed_envelopes[station]
        if envelope.has_points():
            speed = envelope.speed_at(time_sec)
            can_drive = (
                self.story_clocks[station].get_state() == "playing"
                or not self._other_station_playing(station)
            )
            if can_drive and abs(speed - self.playback_controller.get_speed()) >= 0.05:
                self.playback_controller.set_speed(speed, log=False)
                spin = self.playback_controls.speed_spinbox
                spin.blockSignals(True)
                self.playback_controls.set_speed(speed)
                spin.blockSignals(False)
        else:
            speed = self.playback_controller.get_speed()
        self.story_timelines[station].update_speed_display(speed)

    def _on_story_play(self, station: int) -> None:
        self._apply_story_speed(station, self.story_clocks[station].get_current_sec())
        self.story_clocks[station].start()
        if self.story_timelines[station].sync_dy_enabled():
            sent = self.osc_manager.send_dy_command(True, station=station)
            if sent == 0:
                logger.info("Croissant station %d Play: no open Serial port for DY,PLAY", station + 1)

    def _on_story_pause(self, station: int) -> None:
        self.story_clocks[station].pause()
        if self.story_timelines[station].sync_dy_enabled():
            self.osc_manager.send_dy_command(False, station=station)
        self.osc_manager.flush_all_frames()

    def _on_story_stop(self, station: int) -> None:
        self.story_clocks[station].stop()
        if self.story_timelines[station].sync_dy_enabled():
            self.osc_manager.send_dy_command(False, station=station)
        self._apply_story_speed(station, 0.0)
        self.osc_manager.flush_all_frames()

    def _on_dy_device_button(self, station: int, command: str) -> None:
        """Physical DY Play/Stop starts or stops that station's clock (does not echo DY)."""
        if station < 0 or station >= STATION_COUNT:
            return
        if not self.story_timelines[station].sync_dy_enabled():
            return
        cmd = (command or "").strip().upper()
        clock = self.story_clocks[station]
        if cmd == "PLAY":
            if clock.get_state() != "playing":
                self._apply_story_speed(station, clock.get_current_sec())
                clock.start()
        elif cmd == "STOP":
            if clock.get_state() != "stopped":
                clock.stop()
                self._apply_story_speed(station, 0.0)
                self.osc_manager.flush_all_frames()

    def _on_story_finished(self, station: int) -> None:
        if self.story_timelines[station].sync_dy_enabled():
            self.osc_manager.send_dy_command(False, station=station)
        self.osc_manager.flush_all_frames()
        logger.info("Croissant station %d story clock reached the end", station + 1)

    def _on_story_duration_changed(self, station: int, duration_sec: float) -> None:
        self.pin_cues_list[station].set_duration(duration_sec)
        self.speed_envelopes[station].set_duration(duration_sec)
        self.story_clocks[station].set_duration(duration_sec)
        self.story_timelines[station].reload_from_cues()
        self._apply_story_speed(station, self.story_clocks[station].get_current_sec())
        self.osc_manager.flush_all_frames()

    def _on_story_clips_changed(self, station: int) -> None:
        self._apply_story_speed(station, self.story_clocks[station].get_current_sec())
        self.osc_manager.flush_all_frames()

    def _on_story_speed_envelope_changed(self, station: int) -> None:
        self.story_timelines[station].canvas.update()
        self._apply_story_speed(station, self.story_clocks[station].get_current_sec())

    def _on_story_time_changed(self, station: int, time_sec: float) -> None:
        self.story_timelines[station].update_time_display(time_sec)
        self._apply_story_speed(station, time_sec)
        if self.story_clocks[station].get_state() != "playing":
            self.osc_manager.flush_all_frames()

    def _croissant_state_dict(self) -> dict[str, Any]:
        stations: List[dict[str, Any]] = []
        for station in range(STATION_COUNT):
            data = self.pin_cues_list[station].to_dict()
            data["current_sec"] = self.story_clocks[station].get_current_sec()
            data["sync_dy"] = self.story_timelines[station].sync_dy_enabled()
            data.update(self.speed_envelopes[station].to_dict())
            stations.append(data)
        return {"stations": stations}

    def _restore_croissant_state(self, state: dict[str, Any]) -> None:
        data = state.get("croissant")
        if not isinstance(data, dict):
            return
        stations = data.get("stations")
        if not isinstance(stations, list):
            return
        for station, raw in enumerate(stations[:STATION_COUNT]):
            if not isinstance(raw, dict):
                continue
            self.pin_cues_list[station].load_dict(raw)
            self.speed_envelopes[station].set_duration(self.pin_cues_list[station].duration_sec)
            self.speed_envelopes[station].load_dict(raw)
            self.story_clocks[station].set_duration(self.pin_cues_list[station].duration_sec)
            current = raw.get("current_sec", 0.0)
            try:
                self.story_clocks[station].seek(float(current))
            except (TypeError, ValueError):
                self.story_clocks[station].seek(0.0)
            if "sync_dy" in raw:
                self.story_timelines[station].set_sync_dy(bool(raw["sync_dy"]))
            self.story_timelines[station].reload_from_cues()
            self.story_timelines[station].update_button_states(
                self.story_clocks[station].get_state()
            )
            self._apply_story_speed(station, self.story_clocks[station].get_current_sec())
