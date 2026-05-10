"""Menu bar, session save/load, and about dialog."""

import logging
from pathlib import Path

from PySide6.QtWidgets import QFileDialog, QMessageBox, QMenu
from PySide6.QtGui import QCursor

from .base import _MainWindowBase

logger = logging.getLogger(__name__)


class MainWindowSessionMixin(_MainWindowBase):
    """File menu, recent sessions, and session persistence."""

    def _setup_menu_bar(self):
        """Set up the menu bar with File and About menus."""
        menubar = self.menuBar()

        file_menu = menubar.addMenu("File")

        save_action = file_menu.addAction("Save")
        save_action.setShortcut("Ctrl+S")
        save_action.triggered.connect(self._on_save)

        save_as_action = file_menu.addAction("Save As...")
        save_as_action.setShortcut("Ctrl+Shift+S")
        save_as_action.triggered.connect(self._on_save_as)

        load_action = file_menu.addAction("Load...")
        load_action.setShortcut("Ctrl+O")
        load_action.triggered.connect(self._on_load)

        load_recent_action = file_menu.addAction("Load Recent")
        load_recent_action.triggered.connect(self._on_load_recent)

        about_menu = menubar.addMenu("About")

        about_action = about_menu.addAction("About Red Dust Control Center")
        about_action.triggered.connect(self._on_about)

    def _get_recent_sessions(self, max_count: int = 10) -> list[Path]:
        """
        Get list of recent session files, sorted by modification time.

        Args:
            max_count: Maximum number of recent sessions to return

        Returns:
            List of Path objects to recent session files, most recent first
        """
        sessions_dir = self.session_manager.sessions_dir
        if not sessions_dir.exists():
            return []

        session_files = list(sessions_dir.glob("*.json"))

        session_files.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        return session_files[:max_count]

    def _on_load_recent(self):
        """Handle Load Recent toolbar action - show menu with recent sessions."""
        recent_sessions = self._get_recent_sessions()

        if not recent_sessions:
            QMessageBox.information(
                self,
                "No Recent Sessions",
                "No recent session files found.",
            )
            return

        menu = QMenu(self)

        for session_path in recent_sessions:
            display_name = session_path.name
            action = menu.addAction(display_name)
            action.setData(str(session_path))
            action.triggered.connect(
                lambda checked, path=session_path: self._load_session(path)
            )

        menu.exec(QCursor.pos())

    def _on_save(self):
        """Handle Save menu action."""
        if self.current_session_path:
            self._save_session(self.current_session_path)
        else:
            self._on_save_as()

    def _on_save_as(self):
        """Handle Save As menu action."""
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Session",
            str(self.session_manager.sessions_dir / "session.json"),
            "JSON Files (*.json);;All Files (*)",
        )

        if file_path:
            self.current_session_path = Path(file_path)
            self._save_session(self.current_session_path)

    def _save_session(self, file_path: Path):
        """Save current application state to file."""
        try:
            state = self.session_manager.create_state_dict(
                self.data_manager,
                self.waveform_model,
                self.playback_controller,
                self.osc_manager,
                self.data_picker,
                self.object_cards,
            )

            self.session_manager.save_session(file_path, state)

            QMessageBox.information(
                self,
                "Session Saved",
                f"Session saved successfully to:\n{file_path}",
            )
            logger.info("Session saved to %s", file_path)
        except Exception as e:
            logger.error("Failed to save session: %s", e, exc_info=True)
            QMessageBox.critical(
                self,
                "Save Error",
                f"Failed to save session:\n{str(e)}",
            )

    def _on_load(self):
        """Handle Load menu action."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Load Session",
            str(self.session_manager.sessions_dir),
            "JSON Files (*.json);;All Files (*)",
        )

        if file_path:
            self._load_session(Path(file_path))

    def _load_session(self, file_path: Path):
        """Load application state from file."""
        try:
            state = self.session_manager.load_session(file_path)

            self.pending_session_state = state

            selection = self.session_manager.get_data_selection(state)
            if selection:
                self._restore_data_selection(selection)

            if "objects" in state:
                self.session_manager.restore_objects(
                    state["objects"],
                    self.osc_manager,
                    self.object_cards,
                    state,
                )

            if self.waveform_model.get_stream():
                self._restore_session_state_after_load(state)
                self.pending_session_state = None

            self.current_session_path = file_path

            QMessageBox.information(
                self,
                "Session Loaded",
                f"Session loaded successfully from:\n{file_path}",
            )
            logger.info("Session loaded from %s", file_path)
        except FileNotFoundError:
            QMessageBox.warning(
                self,
                "Load Error",
                f"File not found:\n{file_path}",
            )
        except ValueError as e:
            QMessageBox.critical(
                self,
                "Load Error",
                f"Invalid session file:\n{str(e)}",
            )
        except Exception as e:
            logger.error("Failed to load session: %s", e, exc_info=True)
            QMessageBox.critical(
                self,
                "Load Error",
                f"Failed to load session:\n{str(e)}",
            )

    def _restore_session_state_after_load(self, state: dict):
        """Restore session state that depends on data being loaded."""
        if "selected_channels" in state and self.waveform_model:
            raw_sel = state["selected_channels"]
            if not isinstance(raw_sel, list):
                raw_sel = []
            self.waveform_model.set_selected_channels(raw_sel)
            sel = self.waveform_model.get_selected_channels()
            if self.playback_controls:
                self.playback_controls.set_selected_channels(sel)
            if self.waveform_viewer:
                stream = self.waveform_model.get_stream()
                if stream:
                    self.waveform_viewer.update_waveform(stream, sel)
            if not sel:
                self.playback_controller.stop()
            self._update_metadata()
            self._update_object_card_channels()
            tr = self.waveform_model.get_time_range()
            ct = self.playback_controller.get_current_timestamp()
            if tr and ct is not None:
                self.playback_controls.update_position_slider(ct, tr[0], tr[1])
                self.playback_controls.update_time_display(ct, tr[0], tr[1])
            self._refresh_value_display()

        if "playback" in state:
            playback_state = state["playback"]

            if "speed" in playback_state:
                speed = playback_state["speed"]
                if self.playback_controls:
                    self.playback_controls.set_speed(speed)
                self.playback_controller.set_speed(speed)

            if "loop_start" in playback_state and "loop_end" in playback_state:
                loop_start = playback_state["loop_start"]
                loop_end = playback_state["loop_end"]
                if loop_start and loop_end:
                    try:
                        self.playback_controller.set_loop_range(loop_start, loop_end)
                        loop_enabled = playback_state.get("loop_enabled", False)
                        self.playback_controller.enable_loop(loop_enabled)
                        if self.playback_controls:
                            self.playback_controls.set_loop_enabled(loop_enabled)
                            self.playback_controls.update_loop_display(
                                loop_start, loop_end
                            )
                        if self.waveform_viewer:
                            self.waveform_viewer.set_loop_range(loop_start, loop_end)
                    except Exception as e:
                        logger.warning("Failed to restore loop range: %s", e)
            elif self.playback_controls:
                self.playback_controls.set_loop_enabled(False)

    def _on_about(self):
        """Handle About menu action."""
        QMessageBox.about(
            self,
            "About Red Dust Control Center",
            "Red Dust Control Center\n\n"
            "A tool for visualizing and controlling seismic waveform data.\n\n"
            "Features:\n"
            "- Load and visualize seismic data from PDS archive\n"
            "- Playback control with variable speed\n"
            "- Loop range selection\n"
            "- OSC output to interactive objects\n"
            "- Save and load session configurations",
        )
