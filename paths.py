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
CLAUDE_DB_FILE = os.path.join(APP_DIR, "claude_db.json")
MINDMAP_DIR    = os.path.join(APP_DIR, "mindmaps")
PARENTS_FILE   = os.path.join(APP_DIR, "container_parents.json")
UI_STATE_FILE  = os.path.join(APP_DIR, "ui_state.json")
SYNC_CONFIG_FILE      = os.path.join(APP_DIR, "sync_config.json")
GSHEET_CONFIG_FILE    = os.path.join(APP_DIR, "gsheet_config.json")


# ── Helper CLI commands for the Data Brain agent ──────────────────
# The agent queries the databases by running db_query.py / logic_query.py
# through Bash. A packaged build has no python.exe beside it, so "python
# db_query.py" cannot work there; the exe dispatches both scripts itself (see
# Finding8.py). Prompts must take the command from here instead of spelling it
# out, so the source and packaged forms cannot drift apart.

def db_query_cmd() -> str:
    """Command prefix that runs db_query.py -- frozen or from source."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --db-query'
    return "python db_query.py"


def logic_query_cmd() -> str:
    """Command prefix that runs logic_query.py -- frozen or from source."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --logic-query'
    return "python logic_query.py"
