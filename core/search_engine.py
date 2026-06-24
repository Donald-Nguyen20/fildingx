"""
core/search_engine.py — Toàn bộ logic tìm file, không phụ thuộc UI.
"""
import os
import re
import hashlib
from typing import List, Tuple, Optional, Dict

from rapidfuzz import fuzz
from core.percent_exclude_search import parse_percent_query, match_A_percent_B

FileResult = List[Tuple[str, str]]   # [(name, full_path), ...]


def search_files_by_name(folder_path: str, keyword: str) -> FileResult:
    """
    Tìm file theo tên. Hỗ trợ:
      - A,B  → tên chứa A HOẶC B (ít nhất một); hỗ trợ nhiều từ: A,B,C
      - A%B  → có A, không có B
      - A*B  → tên chứa cả A và B (theo thứ tự bất kỳ)
      - từ thường → regex contains, case-insensitive
    """
    matches: FileResult = []

    # --- A,B  OR syntax (tên chứa ít nhất MỘT từ) ---
    if "," in keyword:
        terms = [t.strip() for t in keyword.split(",") if t.strip()]
        if len(terms) >= 2:
            pattern = re.compile("|".join(re.escape(t) for t in terms), re.IGNORECASE)
            for root, _, files in os.walk(folder_path):
                for f in files:
                    if pattern.search(f):
                        matches.append((f, os.path.join(root, f)))
            return matches

    # --- A%B syntax ---
    q = parse_percent_query(keyword)
    if q is not None:
        for root, _, files in os.walk(folder_path):
            for f in files:
                if match_A_percent_B(f, q):
                    matches.append((f, os.path.join(root, f)))
        return matches

    # --- A*B syntax ---
    if "*" in keyword:
        parts = [p.strip() for p in keyword.split("*") if p.strip()]
        if len(parts) == 2:
            p1 = re.escape(parts[0]) + ".*" + re.escape(parts[1])
            p2 = re.escape(parts[1]) + ".*" + re.escape(parts[0])
            pattern = re.compile(f"({p1}|{p2})", re.IGNORECASE)
        else:
            pattern = re.compile(
                re.escape(keyword).replace(r"\*", ".*"), re.IGNORECASE
            )
    else:
        pattern = re.compile(re.escape(keyword), re.IGNORECASE)

    for root, _, files in os.walk(folder_path):
        for f in files:
            if pattern.search(f):
                matches.append((f, os.path.join(root, f)))

    return matches


def search_folders_by_name(folder_path: str, keyword: str) -> FileResult:
    """
    Tìm folder theo tên. Hỗ trợ A,B (OR) và A*B syntax (giống search_files_by_name).
    Trả về [(folder_name, full_path), ...]
    """
    # --- A,B  OR syntax (tên chứa ít nhất MỘT từ) ---
    if "," in keyword:
        terms = [t.strip() for t in keyword.split(",") if t.strip()]
        if len(terms) >= 2:
            pattern = re.compile("|".join(re.escape(t) for t in terms), re.IGNORECASE)
            matches: FileResult = []
            for root, dirs, _ in os.walk(folder_path):
                for d in dirs:
                    if pattern.search(d):
                        matches.append((d, os.path.join(root, d)))
            return matches

    if "*" in keyword:
        parts = [p.strip() for p in keyword.split("*") if p.strip()]
        if len(parts) == 2:
            p1 = re.escape(parts[0]) + ".*" + re.escape(parts[1])
            p2 = re.escape(parts[1]) + ".*" + re.escape(parts[0])
            pattern = re.compile(f"({p1}|{p2})", re.IGNORECASE)
        else:
            pattern = re.compile(
                re.escape(keyword).replace(r"\*", ".*"), re.IGNORECASE
            )
    else:
        pattern = re.compile(re.escape(keyword), re.IGNORECASE)

    matches: FileResult = []
    for root, dirs, _ in os.walk(folder_path):
        for d in dirs:
            if pattern.search(d):
                matches.append((d, os.path.join(root, d)))
    return matches


def fuzzy_search(
    folder_path: str,
    keyword: str,
    synonyms: Dict[str, list],
    threshold: int = 70,
) -> FileResult:
    """
    Tìm kiếm mờ (rapidfuzz) + từ đồng nghĩa.
    Tất cả từ khóa mở rộng đều phải khớp.
    """
    keywords_set: set = set()
    for kw in keyword.split():
        keywords_set.add(kw)
        keywords_set.update(synonyms.get(kw.lower(), []))

    results: FileResult = []
    for root, _, files in os.walk(folder_path):
        for f in files:
            f_lower = f.lower()
            if all(
                fuzz.partial_ratio(f_lower, kw.lower()) >= threshold
                for kw in keywords_set
            ):
                results.append((f, os.path.join(root, f)))
    return results


def calculate_hash(file_path: str) -> Optional[str]:
    """SHA-256 hash, đọc theo chunk 64 KB. Trả None nếu lỗi."""
    sha256 = hashlib.sha256()
    try:
        with open(file_path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                sha256.update(chunk)
        return sha256.hexdigest()
    except Exception:
        return None


def find_duplicate_files(folder_path: str) -> list:
    """
    Trả về danh sách nhóm file trùng (SHA-256 + size):
    [{"size": int, "hash": str, "files": [(name, path), ...]}, ...]
    Sắp xếp theo số lượng file trong nhóm giảm dần.
    """
    groups: dict = {}

    for root, _, files in os.walk(folder_path):
        for name in files:
            path = os.path.join(root, name)
            try:
                size = os.path.getsize(path)
            except Exception:
                continue
            h = calculate_hash(path)
            if not h:
                continue
            groups.setdefault((size, h), []).append((name, path))

    results = [
        {"size": sz, "hash": h, "files": items}
        for (sz, h), items in groups.items()
        if len(items) >= 2
    ]
    results.sort(key=lambda g: len(g["files"]), reverse=True)
    return results
