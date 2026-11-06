"""FastAPI entrypoint.  Run:  uvicorn app.main:app --reload --port 8000"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import select

from app.api import routes_admin, routes_auth, routes_chat, routes_docs
from app.config import get_domain, get_settings
from app.core.db import User, init_db, new_session
from app.core.security import hash_password
from app.generation.llm import get_llm
from app.retrieval.vectorstore import get_store

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log = logging.getLogger("app")


def _ensure_admin() -> None:
    s = get_settings()
    db = new_session()
    try:
        if not db.scalar(select(User).where(User.email == s.admin_email.lower())):
            db.add(User(email=s.admin_email.lower(), name="Admin", password_hash=hash_password(s.admin_password), role="admin"))
            db.commit()
            log.info("Created admin user %s", s.admin_email)
    finally:
        db.close()


@asynccontextmanager
async def lifespan(_: FastAPI):
    s = get_settings()
    if s.jwt_secret.startswith("change-me") and s.app_env == "prod":
        raise RuntimeError("Set JWT_SECRET in .env before running in prod")
    init_db()
    _ensure_admin()
    store = get_store()  # warm up embeddings + BM25
    log.info("Knowledge base ready: %d chunks", store.count())
    if s.use_reranker:
        from app.retrieval.reranker import get_reranker

        get_reranker()
    if not get_llm().configured:
        log.warning("OPENROUTER_API_KEY missing — chat will fail until you set it in .env")
    yield


app = FastAPI(title=f"{get_domain().product_name} — RAG API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

for r in (routes_auth.router, routes_chat.router, routes_docs.router, routes_admin.router):
    app.include_router(r)


@app.get("/api/health")
def health():
    s = get_settings()
    return {
        "status": "ok",
        "chunks": get_store().count(),
        "llm_configured": get_llm().configured,
        "llm_model": s.llm_model,
        "embedding_model": s.embedding_model,
        "reranker": s.reranker_model if s.use_reranker else None,
    }
