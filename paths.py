"""
paths.py — App-wide path constants.
Tất cả module khác import từ đây, không hardcode đường dẫn.
"""
import os
import sys


def _nuitka_exe() -> str:
    """Path of the compiled .exe under Nuitka, else ''.

    Nuitka does not set sys.frozen; it injects a __compiled__ object into every
    module. Two obvious ways to find the program are wrong in a standalone
    build, both checked against Nuitka's own source:
      - sys.executable is <dist>\\python.exe, named after the interpreter that
        ran the build. No such file is shipped.
      - __compiled__.containing_dir is the folder that holds the dist, one
        level above the exe: Nuitka strips a directory for standalone.
    __compiled__.process_exe is the real binary; a Nuitka without that field
    falls back to sys.argv[0]."""
    comp = globals().get("__compiled__")
    if comp is None:
        return ""
    return os.path.abspath(getattr(comp, "process_exe", None) or sys.argv[0])


def is_frozen() -> bool:
    """True in a packaged build -- PyInstaller (sys.frozen) or Nuitka (__compiled__)."""
    return bool(getattr(sys, "frozen", False)) or ("__compiled__" in globals())


def get_app_dir() -> str:
    """Folder holding the program: the repo root from source, the folder of the
    .exe when packaged. Shipped read-only files (DATABRAIN.md, the OCR model)
    are looked up here and under bundle_dir(); the user's config is in DATA_DIR."""
    if getattr(sys, "frozen", False):          # PyInstaller
        return os.path.dirname(sys.executable)
    exe = _nuitka_exe()                         # Nuitka standalone
    if exe:
        return os.path.dirname(exe)
    return os.path.dirname(os.path.abspath(__file__))


def bundle_dir() -> str:
    """Nơi một build đóng gói giữ các data file được gom vào, hoặc '' khi chạy từ
    source. PyInstaller giải nén chúng dưới _MEIPASS (thư mục _internal/); Nuitka
    đặt cạnh binary, tức trùng với APP_DIR."""
    mei = getattr(sys, "_MEIPASS", "")          # PyInstaller
    if mei:
        return mei
    if "__compiled__" in globals():             # Nuitka
        return get_app_dir()
    return ""


APP_DIR        = get_app_dir()


def _user_data_dir() -> str:
    """Writable folder for the user's config and generated files.

    The top of the release folder, beside the program rather than inside it, so
    an update that replaces the program keeps the config, and copying the
    folder carries both:
      - from source: the repo root (APP_DIR), so development is unchanged;
      - PyInstaller: beside the .exe (APP_DIR), which already sits above
        _internal\\;
      - Nuitka standalone: the .exe cannot leave the dist, so the dist is the
        release folder's _internal\\ and the config sits one level up -- the
        folder Nuitka itself calls __compiled__.containing_dir."""
    if "__compiled__" in globals() and not getattr(sys, "frozen", False):
        return os.path.dirname(APP_DIR) or APP_DIR
    return APP_DIR


DATA_DIR = _user_data_dir()
try:
    os.makedirs(DATA_DIR, exist_ok=True)
except OSError:
    DATA_DIR = APP_DIR                          # never crash on an odd path

# User config and generated output -- writable, kept in DATA_DIR so a packaged
# build's update (swapping the dist) does not wipe it. DATABRAIN.md and the OCR
# model stay under APP_DIR/bundle_dir(): they are read-only and shipped.
DATA_FILE      = os.path.join(DATA_DIR, "containers_data.json")
EXE_ADDON_FILE = os.path.join(DATA_DIR, "exe_addons.json")
SYNONYMS_FILE  = os.path.join(DATA_DIR, "synonyms.json")
IMAGE_DIR      = os.path.join(DATA_DIR, "images")
NOTES_FILE     = os.path.join(DATA_DIR, "Notes.xlsm")
STATS_FILE     = os.path.join(DATA_DIR, "file_stats.json")
SUMMARIES_FILE = os.path.join(DATA_DIR, "summaries.json")
NLM_SOURCE_MAP = os.path.join(DATA_DIR, "nlm_source_map.json")
CLAUDE_DB_FILE = os.path.join(DATA_DIR, "claude_db.json")
MINDMAP_DIR    = os.path.join(DATA_DIR, "mindmaps")
PARENTS_FILE   = os.path.join(DATA_DIR, "container_parents.json")
UI_STATE_FILE  = os.path.join(DATA_DIR, "ui_state.json")
SYNC_CONFIG_FILE      = os.path.join(DATA_DIR, "sync_config.json")
GSHEET_CONFIG_FILE    = os.path.join(DATA_DIR, "gsheet_config.json")
DB_LIST_FILE   = os.path.join(DATA_DIR, "db_list.json")


# ── Carry a user's existing config into DATA_DIR on first launch ──
# Config lives in DATA_DIR (beside the dist) so an update that only swaps the
# dist does not wipe it. On startup the app calls migrate_user_data(): each
# known file or folder found inside the dist beside the .exe (APP_DIR) but not
# yet in DATA_DIR is lifted out to DATA_DIR once -- never overwritten, so live
# config always wins. A no-op from source (DATA_DIR == APP_DIR), so a user who
# drops config inside the dist folder by habit has it carried out on first run.
_USER_DATA_NAMES = (
    "containers_data.json", "container_parents.json", "exe_addons.json",
    "synonyms.json", "file_stats.json", "summaries.json", "nlm_source_map.json",
    "claude_db.json", "db_list.json", "llm_config.json", "ui_state.json",
    "sync_config.json", "gsheet_config.json", "diagnosis_history.json",
    "Notes.xlsm", "images", "mindmaps", "reports", "claude_data",
)


def migrate_user_data() -> None:
    """Copy config left beside the .exe into DATA_DIR once (see note above)."""
    if DATA_DIR == APP_DIR:
        return
    import shutil
    for name in _USER_DATA_NAMES:
        src = os.path.join(APP_DIR, name)
        dst = os.path.join(DATA_DIR, name)
        if not os.path.exists(src) or os.path.exists(dst):
            continue
        try:
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
        except OSError:
            pass

# ── OCR recognition model for English text ────────────────────────
# RapidOCR ships only PaddleOCR's Chinese recogniser, which runs English words
# together ("checklistwillbefilledout"). en_PP-OCRv4 read 96% of the words of a
# test set against 81%. It is a 7.6 MB binary, so it is not in git: it lives in
# models/ocr/ beside the app (from source: the repo root), or inside a packaged
# build via --add-data. Source: modelscope.cn/models/RapidAI/RapidOCR,
# onnx/PP-OCRv4/rec/en_PP-OCRv4_rec_mobile.onnx.
OCR_REC_MODEL_NAME = "en_PP-OCRv4_rec_mobile.onnx"


def ocr_rec_model():
    """Path of the English OCR recognition model, or None when it is not installed."""
    places = [APP_DIR]
    bundled = bundle_dir()
    if bundled and bundled not in places:
        places.append(bundled)
    for base in places:
        path = os.path.join(base, "models", "ocr", OCR_REC_MODEL_NAME)
        if os.path.isfile(path):
            return path
    return None


# ── Helper CLI commands for the Data Brain agent ──────────────────
# The agent queries the databases by running db_query.py / logic_query.py
# through Bash. A packaged build has no python.exe beside it, so "python
# db_query.py" cannot work there; the exe dispatches both scripts itself (see
# Finding9.py). Prompts must take the command from here instead of spelling it
# out, so the source and packaged forms cannot drift apart.

def program_exe() -> str:
    """The running program: the packaged .exe when frozen, else the python
    interpreter. Not sys.executable alone, which Nuitka points at a
    <dist>\\python.exe that does not exist (see _nuitka_exe)."""
    return _nuitka_exe() or sys.executable


def db_query_cmd() -> str:
    """Command prefix that runs db_query.py -- frozen or from source."""
    if is_frozen():
        return f'"{program_exe()}" --db-query'
    return "python db_query.py"


def logic_query_cmd() -> str:
    """Command prefix that runs logic_query.py -- frozen or from source."""
    if is_frozen():
        return f'"{program_exe()}" --logic-query'
    return "python logic_query.py"
