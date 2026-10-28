"""
OSC implementation of InteractiveObject.

Firmware / MCU contract (multi-pin):
- One OSC message per tick at the configured base `address`.
- Arguments: W floats (wire index 0 = Pin_A, … index W-1 = last slot),
  then one string: UTC timestamp as "%Y-%m-%dT%H:%M:%S.%fZ".
- Active slots: remapped values clamped to [0, 1]. Unused wire slots: sentinel
  ``settings.WIRE_INACTIVE_PIN_SENTINEL`` (outside [0, 1]); firmware ignores those.
- W = max(slot_index)+1 among configured rows (1..MAX_PIN_SLOTS). Decoder infers W from typetag.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from obspy import UTCDateTime
from pythonosc.udp_client import UDPClient
import logging

from core.interactive_object import InteractiveObject
from settings import WIRE_INACTIVE_PIN_SENTINEL

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
        ordered_normalized: List[Tuple[Optional[str], float]],
        timestamp: UTCDateTime,
    ) -> Optional[Dict[str, float]]:
        if not self.streaming_enabled or self._client is None:
            return None
        if not ordered_normalized:
            return None

        row_by_id = {r.row_id: r for r in self.pin_rows}
        timestamp_str = timestamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        ui_norm: Dict[str, float] = {}

        try:
            from pythonosc.osc_message_builder import OscMessageBuilder

            builder = OscMessageBuilder(self.address)
            for row_id, norm in ordered_normalized:
                n = max(0.0, min(1.0, norm))
                if row_id is None:
                    builder.add_arg(float(WIRE_INACTIVE_PIN_SENTINEL))
                    continue
                row = row_by_id.get(row_id)
                if row is None:
                    logger.warning(
                        "OSC %s: unknown row_id %s in wire bundle", self.object_id, row_id
                    )
                    return None
                ui_norm[row_id] = n
                out = max(0.0, min(1.0, self.remap_for_row(n, row)))
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

        cfg = {
            "type": "OSC",
            "object_id": self.object_id,
            "name": self.object_id,
            "address": self.address,
            "host": self.host,
            "port": self.port,
            "pin_rows": pin_rows_to_dicts(self.pin_rows),
        }
        if self.croissant_station is not None:
            cfg["croissant_station"] = self.croissant_station + 1
        return cfg
