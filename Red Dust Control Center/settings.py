"""
Configuration settings for Red Dust Control Center.

This module contains default values and configuration constants used throughout
the application. These can be modified to change default behavior.
"""

# --- Data defaults (PDS / archive selection) ---

DEFAULT_STATION = "ELYSE"
DEFAULT_YEAR = 2019
DEFAULT_DAY_OF_YEAR = 96

# Network code (typically "XB" for InSight SEIS)
DEFAULT_NETWORK = "XB"

# Available stations from InSight SEIS
AVAILABLE_STATIONS = ["ELYSE", "ELYS0", "ELYHK", "ELYH0"]


# --- Playback & channel selection ---

# Max simultaneous waveform channel selections (must be <= len(CHANNEL_TRACE_COLORS)
# in ui/widgets/channel_colors.py; extra palette colors are unused until you raise this).
MAX_SELECTED_CHANNELS = 5


# --- UI: main window layout ---

LEFT_PANEL_WIDTH = 250  # Dataset Information and Data Picker panels (pixels)
WAVEFORM_VIEWER_DEFAULT_WIDTH = 300  # Default waveform viewer width (pixels)
# Cap points sent to pyqtgraph per channel (display only; stream / cache stay full rate).
MAX_WAVEFORM_PLOT_POINTS_PER_CHANNEL = 8000

# Application color scheme: "system" (follow OS / Qt), "light", or "dark".
# Forced light/dark uses the Fusion style on most platforms for consistent results.
APP_COLOR_SCHEME = "system"


# --- UI: interactive object cards ---

INTERACTIVE_OBJECTS_HEIGHT = 300  # Tab panel height for interactive objects (pixels)
TAB_ICON_SIZE = 20  # Streaming status icon in object tabs (pixels)
OBJECT_CARD_LEFT_PANEL_MAX_WIDTH = 300  # OSC/Serial name & connection column (pixels)
OSC_OBJECT_ENDPOINT_DEBOUNCE_MS = 500  # Apply OSC host/address after typing pauses (avoids DNS per key)

# --- Multi-pin streaming (firmware / protocol contract) ---

MAX_PIN_SLOTS = 5
# Wire order: index 0 = first float in OSC/Serial frame (Pin_A), etc.
PIN_SLOT_LABELS = ("Pin_A", "Pin_B", "Pin_C", "Pin_D", "Pin_E")
# Slots with no mapped channel send this float; firmware treats values outside [0, 1] as inactive.
WIRE_INACTIVE_PIN_SENTINEL = -1.0


# --- OSC streaming ---

STREAMING_PORT = 8000  # Default UDP port (can be overridden per object)
OSC_OUTPUT_RATE = 60  # Transmission rate (Hz)
OSC_OUTPUT_INTERVAL_MS = 1000 // OSC_OUTPUT_RATE  # ~16.67 ms


# --- Serial communication ---

SERIAL_BAUDRATE = 115200  # Default baudrate (can be overridden per object)
SERIAL_OUTPUT_RATE = 60  # Transmission rate (Hz)
SERIAL_OUTPUT_INTERVAL_MS = 1000 // SERIAL_OUTPUT_RATE  # ~16.67 ms


# --- Application persistence (QSettings) ---

QSETTINGS_ORGANIZATION = "Red Dust"
QSETTINGS_APPLICATION = "RDCC"
