# embedding_client.py
import os
import time
import numpy as np


class EmbeddingClient:
    @property
    def dim(self) -> int:
        raise NotImplementedError

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        raise NotImplementedError

    def embed_query(self, text: str) -> np.ndarray:
        raise NotImplementedError


class LocalEmbeddingClient(EmbeddingClient):
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2"):
        import torch
        from sentence_transformers import SentenceTransformer

        cpu_threads = int(os.environ.get("RAG_CPU_THREADS", "14"))
        torch.set_num_threads(cpu_threads)
        os.environ.setdefault("OMP_NUM_THREADS", str(cpu_threads))
        os.environ.setdefault("MKL_NUM_THREADS", str(cpu_threads))

        self.model_name = model_name
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self._model = SentenceTransformer(model_name, device=device)
        self._dim = int(self._model.get_sentence_embedding_dimension())

    @property
    def dim(self) -> int:
        return self._dim

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        batch_size = int(os.environ.get("RAG_BATCH_SIZE", "128"))
        vecs = self._model.encode(
            texts,
            batch_size=batch_size,
            show_progress_bar=True,
            normalize_embeddings=True,
        )
        return np.asarray(vecs, dtype="float32")

    def embed_query(self, text: str) -> np.ndarray:
        v = self._model.encode([text], normalize_embeddings=True)
        return np.asarray(v, dtype="float32")


class GeminiEmbeddingClient(EmbeddingClient):
    _DIM = 768
    _MODEL = "models/text-embedding-004"
    _BATCH_SIZE = 50
    # ~85 req/min stays under free-tier 100 req/min limit
    _BATCH_DELAY = 0.7

    def __init__(self, api_key: str):
        import google.generativeai as genai
        if not api_key:
            raise ValueError("Gemini API key is required for Gemini embedding provider.")
        genai.configure(api_key=api_key)
        self._genai = genai

    @property
    def dim(self) -> int:
        return self._DIM

    def _call_api(self, texts: list[str], task_type: str) -> list[list[float]]:
        for attempt in range(4):
            try:
                result = self._genai.embed_content(
                    model=self._MODEL,
                    content=texts,
                    task_type=task_type,
                )
                embs = result["embedding"]
                # Single text returns a flat list; wrap it
                if embs and not isinstance(embs[0], list):
                    return [embs]
                return embs
            except Exception:
                if attempt == 3:
                    raise
                time.sleep(2 ** attempt)
        return []

    def embed_batch(self, texts: list[str]) -> np.ndarray:
        all_vecs: list[list[float]] = []
        for start in range(0, len(texts), self._BATCH_SIZE):
            batch = texts[start: start + self._BATCH_SIZE]
            all_vecs.extend(self._call_api(batch, "retrieval_document"))
            if start + self._BATCH_SIZE < len(texts):
                time.sleep(self._BATCH_DELAY)

        mat = np.array(all_vecs, dtype="float32")
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        return mat / norms

    def embed_query(self, text: str) -> np.ndarray:
        vecs = self._call_api([text], "retrieval_query")
        mat = np.array(vecs, dtype="float32")
        norms = np.linalg.norm(mat, axis=1, keepdims=True)
        norms = np.where(norms == 0, 1, norms)
        return mat / norms


def create_embedding_client(
    provider: str,
    model_name: str = "",
    api_key: str = "",
) -> EmbeddingClient:
    if provider == "gemini":
        return GeminiEmbeddingClient(api_key=api_key)
    return LocalEmbeddingClient(
        model_name=model_name or "sentence-transformers/all-MiniLM-L6-v2"
    )
