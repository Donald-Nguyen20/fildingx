# Funtion/rag_dedup.py
import os
import re
import hashlib
from typing import Dict, List, Tuple, Set, Any

_WS = re.compile(r"\s+")

def norm_for_hash(s: str) -> str:
    """Normalize nhẹ để hash ổn định nhưng KHÔNG làm mất số/ký tự quan trọng."""
    s = (s or "").strip().lower()
    s = _WS.sub(" ", s)
    return s

def sha1_text(s: str) -> str:
    return hashlib.sha1(s.encode("utf-8", errors="ignore")).hexdigest()

# ----------------------------
# 1) Duplicate FILE NAME check
# ----------------------------
def build_existing_filenames(metadata_list: List[Dict[str, Any]]) -> Dict[str, int]:
    """
    Build a counter of existing file names inside the store, based on metadata.json.
    Assumes each metadata item has 'file_name' (your code does).
    """
    cnt: Dict[str, int] = {}
    for m in metadata_list or []:
        fn = (m.get("file_name") or "").strip()
        if not fn:
            # fallback: parse from abs_path if needed
            ap = m.get("abs_path") or m.get("source") or ""
            fn = os.path.basename(ap) if ap else ""
        if fn:
            key = fn.lower()
            cnt[key] = cnt.get(key, 0) + 1
    return cnt

def is_duplicate_filename(file_path: str, existing_filenames_counter: Dict[str, int]) -> bool:
    """True nếu tên file (basename) đã tồn tại trong store."""
    name = os.path.basename(file_path or "").strip().lower()
    if not name:
        return False
    return existing_filenames_counter.get(name, 0) > 0

# ----------------------------
# 2) Chunk-hash duplicate check
# ----------------------------
def build_existing_chunk_hashes(metadata_list: List[Dict[str, Any]]) -> Set[str]:
    """
    Build a set of hashes of existing chunk texts in store.
    Assumes metadata item has 'text' containing chunk content.
    """
    s: Set[str] = set()
    for m in metadata_list or []:
        t = m.get("text") or ""
        t = t.strip()
        if not t:
            continue
        s.add(sha1_text(norm_for_hash(t)))
    return s

def dedup_chunks_by_hash(
    chunks: List[str],
    existing_hashes: Set[str],
) -> Tuple[List[str], int, float]:
    """
    Remove duplicate chunks (by hash). Returns:
    - unique_chunks: chunks not seen before
    - dup_count: number of skipped duplicate chunks
    - dup_ratio: dup_count/total
    """
    total = len(chunks or [])
    if total == 0:
        return [], 0, 0.0

    uniq: List[str] = []
    dup = 0

    for ch in chunks:
        ch = (ch or "").strip()
        if not ch:
            continue
        h = sha1_text(norm_for_hash(ch))
        if h in existing_hashes:
            dup += 1
            continue
        existing_hashes.add(h)
        uniq.append(ch)

    denom = max(total, 1)
    dup_ratio = dup / denom
    return uniq, dup, dup_ratio

def should_skip_file_by_dup_ratio(dup_ratio: float, threshold: float = 0.80) -> bool:
    """Nếu > threshold thì coi file gần như trùng nội dung, nên skip (tuỳ bạn quyết)."""
    return dup_ratio >= threshold
