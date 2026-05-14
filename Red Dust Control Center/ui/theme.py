"""Apply global light / dark / system color scheme from ``settings.APP_COLOR_SCHEME``."""

from __future__ import annotations

import logging

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication

from settings import APP_COLOR_SCHEME

logger = logging.getLogger(__name__)

_VALID_SCHEMES = frozenset({"system", "light", "dark"})


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


def apply_app_color_scheme(app: QApplication) -> None:
    """
    Respect ``APP_COLOR_SCHEME``:

    - ``system``: follow the OS / Qt default (clears any app-level scheme override).
    - ``light`` / ``dark``: prefer ``QStyleHints.setColorScheme`` when present (Qt 6.8+);
      otherwise Fusion + palette fallback for dark, Fusion + standard palette for light.
    """
    mode = (APP_COLOR_SCHEME or "system").strip().lower()
    if mode not in _VALID_SCHEMES:
        logger.warning("Invalid APP_COLOR_SCHEME %r; using system", APP_COLOR_SCHEME)
        mode = "system"

    hints = app.styleHints()

    if mode == "system":
        if hasattr(hints, "unsetColorScheme"):
            hints.unsetColorScheme()
        elif hasattr(hints, "setColorScheme") and hasattr(Qt, "ColorScheme"):
            try:
                hints.setColorScheme(Qt.ColorScheme.Unknown)
            except (TypeError, AttributeError):
                pass
        return

    app.setStyle("Fusion")

    if hasattr(hints, "setColorScheme") and hasattr(Qt, "ColorScheme"):
        try:
            if mode == "dark":
                hints.setColorScheme(Qt.ColorScheme.Dark)
            else:
                hints.setColorScheme(Qt.ColorScheme.Light)
            return
        except (TypeError, AttributeError) as e:
            logger.debug("setColorScheme not usable (%s); using palette fallback", e)

    logger.info("Using Fusion palette fallback for APP_COLOR_SCHEME=%r", mode)
    if mode == "dark":
        _apply_fusion_dark_palette(app)
    else:
        app.setPalette(app.style().standardPalette())
