from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class ChatRequest(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    conversation_id: int | None = None
    filters: dict[str, str] | None = None
    stream: bool = True


class FeedbackRequest(BaseModel):
    message_id: int
    rating: int = Field(ge=-1, le=1)
    comment: str = ""


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    name: str = ""


class SearchRequest(BaseModel):
    query: str
    top_k: int = 5
    filters: dict[str, str] | None = None
    rewrite: bool = False
