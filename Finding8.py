r"""
Finding8.py — Entry point.

Build:


  
pyinstaller --noconfirm --clean --onedir --windowed --name "Finding9.6.2" "Finding8.py" --icon "icon.ico" `
  --add-data "$env:LOCALAPPDATA\ms-playwright\chromium-1208;ms-playwright\chromium-1208" `
  --add-data "$env:LOCALAPPDATA\ms-playwright\ffmpeg-1011;ms-playwright\ffmpeg-1011" `
  --add-data "$env:LOCALAPPDATA\ms-playwright\winldd-1007;ms-playwright\winldd-1007" `
  --collect-all notebooklm --collect-all playwright `
  --collect-all pdfplumber `
  --collect-all fastembed --collect-all onnxruntime --collect-all rapidocr_onnxruntime `
  --add-data "models/ocr;models/ocr" `
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

Semantic search and PaddleOCR (GPU): the three --collect-all above bundle
fastembed-gpu, onnxruntime-gpu and rapidocr-onnxruntime (its ONNX models).
With only those, both features run on the CPU in the frozen build. For GPU
acceleration the nvidia-*-cu12 CUDA runtime DLLs (cublas, cudnn, cuda_runtime,
cufft, curand, cuda_nvrtc, nvjitlink -- ~2 GB) must also be collected, e.g.
--collect-binaries nvidia; core/cuda_setup.py already adds a frozen build's
nvidia/*/bin dirs (under _MEIPASS) to PATH at startup, so once those DLLs are
present the GPU is used with no further wiring. Shipping them is optional:
leave them out for a smaller CPU-only build.

models/ocr/en_PP-OCRv4_rec_mobile.onnx is PaddleOCR's English recogniser, used
in place of RapidOCR's Chinese one (which runs English words together). It is
gitignored, so a fresh clone must fetch it first -- see paths.ocr_rec_model.
Without it OCR still works, on the Chinese recogniser, and Create DB says so.


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

# ── CUDA DLL path for onnxruntime-gpu (semantic search + PaddleOCR) ───
# onnxruntime's CUDA provider loads cublas/cudnn/cudart at session time through
# the native loader, which only finds them on PATH -- os.add_dll_directory is not
# enough for those transitive deps. Done here, before anything imports onnxruntime,
# so the first session (OCR or embedding) can reach the GPU. No-op on a machine
# without the CUDA wheels; the CLI helpers above exit first and never pay for it.
from core import cuda_setup
cuda_setup.setup()

from PySide6.QtWidgets import QApplication
from ui.main_window import FileSearchApp

if __name__ == "__main__":
    # Ctrl+C in the terminal that started the app -- pressed to copy, with
    # nothing selected -- landed as a KeyboardInterrupt in whichever Qt slot ran
    # next (the Data Brain orb, 60 times a second), and under the debugger that
    # paused the whole app, a build of several hours included. Close the window
    # to quit; the debugger's Stop does not go through SIGINT.
    import signal
    signal.signal(signal.SIGINT, signal.SIG_IGN)

    app = QApplication(sys.argv)
    app.setStyleSheet(
        "QToolTip { background-color: #1e1a2e; color: #e0aaff; "
        "border: 1px solid #b967ff; padding: 6px; font-size: 12px; }"
    )
    window = FileSearchApp()
    window.showMaximized()
    sys.exit(app.exec())
 