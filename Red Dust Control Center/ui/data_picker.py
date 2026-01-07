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
                               QComboBox, QPushButton, QProgressBar)
from PySide6.QtCore import Qt, Signal
import logging
from settings import (
    DEFAULT_STATION, 
    DEFAULT_NETWORK, 
    AVAILABLE_STATIONS,
    DEFAULT_YEAR,
    DEFAULT_DAY_OF_YEAR
)

logger = logging.getLogger(__name__)


class DataPicker(QWidget):
    """Widget for selecting and loading seismic data."""
    
    # Signal emitted when user clicks "Load Data"
    load_requested = Signal(dict)  # Emits: {"network": str, "station": str, "year": int, "doy": int}
    
    def __init__(self, parent=None, data_manager=None):
        """
        Initialize DataPicker.
        
        Args:
            parent: Parent widget
            data_manager: DataManager instance for fetching available dates
        """
        super().__init__(parent)
        self.data_manager = data_manager
        self._available_years: list[int] = []
        self._available_days: list[int] = []
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
        self.station_combo.currentTextChanged.connect(self._on_station_changed)
        station_layout.addWidget(self.station_combo)
        station_layout.addStretch()
        layout.addLayout(station_layout)
        
        # Year selection
        year_layout = QHBoxLayout()
        year_layout.addWidget(QLabel("Year:"))
        self.year_combo = QComboBox()
        self.year_combo.currentTextChanged.connect(self._on_year_changed)
        year_layout.addWidget(self.year_combo)
        year_layout.addStretch()
        layout.addLayout(year_layout)
        
        # Day of year selection
        day_layout = QHBoxLayout()
        day_layout.addWidget(QLabel("Day of Year:"))
        self.day_combo = QComboBox()
        day_layout.addWidget(self.day_combo)
        day_layout.addStretch()
        layout.addLayout(day_layout)
        
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
    
    def set_data_manager(self, data_manager) -> None:
        """
        Set the data manager and load initial data.
        
        Args:
            data_manager: DataManager instance
        """
        self.data_manager = data_manager
        if data_manager:
            self._load_available_years()
    
    def _load_available_years(self) -> None:
        """Load available years for the current station."""
        if not self.data_manager:
            logger.warning("DataManager not set, cannot load available years")
            return
        
        network = self.network_combo.currentText()
        station = self.station_combo.currentText()
        
        logger.info(f"Loading available years for {network}/{station}...")
        try:
            years = self.data_manager.get_available_years(network, station)
            self._available_years = years
            
            # Update year combo box
            self.year_combo.clear()
            if years:
                logger.info(f"Found {len(years)} available years: {years[:5]}{'...' if len(years) > 5 else ''}")
                self.year_combo.addItems([str(y) for y in years])
                # Set default year if available
                if DEFAULT_YEAR in years:
                    index = years.index(DEFAULT_YEAR)
                    self.year_combo.setCurrentIndex(index)
                    logger.info(f"Set default year to {DEFAULT_YEAR}")
                else:
                    self.year_combo.setCurrentIndex(0)
                    logger.info(f"Set year to first available: {years[0]}")
                # Trigger year change to load days
                self._on_year_changed()
            else:
                logger.warning(f"No years found for {network}/{station}")
        except Exception as e:
            logger.error(f"Failed to load available years: {e}", exc_info=True)
    
    def _on_station_changed(self, station: str) -> None:
        """Handle station selection change."""
        logger.debug(f"Station changed to: {station}")
        self._load_available_years()
    
    def _on_year_changed(self, year_str: str = None) -> None:
        """Handle year selection change."""
        if not year_str:
            year_str = self.year_combo.currentText()
        
        if not year_str or not self.data_manager:
            if not year_str:
                logger.debug("No year selected")
            if not self.data_manager:
                logger.warning("DataManager not set, cannot load available days")
            return
        
        try:
            year = int(year_str)
            network = self.network_combo.currentText()
            station = self.station_combo.currentText()
            
            logger.info(f"Loading available days for {network}/{station}/{year}...")
            days = self.data_manager.get_available_days(network, station, year)
            self._available_days = days
            
            # Update day combo box
            self.day_combo.clear()
            if days:
                logger.info(f"Found {len(days)} available days for {year}")
                self.day_combo.addItems([str(d) for d in days])
                # Set default day if available
                if DEFAULT_DAY_OF_YEAR in days:
                    index = days.index(DEFAULT_DAY_OF_YEAR)
                    self.day_combo.setCurrentIndex(index)
                    logger.info(f"Set default day to {DEFAULT_DAY_OF_YEAR}")
                else:
                    self.day_combo.setCurrentIndex(0)
                    logger.info(f"Set day to first available: {days[0]}")
            else:
                logger.warning(f"No days found for {network}/{station}/{year}")
        except (ValueError, Exception) as e:
            logger.error(f"Failed to load available days: {e}", exc_info=True)
    
    def get_selection(self) -> dict:
        """
        Get current selection parameters.
        
        Returns:
            Dictionary with network, station, year, and doy
        """
        network = self.network_combo.currentText()
        station = self.station_combo.currentText()
        
        try:
            year = int(self.year_combo.currentText())
            doy = int(self.day_combo.currentText())
        except (ValueError, AttributeError):
            # Fallback to defaults if combo boxes are empty
            year = DEFAULT_YEAR
            doy = DEFAULT_DAY_OF_YEAR
        
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

