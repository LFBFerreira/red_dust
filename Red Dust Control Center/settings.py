"""
Configuration settings for Red Dust Control Center.

This module contains default values and configuration constants used throughout
the application. These can be modified to change default behavior.
"""

# Default data selection values
DEFAULT_STATION = "ELYHK"
DEFAULT_YEAR = 2018
DEFAULT_DAY_OF_YEAR = 360  # December 26, 2018

# Network code (typically "XB" for InSight SEIS)
DEFAULT_NETWORK = "XB"

# Available stations from InSight SEIS
AVAILABLE_STATIONS = ["ELYSE", "ELYS0", "ELYHK", "ELYH0"]

# UI Layout settings
LEFT_PANEL_WIDTH = 300  # Width for Dataset Information and Data Picker panels (in pixels)