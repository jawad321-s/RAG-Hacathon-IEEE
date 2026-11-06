"""Run the evaluation set and write a JSON + Markdown report.

Eval set format (data/eval/eval_set.json):
[
  {
    "id": "q1",
    "question": "...",
    "reference_answer": "...",            # for correctness judge
    "relevant_sources": ["file.pdf"],      # for retrieval metrics
    "relevant_pages": [12],                # optional
    "relevant_keywords": ["المادة 5"],     # optional alternative to sources
    "type": "factual|dialect|table|multi_hop|out_of_scope|conflict"
  }
]
"""

from __future__ import annotations

import json
import statistics
import time
from datetime import datetime
from pathlib import Path

from app.config import get_settings
from app.generation.generator import answer, build_context
from app.retrieval.retriever import retrieve

from .metrics import correctness, faithfulness, is_relevant, retrieval_metrics


def _mean(xs: list) -> float | None:
    xs = [x for x in xs if isinstance(x, (int, float))]
    return round(statistics.mean(xs), 3) if xs else None


def run_eval(eval_path: Path | None = None, with_generation: bool = True, out_dir: Path | None = None, tag: str = "") -> dict:
    s = get_settings()
    eval_path = eval_path or s.data_dir / "eval" / "eval_set.json"
    out_dir = out_dir or s.data_dir / "eval" / "results"
    out_dir.mkdir(parents=True, exist_ok=True)
    items = json.loads(eval_path.read_text(encoding="utf-8"))
    k = s.top_k
    rows = []
    for item in items:
        t0 = time.perf_counter()
        oos = item.get("type") == "out_of_scope"
        row: dict = {"id": item.get("id"), "type": item.get("type", "factual"), "question": item["question"]}
        if with_generation:
            a = answer(item["question"])
            hits_meta = [(src.text, {"source": src.source, "page": src.page, "original_text": src.original_text}) for src in a.sources]
            row.update(answer=a.answer, refused=a.refused, cited=a.cited, rewritten=a.rewritten_query)
        else:
            r = retrieve(item["question"])
            hits_meta = [(h.text, h.metadata) for h in r.hits]
            row.update(refused=not r.confident or not r.in_scope)

        if not oos:
            flags = [is_relevant(t, m, item) for t, m in hits_meta]
            row.update(retrieval_metrics(flags, k, len(item.get("relevant_sources") or []) or 1))
            row["retrieved"] = [f"{m.get('source')}#p{m.get('page')}" for _, m in hits_meta]

        row["refusal_correct"] = bool(row.get("refused")) == oos
        if with_generation and not row.get("refused") and not oos:
            row["citation_ok"] = bool(row.get("cited"))
            ctx = build_context(a.sources)
            row["faithfulness"] = faithfulness(ctx, a.answer).get("score")
            if item.get("reference_answer"):
                row["correctness"] = correctness(item["question"], item["reference_answer"], a.answer).get("score")
        row["latency_ms"] = int((time.perf_counter() - t0) * 1000)
        rows.append(row)

    in_scope = [r for r in rows if r["type"] != "out_of_scope"]
    summary = {
        "n_questions": len(rows),
        "k": k,
        "hit_rate@k": _mean([r.get("hit") for r in in_scope]),
        "precision@k": _mean([r.get("precision") for r in in_scope]),
        "recall@k": _mean([r.get("recall") for r in in_scope]),
        "mrr": _mean([r.get("mrr") for r in in_scope]),
        "faithfulness": _mean([r.get("faithfulness") for r in rows]),
        "correctness": _mean([r.get("correctness") for r in rows]),
        "citation_rate": _mean([float(r["citation_ok"]) for r in rows if "citation_ok" in r]),
        "refusal_accuracy": _mean([float(r["refusal_correct"]) for r in rows]),
        "avg_latency_ms": _mean([r["latency_ms"] for r in rows]),
        "config": {
            "embedding": f"{s.embedding_provider}:{s.embedding_model}",
            "reranker": s.reranker_model if s.use_reranker else None,
            "llm": s.llm_model,
            "chunk_size": s.chunk_size,
            "chunk_overlap": s.chunk_overlap,
            "hybrid_alpha": s.hybrid_alpha,
            "query_rewrite": s.use_query_rewrite,
            "translate_docs_to": s.translate_docs_to or None,
        },
    }
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    name = f"eval-{stamp}{'-' + tag if tag else ''}"
    report = {"summary": summary, "rows": rows, "created_at": stamp, "tag": tag}
    (out_dir / f"{name}.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "latest.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / f"{name}.md").write_text(to_markdown(report), encoding="utf-8")
    return report


def to_markdown(report: dict) -> str:
    s = report["summary"]
    lines = [
        f"# Evaluation report {report.get('tag', '')} — {report['created_at']}",
        "",
        "| Metric | Value |",
        "|---|---|",
    ]
    for key in ("n_questions", "k", "hit_rate@k", "precision@k", "recall@k", "mrr", "faithfulness", "correctness", "citation_rate", "refusal_accuracy", "avg_latency_ms"):
        lines.append(f"| {key} | {s.get(key)} |")
    lines += ["", "**Config:** `" + json.dumps(s["config"], ensure_ascii=False) + "`", "", "## Per question", ""]
    lines.append("| id | type | hit | P@k | MRR | faithful | correct | refusal ok | question |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in report["rows"]:
        lines.append(
            f"| {r['id']} | {r['type']} | {r.get('hit', '-')} | {r.get('precision', '-')} | {r.get('mrr', '-')} | "
            f"{r.get('faithfulness', '-')} | {r.get('correctness', '-')} | {r['refusal_correct']} | {r['question'][:60]} |"
        )
    lines += ["", "## Error analysis (fill in)", "", "- Worst question & why it failed:", "- What we changed:", "- Effect on metrics:"]
    return "\n".join(lines)
