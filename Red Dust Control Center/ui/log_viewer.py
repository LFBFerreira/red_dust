"""
Log Viewer widget for displaying system logs.
"""
from PySide6.QtWidgets import QTextEdit
from PySide6.QtCore import Qt
from PySide6.QtGui import QTextCharFormat, QColor
import logging
from datetime import datetime


class LogViewer(QTextEdit):
    """Widget for displaying formatted log messages."""
    
    def __init__(self, parent=None):
        """Initialize LogViewer."""
        super().__init__(parent)
        self.setReadOnly(True)
        self.setFontFamily("Courier")
        self.setFontPointSize(9)
        
        # Color formats for different log levels
        self._formats = {
            'INFO': QTextCharFormat(),
            'WARNING': QTextCharFormat(),
            'ERROR': QTextCharFormat()
        }
        
        # Set colors
        self._formats['WARNING'].setForeground(QColor(255, 140, 0))  # Orange
        self._formats['ERROR'].setForeground(QColor(255, 0, 0))  # Red
    
    def append_log(self, level: str, message: str) -> None:
        """
        Append a log message.
        
        Args:
            level: Log level ("INFO", "WARNING", "ERROR")
            message: Log message
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{level}] {timestamp} - {message}"
        
        # Get format for level (default to INFO format)
        fmt = self._formats.get(level, self._formats['INFO'])
        
        # Insert formatted text
        cursor = self.textCursor()
        cursor.movePosition(cursor.MoveOperation.End)
        cursor.setCharFormat(fmt)
        cursor.insertText(formatted_message + "\n")
        
        # Auto-scroll to bottom
        self.verticalScrollBar().setValue(self.verticalScrollBar().maximum())
    
    def clear_logs(self) -> None:
        """Clear all log messages."""
        self.clear()


class LogHandler(logging.Handler):
    """Custom logging handler that emits to LogViewer."""
    
    def __init__(self, log_viewer: LogViewer):
        """
        Initialize LogHandler.
        
        Args:
            log_viewer: LogViewer widget to send messages to
        """
        super().__init__()
        self._log_viewer = log_viewer
    
    def emit(self, record):
        """Emit log record to LogViewer."""
        try:
            level = record.levelname
            message = self.format(record)
            self._log_viewer.append_log(level, message)
        except Exception:
            pass  # Ignore errors in logging

