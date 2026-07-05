"""
Red Dust Control Center - Main Entry Point
"""
import sys

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow
from ui.theme import apply_app_color_scheme, finish_startup_theme

# Note: Logging is configured in MainWindow._setup_logging()
# to avoid duplicate handlers

def main():
    """Main application entry point."""
    app = QApplication(sys.argv)
    app.setApplicationName("Red Dust Control Center")
    apply_app_color_scheme(app)

    window = MainWindow()
    window.show()
    QTimer.singleShot(0, lambda: finish_startup_theme(app))

    sys.exit(app.exec())

if __name__ == "__main__":
    main()

