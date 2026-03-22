"""
Finding7.1.py — Entry point.

Build:
    pyinstaller --noconfirm --clean --onefile --windowed "Finding7.1.py" --icon "icon.ico"
"""
import sys
from PySide6.QtWidgets import QApplication
from ui.main_window import FileSearchApp

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FileSearchApp()
    window.showMaximized()
    sys.exit(app.exec())
