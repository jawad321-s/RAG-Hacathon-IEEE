from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import User, get_db
from app.core.security import create_token, current_user, hash_password, verify_password

from .schemas import LoginRequest, RegisterRequest

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _user_out(u: User) -> dict:
    return {"id": u.id, "email": u.email, "name": u.name, "role": u.role}


@router.post("/register")
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    if db.scalar(select(User).where(User.email == body.email.lower())):
        raise HTTPException(400, "Email already registered")
    u = User(email=body.email.lower(), name=body.name, password_hash=hash_password(body.password), role="user")
    db.add(u)
    db.commit()
    return {"token": create_token(u), "user": _user_out(u)}


@router.post("/login")
def login(body: LoginRequest, db: Session = Depends(get_db)):
    u = db.scalar(select(User).where(User.email == body.email.lower()))
    if not u or not verify_password(body.password, u.password_hash):
        raise HTTPException(401, "Wrong email or password")
    return {"token": create_token(u), "user": _user_out(u)}


@router.get("/me")
def me(user: User = Depends(current_user)):
    return _user_out(user)
