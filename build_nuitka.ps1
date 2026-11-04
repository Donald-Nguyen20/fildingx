# build_nuitka.ps1 — Nuitka standalone build of fildingx (tương đương PyInstaller --onedir).
#
# Dùng:
#   .\build_nuitka.ps1          # bản CPU  -> build_nuitka\Finding8.dist
#   .\build_nuitka.ps1 -Gpu     # bản GPU  -> build_nuitka\gpu\Finding8.dist  (+2.4 GB nvidia cu12)
#
# Cần: pip install nuitka + Visual Studio Build Tools (workload "Desktop
# development with C++"). Dùng --msvc=latest.
# Chạy từ thư mục gốc repo, trong cùng venv đang dùng để chạy app.
#
# PyMuPDF (pymupdf/fitz) KHÔNG biên dịch được bằng Nuitka: wrapper SWIG mupdf.py
# nở thành file C ~2,3 triệu dòng làm cả gcc lẫn cl.exe hết heap (fatal error
# C1002 "out of heap space in pass 2"). Đây là lỗi Nuitka đã biết, còn mở
# (Nuitka #3123/#3291/#3243, PyMuPDF #4126). Cách chữa: --nofollow-import-to để
# Nuitka bỏ qua, rồi copy nguyên gói pymupdf + fitz vào dist SAU khi build (khối
# Copy-Item cuối file) — Nuitka standalone thêm thư mục exe vào sys.path nên vẫn
# import được, và _mupdf.pyd/mupdfcpp64.dll vốn đã biên dịch sẵn nên không mất
# tính năng. Compile mupdf.py ra C cũng chẳng giúp chống sửa (chỉ là keo SWIG),
# code cần bảo vệ là của app. KHÔNG dùng --include-data-dir cho pymupdf/fitz:
# Nuitka loại bỏ file .py/.pyd/.dll khỏi data-dir nên chỉ copy được mỗi mupdf-devel.
# _mupdf.pyd cần python3.dll + MSVCP140/VCRUNTIME140* — Nuitka ĐÃ tự đóng sẵn các
# DLL này vào dist (qua pyside6/shiboken/onnxruntime), nên không cần thêm tay.
# Vì code app `import fitz` trực tiếp mà fitz bị --nofollow, Nuitka dựng "chốt"
# excluded-module-usage làm import fitz lỗi cứng lúc chạy; --no-deployment-flag=
# excluded-module-usage tắt chốt để import fitz rơi xuống gói loose cạnh exe.
# cryptography KHÔNG được exclude: pdfminer (trong pdfplumber) import nó ở
# top-level, exclude là pdfplumber không import nổi.

param([switch]$Gpu)

$ErrorActionPreference = 'Stop'
$outdir = if ($Gpu) { 'build_nuitka\gpu' } else { 'build_nuitka' }
$dist   = "$outdir\Finding8.dist"

$nuitkaArgs = @(
  '--standalone'
  '--enable-plugin=pyside6'
  '--windows-console-mode=disable'
  '--windows-icon-from-ico=icon.ico'
  '--output-filename=Finding9.6.2.exe'
  "--output-dir=$outdir"
  '--assume-yes-for-downloads'
  '--msvc=latest'
  '--low-memory'
  '--lto=no'
  '--no-deployment-flag=excluded-module-usage'
  '--company-name=fildingx'
  '--product-name=fildingx'
  '--product-version=9.6.2'
  "--include-data-dir=$env:LOCALAPPDATA\ms-playwright\chromium-1208=ms-playwright\chromium-1208"
  "--include-data-dir=$env:LOCALAPPDATA\ms-playwright\ffmpeg-1011=ms-playwright\ffmpeg-1011"
  "--include-data-dir=$env:LOCALAPPDATA\ms-playwright\winldd-1007=ms-playwright\winldd-1007"
  '--include-data-dir=models/ocr=models/ocr'
  '--include-data-files=DATABRAIN.md=DATABRAIN.md'
  '--include-data-files=ui/dcs_logic/*.json=ui/dcs_logic/'
  '--include-package=notebooklm';             '--include-package-data=notebooklm'
  '--include-package=playwright';             '--include-package-data=playwright'
  '--include-package=pdfplumber';             '--include-package-data=pdfplumber'
  '--include-package=fastembed';              '--include-package-data=fastembed'
  '--include-package=onnxruntime';            '--include-package-data=onnxruntime'
  '--include-package=rapidocr_onnxruntime';   '--include-package-data=rapidocr_onnxruntime'
  '--include-package=markdown_it';            '--include-package-data=markdown_it'
  '--include-package=pygments';               '--include-package-data=pygments'
  '--include-module=win32com.client'
  '--include-module=win32api'
  '--include-module=rapidfuzz'
  '--include-module=bs4'
  '--include-module=docx'
  '--include-module=pptx'
  '--include-module=openpyxl'
  '--include-module=requests'
  '--include-module=pytesseract'
  '--include-module=PIL'
  '--include-module=db_query'
  '--include-module=logic_query'
  # nofollow: pymupdf/fitz (xem đầu file), sympy (chỉ onnxruntime-gpu dùng, app không),
  # và các thư viện app không dùng để exe gọn.
  '--nofollow-import-to=sympy'
  '--nofollow-import-to=pymupdf'
  '--nofollow-import-to=fitz'
  '--nofollow-import-to=matplotlib'
  '--nofollow-import-to=pandas'
  '--nofollow-import-to=tkinter'
  '--nofollow-import-to=IPython'
  '--nofollow-import-to=jupyter'
  '--nofollow-import-to=notebook'
  '--nofollow-import-to=pytest'
  '--nofollow-import-to=flask'
  '--nofollow-import-to=django'
  '--nofollow-import-to=sqlalchemy'
  '--nofollow-import-to=tensorflow'
  '--nofollow-import-to=keras'
  '--nofollow-import-to=paramiko'
  '--nofollow-import-to=tornado'
  '--nofollow-import-to=lib2to3'
  '--nofollow-import-to=xmlrpc'
  '--nofollow-import-to=curses'
  '--nofollow-import-to=pydoc_data'
  '--nofollow-import-to=doctest'
  '--nofollow-import-to=pygame'
  '--nofollow-import-to=pyarrow'
  '--nofollow-import-to=plotly'
  '--nofollow-import-to=statsmodels'
  '--nofollow-import-to=lightgbm'
  '--nofollow-import-to=patsy'
  '--nofollow-import-to=uvicorn'
  '--nofollow-import-to=opentelemetry'
  '--nofollow-import-to=datasets'
  '--nofollow-import-to=mako'
  '--nofollow-import-to=narwhals'
  '--nofollow-import-to=torch'
  '--nofollow-import-to=faiss'
  '--nofollow-import-to=sentence_transformers'
  '--nofollow-import-to=scipy'
  '--nofollow-import-to=sklearn'
  '--nofollow-import-to=PySide6.QtQuick'
  '--nofollow-import-to=PySide6.QtQml'
  '--nofollow-import-to=PySide6.QtQuickWidgets'
  '--nofollow-import-to=PySide6.QtPositioning'
  '--nofollow-import-to=PySide6.Qt3DCore'
  '--nofollow-import-to=PySide6.Qt3DRender'
  '--nofollow-import-to=PySide6.QtMultimedia'
  '--nofollow-import-to=PySide6.QtMultimediaWidgets'
  '--nofollow-import-to=PySide6.QtCharts'
  '--nofollow-import-to=PySide6.QtDataVisualization'
  '--nofollow-import-to=PySide6.QtBluetooth'
  '--nofollow-import-to=PySide6.QtNfc'
  '--nofollow-import-to=PySide6.QtSensors'
  '--nofollow-import-to=PySide6.QtLocation'
  '--nofollow-import-to=PySide6.QtRemoteObjects'
  '--nofollow-import-to=PySide6.QtScxml'
)

# Bản CPU: bỏ nhân CUDA + TensorRT của onnxruntime (~711 MB) — vô dụng khi không
# có DLL CUDA runtime cạnh exe; onnxruntime tự fallback CPU. Dist CPU ~1.8 -> ~1.1 GB.
# Bản GPU GIỮ lại (bắt buộc để chạy GPU).
if (-not $Gpu) {
    $nuitkaArgs += '--noinclude-data-files=*onnxruntime_providers_cuda.dll'
    $nuitkaArgs += '--noinclude-data-files=*onnxruntime_providers_tensorrt.dll'
}

$nuitkaArgs += 'Finding8.py'

Write-Host "=== Nuitka build: variant=$(if ($Gpu) {'GPU'} else {'CPU'})  ->  $dist ==="
python -m nuitka @nuitkaArgs
$rc = $LASTEXITCODE

# ── Copy PyMuPDF (pymupdf + fitz) vào dist sau khi build ────────────────────
# Phải chép sau nuitka vì --include-data-dir loại bỏ file code (.py/.pyd/.dll).
# Copy-Item chép đủ cả engine (_mupdf.pyd, mupdfcpp64.dll) lẫn wrapper (mupdf.py).
if ($rc -eq 0 -and (Test-Path "$dist\Finding9.6.2.exe")) {
    Copy-Item 'venv\Lib\site-packages\pymupdf' "$dist\" -Recurse -Force
    Copy-Item 'venv\Lib\site-packages\fitz'    "$dist\" -Recurse -Force
    Write-Host "OK: copied pymupdf + fitz into $dist"
    # GPU: copy DLL CUDA (cublas/cudnn/cudart...) của wheel nvidia-*-cu12 cạnh exe,
    # giống --collect-binaries nvidia của PyInstaller. PHẢI dùng Copy-Item chứ
    # KHÔNG --include-data-dir: Nuitka strip hết file .dll khỏi data-dir (chỉ còn
    # header ~14 MB, bản GPU hoá vô dụng). core/cuda_setup.py tự thêm nvidia/*/bin
    # vào PATH lúc chạy. ~2.4 GB -> dist GPU ~4.2 GB.
    if ($Gpu) {
        Copy-Item 'venv\Lib\site-packages\nvidia' "$dist\" -Recurse -Force
        Write-Host "OK: copied nvidia CUDA DLLs into $dist"
    }
} else {
    Write-Host "SKIP post-build copy: nuitka failed or exe missing (LASTEXITCODE=$rc)."
}
