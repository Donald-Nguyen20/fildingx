"""core/semantic.py -- optional semantic (embedding) layer for the Create DB index.

Qt-free. fastembed + onnxruntime run the model; nothing here needs torch, so the
lean build stays lean when semantic is off. Everything imports fastembed lazily,
so `import core.semantic` costs nothing until a vector is actually asked for.

Model: intfloat/multilingual-e5-large (dim 1024), chosen for Vietnamese<->English
cross-lingual retrieval and because fastembed ships an ONNX build of it. e5 wants a
"query: " / "passage: " prefix, which fastembed adds for us -- so query text goes
through embed_query() and chunk text through embed_passages(), never the other way.

The device is picked automatically: CUDA when onnxruntime exposes it (needs the GPU
build, fastembed-gpu), CPU otherwise. Building the index on CPU is slow; searching
is fast either way, since a search only embeds one short query.
"""
import os
import sqlite3

MODEL_NAME = "intfloat/multilingual-e5-large"
DIM = 1024

_model = None
_active_providers = None   # what the loaded model actually got, for device_label()


def available() -> bool:
    """True when fastembed is installed, i.e. semantic can run at all."""
    try:
        import fastembed  # noqa: F401
        import numpy       # noqa: F401
        return True
    except Exception:
        return False


def _cuda_setup():
    try:
        from core import cuda_setup
    except ImportError:
        import cuda_setup
    return cuda_setup


def _providers():
    """CUDA first when it really initialises (DLLs load, not just listed), else CPU."""
    if _cuda_setup().cuda_works():
        return ["CUDAExecutionProvider", "CPUExecutionProvider"]
    return ["CPUExecutionProvider"]


def using_gpu() -> bool:
    """True only when a CUDA session can actually be created on this machine."""
    return _cuda_setup().cuda_works()


def device_label() -> str:
    """'GPU' or 'CPU' -- the device the model is actually set up on once loaded,
    or the device it will try before that."""
    provs = _active_providers if _active_providers is not None else _providers()
    return "GPU" if "CUDAExecutionProvider" in provs else "CPU"


def advice() -> tuple:
    """(status, message) for a UI notice: whether semantic can run, on what device,
    and whether it is worth using. status is 'GPU', 'CPU' or 'unavailable'."""
    if not available():
        return ("unavailable",
                "Semantic needs fastembed  (pip install fastembed-gpu).")
    if using_gpu():
        return ("GPU",
                "GPU detected - semantic search is fast; recommended.")
    return ("CPU",
            "No GPU (CPU only) - semantic still works, but building the index is "
            "slow; Keyword is faster for exact names, numbers and KKS tags.")


def _get_model():
    global _model, _active_providers
    if _model is None:
        _cuda_setup().setup()   # put the CUDA wheel DLLs on PATH before the session
        from fastembed import TextEmbedding
        provs = _providers()
        try:
            _model = TextEmbedding(MODEL_NAME, providers=provs)
            _active_providers = provs
        except Exception:
            # A broken CUDA runtime should not sink the whole feature.
            _model = TextEmbedding(MODEL_NAME, providers=["CPUExecutionProvider"])
            _active_providers = ["CPUExecutionProvider"]
    return _model


# How many chunks go through the model at once. fastembed's own default is 256,
# and e5-large at 256 x 512 tokens needs more than the 8 GB of an RTX 4060: the
# driver spills to system RAM and 640 chunks took over five minutes. Measured
# on real chunks: 16 runs at 31 chunks/s, 32 at 28, 64 at 27 with 6.5 GB of
# VRAM in use -- so the smallest is also the fastest, and leaves room for the
# OCR models that are still loaded when Create DB gets to this step.
EMBED_BATCH = 16


def embed_passages(texts):
    """Embed chunk text (heading + content) as e5 passages. Returns float32 ndarray."""
    import numpy as np
    m = _get_model()
    return np.asarray(list(m.embed(list(texts), batch_size=EMBED_BATCH)), dtype="float32")


def embed_query(text):
    """Embed one search query as an e5 query. Returns a 1-D float32 ndarray."""
    import numpy as np
    m = _get_model()
    return np.asarray(list(m.query_embed([text]))[0], dtype="float32")


# ── Index-side: fill chunk_vectors for chunks that do not have one yet ────────

_MISSING = ("SELECT c.id, c.heading, c.content FROM chunks c "
            "LEFT JOIN chunk_vectors v ON v.chunk_id = c.id WHERE v.chunk_id IS NULL")


def _embed_rows(conn, rows, should_stop=None, progress=None, batch=64, commit=True) -> int:
    """Embed rows of (chunk id, heading, content) into chunk_vectors, batch by
    batch, and return how many were done. Between batches should_stop() is
    asked and progress(done, of) told; what is done before a stop stays."""
    cur = conn.cursor()
    done = 0
    for i in range(0, len(rows), batch):
        if should_stop is not None and should_stop():
            break
        part = rows[i:i + batch]
        texts = [((h + "\n" + b) if h else b) for _, h, b in part]
        vecs = embed_passages(texts)
        cur.executemany(
            "INSERT OR REPLACE INTO chunk_vectors (chunk_id, vector) VALUES (?, ?)",
            [(cid, v.tobytes()) for (cid, _, _), v in zip(part, vecs)],
        )
        if commit:
            conn.commit()
        done += len(part)
        if progress is not None:
            progress(done, len(rows))
    return done


def embed_file(conn, file_id, should_stop=None, progress=None) -> int:
    """Embed the chunks of one file that have no vector yet; returns how many.

    Create DB calls it for each file as it goes, so the vectors of every file
    finished are kept when the build is stopped: they used to be made only
    once every file had been read, and a 36-hour build stopped near its end
    had 140,248 chunks and not one vector. Nothing is committed here -- the
    caller commits the vectors together with the file's chunks."""
    rows = conn.execute(_MISSING + " AND c.file_id = ?", (file_id,)).fetchall()
    return _embed_rows(conn, rows, should_stop, progress, commit=False)


def build_embeddings(conn, progress=None, should_stop=None, batch=64):
    """Embed every chunk missing a vector and record the model used.

    conn is an open read-write connection to a Create DB database whose schema
    already carries chunk_vectors / semantic_meta (init_db creates them). Returns
    how many chunks were embedded. Safe to re-run: it only touches chunks whose
    vector is absent, so an incremental index tops up rather than redoing the lot.
    Each batch is committed, so a stop keeps what was done.
    """
    done = _embed_rows(conn, conn.execute(_MISSING).fetchall(),
                       should_stop, progress, batch, commit=True)
    write_meta(conn)
    return done


def coverage(conn) -> tuple:
    """(chunks that have a vector, all chunks) in an open database."""
    return (conn.execute("SELECT COUNT(*) FROM chunk_vectors v "
                         "JOIN chunks c ON c.id = v.chunk_id").fetchone()[0],
            conn.execute("SELECT COUNT(*) FROM chunks").fetchone()[0])


def write_meta(conn):
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO semantic_meta (key, value) VALUES ('model', ?)",
                (MODEL_NAME,))
    cur.execute("INSERT OR REPLACE INTO semantic_meta (key, value) VALUES ('dim', ?)",
                (str(DIM),))
    conn.commit()


# ── Search-side: cosine over the stored vectors, one matrix per database ──────

_cache = {}   # (abspath, mtime) -> (ids ndarray, normalized matrix ndarray | None)


def has_embeddings(db_path) -> bool:
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        n = conn.execute("SELECT COUNT(*) FROM chunk_vectors").fetchone()[0]
        conn.close()
        return n > 0
    except Exception:
        return False


def _load_matrix(db_path):
    import numpy as np
    key = (os.path.abspath(db_path), os.path.getmtime(db_path))
    hit = _cache.get(key)
    if hit is not None:
        return hit
    _cache.clear()   # one database in memory at a time; the matrix is large
    ids = np.array([], dtype=np.int64)
    mat = None
    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
        rows = conn.execute("SELECT chunk_id, vector FROM chunk_vectors").fetchall()
        conn.close()
        if rows:
            ids = np.fromiter((r[0] for r in rows), dtype=np.int64, count=len(rows))
            mat = np.stack([np.frombuffer(r[1], dtype="float32") for r in rows])
            norms = np.linalg.norm(mat, axis=1, keepdims=True)
            norms[norms == 0] = 1.0
            mat = mat / norms
    except Exception:
        ids, mat = np.array([], dtype=np.int64), None
    _cache[key] = (ids, mat)
    return ids, mat


def search(db_path, query_text, top_k=50):
    """Return [(chunk_id, score), ...] for the chunks closest to query_text."""
    import numpy as np
    ids, mat = _load_matrix(db_path)
    if mat is None or len(ids) == 0:
        return []
    q = embed_query(query_text).astype("float32")
    n = np.linalg.norm(q)
    if n:
        q = q / n
    sims = mat @ q
    k = min(top_k, sims.shape[0])
    top = np.argpartition(-sims, k - 1)[:k]
    top = top[np.argsort(-sims[top])]
    return [(int(ids[i]), float(sims[i])) for i in top]
