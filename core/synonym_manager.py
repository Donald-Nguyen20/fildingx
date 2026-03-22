"""
core/synonym_manager.py — Load/save từ đồng nghĩa (synonyms.json).
"""
import json
from typing import Dict


def load_synonyms(path: str) -> Dict[str, list]:
    """Load synonyms. Trả {} nếu file không tồn tại hoặc lỗi."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_synonyms(synonyms: Dict[str, list], path: str) -> None:
    """Ghi synonyms ra JSON (UTF-8, indent 4)."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(synonyms, f, ensure_ascii=False, indent=4)
