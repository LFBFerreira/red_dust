"""Background QThread helpers used by the main window."""

import logging
import time

from PySide6.QtCore import QThread, Signal

logger = logging.getLogger(__name__)


class DataLoadThread(QThread):
    """Thread for loading data in background."""

    data_loaded = Signal(object)  # Emits Stream
    error_occurred = Signal(str)  # Emits error message
    file_count_known = Signal(int)  # Emits total file count when known
    download_progress = Signal(int, int)  # Emits (downloaded, total) progress

    def __init__(self, data_manager, network, station, year, doy):
        super().__init__()
        self.data_manager = data_manager
        self.network = network
        self.station = station
        self.year = year
        self.doy = doy

    def _interrupted(self) -> bool:
        return self.isInterruptionRequested()

    def run(self):
        thread_start = time.time()
        logger.info(
            "DataLoadThread started for %s/%s/%s/%03d",
            self.network,
            self.station,
            self.year,
            self.doy,
        )

        try:
            if self._interrupted():
                logger.info("DataLoadThread cancelled before start")
                return

            def progress_callback(downloaded: int, total: int):
                if self._interrupted():
                    return
                self.download_progress.emit(downloaded, total)

            def file_count_callback(total: int):
                if self._interrupted():
                    return
                logger.info("Total files to download: %s", total)
                self.file_count_known.emit(total)

            fetch_start = time.time()
            logger.info("Starting fetch_and_cache...")
            cache_path = self.data_manager.fetch_and_cache(
                self.network,
                self.station,
                self.year,
                self.doy,
                progress_callback=progress_callback,
                file_count_callback=file_count_callback,
                cancel_check=self._interrupted,
            )
            fetch_time = time.time() - fetch_start
            logger.info("fetch_and_cache completed in %.2fs", fetch_time)

            if self._interrupted():
                logger.info("DataLoadThread cancelled after fetch")
                return

            load_start = time.time()
            logger.info("Starting load_from_cache...")
            stream = self.data_manager.load_from_cache(
                cache_path, cancel_check=self._interrupted
            )
            load_time = time.time() - load_start
            logger.info("load_from_cache completed in %.2fs", load_time)

            if self._interrupted():
                logger.info("DataLoadThread cancelled after cache load")
                return

            total_time = time.time() - thread_start
            logger.info("DataLoadThread complete in %.2fs total", total_time)
            self.data_loaded.emit(stream)
        except InterruptedError:
            logger.info(
                "DataLoadThread cancelled for %s/%s/%s/%03d",
                self.network,
                self.station,
                self.year,
                self.doy,
            )
        except Exception as e:
            if self._interrupted():
                logger.info(
                    "DataLoadThread cancelled during error handling for %s/%s/%s/%03d",
                    self.network,
                    self.station,
                    self.year,
                    self.doy,
                )
                return
            logger.exception(
                "Error in data load thread for %s/%s/%s/%03d",
                self.network,
                self.station,
                self.year,
                self.doy,
            )
            self.error_occurred.emit(str(e))


class MetadataLoadThread(QThread):
    """Refresh station metadata cache in the background."""

    metadata_loaded = Signal()

    def __init__(self, data_manager, network, station):
        super().__init__()
        self.data_manager = data_manager
        self.network = network
        self.station = station

    def run(self):
        try:
            logger.info(
                "Starting background metadata refresh for %s/%s...",
                self.network,
                self.station,
            )
            self.data_manager.refresh_metadata_cache(self.network, self.station)
            logger.info("Background metadata refresh completed successfully")
            self.metadata_loaded.emit()
        except Exception as e:
            logger.error(
                "Failed to refresh metadata in background: %s", e, exc_info=True
            )
            self.metadata_loaded.emit()

