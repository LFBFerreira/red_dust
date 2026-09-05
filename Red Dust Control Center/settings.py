"""
Configuration settings for Red Dust Control Center.

This module contains default values and configuration constants used throughout
the application. These can be modified to change default behavior.
"""

# --- Application persistence (QSettings) ---

QSETTINGS_ORGANIZATION = "Red Dust"
QSETTINGS_APPLICATION = "RDCC"


# --- Data defaults (PDS / archive selection) ---

DEFAULT_NETWORK = "XB"  # Network code (typically "XB" for InSight SEIS)
DEFAULT_STATION = "ELYSE"
DEFAULT_YEAR = 2019
DEFAULT_DAY_OF_YEAR = 96
AVAILABLE_STATIONS = ["ELYSE", "ELYS0", "ELYHK", "ELYH0"]


# --- Playback & waveform ---

# Max simultaneous waveform channel selections (must be <= len(CHANNEL_TRACE_COLORS)
# in ui/widgets/channel_colors.py; extra palette colors are unused until you raise this).
MAX_SELECTED_CHANNELS = 10

# Cap points sent to pyqtgraph per channel (display only; stream / cache stay full rate).
MAX_WAVEFORM_PLOT_POINTS_PER_CHANNEL = 8000

# Full-screen live strip: one paging window of seismic time, LilyGO-style.
FULLSCREEN_WAVEFORM_WINDOW_SEC = 10.0 * 60.0  # 10 minutes


# --- UI ---

# Theme: default when QSettings has no value yet; Theme menu overrides at runtime
# (``system`` = native Qt style; ``light``/``dark`` = Fusion).
APP_COLOR_SCHEME = "system"

# View menu defaults (persisted in QSettings; see ui/view_prefs.py and ui/widget_debug.py).
SHOW_LOG = False
SHOW_WIDGET_DEBUG_BORDERS = False

# Main window layout.
LEFT_PANEL_WIDTH = 250  # Dataset Information / Data Picker column
STATIONS_PANEL_WIDTH = 720  # Initial width of the Dust Devil timeline column
DEFAULT_WINDOW_WIDTH = 1680
DEFAULT_WINDOW_HEIGHT = 800
WIDGET_PANEL_MARGIN = 12  # Empty space around each major UI panel (pixels)

# Interactive object cards.
TAB_ICON_SIZE = 20  # Streaming status icon in object tabs (pixels)
OBJECT_CARD_LEFT_PANEL_MAX_WIDTH = 300  # OSC/Serial name & connection column (pixels)
OSC_OBJECT_ENDPOINT_DEBOUNCE_MS = 500  # Apply OSC host/address after typing pauses (avoids DNS per key)


# --- Streaming / I/O (firmware & protocol contract) ---

# Multi-pin wire format: index 0 = first float in OSC/Serial frame (Pin_A), etc.
MAX_PIN_SLOTS = 10
PIN_SLOT_LABELS = (
    "Pin_A", "Pin_B", "Pin_C", "Pin_D", "Pin_E",
    "Pin_F", "Pin_G", "Pin_H", "Pin_I", "Pin_J",
)
# Slots with no mapped channel send this float; firmware treats values outside [0, 1] as inactive.
WIRE_INACTIVE_PIN_SENTINEL = -1.0

# OSC (defaults; can be overridden per object).
STREAMING_PORT = 8000
OSC_OUTPUT_RATE = 60  # Hz
OSC_OUTPUT_INTERVAL_MS = 1000 // OSC_OUTPUT_RATE  # ~16.67 ms

# Serial (defaults; can be overridden per object).
SERIAL_BAUDRATE = 115200
SERIAL_OUTPUT_RATE = 60  # Hz
SERIAL_OUTPUT_INTERVAL_MS = 1000 // SERIAL_OUTPUT_RATE  # ~16.67 ms


# --- Dust Devil story timeline (pin on/off cues) ---

# First N wire slots (Pin_A ..) that the story timeline can gate.
STORY_PIN_COUNT = 6
# Default story length: 14 minutes 30 seconds.
STORY_DURATION_SEC = 14 * 60 + 30
# Shortest clip that can be drawn on a lane.
STORY_MIN_CLIP_SEC = 0.25
# Waveform playback-speed envelope drawn on the Dust Devil timeline.
STORY_SPEED_MIN = 1.0
STORY_SPEED_MAX = 100.0
STORY_SPEED_DEFAULT = 1.0
