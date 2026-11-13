"""Check extraction quality BEFORE ingesting (Arabic PDFs can come out broken/reversed/scanned).

    python -m scripts.inspect_doc data/raw/myfile.pdf
Prints pages, detected tables and the first chunks so you can eyeball them.
"""

import sys
from pathlib import Path

from app.config import get_settings
from app.ingestion.arabic import is_arabic
from app.ingestion.chunker import chunk_pages
from app.ingestion.loaders import load_document

if __name__ == "__main__":
    path = Path(sys.argv[1])
    s = get_settings()
    pages = load_document(path)
    print(f"Pages with text: {len(pages)}")
    for p in pages[:3]:
        print(f"\n--- page {p.page} | arabic={is_arabic(p.text)} | table={p.metadata.get('has_table')} ---")
        print(p.text[:700])
    chunks = chunk_pages(pages, s.chunk_size, s.chunk_overlap)
    lens = [len(c.text) for c in chunks]
    print(f"\nChunks: {len(chunks)} | avg {sum(lens) // max(1, len(lens))} chars | tables {sum(c.metadata['is_table'] for c in chunks)}")
    for c in chunks[:3]:
        print(f"\n### chunk {c.metadata['chunk_index']} (p{c.metadata['page']}, section={c.metadata['section']!r})\n{c.text[:400]}")
    print("\nIf Arabic looks broken (reversed letters / weird symbols): try another source file, "
          "or OCR the PDF (e.g. `ocrmypdf -l ara in.pdf out.pdf`) and re-run.")
