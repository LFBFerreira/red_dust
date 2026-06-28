"""Optional debug outlines for major ui/widgets components (QSettings + View menu)."""

from __future__ import annotations

from typing import Iterable, Mapping

from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QLabel, QWidget

from settings import (
    QSETTINGS_APPLICATION,
    QSETTINGS_ORGANIZATION,
    SHOW_WIDGET_DEBUG_BORDERS,
)

WIDGET_DEBUG_QSETTINGS_KEY = "show_widget_debug_borders"
_DEBUG_LABEL_OBJECT_NAME = "_rdcc_widget_debug_label"
_ORIGINAL_STYLESHEET_PROP = "_rdcc_widget_debug_original_ss"
_DEBUG_LABEL_BG_ALPHA = 0.55

# Distinct colors for each major widget (name -> hex).
WIDGET_DEBUG_COLORS: dict[str, str] = {
    "DatasetInformation": "#1abc9c",
    "DataPicker": "#e74c3c",
    "WaveformViewer": "#3498db",
    "PlaybackControls": "#2ecc71",
    "ObjectCards": "#9b59b6",
    "LogViewer": "#f39c12",
}


def read_show_widget_debug_borders() -> bool:
    s = QSettings(QSETTINGS_ORGANIZATION, QSETTINGS_APPLICATION)
    raw = s.value(WIDGET_DEBUG_QSETTINGS_KEY, SHOW_WIDGET_DEBUG_BORDERS)
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return bool(SHOW_WIDGET_DEBUG_BORDERS)
    return str(raw).strip().lower() in ("1", "true", "yes", "on")


def write_show_widget_debug_borders(enabled: bool) -> None:
    s = QSettings(QSETTINGS_ORGANIZATION, QSETTINGS_APPLICATION)
    s.setValue(WIDGET_DEBUG_QSETTINGS_KEY, bool(enabled))


def _hex_to_rgba(hex_color: str, alpha: float) -> str:
    h = hex_color.lstrip("#")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha})"


def _find_debug_label(widget: QWidget) -> QLabel | None:
    return widget.findChild(QLabel, _DEBUG_LABEL_OBJECT_NAME)


def _apply_border(widget: QWidget, name: str, color: str) -> None:
    if widget.property(_ORIGINAL_STYLESHEET_PROP) is None:
        widget.setProperty(_ORIGINAL_STYLESHEET_PROP, widget.styleSheet())

    original = widget.property(_ORIGINAL_STYLESHEET_PROP) or ""
    border_rule = f"border: 1px dashed {color};"
    widget.setStyleSheet(f"{original}\n{border_rule}" if original else border_rule)

    bg = _hex_to_rgba(color, _DEBUG_LABEL_BG_ALPHA)
    label = _find_debug_label(widget)
    if label is None:
        label = QLabel(name, widget)
        label.setObjectName(_DEBUG_LABEL_OBJECT_NAME)
        label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
    label.setText(name)
    label.setStyleSheet(
        f"background-color: {bg}; color: rgba(255, 255, 255, 0.92); "
        "font-size: 10px; font-weight: bold; padding: 1px 4px; border: none;"
    )
    label.adjustSize()
    label.move(4, 4)
    label.show()
    label.raise_()


def _clear_border(widget: QWidget) -> None:
    original = widget.property(_ORIGINAL_STYLESHEET_PROP)
    if original is not None:
        widget.setStyleSheet(str(original))
        widget.setProperty(_ORIGINAL_STYLESHEET_PROP, None)

    label = _find_debug_label(widget)
    if label is not None:
        label.hide()


def apply_widget_debug_borders(
    targets: Mapping[str, QWidget],
    *,
    enabled: bool,
    colors: Mapping[str, str] | None = None,
) -> None:
    """Show or hide debug outlines on the given widgets."""
    palette = colors or WIDGET_DEBUG_COLORS
    for name, widget in targets.items():
        if widget is None:
            continue
        if enabled:
            _apply_border(widget, name, palette.get(name, "#888888"))
        else:
            _clear_border(widget)


def iter_widget_debug_targets(main_window) -> Iterable[tuple[str, QWidget]]:
    """Major layout panels hosted in the main window."""
    yield "DatasetInformation", main_window.metadata_widget
    yield "DataPicker", main_window.data_picker
    yield "WaveformViewer", main_window.waveform_viewer
    yield "PlaybackControls", main_window.playback_controls
    yield "ObjectCards", main_window.object_cards
    yield "LogViewer", main_window.log_viewer
