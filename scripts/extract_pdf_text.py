#!/usr/bin/env python3
"""
Extract text (and tables) from every study-plan PDF in data/pdfs and
data/general into data/text/<same path>.md, ready for chunking/embedding.

Arabic PDFs often come out in visual (reversed) order; the raw text is kept
as-is and tables are emitted as Markdown so course codes / credit hours stay
aligned. If a page has no text layer (scanned), it is flagged for OCR.
"""
import os
import sys

import pdfplumber

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "data"))


def table_md(rows):
    rows = [[(c or "").replace("\n", " ").strip() for c in r] for r in rows if r and any(r)]
    if not rows:
        return ""
    w = max(len(r) for r in rows)
    rows = [r + [""] * (w - len(r)) for r in rows]
    out = ["| " + " | ".join(rows[0]) + " |", "|" + "---|" * w]
    out += ["| " + " | ".join(r) + " |" for r in rows[1:]]
    return "\n".join(out)


def convert(src, dst):
    parts = [f"---\nsource_pdf: {os.path.relpath(src, ROOT)}\n---\n"]
    needs_ocr = 0
    with pdfplumber.open(src) as pdf:
        for i, page in enumerate(pdf.pages, 1):
            text = page.extract_text() or ""
            if not text.strip():
                needs_ocr += 1
            parts.append(f"\n## page {i}\n\n{text.strip()}\n")
            for t in page.extract_tables():
                tm = table_md(t)
                if tm:
                    parts.append("\n" + tm + "\n")
    if needs_ocr:
        parts.insert(1, f"\n> NOTE: {needs_ocr} page(s) without a text layer - needs OCR.\n")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        f.write("".join(parts))
    return needs_ocr


def main():
    n = bad = 0
    for sub in ("pdfs", "general"):
        for dp, _, files in os.walk(os.path.join(ROOT, sub)):
            for fn in sorted(files):
                if not fn.lower().endswith(".pdf"):
                    continue
                src = os.path.join(dp, fn)
                dst = os.path.join(ROOT, "text", os.path.relpath(src, ROOT))[:-4] + ".md"
                try:
                    if convert(src, dst):
                        bad += 1
                    n += 1
                except Exception as e:  # keep going on broken files
                    print(f"! {src}: {e}", file=sys.stderr)
    print(f"converted {n} pdfs ({bad} need OCR)")


if __name__ == "__main__":
    main()
