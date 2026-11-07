#!/usr/bin/env python3
"""
Extract readable text from every PDF in data/pdfs and data/general/pdfs into
data/text/<same path>.md, ready for chunking / embedding.

Uses the glyph-position based reader from build_advisor_data.py, which puts
Arabic text back into logical order (the PDFs store it visually reversed) and
turns each table row into one line. Scanned PDFs (no text layer) are flagged.
"""
import os
import sys

import pdfplumber

sys.path.insert(0, os.path.dirname(__file__))
from build_advisor_data import ROOT, row_lines  # noqa: E402


def convert(src, dst):
    parts = [f"---\nsource_pdf: {os.path.relpath(src, ROOT)}\n---\n"]
    empty = 0
    with pdfplumber.open(src) as pdf:
        n = len(pdf.pages)
        for i, page in enumerate(pdf.pages, 1):
            lines = row_lines(page)
            if not any(l.strip() for l in lines):
                empty += 1
            parts.append(f"\n## صفحة {i}\n\n" + "\n".join(lines) + "\n")
    if n == 0 or empty == n:
        parts.insert(1, "\n> NOTE: scanned PDF without a text layer - needs OCR.\n")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, "w", encoding="utf-8") as f:
        f.write("".join(parts))
    return n == 0 or empty == n


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
                        print("needs OCR:", os.path.relpath(src, ROOT))
                    n += 1
                except Exception as e:  # keep going on broken files
                    print(f"! {src}: {e}", file=sys.stderr)
    print(f"converted {n} pdfs ({bad} need OCR)")


if __name__ == "__main__":
    main()
