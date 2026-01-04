# vector_retriever.py
import os, json
import numpy as np
import faiss
from sentence_transformers import SentenceTransformer

class VectorRetriever:
    def __init__(self, store_dir: str, model_name: str = "all-MiniLM-L6-v2"):
        self.store_dir = store_dir
        self.index = faiss.read_index(os.path.join(store_dir, "index.faiss"))
        with open(os.path.join(store_dir, "metadata.json"), "r", encoding="utf-8") as f:
            self.meta = json.load(f)
        with open(os.path.join(store_dir, "base_path.txt"), "r", encoding="utf-8") as f:
            self.base_path = f.read().strip()

        self.model = SentenceTransformer(model_name)

    def search(self, query: str, top_k: int = 6):
        qv = self.model.encode([query], normalize_embeddings=True)
        qv = np.asarray(qv, dtype="float32")

        D, I = self.index.search(qv, top_k)

        results = []
        for score, idx in zip(D[0], I[0]):
            if idx < 0:
                continue
            m = self.meta[idx]
            # đảm bảo có abs_path (nếu metadata bạn chưa có abs_path thì tự ghép)
            abs_path = m.get("abs_path")
            if not abs_path:
                abs_path = os.path.join(self.base_path, m.get("rel_path", ""))

            results.append({
                "score": float(score),
                "text": m.get("text", ""),
                "file_name": m.get("file_name", ""),
                "rel_path": m.get("rel_path", ""),
                "abs_path": abs_path,
                "chunk_id": m.get("chunk_id", 0),
                "file_type": m.get("file_type", ""),
                "mtime": m.get("mtime"),
                "size_kb": m.get("size_kb"),
            })
        return results
