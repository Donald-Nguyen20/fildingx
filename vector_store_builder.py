# vector_store_builder.py
import os
import re
import json
import time
from dataclasses import dataclass
from typing import Callable, List, Optional, Set

import numpy as np
import faiss
import torch
from sentence_transformers import SentenceTransformer


@dataclass
class ChunkMeta:
    id: int
    file_name: str
    rel_path: str
    abs_path: str
    file_type: str
    source_folder: str
    chunk_id: int
    chunk_len: int
    mtime: float
    size_kb: int
    created_at: float
    section: str = ""
    subsection: str = ""
    text: str = ""



def normalize_text(text: str) -> str:
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

import re
from typing import Dict, Tuple

HEADING_RE = re.compile(r"^\s*(\d+(\.\d+)*)\s*[.)-]?\s+(.+)$")  # 1. / 6.2 / 3) ...
BULLET_RE  = re.compile(r"^\s*([-*•]|\d+[.)])\s+")

def _is_heading(line: str) -> bool:
    line = (line or "").strip()
    if not line:
        return False
    # dạng "6. SYSTEM DESIGN LIMITATIONS" hoặc "8 INITIAL CONDITIONS"
    if HEADING_RE.match(line):
        return True
    # heading IN HOA dài vừa
    if line.isupper() and 6 <= len(line) <= 120:
        return True
    return False

def sop_blocks(text: str) -> list[dict]:
    """
    Trả về list các block theo cấu trúc:
    {section, subsection, text}
    """
    lines = [ln.rstrip() for ln in (text or "").splitlines()]
    section = ""
    subsection = ""
    buf = []
    blocks = []

    def flush():
        nonlocal buf
        chunk = "\n".join([x for x in buf if x.strip()]).strip()
        if chunk:
            blocks.append({
                "section": section,
                "subsection": subsection,
                "text": chunk
            })
        buf = []

    for ln in lines:
        s = ln.strip()
        if not s:
            # giữ 1 dòng trống để phân tách bullet group
            if buf and buf[-1] != "":
                buf.append("")
            continue

        if _is_heading(s):
            # gặp heading => kết thúc block cũ
            flush()
            section = s
            subsection = ""  # reset
            buf.append(s)
            continue

        # sub-heading: dòng kết thúc ':' hoặc dạng "Circuit Breaker LV 400V..."
        if s.endswith(":") and len(s) <= 120:
            flush()
            subsection = s.rstrip(":")
            buf.append(s)
            continue

        # bullet hoặc nội dung thường
        buf.append(s)

    flush()
    return blocks

def pack_blocks_to_chunks(blocks: list[dict], target_chars: int = 1400, hard_max: int = 1800) -> list[dict]:
    """
    Gộp nhiều block nhỏ thành chunk ~ target_chars nhưng không vượt hard_max.
    Mỗi chunk vẫn giữ section/subsection gần nhất.
    """
    chunks = []
    cur = {"section": "", "subsection": "", "text": ""}

    def push_cur():
        nonlocal cur
        t = cur["text"].strip()
        if t:
            chunks.append({"section": cur["section"], "subsection": cur["subsection"], "text": t})
        cur = {"section": "", "subsection": "", "text": ""}

    for b in blocks:
        btxt = b["text"].strip()
        if not btxt:
            continue

        # nếu chunk trống -> lấy section/subsection hiện tại
        if not cur["text"]:
            cur["section"] = b.get("section", "") or cur["section"]
            cur["subsection"] = b.get("subsection", "") or cur["subsection"]

        candidate = (cur["text"] + "\n\n" + btxt).strip() if cur["text"] else btxt

        if len(candidate) <= hard_max:
            cur["text"] = candidate
        else:
            # đẩy chunk hiện tại, rồi bắt đầu chunk mới
            push_cur()
            cur["section"] = b.get("section", "")
            cur["subsection"] = b.get("subsection", "")
            cur["text"] = btxt

        # nếu đã đạt target -> chốt luôn để không “loãng”
        if len(cur["text"]) >= target_chars:
            push_cur()

    push_cur()
    return chunks

def chunk_text_sop(text: str, target_chars: int = 1400, hard_max: int = 1800) -> list[dict]:
    blocks = sop_blocks(text)
    return pack_blocks_to_chunks(blocks, target_chars=target_chars, hard_max=hard_max)


def chunk_text(text: str, chunk_size: int = 900, overlap: int = 150) -> List[str]:
    text = (text or "").strip()
    if not text:
        return []

    chunks = []
    start, n = 0, len(text)

    while start < n:
        end = min(start + chunk_size, n)
        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end == n:
            break
        start = max(0, end - overlap)

    return chunks


def build_vector_store(
    folder_path: str,
    extract_content_fn: Callable[[str], str],
    output_dir: str,
    model_name: str = "sentence-transformers/all-MiniLM-L6-v2",
    allowed_ext: Optional[Set[str]] = None,
    chunk_size: int = 900,
    overlap: int = 150,
    progress_cb: Optional[Callable[[int], None]] = None,
) -> str:
    # ---- CPU tuning for i7-12700F (20 threads logical) ----
    CPU_THREADS = int(os.environ.get("RAG_CPU_THREADS", "14"))
    torch.set_num_threads(CPU_THREADS)
    os.environ["OMP_NUM_THREADS"] = str(CPU_THREADS)
    os.environ["MKL_NUM_THREADS"] = str(CPU_THREADS)

    if allowed_ext is None:
        allowed_ext = {
            ".pdf", ".docx", ".xlsx", ".pptx", ".txt",
            ".csv", ".md", ".html", ".json", ".xml"
        }

    files = []
    for root, _, fnames in os.walk(folder_path):
        for fn in fnames:
            ext = os.path.splitext(fn)[1].lower()
            if ext in allowed_ext:
                files.append(os.path.join(root, fn))

    if not files:
        raise RuntimeError("No supported files found.")

    os.makedirs(output_dir, exist_ok=True)

    metas: List[ChunkMeta] = []
    total = len(files)
    next_id = 0
    created_at = time.time()
    source_folder = os.path.basename(folder_path.rstrip(os.sep))

    MIN_CHUNK_LEN = int(os.environ.get("RAG_MIN_CHUNK_LEN", "80"))

    for i, file_path in enumerate(files, start=1):
        stat = os.stat(file_path)
        name = os.path.basename(file_path)
        ext = os.path.splitext(file_path)[1].lower()
        rel_path = os.path.relpath(file_path, folder_path)

        try:
            raw = extract_content_fn(file_path)
        except Exception:
            raw = ""  # skip noisy error text

        text = normalize_text(raw)
        if not text:
            continue

        chunks = chunk_text_sop(text, target_chars=chunk_size, hard_max=chunk_size + 400)



        for cid, obj in enumerate(chunks):
            ch = (obj.get("text") or "").strip()
            if len(ch) < MIN_CHUNK_LEN:
                continue

            metas.append(ChunkMeta(
                id=next_id,
                file_name=name,
                rel_path=rel_path,
                abs_path=file_path,
                file_type=ext.lstrip("."),
                source_folder=source_folder,
                chunk_id=cid,
                chunk_len=len(ch),
                mtime=float(stat.st_mtime),
                size_kb=int(stat.st_size / 1024),
                created_at=float(created_at),
                section=(obj.get("section") or ""),
                subsection=(obj.get("subsection") or ""),
                text=ch,
            ))
            next_id += 1



        if progress_cb:
            progress_cb(int(i * 60 / total))

    if not metas:
        raise RuntimeError("No chunks created.")

    # ---- Embedding (use RTX 4060 if available) ----
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer(model_name, device=device)

    texts = [m.text for m in metas]

    batch_size = int(os.environ.get("RAG_BATCH_SIZE", "128"))  # 4060 + 32GB thường ok
    vectors = model.encode(
        texts,
        batch_size=batch_size,
        show_progress_bar=True,
        normalize_embeddings=True
    )
    vectors = np.asarray(vectors, dtype="float32")
    dim = vectors.shape[1]

    # ---- FAISS index: HNSW by default (scale-friendly) ----
    use_hnsw = os.environ.get("RAG_INDEX", "hnsw").lower() == "hnsw"
    if use_hnsw:
        M = int(os.environ.get("RAG_HNSW_M", "32"))
        index = faiss.IndexHNSWFlat(dim, M)
        index.hnsw.efConstruction = int(os.environ.get("RAG_EF_CONSTRUCT", "200"))
        index.add(vectors)
    else:
        index = faiss.IndexFlatIP(dim)
        index.add(vectors)

    if progress_cb:
        progress_cb(85)

    # Save files
    faiss.write_index(index, os.path.join(output_dir, "index.faiss"))

    with open(os.path.join(output_dir, "metadata.json"), "w", encoding="utf-8") as f:
        json.dump([m.__dict__ for m in metas], f, ensure_ascii=False, indent=2)

    with open(os.path.join(output_dir, "base_path.txt"), "w", encoding="utf-8") as f:
        f.write(folder_path)

    # Save index contract (to avoid model mismatch later)
    cfg = {
        "model_name": model_name,
        "normalize_embeddings": True,
        "index_type": "HNSW" if use_hnsw else "FlatIP",
        "dim": int(dim),
        "chunk_size": int(chunk_size),
        "overlap": int(overlap),
        "batch_size": int(batch_size),
        "cpu_threads": int(CPU_THREADS),
        "created_at": created_at,
        "min_chunk_len": int(MIN_CHUNK_LEN),
    }
    with open(os.path.join(output_dir, "index_config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)

    if progress_cb:
        progress_cb(100)

    return output_dir
def _load_manifest(store_dir: str) -> dict:
    p = os.path.join(store_dir, "manifest.json")
    if os.path.exists(p):
        try:
            with open(p, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"files": []}

def _save_json_atomic(path: str, obj):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)

def append_vector_store(
    store_dir: str,
    file_paths: list,
    extract_content_fn: Callable[[str], str],
    progress_cb: Optional[Callable[[int], None]] = None,
) -> int:
    """
    Append documents to an existing store_dir:
    Required: index.faiss, metadata.json, index_config.json
    Writes/Updates: index.faiss, metadata.json, manifest.json
    Returns: added_chunks
    """
    index_path = os.path.join(store_dir, "index.faiss")
    meta_path  = os.path.join(store_dir, "metadata.json")
    cfg_path   = os.path.join(store_dir, "index_config.json")
    base_path  = os.path.join(store_dir, "base_path.txt")

    if not (os.path.exists(index_path) and os.path.exists(meta_path) and os.path.exists(cfg_path)):
        raise FileNotFoundError("Store thiếu index.faiss / metadata.json / index_config.json")

    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # load base folder used when build (để rel_path consistent)
    folder_path = ""
    if os.path.exists(base_path):
        folder_path = (open(base_path, "r", encoding="utf-8", errors="replace").read() or "").strip()

    # load index + metadata
    index = faiss.read_index(index_path)
    with open(meta_path, "r", encoding="utf-8") as f:
        metas_raw = json.load(f)  # list[dict]

    # next_id = max existing id + 1
    max_id = -1
    for m in metas_raw:
        try:
            max_id = max(max_id, int(m.get("id", -1)))
        except Exception:
            pass
    next_id = max_id + 1

    # dedup by manifest
    manifest = _load_manifest(store_dir)
    seen = set()
    for it in manifest.get("files", []):
        seen.add((it.get("path"), it.get("mtime"), it.get("size")))

    allowed_ext = {".txt", ".md", ".pdf", ".docx"}
    new_files = []
    for fp in (file_paths or []):
        if not fp or not os.path.isfile(fp):
            continue
        ext = os.path.splitext(fp)[1].lower()
        if ext not in allowed_ext:
            continue
        ab = os.path.abspath(fp)
        st = os.stat(ab)
        key = (ab, int(st.st_mtime), int(st.st_size))
        if key in seen:
            continue
        new_files.append(ab)

    if not new_files:
        if progress_cb: progress_cb(100)
        return 0

    # validate embedding model/dim
    model_name = cfg.get("model_name", "sentence-transformers/all-MiniLM-L6-v2")
    dim_expected = int(cfg.get("dim", 0))

    # CPU tuning (giữ giống build)
    CPU_THREADS = int(os.environ.get("RAG_CPU_THREADS", str(cfg.get("cpu_threads", 14))))
    torch.set_num_threads(CPU_THREADS)
    os.environ["OMP_NUM_THREADS"] = str(CPU_THREADS)
    os.environ["MKL_NUM_THREADS"] = str(CPU_THREADS)

    model = SentenceTransformer(model_name)
    dim_now = int(model.get_sentence_embedding_dimension())
    if dim_expected and dim_expected != dim_now:
        raise ValueError(f"Embedding dim mismatch: store={dim_expected}, current={dim_now}")

    chunk_size = int(cfg.get("chunk_size", 900))
    overlap    = int(cfg.get("overlap", 150))  # (hiện build bạn không dùng overlap nhưng vẫn lưu)
    batch_size = int(cfg.get("batch_size", 32))
    MIN_CHUNK_LEN = int(os.environ.get("RAG_MIN_CHUNK_LEN", str(cfg.get("min_chunk_len", 80))))

    source_folder = os.path.basename((folder_path or "").rstrip(os.sep)) if folder_path else ""

    added_chunks = 0
    new_meta_dicts = []
    new_manifest = []

    total = len(new_files)
    for i, file_path in enumerate(new_files, start=1):
        if progress_cb:
            progress_cb(int((i - 1) * 80 / max(total, 1)))

        stat = os.stat(file_path)
        name = os.path.basename(file_path)
        ext = os.path.splitext(file_path)[1].lower()

        # rel_path: relative to original folder if possible
        if folder_path:
            try:
                rel_path = os.path.relpath(file_path, folder_path)
            except Exception:
                rel_path = name
        else:
            rel_path = name

        try:
            raw = extract_content_fn(file_path)
        except Exception:
            raw = ""

        text = normalize_text(raw)
        if not text:
            continue

        # IMPORTANT: giữ y chang build: dùng chunk_text_sop
        chunks = chunk_text_sop(text, target_chars=chunk_size, hard_max=chunk_size + 400)

        texts = []
        temp_meta = []
        for cid, obj in enumerate(chunks):
            ch = (obj.get("text") or "").strip()
            if len(ch) < MIN_CHUNK_LEN:
                continue

            texts.append(ch)
            temp_meta.append(ChunkMeta(
                id=next_id,
                file_name=name,
                rel_path=rel_path,
                abs_path=file_path,
                file_type=ext.lstrip("."),
                source_folder=source_folder,
                chunk_id=cid,
                chunk_len=len(ch),
                mtime=float(stat.st_mtime),
                size_kb=int(stat.st_size / 1024),
                created_at=float(time.time()),
                section=(obj.get("section") or ""),
                subsection=(obj.get("subsection") or ""),
                text=ch,
            ))
            next_id += 1

        if not texts:
            continue

        # embed + add to FAISS
        vecs = model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=False,
            normalize_embeddings=True
        )
        vecs = np.asarray(vecs, dtype="float32")
        index.add(vecs)

        # append metadata
        for m in temp_meta:
            new_meta_dicts.append(m.__dict__)

        added_chunks += len(temp_meta)

        # update manifest record for dedup
        new_manifest.append({
            "path": os.path.abspath(file_path),
            "mtime": int(stat.st_mtime),
            "size": int(stat.st_size),
        })

    # save
    if added_chunks > 0:
        metas_raw.extend(new_meta_dicts)

        # index atomic
        tmp_index = index_path + ".tmp"
        faiss.write_index(index, tmp_index)
        os.replace(tmp_index, index_path)

        _save_json_atomic(meta_path, metas_raw)

        manifest["files"] = (manifest.get("files", []) + new_manifest)
        _save_json_atomic(os.path.join(store_dir, "manifest.json"), manifest)

    if progress_cb:
        progress_cb(100)

    return int(added_chunks)
