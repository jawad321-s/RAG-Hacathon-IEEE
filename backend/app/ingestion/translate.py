"""Arabic-first knowledge base: translate non-Arabic pages to Arabic at ingestion time.

Why at ingestion (not at answer time)?
- Every downstream step then works in Arabic: BM25 matches Arabic words, the reranker
  compares Arabic with Arabic, and the sources panel shows Arabic text to the user.
- It is paid once. Translations are cached on disk (data/translations/), keyed by the
  page text + model, so `make reset` or changing CHUNK_SIZE does not translate again.
- We translate whole pages BEFORE chunking, so the cache survives chunk-size experiments.

Honesty: every translated chunk keeps `translated=True`, `source_lang` and the
`original_text` of its page, so the UI can show "machine-translated" + the original.
"""

from __future__ import annotations

import hashlib
import json
import logging
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

from app.config import get_settings
from app.generation.llm import get_llm

from .arabic import clean_text, is_arabic
from .loaders import PageContent

log = logging.getLogger(__name__)

TRANSLATE_PROMPT = """Translate the following document page into Modern Standard Arabic (فصحى واضحة).
Rules:
- Translate faithfully. Do not summarise, add, explain or omit anything.
- Keep numbers, dates, units, doses, prices, codes, article/section numbers, URLs and emails exactly as written.
- Keep proper names; for technical terms write the Arabic term followed by the original in parentheses the first time, e.g. "الري بالتنقيط (drip irrigation)".
- Keep Markdown structure exactly: headings (#), lists, and tables (| a | b |) with the same number of rows and columns.
- Keep the line "[جدول / Table]" unchanged.
- Output ONLY the Arabic translation.

PAGE:
{text}"""


def _cache_path(digest: str):
    d = get_settings().data_dir / "translations"
    d.mkdir(parents=True, exist_ok=True)
    return d / f"{digest}.json"


def _translate_text(text: str, target: str, model: str) -> str:
    digest = hashlib.sha1(f"{model}|{target}|{text}".encode()).hexdigest()
    path = _cache_path(digest)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))["text"]
    res = get_llm().complete(
        [{"role": "user", "content": TRANSLATE_PROMPT.format(text=text)}],
        model=model,
        temperature=0,
        max_tokens=min(8000, 300 + len(text)),  # Arabic output ~ same char count as English input
    )
    out = clean_text(res.text)
    path.write_text(json.dumps({"text": out, "model": res.model}, ensure_ascii=False), encoding="utf-8")
    return out


def needs_translation(page: PageContent, target: str) -> bool:
    return target == "ar" and not is_arabic(page.text)


def translate_pages(pages: list[PageContent], target: str = "ar") -> list[PageContent]:
    """Returns pages in `target` language. Arabic pages pass through untouched.
    If the LLM is unavailable, the original page is kept (multilingual embeddings still work)."""
    s = get_settings()
    llm = get_llm()
    todo = [i for i, p in enumerate(pages) if needs_translation(p, target)]
    if not todo:
        return pages
    if not llm.configured or s.llm_mock:
        log.warning("Translation skipped (no LLM). %d non-Arabic pages kept in original language.", len(todo))
        return pages
    model = s.translation_model or s.llm_utility_model
    log.info("Translating %d/%d pages to %s with %s ...", len(todo), len(pages), target, model)

    def work(i: int) -> tuple[int, str | None]:
        try:
            return i, _translate_text(pages[i].text, target, model)
        except Exception as exc:  # one bad page must not kill the ingest
            log.error("Translation failed for %s p%s: %s", pages[i].source, pages[i].page, exc)
            return i, None

    out = list(pages)
    with ThreadPoolExecutor(max_workers=s.translation_workers) as pool:
        for i, translated in pool.map(work, todo):
            if not translated:
                continue
            p = pages[i]
            out[i] = replace(
                p,
                text=translated,
                metadata={**p.metadata, "translated": True, "source_lang": "en", "original_text": p.text[:6000]},
            )
    return out
