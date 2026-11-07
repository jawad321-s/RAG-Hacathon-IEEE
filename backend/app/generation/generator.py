"""Answer generation with citations and refusal.

`answer()` returns a full result; `answer_stream()` yields SSE-friendly events:
    {"type": "sources", ...} -> {"type": "token", "text": ...}* -> {"type": "done", ...}
"""

from __future__ import annotations

import re
import time
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field

from app.config import get_domain, get_settings
from app.retrieval.retriever import RetrievalResult, retrieve
from app.retrieval.vectorstore import Hit

from .llm import get_llm
from .prompts import USER_TEMPLATE, system_prompt

_CITATION = re.compile(r"\[(\d{1,2})\]")


@dataclass
class Source:
    index: int
    id: str
    source: str
    page: int | None
    section: str
    text: str
    score: float
    scores: dict
    translated: bool = False
    original_text: str = ""


@dataclass
class Answer:
    answer: str
    sources: list[Source]
    cited: list[int]
    refused: bool
    rewritten_query: str
    model: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0
    timings_ms: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _to_sources(hits: list[Hit]) -> list[Source]:
    out = []
    for i, h in enumerate(hits, start=1):
        page = h.metadata.get("page", -1)
        out.append(
            Source(
                index=i,
                id=h.id,
                source=h.metadata.get("source", "?"),
                page=None if page in (-1, None) else int(page),
                section=h.metadata.get("section", ""),
                text=h.text,
                score=round(float(h.score), 4),
                scores={k: round(float(v), 4) for k, v in h.scores.items()},
                translated=bool(h.metadata.get("translated")),
                original_text=str(h.metadata.get("original_text", "")),
            )
        )
    return out


def build_context(sources: list[Source]) -> str:
    blocks = []
    for s in sources:
        loc = f"{s.source}" + (f" — صفحة {s.page}" if s.page else "") + (f" — {s.section}" if s.section else "")
        blocks.append(f"[{s.index}] ({loc})\n{s.text}")
    return "\n\n---\n\n".join(blocks)


def build_messages(question: str, sources: list[Source], history: list[dict] | None = None, lang: str = "ar") -> list[dict]:
    msgs = [{"role": "system", "content": system_prompt(lang)}]
    for m in (history or [])[-6:]:
        if m.get("role") in ("user", "assistant"):
            msgs.append({"role": m["role"], "content": m["content"][:1500]})
    content = USER_TEMPLATE.format(context=build_context(sources), question=question)
    if lang == "en":
        content += "\n\nAnswer in English."  # explicit, last thing the model reads: sources are Arabic
    msgs.append({"role": "user", "content": content})
    return msgs


def _is_refusal(text: str) -> bool:
    d = get_domain()
    return d.refusal_message[:25] in text or d.refusal_message_en[:25] in text


def extract_citations(text: str, n_sources: int) -> list[int]:
    return sorted({int(x) for x in _CITATION.findall(text) if 1 <= int(x) <= n_sources})


def _should_refuse(r: RetrievalResult) -> bool:
    return not r.hits or not r.in_scope or not r.confident


def answer(question: str, history: list[dict] | None = None, filters: dict | None = None, use_rewrite: bool | None = None) -> Answer:
    t0 = time.perf_counter()
    r = retrieve(question, history, filters, use_rewrite=use_rewrite)
    sources = _to_sources(r.hits)
    d = get_domain()
    lang = d.answer_lang(question)
    if _should_refuse(r):
        return Answer(
            answer=d.refusal_for(lang),
            sources=sources,
            cited=[],
            refused=True,
            rewritten_query=r.rewritten,
            timings_ms={**r.timings_ms, "total": int((time.perf_counter() - t0) * 1000)},
        )
    res = get_llm().complete(build_messages(question, sources, history, lang))
    cited = extract_citations(res.text, len(sources))
    refused = _is_refusal(res.text) or not cited
    return Answer(
        answer=res.text,
        sources=sources,
        cited=cited,
        refused=refused and not cited,
        rewritten_query=r.rewritten,
        model=res.model,
        prompt_tokens=res.prompt_tokens,
        completion_tokens=res.completion_tokens,
        timings_ms={**r.timings_ms, "llm": res.latency_ms, "total": int((time.perf_counter() - t0) * 1000)},
    )


def answer_stream(question: str, history: list[dict] | None = None, filters: dict | None = None) -> Iterator[dict]:
    t0 = time.perf_counter()
    r = retrieve(question, history, filters)
    sources = _to_sources(r.hits)
    d = get_domain()
    lang = d.answer_lang(question)
    yield {"type": "sources", "sources": [asdict(s) for s in sources], "rewritten_query": r.rewritten}

    if _should_refuse(r):
        yield {"type": "token", "text": d.refusal_for(lang)}
        yield {
            "type": "done",
            "answer": d.refusal_for(lang),
            "cited": [],
            "refused": True,
            "model": "",
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "timings_ms": {**r.timings_ms, "total": int((time.perf_counter() - t0) * 1000)},
        }
        return

    full = []
    usage: dict = {}
    for tok, u in get_llm().stream(build_messages(question, sources, history, lang)):
        if tok:
            full.append(tok)
            yield {"type": "token", "text": tok}
        if u:
            usage = u
    text = "".join(full)
    cited = extract_citations(text, len(sources))
    if d.disclaimer_for(lang):
        yield {"type": "token", "text": f"\n\n> {d.disclaimer_for(lang)}"}
    yield {
        "type": "done",
        "answer": text,
        "cited": cited,
        "refused": not cited and _is_refusal(text),
        "model": usage.get("model", get_settings().llm_model),
        "prompt_tokens": usage.get("prompt_tokens", 0),
        "completion_tokens": usage.get("completion_tokens", 0),
        "timings_ms": {**r.timings_ms, "llm": usage.get("latency_ms", 0), "total": int((time.perf_counter() - t0) * 1000)},
    }
