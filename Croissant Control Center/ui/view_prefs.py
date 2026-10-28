"""View menu preferences persisted in QSettings."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, QSettings

from settings import (
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
    QSETTINGS_APPLICATION,
    QSETTINGS_ORGANIZATION,
    SHOW_LOG,
)

SHOW_LOG_QSETTINGS_KEY = "show_log"
WINDOW_GEOMETRY_QSETTINGS_KEY = "window_geometry"


def read_show_log() -> bool:
    s = QSettings(QSETTINGS_ORGANIZATION, QSETTINGS_APPLICATION)
    raw = s.value(SHOW_LOG_QSETTINGS_KEY, SHOW_LOG)
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return bool(SHOW_LOG)
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def write_show_log(enabled: bool) -> None:
    s = QSettings(QSETTINGS_ORGANIZATION, QSETTINGS_APPLICATION)
    s.setValue(SHOW_LOG_QSETTINGS_KEY, bool(enabled))


def read_window_geometry() -> QByteArray | None:
    s = QSettings(QSETTINGS_ORGANIZATION, QSETTINGS_APPLICATION)
    raw = s.value(WINDOW_GEOMETRY_QSETTINGS_KEY)
    if raw is None:
        return None
    if isinstance(raw, QByteArray):
        return raw if not raw.isEmpty() else None
    if isinstance(raw, (bytes, bytearray)):
        geometry = QByteArray(raw)
        return geometry if not geometry.isEmpty() else None
    return None


def write_window_geometry(geometry: QByteArray) -> None:
    s = QSettings(QSETTINGS_ORGANIZATION, QSETTINGS_APPLICATION)
    s.setValue(WINDOW_GEOMETRY_QSETTINGS_KEY, geometry)


def default_window_size() -> tuple[int, int]:
    return DEFAULT_WINDOW_WIDTH, DEFAULT_WINDOW_HEIGHT
