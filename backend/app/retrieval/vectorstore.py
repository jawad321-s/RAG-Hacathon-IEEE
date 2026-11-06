"""ChromaDB wrapper (persistent, cosine distance) + in-memory BM25 index.

Chroma is the single source of truth for chunks. The BM25 index is rebuilt
from Chroma on startup and after every ingest/delete, so the two never drift.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from functools import lru_cache

import chromadb
from chromadb.config import Settings as ChromaSettings
from rank_bm25 import BM25Okapi

from app.config import get_settings
from app.ingestion.arabic import tokenize
from app.ingestion.chunker import Chunk

from .embeddings import get_embedder

log = logging.getLogger(__name__)


@dataclass
class Hit:
    id: str
    text: str
    metadata: dict
    score: float = 0.0
    scores: dict = field(default_factory=dict)  # per-stage scores, for explainability


def _where(filters: dict | None) -> dict | None:
    """{"category": "faq"} -> equality;  {"category": ["public", "hr"]} -> $in (used for RBAC)."""
    if not filters:
        return None
    clauses = [{k: {"$in": list(v)} if isinstance(v, (list, tuple, set)) else v} for k, v in filters.items() if v not in (None, "", [])]
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"$and": clauses}


def _matches(meta: dict, filters: dict) -> bool:
    for key, v in filters.items():
        if v in (None, "", []):
            continue
        if isinstance(v, (list, tuple, set)):
            if meta.get(key) not in v:
                return False
        elif meta.get(key) != v:
            return False
    return True


class VectorStore:
    def __init__(self) -> None:
        s = get_settings()
        self._client = chromadb.PersistentClient(
            path=str(s.chroma_dir), settings=ChromaSettings(anonymized_telemetry=False)
        )
        self.embedder = get_embedder()
        self.collection = self._client.get_or_create_collection(
            name=s.collection_name,
            metadata={"hnsw:space": "cosine", "embedding_model": self.embedder.name},
            embedding_function=None,
        )
        stored_model = (self.collection.metadata or {}).get("embedding_model")
        if stored_model and stored_model != self.embedder.name:
            log.warning(
                "Collection was built with %s but current model is %s. Re-ingest (make reset ingest).",
                stored_model,
                self.embedder.name,
            )
        self._lock = threading.Lock()
        self._bm25: BM25Okapi | None = None
        self._bm25_ids: list[str] = []
        self._bm25_docs: dict[str, tuple[str, dict]] = {}
        self.rebuild_bm25()

    # ---------------------------------------------------------------- write
    def add_chunks(self, chunks: list[Chunk]) -> int:
        if not chunks:
            return 0
        # de-duplicate ids inside the batch
        uniq = {c.id: c for c in chunks}
        chunks = list(uniq.values())
        bs = 128
        for i in range(0, len(chunks), bs):
            batch = chunks[i : i + bs]
            self.collection.upsert(
                ids=[c.id for c in batch],
                documents=[c.text for c in batch],
                metadatas=[c.metadata for c in batch],
                embeddings=self.embedder.embed_documents([c.text for c in batch]),
            )
        self.rebuild_bm25()
        return len(chunks)

    def delete_source(self, source: str) -> None:
        self.collection.delete(where={"source": source})
        self.rebuild_bm25()

    def reset(self) -> None:
        s = get_settings()
        self._client.delete_collection(s.collection_name)
        self.collection = self._client.get_or_create_collection(
            name=s.collection_name,
            metadata={"hnsw:space": "cosine", "embedding_model": self.embedder.name},
            embedding_function=None,
        )
        self.rebuild_bm25()

    # ----------------------------------------------------------------- read
    def rebuild_bm25(self) -> None:
        with self._lock:
            data = self.collection.get(include=["documents", "metadatas"])
            ids = data.get("ids") or []
            docs = data.get("documents") or []
            metas = data.get("metadatas") or []
            self._bm25_ids = list(ids)
            self._bm25_docs = {i: (d, m or {}) for i, d, m in zip(ids, docs, metas)}
            corpus = [tokenize(d) for d in docs]
            self._bm25 = BM25Okapi(corpus) if corpus and any(corpus) else None
            log.info("BM25 index rebuilt with %d chunks", len(ids))

    def dense_search(self, query: str, k: int, filters: dict | None = None) -> list[Hit]:
        if self.count() == 0:
            return []
        res = self.collection.query(
            query_embeddings=[self.embedder.embed_query(query)],
            n_results=min(k, self.count()),
            where=_where(filters),
            include=["documents", "metadatas", "distances"],
        )
        hits = []
        for i, d, m, dist in zip(res["ids"][0], res["documents"][0], res["metadatas"][0], res["distances"][0]):
            sim = 1.0 - float(dist)  # cosine distance -> similarity
            hits.append(Hit(id=i, text=d, metadata=m or {}, score=sim, scores={"dense": sim}))
        return hits

    def bm25_search(self, query: str, k: int, filters: dict | None = None) -> list[Hit]:
        if self._bm25 is None:
            return []
        q = tokenize(query)
        if not q:
            return []
        scores = self._bm25.get_scores(q)
        order = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)
        hits: list[Hit] = []
        for idx in order:
            if scores[idx] <= 0 or len(hits) >= k:
                break
            cid = self._bm25_ids[idx]
            text, meta = self._bm25_docs[cid]
            if filters and not _matches(meta, filters):
                continue
            hits.append(Hit(id=cid, text=text, metadata=meta, score=float(scores[idx]), scores={"bm25": float(scores[idx])}))
        return hits

    def count(self) -> int:
        return self.collection.count()

    def list_sources(self) -> list[dict]:
        data = self.collection.get(include=["metadatas"])
        agg: dict[str, dict] = {}
        for m in data.get("metadatas") or []:
            if not m:
                continue
            src = m.get("source", "unknown")
            a = agg.setdefault(src, {"source": src, "chunks": 0, "pages": set(), "category": m.get("category", "")})
            a["chunks"] += 1
            if m.get("page", -1) != -1:
                a["pages"].add(m["page"])
        return [{**a, "pages": len(a["pages"])} for a in sorted(agg.values(), key=lambda x: x["source"])]

    def facet_values(self, key: str) -> list[str]:
        data = self.collection.get(include=["metadatas"])
        return sorted({str(m[key]) for m in data.get("metadatas") or [] if m and m.get(key) not in (None, "")})


@lru_cache
def get_store() -> VectorStore:
    return VectorStore()
