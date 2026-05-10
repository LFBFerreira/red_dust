"""
OSC implementation of InteractiveObject.

Firmware / MCU contract (multi-pin):
- One OSC message per tick at the configured base `address`.
- Arguments: N remapped floats (wire order: row 0 = Pin_A, row 1 = Pin_B, ...),
  then one string: UTC timestamp as "%Y-%m-%dT%H:%M:%S.%fZ".
- N = number of configured pin rows (1..MAX_PIN_SLOTS). Decoder infers N from typetag.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from obspy import UTCDateTime
from pythonosc.udp_client import UDPClient
import logging

from core.interactive_object import InteractiveObject

logger = logging.getLogger(__name__)


class OSCObject(InteractiveObject):
    """OSC implementation of interactive object."""

    def __init__(self, object_id: str, address: str, host: str, port: int):
        super().__init__(object_id)
        self.address = address
        self.host = host
        self.port = port
        self._client: Optional[UDPClient] = None

        try:
            self._client = UDPClient(host, port)
            logger.info("Created OSC client for %s at %s:%s", object_id, host, port)
        except Exception as e:
            logger.error("Failed to create OSC client for %s: %s", object_id, e)

    @property
    def communication_type(self) -> str:
        return "OSC"

    def send_pin_bundle(
        self,
        ordered_normalized: List[Tuple[str, float]],
        timestamp: UTCDateTime,
    ) -> Optional[Dict[str, float]]:
        if not self.streaming_enabled or self._client is None:
            return None
        if len(ordered_normalized) != len(self.pin_rows):
            logger.warning(
                "OSC %s: pin value count %s != rows %s",
                self.object_id,
                len(ordered_normalized),
                len(self.pin_rows),
            )
            return None
        for i, (rid, _) in enumerate(ordered_normalized):
            if i >= len(self.pin_rows) or self.pin_rows[i].row_id != rid:
                logger.warning("OSC %s: row_id mismatch at index %s", self.object_id, i)
                return None

        timestamp_str = timestamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        ui_norm: Dict[str, float] = {}

        try:
            from pythonosc.osc_message_builder import OscMessageBuilder

            builder = OscMessageBuilder(self.address)
            for i, (row_id, norm) in enumerate(ordered_normalized):
                row = self.pin_rows[i]
                n = max(0.0, min(1.0, norm))
                ui_norm[row_id] = n
                out = self.remap_for_row(n, row)
                builder.add_arg(float(out))
            builder.add_arg(timestamp_str)
            msg = builder.build()
            self._client.send(msg)
            return ui_norm
        except Exception as e:
            logger.error("Failed to send OSC message for %s: %s", self.object_id, e)
            return None

    def close(self) -> None:
        self._client = None

    def get_config_dict(self) -> dict:
        from core.pin_stream import pin_rows_to_dicts

        return {
            "type": "OSC",
            "object_id": self.object_id,
            "name": self.object_id,
            "address": self.address,
            "host": self.host,
            "port": self.port,
            "pin_rows": pin_rows_to_dicts(self.pin_rows),
        }
