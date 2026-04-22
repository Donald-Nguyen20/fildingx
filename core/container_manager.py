"""
core/container_manager.py — Lưu/tải container data (JSON).
"""
import json
import os
from typing import Dict


def load_containers(path: str) -> Dict:
    """Load containers từ JSON. Trả {} nếu file không tồn tại hoặc lỗi."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_containers(containers: Dict, path: str) -> None:
    """Ghi containers ra JSON (UTF-8, indent 2)."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(containers, f, ensure_ascii=False, indent=2)



def load_parents(path: str) -> Dict:
    """Load container parent relationships từ JSON. Trả {} nếu lỗi."""
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_parents(parents: Dict, path: str) -> None:
    """Ghi container_parents ra JSON."""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(parents, f, ensure_ascii=False, indent=2)


def get_file_containers(file_path: str, containers: Dict) -> list:
    """Trả về danh sách tên container đang chứa file_path."""
    result = []
    for name, files in containers.items():
        for fp, *_ in files:
            if os.path.normcase(fp) == os.path.normcase(file_path):
                result.append(name)
                break
    return result
