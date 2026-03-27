"""
Finding8.py — Entry point.

Build:
    pyinstaller --noconfirm --clean --onedir --windowed "Finding8.py" --icon "icon.ico" ^
      --add-data "%LOCALAPPDATA%\ms-playwright;ms-playwright" ^
      --collect-all notebooklm --collect-all playwright ^
      --exclude-module matplotlib --exclude-module pandas --exclude-module tkinter ^
      --exclude-module IPython --exclude-module jupyter --exclude-module notebook ^
      --exclude-module pytest --exclude-module cv2 --exclude-module flask ^
      --exclude-module django --exclude-module sqlalchemy --exclude-module tensorflow ^
      --exclude-module keras --exclude-module cryptography --exclude-module paramiko ^
      --exclude-module tornado --exclude-module lib2to3 --exclude-module xmlrpc ^
      --exclude-module curses --exclude-module pydoc_data --exclude-module doctest ^
      --exclude-module pygame --exclude-module pyarrow --exclude-module plotly ^
      --exclude-module statsmodels --exclude-module lightgbm --exclude-module patsy ^
      --exclude-module uvicorn --exclude-module opentelemetry --exclude-module datasets ^
      --exclude-module mako --exclude-module narwhals --exclude-module torch ^
      --exclude-module faiss --exclude-module sentence_transformers ^
      --exclude-module numpy --exclude-module scipy --exclude-module sklearn ^
      --hidden-import=win32com.client --hidden-import=win32api ^
      --hidden-import=rapidfuzz --hidden-import=bs4 ^
      --hidden-import=docx --hidden-import=pptx --hidden-import=fitz
"""
import os
import sys

# ── Playwright browser path khi chạy từ exe đã đóng gói ──────────
if getattr(sys, "frozen", False):
    _exe_dir = os.path.dirname(sys.executable)
    _browsers = os.path.join(_exe_dir, "ms-playwright")
    if os.path.isdir(_browsers):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = _browsers

from PySide6.QtWidgets import QApplication
from ui.main_window import FileSearchApp

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FileSearchApp()
    window.showMaximized()
    sys.exit(app.exec())
