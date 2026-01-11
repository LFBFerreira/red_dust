"""
Red Dust Control Center - Main Entry Point
"""
import sys
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow

# Note: Logging is configured in MainWindow._setup_logging()
# to avoid duplicate handlers

def main():
    """Main application entry point."""
    app = QApplication(sys.argv)
    app.setApplicationName("Red Dust Control Center")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

