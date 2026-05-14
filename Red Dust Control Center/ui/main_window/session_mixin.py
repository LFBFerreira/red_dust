"""Menu bar, session save/load, and about dialog."""

import logging
from pathlib import Path

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QFileDialog, QMessageBox, QMenu

from settings import QSETTINGS_APPLICATION, QSETTINGS_ORGANIZATION

from .base import _MainWindowBase

logger = logging.getLogger(__name__)

_RECENT_SESSION_FILES_KEY = "recent_session_files"
_RECENT_SESSION_FILES_MAX_STORED = 20


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

        self._load_recent_menu = QMenu("Load Recent", self)
        self._load_recent_menu.aboutToShow.connect(self._populate_load_recent_menu)
        file_menu.addMenu(self._load_recent_menu)

        about_menu = menubar.addMenu("About")

        about_action = about_menu.addAction("About Red Dust Control Center")
        about_action.triggered.connect(self._on_about)

    def _session_qsettings(self) -> QSettings:
        return QSettings(QSETTINGS_ORGANIZATION, QSETTINGS_APPLICATION)

    def _read_recent_session_paths(self) -> list[str]:
        """Paths from last successful File > Load / Save, most recent first."""
        raw = self._session_qsettings().value(_RECENT_SESSION_FILES_KEY, [])
        if not raw:
            return []
        if isinstance(raw, str):
            return [raw]
        return [str(x) for x in raw]

    def _write_recent_session_paths(self, paths: list[str]) -> None:
        self._session_qsettings().setValue(_RECENT_SESSION_FILES_KEY, paths)

    def _remember_session_path(self, file_path: Path) -> None:
        """Record a session file for File > Load Recent (after successful load or save)."""
        try:
            resolved = str(Path(file_path).resolve())
        except OSError as e:
            logger.warning("Could not resolve session path %s: %s", file_path, e)
            return
        paths = self._read_recent_session_paths()
        paths = [p for p in paths if Path(p).resolve() != Path(resolved)]
        paths.insert(0, resolved)
        paths = paths[:_RECENT_SESSION_FILES_MAX_STORED]
        self._write_recent_session_paths(paths)

    def _get_recent_sessions(self, max_count: int = 10) -> list[Path]:
        """
        Recent session JSON files: MRU from successful Load/Save, then others
        in ``sessions_dir`` by modification time. Paths must still exist.
        """
        raw = self._read_recent_session_paths()
        mru_valid: list[Path] = []
        seen_mru: set[Path] = set()
        for s in raw:
            p = Path(s).expanduser()
            if not p.is_file() or p.suffix.lower() != ".json":
                continue
            key = p.resolve()
            if key in seen_mru:
                continue
            seen_mru.add(key)
            mru_valid.append(p)

        new_stored = [str(p.resolve()) for p in mru_valid]
        if new_stored != list(raw):
            self._write_recent_session_paths(new_stored)

        result = mru_valid[:max_count]
        seen: set[Path] = {p.resolve() for p in result}

        if len(result) < max_count:
            sessions_dir = self.session_manager.sessions_dir
            if sessions_dir.exists():
                extra = [p for p in sessions_dir.glob("*.json") if p.is_file()]
                extra.sort(key=lambda p: p.stat().st_mtime, reverse=True)
                for p in extra:
                    key = p.resolve()
                    if key in seen:
                        continue
                    seen.add(key)
                    result.append(p)
                    if len(result) >= max_count:
                        break

        return result

    def _populate_load_recent_menu(self):
        """Rebuild File → Load Recent submenu when it opens (hover or keyboard)."""
        self._load_recent_menu.clear()
        recent_sessions = self._get_recent_sessions()
        if not recent_sessions:
            placeholder = self._load_recent_menu.addAction("No recent sessions")
            placeholder.setEnabled(False)
            return
        for session_path in recent_sessions:
            action = self._load_recent_menu.addAction(session_path.name)
            action.triggered.connect(
                lambda checked=False, path=session_path: self._load_session(path)
            )

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
            self._remember_session_path(file_path)

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
            self._remember_session_path(file_path)

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
            self._sync_interactive_objects_to_playback_channels(set(sel))
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
