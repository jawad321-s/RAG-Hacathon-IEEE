"""Embedding providers.

Default: `intfloat/multilingual-e5-large` via fastembed (ONNX, CPU).
Why: top-tier open multilingual retrieval model with strong Arabic support,
runs locally (no per-query cost, documents never leave the machine -> privacy),
no PyTorch needed. E5 models expect "query: " / "passage: " prefixes.

Alternatives (set in .env):
- EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-mpnet-base-v2 (smaller/faster)
- EMBEDDING_PROVIDER=openrouter + EMBEDDING_MODEL=openai/text-embedding-3-small (remote)
"""

from __future__ import annotations

import hashlib
import logging
from functools import lru_cache
from typing import Protocol

import numpy as np

from app.config import get_settings

log = logging.getLogger(__name__)


class Embedder(Protocol):
    name: str

    def embed_documents(self, texts: list[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedEmbedder:
    def __init__(self, model: str, batch_size: int = 32):
        from fastembed import TextEmbedding

        self.name = model
        self.batch_size = batch_size
        self._is_e5 = "e5" in model.lower()
        log.info("Loading embedding model %s (first run downloads it)...", model)
        self._model = TextEmbedding(model_name=model, cache_dir=str(get_settings().models_cache_dir))

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        if self._is_e5:
            texts = [f"passage: {t}" for t in texts]
        return [v.tolist() for v in self._model.embed(texts, batch_size=self.batch_size)]

    def embed_query(self, text: str) -> list[float]:
        if self._is_e5:
            text = f"query: {text}"
        return next(iter(self._model.embed([text]))).tolist()


class OpenRouterEmbedder:
    def __init__(self, model: str, batch_size: int = 64):
        from openai import OpenAI

        s = get_settings()
        if reason := s.paid_model_reason(model, s.openrouter_base_url):
            raise RuntimeError(f"FREE_ONLY: {reason}. Use EMBEDDING_PROVIDER=fastembed (local, free).")
        self.name = model
        self.batch_size = batch_size
        self._client = OpenAI(api_key=s.openrouter_api_key, base_url=s.openrouter_base_url)

    def _embed(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            resp = self._client.embeddings.create(model=self.name, input=texts[i : i + self.batch_size])
            out.extend(d.embedding for d in resp.data)
        return out

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embed(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embed([text])[0]


class HashEmbedder:
    """Deterministic bag-of-words hashing embedder. TESTS ONLY (no semantics)."""

    def __init__(self, dim: int = 256):
        self.name = f"hash-{dim}"
        self.dim = dim

    def _vec(self, text: str) -> list[float]:
        from app.ingestion.arabic import tokenize

        v = np.zeros(self.dim, dtype=np.float32)
        for tok in tokenize(text):
            v[int(hashlib.md5(tok.encode()).hexdigest(), 16) % self.dim] += 1.0
        n = np.linalg.norm(v)
        return (v / n if n else v).tolist()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._vec(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vec(text)


class CachedEmbedder:
    """Disk cache (SQLite) in front of any embedder: a chunk with the same text and model
    is embedded once, ever. `make reset` and chunking experiments become near-instant for
    unchanged text — important on laptop CPUs with thousands of chunks."""

    def __init__(self, inner: Embedder, path):
        import sqlite3

        self.inner = inner
        self.name = inner.name
        self._db = sqlite3.connect(str(path), check_same_thread=False)
        self._db.execute("CREATE TABLE IF NOT EXISTS emb (k TEXT PRIMARY KEY, v BLOB)")

    def _key(self, text: str) -> str:
        return hashlib.sha1(f"{self.name}|passage|{text}".encode()).hexdigest()

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        keys = [self._key(t) for t in texts]
        found: dict[str, list[float]] = {}
        for i in range(0, len(keys), 500):
            part = keys[i : i + 500]
            q = f"SELECT k, v FROM emb WHERE k IN ({','.join('?' * len(part))})"
            for k, v in self._db.execute(q, part):
                found[k] = np.frombuffer(v, dtype=np.float32).tolist()
        missing = [(k, t) for k, t in zip(keys, texts) if k not in found]
        if missing:
            vecs = self.inner.embed_documents([t for _, t in missing])
            with self._db:
                self._db.executemany(
                    "INSERT OR REPLACE INTO emb VALUES (?, ?)",
                    [(k, np.asarray(v, dtype=np.float32).tobytes()) for (k, _), v in zip(missing, vecs)],
                )
            found.update({k: v for (k, _), v in zip(missing, vecs)})
        return [found[k] for k in keys]

    def embed_query(self, text: str) -> list[float]:
        return self.inner.embed_query(text)


@lru_cache
def get_embedder() -> Embedder:
    s = get_settings()
    if s.embedding_provider == "openrouter":
        return CachedEmbedder(OpenRouterEmbedder(s.embedding_model), s.data_dir / "embeddings_cache.sqlite")
    if s.embedding_provider == "hash":
        return HashEmbedder()
    return CachedEmbedder(FastEmbedEmbedder(s.embedding_model, s.embedding_batch_size), s.data_dir / "embeddings_cache.sqlite")
