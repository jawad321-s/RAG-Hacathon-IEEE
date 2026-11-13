"""Cross-encoder reranker (multilingual, local ONNX via fastembed).

Bi-encoders (embeddings) are fast but approximate. A cross-encoder reads the
(query, chunk) pair together and scores true relevance, which typically gives
a large jump in Precision@k. We only rerank the ~20 fused candidates, so the
extra latency is small.
"""

from __future__ import annotations

import logging
import math
from functools import lru_cache

from app.config import get_settings

from .vectorstore import Hit

log = logging.getLogger(__name__)


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


class Reranker:
    def __init__(self, model: str):
        from fastembed.rerank.cross_encoder import TextCrossEncoder

        log.info("Loading reranker %s ...", model)
        self.name = model
        self._model = TextCrossEncoder(model_name=model, cache_dir=str(get_settings().models_cache_dir))

    def rerank(self, query: str, hits: list[Hit], top_k: int) -> list[Hit]:
        if not hits:
            return []
        raw = list(self._model.rerank(query, [h.text for h in hits]))
        for h, s in zip(hits, raw):
            h.scores["rerank"] = _sigmoid(float(s))
            h.score = h.scores["rerank"]
        return sorted(hits, key=lambda h: h.score, reverse=True)[:top_k]


@lru_cache
def get_reranker() -> Reranker | None:
    s = get_settings()
    if not s.use_reranker or s.embedding_provider == "hash":
        return None
    try:
        return Reranker(s.reranker_model)
    except Exception as exc:  # never let the reranker take the system down
        log.error("Reranker unavailable (%s). Continuing without it.", exc)
        return None
