"""
Serial implementation of InteractiveObject.

Firmware contract (multi-pin):
- One line per tick: v1,v2,...,vW,timestamp\\n
- Floats in **wire slot order** (index 0 = Pin_A); W = max(slot_index)+1.
- Active slots: remapped values clamped to [0, 1]. Unused slots: sentinel
  ``settings.WIRE_INACTIVE_PIN_SENTINEL`` (outside [0, 1]); firmware ignores those.
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from obspy import UTCDateTime
import serial
import logging

from core.interactive_object import InteractiveObject
from settings import WIRE_INACTIVE_PIN_SENTINEL

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
        self._rx_buffer = ""

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
            self._rx_buffer = ""
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
        ordered_normalized: List[Tuple[Optional[str], float]],
        timestamp: UTCDateTime,
    ) -> Optional[Dict[str, float]]:
        if not self.streaming_enabled or self._serial is None or not self._serial.is_open:
            return None
        if not ordered_normalized:
            return None

        row_by_id = {r.row_id: r for r in self.pin_rows}
        timestamp_str = timestamp.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
        ui_norm: Dict[str, float] = {}
        parts: List[str] = []

        try:
            for row_id, norm in ordered_normalized:
                n = max(0.0, min(1.0, norm))
                if row_id is None:
                    parts.append(f"{WIRE_INACTIVE_PIN_SENTINEL:.6f}")
                    continue
                row = row_by_id.get(row_id)
                if row is None:
                    logger.warning(
                        "Serial %s: unknown row_id %s in wire bundle", self.object_id, row_id
                    )
                    return None
                ui_norm[row_id] = n
                out = max(0.0, min(1.0, self.remap_for_row(n, row)))
                parts.append(f"{out:.6f}")
            parts.append(timestamp_str)
            message = ",".join(parts) + "\n"
            self._serial.write(message.encode("utf-8"))
            return ui_norm
        except Exception as e:
            logger.error("Failed to send Serial message for %s: %s", self.object_id, e)
            return None

    def read_available_lines(self) -> List[str]:
        """Non-blocking read of complete lines from the device (e.g. ``DY,BTN,PLAY``)."""
        if self._serial is None or not self._serial.is_open:
            return []
        try:
            waiting = getattr(self._serial, "in_waiting", 0) or 0
            if waiting:
                chunk = self._serial.read(waiting)
                self._rx_buffer += chunk.decode("utf-8", errors="replace")
        except Exception as e:
            logger.error("Failed to read Serial input for %s: %s", self.object_id, e)
            return []

        lines: List[str] = []
        while "\n" in self._rx_buffer:
            raw, self._rx_buffer = self._rx_buffer.split("\n", 1)
            text = raw.strip()
            if text:
                lines.append(text)
        if len(self._rx_buffer) > 1024:
            self._rx_buffer = ""
        return lines

    def send_control_line(self, line: str) -> bool:
        """Send a firmware control line (e.g. ``DY,PLAY``). Port must already be open."""
        if self._serial is None or not self._serial.is_open:
            return False
        text = line if line.endswith("\n") else line + "\n"
        try:
            self._serial.write(text.encode("utf-8"))
            return True
        except Exception as e:
            logger.error("Failed to send Serial control line for %s: %s", self.object_id, e)
            return False

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
                self._rx_buffer = ""

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
