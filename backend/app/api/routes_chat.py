"""Chat endpoints: streaming (SSE) + non-streaming, conversation history, feedback."""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_domain, get_settings
from app.core.db import Conversation, Feedback, Message, QueryLog, User, get_db, new_session
from app.core.security import chat_user, current_user, rate_limit, redact_pii
from app.generation.generator import answer, answer_stream
from app.generation.llm import LLMError

from .schemas import ChatRequest, FeedbackRequest

log = logging.getLogger(__name__)
router = APIRouter(prefix="/api", tags=["chat"])


def _get_or_create_conversation(db: Session, conv_id: int | None, user: User | None, question: str) -> Conversation:
    if conv_id:
        conv = db.get(Conversation, conv_id)
        if not conv or (conv.user_id and (not user or conv.user_id != user.id)):
            raise HTTPException(404, "Conversation not found")
        return conv
    conv = Conversation(user_id=user.id if user else None, title=question[:60])
    db.add(conv)
    db.commit()
    return conv


def _scoped_filters(user: User | None, filters: dict | None) -> dict | None:
    """Apply RBAC from domain.yaml: users only retrieve chunks from categories they may see.
    Filtering happens inside the vector search, so forbidden text never reaches the LLM."""
    allowed = get_domain().allowed_categories(user.role if user else None)
    if allowed is None:
        return filters
    f = dict(filters or {})
    wanted = f.get("category")
    f["category"] = [wanted] if wanted in allowed else allowed
    return f


def _history(conv: Conversation) -> list[dict]:
    return [{"role": m.role, "content": m.content} for m in conv.messages][-6:]


def _log(user: User | None, conv_id: int, msg_id: int, question: str, done: dict, sources: list[dict]) -> None:
    s = get_settings()
    db = new_session()
    try:
        db.add(
            QueryLog(
                user_id=user.id if user else None,
                conversation_id=conv_id,
                message_id=msg_id,
                question=redact_pii(question),
                rewritten=redact_pii(done.get("rewritten_query", "")),
                refused=bool(done.get("refused")),
                n_sources=len(sources),
                top_score=float(sources[0]["score"]) if sources else 0.0,
                top_source=sources[0]["source"] if sources else "",
                model=done.get("model", ""),
                prompt_tokens=done.get("prompt_tokens", 0),
                completion_tokens=done.get("completion_tokens", 0),
                cost_usd=s.cost_usd(done.get("prompt_tokens", 0), done.get("completion_tokens", 0)),
                latency_ms=done.get("timings_ms", {}).get("total", 0),
            )
        )
        db.commit()
    finally:
        db.close()


@router.post("/chat", dependencies=[Depends(rate_limit)])
def chat(body: ChatRequest, user: User | None = Depends(chat_user), db: Session = Depends(get_db)):
    conv = _get_or_create_conversation(db, body.conversation_id, user, body.question)
    history = _history(conv)
    filters = _scoped_filters(user, body.filters)
    db.add(Message(conversation_id=conv.id, role="user", content=body.question))
    db.commit()

    if not body.stream:
        try:
            a = answer(body.question, history, filters)
        except LLMError as exc:
            raise HTTPException(503, str(exc))
        sources = [s.__dict__ for s in a.sources]
        msg = Message(conversation_id=conv.id, role="assistant", content=a.answer, sources=sources)
        db.add(msg)
        db.commit()
        _log(user, conv.id, msg.id, body.question, {**a.to_dict(), "rewritten_query": a.rewritten_query}, sources)
        return {**a.to_dict(), "conversation_id": conv.id, "message_id": msg.id}

    conv_id = conv.id

    def event_stream():
        sources: list[dict] = []
        rewritten = ""
        try:
            for ev in answer_stream(body.question, history, filters):
                if ev["type"] == "sources":
                    sources, rewritten = ev["sources"], ev.get("rewritten_query", "")
                    ev = {**ev, "conversation_id": conv_id}
                if ev["type"] == "done":
                    s2 = new_session()
                    try:
                        msg = Message(conversation_id=conv_id, role="assistant", content=ev["answer"], sources=sources)
                        s2.add(msg)
                        s2.commit()
                        ev["message_id"] = msg.id
                    finally:
                        s2.close()
                    _log(user, conv_id, ev["message_id"], body.question, {**ev, "rewritten_query": rewritten}, sources)
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except Exception as exc:
            log.exception("chat stream failed")
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)}, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/conversations")
def list_conversations(user: User = Depends(current_user), db: Session = Depends(get_db)):
    convs = db.scalars(select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.updated_at.desc()).limit(50))
    return [{"id": c.id, "title": c.title, "updated_at": c.updated_at.isoformat()} for c in convs]


@router.get("/conversations/{conv_id}")
def get_conversation(conv_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = db.get(Conversation, conv_id)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Not found")
    return {
        "id": c.id,
        "title": c.title,
        "messages": [{"id": m.id, "role": m.role, "content": m.content, "sources": m.sources or []} for m in c.messages],
    }


@router.delete("/conversations/{conv_id}")
def delete_conversation(conv_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    c = db.get(Conversation, conv_id)
    if not c or c.user_id != user.id:
        raise HTTPException(404, "Not found")
    db.delete(c)
    db.commit()
    return {"ok": True}


@router.post("/feedback")
def feedback(body: FeedbackRequest, db: Session = Depends(get_db)):
    db.add(Feedback(message_id=body.message_id, rating=body.rating, comment=body.comment[:1000]))
    db.commit()
    return {"ok": True}
