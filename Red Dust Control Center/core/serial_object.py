"""
Serial implementation of InteractiveObject.

Firmware contract (multi-pin):
- One line per tick: v1,v2,...,vN,timestamp\\n
- Values are remapped floats in pin row order (Pin_A first); timestamp is ISO8601 UTC.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from obspy import UTCDateTime
import serial
import logging

from core.interactive_object import InteractiveObject

logger = logging.getLogger(__name__)


class SerialObject(InteractiveObject):
    """Serial implementation of interactive object."""

    def __init__(self, object_id: str, port: str, baudrate: int = 9600):
        super().__init__(object_id)
        self.port = port
        self.baudrate = baudrate
        self._serial = None
        self._connection_failed = False
        self._port_opened = False

    @property
    def communication_type(self) -> str:
        return "Serial"

    def is_connected(self) -> bool:
        if self._connection_failed:
            return False
        return self._serial is not None and self._serial.is_open

    def open_port(self) -> bool:
        self.close()
        self._connection_failed = False
        try:
            self._serial = serial.Serial(self.port, self.baudrate, timeout=1)
            logger.info(
                "Opened Serial connection for %s on %s at %s baud",
                self.object_id,
                self.port,
                self.baudrate,
            )
            self._port_opened = True
            return True
        except Exception as e:
            logger.error("Failed to open Serial connection for %s: %s", self.object_id, e)
            self._connection_failed = True
            self._port_opened = False
            return False

    def reconnect(self) -> bool:
        return self.open_port()

    def update_port(self, port: str) -> bool:
        self.port = port
        return self.open_port()

    def send_pin_bundle(
        self,
        ordered_normalized: List[Tuple[str, float]],
        timestamp: UTCDateTime,
    ) -> Optional[Dict[str, float]]:
        if not self.streaming_enabled or self._serial is None or not self._serial.is_open:
            return None
        if len(ordered_normalized) != len(self.pin_rows):
            logger.warning(
                "Serial %s: pin value count %s != rows %s",
                self.object_id,
                len(ordered_normalized),
                len(self.pin_rows),
            )
            return None
        for i, (rid, _) in enumerate(ordered_normalized):
            if i >= len(self.pin_rows) or self.pin_rows[i].row_id != rid:
                logger.warning("Serial %s: row_id mismatch at index %s", self.object_id, i)
                return None

        timestamp_str = timestamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        ui_norm: Dict[str, float] = {}
        parts: List[str] = []

        try:
            for i, (row_id, norm) in enumerate(ordered_normalized):
                row = self.pin_rows[i]
                n = max(0.0, min(1.0, norm))
                ui_norm[row_id] = n
                out = self.remap_for_row(n, row)
                parts.append(f"{out:.6f}")
            parts.append(timestamp_str)
            message = ",".join(parts) + "\n"
            self._serial.write(message.encode("utf-8"))
            return ui_norm
        except Exception as e:
            logger.error("Failed to send Serial message for %s: %s", self.object_id, e)
            return None

    def close(self) -> None:
        if self._serial is not None:
            try:
                if self._serial.is_open:
                    self._serial.close()
                    logger.info("Closed Serial connection for %s", self.object_id)
            except Exception as e:
                logger.error("Error closing Serial connection for %s: %s", self.object_id, e)
            finally:
                self._serial = None
                self._connection_failed = False
                self._port_opened = False

    def get_config_dict(self) -> dict:
        from core.pin_stream import pin_rows_to_dicts

        return {
            "type": "Serial",
            "object_id": self.object_id,
            "name": self.object_id,
            "port": self.port,
            "baudrate": self.baudrate,
            "pin_rows": pin_rows_to_dicts(self.pin_rows),
        }
