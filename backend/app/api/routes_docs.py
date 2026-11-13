"""Knowledge base management (admin): upload, list, delete, re-index, debug search."""

from __future__ import annotations

import re
from dataclasses import asdict

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_domain, get_settings
from app.core.db import Document, User, get_db
from app.core.security import require_admin
from app.ingestion.loaders import SUPPORTED_EXTENSIONS
from app.ingestion.pipeline import ingest_directory, ingest_file
from app.retrieval.retriever import retrieve
from app.retrieval.vectorstore import get_store

from .schemas import SearchRequest

router = APIRouter(prefix="/api/documents", tags=["documents"])


def _safe_name(name: str) -> str:
    name = name.replace("\\", "/").split("/")[-1]
    name = re.sub(r"[^\w؀-ۿ.\- ]", "_", name).strip()
    if not name or name.startswith("."):
        raise HTTPException(400, "Invalid file name")
    return name


@router.get("")
def list_documents():
    store = get_store()
    return {"total_chunks": store.count(), "documents": store.list_sources()}


@router.get("/facets")
def facets():
    store = get_store()
    return {key: store.facet_values(key) for key in get_domain().metadata_filters}


@router.post("/upload")
async def upload(
    file: UploadFile = File(...),
    category: str = Form(""),
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    s = get_settings()
    name = _safe_name(file.filename or "")
    ext = "." + name.rsplit(".", 1)[-1].lower() if "." in name else ""
    if ext not in SUPPORTED_EXTENSIONS:
        raise HTTPException(400, f"Unsupported type {ext}. Allowed: {sorted(SUPPORTED_EXTENSIONS)}")
    data = await file.read()
    if len(data) > s.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"File larger than {s.max_upload_mb}MB")
    dest = s.uploads_dir / name
    dest.write_bytes(data)
    meta = {"category": category} if category else None
    stats = await run_in_threadpool(ingest_file, dest, meta)
    doc = db.scalar(select(Document).where(Document.source == name)) or Document(source=name)
    doc.category, doc.pages, doc.chunks, doc.uploaded_by = category, stats["pages"], stats["chunks"], admin.id
    db.add(doc)
    db.commit()
    return stats


@router.delete("/{source}")
def delete(source: str, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    get_store().delete_source(source)
    doc = db.scalar(select(Document).where(Document.source == source))
    if doc:
        db.delete(doc)
        db.commit()
    return {"ok": True}


@router.post("/reindex")
async def reindex(_: User = Depends(require_admin)):
    """Wipe the collection and re-ingest data/raw + data/uploads."""
    s = get_settings()
    get_store().reset()
    res = await run_in_threadpool(ingest_directory, s.raw_docs_dir)
    res += await run_in_threadpool(ingest_directory, s.uploads_dir)
    return {"results": res, "total_chunks": get_store().count()}


@router.post("/search")
def search(body: SearchRequest, _: User = Depends(require_admin)):
    """Debug endpoint: see exactly what the retriever returns (great for the demo)."""
    r = retrieve(body.query, filters=body.filters, top_k=body.top_k, use_rewrite=body.rewrite)
    return {
        "query": r.query,
        "rewritten": r.rewritten,
        "keywords": r.keywords,
        "confident": r.confident,
        "timings_ms": r.timings_ms,
        "hits": [asdict(h) for h in r.hits],
    }
