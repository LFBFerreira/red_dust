"""Interactive object cards and per-object OSC/serial streaming."""

from __future__ import annotations

import logging
from typing import List

from core.pin_stream import pin_rows_from_dicts
from core.serial_object import SerialObject
from settings import SERIAL_BAUDRATE
from .base import _MainWindowBase

logger = logging.getLogger(__name__)


class MainWindowObjectsMixin(_MainWindowBase):
    """Wires ObjectCardsContainer to OSCManager."""

    def _valid_selected_channels_for_io(self) -> List[str]:
        sel = self.waveform_model.get_selected_channels()
        valid = set(self.waveform_model.get_all_channels())
        return [c for c in sel if c in valid]

    def _pin_rows_core(self, config: dict):
        raw = config.get("pin_rows") or []
        if not raw:
            return []
        return pin_rows_from_dicts(raw)

    def _on_object_added(self, object_id: str):
        """Handle new object added."""
        card = self.object_cards.get_card(object_id)
        if not card:
            return

        card.streaming_started.connect(self._on_card_streaming_started)
        card.streaming_stopped.connect(self._on_card_streaming_stopped)

        config = card.get_config()
        comm_type = config.get("type", "OSC")
        pin_rows = self._pin_rows_core(config)

        if comm_type == "OSC":
            self.osc_manager.add_osc_object(
                config["object_id"],
                config["address"],
                config["host"],
                config["port"],
                pin_rows,
            )
        elif comm_type == "Serial":
            port = config.get("port", "")
            if port and port != "Select port...":
                self.osc_manager.add_serial_object(
                    config["object_id"],
                    port,
                    config.get("baudrate", SERIAL_BAUDRATE),
                    pin_rows,
                )
                obj = self.osc_manager.get_object(object_id)
                if obj and isinstance(obj, SerialObject):
                    if obj.open_port():
                        self.osc_manager.object_connection_state_changed.emit(
                            object_id, True
                        )
                        card.set_connection_state(True)
                    else:
                        self.osc_manager.object_connection_state_changed.emit(
                            object_id, False
                        )
                        card.set_connection_state(False)
            else:
                self.osc_manager.add_serial_object(
                    config["object_id"],
                    "Select port...",
                    config.get("baudrate", SERIAL_BAUDRATE),
                    pin_rows,
                )
                card.set_connection_state(False)
        else:
            logger.error("Unknown communication type: %s", comm_type)
            return

        if config.get("streaming_enabled", False):
            self.osc_manager.start_object_streaming(object_id)
        else:
            self.osc_manager.stop_object_streaming(object_id)

    def _on_object_removed(self, object_id: str):
        """Handle object removed."""
        self.osc_manager.remove_object(object_id)

    def _on_object_config_changed(self, object_id: str):
        """Handle object configuration change."""
        card = self.object_cards.get_card(object_id)
        if not card:
            return

        config = card.get_config()
        obj = self.osc_manager.get_object(object_id)
        if not obj:
            return

        pin_rows = self._pin_rows_core(config)
        self.osc_manager.update_object_pin_rows(object_id, pin_rows)

        comm_type = config.get("type", "OSC")
        needs_recreate = False

        if comm_type == "OSC":
            if hasattr(obj, "address") and hasattr(obj, "host") and hasattr(obj, "port"):
                if (
                    obj.host != config.get("host")
                    or obj.port != config.get("port")
                    or obj.address != config.get("address")
                ):
                    needs_recreate = True
        elif comm_type == "Serial":
            if hasattr(obj, "port") and hasattr(obj, "baudrate"):
                new_port = config.get("port", "")
                if new_port and new_port != "Select port..." and obj.port != new_port:
                    needs_recreate = True
                elif new_port and new_port != "Select port..." and obj.port == new_port:
                    if isinstance(obj, SerialObject) and not obj.is_connected():
                        if obj.open_port():
                            self.osc_manager.object_connection_state_changed.emit(
                                object_id, True
                            )
                            card.set_connection_state(True)
                        else:
                            self.osc_manager.object_connection_state_changed.emit(
                                object_id, False
                            )
                            card.set_connection_state(False)
                elif new_port and new_port == "Select port...":
                    if isinstance(obj, SerialObject) and obj.is_connected():
                        obj.close()
                        self.osc_manager.object_connection_state_changed.emit(
                            object_id, False
                        )
                        card.set_connection_state(False)

        if needs_recreate:
            was_streaming = obj.streaming_enabled

            self.osc_manager.remove_object(object_id)

            if comm_type == "OSC":
                self.osc_manager.add_osc_object(
                    config["object_id"],
                    config["address"],
                    config["host"],
                    config["port"],
                    pin_rows,
                )
            elif comm_type == "Serial":
                new_port = config.get("port", "")
                if new_port and new_port != "Select port...":
                    self.osc_manager.add_serial_object(
                        config["object_id"],
                        new_port,
                        config.get("baudrate", SERIAL_BAUDRATE),
                        pin_rows,
                    )
                    new_obj = self.osc_manager.get_object(object_id)
                    if new_obj and isinstance(new_obj, SerialObject):
                        if new_obj.open_port():
                            self.osc_manager.object_connection_state_changed.emit(
                                object_id, True
                            )
                            card.set_connection_state(True)
                        else:
                            self.osc_manager.object_connection_state_changed.emit(
                                object_id, False
                            )
                            card.set_connection_state(False)

            if was_streaming:
                self.osc_manager.start_object_streaming(object_id)

        if config.get("streaming_enabled", False):
            if not self.osc_manager.is_object_streaming(object_id):
                self.osc_manager.start_object_streaming(object_id)
        else:
            if self.osc_manager.is_object_streaming(object_id):
                self.osc_manager.stop_object_streaming(object_id)

        if self.osc_manager.is_object_streaming(object_id):
            self.osc_manager.flush_object_frame(object_id)

    def _on_streaming_state_changed(self, streaming: bool):
        """Handle OSC streaming state change (global)."""
        logger.debug(
            "OSC streaming (global): %s", "started" if streaming else "stopped"
        )

    def _on_object_streaming_state_changed(self, object_id: str, streaming: bool):
        """Handle per-object streaming state change."""
        card = self.object_cards.get_card(object_id)
        if card:
            card.set_streaming_state(streaming)
        logger.debug(
            "Object %s streaming: %s", object_id, "started" if streaming else "stopped"
        )

    def _on_object_value_updated(self, object_id: str, values: dict):
        """Handle object value update for UI display (row_id -> normalized)."""
        card = self.object_cards.get_card(object_id)
        if card:
            card.update_channel_values(values)

    def _on_object_connection_state_changed(self, object_id: str, connected: bool):
        """Handle object connection state change (for Serial objects)."""
        card = self.object_cards.get_card(object_id)
        if card:
            card.set_connection_state(connected)
        logger.debug(
            "Object %s connection: %s",
            object_id,
            "connected" if connected else "disconnected",
        )

    def _update_object_card_channels(self):
        """Update reference channel coloring for all object cards."""
        active_channel = self.waveform_model.get_active_channel()
        for card in self.object_cards._cards.values():
            card.set_active_channel(active_channel)

    def _sync_interactive_objects_to_playback_channels(
        self, allowed_channel_ids: set[str]
    ) -> None:
        """
        Drop pin rows on each ``InteractiveObject`` (and matching card UI) whose
        ``channel_id`` is not in the current playback selection.
        """
        allowed = frozenset(allowed_channel_ids)
        for oid in list(self.osc_manager.get_all_objects().keys()):
            obj = self.osc_manager.get_object(oid)
            if obj is None:
                continue
            if not obj.prune_pin_rows_to_channels(allowed):
                continue
            if obj.streaming_enabled and not obj.pin_rows:
                self.osc_manager.stop_object_streaming(oid)
            card = self.object_cards.get_card(oid)
            if card is not None:
                card.apply_pin_rows_from_core(obj.pin_rows)
            if obj.streaming_enabled:
                self.osc_manager.flush_object_frame(oid)
            logger.debug(
                "Pruned interactive object %s pins to %s slot(s) for playback selection",
                oid,
                len(obj.pin_rows),
            )

    def _on_card_streaming_started(self, object_id: str):
        """Handle card start button clicked."""
        self.osc_manager.start_object_streaming(object_id)

    def _on_card_streaming_stopped(self, object_id: str):
        """Handle card stop button clicked."""
        self.osc_manager.stop_object_streaming(object_id)
