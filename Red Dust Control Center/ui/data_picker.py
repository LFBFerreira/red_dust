"""
Data Picker widget for selecting seismic datasets.
"""
import sys
from pathlib import Path

# Add project root to path to allow imports from root directory
# Only add if not already present to avoid duplicates
_project_root = Path(__file__).parent.parent
_project_root_str = str(_project_root)
if _project_root_str not in sys.path:
    sys.path.insert(0, _project_root_str)

from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, 
                               QComboBox, QDateEdit, QPushButton, QProgressBar)
from PySide6.QtCore import Qt, QDate, Signal
from datetime import datetime
import logging
from settings import (
    DEFAULT_STATION, 
    DEFAULT_NETWORK, 
    AVAILABLE_STATIONS
)
from utils import get_default_date

logger = logging.getLogger(__name__)


class DataPicker(QWidget):
    """Widget for selecting and loading seismic data."""
    
    # Signal emitted when user clicks "Load Data"
    load_requested = Signal(dict)  # Emits: {"network": str, "station": str, "year": int, "doy": int}
    
    def __init__(self, parent=None):
        """Initialize DataPicker."""
        super().__init__(parent)
        self._setup_ui()
    
    def _setup_ui(self):
        """Set up the UI components."""
        layout = QVBoxLayout()
        
        # Network selection
        network_layout = QHBoxLayout()
        network_layout.addWidget(QLabel("Network:"))
        self.network_combo = QComboBox()
        self.network_combo.addItem(DEFAULT_NETWORK)
        self.network_combo.setEditable(False)
        network_layout.addWidget(self.network_combo)
        network_layout.addStretch()
        layout.addLayout(network_layout)
        
        # Station selection
        station_layout = QHBoxLayout()
        station_layout.addWidget(QLabel("Station:"))
        self.station_combo = QComboBox()
        self.station_combo.addItems(AVAILABLE_STATIONS)
        # Set default station
        default_station_index = AVAILABLE_STATIONS.index(DEFAULT_STATION)
        if default_station_index >= 0:
            self.station_combo.setCurrentIndex(default_station_index)
        station_layout.addWidget(self.station_combo)
        station_layout.addStretch()
        layout.addLayout(station_layout)
        
        # Date picker
        date_layout = QHBoxLayout()
        date_layout.addWidget(QLabel("Date:"))
        self.date_picker = QDateEdit()
        self.date_picker.setCalendarPopup(True)
        # Set default date from settings
        default_date = get_default_date()
        self.date_picker.setDate(QDate(default_date.year, default_date.month, default_date.day))
        self.date_picker.setDisplayFormat("yyyy-MM-dd")
        date_layout.addWidget(self.date_picker)
        date_layout.addStretch()
        layout.addLayout(date_layout)
        
        # Load button
        self.load_button = QPushButton("Load Data")
        self.load_button.clicked.connect(self._on_load_clicked)
        layout.addWidget(self.load_button)
        
        # Loading indicator
        progress_layout = QVBoxLayout()
        self.progress_label = QLabel("")
        self.progress_label.setVisible(False)
        progress_layout.addWidget(self.progress_label)
        
        self.progress_bar = QProgressBar()
        self.progress_bar.setVisible(False)
        self.progress_bar.setRange(0, 0)  # Indeterminate progress
        progress_layout.addWidget(self.progress_bar)
        layout.addLayout(progress_layout)
        
        layout.addStretch()
        self.setLayout(layout)
    
    def date_to_doy(self, date: QDate) -> tuple[int, int]:
        """
        Convert QDate to (year, day_of_year).
        
        Args:
            date: QDate object
        
        Returns:
            Tuple of (year, day_of_year)
        """
        python_date = date.toPython()
        year = python_date.year
        doy = python_date.timetuple().tm_yday
        return (year, doy)
    
    def get_selection(self) -> dict:
        """
        Get current selection parameters.
        
        Returns:
            Dictionary with network, station, year, and doy
        """
        network = self.network_combo.currentText()
        station = self.station_combo.currentText()
        year, doy = self.date_to_doy(self.date_picker.date())
        
        return {
            "network": network,
            "station": station,
            "year": year,
            "doy": doy
        }
    
    def set_loading(self, loading: bool) -> None:
        """
        Set loading state.
        
        Args:
            loading: True to show loading indicator
        """
        self.load_button.setEnabled(not loading)
        self.progress_bar.setVisible(loading)
        self.progress_label.setVisible(loading)
        if not loading:
            # Reset progress bar
            self.progress_bar.setRange(0, 0)
            self.progress_label.setText("")
    
    def set_total_files(self, total: int) -> None:
        """
        Set the total number of files to download.
        Switches progress bar from indeterminate to determinate mode.
        
        Args:
            total: Total number of files
        """
        self.progress_bar.setRange(0, total)
        self.progress_bar.setValue(0)
        self.progress_label.setText(f"Downloading: 0 / {total} files")
    
    def update_download_progress(self, downloaded: int, total: int) -> None:
        """
        Update download progress.
        
        Args:
            downloaded: Number of files downloaded so far
            total: Total number of files
        """
        self.progress_bar.setValue(downloaded)
        self.progress_label.setText(f"Downloading: {downloaded} / {total} files")
    
    def _on_load_clicked(self) -> None:
        """Handle Load Data button click."""
        selection = self.get_selection()
        logger.info(f"Load requested: {selection}")
        self.load_requested.emit(selection)


# Test code - only runs if file is executed directly
if __name__ == "__main__":
    from PySide6.QtWidgets import QApplication
    import sys as _sys
    
    app = QApplication(_sys.argv)
    widget = DataPicker()
    widget.show()
    _sys.exit(app.exec())

