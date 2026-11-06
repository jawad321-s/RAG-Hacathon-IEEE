"""Sanity check: API key, model availability on OpenRouter, a test completion."""

import sys

from app.config import get_settings
from app.generation.llm import get_llm

if __name__ == "__main__":
    s = get_settings()
    llm = get_llm()
    if not llm.configured:
        sys.exit("❌ OPENROUTER_API_KEY missing in .env")
    try:
        ids = {m.id for m in llm.client.models.list().data}
        for m in [s.llm_model, s.llm_utility_model, *s.fallback_models]:
            print(("✅" if m in ids else "❌ NOT FOUND"), m)
    except Exception as exc:
        print("⚠️ could not list models:", exc)
    r = llm.complete([{"role": "user", "content": "قل: النظام يعمل"}], max_tokens=20)
    print(f"✅ completion via {r.model}: {r.text} ({r.latency_ms} ms, {r.prompt_tokens}+{r.completion_tokens} tokens)")
