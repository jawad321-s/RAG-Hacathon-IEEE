"""Turn the scraped Hebron University data (branch `claude/magical-cerf-dpnkye`, folder `data/`)
into a clean, de-duplicated knowledge base under backend/data/raw/:

    raw/plans/        one Markdown file per study plan (requirement + course tables only)
    raw/courses/      courses.json — one record per course (hours, prerequisite, description, plans)
    raw/departments/  per-department pages: overview, objectives, career paths, guide plans
    raw/general/      admission, admission requirements, fees, scholarships, new students...

Why: the original plan files repeat every course description in every plan and track
(~12 MB of duplicates). Storing each fact once makes indexing ~5x faster and retrieval sharper.

Usage (from backend/):
    python -m scripts.prepare_hebron /path/to/hebron-data/data
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from pathlib import Path

RAW = Path(__file__).resolve().parent.parent / "data" / "raw"
PAGE_KINDS = ("overview", "obj", "jobs", "guideplan", "prog")  # skip *-courses / *-plans: duplicated by advisor data


def _clean_markdown(text: str) -> tuple[str, str]:
    """Strip front matter and site chrome; return (body, source_url)."""
    src = ""
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    if m:
        fm = m.group(1)
        sm = re.search(r"^source:\s*(\S+)", fm, re.M)
        src = sm.group(1) if sm else ""
        text = text[m.end():]
    text = re.sub(r"^\*\s*\[(tweet|share|Tweet)\].*$", "", text, flags=re.M)
    text = re.sub(r"\[([^\]]+)\]\((?:/|https?://)[^)]*\)", r"\1", text)  # keep link text, drop URLs
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    return text, src


def plans(src: Path, out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted((src / "advisor" / "majors").glob("*.md")):
        body = f.read_text(encoding="utf-8").split("\n## وصف المساقات")[0]
        # Some plans are titled just "الخطة الدراسية 2022": add the major from the file name
        slug = re.sub(r"^(Academic[-_ ]?(Advisory[-_ ]?)?Plan[-_ ]?|Course_Description-)", "", f.stem, flags=re.I)
        slug = re.sub(r"[-_]+", " ", slug).strip()
        body = re.sub(r"^# (.+)$", lambda m, s=slug: f"# {m.group(1)} ({s})", body, count=1, flags=re.M)
        body = re.sub(r"^- (سنة الخطة|مجموع ساعات الخطة): None.*\n", "", body, flags=re.M)
        body = body.replace(" (None ساعة)", "").replace("| None |", "| — |")
        (out / f.name).write_text(body.strip() + "\n", encoding="utf-8")
        n += 1
    return n


def courses(src: Path, out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    data = json.loads((src / "advisor" / "courses.json").read_text(encoding="utf-8"))
    items = data.values() if isinstance(data, dict) else data
    records = []
    for c in items:
        name = c.get("name_ar") or c.get("name_en") or ""
        if not name:
            continue
        en = f" ({c['name_en']})" if c.get("name_en") else ""
        pre = "، ".join(c.get("prerequisite_names") or c.get("prerequisites") or []) or "لا يوجد"
        plans_in = c.get("in_plans") or []
        lines = [
            f"مساق {c.get('code', '')} — {name}{en}",
            f"الساعات المعتمدة: {c.get('credit_hours', '—')}",
            f"المتطلب السابق: {pre}",
        ]
        if c.get("description"):
            lines.append(f"وصف المساق: {c['description'].strip()}")
        if plans_in:
            more = f" و{len(plans_in) - 6} خطط أخرى" if len(plans_in) > 6 else ""
            lines.append("يرد في: " + "؛ ".join(plans_in[:6]) + more)
        records.append({"text": "\n".join(lines), "code": str(c.get("code", "")), "course": name})
    (out / "courses.json").write_text(json.dumps(records, ensure_ascii=False, indent=1), encoding="utf-8")
    return len(records)


def departments(src: Path, out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for dept in sorted((src / "pages").iterdir()):
        if not dept.is_dir():
            continue
        parts = []
        for f in sorted(dept.glob("*.md")):
            kind = f.stem.rsplit("-", 1)[-1]
            if kind not in PAGE_KINDS and f.stem != dept.name.split("__")[-1]:
                continue
            body, url = _clean_markdown(f.read_text(encoding="utf-8"))
            if len(body) < 40:
                continue
            parts.append(body + (f"\n\nالمصدر: {url}" if url else ""))
        if parts:
            (out / f"{dept.name}.md").write_text("\n\n".join(parts) + "\n", encoding="utf-8")
            n += 1
    return n


def general(src: Path, out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    n = 0
    for f in sorted((src / "general").glob("*.md")):
        body, url = _clean_markdown(f.read_text(encoding="utf-8"))
        (out / f.name).write_text(body + (f"\n\nالمصدر: {url}\n" if url else "\n"), encoding="utf-8")
        n += 1
    return n


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    src = Path(sys.argv[1])
    if not (src / "advisor" / "courses.json").exists():
        sys.exit(f"{src}/advisor/courses.json not found — run the branch's build_advisor_data.py first")
    for sub in ("plans", "courses", "departments", "general"):
        shutil.rmtree(RAW / sub, ignore_errors=True)
    stats = {
        "plans": plans(src, RAW / "plans"),
        "courses": courses(src, RAW / "courses"),
        "departments": departments(src, RAW / "departments"),
        "general": general(src, RAW / "general"),
    }
    print(json.dumps(stats, ensure_ascii=False))
