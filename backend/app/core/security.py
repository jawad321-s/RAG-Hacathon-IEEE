"""Auth (JWT + bcrypt), role checks, rate limiting and PII redaction."""

from __future__ import annotations

import re
import time
from collections import defaultdict, deque
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.config import get_settings

from .db import User, get_db

_bearer = HTTPBearer(auto_error=False)


# ------------------------------------------------------------------ passwords
def hash_password(pw: str) -> str:
    return bcrypt.hashpw(pw.encode()[:72], bcrypt.gensalt()).decode()


def verify_password(pw: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(pw.encode()[:72], hashed.encode())
    except ValueError:
        return False


# ----------------------------------------------------------------------- JWT
def create_token(user: User) -> str:
    s = get_settings()
    payload = {
        "sub": str(user.id),
        "role": user.role,
        "exp": datetime.now(UTC) + timedelta(minutes=s.jwt_expire_minutes),
    }
    return jwt.encode(payload, s.jwt_secret, algorithm="HS256")


def _decode(token: str) -> dict:
    return jwt.decode(token, get_settings().jwt_secret, algorithms=["HS256"])


def current_user_optional(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer), db: Session = Depends(get_db)
) -> User | None:
    if not creds:
        return None
    try:
        data = _decode(creds.credentials)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    return db.get(User, int(data["sub"]))


def current_user(user: User | None = Depends(current_user_optional)) -> User:
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login required")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin only")
    return user


def chat_user(user: User | None = Depends(current_user_optional)) -> User | None:
    if user is None and not get_settings().allow_anonymous_chat:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Login required")
    return user


# ---------------------------------------------------------------- rate limit
_hits: dict[str, deque] = defaultdict(deque)


def rate_limit(request: Request) -> None:
    """Simple in-memory sliding window per client IP (fine for a single instance)."""
    limit = get_settings().rate_limit_per_minute
    key = request.client.host if request.client else "anon"
    now = time.time()
    q = _hits[key]
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many requests, slow down.")
    q.append(now)


# ------------------------------------------------------------- PII redaction
_PII_PATTERNS = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "[EMAIL]"),
    (re.compile(r"(?:\+?\d[\d\s-]{8,}\d)"), "[PHONE]"),
    (re.compile(r"\b\d{9,10}\b"), "[ID]"),
]


def redact_pii(text: str) -> str:
    """Applied before storing questions in analytics logs (privacy by design)."""
    for pat, repl in _PII_PATTERNS:
        text = pat.sub(repl, text)
    return text
