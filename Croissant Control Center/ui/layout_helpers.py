"""Layout helpers for consistent panel spacing and section titles."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QSizePolicy, QVBoxLayout, QWidget

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


def flush_vbox(parent: QWidget) -> QVBoxLayout:
    """Zero-margin column. Callers may setSpacing; outer gap usually comes from wrap_panel."""
    layout = QVBoxLayout(parent)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    return layout


def panel_title(text: str) -> QLabel:
    """Section title for a major panel, top-left so columns line up."""
    label = QLabel(text)
    label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
    return label


def set_vertical_policy(widget: QWidget, policy: QSizePolicy.Policy) -> None:
    """Lock vertical growth so splitters don't stretch compact rows or squash plots."""
    size_policy = widget.sizePolicy()
    size_policy.setVerticalPolicy(policy)
    widget.setSizePolicy(size_policy)
