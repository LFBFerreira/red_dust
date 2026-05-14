"""
Object Cards widget for managing interactive objects (OSC and Serial).
"""
from __future__ import annotations

import logging
import uuid
from typing import Callable, Dict, List, Optional, Set

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDoubleSpinBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QProgressBar,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
    QComboBox,
)

from core.pin_stream import (
    PinStreamRow,
    pin_rows_to_dicts,
    slot_label_for_index,
)
from .channel_colors import color_for_channel
from settings import (
    INTERACTIVE_OBJECTS_HEIGHT,
    MAX_PIN_SLOTS,
    OBJECT_CARD_LEFT_PANEL_MAX_WIDTH,
    PIN_SLOT_LABELS,
    SERIAL_BAUDRATE,
    STREAMING_PORT,
    TAB_ICON_SIZE,
)

logger = logging.getLogger(__name__)


def streaming_status_tab_icon(streaming: bool) -> QIcon:
    """Small circle: green when streaming, red when idle (for tab bar)."""
    pix = QPixmap(TAB_ICON_SIZE, TAB_ICON_SIZE)
    pix.fill(QColor(0, 0, 0, 0))
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
    painter.setBrush(QColor(34, 197, 94) if streaming else QColor(239, 68, 68))
    painter.setPen(Qt.PenStyle.NoPen)
    m = 3
    painter.drawEllipse(m, m, TAB_ICON_SIZE - 2 * m, TAB_ICON_SIZE - 2 * m)
    painter.end()
    return QIcon(pix)


class ObjectCard(QWidget):
    """Tab page widget for an interactive object (OSC or Serial)."""

    config_changed = Signal(str)
    display_title_changed = Signal(str, str)
    streaming_started = Signal(str)
    streaming_stopped = Signal(str)

    def __init__(
        self,
        object_id: str,
        display_title: str,
        communication_type: str = "OSC",
        get_selected_channels: Optional[Callable[[], List[str]]] = None,
        get_sorted_stream_channels: Optional[Callable[[], List[str]]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._object_id = object_id
        self._display_title = display_title
        self._communication_type = communication_type
        self._streaming = False
        self._refreshing_ports = False
        self._get_selected_channels = get_selected_channels
        self._get_sorted_stream_channels = get_sorted_stream_channels
        self._pin_rows: List[dict] = []
        self._row_progress: Dict[str, QProgressBar] = {}
        self._active_channel: Optional[str] = None
        self._serial_connected = False
        self._setup_ui()

    def _setup_ui(self) -> None:
        main = QHBoxLayout()
        main.setSpacing(12)
        main.setContentsMargins(8, 8, 8, 8)

        left = QVBoxLayout()
        left.setSpacing(8)

        type_hint = QLabel(f"<i>{self._communication_type}</i>")
        left.addWidget(type_hint)

        title_row = QHBoxLayout()
        title_row.addWidget(QLabel("Name:"))
        self.title_edit = QLineEdit()
        self.title_edit.setText(self._display_title)
        self.title_edit.textEdited.connect(self._on_title_edited)
        title_row.addWidget(self.title_edit, 1)
        left.addLayout(title_row)

        if self._communication_type == "OSC":
            addr_row = QHBoxLayout()
            addr_row.addWidget(QLabel("Base address:"))
            self.address_edit = QLineEdit()
            self.address_edit.setText(
                f"/red_dust/{self._display_title.lower().replace(' ', '_')}"
            )
            self.address_edit.textChanged.connect(
                lambda: self.config_changed.emit(self._object_id)
            )
            addr_row.addWidget(self.address_edit, 1)
            left.addLayout(addr_row)

            host_row = QHBoxLayout()
            host_row.addWidget(QLabel("IP Address:"))
            self.host_edit = QLineEdit()
            self.host_edit.setText("127.0.0.1")
            self.host_edit.textChanged.connect(
                lambda: self.config_changed.emit(self._object_id)
            )
            host_row.addWidget(self.host_edit, 1)
            left.addLayout(host_row)
        else:
            port_row = QHBoxLayout()
            port_row.addWidget(QLabel("Serial Port:"))
            self.port_combo = QComboBox()
            self.port_combo.setEditable(True)
            self._populate_serial_ports()
            self.port_combo.currentTextChanged.connect(self._on_serial_port_changed)
            port_row.addWidget(self.port_combo, 1)
            self.retry_button = QPushButton("Retry")
            self.retry_button.setFixedWidth(72)
            self.retry_button.clicked.connect(self._on_retry_serial_connection)
            self.retry_button.setEnabled(False)
            port_row.addWidget(self.retry_button)
            left.addLayout(port_row)

        stream_btns = QHBoxLayout()
        self.stream_toggle_button = QPushButton("Start")
        self.stream_toggle_button.clicked.connect(self._on_stream_toggle_clicked)
        stream_btns.addWidget(self.stream_toggle_button, 1)
        left.addLayout(stream_btns)

        left.addStretch()

        left_wrap = QWidget()
        left_wrap.setLayout(left)
        left_wrap.setMinimumWidth(220)
        left_wrap.setMaximumWidth(OBJECT_CARD_LEFT_PANEL_MAX_WIDTH)

        right = QVBoxLayout()
        add_row = QHBoxLayout()
        self.add_channels_button = QPushButton("Add channels")
        self.add_channels_button.setToolTip(
            "Adds each currently selected waveform channel as a pin row "
            f"(max {MAX_PIN_SLOTS}). Duplicate channels are skipped."
        )
        self.add_channels_button.clicked.connect(self._on_add_from_selection)
        add_row.addWidget(self.add_channels_button)
        add_row.addStretch()
        right.addLayout(add_row)

        self.pin_table = QTableWidget(0, 6)
        self.pin_table.setHorizontalHeaderLabels(
            ["Slot", "Channel", "Min", "Max", "Value", ""]
        )
        hdr = self.pin_table.horizontalHeader()
        hdr.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        hdr.setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        hdr.setSectionResizeMode(5, QHeaderView.ResizeMode.ResizeToContents)
        self.pin_table.verticalHeader().setVisible(False)
        right.addWidget(self.pin_table, 1)

        right_wrap = QWidget()
        right_wrap.setLayout(right)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left_wrap)
        splitter.addWidget(right_wrap)
        splitter.setStretchFactor(1, 1)
        main.addWidget(splitter)
        self.setLayout(main)
        self._update_add_button_state()
        self._update_stream_button()

    def _on_title_edited(self, text: str) -> None:
        self._display_title = text
        self.display_title_changed.emit(self._object_id, text)

    def _channels_in_table(self) -> set:
        return {r["channel_id"] for r in self._pin_rows}

    def _on_add_from_selection(self) -> None:
        if self._get_selected_channels is None:
            return
        selected = self._get_selected_channels()
        if not selected:
            return
        existing = self._channels_in_table()
        for ch in selected:
            if len(self._pin_rows) >= MAX_PIN_SLOTS:
                break
            if ch in existing:
                continue
            row_id = str(uuid.uuid4())
            slot_index = len(self._pin_rows)
            self._pin_rows.append(
                {
                    "row_id": row_id,
                    "channel_id": ch,
                    "remap_min": 0.0,
                    "remap_max": 1.0,
                    "slot_index": slot_index,
                }
            )
            existing.add(ch)
        self._rebuild_pin_table()
        self.config_changed.emit(self._object_id)
        self._update_add_button_state()
        self._update_stream_button()

    def _rebuild_pin_table(self) -> None:
        self._row_progress.clear()
        self.pin_table.setRowCount(0)
        for i, row in enumerate(self._pin_rows):
            row["slot_index"] = i
            self.pin_table.insertRow(i)
            slot_name = (
                PIN_SLOT_LABELS[i] if i < len(PIN_SLOT_LABELS) else slot_label_for_index(i)
            )
            slot_item = QTableWidgetItem(slot_name)
            slot_item.setFlags(slot_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.pin_table.setItem(i, 0, slot_item)

            ch_item = QTableWidgetItem(row["channel_id"])
            ch_item.setFlags(ch_item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.pin_table.setItem(i, 1, ch_item)

            min_spin = QDoubleSpinBox()
            min_spin.setRange(-1e6, 1e6)
            min_spin.setDecimals(3)
            min_spin.setSingleStep(0.05)
            min_spin.setValue(row["remap_min"])
            min_spin.editingFinished.connect(
                lambda r=row, s=min_spin: self._on_row_min_changed(r, s)
            )
            self.pin_table.setCellWidget(i, 2, min_spin)

            max_spin = QDoubleSpinBox()
            max_spin.setRange(-1e6, 1e6)
            max_spin.setDecimals(3)
            max_spin.setSingleStep(0.05)
            max_spin.setValue(row["remap_max"])
            max_spin.editingFinished.connect(
                lambda r=row, s=max_spin: self._on_row_max_changed(r, s)
            )
            self.pin_table.setCellWidget(i, 3, max_spin)

            bar = QProgressBar()
            bar.setRange(0, 100)
            bar.setValue(0)
            bar.setFormat("0.000")
            bar.setMinimumHeight(22)
            bar.setMinimumWidth(80)
            self.pin_table.setCellWidget(i, 4, bar)
            self._row_progress[row["row_id"]] = bar

            rm = QPushButton("Remove")
            rid = row["row_id"]
            rm.clicked.connect(lambda checked=False, x=rid: self._remove_pin_row(x))
            self.pin_table.setCellWidget(i, 5, rm)

        self._restyle_active_rows()

    def _on_row_min_changed(self, row: dict, spin: QDoubleSpinBox) -> None:
        lo = spin.value()
        hi = row["remap_max"]
        if lo >= hi:
            spin.setValue(row["remap_min"])
            return
        row["remap_min"] = lo
        self.config_changed.emit(self._object_id)

    def _on_row_max_changed(self, row: dict, spin: QDoubleSpinBox) -> None:
        hi = spin.value()
        lo = row["remap_min"]
        if lo >= hi:
            spin.setValue(row["remap_max"])
            return
        row["remap_max"] = hi
        self.config_changed.emit(self._object_id)

    def _remove_pin_row(self, row_id: str) -> None:
        self._pin_rows = [r for r in self._pin_rows if r["row_id"] != row_id]
        self._rebuild_pin_table()
        if not self._pin_rows and self._streaming:
            self._on_stop_clicked()
        self.config_changed.emit(self._object_id)
        self._update_add_button_state()
        self._update_stream_button()

    def apply_pin_rows_from_core(self, rows: List[PinStreamRow]) -> None:
        """Mirror ``InteractiveObject.pin_rows`` in the table (no ``config_changed`` emit)."""
        self._pin_rows = pin_rows_to_dicts(rows)
        self._rebuild_pin_table()
        self._update_add_button_state()
        self._update_stream_button()

    def _update_add_button_state(self) -> None:
        has_fn = self._get_selected_channels is not None
        at_cap = len(self._pin_rows) >= MAX_PIN_SLOTS
        self.add_channels_button.setEnabled(has_fn and not at_cap)

    def _update_stream_button(self) -> None:
        has_pins = len(self._pin_rows) > 0
        if self._streaming:
            self.stream_toggle_button.setText("Stop")
            self.stream_toggle_button.setEnabled(True)
            return
        self.stream_toggle_button.setText("Start")
        if self._communication_type == "Serial":
            self.stream_toggle_button.setEnabled(self._serial_connected and has_pins)
        else:
            self.stream_toggle_button.setEnabled(has_pins)

    def get_object_id(self) -> str:
        return self._object_id

    def get_display_title(self) -> str:
        return self.title_edit.text()

    def _populate_serial_ports(self, excluded_ports: Optional[Set[str]] = None) -> None:
        if self._communication_type != "Serial":
            return
        if self._refreshing_ports:
            return

        if excluded_ports is None:
            excluded_ports = set()

        self._refreshing_ports = True
        try:
            current_port = self.port_combo.currentText()
            is_current_port_valid = (
                current_port
                and current_port != "Select port..."
                and current_port.strip() != ""
            )

            try:
                import serial.tools.list_ports

                ports = serial.tools.list_ports.comports()
                available_ports = [port.device for port in ports]

                filtered_ports = [
                    port
                    for port in available_ports
                    if port not in excluded_ports or port == current_port
                ]

                self.port_combo.blockSignals(True)

                self.port_combo.clear()
                self.port_combo.addItems(filtered_ports)

                if not filtered_ports:
                    self.port_combo.addItem("Select port...")
                    if not is_current_port_valid:
                        self.port_combo.setCurrentText("Select port...")
                else:
                    self.port_combo.insertItem(0, "Select port...")
                    if is_current_port_valid and current_port in filtered_ports:
                        self.port_combo.setCurrentText(current_port)
                    else:
                        self.port_combo.setCurrentIndex(0)

                self.port_combo.blockSignals(False)
            except RecursionError:
                print(
                    "Warning: RecursionError while listing serial ports (problematic device detected)"
                )
                self.port_combo.blockSignals(True)
                self.port_combo.clear()
                self.port_combo.addItem("Select port...")
                if not is_current_port_valid:
                    self.port_combo.setCurrentText("Select port...")
                self.port_combo.blockSignals(False)
            except Exception as e:
                print(f"Error: Failed to list serial ports: {type(e).__name__}: {e}")
                self.port_combo.blockSignals(True)
                self.port_combo.clear()
                self.port_combo.addItem("Select port...")
                if not is_current_port_valid:
                    self.port_combo.setCurrentText("Select port...")
                self.port_combo.blockSignals(False)
        finally:
            self._refreshing_ports = False

    def _set_serial_port(self, port_name: str) -> None:
        current_items = [self.port_combo.itemText(i) for i in range(self.port_combo.count())]

        if port_name not in current_items:
            self.port_combo.addItem(port_name)

        if port_name and port_name != "Select port...":
            self.port_combo.setCurrentText(port_name)
        else:
            self.port_combo.blockSignals(True)
            self.port_combo.setCurrentText("Select port...")
            self.port_combo.blockSignals(False)

    def _on_serial_port_changed(self, port_name: str) -> None:
        if self._communication_type != "Serial":
            return

        self.config_changed.emit(self._object_id)

        if not self._refreshing_ports:
            self._request_port_refresh()

    def _request_port_refresh(self) -> None:
        parent = self.parent()
        while parent:
            if isinstance(parent, ObjectCardsContainer):
                parent._refresh_all_serial_ports()
                break
            parent = parent.parent()

    def _on_stream_toggle_clicked(self) -> None:
        if self._streaming:
            self._on_stop_clicked()
        else:
            self._on_start_clicked()

    def _on_start_clicked(self) -> None:
        self._streaming = True
        self.streaming_started.emit(self._object_id)
        self._update_stream_button()

    def _on_stop_clicked(self) -> None:
        self._streaming = False
        self.streaming_stopped.emit(self._object_id)
        self._update_stream_button()

    def set_streaming_state(self, streaming: bool) -> None:
        if streaming == self._streaming:
            return
        if streaming:
            if not self._streaming:
                self._on_start_clicked()
        else:
            if self._streaming:
                self._on_stop_clicked()

    def set_connection_state(self, connected: bool) -> None:
        if self._communication_type == "Serial":
            self._serial_connected = connected
            if not connected:
                port_name = self.port_combo.currentText()
                if port_name and port_name != "Select port...":
                    self.retry_button.setEnabled(True)
                else:
                    self.retry_button.setEnabled(False)
                if self._streaming:
                    self._on_stop_clicked()
            else:
                self.retry_button.setEnabled(False)
            self._update_stream_button()

    def _on_retry_serial_connection(self) -> None:
        if self._communication_type != "Serial":
            return

        port_name = self.port_combo.currentText()
        if port_name and port_name != "Select port...":
            self.config_changed.emit(self._object_id)

    def set_active_channel(self, channel: Optional[str]) -> None:
        self._active_channel = channel
        self._restyle_active_rows()

    def _restyle_active_rows(self) -> None:
        sorted_ids: List[str] = []
        if self._get_sorted_stream_channels is not None:
            try:
                sorted_ids = list(self._get_sorted_stream_channels())
            except Exception:
                sorted_ids = []

        for i, row in enumerate(self._pin_rows):
            ch_item = self.pin_table.item(i, 1)
            if ch_item is None:
                continue
            cid = row["channel_id"]
            hex_c = color_for_channel(cid, sorted_ids)
            trace = QColor(hex_c)
            ch_item.setForeground(QBrush(QColor(0, 0, 0)))

            is_active = bool(self._active_channel and cid == self._active_channel)
            bg = QColor(trace)
            bg.setAlpha(170 if is_active else 60)
            ch_item.setBackground(QBrush(bg))

    def update_channel_values(self, normalized_by_row_id: Dict[str, float]) -> None:
        for row in self._pin_rows:
            rid = row["row_id"]
            if rid not in normalized_by_row_id:
                continue
            bar = self._row_progress.get(rid)
            if bar is None:
                continue
            n = max(0.0, min(1.0, normalized_by_row_id[rid]))
            lo = row["remap_min"]
            hi = row["remap_max"]
            if hi == lo:
                remapped = lo
                pct = 50.0
            else:
                remapped = lo + n * (hi - lo)
                pct = n * 100.0
            bar.setValue(int(pct))
            bar.setFormat(f"{remapped:.3f}")

    def get_config(self) -> dict:
        config: Dict = {
            "object_id": self._object_id,
            "title": self.title_edit.text(),
            "name": self._object_id,
            "type": self._communication_type,
            "pin_rows": [dict(r) for r in self._pin_rows],
            "streaming_enabled": self._streaming,
        }

        if self._communication_type == "OSC":
            config["address"] = self.address_edit.text()
            config["host"] = self.host_edit.text()
            config["port"] = STREAMING_PORT
        else:
            config["port"] = self.port_combo.currentText()
            config["baudrate"] = SERIAL_BAUDRATE

        return config

    def set_config(self, config: dict) -> None:
        if "type" in config and config["type"] != self._communication_type:
            logger.warning(
                "Cannot change communication type from %s to %s",
                self._communication_type,
                config["type"],
            )

        if "title" in config:
            self.title_edit.blockSignals(True)
            self.title_edit.setText(config["title"])
            self.title_edit.blockSignals(False)
            self._display_title = config["title"]

        if self._communication_type == "OSC":
            if "address" in config:
                self.address_edit.setText(config["address"])
            if "host" in config:
                self.host_edit.setText(config["host"])
        else:
            if "port" in config:
                self._set_serial_port(config["port"])

        if "pin_rows" in config and isinstance(config["pin_rows"], list):
            self._pin_rows = []
            for i, pr in enumerate(config["pin_rows"][:MAX_PIN_SLOTS]):
                self._pin_rows.append(
                    {
                        "row_id": str(pr.get("row_id", uuid.uuid4())),
                        "channel_id": str(pr["channel_id"]),
                        "remap_min": float(pr.get("remap_min", 0.0)),
                        "remap_max": float(pr.get("remap_max", 1.0)),
                        "slot_index": int(pr.get("slot_index", i)),
                    }
                )
            self._rebuild_pin_table()

        if "streaming_enabled" in config:
            self.set_streaming_state(config["streaming_enabled"])
        elif "enabled" in config:
            self.set_streaming_state(config["enabled"])

        self._update_add_button_state()
        self._update_stream_button()


class ObjectCardsContainer(QFrame):
    """Container widget for multiple interactive objects (tabbed)."""

    object_added = Signal(str)
    object_removed = Signal(str)
    object_config_changed = Signal(str)

    def __init__(
        self,
        parent=None,
        selected_channels_provider: Optional[Callable[[], List[str]]] = None,
        sorted_stream_channels_provider: Optional[Callable[[], List[str]]] = None,
    ):
        super().__init__(parent)
        self._cards: Dict[str, ObjectCard] = {}
        self._refreshing_ports = False
        self._selected_channels_provider = selected_channels_provider
        self._sorted_stream_channels_provider = sorted_stream_channels_provider
        self._setup_ui()

    def set_selected_channels_provider(
        self, fn: Optional[Callable[[], List[str]]]
    ) -> None:
        self._selected_channels_provider = fn
        for card in self._cards.values():
            card._get_selected_channels = fn
            card._update_add_button_state()

    def set_sorted_stream_channels_provider(
        self, fn: Optional[Callable[[], List[str]]]
    ) -> None:
        self._sorted_stream_channels_provider = fn
        for card in self._cards.values():
            card._get_sorted_stream_channels = fn
            card._restyle_active_rows()

    def _setup_ui(self) -> None:
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFrameShadow(QFrame.Shadow.Plain)
        self.setLineWidth(0)
        self.setAutoFillBackground(False)

        layout = QVBoxLayout()
        layout.setContentsMargins(8, 8, 8, 8)

        header_layout = QHBoxLayout()
        header_layout.addWidget(QLabel("<b>Interactive Objects</b>"))
        header_layout.addStretch()

        add_osc_button = QPushButton("Add OSC")
        add_osc_button.clicked.connect(lambda: self._add_object("OSC"))
        header_layout.addWidget(add_osc_button)

        add_serial_button = QPushButton("Add Serial")
        add_serial_button.clicked.connect(lambda: self._add_object("Serial"))
        header_layout.addWidget(add_serial_button)
        layout.addLayout(header_layout)

        self.tab_widget = QTabWidget()
        self.tab_widget.setTabsClosable(True)
        self.tab_widget.tabCloseRequested.connect(self._on_tab_close_requested)
        self.tab_widget.setStyleSheet(
            """
            QTabBar::tab:selected {
                font-weight: bold;
                font-size: 1.09em;
            }
        """
        )
        layout.addWidget(self.tab_widget)

        self.setFixedHeight(INTERACTIVE_OBJECTS_HEIGHT)
        self.setLayout(layout)

    def _on_tab_close_requested(self, index: int) -> None:
        card = self.tab_widget.widget(index)
        if not isinstance(card, ObjectCard):
            return
        self._remove_object(card.get_object_id())

    def _next_default_title(self, communication_type: str) -> str:
        counter = 1
        base_name = f"{communication_type} Object"
        titles = {c.get_display_title() for c in self._cards.values()}
        name = f"{base_name} {counter}"
        while name in titles:
            counter += 1
            name = f"{base_name} {counter}"
        return name

    def _add_object(
        self,
        communication_type: str = "OSC",
        object_id: Optional[str] = None,
        display_title: Optional[str] = None,
        emit_added: bool = True,
    ) -> ObjectCard:
        if object_id is None:
            object_id = str(uuid.uuid4())
        if display_title is None:
            display_title = self._next_default_title(communication_type)

        card = ObjectCard(
            object_id,
            display_title,
            communication_type,
            get_selected_channels=self._selected_channels_provider,
            get_sorted_stream_channels=self._sorted_stream_channels_provider,
            parent=self,
        )
        card.config_changed.connect(self.object_config_changed.emit)
        card.display_title_changed.connect(self._on_display_title_changed)
        card.streaming_started.connect(self._on_streaming_started)
        card.streaming_stopped.connect(self._on_streaming_stopped)

        idx = self.tab_widget.addTab(card, display_title)
        self.tab_widget.setCurrentIndex(idx)
        self._cards[object_id] = card
        self._apply_tab_streaming_icon(object_id)

        if communication_type == "Serial":
            excluded = self._get_used_serial_ports(exclude_object_id=object_id)
            card._populate_serial_ports(excluded_ports=excluded)

        if emit_added:
            self.object_added.emit(object_id)
        logger.info("Added %s object tab: %s", communication_type, object_id)
        return card

    def _on_display_title_changed(self, object_id: str, title: str) -> None:
        card = self._cards.get(object_id)
        if not card:
            return
        idx = self.tab_widget.indexOf(card)
        if idx >= 0:
            self.tab_widget.setTabText(idx, title)

    def _apply_tab_streaming_icon(self, object_id: str) -> None:
        card = self._cards.get(object_id)
        if not card:
            return
        idx = self.tab_widget.indexOf(card)
        if idx < 0:
            return
        self.tab_widget.setTabIcon(idx, streaming_status_tab_icon(card._streaming))

    def _on_streaming_started(self, object_id: str) -> None:
        self._apply_tab_streaming_icon(object_id)

    def _on_streaming_stopped(self, object_id: str) -> None:
        self._apply_tab_streaming_icon(object_id)

    def _remove_object(self, object_id: str) -> None:
        if object_id not in self._cards:
            return

        card = self._cards[object_id]
        was_serial = card._communication_type == "Serial"

        idx = self.tab_widget.indexOf(card)
        if idx >= 0:
            self.tab_widget.removeTab(idx)

        card.deleteLater()
        del self._cards[object_id]

        if was_serial:
            self._refresh_all_serial_ports()
        self.object_removed.emit(object_id)
        logger.info("Removed object tab: %s", object_id)

    def get_card(self, object_id: str) -> Optional[ObjectCard]:
        return self._cards.get(object_id)

    def get_all_configs(self) -> list[dict]:
        return [card.get_config() for card in self._cards.values()]

    def _get_used_serial_ports(self, exclude_object_id: Optional[str] = None) -> set:
        used_ports = set()
        for oid, card in self._cards.items():
            if oid == exclude_object_id:
                continue
            if card._communication_type == "Serial":
                port = card.port_combo.currentText()
                if port and port != "Select port..." and port.strip() != "":
                    used_ports.add(port)
        return used_ports

    def _refresh_all_serial_ports(self) -> None:
        if self._refreshing_ports:
            return

        self._refreshing_ports = True
        try:
            for oid, card in self._cards.items():
                if card._communication_type == "Serial":
                    excluded = self._get_used_serial_ports(exclude_object_id=oid)
                    card._populate_serial_ports(excluded_ports=excluded)
        finally:
            self._refreshing_ports = False
