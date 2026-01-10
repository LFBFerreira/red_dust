# Interactive Objects Streaming - Development Plan

## Overview
Enhance the Interactive Objects system to support per-object streaming controls with data remapping, individual start/stop controls, and visual feedback. Each object card will stream waveform data independently with customizable remapping parameters.

## Current State Analysis

### Existing Components
1. **ObjectCard** (`ui/object_cards.py`):
   - Basic OSC configuration (address, host, port, scale, enabled)
   - Vertical card layout
   - Simple scale slider (0-100%)

2. **OSCManager** (`core/osc_manager.py`):
   - Streams normalized data (0-1) to all objects simultaneously
   - Uses single scale factor per object
   - Streaming controlled globally (starts/stops with playback)

3. **WaveformModel** (`core/waveform_model.py`):
   - Provides normalized values (0-1) based on percentile normalization
   - Single normalization range for active channel

### Current Limitations
- All objects receive same normalized value
- No per-object remapping (min/max range adjustment)
- No per-object streaming controls (all stream together)
- No visual feedback of streamed values
- Cards arranged vertically
- Port is per-object, not centralized in settings

## Requirements

### 1. Per-Object Streaming Controls
- **Start/Stop buttons** for each object
- Independent streaming state per object
- Objects can stream even when playback is paused/stopped (using current playhead position)

### 2. Data Remapping
- **Input Range**: Normalized data (0-1) from waveform model
- **Output Range**: User-defined min/max values
- **Remapping Formula**: `output = input_min + (normalized_value * (input_max - input_min))`
- **UI Controls**: 
  - Min value input (DoubleSpinBox)
  - Max value input (DoubleSpinBox)
  - Visual preview of remapping range

### 3. IP Address Configuration
- **IP Address**: Per-object (already exists as "Host")
- **Port**: Hardcoded per-object but default from `settings.py`
- Add `STREAMING_PORT` constant to `settings.py`
- Port field should use default from settings but allow override

### 4. Stream Name Mapping
- **Cache Name to IP Mapping**: Store mapping of stream name (object name) to IP address
- Display stream name prominently in card
- Use stream name in OSC address (already partially implemented)

### 5. Visual Feedback
- **Progress Bar Style Visualizer**: 
  - Shows final remapped value
  - Horizontal progress bar (0-100% based on remapped value)
  - Color-coded (e.g., green for normal, red for high)
  - Updates in real-time during streaming
  - Shows numeric value alongside bar

### 6. UI Layout Changes
- **Horizontal Card Layout**: Cards arranged side-by-side
- **Taller Row**: Increase height of Interactive Objects row
- **Horizontal Scroll**: Enable horizontal scrolling for many cards
- **Card Width**: Fixed or minimum width for cards

## Implementation Plan

### Phase 1: Settings & Configuration
**File: `settings.py`**
- [ ] Add `STREAMING_PORT = 8000` constant
- [ ] Document port usage

### Phase 2: Data Remapping System
**File: `core/osc_manager.py`**
- [ ] Extend `OSCObject` class:
  - Add `remap_min` and `remap_max` properties
  - Add `streaming_enabled` property (per-object streaming state)
  - Modify `send()` method to apply remapping:
    ```python
    def remap_value(self, normalized_value: float) -> float:
        """Remap normalized value (0-1) to output range."""
        if self.remap_max == self.remap_min:
            return self.remap_min
        return self.remap_min + (normalized_value * (self.remap_max - self.remap_min))
    ```
- [ ] Update `OSCManager`:
  - Add per-object streaming state tracking
  - Modify `_send_frame()` to check per-object streaming state
  - Add methods: `start_object_streaming(name)`, `stop_object_streaming(name)`
  - Emit signal when object streaming state changes

**File: `core/waveform_model.py`**
- [ ] No changes needed (already provides normalized 0-1 values)

### Phase 3: UI Components - Object Card
**File: `ui/object_cards.py`**

#### ObjectCard Enhancements:
- [ ] **Stream Name Display**: 
  - Prominent label at top (already exists as name)
  - Make it editable or show as read-only with edit option

- [ ] **IP Address**:
  - Rename "Host" label to "IP Address" for clarity
  - Keep existing QLineEdit

- [ ] **Port**:
  - Use default from `settings.STREAMING_PORT`
  - Allow override via QSpinBox
  - Show "(default)" indicator when using default

- [ ] **Remapping Controls**:
  - Add "Remapping" section
  - Min value: QDoubleSpinBox (default: 0.0)
  - Max value: QDoubleSpinBox (default: 1.0)
  - Range validation (min < max)
  - Visual indicator showing input range (0-1) → output range (min-max)

- [ ] **Streaming Controls**:
  - Add "Streaming" section
  - Start button (enabled when stopped)
  - Stop button (enabled when streaming)
  - Status indicator (label showing "Streaming" or "Stopped")
  - Connect to OSCManager per-object streaming methods

- [ ] **Value Visualizer**:
  - Add "Value" section
  - QProgressBar widget (horizontal, 0-100%)
  - QLabel showing numeric value
  - Update via signal from OSCManager
  - Color coding:
    - Green: 0-50%
    - Yellow: 50-75%
    - Red: 75-100%

- [ ] **Remove old "Scale" control** (replaced by remapping)
- [ ] **Remove old "Enabled" checkbox** (replaced by Start/Stop)

#### ObjectCardsContainer Changes:
- [ ] Change `cards_layout` from `QVBoxLayout` to `QHBoxLayout`
- [ ] Enable horizontal scrolling:
  - Set `setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)`
  - Set `setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)`
- [ ] Set fixed/minimum card width
- [ ] Add stretch at end of horizontal layout

### Phase 4: Signal Connections
**File: `ui/main_window.py`**

- [ ] Connect object card signals:
  - `streaming_started` signal → `osc_manager.start_object_streaming()`
  - `streaming_stopped` signal → `osc_manager.stop_object_streaming()`
  - `remap_changed` signal → update OSC object remapping parameters
  - `value_updated` signal → update progress bar in card

- [ ] Connect OSCManager signals:
  - `object_streaming_state_changed` → update card UI (start/stop buttons)
  - `object_value_updated` → update progress bar and value label

- [ ] Update `_on_object_config_changed()`:
  - Handle remapping parameters
  - Handle per-object streaming state

### Phase 5: Real-time Value Updates
**File: `core/osc_manager.py`**

- [ ] Add signal: `object_value_updated = Signal(str, float)` 
  - Emits: (object_name, remapped_value)
- [ ] Emit signal in `_send_frame()` after remapping
- [ ] Only emit for objects that are actively streaming

**File: `ui/object_cards.py`**

- [ ] Add method `update_value(value: float)` to ObjectCard
- [ ] Update progress bar and value label
- [ ] Connect to OSCManager signal in MainWindow

### Phase 6: UI Layout Adjustments
**File: `ui/main_window.py`**

- [ ] Set minimum height for `object_cards` widget
- [ ] Adjust stretch factors if needed
- [ ] Test with multiple cards (horizontal scrolling)

**File: `ui/object_cards.py`**

- [ ] Set fixed width for cards (e.g., 250-300px)
- [ ] Set minimum height for cards
- [ ] Ensure cards align properly horizontally

### Phase 7: Session Management
**File: `core/session_manager.py`**

- [ ] Update `create_state_dict()`:
  - Include remapping parameters (remap_min, remap_max)
  - Include per-object streaming state
  - Include IP address and port

- [ ] Update `restore_objects()`:
  - Restore remapping parameters
  - Restore streaming state (but don't auto-start streaming)
  - Restore IP and port

## Data Flow

```
WaveformModel (normalized 0-1)
    ↓
PlaybackController (current timestamp)
    ↓
OSCManager._send_frame() (60 Hz timer)
    ↓
For each OSCObject:
    - Check if object streaming is enabled
    - Get normalized value from WaveformModel
    - Apply remapping: remap_min + (normalized * (remap_max - remap_min))
    - Send via OSC
    - Emit value_updated signal
    ↓
ObjectCard.update_value() → Update progress bar & label
```

## UI Layout Structure

```
┌─────────────────────────────────────────────────────────────┐
│ Interactive Objects                    [Add Object]         │
├─────────────────────────────────────────────────────────────┤
│ ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐      │
│ │ Object 1 │ │ Object 2 │ │ Object 3 │ │ Object 4 │ ...  │
│ │          │ │          │ │          │ │          │      │
│ │ Name:    │ │ Name:    │ │ Name:    │ │ Name:    │      │
│ │ [IP]     │ │ [IP]     │ │ [IP]     │ │ [IP]     │      │
│ │          │ │          │ │          │ │          │      │
│ │ Remap:   │ │ Remap:   │ │ Remap:   │ │ Remap:   │      │
│ │ Min: [0] │ │ Min: [0] │ │ Min: [0] │ │ Min: [0] │      │
│ │ Max: [1] │ │ Max: [1] │ │ Max: [1] │ │ Max: [1] │      │
│ │          │ │          │ │          │ │          │      │
│ │ [Start]  │ │ [Stop]   │ │ [Start]  │ │ [Start]  │      │
│ │          │ │          │ │          │ │          │      │
│ │ Value:   │ │ Value:   │ │ Value:   │ │ Value:   │      │
│ │ [████]   │ │ [███]    │ │ [█████]  │ │ [██]     │      │
│ │ 0.75     │ │ 0.50     │ │ 0.90     │ │ 0.30     │      │
│ └──────────┘ └──────────┘ └──────────┘ └──────────┘      │
└─────────────────────────────────────────────────────────────┘
```

## Testing Checklist

- [ ] Create multiple object cards
- [ ] Verify horizontal layout and scrolling
- [ ] Test per-object start/stop streaming
- [ ] Test remapping with various min/max values
- [ ] Verify progress bar updates in real-time
- [ ] Test with playback playing/paused/stopped
- [ ] Verify OSC messages sent correctly
- [ ] Test session save/load with new parameters
- [ ] Test port default from settings
- [ ] Test edge cases (min=max, negative values, etc.)

## Migration Notes

### Breaking Changes
- Old "Scale" control removed (replaced by remapping)
- Old "Enabled" checkbox removed (replaced by Start/Stop)
- Per-object streaming state (not global)

### Backward Compatibility
- Session files: Old sessions will load with defaults:
  - remap_min = 0.0
  - remap_max = 1.0
  - streaming_enabled = False (user must start manually)

## Future Enhancements (Out of Scope)
- Preset remapping ranges
- Value history graph
- OSC message rate display
- Connection status indicator
- Multiple remapping curves (e.g., logarithmic)

