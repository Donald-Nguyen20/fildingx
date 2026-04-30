"""
paths.py — App-wide path constants.
Tất cả module khác import từ đây, không hardcode đường dẫn.
"""
import os
import sys


def get_app_dir() -> str:
    """Trả về thư mục gốc của app (cạnh Finding7.1.py hoặc .exe)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


APP_DIR        = get_app_dir()
DATA_FILE      = os.path.join(APP_DIR, "containers_data.json")
EXE_ADDON_FILE = os.path.join(APP_DIR, "exe_addons.json")
SYNONYMS_FILE  = os.path.join(APP_DIR, "synonyms.json")
IMAGE_DIR      = os.path.join(APP_DIR, "images")
NOTES_FILE     = os.path.join(APP_DIR, "Notes.xlsm")
STATS_FILE     = os.path.join(APP_DIR, "file_stats.json")
SUMMARIES_FILE = os.path.join(APP_DIR, "summaries.json")
NLM_SOURCE_MAP = os.path.join(APP_DIR, "nlm_source_map.json")
MINDMAP_DIR    = os.path.join(APP_DIR, "mindmaps")
PARENTS_FILE   = os.path.join(APP_DIR, "container_parents.json")
UI_STATE_FILE  = os.path.join(APP_DIR, "ui_state.json")
