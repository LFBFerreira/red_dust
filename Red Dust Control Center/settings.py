"""
Configuration settings for Red Dust Control Center.

This module contains default values and configuration constants used throughout
the application. These can be modified to change default behavior.
"""

# Default data selection values
DEFAULT_STATION = "ELYHK"
DEFAULT_YEAR = 2018
DEFAULT_DAY_OF_YEAR = 355  # December 21, 2018

# Network code (typically "XB" for InSight SEIS)
DEFAULT_NETWORK = "XB"

# Available stations from InSight SEIS
AVAILABLE_STATIONS = ["ELYSE", "ELYS0", "ELYHK", "ELYH0"]
