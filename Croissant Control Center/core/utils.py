"""
Utility functions for Red Dust Control Center.

This module contains helper functions used throughout the application.
"""
from datetime import date, timedelta
from settings import DEFAULT_YEAR, DEFAULT_DAY_OF_YEAR


def get_default_date() -> date:
    """
    Get the default date as a Python date object.
    
    Returns:
        date object for the default year and day of year
    """
    return date(DEFAULT_YEAR, 1, 1) + timedelta(days=DEFAULT_DAY_OF_YEAR - 1)
