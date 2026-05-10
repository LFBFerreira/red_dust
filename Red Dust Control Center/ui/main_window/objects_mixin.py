"""Interactive object cards and per-object OSC/serial streaming."""

import logging

from core.serial_object import SerialObject
from settings import SERIAL_BAUDRATE
from .base import _MainWindowBase

logger = logging.getLogger(__name__)


class MainWindowObjectsMixin(_MainWindowBase):
    """Wires ObjectCardsContainer to OSCManager."""

    def _on_object_added(self, name: str):
        """Handle new object added."""
        card = self.object_cards.get_card(name)
        if not card:
            return

        card.streaming_started.connect(self._on_card_streaming_started)
        card.streaming_stopped.connect(self._on_card_streaming_stopped)

        config = card.get_config()
        comm_type = config.get("type", "OSC")

        if comm_type == "OSC":
            self.osc_manager.add_osc_object(
                config["name"],
                config["address"],
                config["host"],
                config["port"],
                config.get("remap_min", 0.0),
                config.get("remap_max", 1.0),
            )
        elif comm_type == "Serial":
            port = config.get("port", "")
            if port and port != "Select port...":
                self.osc_manager.add_serial_object(
                    config["name"],
                    port,
                    config.get("baudrate", SERIAL_BAUDRATE),
                    config.get("remap_min", 0.0),
                    config.get("remap_max", 1.0),
                )
                obj = self.osc_manager.get_object(name)
                if obj and isinstance(obj, SerialObject):
                    if obj.open_port():
                        self.osc_manager.object_connection_state_changed.emit(
                            name, True
                        )
                        card.set_connection_state(True)
                    else:
                        self.osc_manager.object_connection_state_changed.emit(
                            name, False
                        )
                        card.set_connection_state(False)
            else:
                self.osc_manager.add_serial_object(
                    config["name"],
                    "Select port...",
                    config.get("baudrate", SERIAL_BAUDRATE),
                    config.get("remap_min", 0.0),
                    config.get("remap_max", 1.0),
                )
                card.set_connection_state(False)
        else:
            logger.error("Unknown communication type: %s", comm_type)
            return

        if config.get("streaming_enabled", False):
            self.osc_manager.start_object_streaming(name)
        else:
            self.osc_manager.stop_object_streaming(name)

    def _on_object_removed(self, name: str):
        """Handle object removed."""
        self.osc_manager.remove_object(name)

    def _on_object_config_changed(self, name: str):
        """Handle object configuration change."""
        card = self.object_cards.get_card(name)
        if not card:
            return

        config = card.get_config()
        obj = self.osc_manager.get_object(name)
        if not obj:
            return

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
                                name, True
                            )
                            card.set_connection_state(True)
                        else:
                            self.osc_manager.object_connection_state_changed.emit(
                                name, False
                            )
                            card.set_connection_state(False)
                elif new_port and new_port == "Select port...":
                    if isinstance(obj, SerialObject) and obj.is_connected():
                        obj.close()
                        self.osc_manager.object_connection_state_changed.emit(
                            name, False
                        )
                        card.set_connection_state(False)

        if needs_recreate:
            was_streaming = obj.streaming_enabled

            self.osc_manager.remove_object(name)

            if comm_type == "OSC":
                self.osc_manager.add_osc_object(
                    config["name"],
                    config["address"],
                    config["host"],
                    config["port"],
                    config.get("remap_min", 0.0),
                    config.get("remap_max", 1.0),
                )
            elif comm_type == "Serial":
                new_port = config.get("port", "")
                if new_port and new_port != "Select port...":
                    self.osc_manager.add_serial_object(
                        config["name"],
                        new_port,
                        config.get("baudrate", SERIAL_BAUDRATE),
                        config.get("remap_min", 0.0),
                        config.get("remap_max", 1.0),
                    )
                    new_obj = self.osc_manager.get_object(name)
                    if new_obj and isinstance(new_obj, SerialObject):
                        if new_obj.open_port():
                            self.osc_manager.object_connection_state_changed.emit(
                                name, True
                            )
                            card.set_connection_state(True)
                        else:
                            self.osc_manager.object_connection_state_changed.emit(
                                name, False
                            )
                            card.set_connection_state(False)

            if was_streaming:
                self.osc_manager.start_object_streaming(name)
        else:
            self.osc_manager.update_object_remapping(
                name,
                config.get("remap_min", 0.0),
                config.get("remap_max", 1.0),
            )

        if config.get("streaming_enabled", False):
            if not self.osc_manager.is_object_streaming(name):
                self.osc_manager.start_object_streaming(name)
        else:
            if self.osc_manager.is_object_streaming(name):
                self.osc_manager.stop_object_streaming(name)

    def _on_streaming_state_changed(self, streaming: bool):
        """Handle OSC streaming state change (global)."""
        logger.debug(
            "OSC streaming (global): %s", "started" if streaming else "stopped"
        )

    def _on_object_streaming_state_changed(self, name: str, streaming: bool):
        """Handle per-object streaming state change."""
        card = self.object_cards.get_card(name)
        if card:
            card.set_streaming_state(streaming)
        logger.debug(
            "Object %s streaming: %s", name, "started" if streaming else "stopped"
        )

    def _on_object_value_updated(self, name: str, normalized_value: float):
        """Handle object value update for UI display."""
        card = self.object_cards.get_card(name)
        if card:
            card.update_value(normalized_value)

    def _on_object_connection_state_changed(self, name: str, connected: bool):
        """Handle object connection state change (for Serial objects)."""
        card = self.object_cards.get_card(name)
        if card:
            card.set_connection_state(connected)
        logger.debug(
            "Object %s connection: %s",
            name,
            "connected" if connected else "disconnected",
        )

    def _update_object_card_channels(self):
        """Update reference channel coloring for all object cards."""
        active_channel = self.waveform_model.get_active_channel()
        for card in self.object_cards._cards.values():
            card.set_active_channel(active_channel)

    def _on_card_streaming_started(self, name: str):
        """Handle card start button clicked."""
        self.osc_manager.start_object_streaming(name)

    def _on_card_streaming_stopped(self, name: str):
        """Handle card stop button clicked."""
        self.osc_manager.stop_object_streaming(name)
