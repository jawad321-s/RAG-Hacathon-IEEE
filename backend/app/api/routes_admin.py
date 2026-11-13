"""Analytics + evaluation endpoints for the admin dashboard."""

from __future__ import annotations

import json
from collections import Counter
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from fastapi.concurrency import run_in_threadpool
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import get_domain, get_settings
from app.core.db import Conversation, Feedback, QueryLog, User, get_db
from app.core.security import require_admin
from app.evaluation.runner import run_eval
from app.retrieval.vectorstore import get_store

router = APIRouter(prefix="/api", tags=["admin"])


@router.get("/config/public")
def public_config():
    """Non-secret config the frontend needs (product name, sample questions...)."""
    d = get_domain()
    s = get_settings()
    return {
        "product_name": d.product_name,
        "tagline": d.tagline,
        "audience": d.audience,
        "problem_statement": d.problem_statement,
        "language": d.language,
        "sample_questions": d.sample_questions,
        "disclaimer": d.disclaimer,
        "metadata_filters": d.metadata_filters,
        "allow_anonymous_chat": s.allow_anonymous_chat,
    }


@router.get("/analytics")
def analytics(days: int = 14, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    since = datetime.now(UTC) - timedelta(days=days)
    logs = list(db.scalars(select(QueryLog).where(QueryLog.created_at >= since)))
    by_day: dict[str, dict] = {}
    for q in logs:
        d = q.created_at.date().isoformat()
        e = by_day.setdefault(d, {"date": d, "questions": 0, "refused": 0, "cost_usd": 0.0})
        e["questions"] += 1
        e["refused"] += int(q.refused)
        e["cost_usd"] += q.cost_usd
    top_sources = Counter(q.top_source for q in logs if q.top_source).most_common(8)
    fb = list(db.scalars(select(Feedback).where(Feedback.created_at >= since)))
    total = len(logs)
    latencies = sorted(q.latency_ms for q in logs)
    return {
        "kpis": {
            "questions": total,
            "users": db.scalar(select(func.count(User.id))) or 0,
            "conversations": db.scalar(select(func.count(Conversation.id))) or 0,
            "refusal_rate": round(sum(q.refused for q in logs) / total, 3) if total else 0,
            "avg_latency_ms": int(sum(latencies) / total) if total else 0,
            "p95_latency_ms": latencies[int(0.95 * (total - 1))] if total else 0,
            "total_cost_usd": round(sum(q.cost_usd for q in logs), 4),
            "cost_per_answer_usd": round(sum(q.cost_usd for q in logs) / total, 5) if total else 0,
            "satisfaction": round(sum(1 for f in fb if f.rating > 0) / len(fb), 3) if fb else None,
            "chunks_indexed": get_store().count(),
        },
        "by_day": sorted(by_day.values(), key=lambda x: x["date"]),
        "top_sources": [{"source": s, "count": c} for s, c in top_sources],
        "recent_questions": [
            {"question": q.question, "refused": q.refused, "score": round(q.top_score, 3), "at": q.created_at.isoformat()}
            for q in sorted(logs, key=lambda x: x.created_at, reverse=True)[:15]
        ],
        "unanswered": [q.question for q in logs if q.refused][-15:],
    }


@router.get("/eval/latest")
def eval_latest(_: User = Depends(require_admin)):
    p = get_settings().data_dir / "eval" / "results" / "latest.json"
    if not p.exists():
        raise HTTPException(404, "No evaluation run yet. Run `make eval` or POST /api/eval/run")
    return json.loads(p.read_text(encoding="utf-8"))


@router.post("/eval/run")
async def eval_run(with_generation: bool = True, _: User = Depends(require_admin)):
    return await run_in_threadpool(run_eval, None, with_generation)
