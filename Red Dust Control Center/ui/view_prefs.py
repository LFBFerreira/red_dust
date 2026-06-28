"""View menu preferences persisted in QSettings."""

from __future__ import annotations

from PySide6.QtCore import QSettings

from settings import QSETTINGS_APPLICATION, QSETTINGS_ORGANIZATION, SHOW_LOG

SHOW_LOG_QSETTINGS_KEY = "show_log"


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
