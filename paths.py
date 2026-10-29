"""
paths.py — App-wide path constants.
Tất cả module khác import từ đây, không hardcode đường dẫn.
"""
import os
import sys


def _nuitka_dir() -> str:
    """Folder holding the compiled binary under Nuitka, else ''.

    Nuitka does not set sys.frozen; it injects a __compiled__ object into every
    module. Its containing_dir is the folder beside the binary -- where both the
    files left next to the exe and the --include-data files live. Older Nuitka
    builds without that attribute fall back to sys.argv[0]'s folder."""
    comp = globals().get("__compiled__")
    if comp is None:
        return ""
    cdir = getattr(comp, "containing_dir", "")
    return cdir or os.path.dirname(os.path.abspath(sys.argv[0]))


def is_frozen() -> bool:
    """True in a packaged build -- PyInstaller (sys.frozen) or Nuitka (__compiled__)."""
    return bool(getattr(sys, "frozen", False)) or ("__compiled__" in globals())


def get_app_dir() -> str:
    """Thư mục gốc của app: cạnh Finding8.py khi chạy từ source, cạnh .exe khi
    đã đóng gói. File app đọc/ghi nằm ở đây và sửa được mà không cần build lại."""
    if getattr(sys, "frozen", False):          # PyInstaller
        return os.path.dirname(sys.executable)
    nk = _nuitka_dir()                          # Nuitka standalone/onefile
    if nk:
        return nk
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
DATA_FILE      = os.path.join(APP_DIR, "containers_data.json")
EXE_ADDON_FILE = os.path.join(APP_DIR, "exe_addons.json")
SYNONYMS_FILE  = os.path.join(APP_DIR, "synonyms.json")
IMAGE_DIR      = os.path.join(APP_DIR, "images")
NOTES_FILE     = os.path.join(APP_DIR, "Notes.xlsm")
STATS_FILE     = os.path.join(APP_DIR, "file_stats.json")
SUMMARIES_FILE = os.path.join(APP_DIR, "summaries.json")
NLM_SOURCE_MAP = os.path.join(APP_DIR, "nlm_source_map.json")
CLAUDE_DB_FILE = os.path.join(APP_DIR, "claude_db.json")
MINDMAP_DIR    = os.path.join(APP_DIR, "mindmaps")
PARENTS_FILE   = os.path.join(APP_DIR, "container_parents.json")
UI_STATE_FILE  = os.path.join(APP_DIR, "ui_state.json")
SYNC_CONFIG_FILE      = os.path.join(APP_DIR, "sync_config.json")
GSHEET_CONFIG_FILE    = os.path.join(APP_DIR, "gsheet_config.json")

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
# Finding8.py). Prompts must take the command from here instead of spelling it
# out, so the source and packaged forms cannot drift apart.

def db_query_cmd() -> str:
    """Command prefix that runs db_query.py -- frozen or from source."""
    if is_frozen():
        return f'"{sys.executable}" --db-query'
    return "python db_query.py"


def logic_query_cmd() -> str:
    """Command prefix that runs logic_query.py -- frozen or from source."""
    if is_frozen():
        return f'"{sys.executable}" --logic-query'
    return "python logic_query.py"
