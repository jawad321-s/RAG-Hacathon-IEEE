"""Retrieval + generation metrics.

Retrieval (needs `relevant_sources` / `relevant_keywords` in the eval set):
- Hit@k        : at least one relevant chunk in top-k
- Precision@k  : fraction of top-k chunks that are relevant
- Recall@k     : fraction of relevant sources found in top-k
- MRR          : 1 / rank of first relevant chunk

Generation (LLM-as-judge, needs an API key):
- Faithfulness : share of answer claims supported by retrieved sources
- Correctness  : agreement with the reference answer
- Citation rate: answers that contain at least one valid [n] citation
- Refusal acc. : out-of-scope questions correctly refused, in-scope ones answered
"""

from __future__ import annotations

import json
import re

from app.config import get_settings
from app.generation.llm import get_llm
from app.generation.prompts import CORRECTNESS_JUDGE, FAITHFULNESS_JUDGE
from app.ingestion.arabic import normalize_for_search


def is_relevant(chunk_text: str, chunk_meta: dict, item: dict) -> bool:
    """A chunk is relevant if it comes from an expected source (and page, if given)
    OR contains one of the expected keywords."""
    srcs = item.get("relevant_sources") or []
    pages = item.get("relevant_pages") or []
    kws = item.get("relevant_keywords") or []
    src_ok = any(s.lower() in str(chunk_meta.get("source", "")).lower() for s in srcs)
    if src_ok and pages:
        src_ok = chunk_meta.get("page") in pages
    norm = normalize_for_search(chunk_text)
    kw_ok = any(normalize_for_search(k) in norm for k in kws)
    if item.get("strict") and srcs and kws:  # both must match
        return src_ok and kw_ok
    return src_ok or kw_ok


def retrieval_metrics(flags: list[bool], k: int, n_relevant_expected: int = 1) -> dict:
    top = flags[:k]
    first = next((i for i, f in enumerate(flags) if f), None)
    return {
        "hit": float(any(top)),
        "precision": sum(top) / k if k else 0.0,
        "recall": min(1.0, sum(top) / max(1, n_relevant_expected)),
        "mrr": 1.0 / (first + 1) if first is not None else 0.0,
    }


def _judge(prompt: str) -> dict:
    s = get_settings()
    res = get_llm().complete([{"role": "user", "content": prompt}], model=s.llm_utility_model, temperature=0, max_tokens=400, json_mode=True)
    m = re.search(r"\{.*\}", res.text, re.S)
    return json.loads(m.group(0) if m else res.text)


def faithfulness(context: str, answer: str) -> dict:
    try:
        return _judge(FAITHFULNESS_JUDGE.format(context=context[:12000], answer=answer))
    except Exception as exc:
        return {"score": None, "error": str(exc)}


def correctness(question: str, reference: str, answer: str) -> dict:
    try:
        return _judge(CORRECTNESS_JUDGE.format(question=question, reference=reference, answer=answer))
    except Exception as exc:
        return {"score": None, "error": str(exc)}
