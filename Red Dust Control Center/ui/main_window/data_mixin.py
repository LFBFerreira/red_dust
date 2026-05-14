"""Data loading, metadata display, and data picker session restore."""

import logging
import time

from settings import DEFAULT_NETWORK, DEFAULT_STATION
from .base import _MainWindowBase
from .constants import (
    DATASET_LABEL_TITLE_HTML,
    DATASET_METADATA_EMPTY_MESSAGE,
    _LOG_TAG,
)
from .threads import DataLoadThread, MetadataLoadThread

logger = logging.getLogger(__name__)


class MainWindowDataMixin(_MainWindowBase):
    """Waveform data fetch, model updates, and metadata UI."""

    def _reset_state_for_new_load(self):
        """Reset all state when loading new data (especially when station changes)."""
        logger.info("Resetting state for new data load...")

        if self.playback_controller:
            logger.debug("Stopping playback controller...")
            self.playback_controller.stop()

        if self.waveform_viewer:
            logger.debug("Clearing waveform viewer...")
            self.waveform_viewer.plot_widget.clear()

        if self.waveform_model:
            logger.debug("Resetting waveform model...")
            self.waveform_model.set_stream(None)

        if self.osc_manager:
            logger.debug("Stopping OSC streaming...")

        if self.load_thread and self.load_thread.isRunning():
            logger.warning("Previous load thread still running, waiting for it...")
            self.load_thread.wait(1000)

        logger.info("State reset complete")

    def _on_load_requested(self, selection: dict):
        """Handle data load request."""
        logger.info("===== Starting data load request =====")
        logger.info("Selection: %s", selection)
        logger.info("Station: %s", selection.get("station", "unknown"))

        logger.info("Resetting state for new data load...")
        self._reset_state_for_new_load()

        self.data_picker.set_loading(True)

        self.load_thread = DataLoadThread(
            self.data_manager,
            selection["network"],
            selection["station"],
            selection["year"],
            selection["doy"],
        )
        self.load_thread.data_loaded.connect(self._on_data_loaded)
        self.load_thread.error_occurred.connect(self._on_load_error)
        self.load_thread.file_count_known.connect(self.data_picker.set_total_files)
        self.load_thread.download_progress.connect(self.data_picker.update_download_progress)
        self.load_thread.start()
        logger.info("Data load thread started")

    def _on_data_loaded(self, stream):
        """Handle successful data load."""
        process_start = time.time()

        logger.info("===== Data loaded callback started =====")
        logger.info("Stream contains %s traces", len(stream))

        if stream and len(stream) > 0:
            first_trace = stream[0]
            logger.info(
                "First trace: %s, station: %s, samples: %s, rate: %s Hz",
                first_trace.id,
                first_trace.stats.station,
                f"{first_trace.stats.npts:,}",
                first_trace.stats.sampling_rate,
            )
            total_samples = sum(t.stats.npts for t in stream)
            logger.info("Total samples across all traces: %s", f"{total_samples:,}")

        self.data_picker.set_loading(False)

        logger.info("Setting stream in waveform model...")
        model_start = time.time()
        self.waveform_model.set_stream(stream)
        model_time = time.time() - model_start
        logger.info("Waveform model updated in %.2fs", model_time)

        logger.info("Updating channel controls...")
        channels = self.waveform_model.get_all_channels()
        logger.info("Found %s channels: %s", len(channels), channels)
        self.playback_controls.set_channels(channels)
        selected = self.waveform_model.get_selected_channels()
        self.playback_controls.set_selected_channels(selected)
        self._update_object_card_channels()
        self._sync_interactive_objects_to_playback_channels(set(selected))

        logger.info("Updating waveform viewer...")
        viewer_start = time.time()
        self.waveform_viewer.update_waveform(stream, selected)
        viewer_time = time.time() - viewer_start
        logger.info("Waveform viewer updated in %.2fs", viewer_time)

        logger.info("Updating metadata display...")
        self._update_metadata()

        logger.info("Resetting playback controller...")
        self.playback_controller.stop()

        self.playback_controller.set_waveform_model(self.waveform_model)

        logger.info("Updating value display...")
        time_range = self.waveform_model.get_time_range()
        if time_range:
            initial_time = time_range[0]
            self._refresh_value_display(initial_time)
            self.playback_controls.update_position_slider(
                initial_time, time_range[0], time_range[1]
            )

        if self.pending_session_state:
            logger.info("Restoring pending session state...")
            self._restore_session_state_after_load(self.pending_session_state)
            self.pending_session_state = None

        logger.debug(
            "%s _on_data_loaded done selected=%s ref=%s",
            _LOG_TAG,
            len(self.waveform_model.get_selected_channels()),
            self.waveform_model.get_active_channel(),
        )
        process_time = time.time() - process_start
        logger.info(
            "===== Data loaded callback complete in %.2fs =====", process_time
        )

    def _on_load_error(self, error_message: str):
        """Handle data load error."""
        logger.error("Failed to load data: %s", error_message)
        self.data_picker.set_loading(False)

    def _update_metadata(self):
        """Update metadata display."""
        self.dataset_label.setText(DATASET_LABEL_TITLE_HTML)

        if not self.waveform_model.get_stream():
            self.metadata_text.setPlainText(DATASET_METADATA_EMPTY_MESSAGE)
            return

        stream = self.waveform_model.get_stream()
        if stream is None or len(stream) == 0:
            self.metadata_text.setPlainText(DATASET_METADATA_EMPTY_MESSAGE)
            return

        trace = stream[0]
        active_channel = self.waveform_model.get_active_channel()
        selected = self.waveform_model.get_selected_channels()
        selected_line = ", ".join(selected) if selected else "—"
        channel_info = self.waveform_model.get_channel_info(active_channel)
        sr = self.waveform_model.get_sample_rate()
        sr_line = f"{sr:.2f} Hz" if sr is not None else "--"

        metadata = f"""Network: {trace.stats.network}
Station: {trace.stats.station}
Reference Channel: {active_channel or '—'}
Selected channels: {selected_line}
Sample Rate: {sr_line}"""

        if channel_info:
            time_range = self.waveform_model.get_time_range()
            if time_range:
                t0, t1 = time_range[0], time_range[1]
                duration_h = float(t1 - t0) / 3600.0
                metadata += f"""
Time Range: {t0} to {t1}
Duration: {duration_h:.2f} hours"""

        self.metadata_text.setText(metadata)

    def _load_metadata_async(self):
        """Load metadata (available years/days) in background."""
        logger.info("Starting background thread to refresh metadata from PDS...")
        self.metadata_thread = MetadataLoadThread(
            self.data_manager,
            DEFAULT_NETWORK,
            DEFAULT_STATION,
        )

        def on_metadata_loaded():
            logger.info("Metadata refresh complete, updating UI...")
            if self.data_picker and self.data_picker.data_manager:
                self.data_picker._load_available_years()
            else:
                logger.warning(
                    "Cannot update UI: DataPicker or DataManager not available"
                )

        self.metadata_thread.metadata_loaded.connect(on_metadata_loaded)
        self.metadata_thread.start()
        logger.info("Background metadata refresh thread started")

    def _restore_data_selection(self, selection: dict):
        """Restore data selection and trigger data load."""
        network = selection["network"]
        station = selection["station"]
        year = selection["year"]
        doy = selection["doy"]

        logger.info(
            "Restoring data selection: %s/%s/%s/%s", network, station, year, doy
        )

        self.data_picker.station_combo.blockSignals(True)
        self.data_picker.year_combo.blockSignals(True)
        self.data_picker.day_combo.blockSignals(True)

        try:
            network_index = self.data_picker.network_combo.findText(network)
            if network_index >= 0:
                self.data_picker.network_combo.setCurrentIndex(network_index)

            station_index = self.data_picker.station_combo.findText(station)
            if station_index >= 0:
                self.data_picker.station_combo.setCurrentIndex(station_index)

            if self.data_picker.data_manager:
                try:
                    years = self.data_picker.data_manager.get_available_years(
                        network, station
                    )
                    self.data_picker._available_years = years

                    self.data_picker.year_combo.clear()
                    if years:
                        self.data_picker.year_combo.addItems([str(y) for y in years])
                        year_index = self.data_picker.year_combo.findText(str(year))
                        if year_index >= 0:
                            self.data_picker.year_combo.setCurrentIndex(year_index)
                        else:
                            logger.warning("Year %s not found in available years", year)
                            self.data_picker.year_combo.setCurrentIndex(0)
                    else:
                        logger.warning("No years found for %s/%s", network, station)
                except Exception as e:
                    logger.error("Failed to load available years: %s", e, exc_info=True)

            if self.data_picker.data_manager and self.data_picker.year_combo.count() > 0:
                try:
                    days = self.data_picker.data_manager.get_available_days(
                        network, station, year
                    )
                    self.data_picker._available_days = days

                    self.data_picker.day_combo.clear()
                    if days:
                        self.data_picker.day_combo.addItems([str(d) for d in days])
                        day_index = self.data_picker.day_combo.findText(str(doy))
                        if day_index >= 0:
                            self.data_picker.day_combo.setCurrentIndex(day_index)
                        else:
                            logger.warning("Day %s not found in available days", doy)
                            self.data_picker.day_combo.setCurrentIndex(0)
                    else:
                        logger.warning(
                            "No days found for %s/%s/%s", network, station, year
                        )
                except Exception as e:
                    logger.error("Failed to load available days: %s", e, exc_info=True)

            self.data_picker.load_requested.emit(
                {
                    "network": network,
                    "station": station,
                    "year": year,
                    "doy": doy,
                }
            )
        finally:
            self.data_picker.station_combo.blockSignals(False)
            self.data_picker.year_combo.blockSignals(False)
            self.data_picker.day_combo.blockSignals(False)
