#!/usr/bin/env python3
"""
Build the student-facing academic-advisor dataset from the scraped data.

Inputs  : data/catalog.json, data/pdfs/**/Academic-Plan*.pdf (registration
          "تقرير خطة تخصص" reports), data/pages/*/*courses*.md
Outputs : data/advisor/courses.json   - every course: code, Arabic/English name,
                                         credit hours, prerequisites, description
          data/advisor/plans.json     - every study plan: major, year, total hours,
                                         requirement categories -> courses
          data/advisor/majors/*.md    - one readable document per study plan
                                         (best unit for RAG retrieval)
"""
import json
import os
import re
import unicodedata
from collections import defaultdict

import pdfplumber

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))
OUT = os.path.join(ROOT, "advisor")
AR = re.compile(r"[؀-ۿﭐ-﷿ﹰ-﻿]")
CODE = r"[0-9A-Z]{5,6}"


def _units(chars):
    """Sort a line's glyphs left->right; glyphs sharing one box (lam-alef
    ligatures) are kept together in their original (logical) order."""
    chars = sorted(chars, key=lambda c: c["x0"])
    units = []
    for c in chars:
        if c["text"].isspace():
            continue
        if units and abs(c["x0"] - units[-1]["x0"]) < 0.05 and abs(c["x1"] - units[-1]["x1"]) < 0.05:
            if c["text"] != units[-1]["t"] and not units[-1]["t"].endswith(c["text"]):
                units[-1]["t"] += c["text"]
            continue
        units.append({"t": c["text"], "x0": c["x0"], "x1": c["x1"], "size": c.get("size", 10)})
    return units


def _tokens(units):
    toks, cur, prev = [], [], None
    for u in units:
        if prev is not None and u["x0"] - prev["x1"] > 0.2 * u["size"]:
            toks.append(cur)
            cur = []
        cur.append(u["t"])
        prev = u
    if cur:
        toks.append(cur)
    return toks


def fix_tokens(toks):
    """toks: list of tokens in visual order, each a list of glyph units.
    Arabic runs are reversed (token order and glyph order), then normalised."""
    out, i = [], 0
    is_ar = [bool(AR.search("".join(t))) for t in toks]
    while i < len(toks):
        if is_ar[i]:
            j = i
            while j < len(toks) and is_ar[j]:
                j += 1
            out += ["".join(t[::-1]) for t in toks[i:j]][::-1]
            i = j
        else:
            out.append("".join(toks[i]))
            i += 1
    txt = unicodedata.normalize("NFKC", " ".join(out))
    # brackets inside reversed Arabic runs come out mirrored
    return re.sub(r"\)(\d+)\(", r"(\1)", txt)


def fix_line(line):
    return fix_tokens([list(t) for t in line.split()])


def page_lines(page):
    out = []
    for l in page.extract_text_lines(return_chars=True):
        out.append(fix_tokens(_tokens(_units(l["chars"]))))
    return out


COURSE_RE = re.compile(rf"^(?:(?P<pre>[0-9A-Za-z,]+)\s+)?(?P<h>\d{{1,2}})\s+(?P<rest>.+?)\s+(?P<seq>\d{{1,3}})\s+(?P<code>{CODE})$")
CAT_RE = re.compile(r"^(?P<h>\d+)\s+نوع الخطة\s+(?P<name>.+?)\s+عدد الساعات المطلوبة$")
GRP_RE = re.compile(r"^(?P<h>\d+)\s+ساعات المجموعة\s*(?P<name>.*?)\s*رقم المجموعة\s*(?P<n>\d+)")
TOTAL_RE = re.compile(r"^(\d+)\s+ساعات الخطة")
MAJOR_RE = re.compile(r"التخصص:\s*(.+?)\s+سنة الخطة")


def split_names(rest):
    toks = rest.split()
    k = next((i for i, t in enumerate(toks) if AR.search(t)), len(toks))
    en, ar = " ".join(toks[:k]), " ".join(toks[k:])
    # "(1) Chinese Language (1) اللغة الصينية" -> keep the number once, at the end
    m = re.match(r"^\((\d)\)\s+(.*)", en)
    if m:
        en = f"{m.group(2)} ({m.group(1)})"
        ar = re.sub(r"^\(\d\)\s*", "", ar)
        ar = f"{ar} ({m.group(1)})"
    return en.strip(), ar.strip()


CODE_TOK = re.compile(r"^(?=.*\d)(?:[0-9]{5}|[A-Z][0-9]{4}|[0-9]{2}[A-Za-z]{2}[0-9]|[0-9]{3}[A-Za-z][0-9]|[0-9]{2}[A-Za-z][0-9]{2}|[A-Z]{1,2}[0-9]{3,4})$")
DASH_TOK = re.compile(r"^[-ـ—–]+$")
HOURS_TOK = re.compile(r"^\d{1,2}$")
CAT_WORDS = re.compile(r"(متطلبات|المتطلبات|مساقات)")
SKIP_WORDS = ("متطلب سابق", "المتطلب السابق", "اسم المساق", "Course Name", "Prerequisite", "Pre-requisite")


def row_lines(page):
    """Text lines of a page in reading order; each table row becomes one line
    (cells joined left->right), so every layout can be parsed the same way."""
    items = []
    boxes = []
    for t in page.find_tables():
        boxes.append(t.bbox)
        for row in t.rows:
            cells = [c for c in row.cells if c]
            parts = []
            for bb in sorted(cells, key=lambda b: b[0]):
                try:
                    sub = page.within_bbox(bb)
                except ValueError:
                    continue
                txt = " ".join(page_lines(sub)).strip()
                if txt:
                    parts.append(txt)
            if parts:
                items.append((row.bbox[1], " ".join(parts)))

    def inside(l):
        cx, cy = (l["x0"] + l["x1"]) / 2, (l["top"] + l["bottom"]) / 2
        return any(b[0] <= cx <= b[2] and b[1] <= cy <= b[3] for b in boxes)

    for l in page.extract_text_lines(return_chars=True):
        if not inside(l):
            items.append((l["top"], fix_tokens(_tokens(_units(l["chars"])))))
    return [t for _, t in sorted(items, key=lambda x: x[0])]


def classify(line):
    """Return course dict if the line is a course row, else None."""
    if any(w in line for w in SKIP_WORDS):
        return None
    toks = line.split()
    hi = next((i for i, t in enumerate(toks) if HOURS_TOK.match(t) and 0 < int(t) <= 12), None)
    if hi is None:
        return None
    codes = [i for i, t in enumerate(toks) if CODE_TOK.match(t.strip(",،")) and i != hi]
    after = [i for i in codes if i > hi]
    if not after:
        return None
    ci = after[-1] if not AR.search(" ".join(toks[after[-1]:])) else after[0]
    # Arabic names never contain codes; pick the code after hours closest to the end
    ci = max(after)
    pre, j = [], hi - 1
    while j >= 0 and (CODE_TOK.match(toks[j].strip(",،")) or DASH_TOK.match(toks[j]) or toks[j] in (",", "،", "&", "و")):
        if CODE_TOK.match(toks[j].strip(",،")):
            pre.insert(0, toks[j].strip(",،").upper())
        j -= 1
    rest = [t for k, t in enumerate(toks) if k not in (hi, ci) and not (j < k < hi)]
    rest = [t for t in rest if not re.match(r"^\.?\d{1,3}\.?$", t) and not DASH_TOK.match(t)]
    ar = " ".join(t for t in rest if AR.search(t) or (re.match(r"^\(\d\)$", t)))
    en = " ".join(t for t in rest if not AR.search(t) and not re.match(r"^\(\d\)$", t) and not CODE_TOK.match(t))
    m = re.search(r"\((\d)\)", " ".join(rest))
    if m and f"({m.group(1)})" not in en:
        en = f"{en} ({m.group(1)})".strip()
    ar = re.sub(r"^\((\d)\)\s*(.*)$", r"\2 (\1)", ar)
    if not ar and not en:
        return None
    return {"code": toks[ci].upper(), "name_ar": ar.strip(), "name_en": en.strip(),
            "credit_hours": int(toks[hi]), "prerequisites": pre}


def parse_plan(path):
    with pdfplumber.open(path) as pdf:
        lines = [l.strip() for p in pdf.pages for l in row_lines(p)]
    plan = {"source_pdf": os.path.relpath(path, ROOT), "major_name": None, "total_hours": None, "requirements": []}
    fmt1 = any("تقرير خطة تخصص" in l for l in lines[:8])
    cat = grp = None

    def new_cat(name, hours):
        nonlocal cat, grp
        cat = {"category": name, "required_hours": hours, "groups": []}
        plan["requirements"].append(cat)
        grp = None

    for l in lines[:40]:
        if plan["major_name"] is None and (m := MAJOR_RE.search(l)):
            plan["major_name"] = m.group(1).strip()
        if plan["total_hours"] is None and (m := re.search(r"(\d{3})\s+ساعات الخطة", l)):
            plan["total_hours"] = int(m.group(1))
    if plan["total_hours"] is None:
        for l in lines[:15]:
            for n in re.findall(r"(?<![\d/])(\d{3})(?![\d/])", l):
                if 100 <= int(n) <= 250:
                    plan["total_hours"] = int(n)
                    break
            if plan["total_hours"]:
                break
    if plan["major_name"] is None:
        plan["major_name"] = next((l for l in lines[:10] if "تخصص" in l or "قسم" in l), None)

    for i, l in enumerate(lines):
        if fmt1:
            if m := CAT_RE.match(l):
                new_cat(m.group("name"), int(m.group("h")))
                continue
            if (m := GRP_RE.match(l)) and cat is not None:
                note = re.sub(r"اسم المجموعة|Group|Compalsory", "", m.group("name")).strip()
                grp = {"group": int(m.group("n")), "group_hours": int(m.group("h")), "note": note, "courses": []}
                cat["groups"].append(grp)
                continue
        c = classify(l)
        if c:
            if not c["name_en"] and i + 1 < len(lines) and ASCII_LINE.match(lines[i + 1]) and not classify(lines[i + 1]):
                c["name_en"] = lines[i + 1]
            if i and ASCII_LINE.match(lines[i - 1]) and not classify(lines[i - 1]) and not CAT_WORDS.search(lines[i - 1]):
                prev = re.sub(r"\s*\.?\d{1,3}\.?$", "", lines[i - 1])
                if not re.search(r"Course|Credit|Hebron|College|Department|Compulsory|Elective|Requirement", prev, re.I):
                    c["name_en"] = (prev + " " + c["name_en"]).strip()
            if cat is None:
                new_cat("متطلبات", None)
            if grp is None:
                grp = {"group": 1, "group_hours": cat["required_hours"], "note": "", "courses": []}
                cat["groups"].append(grp)
            grp["courses"].append(c)
            continue
        if not fmt1 and CAT_WORDS.search(l) and not any(w in l for w in SKIP_WORDS[:3]):
            nums = [int(n) for n in re.findall(r"(?<![\w.])(\d{1,3})(?![\w.])", l) if 0 < int(n) <= 200]
            k = l.find(CAT_WORDS.search(l).group(1))
            name = re.sub(r"[()\d.]+", " ", l[k:])
            name = re.sub(r"\s+", " ", name).strip(" -:")
            new_cat(name, nums[0] if nums else None)
    # drop empty categories
    plan["requirements"] = [r for r in plan["requirements"] if any(g["courses"] for g in r["groups"])]
    return plan if plan["requirements"] else None


ASCII_LINE = re.compile(r"^[A-Za-z][A-Za-z0-9 &:,'()\-/.]*$")


DESC_HEAD = re.compile(rf"^\*\*\s*({CODE})\s+(.+?)\s*\*\*\s*$")


def parse_descriptions(md_text):
    out, cur, section = {}, None, None
    for line in md_text.splitlines():
        s = line.strip()
        if s.startswith("## "):
            section = s[3:].strip()
            cur = None
            continue
        m = None
        if s.startswith("**"):
            t = re.sub(r"\s+", " ", re.sub(r"\*+", " ", s.replace("\u00a0", " "))).strip()
            m = re.match(rf"^({CODE})\s*[-–:]?\s+(.{{2,120}}?)\s*[:：]?$", t)
        if m:
            cur = m.group(1).upper()
            if cur in out and out[cur]["description"]:
                cur = None  # same course listed again (another tab) - keep first text
                continue
            out.setdefault(cur, {"name_ar": m.group(2).strip(" :"), "description": "", "section": section})
            continue
        if cur and s and not s.startswith(("*", "#", "[", "---", "|")):
            out[cur]["description"] = (out[cur]["description"] + " " + s).strip()
    return out


def main():
    cat = json.load(open(os.path.join(ROOT, "catalog.json"), encoding="utf-8"))
    for d in cat["departments"]:
        d["pages"] = {k: v for k, v in d["pages"].items() if os.path.exists(os.path.join(ROOT, v["file"]))}
        d["pdfs"] = [p for p in d["pdfs"] if p.get("file") and os.path.exists(os.path.join(ROOT, p["file"]))]
    g = cat.get("general", {})
    g["pages"] = {k: v for k, v in g.get("pages", {}).items() if os.path.exists(os.path.join(ROOT, v["file"]))}
    json.dump(cat, open(os.path.join(ROOT, "catalog.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    os.makedirs(os.path.join(OUT, "majors"), exist_ok=True)
    dept_of_major = {}
    for d in cat["departments"]:
        for m in d["majors"]:
            dept_of_major[m] = d["slug"]

    # 1) course descriptions from department pages
    descs, desc_depts = {}, defaultdict(set)
    for d in cat["departments"]:
        for name, pg in d["pages"].items():
            if "courses" not in name:
                continue
            txt = open(os.path.join(ROOT, pg["file"]), encoding="utf-8").read()
            for code, v in parse_descriptions(txt).items():
                desc_depts[code].add(d["slug"])
                if len(v["description"]) > len(descs.get(code, {}).get("description", "")):
                    descs[code] = v

    # 2) study plans from PDFs
    plans = []
    for d in cat["departments"]:
        for p in d["pdfs"]:
            f = p.get("file")
            if not f or not f.lower().endswith(".pdf"):
                continue
            base = os.path.basename(f).lower()
            if "course" in base and "desc" in base:
                continue
            try:
                plan = parse_plan(os.path.join(ROOT, f))
            except Exception as e:
                print("!", f, e)
                continue
            if not plan:
                continue
            ym = re.search(r"(20\d\d)", os.path.basename(f))
            plan.update({"plan_type": "guide_plan (الخطة الاسترشادية)" if "advisory" in base else "study_plan (الخطة الدراسية)",
                         "title": p.get("label") or plan["major_name"], "department": d["slug"],
                         "plan_year": int(ym.group(1)) if ym else None,
                         "source_url": p["url"], "department_majors": d["majors"]})
            if not any(x["source_pdf"] == plan["source_pdf"] for x in plans):
                plans.append(plan)

    # 3) merge into one course table
    courses = {}
    for plan in plans:
        for r in plan["requirements"]:
            for g in r["groups"]:
                for c in g["courses"]:
                    e = courses.setdefault(c["code"], {"code": c["code"], "name_ar": c["name_ar"], "name_en": c["name_en"],
                                                       "credit_hours": c["credit_hours"], "prerequisites": [],
                                                       "description": "", "in_plans": []})
                    for k in ("name_ar", "name_en", "credit_hours"):
                        if not e.get(k) and c.get(k):
                            e[k] = c[k]
                    for pre in c["prerequisites"]:
                        if pre not in e["prerequisites"]:
                            e["prerequisites"].append(pre)
                    e["in_plans"].append(plan["title"])
    for code, v in descs.items():
        e = courses.setdefault(code, {"code": code, "name_ar": v["name_ar"], "name_en": "", "credit_hours": None,
                                      "prerequisites": [], "description": "", "in_plans": []})
        e["description"] = v["description"]
        if v["name_ar"] and len(v["name_ar"]) <= 80:
            e["name_ar"] = v["name_ar"]  # department pages have the cleanest names
        e.setdefault("description_departments", sorted(desc_depts[code]))
    for e in courses.values():
        e["in_plans"] = sorted(set(e["in_plans"]))
        e["prerequisite_names"] = [courses[p]["name_ar"] if p in courses else p for p in e["prerequisites"]]

    json.dump(dict(sorted(courses.items())), open(os.path.join(OUT, "courses.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=1)
    json.dump(plans, open(os.path.join(OUT, "plans.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    # 4) one markdown document per plan (student friendly)
    for plan in plans:
        slug = os.path.basename(plan["source_pdf"])[:-4]
        kind = "الخطة الاسترشادية" if plan["plan_type"].startswith("guide") else "الخطة الدراسية"
        L = [f"# {kind}: {plan['title']}", "",
             f"- التخصص (حسب نظام التسجيل): {plan['major_name']}",
             f"- سنة الخطة: {plan['plan_year']}",
             f"- مجموع ساعات الخطة: {plan['total_hours']} ساعة معتمدة",
             f"- القسم: {plan['department']}",
             f"- المصدر الرسمي: {plan['source_url']}", "",
             "## ملخص المتطلبات", "", "| نوع المتطلب | الساعات المطلوبة |", "|---|---|"]
        L += [f"| {r['category']} | {r['required_hours'] if r['required_hours'] is not None else 'غير محدد'} |" for r in plan["requirements"]]
        for r in plan["requirements"]:
            L += ["", f"## {r['category']}" + (f" ({r['required_hours']} ساعة)" if r["required_hours"] else "")]
            for g in r["groups"]:
                if len(r["groups"]) > 1 or g["group_hours"] != r["required_hours"]:
                    L += ["", f"### مجموعة {g['group']} — يدرس الطالب {g['group_hours']} ساعة"]
                L += ["", "| رقم المساق | اسم المساق | Course Name | الساعات | المتطلب السابق |", "|---|---|---|---|---|"]
                for c in g["courses"]:
                    pre = "، ".join(f"{p} {courses.get(p, {}).get('name_ar', '')}".strip() for p in c["prerequisites"]) or "—"
                    L.append(f"| {c['code']} | {courses[c['code']]['name_ar'] or c['name_ar']} | {courses[c['code']]['name_en'] or c['name_en']} | {c['credit_hours']} | {pre} |")
        L += ["", "## وصف المساقات", ""]
        seen = set()
        for r in plan["requirements"]:
            for g in r["groups"]:
                for c in g["courses"]:
                    if c["code"] in seen:
                        continue
                    seen.add(c["code"])
                    desc = courses[c["code"]]["description"]
                    if desc:
                        L += [f"**{c['code']} — {c['name_ar']} ({c['credit_hours']} ساعات)**", "", desc, ""]
        open(os.path.join(OUT, "majors", slug + ".md"), "w", encoding="utf-8").write("\n".join(L) + "\n")

    n_desc = sum(1 for c in courses.values() if c["description"])
    print(f"{len(plans)} plans, {len(courses)} courses ({n_desc} with description)")


if __name__ == "__main__":
    main()
