# build_nuitka.ps1 — Nuitka standalone build of fildingx (tương đương PyInstaller --onedir).
#
# Usage:
#   build_nuitka.bat                                  # double-click: asks CPU or GPU, then the name
#   .\build_nuitka.ps1                                # CPU build; asks for the release name first
#   .\build_nuitka.ps1 -Gpu                           # GPU build (+2.4 GB nvidia cu12)
#   .\build_nuitka.ps1 -ReleaseName "Finding9.6.3"    # name given up front, no prompt
#
# The release name names the folder and both exes, and the version number in it
# (9.6.3) becomes their Windows file version. The output is laid out like a
# PyInstaller onedir build (see "release folder" at the end):
#   build_nuitka\Finding9.6.3\           (GPU: build_nuitka\gpu\Finding9.6.3\)
#       ├─ _internal\            the whole dist: exe + DLLs + data
#       │     └─ Finding9.6.3.exe
#       └─ Finding9.6.3.exe      ~70 KB launcher that starts _internal\Finding9.6.3.exe
# The build ships no config. Users copy their JSON files beside _internal (into
# <ReleaseName>\), or the app creates them there on first use: that folder is
# DATA_DIR (paths.py), so replacing _internal on an update keeps them.
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

param([switch]$Gpu, [string]$ReleaseName = "")

$ErrorActionPreference = 'Stop'
$outdir = if ($Gpu) { 'build_nuitka\gpu' } else { 'build_nuitka' }
$dist   = "$outdir\Finding9.dist"

# The release name -- asked for, or -ReleaseName -- names the release folder
# and both exes: build_nuitka\Finding9.6.3\Finding9.6.3.exe starts
# _internal\Finding9.6.3.exe. The version number in it (9.6.3) becomes the
# exes' Windows file and product version, so a new release needs no edit here,
# only its name. Enter takes "Finding$DefaultVersion", and a name with no
# version number in it gets $DefaultVersion as its version.
$DefaultVersion = '9.6.2'

# Settled before the build, which takes a long time, so nobody has to wait for
# the end to answer, and a name Windows refuses is caught before the time is
# spent. Asked again until it can be a file name.
$default = "Finding$DefaultVersion"
$ask = -not $ReleaseName
while ($true) {
    if ($ask) {
        try { $ans = Read-Host "Release name, also the exe name (Enter = '$default')" } catch { $ans = '' }
        $ReleaseName = if ($ans -and $ans.Trim()) { $ans } else { $default }
    }
    # ".exe" is added below; Windows drops trailing dots and spaces anyway.
    $ReleaseName = ($ReleaseName.Trim() -replace '\.exe$', '').TrimEnd('.', ' ')
    if ($ReleaseName -and $ReleaseName -notin '.', '..' -and
        $ReleaseName.IndexOfAny([IO.Path]::GetInvalidFileNameChars()) -lt 0) { break }
    Write-Host "'$ReleaseName' cannot be a file name: leave out \ / : * ? `" < > |"
    if (-not $ask) { exit 1 }
}
$ExeName = "$ReleaseName.exe"
# Windows keeps up to four numbers of at most 65535 in a version resource.
$ProductVersion = $DefaultVersion
if ($ReleaseName -match '\d+(\.\d+){1,3}') {
    if ($Matches[0].Split('.') | Where-Object { $_.Length -gt 5 -or [int]$_ -gt 65535 }) {
        Write-Host "Note: '$($Matches[0])' cannot be a Windows version number -- the exes get $DefaultVersion."
    } else {
        $ProductVersion = $Matches[0]
    }
}
$release = Join-Path $outdir $ReleaseName
if (Test-Path (Join-Path $release '_internal')) {
    Write-Host "Note: $release exists -- its _internal\ and launcher will be replaced, the config beside them kept."
}

$nuitkaArgs = @(
  '--standalone'
  '--enable-plugin=pyside6'
  '--windows-console-mode=disable'
  '--windows-icon-from-ico=icon.ico'
  "--output-filename=$ExeName"
  "--output-dir=$outdir"
  '--assume-yes-for-downloads'
  '--msvc=latest'
  '--low-memory'
  '--lto=no'
  '--no-deployment-flag=excluded-module-usage'
  '--company-name=fildingx'
  '--product-name=fildingx'
  "--product-version=$ProductVersion"
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

# Bản CPU: nhân CUDA + TensorRT của onnxruntime (~712 MB) vô dụng khi không có DLL
# CUDA runtime cạnh exe (onnxruntime tự fallback CPU), nên bị XÓA ở bước post-build
# phía dưới. KHÔNG dùng --noinclude-data-files: Nuitka gom các DLL này như binary
# phụ thuộc, cờ đó chỉ lọc data-file nên KHÔNG loại được chúng (đo thực tế: file
# 712 MB vẫn còn nguyên). Bản GPU GIỮ lại (bắt buộc để chạy GPU). CPU ~1.8 -> ~1.1 GB.

$nuitkaArgs += 'Finding9.py'

Write-Host "=== Nuitka build: variant=$(if ($Gpu) {'GPU'} else {'CPU'})  ->  $release\$ExeName  (version $ProductVersion) ==="
# Nuitka ghi tiến trình ra stderr; với ErrorActionPreference='Stop' (đầu file) +
# stream bị capture/redirect, PowerShell 5.1 biến mỗi dòng stderr thành lỗi kết
# thúc, build chết ngay khi Nuitka in dòng đầu. Tạm nới 'Continue' quanh lệnh
# build để CHỈ $LASTEXITCODE quyết định thành/bại.
$prevEAP = $ErrorActionPreference
$ErrorActionPreference = 'Continue'
python -m nuitka @nuitkaArgs
$rc = $LASTEXITCODE
$ErrorActionPreference = $prevEAP

# ── Copy PyMuPDF (pymupdf + fitz) vào dist sau khi build ────────────────────
# Phải chép sau nuitka vì --include-data-dir loại bỏ file code (.py/.pyd/.dll).
# Copy-Item chép đủ cả engine (_mupdf.pyd, mupdfcpp64.dll) lẫn wrapper (mupdf.py).
if ($rc -eq 0 -and (Test-Path "$dist\$ExeName")) {
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
    } else {
        # CPU: xóa nhân CUDA/TensorRT của onnxruntime (~712 MB) — bản CPU không nạp
        # chúng (không có DLL nvidia cạnh exe), onnxruntime chạy CPU. Phải xóa ở đây
        # vì --noinclude-data-files không loại được DLL phụ thuộc (xem ghi chú trên).
        Remove-Item "$dist\onnxruntime\capi\onnxruntime_providers_cuda.dll"     -Force -ErrorAction SilentlyContinue
        Remove-Item "$dist\onnxruntime\capi\onnxruntime_providers_tensorrt.dll" -Force -ErrorAction SilentlyContinue
        Write-Host "OK: removed CUDA/TensorRT providers (CPU build, ~712 MB freed)"
    }

    # ── Lay out the release folder (PyInstaller-onedir style) ──────────────────
    # Nuitka can't split the exe from its DLLs, so the whole dist becomes the
    # "_internal" content folder, nested in a version-named release folder with a
    # launcher of the same name beside it (below). Config the user drops into
    # the release folder sits beside _internal -- that is DATA_DIR (paths.py), so
    # replacing _internal on an update keeps the config. Rebuilding into the same
    # ReleaseName replaces _internal only; anything else in the folder is left alone.
    $content = Join-Path $release '_internal'
    New-Item -ItemType Directory -Force -Path $release | Out-Null   # keep config already here
    if (Test-Path $content) { Remove-Item -Recurse -Force $content }
    # robocopy /MOVE, not Move-Item: it copies each file then deletes the source,
    # retries a locked file (Defender scanning the fresh 185 MB exe can hold one),
    # and returns a real exit code (<8 = success). Move-Item renames the whole tree
    # in one step and, if that step is refused, can leave the dist neither here nor
    # there -- which is exactly how an earlier build's dist was lost. Verify the exe
    # landed before deleting the source shell; bail loudly if anything is off.
    $prevEAP2 = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    robocopy $dist $content /E /MOVE /NFL /NDL /NJH /NJS /R:3 /W:2 | Out-Null
    $rcmove = $LASTEXITCODE
    $ErrorActionPreference = $prevEAP2
    if ($rcmove -ge 8 -or -not (Test-Path (Join-Path $content $ExeName))) {
        Write-Host "ERROR: could not move dist into _internal (robocopy=$rcmove). Dist left at $dist."
        exit 1
    }
    Remove-Item $dist -Recurse -Force -ErrorAction SilentlyContinue   # now-empty source shell

    # The launcher. Nuitka cannot put its exe outside the folder of its DLLs
    # (there is no _internal option, Nuitka #3663), and a .lnk holds an absolute
    # path that breaks once the folder is copied elsewhere. So the top of the
    # release folder gets a ~70 KB GUI exe of the same name, compiled here by the
    # C# compiler of the .NET Framework that ships with Windows: it starts
    # _internal\<exe> with its own arguments and exits.
    $launcher = Join-Path $release $ExeName
    $csFile   = Join-Path $env:TEMP "fildingx_launcher_$PID.cs"
    @"
using System;
using System.Diagnostics;
using System.IO;
using System.Reflection;
using System.Windows.Forms;

[assembly: AssemblyTitle("Finding9")]
[assembly: AssemblyProduct("fildingx")]
[assembly: AssemblyCompany("fildingx")]
[assembly: AssemblyFileVersion("$ProductVersion")]

public static class Launcher {
    [STAThread]
    public static int Main() {
        string exe = Path.Combine(AppDomain.CurrentDomain.BaseDirectory, @"_internal\$ExeName");
        if (!File.Exists(exe)) {
            MessageBox.Show("Cannot find " + exe + "\n\nKeep the _internal folder beside this file.",
                            "Finding9", MessageBoxButtons.OK, MessageBoxIcon.Error);
            return 1;
        }
        ProcessStartInfo psi = new ProcessStartInfo(exe, RawArgs());
        psi.WorkingDirectory = Path.GetDirectoryName(exe);
        psi.UseShellExecute = false;
        Process.Start(psi);
        return 0;
    }

    // This launcher's command line without its own path, passed on verbatim.
    static string RawArgs() {
        string cl = Environment.CommandLine;
        int i;
        if (cl.StartsWith("\"")) { i = cl.IndexOf('"', 1); i = i < 0 ? cl.Length : i + 1; }
        else { i = cl.IndexOf(' '); if (i < 0) i = cl.Length; }
        return cl.Substring(i).TrimStart();
    }
}
"@ | Set-Content -Encoding UTF8 $csFile
    $csc = Join-Path ([Runtime.InteropServices.RuntimeEnvironment]::GetRuntimeDirectory()) 'csc.exe'
    $ico = (Resolve-Path 'icon.ico').Path
    $prevEAP3 = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    & $csc /nologo /target:winexe /optimize+ "/win32icon:$ico" "/out:$launcher" /r:System.Windows.Forms.dll $csFile | Out-Host
    $rccsc = $LASTEXITCODE
    $ErrorActionPreference = $prevEAP3
    Remove-Item $csFile -Force -ErrorAction SilentlyContinue
    if ($rccsc -ne 0 -or -not (Test-Path $launcher)) {
        Write-Host "ERROR: launcher compile failed (csc=$rccsc)."
        exit 1
    }
    Remove-Item (Join-Path $release 'Finding9.lnk') -Force -ErrorAction SilentlyContinue   # earlier builds made one
    Write-Host "OK: release laid out -> $release  ($ExeName + _internal\)"
} else {
    Write-Host "SKIP post-build copy: nuitka failed or exe missing (LASTEXITCODE=$rc)."
    exit $(if ($rc) { $rc } else { 1 })
}
# robocopy leaves exit code 1 behind on success ("files copied"); without this
# the script would report failure after a good build.
exit 0
