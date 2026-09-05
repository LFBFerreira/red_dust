"""Menu bar, session save/load, and about dialog."""

import logging
from pathlib import Path

from obspy import UTCDateTime
from PySide6.QtCore import QSettings
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import QFileDialog, QMessageBox, QMenu, QApplication

from settings import QSETTINGS_APPLICATION, QSETTINGS_ORGANIZATION
from ui.theme import (
    apply_app_color_scheme,
    read_saved_color_scheme,
    write_saved_color_scheme,
    normalize_color_scheme,
)
from ui.view_prefs import read_show_log, write_show_log
from ui.widget_debug import read_show_widget_debug_borders, write_show_widget_debug_borders

from .base import _MainWindowBase

logger = logging.getLogger(__name__)

_RECENT_SESSION_FILES_KEY = "recent_session_files"
_RECENT_SESSION_FILES_MAX_STORED = 20


class MainWindowSessionMixin(_MainWindowBase):
    """File menu, recent sessions, and session persistence."""

    def _setup_menu_bar(self):
        """Set up the menu bar with File, Theme, and About menus."""
        self._app_color_scheme = read_saved_color_scheme()

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

        theme_menu = menubar.addMenu("Theme")
        self._theme_action_group = QActionGroup(self)
        self._theme_action_group.setExclusive(True)
        self._theme_actions: dict[str, QAction] = {}
        for label, mode in (
            ("System", "system"),
            ("Light", "light"),
            ("Dark", "dark"),
        ):
            act = QAction(label, self)
            act.setCheckable(True)
            act.setData(mode)
            self._theme_action_group.addAction(act)
            theme_menu.addAction(act)
            self._theme_actions[mode] = act
            act.triggered.connect(
                lambda checked=False, m=mode: self._on_theme_selected(m)
            )
        self._sync_theme_menu_checks()

        view_menu = menubar.addMenu("View")
        self._view_log_action = QAction("View Log", self)
        self._view_log_action.setCheckable(True)
        self._view_log_action.setChecked(read_show_log())
        self._view_log_action.triggered.connect(self._on_view_log_toggled)
        view_menu.addAction(self._view_log_action)

        self._show_widget_boundaries_action = QAction(
            "Show Widget Boundaries", self
        )
        self._show_widget_boundaries_action.setCheckable(True)
        self._show_widget_boundaries_action.setChecked(
            read_show_widget_debug_borders()
        )
        self._show_widget_boundaries_action.triggered.connect(
            self._on_widget_boundaries_toggled
        )
        view_menu.addAction(self._show_widget_boundaries_action)

        about_menu = menubar.addMenu("About")

        about_action = about_menu.addAction("About Red Dust Control Center")
        about_action.triggered.connect(self._on_about)

    def _session_qsettings(self) -> QSettings:
        return QSettings(QSETTINGS_ORGANIZATION, QSETTINGS_APPLICATION)

    def _sync_theme_menu_checks(self) -> None:
        mode = getattr(self, "_app_color_scheme", read_saved_color_scheme())
        for m, act in self._theme_actions.items():
            act.setChecked(m == mode)

    def _on_theme_selected(self, mode: str) -> None:
        mode = normalize_color_scheme(mode)
        app = QApplication.instance()
        if app:
            apply_app_color_scheme(app, mode)
        write_saved_color_scheme(mode)
        self._app_color_scheme = mode
        self._sync_theme_menu_checks()

    def _on_view_log_toggled(self, checked: bool) -> None:
        write_show_log(checked)
        self._apply_log_visibility(checked)

    def _on_widget_boundaries_toggled(self, checked: bool) -> None:
        write_show_widget_debug_borders(checked)
        self._apply_widget_debug_borders(checked)

    def _apply_session_theme_if_present(self, state: dict) -> None:
        """Apply ``app_color_scheme`` from a loaded session and persist to QSettings."""
        raw = state.get("app_color_scheme")
        if raw is None:
            return
        mode = normalize_color_scheme(str(raw))
        app = QApplication.instance()
        if app:
            apply_app_color_scheme(app, mode)
        write_saved_color_scheme(mode)
        self._app_color_scheme = mode
        self._sync_theme_menu_checks()

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
                app_color_scheme=getattr(
                    self, "_app_color_scheme", read_saved_color_scheme()
                ),
                dust_devil=self._dust_devil_state_dict(),
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

            self._apply_session_theme_if_present(state)

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

            self._restore_dust_devil_state(state)

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
        if "scaling" in state and self.waveform_model:
            sc = state["scaling"]
            if isinstance(sc, dict):
                lo = float(sc.get("lo_percentile", 1.0))
                hi = float(sc.get("hi_percentile", 99.0))
                self.waveform_model.update_scaling(lo, hi)

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

        if "playback" in state:
            playback_state = state["playback"]

            if "speed" in playback_state:
                speed = playback_state["speed"]
                if self.playback_controls:
                    self.playback_controls.set_speed(speed)
                self.playback_controller.set_speed(speed)

            loop_start = playback_state.get("loop_start")
            loop_end = playback_state.get("loop_end")
            if loop_start and loop_end:
                try:
                    self.playback_controller.set_loop_range(loop_start, loop_end)
                    loop_enabled = playback_state.get("loop_enabled", False)
                    self.playback_controller.enable_loop(loop_enabled)
                    if self.playback_controls:
                        self.playback_controls.set_loop_enabled(loop_enabled)
                        tr = self.waveform_model.get_time_range()
                        if tr:
                            self.playback_controls.set_data_time_range(tr[0], tr[1])
                        self.playback_controls.update_loop_display(loop_start, loop_end)
                    self._sync_loop_visualization()
                except Exception as e:
                    logger.warning("Failed to restore loop range: %s", e)
                    self.playback_controller.clear_loop()
                    if self.playback_controls:
                        self.playback_controls.set_loop_enabled(False)
                        self.playback_controls.clear_loop_display()
                    if self.waveform_viewer:
                        self.waveform_viewer.clear_loop_markers()
            else:
                self.playback_controller.clear_loop()
                if self.playback_controls:
                    self.playback_controls.set_loop_enabled(False)
                    self.playback_controls.clear_loop_display()
                if self.waveform_viewer:
                    self.waveform_viewer.clear_loop_markers()

            saved_ct = playback_state.get("current_time")
            tr = self.waveform_model.get_time_range() if self.waveform_model else None
            sel = (
                self.waveform_model.get_selected_channels()
                if self.waveform_model
                else []
            )
            if tr and sel and saved_ct is not None:
                try:
                    ts = (
                        saved_ct
                        if isinstance(saved_ct, UTCDateTime)
                        else UTCDateTime(saved_ct)
                    )
                    self.playback_controller.seek(ts)
                except Exception as e:
                    logger.warning("Failed to restore playhead time: %s", e)
        else:
            self.playback_controller.clear_loop()
            if self.playback_controls:
                self.playback_controls.set_loop_enabled(False)
                self.playback_controls.clear_loop_display()
            if self.waveform_viewer:
                self.waveform_viewer.clear_loop_markers()

        tr = (
            self.waveform_model.get_time_range() if self.waveform_model else None
        )
        ct = (
            self.playback_controller.get_current_timestamp()
            if self.playback_controller
            else None
        )
        if tr and ct is not None and self.playback_controls:
            self.playback_controls.set_data_time_range(tr[0], tr[1])
            self.playback_controls.update_position_slider(ct, tr[0], tr[1])
            self.playback_controls.update_time_display(ct, tr[0], tr[1])
        if self.waveform_viewer and ct is not None:
            self.waveform_viewer.update_playhead(ct)
        self._refresh_value_display()

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
