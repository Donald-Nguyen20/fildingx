# vector_retriever.py
import os, json
import numpy as np
import faiss
import torch
from sentence_transformers import SentenceTransformer


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

    def search(
        self,
        query: str,
        top_k: int = 8,
        candidate_k: int = 30,
        min_score: float = 0.28,
        max_per_file: int = 2,
    ):
        qv = self.model.encode([query], normalize_embeddings=True)
        qv = np.asarray(qv, dtype="float32")

        D, I = self.index.search(qv, candidate_k)

        results = []
        file_count = {}

        for score, idx in zip(D[0], I[0]):
            if idx < 0:
                continue

            score = float(score)
            if score < min_score:
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

            results.append({
                "score": score,
                "text": text,
                "file_name": file_name,
                "rel_path": m.get("rel_path", ""),
                "abs_path": abs_path,
                "chunk_id": m.get("chunk_id", 0),
                "file_type": m.get("file_type", ""),
                "mtime": m.get("mtime"),
                "size_kb": m.get("size_kb"),
            })

            file_count[file_name] = file_count.get(file_name, 0) + 1

            if len(results) >= top_k:
                break

        return results
