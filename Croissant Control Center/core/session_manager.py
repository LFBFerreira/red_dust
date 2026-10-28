"""
Session Manager for saving and loading application state.
"""
import json
import uuid
from pathlib import Path
from typing import Dict, Optional, Any
from obspy import UTCDateTime
import logging

from settings import SERIAL_BAUDRATE, STREAMING_PORT

logger = logging.getLogger(__name__)


class SessionManager:
    """Manages saving and loading application sessions."""
    
    def __init__(self, sessions_dir: Path = Path("sessions")):
        """
        Initialize SessionManager.
        
        Args:
            sessions_dir: Directory for session files
        """
        self.sessions_dir = Path(sessions_dir)
        self.sessions_dir.mkdir(parents=True, exist_ok=True)
    
    def save_session(self, file_path: Path, state: Dict[str, Any]) -> None:
        """
        Save session state to JSON file.
        
        Args:
            file_path: Path to save session file
            state: State dictionary
        """
        try:
            # Convert UTCDateTime objects to ISO8601 strings
            serializable_state = self._make_serializable(state)
            
            with open(file_path, 'w') as f:
                json.dump(serializable_state, f, indent=2)
            
            logger.info(f"Session saved to {file_path}")
        except Exception as e:
            logger.error(f"Failed to save session: {e}")
            raise
    
    def load_session(self, file_path: Path) -> Dict[str, Any]:
        """
        Load session state from JSON file.
        
        Args:
            file_path: Path to session file
        
        Returns:
            State dictionary
        
        Raises:
            FileNotFoundError: If file doesn't exist
            ValueError: If JSON is invalid
        """
        if not file_path.exists():
            raise FileNotFoundError(f"Session file not found: {file_path}")
        
        try:
            with open(file_path, 'r') as f:
                state = json.load(f)
            
            # Convert ISO8601 strings back to UTCDateTime where needed
            state = self._deserialize_timestamps(state)
            
            logger.info(f"Session loaded from {file_path}")
            return state
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in session file: {e}")
            raise ValueError(f"Invalid session file: {e}")
        except Exception as e:
            logger.error(f"Failed to load session: {e}")
            raise
    
    def create_state_dict(
        self,
        data_manager,
        waveform_model,
        playback_controller,
        osc_manager,
        data_picker=None,
        object_cards=None,
        app_color_scheme: Optional[str] = None,
        croissant: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Create state dictionary from current application state.
        
        Args:
            data_manager: DataManager instance
            waveform_model: WaveformModel instance
            playback_controller: PlaybackController instance
            osc_manager: OSCManager instance
            data_picker: DataPicker instance (optional)
            object_cards: Object cards container (optional)
            app_color_scheme: ``system`` | ``light`` | ``dark`` for session JSON (optional)
            croissant: Two-station story timeline / pin cue dict (optional)

        Returns:
            State dictionary
        """
        state = {}

        if app_color_scheme is not None:
            state["app_color_scheme"] = str(app_color_scheme).strip().lower()

        # Data picker selection (network, station, year, doy)
        if data_picker:
            selection = data_picker.get_selection()
            state['data_selection'] = {
                'network': selection['network'],
                'station': selection['station'],
                'year': selection['year'],
                'doy': selection['doy']
            }
        
        # Dataset information (if available)
        if waveform_model and waveform_model.get_stream():
            # Try to infer from stream metadata
            stream = waveform_model.get_stream()
            if stream and len(stream) > 0:
                trace = stream[0]
                state['dataset'] = {
                    'network': trace.stats.network,
                    'station': trace.stats.station,
                }
        
        if waveform_model:
            state['selected_channels'] = waveform_model.get_selected_channels()
            lo_p, hi_p = waveform_model.get_scaling_percentiles()
            state['scaling'] = {
                'lo_percentile': lo_p,
                'hi_percentile': hi_p,
            }
        
        # Playback settings
        if playback_controller:
            state['playback'] = {
                'speed': playback_controller.get_speed(),
                'loop_enabled': playback_controller.is_loop_enabled(),
            }
            ct = playback_controller.get_current_timestamp()
            if ct is not None:
                state['playback']['current_time'] = ct

            loop_range = playback_controller.get_loop_range()
            if loop_range:
                state['playback']['loop_start'] = loop_range[0]
                state['playback']['loop_end'] = loop_range[1]
            else:
                state['playback']['loop_start'] = None
                state['playback']['loop_end'] = None
        
        # Interactive objects (OSC and Serial) — prefer live card config for title + pin_rows
        objects = []
        if object_cards and osc_manager:
            for cfg in object_cards.get_all_configs():
                oid = cfg.get("object_id")
                if not oid:
                    continue
                entry = dict(cfg)
                o = osc_manager.get_object(oid)
                if o:
                    entry["streaming_enabled"] = o.streaming_enabled
                objects.append(entry)
        elif osc_manager:
            for _, obj in osc_manager.get_all_objects().items():
                obj_config = obj.get_config_dict()
                obj_config["streaming_enabled"] = obj.streaming_enabled
                objects.append(obj_config)
        if objects:
            state["objects"] = objects

        if croissant:
            state["croissant"] = croissant

        return state
    
    def _make_serializable(self, obj: Any) -> Any:
        """Convert non-serializable objects to JSON-compatible types."""
        if isinstance(obj, UTCDateTime):
            return obj.isoformat()
        elif isinstance(obj, dict):
            return {k: self._make_serializable(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            return [self._make_serializable(item) for item in obj]
        elif isinstance(obj, Path):
            return str(obj)
        else:
            return obj
    
    def _deserialize_timestamps(self, obj: Any) -> Any:
        """Convert ISO8601 strings back to UTCDateTime where appropriate."""
        if isinstance(obj, dict):
            # Check for timestamp-like keys
            timestamp_keys = ('loop_start', 'loop_end', 'current_time')
            result = {}
            for k, v in obj.items():
                if k in timestamp_keys and isinstance(v, str):
                    try:
                        result[k] = UTCDateTime(v)
                    except:
                        result[k] = v
                else:
                    result[k] = self._deserialize_timestamps(v)
            return result
        elif isinstance(obj, list):
            return [self._deserialize_timestamps(item) for item in obj]
        else:
            return obj
    
    def get_data_selection(self, state: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Get data selection from state dictionary.
        
        Args:
            state: State dictionary loaded from file
        
        Returns:
            Dictionary with network, station, year, doy or None
        """
        if 'data_selection' not in state:
            return None
        
        selection = state['data_selection']
        network = selection.get('network')
        station = selection.get('station')
        year = selection.get('year')
        doy = selection.get('doy')
        
        if not (network and station and year and doy):
            return None
        
        return {
            'network': network,
            'station': station,
            'year': year,
            'doy': doy
        }
    
    def _migrate_interactive_object_config(
        self, obj_config: dict, session_state: Optional[dict]
    ) -> dict:
        cfg = dict(obj_config)
        if "scale" in cfg and "remap_max" not in cfg:
            cfg["remap_max"] = cfg.pop("scale")
            cfg["remap_min"] = 0.0
        if "enabled" in cfg and "streaming_enabled" not in cfg:
            cfg["streaming_enabled"] = cfg.pop("enabled")

        oid = cfg.get("object_id") or cfg.get("name")
        if not oid:
            oid = str(uuid.uuid4())
        cfg["object_id"] = oid
        if "title" not in cfg:
            cfg["title"] = str(cfg.get("name", "Object"))

        if cfg.get("pin_rows"):
            return cfg

        remap_min = cfg.get("remap_min")
        remap_max = cfg.get("remap_max")
        if remap_min is None or remap_max is None:
            scale = cfg.get("scale", 1.0)
            remap_min = 0.0
            remap_max = scale

        ch = None
        if session_state:
            raw = session_state.get("selected_channels") or []
            if isinstance(raw, list) and raw:
                ch = raw[0]
        if ch:
            cfg["pin_rows"] = [
                {
                    "row_id": str(uuid.uuid4()),
                    "channel_id": ch,
                    "remap_min": float(remap_min),
                    "remap_max": float(remap_max),
                    "slot_index": 0,
                }
            ]
        else:
            cfg["pin_rows"] = []
        return cfg

    def restore_objects(
        self,
        objects: list,
        osc_manager,
        object_cards,
        session_state: Optional[dict] = None,
    ) -> None:
        """
        Restore interactive objects (OSC and Serial).

        Args:
            objects: List of object configuration dictionaries
            osc_manager: OSCManager instance
            object_cards: ObjectCardsContainer instance
            session_state: Full session dict (optional, for legacy pin_row migration)
        """
        if not objects:
            return

        logger.info("Restoring %s interactive objects", len(objects))

        if object_cards:
            oids = list(object_cards._cards.keys())
            for oid in oids:
                object_cards._remove_object(oid)

        if osc_manager:
            for oid in list(osc_manager._objects.keys()):
                osc_manager.remove_object(oid)

        for obj_config in objects:
            cfg = self._migrate_interactive_object_config(obj_config, session_state)
            oid = cfg["object_id"]
            comm_type = cfg.get("type", "OSC")

            cfg["streaming_enabled"] = False

            if object_cards:
                card = object_cards._add_object(
                    comm_type,
                    object_id=oid,
                    display_title=cfg.get("title", "Object"),
                    emit_added=False,
                )
                card.set_config(cfg)
                object_cards.object_added.emit(oid)
            elif osc_manager:
                from core.pin_stream import pin_rows_from_dicts

                pin_rows = pin_rows_from_dicts(cfg.get("pin_rows") or [])
                if comm_type == "OSC":
                    osc_manager.add_osc_object(
                        oid,
                        cfg.get("address", f"/red_dust/{oid.lower().replace(' ', '_')}"),
                        cfg.get("host", "127.0.0.1"),
                        cfg.get("port", STREAMING_PORT),
                        pin_rows,
                    )
                elif comm_type == "Serial":
                    osc_manager.add_serial_object(
                        oid,
                        cfg.get("port", "COM3"),
                        cfg.get("baudrate", SERIAL_BAUDRATE),
                        pin_rows,
                    )
                else:
                    logger.warning(
                        "Unknown communication type %s for object %s, skipping",
                        comm_type,
                        oid,
                    )

