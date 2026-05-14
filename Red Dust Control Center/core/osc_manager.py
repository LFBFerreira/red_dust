"""
Object Manager for streaming normalized data to interactive objects (OSC and Serial).
"""
from __future__ import annotations

from typing import Dict, List, Optional, Tuple

from obspy import UTCDateTime
from PySide6.QtCore import QObject, QTimer, Signal
import logging

from core.interactive_object import InteractiveObject
from core.osc_object import OSCObject
from core.pin_stream import PinStreamRow, wire_bundle_width
from core.serial_object import SerialObject
from settings import SERIAL_BAUDRATE, OSC_OUTPUT_INTERVAL_MS, SERIAL_OUTPUT_INTERVAL_MS

logger = logging.getLogger(__name__)

__all__ = ["OSCManager", "OSCObject", "SerialObject"]


class OSCManager(QObject):
    """Manages streaming to multiple interactive objects (OSC and Serial)."""

    streaming_state_changed = Signal(bool)
    object_streaming_state_changed = Signal(str, bool)
    object_value_updated = Signal(str, dict)
    object_connection_state_changed = Signal(str, bool)

    def __init__(self, waveform_model=None, playback_controller=None):
        super().__init__()
        self._waveform_model = waveform_model
        self._playback_controller = playback_controller
        self._objects: Dict[str, InteractiveObject] = {}
        self._streaming = False

        self._osc_timer = QTimer()
        self._osc_timer.timeout.connect(self._send_osc_frame)
        self._osc_timer.setInterval(OSC_OUTPUT_INTERVAL_MS)

        self._serial_timer = QTimer()
        self._serial_timer.timeout.connect(self._send_serial_frame)
        self._serial_timer.setInterval(SERIAL_OUTPUT_INTERVAL_MS)

    def set_waveform_model(self, waveform_model) -> None:
        self._waveform_model = waveform_model

    def set_playback_controller(self, playback_controller) -> None:
        self._playback_controller = playback_controller

    def add_osc_object(
        self,
        object_id: str,
        address: str,
        host: str,
        port: int,
        pin_rows: Optional[List[PinStreamRow]] = None,
    ) -> OSCObject:
        if object_id in self._objects:
            logger.warning("Object %s already exists, replacing it", object_id)
            self.remove_object(object_id)

        obj = OSCObject(object_id, address, host, port)
        if pin_rows:
            obj.set_pin_rows(pin_rows)
        self._objects[object_id] = obj

        if not self._osc_timer.isActive():
            self._osc_timer.start()

        logger.info("Added OSC object: %s", object_id)
        return obj

    def add_serial_object(
        self,
        object_id: str,
        port: str,
        baudrate: int = None,
        pin_rows: Optional[List[PinStreamRow]] = None,
    ) -> SerialObject:
        if object_id in self._objects:
            logger.warning("Object %s already exists, replacing it", object_id)
            self.remove_object(object_id)

        if baudrate is None:
            baudrate = SERIAL_BAUDRATE

        obj = SerialObject(object_id, port, baudrate)
        if pin_rows:
            obj.set_pin_rows(pin_rows)
        self._objects[object_id] = obj

        self.object_connection_state_changed.emit(object_id, obj.is_connected())

        if not self._serial_timer.isActive():
            self._serial_timer.start()

        logger.info("Added Serial object: %s", object_id)
        return obj

    def add_object(
        self,
        object_id: str,
        address: str,
        host: str,
        port: int,
        pin_rows: Optional[List[PinStreamRow]] = None,
    ) -> OSCObject:
        return self.add_osc_object(object_id, address, host, port, pin_rows)

    def remove_object(self, object_id: str) -> None:
        if object_id in self._objects:
            obj = self._objects[object_id]

            if obj.streaming_enabled:
                self.stop_object_streaming(object_id)

            obj.close()

            if isinstance(obj, SerialObject):
                self.object_connection_state_changed.emit(object_id, False)

            del self._objects[object_id]
            logger.info("Removed object: %s", object_id)

    def get_object(self, object_id: str) -> Optional[InteractiveObject]:
        return self._objects.get(object_id)

    def get_all_objects(self) -> Dict[str, InteractiveObject]:
        return self._objects.copy()

    def update_object_pin_rows(self, object_id: str, pin_rows: List[PinStreamRow]) -> None:
        if object_id in self._objects:
            self._objects[object_id].set_pin_rows(pin_rows)
            logger.debug("Updated pin rows for %s: %s slots", object_id, len(pin_rows))

    def start_object_streaming(self, object_id: str) -> None:
        if object_id not in self._objects:
            return
        obj = self._objects[object_id]

        if not obj.pin_rows:
            logger.warning("Cannot start streaming for %s: no pin rows", object_id)
            return

        if isinstance(obj, SerialObject):
            if not obj.is_connected():
                logger.warning("Serial object %s is not connected, attempting reconnect", object_id)
                if not obj.reconnect():
                    logger.error("Cannot start streaming for %s: Serial connection failed", object_id)
                    self.object_connection_state_changed.emit(object_id, False)
                    return
                self.object_connection_state_changed.emit(object_id, True)

        if not obj.streaming_enabled:
            obj.streaming_enabled = True
            self.object_streaming_state_changed.emit(object_id, True)
            logger.info("Started streaming for object: %s", object_id)

            if isinstance(obj, SerialObject):
                if not self._serial_timer.isActive():
                    self._serial_timer.start()
            else:
                if not self._osc_timer.isActive():
                    self._osc_timer.start()

    def stop_object_streaming(self, object_id: str) -> None:
        if object_id not in self._objects:
            return
        obj = self._objects[object_id]
        if not obj.streaming_enabled:
            return

        if self._playback_controller:
            current_time = self._playback_controller.get_current_timestamp()
            if current_time is None:
                current_time = UTCDateTime.now()
        else:
            current_time = UTCDateTime.now()

        if obj.pin_rows:
            w = wire_bundle_width(list(obj.pin_rows))
            if w > 0:
                zeros: List[Tuple[Optional[str], float]] = [(None, 0.0)] * w
                sent = obj.send_pin_bundle(zeros, current_time)
            if sent is not None:
                self.object_value_updated.emit(object_id, sent)

        obj.streaming_enabled = False
        self.object_streaming_state_changed.emit(object_id, False)
        logger.info("Stopped streaming for object: %s", object_id)

        if isinstance(obj, SerialObject):
            if not any(
                o.streaming_enabled
                for o in self._objects.values()
                if isinstance(o, SerialObject)
            ):
                self._serial_timer.stop()
        else:
            if not any(
                o.streaming_enabled
                for o in self._objects.values()
                if isinstance(o, OSCObject)
            ):
                self._osc_timer.stop()

    def is_object_streaming(self, object_id: str) -> bool:
        if object_id in self._objects:
            return self._objects[object_id].streaming_enabled
        return False

    def set_object_enabled(self, object_id: str, enabled: bool) -> None:
        if enabled:
            self.start_object_streaming(object_id)
        else:
            self.stop_object_streaming(object_id)

    def start_streaming(self) -> None:
        if self._streaming:
            return

        self._streaming = True
        has_osc = any(
            isinstance(obj, OSCObject) and obj.streaming_enabled
            for obj in self._objects.values()
        )
        has_serial = any(
            isinstance(obj, SerialObject) and obj.streaming_enabled
            for obj in self._objects.values()
        )
        if has_osc and not self._osc_timer.isActive():
            self._osc_timer.start()
        if has_serial and not self._serial_timer.isActive():
            self._serial_timer.start()
        self.streaming_state_changed.emit(True)
        logger.info("OSC streaming started (global)")

    def stop_streaming(self) -> None:
        if not self._streaming:
            return

        if self._playback_controller:
            current_time = self._playback_controller.get_current_timestamp()
            if current_time is None:
                current_time = UTCDateTime.now()
        else:
            current_time = UTCDateTime.now()

        for obj in self._objects.values():
            if obj.streaming_enabled and obj.pin_rows:
                w = wire_bundle_width(list(obj.pin_rows))
                if w > 0:
                    zeros: List[Tuple[Optional[str], float]] = [(None, 0.0)] * w
                    obj.send_pin_bundle(zeros, current_time)

        self._streaming = False
        self.streaming_state_changed.emit(False)
        logger.info("OSC streaming stopped (global)")

    def is_streaming(self) -> bool:
        return self._streaming

    def shutdown(self) -> None:
        logger.info("OSCManager: shutdown (stopping timers, closing all objects)")
        self._osc_timer.stop()
        self._serial_timer.stop()
        try:
            for oid in list(self._objects.keys()):
                try:
                    self.remove_object(oid)
                except Exception as e:
                    logger.warning("OSCManager: failed to remove object %s: %s", oid, e)
        finally:
            self._osc_timer.stop()
            self._serial_timer.stop()
            if self._streaming:
                self._streaming = False
                self.streaming_state_changed.emit(False)
            logger.info("OSCManager: shutdown complete")

    def _build_ordered_values(
        self, obj: InteractiveObject, current_time: UTCDateTime
    ) -> Optional[List[Tuple[Optional[str], float]]]:
        if not self._waveform_model or not obj.pin_rows:
            return None
        width = wire_bundle_width(list(obj.pin_rows))
        if width <= 0:
            return None
        by_slot: Dict[int, PinStreamRow] = {}
        for row in obj.pin_rows:
            si = int(row.slot_index)
            if 0 <= si < width:
                by_slot[si] = row
        ordered: List[Tuple[Optional[str], float]] = []
        for s in range(width):
            r = by_slot.get(s)
            if r is None:
                ordered.append((None, 0.0))
            else:
                n = self._waveform_model.get_normalized_value_for_channel(
                    r.channel_id, current_time
                )
                ordered.append((r.row_id, n))
        return ordered

    def flush_object_frame(self, object_id: str) -> None:
        """Send one streaming frame immediately (e.g. after pin layout changes while streaming)."""
        if self._waveform_model is None or self._playback_controller is None:
            return
        obj = self._objects.get(object_id)
        if obj is None or not obj.streaming_enabled or not obj.pin_rows:
            return
        current_time = self._playback_controller.get_current_timestamp()
        if current_time is None:
            return
        ordered = self._build_ordered_values(obj, current_time)
        if not ordered:
            return
        sent = obj.send_pin_bundle(ordered, current_time)
        if sent is not None:
            self.object_value_updated.emit(obj.object_id, sent)

    def _send_osc_frame(self) -> None:
        if self._waveform_model is None or self._playback_controller is None:
            return

        current_time = self._playback_controller.get_current_timestamp()
        if current_time is None:
            return

        for obj in self._objects.values():
            if not isinstance(obj, OSCObject) or not obj.streaming_enabled:
                continue
            ordered = self._build_ordered_values(obj, current_time)
            if not ordered:
                continue
            sent = obj.send_pin_bundle(ordered, current_time)
            if sent is not None:
                self.object_value_updated.emit(obj.object_id, sent)

    def _send_serial_frame(self) -> None:
        if self._waveform_model is None or self._playback_controller is None:
            return

        current_time = self._playback_controller.get_current_timestamp()
        if current_time is None:
            return

        for obj in self._objects.values():
            if not isinstance(obj, SerialObject) or not obj.streaming_enabled:
                continue
            ordered = self._build_ordered_values(obj, current_time)
            if not ordered:
                continue
            sent = obj.send_pin_bundle(ordered, current_time)
            if sent is not None:
                self.object_value_updated.emit(obj.object_id, sent)
