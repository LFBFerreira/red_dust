"""Full-screen preview of dataset information and a live paging waveform."""

from __future__ import annotations

import html
from typing import Optional, Sequence

from obspy import Stream, UTCDateTime
from PySide6.QtCore import Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .live_waveform import LiveWaveformStrip


class FullscreenPreviewWindow(QWidget):
    """Independent full-screen window for gallery / projection use."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.Window)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose, True)
        self.setWindowTitle("Red Dust Control Center — Full Screen")
        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 16)
        layout.setSpacing(16)

        info_frame = QFrame()
        info_frame.setFrameShape(QFrame.Shape.NoFrame)
        info_layout = QVBoxLayout(info_frame)
        info_layout.setContentsMargins(0, 0, 0, 0)
        info_layout.setSpacing(8)

        self.dataset_label = QLabel("<b>Dataset Information</b>")
        self.dataset_label.setStyleSheet("font-size: 22pt;")
        info_layout.addWidget(self.dataset_label)

        self.mission_label = QLabel("<b>SEIS raw data, InSight Mission</b>")
        self.mission_label.setStyleSheet("font-size: 16pt;")
        info_layout.addWidget(self.mission_label)

        self.metadata_text = QTextEdit()
        self.metadata_text.setReadOnly(True)
        self.metadata_text.setFrameShape(QFrame.Shape.NoFrame)
        self.metadata_text.setStyleSheet("font-size: 16pt; background: transparent;")
        self.metadata_text.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum
        )
        self.metadata_text.setFixedHeight(160)
        info_layout.addWidget(self.metadata_text)

        self.credit_label = QLabel(
            "<i>Data courtesy of NASA/JPL-Caltech/CNES/IPGP</i>"
        )
        self.credit_label.setAlignment(
            Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter
        )
        self.credit_label.setStyleSheet("font-size: 14pt;")
        info_layout.addWidget(self.credit_label)
        layout.addWidget(info_frame, 0)

        self.placeholder = QLabel()
        self.placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.placeholder.setWordWrap(True)
        self.placeholder.setStyleSheet("font-size: 18pt; color: gray;")
        self.placeholder.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding
        )
        layout.addWidget(self.placeholder, 1)

        self.live_waveform = LiveWaveformStrip()
        layout.addWidget(self.live_waveform, 1)
        self.live_waveform.hide()

        hint_row = QHBoxLayout()
        hint_row.addStretch(1)
        hint = QLabel("Press Esc to exit full screen")
        hint.setStyleSheet("font-size: 11pt; color: gray;")
        hint_row.addWidget(hint)
        layout.addLayout(hint_row)

    def set_metadata(self, html_text: str) -> None:
        self.metadata_text.setHtml(html_text)

    def set_dataset_fields(
        self,
        *,
        network: Optional[str] = None,
        station: Optional[str] = None,
        selected_channels: Optional[str] = None,
        time_range: Optional[str] = None,
        duration: Optional[str] = None,
        empty_message: Optional[str] = None,
    ) -> None:
        """Exhibition layout for Dataset Information (fullscreen only)."""
        show_credit = empty_message is None
        self.mission_label.setVisible(show_credit)
        self.credit_label.setVisible(show_credit)
        if empty_message:
            self.metadata_text.setHtml(f"<p>{html.escape(empty_message)}</p>")
            return

        rows: list[str] = []
        if network:
            rows.append(f"Network: {html.escape(network)}")
        if station:
            rows.append(f"Station: {html.escape(station)}")
        if selected_channels:
            rows.append(f"Selected channels: {html.escape(selected_channels)}")
        if time_range:
            rows.append(f"Time Range: {html.escape(time_range)}")
        if duration:
            rows.append(f"Duration: {html.escape(duration)}")
        self.metadata_text.setHtml(f"<p>{'<br>'.join(rows)}</p>")

    def set_live_source(
        self,
        stream: Optional[Stream],
        visible_channels: Sequence[str],
        time_span: Optional[tuple[UTCDateTime, UTCDateTime]],
        color_channel_ids: Optional[Sequence[str]] = None,
    ) -> None:
        if stream is None or len(stream) == 0 or not visible_channels:
            self._show_placeholder(
                "Load data and select channels to display the live waveform."
            )
            return
        if time_span is None:
            self._show_placeholder(
                "Set a loop range, or load data, to display the live waveform."
            )
            return
        if not self.live_waveform.set_source(
            stream,
            visible_channels,
            time_span,
            color_channel_ids=color_channel_ids,
        ):
            self._show_placeholder("No samples in the current time range.")
            return
        self.placeholder.hide()
        self.live_waveform.show()

    def update_playhead(self, timestamp: UTCDateTime) -> None:
        if self.live_waveform.isVisible():
            self.live_waveform.update_playhead(timestamp)

    def _show_placeholder(self, message: str) -> None:
        self.live_waveform.clear()
        self.live_waveform.hide()
        self.placeholder.setText(message)
        self.placeholder.show()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
            return
        super().keyPressEvent(event)
