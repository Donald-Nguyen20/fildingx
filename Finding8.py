r"""
Finding8.py — Entry point.

Build:
    pyinstaller --noconfirm --clean --onedir --windowed --name "Finding8.1.5" "Finding8.py" --icon "icon.ico" `
  --add-data "$env:LOCALAPPDATA\ms-playwright\chromium-1208;ms-playwright\chromium-1208" `
  --add-data "$env:LOCALAPPDATA\ms-playwright\ffmpeg-1011;ms-playwright\ffmpeg-1011" `
  --add-data "$env:LOCALAPPDATA\ms-playwright\winldd-1007;ms-playwright\winldd-1007" `
  --collect-all notebooklm --collect-all playwright `
  --exclude-module matplotlib --exclude-module pandas --exclude-module tkinter `
  --exclude-module IPython --exclude-module jupyter --exclude-module notebook `
  --exclude-module pytest --exclude-module flask `
  --exclude-module django --exclude-module sqlalchemy --exclude-module tensorflow `
  --exclude-module keras --exclude-module cryptography --exclude-module paramiko `
  --exclude-module tornado --exclude-module lib2to3 --exclude-module xmlrpc `
  --exclude-module curses --exclude-module pydoc_data --exclude-module doctest `
  --exclude-module pygame --exclude-module pyarrow --exclude-module plotly `
  --exclude-module statsmodels --exclude-module lightgbm --exclude-module patsy `
  --exclude-module uvicorn --exclude-module opentelemetry --exclude-module datasets `
  --exclude-module mako --exclude-module narwhals --exclude-module torch `
  --exclude-module faiss --exclude-module sentence_transformers `
  --exclude-module scipy --exclude-module sklearn `
  --exclude-module PySide6.QtQuick --exclude-module PySide6.QtQml `
  --exclude-module PySide6.QtQuickWidgets --exclude-module PySide6.QtPositioning `
  --exclude-module PySide6.Qt3DCore --exclude-module PySide6.Qt3DRender `
  --exclude-module PySide6.QtMultimedia --exclude-module PySide6.QtMultimediaWidgets `
  --exclude-module PySide6.QtCharts --exclude-module PySide6.QtDataVisualization `
  --exclude-module PySide6.QtBluetooth --exclude-module PySide6.QtNfc `
  --exclude-module PySide6.QtSensors --exclude-module PySide6.QtLocation `
  --exclude-module PySide6.QtRemoteObjects --exclude-module PySide6.QtScxml `
  --collect-all markdown_it --collect-all pygments `
  --hidden-import=win32com.client --hidden-import=win32api `
  --hidden-import=rapidfuzz --hidden-import=bs4 `
  --hidden-import=docx --hidden-import=pptx --hidden-import=fitz

"""
"""""
cd "d:\3. Coding\Tim file\fildingx"

.\venv\Scripts\python.exe -m PyInstaller `
  --noconfirm --clean --onedir --windowed `
  "Finding8.py" --icon "icon.ico" `
  --add-data "$env:LOCALAPPDATA\ms-playwright\chromium-1208;ms-playwright\chromium-1208" `
  --add-data "$env:LOCALAPPDATA\ms-playwright\ffmpeg-1011;ms-playwright\ffmpeg-1011" `
  --add-data "$env:LOCALAPPDATA\ms-playwright\winldd-1007;ms-playwright\winldd-1007" `
  --collect-all notebooklm --collect-all playwright `
  --collect-all markdown_it --collect-all pygments `
  --hidden-import=win32com.client --hidden-import=win32api `
  --hidden-import=rapidfuzz --hidden-import=bs4 `
  --hidden-import=docx --hidden-import=pptx --hidden-import=fitz `
  --exclude-module matplotlib --exclude-module pandas --exclude-module tkinter `
  --exclude-module IPython --exclude-module jupyter --exclude-module torch `
  --exclude-module faiss --exclude-module sentence_transformers `
  --exclude-module scipy --exclude-module sklearn `
  --exclude-module PySide6.QtQuick --exclude-module PySide6.QtQml `
  --exclude-module PySide6.Qt3DCore --exclude-module PySide6.Qt3DRender `
  --exclude-module PySide6.QtMultimedia --exclude-module PySide6.QtCharts
"""""


import os
import sys

# ── Playwright browser path khi chạy từ exe đã đóng gói ──────────
if getattr(sys, "frozen", False):
    _internal = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    _browsers = os.path.join(_internal, "ms-playwright")
    if os.path.isdir(_browsers):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = _browsers

from PySide6.QtWidgets import QApplication
from ui.main_window import FileSearchApp

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = FileSearchApp()
    window.showMaximized()
    sys.exit(app.exec())
 