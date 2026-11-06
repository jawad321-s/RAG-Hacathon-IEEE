"""Hybrid retrieval pipeline.

    question
      │  (1) query rewrite: dialect -> MSA standalone question + keywords (LLM, optional)
      ▼
    dense (Chroma, multilingual-e5)  +  sparse (BM25, Arabic-normalized)
      │  (2) Reciprocal Rank Fusion  — robust, no score calibration needed
      ▼
    top ~20 candidates
      │  (3) cross-encoder rerank (multilingual)
      ▼
    top_k chunks + relevance gate (refuse if best score < threshold)

Why hybrid? Embeddings catch meaning/paraphrases & dialect; BM25 catches exact
terms: article numbers, course codes, drug names, IDs — things embeddings blur.
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field

from app.config import get_domain, get_settings
from app.generation.llm import get_llm
from app.generation.prompts import QUERY_REWRITE

from .reranker import get_reranker
from .vectorstore import Hit, get_store

log = logging.getLogger(__name__)


@dataclass
class RetrievalResult:
    query: str
    rewritten: str
    keywords: list[str]
    hits: list[Hit]
    in_scope: bool = True
    confident: bool = True
    timings_ms: dict = field(default_factory=dict)


def reciprocal_rank_fusion(result_lists: list[list[Hit]], weights: list[float], k: int = 60) -> list[Hit]:
    fused: dict[str, Hit] = {}
    totals: dict[str, float] = {}
    for hits, w in zip(result_lists, weights):
        for rank, h in enumerate(hits):
            totals[h.id] = totals.get(h.id, 0.0) + w / (k + rank + 1)
            if h.id in fused:
                fused[h.id].scores.update(h.scores)
            else:
                fused[h.id] = Hit(id=h.id, text=h.text, metadata=h.metadata, scores=dict(h.scores))
    for cid, h in fused.items():
        h.scores["rrf"] = totals[cid]
        h.score = totals[cid]
    return sorted(fused.values(), key=lambda h: h.score, reverse=True)


def rewrite_query(question: str, history: list[dict] | None = None) -> tuple[str, list[str], bool]:
    s = get_settings()
    llm = get_llm()
    if not s.use_query_rewrite or not llm.configured:
        return question, [], True
    d = get_domain()
    hist = "\n".join(f"{m['role']}: {m['content'][:300]}" for m in (history or [])[-4:]) or "(none)"
    prompt = QUERY_REWRITE.format(
        language_name="Arabic" if d.language == "ar" else "English",
        scope=f"{d.product_name} — {d.tagline} — {d.audience}",
        history=hist,
        question=question,
    )
    try:
        res = llm.complete([{"role": "user", "content": prompt}], model=s.llm_utility_model, temperature=0, max_tokens=300, json_mode=True)
        raw = re.search(r"\{.*\}", res.text, re.S)
        data = json.loads(raw.group(0) if raw else res.text)
        return (
            (data.get("standalone") or question).strip(),
            [k for k in data.get("keywords", []) if isinstance(k, str)][:8],
            bool(data.get("in_scope", True)),
        )
    except Exception as exc:
        log.warning("query rewrite failed: %s", exc)
        return question, [], True


def retrieve(
    question: str,
    history: list[dict] | None = None,
    filters: dict | None = None,
    top_k: int | None = None,
    use_rewrite: bool | None = None,
) -> RetrievalResult:
    s = get_settings()
    store = get_store()
    top_k = top_k or s.top_k
    timings: dict[str, int] = {}

    t = time.perf_counter()
    if use_rewrite is False:
        rewritten, keywords, in_scope = question, [], True
    else:
        rewritten, keywords, in_scope = rewrite_query(question, history)
    timings["rewrite"] = int((time.perf_counter() - t) * 1000)

    t = time.perf_counter()
    dense_q = rewritten
    sparse_q = " ".join([question, rewritten, *keywords])
    dense = store.dense_search(dense_q, s.candidate_k, filters)
    if rewritten != question:  # also search with the original wording (dialect terms)
        dense += [h for h in store.dense_search(question, s.candidate_k // 2, filters) if h.id not in {d.id for d in dense}]
    sparse = store.bm25_search(sparse_q, s.candidate_k, filters)
    timings["search"] = int((time.perf_counter() - t) * 1000)

    fused = reciprocal_rank_fusion([dense, sparse], [s.hybrid_alpha, 1 - s.hybrid_alpha], k=s.rrf_k)[: s.candidate_k]

    t = time.perf_counter()
    reranker = get_reranker()
    if reranker and fused:
        hits = reranker.rerank(rewritten, fused, top_k)
        confident = bool(hits) and hits[0].scores.get("rerank", 0) >= s.min_relevance_score
    else:
        hits = fused[:top_k]
        # without reranker, gate on dense cosine similarity of the best hit
        best_dense = max((h.scores.get("dense", 0) for h in hits), default=0)
        confident = bool(hits) and (best_dense >= 0.75 or any("bm25" in h.scores for h in hits[:2]))
    timings["rerank"] = int((time.perf_counter() - t) * 1000)

    return RetrievalResult(
        query=question,
        rewritten=rewritten,
        keywords=keywords,
        hits=hits,
        in_scope=in_scope,
        confident=confident,
        timings_ms=timings,
    )
