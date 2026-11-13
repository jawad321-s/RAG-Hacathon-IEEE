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


# --------------------------------------------------------------------------- overview
# Questions like "شو في تخصصات شريعة؟" need ONE place that lists a college's majors.
# The site has that only as two flat tables (colleges -> departments, and all programs),
# whose rows never mention the college. We join them into one section per college.

COLLEGE_RULES = [  # (keyword in program name, college) — first match wins, order matters
    ("الفقه والقانون", "كلية الحقوق والعلوم السياسية"), ("القانون", "كلية الحقوق والعلوم السياسية"),
    ("العلوم السياسية", "كلية الحقوق والعلوم السياسية"),
    ("معلم", "كلية العلوم الإنسانية والتربوية"), ("الارشاد النفسي", "كلية العلوم الإنسانية والتربوية"),
    ("رياض الاطفال", "كلية العلوم الإنسانية والتربوية"),
    ("اصول الدين", "كلية الشريعة"), ("أصول الدين", "كلية الشريعة"), ("أصول دين", "كلية الشريعة"),
    ("الفقه", "كلية الشريعة"), ("الشريعة", "كلية الشريعة"),
    ("الرياضيات", "كلية العلوم والتكنولوجيا"), ("الكيمياء", "كلية العلوم والتكنولوجيا"),
    ("الاحياء", "كلية العلوم والتكنولوجيا"), ("الأحياء", "كلية العلوم والتكنولوجيا"),
    ("الحاسوب", "كلية تكنولوجيا المعلومات"), ("الويب", "كلية تكنولوجيا المعلومات"),
    ("الامن السيبراني", "كلية تكنولوجيا المعلومات"), ("الأمن السيبراني", "كلية تكنولوجيا المعلومات"),
    ("العلوم الطبية المخبرية", "كلية العلوم الصحية التطبيقية"), ("الفيزياء الطبية", "كلية العلوم الصحية التطبيقية"),
    ("التصوير الطبي", "كلية العلوم الصحية التطبيقية"), ("العلاج الطبيعي", "كلية العلوم الصحية التطبيقية"),
    ("صيدل", "كلية الصيدلة"), ("التمريض", "كلية التمريض"), ("القبالة", "كلية التمريض"),
    ("الانتاج النباتي", "كلية الهندسة الزراعة"), ("الإنتاج الحيواني", "كلية الهندسة الزراعة"),
    ("الانتاج الحيواني", "كلية الهندسة الزراعة"), ("التغذية", "كلية الهندسة الزراعة"), ("البستنة", "كلية الهندسة الزراعة"),
    ("ادارة الاعمال", "كلية التمويل والادارة"), ("العلوم المالية", "كلية التمويل والادارة"),
    ("التسويق الرقمي", "كلية التمويل والادارة"), ("الادارة العامة", "كلية التمويل والادارة"),
    ("اللغة العربية", "كلية العلوم الإنسانية والتربوية"), ("اللغة الانجليزية", "كلية العلوم الإنسانية والتربوية"),
    ("التاريخ", "كلية العلوم الإنسانية والتربوية"), ("تاريخ", "كلية العلوم الإنسانية والتربوية"), ("الاعلام", "كلية العلوم الإنسانية والتربوية"),
    ("الإعلام", "كلية العلوم الإنسانية والتربوية"), ("الجغرافيا", "كلية العلوم الإنسانية والتربوية"),
    ("السياحة", "كلية العلوم الإنسانية والتربوية"), ("الترجمة", "كلية العلوم الإنسانية والتربوية"),
    ("الطب البشري", "كلية الطب البشري"),
]
COLLEGE_ALIASES = {  # words students use, so the section is found by dialect/informal questions
    "كلية الشريعة": "تخصصات الشريعة، الدراسات الإسلامية، أصول الدين، الفقه",
    "كلية تكنولوجيا المعلومات": "تخصصات الحاسوب والبرمجة وتكنولوجيا المعلومات IT",
    "كلية العلوم والتكنولوجيا": "تخصصات العلوم: رياضيات، كيمياء، أحياء، بيئة",
    "كلية العلوم الصحية التطبيقية": "التخصصات الصحية والطبية المساندة",
    "كلية الهندسة الزراعة": "تخصصات الزراعة",
    "كلية التمويل والادارة": "تخصصات الإدارة والمحاسبة والتسويق والبزنس",
    "كلية العلوم الإنسانية والتربوية": "تخصصات الآداب واللغات والتربية والتعليم والإعلام",
    "كلية الحقوق والعلوم السياسية": "تخصصات القانون والحقوق والسياسة",
}
OTHER = "برامج لم تحدد صفحة الكليات كليتها"


def _college_of(program: str) -> str:
    return next((c for k, c in COLLEGE_RULES if k in program), OTHER)


def _parse_colleges(text: str) -> dict[str, str]:
    out = {}
    for m in re.finditer(r"\*\*((?:كلية|برامج)[^*]+)\*\*([^|]*)", text):
        out[re.sub(r"\s+", " ", m.group(1)).strip()] = re.sub(r"\s+", " ", m.group(2)).strip()
    return out


def _table_rows(text: str) -> list[list[str]]:
    rows = []
    for line in text.splitlines():
        if line.startswith("|") and "---" not in line:
            cells = [re.sub(r"\*+", "", c).strip() for c in line.strip().strip("|").split("|")]
            if any(cells):
                rows.append(cells)
    return rows


def overview(general_dir: Path, out: Path) -> int:
    out.mkdir(parents=True, exist_ok=True)
    colleges = _parse_colleges((general_dir / "colleges.md").read_text(encoding="utf-8"))
    programs = [r for r in _table_rows((general_dir / "undergraduate-programs.md").read_text(encoding="utf-8"))
                if len(r) >= 2 and r[1].isdigit()]
    diplomas = [r for r in _table_rows((general_dir / "admissions-regulations.md").read_text(encoding="utf-8"))
                if len(r) >= 5 and r[1].isdigit()]
    by_college: dict[str, list[list[str]]] = {}
    for r in programs:
        c = _college_of(r[0])
        by_college.setdefault(c if c in colleges else OTHER, []).append(r)  # never drop a program

    src = "المصدر: https://www.hebron.edu/index.php/academic/aca01/colleges.html و https://www.hebron.edu/index.php/academic/aca01/undergraduate.html"
    lines = ["# الكليات والتخصصات في جامعة الخليل", "",
             "## قائمة كليات جامعة الخليل", ""]
    lines += [f"- {c}" for c in colleges if c.startswith("كلية")]
    lines += ["", f"عدد برامج البكالوريوس: {len(programs)} برنامجاً. عدد برامج الدبلوم المتوسط: {len(diplomas)}.", src, ""]
    for college, depts in colleges.items():
        if not college.startswith("كلية") or college == "كلية الدراسات العليا والبحث العلمي":
            continue
        alias = f" ({COLLEGE_ALIASES[college]})" if college in COLLEGE_ALIASES else ""
        lines += [f"## {college} — التخصصات{alias}", ""]
        if depts:
            lines += [f"أقسام {college}: {depts}.", ""]
        progs = by_college.get(college, [])
        if progs:
            lines += [f"برامج البكالوريوس في {college} ({len(progs)}):", "",
                      "| البرنامج | الساعات المعتمدة | فروع الثانوية العامة المقبولة |", "|---|---|---|"]
            lines += [f"| {r[0]} | {r[1]} | {r[2] if len(r) > 2 else ''} |" for r in progs]
            lines.append("")
        lines += [src, ""]
    if by_college.get(OTHER):
        lines += [f"## {OTHER}", "", "| البرنامج | الساعات المعتمدة | فروع الثانوية العامة المقبولة |", "|---|---|---|"]
        lines += [f"| {r[0]} | {r[1]} | {r[2] if len(r) > 2 else ''} |" for r in by_college[OTHER]] + [""]
    # Bachelor admission conditions as their own short section (they were crowded out by the
    # long per-stream lists, which also mention "الثانوية العامة" and "البكالوريوس").
    adm = (general_dir / "admissions-regulations.md").read_text(encoding="utf-8")
    m = re.search(r"شروط القبول لبرامج البكالوريوس.*?(?=\*\*شروط القبول لبرامج الدبلوم|\n\|)", adm, re.S)
    if m:
        bullets = [b.strip(" *") for b in m.group(0).splitlines() if b.strip().startswith("*") and len(b.strip()) > 3]
        lines += ["## شروط القبول في برامج البكالوريوس (معدل الثانوية العامة الأدنى وامتحان القبول)", ""]
        lines += [f"- {b}" for b in bullets]
        lines += ["", "المصدر: https://www.hebron.edu/index.php/academic/aca02/admission-req.html", ""]
    # Programs open to each high-school (Tawjihi) stream: "شو بقدر أدرس إذا أنا أدبي؟"
    streams = ["العلمي", "الأدبي", "الصناعي", "الزراعي", "الفندقي", "الريادة والأعمال", "تكنولوجيا المعلومات", "الشرعي"]
    norm = lambda t: t.replace("الادبي", "الأدبي")  # noqa: E731
    for st in streams:
        ok = [r for r in programs if len(r) > 2 and st in norm(r[2])]
        if not ok:
            continue
        lines += [f"## التخصصات المتاحة لطلبة الفرع {st} في الثانوية العامة (التوجيهي)", "",
                  f"عدد برامج البكالوريوس التي تقبل الفرع {st}: {len(ok)}.", ""]
        lines += [f"- {r[0]} ({r[1]} ساعة) — {_college_of(r[0])}" for r in ok] + ["", src, ""]
    grad = colleges.get("كلية الدراسات العليا والبحث العلمي", "")
    if grad:
        items = [x.strip() for x in re.split(r"\s(?=ماجستير|الدكتوراة|دكتوراة)", grad) if x.strip()]
        lines += ["## الدراسات العليا (الماجستير والدكتوراة) — كلية الدراسات العليا والبحث العلمي", ""]
        lines += [f"- {x}" for x in items] + ["", src, ""]
    if diplomas:
        lines += ["## برامج الدبلوم المتوسط (سنتان)", "",
                  "| البرنامج | الساعات | مدة الدراسة | علامة الثانوية | شروط القبول |", "|---|---|---|---|---|"]
        lines += [f"| {' | '.join(r[:5])} |" for r in diplomas]
        lines += ["", "المصدر: https://www.hebron.edu/index.php/academic/aca02/admission-req.html", ""]
    (out / "colleges-and-majors.md").write_text("\n".join(lines), encoding="utf-8")
    return len(programs)


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    src = Path(sys.argv[1])
    if not (src / "advisor" / "courses.json").exists():
        sys.exit(f"{src}/advisor/courses.json not found — run the branch's build_advisor_data.py first")
    for sub in ("plans", "courses", "departments", "general", "overview"):
        shutil.rmtree(RAW / sub, ignore_errors=True)
    stats = {
        "plans": plans(src, RAW / "plans"),
        "courses": courses(src, RAW / "courses"),
        "departments": departments(src, RAW / "departments"),
        "general": general(src, RAW / "general"),
    }
    stats["overview_programs"] = overview(RAW / "general", RAW / "overview")
    print(json.dumps(stats, ensure_ascii=False))
