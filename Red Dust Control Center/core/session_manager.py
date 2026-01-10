"""
Session Manager for saving and loading application state.
"""
import json
from pathlib import Path
from typing import Dict, Optional, Any
from obspy import UTCDateTime
import logging

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
    
    def create_state_dict(self, data_manager, waveform_model, playback_controller, osc_manager, data_picker=None) -> Dict[str, Any]:
        """
        Create state dictionary from current application state.
        
        Args:
            data_manager: DataManager instance
            waveform_model: WaveformModel instance
            playback_controller: PlaybackController instance
            osc_manager: OSCManager instance
            data_picker: DataPicker instance (optional)
        
        Returns:
            State dictionary
        """
        state = {}
        
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
        
        # Active channel
        if waveform_model:
            state['active_channel'] = waveform_model.get_active_channel()
            
            # Scaling settings
            # Note: We don't store the percentile values directly, but we could
            # For now, store the normalization range
            state['scaling'] = {
                'lo_percentile': 1.0,  # Default, would need to be stored in model
                'hi_percentile': 99.0
            }
        
        # Playback settings
        if playback_controller:
            state['playback'] = {
                'speed': playback_controller.get_speed(),
                'loop_enabled': playback_controller.is_loop_enabled(),
            }
            
            loop_range = playback_controller.get_loop_range()
            if loop_range:
                state['playback']['loop_start'] = loop_range[0]
                state['playback']['loop_end'] = loop_range[1]
            else:
                state['playback']['loop_start'] = None
                state['playback']['loop_end'] = None
        
        # OSC objects
        if osc_manager:
            objects = []
            for name, obj in osc_manager.get_all_objects().items():
                objects.append({
                    'name': obj.name,
                    'address': obj.address,
                    'host': obj.host,
                    'port': obj.port,
                    'remap_min': obj.remap_min,
                    'remap_max': obj.remap_max,
                    'streaming_enabled': obj.streaming_enabled
                })
            state['objects'] = objects
        
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
            timestamp_keys = ['loop_start', 'loop_end']
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
    
    def restore_objects(self, objects: list, osc_manager, object_cards) -> None:
        """
        Restore OSC objects configuration.
        
        Args:
            objects: List of object configuration dictionaries
            osc_manager: OSCManager instance
            object_cards: ObjectCardsContainer instance
        """
        if not objects:
            return
        
        logger.info(f"Restoring {len(objects)} OSC objects")
        
        # Clear existing objects
        if object_cards:
            # Remove all existing cards
            card_names = list(object_cards._cards.keys())
            for name in card_names:
                object_cards._remove_object(name)
        
        if osc_manager:
            osc_manager._objects.clear()
        
        # Add restored objects
        for obj_config in objects:
            name = obj_config.get('name')
            if name:
                # Add card
                if object_cards:
                    card = object_cards._add_object(name)
                    # Convert old format to new format if needed
                    config = obj_config.copy()
                    if 'scale' in config and 'remap_max' not in config:
                        # Backward compatibility: convert scale to remap_max
                        config['remap_max'] = config.pop('scale')
                        config['remap_min'] = 0.0
                    if 'enabled' in config and 'streaming_enabled' not in config:
                        # Backward compatibility: convert enabled to streaming_enabled
                        config['streaming_enabled'] = config.pop('enabled')
                    card.set_config(config)
                
                # Add OSC object
                if osc_manager:
                    remap_min = obj_config.get('remap_min')
                    remap_max = obj_config.get('remap_max')
                    
                    # Backward compatibility: convert old scale to remap_max
                    if remap_min is None or remap_max is None:
                        scale = obj_config.get('scale', 1.0)
                        remap_min = 0.0
                        remap_max = scale
                    
                    osc_manager.add_object(
                        name,
                        obj_config.get('address', f'/red_dust/{name.lower().replace(" ", "_")}'),
                        obj_config.get('host', '127.0.0.1'),
                        obj_config.get('port', 8000),
                        remap_min,
                        remap_max
                    )
                    
                    # Restore streaming state (but don't auto-start)
                    streaming_enabled = obj_config.get('streaming_enabled', False)
                    # Also check old 'enabled' for backward compatibility
                    if 'enabled' in obj_config and 'streaming_enabled' not in obj_config:
                        streaming_enabled = obj_config.get('enabled', False)
                    
                    if streaming_enabled:
                        # Don't auto-start streaming when loading session
                        # User must manually start streaming
                        pass
                    else:
                        osc_manager.stop_object_streaming(name)

