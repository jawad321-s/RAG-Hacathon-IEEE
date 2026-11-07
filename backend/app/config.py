"""Central configuration.

Two sources:
1. Environment variables / `.env`  -> secrets & infra (API keys, paths, model names).
2. `config/domain.yaml`             -> everything about the *problem* (name, persona,
   system prompt, refusal message, sample questions). Change this file on hackathon
   day instead of touching code.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import AliasChoices, BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_DIR = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(REPO_DIR / ".env", BACKEND_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App ---------------------------------------------------------------
    app_env: Literal["dev", "prod", "test"] = "dev"
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    domain_config_path: Path = BACKEND_DIR / "config" / "domain.yaml"

    # --- Storage -----------------------------------------------------------
    data_dir: Path = BACKEND_DIR / "data"
    chroma_dir: Path = BACKEND_DIR / "data" / "chroma"
    raw_docs_dir: Path = BACKEND_DIR / "data" / "raw"
    uploads_dir: Path = BACKEND_DIR / "data" / "uploads"
    sqlite_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'app.db'}"
    collection_name: str = "knowledge_base"
    max_upload_mb: int = 25

    # --- LLM (any OpenAI-compatible API) ------------------------------------
    # COMPETITION RULE: only FREE APIs are allowed. Default = Google Gemini free tier
    # (aistudio.google.com/apikey, OpenAI-compatible endpoint). Env names LLM_* or the
    # older OPENROUTER_* both work.
    openrouter_api_key: str = Field("", validation_alias=AliasChoices("LLM_API_KEY", "OPENROUTER_API_KEY"))
    openrouter_base_url: str = Field(
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        validation_alias=AliasChoices("LLM_BASE_URL", "OPENROUTER_BASE_URL"),
    )
    llm_model: str = "gemini-3.5-flash"
    # Comma separated fallbacks on the SAME provider, tried in order if the main model fails
    # (on Gemini's free tier each model has its own rate limit, so this also spreads the load).
    llm_fallback_models: str = "gemini-3.5-flash-lite,gemini-3.6-flash"
    # Refuse any model that is not free (e.g. OpenRouter models without the ":free" suffix).
    free_only: bool = True
    # Optional separate provider for the *utility* calls (query rewrite, translation, eval judge).
    # Lets the answering model run on a free API while helper calls use a paid one (or vice versa).
    # Empty = same provider as the answering model.
    utility_base_url: str = ""
    utility_api_key: str = ""
    # Fast model for query rewriting, translation & LLM-as-judge evaluation.
    llm_utility_model: str = "gemini-3.5-flash-lite"
    llm_temperature: float = 0.1
    # Seconds before giving up on a model and trying the next fallback (free tiers can stall).
    llm_timeout: float = 20
    # Thinking budget for reasoning models (e.g. Gemini 3.x): "low" = fast answers.
    # Empty = don't send the parameter. Dropped automatically if a provider rejects it.
    llm_reasoning_effort: str = "low"
    llm_max_tokens: int = 1024
    # USD per 1M tokens for cost tracking. 0 on free tiers; put the PAID list price here
    # only when modelling costs for the business plan (make cost).
    llm_price_input_per_m: float = 0.0
    llm_price_output_per_m: float = 0.0
    # Offline safety net: extractive answers (no LLM) if the internet dies during the demo.
    llm_mock: bool = False
    app_public_url: str = "http://localhost:3000"
    app_title: str = "RAG Hackathon"

    # --- Arabic-first knowledge base ---
    # "ar" = translate non-Arabic pages to Arabic at ingestion (cached). "" = keep original language.
    translate_docs_to: str = ""
    translation_model: str = ""  # empty = LLM_UTILITY_MODEL
    translation_workers: int = 6

    # --- Embeddings --------------------------------------------------------
    # fastembed  = local ONNX model (free, private, offline after first download)
    # openrouter = remote embeddings through OpenRouter's OpenAI-compatible API
    # hash       = deterministic fake embeddings for tests only
    embedding_provider: Literal["fastembed", "openrouter", "hash"] = "fastembed"
    embedding_model: str = "intfloat/multilingual-e5-large"
    embedding_batch_size: int = 32
    # Where ONNX models are cached (kept out of /tmp so they survive reboots)
    models_cache_dir: Path = BACKEND_DIR / "data" / "models"

    # --- Chunking ----------------------------------------------------------
    chunk_size: int = 900  # characters
    chunk_overlap: int = 150  # characters

    # --- Retrieval ---------------------------------------------------------
    top_k: int = 5  # chunks sent to the LLM
    candidate_k: int = 20  # candidates per retriever before fusion / rerank
    hybrid_alpha: float = 0.5  # weight of dense vs BM25 in RRF (0..1)
    rrf_k: int = 60
    use_reranker: bool = True
    reranker_model: str = "jinaai/jina-reranker-v2-base-multilingual"
    use_query_rewrite: bool = True  # dialect -> MSA + keyword expansion via LLM
    # If the best reranker / fused score is below this, refuse instead of guessing.
    min_relevance_score: float = 0.15

    # --- Auth --------------------------------------------------------------
    jwt_secret: str = "change-me-in-.env-please-use-a-long-random-string"
    jwt_expire_minutes: int = 60 * 24
    admin_email: str = "admin@example.com"
    admin_password: str = "admin12345"
    allow_anonymous_chat: bool = True

    # --- Rate limit --------------------------------------------------------
    rate_limit_per_minute: int = 30

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    def cost_usd(self, prompt_tokens: int, completion_tokens: int) -> float:
        return (prompt_tokens * self.llm_price_input_per_m + completion_tokens * self.llm_price_output_per_m) / 1_000_000

    def paid_model_reason(self, model: str, base_url: str) -> str | None:
        """Returns why a model is NOT allowed under free_only, or None if it is allowed."""
        if not self.free_only:
            return None
        if "openrouter.ai" in base_url and not model.endswith(":free"):
            return f"'{model}' is a paid OpenRouter model (free ones end with ':free')"
        return None

    @property
    def fallback_models(self) -> list[str]:
        return [m.strip() for m in self.llm_fallback_models.split(",") if m.strip()]


class DomainConfig(BaseModel):
    """Problem-specific config loaded from YAML."""

    product_name: str = "Assistant"
    tagline: str = ""
    language: str = "ar"
    # Language of every answer: "ar" = always Arabic (even for English sources/questions),
    # "auto" = same language as the question.
    answer_language: str = "auto"
    audience: str = ""
    problem_statement: str = ""
    persona: str = ""
    system_prompt_extra: str = ""
    refusal_message: str = "لا تتوفر لدي معلومات كافية في المصادر للإجابة عن هذا السؤال."
    disclaimer: str = ""
    # English versions, used when answer_language is "auto" and the question is in English.
    refusal_message_en: str = "Sorry, I couldn't find enough information in the available sources to answer this question."
    disclaimer_en: str = ""

    def answer_lang(self, question: str) -> str:
        """'ar' or 'en' for this question (answer_language 'ar' forces Arabic)."""
        from app.ingestion.arabic import is_arabic

        if self.answer_language == "ar":
            return "ar"
        letters = [c for c in question if c.isalpha()]
        return "ar" if not letters or is_arabic(question, threshold=0.3) else "en"

    def refusal_for(self, lang: str) -> str:
        return self.refusal_message_en if lang == "en" else self.refusal_message

    def disclaimer_for(self, lang: str) -> str:
        return self.disclaimer_en if lang == "en" else self.disclaimer
    escalation_message: str = ""
    sample_questions: list[str] = Field(default_factory=list)
    out_of_scope_examples: list[str] = Field(default_factory=list)
    metadata_filters: list[str] = Field(default_factory=list)
    # Role-based access control on retrieval. role -> allowed `category` values.
    # Missing role / null = no restriction. Example: {"anonymous": ["public"], "user": ["public"], "admin": null}
    role_categories: dict[str, list[str] | None] = Field(default_factory=dict)

    def allowed_categories(self, role: str | None) -> list[str] | None:
        return self.role_categories.get(role or "anonymous") if self.role_categories else None


@lru_cache
def get_settings() -> Settings:
    s = Settings()
    for d in (s.data_dir, s.chroma_dir, s.raw_docs_dir, s.uploads_dir):
        d.mkdir(parents=True, exist_ok=True)
    return s


@lru_cache
def get_domain() -> DomainConfig:
    path = get_settings().domain_config_path
    if path.exists():
        return DomainConfig(**(yaml.safe_load(path.read_text(encoding="utf-8")) or {}))
    return DomainConfig()
