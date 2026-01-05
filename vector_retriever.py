# vector_retriever.py
import os, json
import numpy as np
import faiss
import torch
from sentence_transformers import SentenceTransformer

import math
import re
from collections import Counter, defaultdict

# --- reranker (CrossEncoder) optional
try:
    from sentence_transformers import CrossEncoder
except Exception:
    CrossEncoder = None


# =========================
# BM25 (lexical) - mini
# =========================
WORD_RE = re.compile(r"[A-Za-z0-9_./-]+")

def tokenize(s: str):
    return WORD_RE.findall((s or "").lower())

class BM25Mini:
    """
    BM25 rất gọn (pure python).
    - docs: list các document đã tokenize
    """
    def __init__(self, docs: list[list[str]], k1=1.5, b=0.75):
        self.docs = docs
        self.k1 = k1
        self.b = b

        self.df = defaultdict(int)
        self.doc_len = [len(d) for d in docs]
        self.avgdl = (sum(self.doc_len) / max(1, len(self.doc_len)))

        for d in docs:
            seen = set(d)
            for w in seen:
                self.df[w] += 1

        self.N = len(docs)
        self.idf = {}
        for w, df in self.df.items():
            self.idf[w] = math.log(1 + (self.N - df + 0.5) / (df + 0.5))

        self.tfs = [Counter(d) for d in docs]

    def score(self, q_tokens: list[str], i: int) -> float:
        tf = self.tfs[i]
        dl = self.doc_len[i]
        score = 0.0

        for w in q_tokens:
            if w not in tf:
                continue
            f = tf[w]
            idf = self.idf.get(w, 0.0)
            denom = f + self.k1 * (1 - self.b + self.b * (dl / (self.avgdl + 1e-9)))
            score += idf * (f * (self.k1 + 1)) / (denom + 1e-9)

        return score

    def topk(self, query: str, k: int = 30) -> list[tuple[int, float]]:
        q = tokenize(query)
        scored = [(i, self.score(q, i)) for i in range(self.N)]
        scored.sort(key=lambda x: x[1], reverse=True)
        return scored[:k]


# =========================
# Vector Retriever (Dense + Hybrid + Rerank)
# =========================
class VectorRetriever:
    def __init__(self, store_dir: str, model_name: str = "all-MiniLM-L6-v2"):
        self.store_dir = store_dir
        self.index = faiss.read_index(os.path.join(store_dir, "index.faiss"))

        with open(os.path.join(store_dir, "metadata.json"), "r", encoding="utf-8") as f:
            self.meta = json.load(f)

        with open(os.path.join(store_dir, "base_path.txt"), "r", encoding="utf-8") as f:
            self.base_path = f.read().strip()

        device = "cuda" if torch.cuda.is_available() else "cpu"
        self.model = SentenceTransformer(model_name, device=device)

        # Nếu index là HNSW thì set efSearch để tăng chất lượng
        if hasattr(self.index, "hnsw"):
            self.index.hnsw.efSearch = 64

        # BM25 lazy init
        self._bm25 = None

        # Reranker lazy init
        self._reranker = None
        self.enable_rerank = os.environ.get("RAG_ENABLE_RERANK", "1") == "1"
        self.rerank_model_name = os.environ.get(
            "RAG_RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2"
        )

        # số candidate đem đi rerank (đừng quá lớn sẽ chậm)
        self.rerank_topn = int(os.environ.get("RAG_RERANK_TOPN", "40"))

        # trọng số trộn rerank vào điểm cuối
        # final = alpha * rerank + (1-alpha) * mix
        self.rerank_alpha = float(os.environ.get("RAG_RERANK_ALPHA", "0.70"))

    def _ensure_bm25(self):
        if self._bm25 is not None:
            return
        docs = [tokenize(m.get("text", "")) for m in self.meta]
        self._bm25 = BM25Mini(docs)

    def _ensure_reranker(self):
        if not self.enable_rerank:
            return
        if CrossEncoder is None:
            # không có CrossEncoder (thiếu deps) => auto disable
            self.enable_rerank = False
            return
        if self._reranker is None:
            # CrossEncoder tự chọn device (cuda/cpu) theo torch
            self._reranker = CrossEncoder(self.rerank_model_name)

    @staticmethod
    def _minmax_norm(vals: list[float]):
        if not vals:
            return lambda x: 0.0
        vmin = min(vals)
        vmax = max(vals)
        if vmax == vmin:
            return lambda x: 0.0
        return lambda x: (x - vmin) / (vmax - vmin)

    @staticmethod
    def _minmax_norm_arr(arr: list[float]):
        if not arr:
            return [0.0] * 0
        vmin = min(arr)
        vmax = max(arr)
        if vmax == vmin:
            return [0.0 for _ in arr]
        return [(x - vmin) / (vmax - vmin) for x in arr]

    def search(
        self,
        query: str,
        top_k: int = 8,
        candidate_k: int = 30,
        min_score: float = 0.15,     # thang 0..1
        max_per_file: int = 2,
        use_hybrid: bool = True,
        w_dense: float = 0.65,
        w_bm25: float = 0.35,
    ):
        """
        Bước 2: Hybrid retrieval (dense + bm25)
        Bước 3: Rerank topN bằng CrossEncoder (optional)
        """

        # ---- 1) Dense search
        qv = self.model.encode([query], normalize_embeddings=True)
        qv = np.asarray(qv, dtype="float32")
        D, I = self.index.search(qv, candidate_k)

        dense_ids = [int(x) for x in I[0] if int(x) >= 0]
        dense_scores = [float(x) for x in D[0][:len(dense_ids)]]

        dense_norm = self._minmax_norm(dense_scores)

        cand_dense = {}
        for idx, sc in zip(dense_ids, dense_scores):
            cand_dense[idx] = max(cand_dense.get(idx, 0.0), dense_norm(sc))

        # ---- 2) BM25 search
        cand_bm25 = {}
        if use_hybrid:
            self._ensure_bm25()
            bm = self._bm25.topk(query, k=candidate_k)
            if bm:
                bm_scores = [float(x[1]) for x in bm]
                bm_max = max(bm_scores) if max(bm_scores) > 0 else 1.0
                for idx, sc in bm:
                    sc = float(sc)
                    if sc <= 0:
                        continue
                    cand_bm25[int(idx)] = max(cand_bm25.get(int(idx), 0.0), sc / bm_max)

        # ---- 3) Merge candidates -> mix_score
        all_ids = set(cand_dense.keys()) | set(cand_bm25.keys())

        mix = []
        for idx in all_ids:
            ds = cand_dense.get(idx, 0.0)
            bs = cand_bm25.get(idx, 0.0)
            mix_score = (w_dense * ds) + (w_bm25 * bs)
            mix.append((idx, mix_score, ds, bs))

        mix.sort(key=lambda x: x[1], reverse=True)  # sort by mix_score

        # ---- 4) RERANK topN (Bước 3)
        # Chỉ rerank head; tail giữ nguyên mix_score
        rerank_map = {}  # idx -> rerank_norm (0..1)
        final_scores = {}  # idx -> final_score

        if self.enable_rerank and len(mix) > 0:
            self._ensure_reranker()

        if self.enable_rerank and self._reranker is not None and len(mix) > 0:
            topN = min(self.rerank_topn, len(mix))
            head = mix[:topN]

            # tạo pairs (query, doc_text)
            pairs = []
            head_ids = []
            for idx, mix_score, ds, bs in head:
                text = (self.meta[idx].get("text", "") or "").strip()
                if not text:
                    # bỏ chunk rỗng
                    continue
                head_ids.append(idx)
                pairs.append((query, text))

            if pairs:
                rr = self._reranker.predict(pairs)  # list scores
                rr = [float(x) for x in rr]
                rr_norm = self._minmax_norm_arr(rr)

                for idx, s in zip(head_ids, rr_norm):
                    rerank_map[idx] = float(s)

        # final score = alpha*rerank + (1-alpha)*mix (nếu có rerank)
        alpha = self.rerank_alpha
        for idx, mix_score, ds, bs in mix:
            r = rerank_map.get(idx, None)
            if r is None:
                final = float(mix_score)
            else:
                final = alpha * float(r) + (1.0 - alpha) * float(mix_score)
            final_scores[idx] = final

        # sort theo final_score
        ranked = sorted(mix, key=lambda x: final_scores.get(x[0], x[1]), reverse=True)

        # ---- 5) Build results (lọc theo min_score + max_per_file)
        results = []
        file_count = {}

        for idx, mix_score, ds, bs in ranked:
            final = float(final_scores.get(idx, mix_score))

            if final < min_score:
                continue

            m = self.meta[idx]
            file_name = m.get("file_name", "")

            if file_count.get(file_name, 0) >= max_per_file:
                continue

            abs_path = m.get("abs_path")
            if not abs_path:
                abs_path = os.path.join(self.base_path, m.get("rel_path", ""))

            text = (m.get("text") or "").strip()
            if not text:
                continue

            out = {
                "score": final,                 # điểm cuối (đã rerank nếu bật)
                "mix": float(mix_score),         # điểm hybrid trước rerank
                "dense": float(ds),              # debug
                "bm25": float(bs),               # debug
                "rerank": float(rerank_map.get(idx, 0.0)) if idx in rerank_map else None,
                "text": text,
                "file_name": file_name,
                "rel_path": m.get("rel_path", ""),
                "abs_path": abs_path,
                "chunk_id": m.get("chunk_id", 0),
                "file_type": m.get("file_type", ""),
                "mtime": m.get("mtime"),
                "size_kb": m.get("size_kb"),
            }
            results.append(out)

            file_count[file_name] = file_count.get(file_name, 0) + 1

            if len(results) >= top_k:
                break

        return results
