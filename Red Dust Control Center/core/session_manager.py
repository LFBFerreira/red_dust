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
    
    def create_state_dict(self, data_manager, waveform_model, playback_controller, osc_manager) -> Dict[str, Any]:
        """
        Create state dictionary from current application state.
        
        Args:
            data_manager: DataManager instance
            waveform_model: WaveformModel instance
            playback_controller: PlaybackController instance
            osc_manager: OSCManager instance
        
        Returns:
            State dictionary
        """
        state = {}
        
        # Dataset information (if available)
        if waveform_model and waveform_model.get_stream():
            # Try to infer from stream metadata
            stream = waveform_model.get_stream()
            if stream and len(stream) > 0:
                trace = stream[0]
                state['dataset'] = {
                    'network': trace.stats.network,
                    'station': trace.stats.station,
                    # Year and DOY would need to be stored separately
                    # For now, we'll need to get this from the data manager
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
                    'scale': obj.scale,
                    'enabled': obj.enabled
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

