"""LLM client for any OpenAI-compatible API (default: Gemini free tier) with fallback, usage tracking and a FREE_ONLY guard."""

from __future__ import annotations

import logging
import re
import time
from collections.abc import Iterator
from dataclasses import dataclass, field
from functools import lru_cache

from openai import OpenAI

from app.config import get_settings

log = logging.getLogger(__name__)


@dataclass
class LLMResult:
    text: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: int = 0
    extra: dict = field(default_factory=dict)


class LLMError(RuntimeError):
    pass


class LLM:
    def __init__(self) -> None:
        s = get_settings()
        self.settings = s
        self.client = OpenAI(
            api_key=s.openrouter_api_key or "missing-key",
            base_url=s.openrouter_base_url,
            default_headers={"HTTP-Referer": s.app_public_url, "X-Title": s.app_title},
            timeout=60,
            max_retries=1,
        )
        self.separate_utility = bool(s.utility_base_url or s.utility_api_key)
        self.utility_client = (
            OpenAI(
                api_key=s.utility_api_key or s.openrouter_api_key or "missing-key",
                base_url=s.utility_base_url or s.openrouter_base_url,
                default_headers={"HTTP-Referer": s.app_public_url, "X-Title": s.app_title},
                timeout=60,
                max_retries=1,
            )
            if self.separate_utility
            else self.client
        )

    @property
    def configured(self) -> bool:
        return self.settings.llm_mock or bool(self.settings.openrouter_api_key)

    @staticmethod
    def _mock_answer(messages: list[dict]) -> str:
        """Extractive fallback: quote the first sentences of the top sources with citations."""
        user = messages[-1]["content"]
        if "<sources>" not in user:
            return '{"standalone": "", "keywords": [], "in_scope": true}'
        body = user.split("<sources>", 1)[1].split("</sources>", 1)[0]
        parts = []
        for block in body.split("\n\n---\n\n")[:2]:
            head, _, text = block.strip().partition("\n")
            idx = head[1 : head.find("]")]
            if "[جدول / Table]" in text:  # keep tables as real markdown tables
                rows = [ln for ln in text.splitlines() if ln.startswith("|")]
                parts.append("\n".join(rows) + f"\n\n[{idx}]")
                continue
            sentence = re.split(r"(?<=[.!؟?])\s", text.strip(), maxsplit=1)[0][:400]
            parts.append(f"- {sentence} [{idx}]")
        return "وضع عدم الاتصال (مقتطفات من المصادر):\n\n" + "\n\n".join(parts)

    def _models(self, model: str | None) -> list[str]:
        primary = model or self.settings.llm_model
        return [primary] + [m for m in self.settings.fallback_models if m != primary]

    def _extras(self) -> dict:
        """Optional request params. reasoning_effort keeps "thinking" models (Gemini 3.x, etc.)
        from spending the whole token budget and a minute of latency on hidden reasoning."""
        e = self.settings.llm_reasoning_effort.strip()
        return {"reasoning_effort": e} if e else {}

    @staticmethod
    def _create(client, base: dict, extras: dict):
        """Call the API; if the provider rejects optional params, drop them one by one and retry."""
        keys = list(extras)
        while True:
            try:
                return client.chat.completions.create(**base, **{k: extras[k] for k in keys})
            except Exception as exc:
                status = getattr(exc, "status_code", None)
                if not keys or status not in (400, 422):  # only retry on "bad parameter" errors
                    raise
                log.info("Provider rejected %s; retrying without it", keys[-1])
                keys.pop()

    def complete(
        self,
        messages: list[dict],
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        json_mode: bool = False,
        utility: bool = False,
    ) -> LLMResult:
        """utility=True routes helper calls (rewrite/translate/judge) to the utility provider."""
        if not self.configured:
            raise LLMError("LLM_API_KEY is not set. Copy .env.example to .env and add your free Gemini key.")
        if self.settings.llm_mock:
            return LLMResult(text=self._mock_answer(messages), model="offline-extractive")
        client = self.utility_client if utility else self.client
        models = [model or self.settings.llm_utility_model] if (utility and self.separate_utility) else self._models(model)
        base_url = str(getattr(client, "base_url", ""))
        last_exc: Exception | None = None
        for m in models:
            if reason := self.settings.paid_model_reason(m, base_url):
                log.error("FREE_ONLY: blocked %s", reason)
                last_exc = LLMError(f"Blocked by FREE_ONLY: {reason}")
                continue
            t0 = time.perf_counter()
            try:
                extras = self._extras()
                if json_mode:
                    extras["response_format"] = {"type": "json_object"}
                base = dict(model=m, messages=messages,
                            temperature=self.settings.llm_temperature if temperature is None else temperature,
                            max_tokens=max_tokens or self.settings.llm_max_tokens)
                resp = self._create(client, base, extras)
                usage = resp.usage
                return LLMResult(
                    text=(resp.choices[0].message.content or "").strip(),
                    model=resp.model or m,
                    prompt_tokens=getattr(usage, "prompt_tokens", 0) or 0,
                    completion_tokens=getattr(usage, "completion_tokens", 0) or 0,
                    latency_ms=int((time.perf_counter() - t0) * 1000),
                )
            except Exception as exc:
                log.warning("LLM call failed on %s: %s %s — trying fallback", m, exc, str(getattr(exc, "body", "") or "")[:300])
                last_exc = exc
        raise LLMError(f"All models failed: {last_exc}")

    def stream(self, messages: list[dict], model: str | None = None) -> Iterator[tuple[str, dict | None]]:
        """Yields (token, None) ... and finally ("", usage_dict)."""
        if not self.configured:
            raise LLMError("LLM_API_KEY is not set. Copy .env.example to .env and add your free Gemini key.")
        if self.settings.llm_mock:
            for word in self._mock_answer(messages).split(" "):
                yield word + " ", None
            yield "", {"model": "offline-extractive", "prompt_tokens": 0, "completion_tokens": 0, "latency_ms": 0}
            return
        last_exc: Exception | None = None
        for m in self._models(model):
            if reason := self.settings.paid_model_reason(m, str(self.client.base_url)):
                log.error("FREE_ONLY: blocked %s", reason)
                last_exc = LLMError(f"Blocked by FREE_ONLY: {reason}")
                continue
            t0 = time.perf_counter()
            emitted = False
            try:
                base = dict(model=m, messages=messages, temperature=self.settings.llm_temperature,
                            max_tokens=self.settings.llm_max_tokens, stream=True)
                stream = self._create(self.client, base, {**self._extras(), "stream_options": {"include_usage": True}})
                usage = {"model": m, "prompt_tokens": 0, "completion_tokens": 0}
                for chunk in stream:
                    if chunk.usage:
                        usage["prompt_tokens"] = chunk.usage.prompt_tokens or 0
                        usage["completion_tokens"] = chunk.usage.completion_tokens or 0
                    if chunk.model:
                        usage["model"] = chunk.model
                    if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                        emitted = True
                        yield chunk.choices[0].delta.content, None
                usage["latency_ms"] = int((time.perf_counter() - t0) * 1000)
                yield "", usage
                return
            except Exception as exc:
                if emitted:  # can't silently switch models mid-answer
                    raise LLMError(f"Stream interrupted: {exc}") from exc
                log.warning("LLM stream failed on %s: %s — trying fallback", m, exc)
                last_exc = exc
        raise LLMError(f"All models failed: {last_exc}")


@lru_cache
def get_llm() -> LLM:
    return LLM()
