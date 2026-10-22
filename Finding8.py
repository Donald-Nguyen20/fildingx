r"""
Finding8.py — Entry point.

Build:


  
pyinstaller --noconfirm --clean --onedir --windowed --name "Finding9.6.2" "Finding8.py" --icon "icon.ico" `
  --add-data "$env:LOCALAPPDATA\ms-playwright\chromium-1208;ms-playwright\chromium-1208" `
  --add-data "$env:LOCALAPPDATA\ms-playwright\ffmpeg-1011;ms-playwright\ffmpeg-1011" `
  --add-data "$env:LOCALAPPDATA\ms-playwright\winldd-1007;ms-playwright\winldd-1007" `
  --collect-all notebooklm --collect-all playwright `
  --collect-all pdfplumber `
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
  --hidden-import=docx --hidden-import=pptx --hidden-import=fitz `
  --hidden-import=openpyxl --hidden-import=requests `
  --hidden-import=pytesseract --hidden-import=PIL `
  --add-data "DATABRAIN.md;." `
  --add-data "ui/dcs_logic/*.json;ui/dcs_logic"

After the build, copy DATABRAIN.md beside the .exe as well: the --add-data copy
above is only a fallback inside the bundle, and the one outside can be edited
without rebuilding. db_query.py and logic_query.py no longer need copying --
the exe runs them itself through --db-query / --logic-query.

Create DB (the Tools panel) runs core/create_index_v3.py, which OCRs
scanned PDFs through pytesseract. pytesseract is only a wrapper: it calls
tesseract.exe, which cannot be bundled and has to be installed on the
machine and be on PATH. Without it the indexer still works, but every
scanned document comes out as "[OCR Error: ...]".


"""


import os
import sys

# ── Playwright browser path khi chạy từ exe đã đóng gói ──────────
if getattr(sys, "frozen", False):
    _internal = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    _browsers = os.path.join(_internal, "ms-playwright")
    if os.path.isdir(_browsers):
        os.environ["PLAYWRIGHT_BROWSERS_PATH"] = _browsers

# ── Helper CLI mode: the exe is its own interpreter ───────────────
# The Data Brain agent reads the databases by running db_query.py and
# logic_query.py through Bash. A packaged build has no python.exe beside it,
# so the agent calls this exe with --db-query / --logic-query instead and the
# arguments go straight to the matching script. The two imports are spelt out
# rather than resolved through importlib because that is also what makes
# PyInstaller bundle the modules. Placed above the PySide6 import so a query
# never loads Qt, and sys.argv is rewritten rather than the scripts changed,
# so both still run on their own from source.
_HELPER_FLAGS = {"--db-query": "db_query.py", "--logic-query": "logic_query.py"}

if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] in _HELPER_FLAGS:
    _helper_name = _HELPER_FLAGS[sys.argv[1]]
    if sys.argv[1] == "--db-query":
        import db_query as _helper
    else:
        import logic_query as _helper
    sys.argv = [_helper_name, *sys.argv[2:]]   # both helpers read sys.argv directly
    _helper.main()
    sys.exit(0)

from PySide6.QtWidgets import QApplication
from ui.main_window import FileSearchApp

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyleSheet(
        "QToolTip { background-color: #1e1a2e; color: #e0aaff; "
        "border: 1px solid #b967ff; padding: 6px; font-size: 12px; }"
    )
    window = FileSearchApp()
    window.showMaximized()
    sys.exit(app.exec())
 