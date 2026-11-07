"""Calibrate MIN_RELEVANCE_SCORE (the refusal gate) on YOUR models and data.

For every eval question it prints the best reranker score and whether the expected
source was retrieved. In-scope questions should score ABOVE the threshold, out-of-scope
questions BELOW it. The suggested value sits between the two groups.

    make calibrate
"""

import json

from app.config import get_settings
from app.evaluation.metrics import is_relevant
from app.retrieval.retriever import retrieve

if __name__ == "__main__":
    s = get_settings()
    items = json.loads((s.data_dir / "eval" / "eval_set.json").read_text(encoding="utf-8"))
    ins, outs = [], []
    print(f"{'id':5s} {'type':13s} {'top':>6s}  found  top source")
    for it in items:
        r = retrieve(it["question"])
        top = max((h.scores.get("rerank", h.score) for h in r.hits), default=0.0)
        oos = it.get("type") == "out_of_scope"
        found = "-" if oos else ("yes" if any(is_relevant(h.text, h.metadata, it) for h in r.hits) else "NO")
        (outs if oos else ins).append(top)
        src = r.hits[0].metadata.get("source", "") if r.hits else ""
        print(f"{it['id']:5s} {it.get('type', ''):13s} {top:6.3f}  {found:5s}  {src[:50]}  in_scope={r.in_scope}")
    if ins and outs:
        lo_in, hi_out = min(ins), max(outs)
        print(f"\nlowest in-scope score : {lo_in:.3f}\nhighest out-of-scope  : {hi_out:.3f}")
        if hi_out < lo_in:
            print(f"✅ Suggested MIN_RELEVANCE_SCORE = {(hi_out + lo_in) / 2:.3f}  (current {s.min_relevance_score})")
        else:
            print("⚠️ Groups overlap: keep the threshold low (e.g. 0.05) and let the LLM + in_scope check refuse.")
    print("Rows with found=NO are retrieval misses: check them in the admin Retrieval lab.")
