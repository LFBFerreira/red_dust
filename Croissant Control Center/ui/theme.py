"""Global light / dark / system color scheme (QSettings + session JSON)."""

from __future__ import annotations

import logging
from typing import Optional

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from settings import APP_COLOR_SCHEME, QSETTINGS_APPLICATION, QSETTINGS_ORGANIZATION

logger = logging.getLogger(__name__)

_VALID_SCHEMES = frozenset({"system", "light", "dark"})
THEME_QSETTINGS_KEY = "app_color_scheme"

# Last mode we applied (None = startup, before any theme call — matches plain QApplication).
_last_applied_theme_mode: Optional[str] = None


def normalize_color_scheme(mode: Optional[str]) -> str:
    m = (mode or "").strip().lower()
    if m not in _VALID_SCHEMES:
        if mode:
            logger.warning("Invalid color scheme %r; using system", mode)
        return "system"
    return m


def read_saved_color_scheme() -> str:
    s = QSettings(QSETTINGS_ORGANIZATION, QSETTINGS_APPLICATION)
    raw = s.value(THEME_QSETTINGS_KEY, APP_COLOR_SCHEME)
    return normalize_color_scheme(str(raw) if raw is not None else APP_COLOR_SCHEME)


def write_saved_color_scheme(mode: str) -> None:
    s = QSettings(QSETTINGS_ORGANIZATION, QSETTINGS_APPLICATION)
    s.setValue(THEME_QSETTINGS_KEY, normalize_color_scheme(mode))


def _apply_fusion_dark_palette(app: QApplication) -> None:
    """Fusion-friendly dark palette when ``QStyleHints.setColorScheme`` is unavailable."""
    p = QPalette()
    p.setColor(QPalette.ColorRole.Window, QColor(53, 53, 53))
    p.setColor(QPalette.ColorRole.WindowText, QColor(220, 220, 220))
    p.setColor(QPalette.ColorRole.Base, QColor(42, 42, 42))
    p.setColor(QPalette.ColorRole.AlternateBase, QColor(66, 66, 66))
    p.setColor(QPalette.ColorRole.ToolTipBase, QColor(53, 53, 53))
    p.setColor(QPalette.ColorRole.ToolTipText, QColor(220, 220, 220))
    p.setColor(QPalette.ColorRole.Text, QColor(220, 220, 220))
    p.setColor(QPalette.ColorRole.Button, QColor(53, 53, 53))
    p.setColor(QPalette.ColorRole.ButtonText, QColor(220, 220, 220))
    p.setColor(QPalette.ColorRole.BrightText, Qt.GlobalColor.red)
    p.setColor(QPalette.ColorRole.Link, QColor(42, 130, 218))
    p.setColor(QPalette.ColorRole.Highlight, QColor(42, 130, 218))
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(250, 250, 250))
    p.setColor(QPalette.ColorRole.PlaceholderText, QColor(127, 127, 127))
    app.setPalette(p)


def _unset_app_color_scheme_override(hints) -> None:
    if hasattr(hints, "unsetColorScheme"):
        hints.unsetColorScheme()
    elif hasattr(hints, "setColorScheme") and hasattr(Qt, "ColorScheme"):
        try:
            hints.setColorScheme(Qt.ColorScheme.Unknown)
        except (TypeError, AttributeError):
            pass


def _refresh_theme_sensitive_widgets(app: QApplication) -> None:
    """Widgets whose QSS must be reapplied after global palette / style changes."""
    for top in app.topLevelWidgets():
        oc = getattr(top, "object_cards", None)
        if oc is not None and hasattr(oc, "_refresh_interactive_objects_tab_style"):
            oc._refresh_interactive_objects_tab_style()
        pc = getattr(top, "playback_controls", None)
        if pc is not None and hasattr(pc, "_refresh_channel_strip_theme"):
            pc._refresh_channel_strip_theme()
        st = getattr(top, "story_timelines", None)
        if st:
            for panel in st:
                panel.update()
                canvas = getattr(panel, "canvas", None)
                if canvas is not None:
                    canvas.update()
        else:
            single = getattr(top, "story_timeline", None)
            if single is not None:
                single.update()
                canvas = getattr(single, "canvas", None)
                if canvas is not None:
                    canvas.update()
        fs = getattr(top, "_fullscreen_window", None)
        if fs is not None:
            fs.update()


def _sync_native_style_palette(app: QApplication) -> None:
    """Re-read the active native style palette (fixes unset ButtonText on some platforms)."""
    style = app.style()
    if style is not None:
        app.setPalette(style.standardPalette())


def finish_startup_theme(app: QApplication) -> None:
    """
    Run once after the main window is shown when using the system theme.

    On macOS and Linux (including Raspberry Pi), the native palette can leave
    button text the same colour as the button until the first sync — switching
    to Light/Dark and back fixes it because that path rebuilds the palette.
    """
    if _last_applied_theme_mode != "system":
        return

    _sync_native_style_palette(app)
    _refresh_theme_sensitive_widgets(app)


def apply_app_color_scheme(app: QApplication, mode: Optional[str] = None) -> str:
    """
    Apply ``mode`` (``system`` / ``light`` / ``dark``). If ``mode`` is None, use QSettings
    or ``settings.APP_COLOR_SCHEME``.

    ``system``: matches a plain Qt startup when already on system — no palette/style
    overrides. Only when switching *from* Light/Dark do we clear Fusion, app palette,
    and color-scheme hints so the native style can show again.

    ``light`` / ``dark``: Fusion style with forced light or dark appearance.
    Returns the normalized mode that was applied.
    """
    global _last_applied_theme_mode

    if mode is None:
        mode = read_saved_color_scheme()
    else:
        mode = normalize_color_scheme(mode)

    prev = _last_applied_theme_mode
    hints = app.styleHints()

    try:
        if mode == "system":
            if prev in ("light", "dark"):
                _unset_app_color_scheme_override(hints)
                app.setStyle(None)
                app.setPalette(QPalette())
            elif prev is None:
                # Prime palette before widgets are built; finish_startup_theme() runs
                # again after the main window is shown for QSS that uses palette().
                _sync_native_style_palette(app)
            return mode

        app.setStyle("Fusion")

        if hasattr(hints, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            try:
                if mode == "dark":
                    hints.setColorScheme(Qt.ColorScheme.Dark)
                else:
                    hints.setColorScheme(Qt.ColorScheme.Light)
                return mode
            except (TypeError, AttributeError) as e:
                logger.debug("setColorScheme not usable (%s); using palette fallback", e)

        logger.info("Using Fusion palette fallback for color scheme %r", mode)
        if mode == "dark":
            _apply_fusion_dark_palette(app)
        else:
            app.setPalette(app.style().standardPalette())
        return mode
    finally:
        _refresh_theme_sensitive_widgets(app)
        _last_applied_theme_mode = mode
