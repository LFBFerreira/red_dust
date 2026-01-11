"""
Configuration settings for Red Dust Control Center.

This module contains default values and configuration constants used throughout
the application. These can be modified to change default behavior.
"""

# Default data selection values
DEFAULT_STATION = "ELYSE"
DEFAULT_YEAR = 2018
DEFAULT_DAY_OF_YEAR = 354 

# Network code (typically "XB" for InSight SEIS)
DEFAULT_NETWORK = "XB"

# Available stations from InSight SEIS
AVAILABLE_STATIONS = ["ELYSE", "ELYS0", "ELYHK", "ELYH0"]

# UI Layout settings
LEFT_PANEL_WIDTH = 250  # Width for Dataset Information and Data Picker panels (in pixels)

WAVEFORM_VIEWER_DEFAULT_WIDTH = 300  # Default width for Waveform Viewer (in pixels)

# Interactive Objects settings
INTERACTIVE_OBJECTS_HEIGHT = 280  # Fixed height for Interactive Objects container (in pixels)

OBJECT_CARD_WIDTH = 250  # Fixed width for individual object cards (in pixels)

# OSC Streaming settings
STREAMING_PORT = 8000  # Default UDP port for OSC streaming (can be overridden per object)

# Waveform Viewer settings
WAVEFORM_INACTIVE_CHANNEL_MAX_POINTS = 10000  # Maximum number of data points for inactive channels (active channel uses full resolution)
WAVEFORM_SHOW_ONLY_ACTIVE_CHANNEL = True  # If True, only display the active channel (hide inactive channels)