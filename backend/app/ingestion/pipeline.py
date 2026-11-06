"""File -> pages -> chunks -> embeddings -> Chroma (+ BM25 rebuild)."""

from __future__ import annotations

import logging
import time
from pathlib import Path

from app.config import get_settings
from app.retrieval.vectorstore import get_store

from .chunker import chunk_pages
from .loaders import SUPPORTED_EXTENSIONS, load_document
from .translate import translate_pages

log = logging.getLogger(__name__)


def ingest_file(path: Path, extra_metadata: dict | None = None, replace: bool = True) -> dict:
    s = get_settings()
    store = get_store()
    t0 = time.perf_counter()
    pages = load_document(path)
    if s.translate_docs_to:
        pages = translate_pages(pages, s.translate_docs_to)
    chunks = chunk_pages(pages, s.chunk_size, s.chunk_overlap, extra_metadata)
    if replace:
        store.delete_source(path.name)
    n = store.add_chunks(chunks)
    stats = {
        "source": path.name,
        "pages": len(pages),
        "chunks": n,
        "tables": sum(1 for c in chunks if c.metadata.get("is_table")),
        "translated_pages": sum(1 for p in pages if p.metadata.get("translated")),
        "seconds": round(time.perf_counter() - t0, 2),
    }
    log.info("Ingested %s", stats)
    return stats


def _category_from_path(path: Path, root: Path) -> str:
    rel = path.relative_to(root)
    return rel.parts[0] if len(rel.parts) > 1 else ""


def ingest_directory(root: Path | None = None) -> list[dict]:
    """Ingest every supported file. Sub-folder name becomes the `category` metadata,
    e.g. data/raw/policies/leave.pdf -> category="policies"."""
    root = root or get_settings().raw_docs_dir
    results = []
    for p in sorted(root.rglob("*")):
        if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS and not p.name.startswith("."):
            cat = _category_from_path(p, root)
            try:
                results.append(ingest_file(p, {"category": cat} if cat else None))
            except Exception as exc:
                log.exception("Failed to ingest %s", p)
                results.append({"source": p.name, "error": str(exc)})
    return results
