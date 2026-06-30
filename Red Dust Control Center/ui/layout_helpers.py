"""Layout helpers for consistent panel spacing."""

from __future__ import annotations

from PySide6.QtWidgets import QVBoxLayout, QWidget

from settings import WIDGET_PANEL_MARGIN


def wrap_panel(widget: QWidget, margin: int | None = None) -> QWidget:
    """Wrap ``widget`` with fixed empty space on all sides."""
    m = WIDGET_PANEL_MARGIN if margin is None else margin
    wrapper = QWidget()
    layout = QVBoxLayout(wrapper)
    layout.setContentsMargins(m, m, m, m)
    layout.setSpacing(0)
    layout.addWidget(widget)
    return wrapper
