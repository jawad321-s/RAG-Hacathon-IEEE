"""Sanity check: API keys, model availability, a test completion on each provider."""

import sys

from app.config import get_settings
from app.generation.llm import get_llm

if __name__ == "__main__":
    s = get_settings()
    llm = get_llm()
    if not llm.configured:
        sys.exit("❌ OPENROUTER_API_KEY missing in .env")
    print(f"Answering provider: {s.openrouter_base_url}")
    try:
        ids = {m.id for m in llm.client.models.list().data}
        for m in [s.llm_model, *s.fallback_models]:
            print(("✅" if m in ids or f"models/{m}" in ids else "❌ NOT FOUND"), m)
    except Exception as exc:
        print("⚠️ could not list models:", exc)
    r = llm.complete([{"role": "user", "content": "قل: النظام يعمل"}], max_tokens=20)
    print(f"✅ answer model via {r.model}: {r.text} ({r.latency_ms} ms)")
    if llm.separate_utility:
        print(f"Utility provider: {s.utility_base_url or s.openrouter_base_url}")
    r = llm.complete([{"role": "user", "content": "قل: جاهز"}], max_tokens=20, utility=True, model=s.llm_utility_model)
    print(f"✅ utility model via {r.model}: {r.text} ({r.latency_ms} ms)")
