"""
Red Dust Control Center - Main Entry Point
"""
import sys
import logging
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow

# Configure logging before importing modules
logging.basicConfig(
    level=logging.DEBUG,  # Temporarily set to DEBUG to see HTML samples
    format='[%(levelname)s] %(message)s'
)

def main():
    """Main application entry point."""
    app = QApplication(sys.argv)
    app.setApplicationName("Red Dust Control Center")
    
    window = MainWindow()
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

