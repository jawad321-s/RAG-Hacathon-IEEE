"""Document loaders -> list of `PageContent` (one per page / logical section).

Every page keeps its source file name and page number so we can cite
"(المصدر: دليل الطالب.pdf، صفحة 12)" in answers.

Tables in PDFs are extracted separately and rendered as Markdown so the LLM
can read rows/columns instead of a jumble of words.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from dataclasses import dataclass, field
from pathlib import Path

from .arabic import clean_text

log = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".txt", ".md", ".html", ".htm", ".csv", ".json"}


@dataclass
class PageContent:
    text: str
    source: str
    page: int | None = None
    metadata: dict = field(default_factory=dict)


def _table_to_markdown(rows: list[list]) -> str:
    rows = [[("" if c is None else str(c).replace("\n", " ").strip()) for c in r] for r in rows]
    rows = [r for r in rows if any(r)]
    if not rows:
        return ""
    width = max(len(r) for r in rows)
    rows = [r + [""] * (width - len(r)) for r in rows]
    header, *body = rows
    lines = ["| " + " | ".join(header) + " |", "|" + "---|" * width]
    lines += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(lines)


def load_pdf(path: Path) -> list[PageContent]:
    import pymupdf

    pages: list[PageContent] = []
    with pymupdf.open(path) as doc:
        meta = {k: v for k, v in (doc.metadata or {}).items() if v and k in ("title", "author")}
        for i, page in enumerate(doc, start=1):
            parts: list[str] = []
            table_md: list[str] = []
            try:
                tables = page.find_tables()
                for t in tables.tables:
                    md = _table_to_markdown(t.extract())
                    if md:
                        table_md.append(md)
            except Exception as exc:  # table detection is best-effort
                log.debug("table extraction failed on %s p%s: %s", path.name, i, exc)

            # sort=True gives natural reading order; works fine for RTL Arabic text.
            text = page.get_text("text", sort=True)
            if text.strip():
                parts.append(text)
            if table_md:
                parts.append("\n\n".join(f"[جدول / Table]\n{md}" for md in table_md))

            content = clean_text("\n\n".join(parts))
            if len(content) < 20 and not table_md:
                # Probably a scanned page. OCR hook: plug pytesseract / an OCR API here.
                log.warning("Page %s of %s has almost no text (scanned?)", i, path.name)
                continue
            pages.append(
                PageContent(
                    text=content,
                    source=path.name,
                    page=i,
                    metadata={**meta, "has_table": bool(table_md)},
                )
            )
    return pages


def load_docx(path: Path) -> list[PageContent]:
    import docx
    from docx.table import Table
    from docx.text.paragraph import Paragraph

    d = docx.Document(str(path))
    blocks: list[str] = []
    # Walk the body in document order so tables stay next to their headings.
    for el in d.element.body.iterchildren():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag == "p":
            p = Paragraph(el, d)
            if p.text.strip():
                style = (p.style.name or "").lower() if p.style else ""
                prefix = "## " if style.startswith(("heading", "title")) else ""
                blocks.append(prefix + p.text.strip())
        elif tag == "tbl":
            rows = [[c.text for c in r.cells] for r in Table(el, d).rows]
            md = _table_to_markdown(rows)
            if md:
                blocks.append(f"[جدول / Table]\n{md}")
    return [PageContent(text=clean_text("\n\n".join(blocks)), source=path.name, page=None)]


def load_text(path: Path) -> list[PageContent]:
    return [PageContent(text=clean_text(path.read_text(encoding="utf-8", errors="ignore")), source=path.name)]


def load_html(path: Path) -> list[PageContent]:
    from bs4 import BeautifulSoup

    soup = BeautifulSoup(path.read_text(encoding="utf-8", errors="ignore"), "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    title = soup.title.get_text(strip=True) if soup.title else ""
    return [
        PageContent(
            text=clean_text(soup.get_text("\n")),
            source=path.name,
            metadata={"title": title} if title else {},
        )
    ]


def load_csv(path: Path) -> list[PageContent]:
    """Each row becomes a 'key: value' record — great for FAQs / catalogs."""
    text = path.read_text(encoding="utf-8-sig", errors="ignore")
    reader = csv.DictReader(io.StringIO(text))
    records = []
    for i, row in enumerate(reader, start=1):
        rec = "\n".join(f"{k}: {v}" for k, v in row.items() if k and v)
        if rec.strip():
            records.append(PageContent(text=clean_text(rec), source=path.name, page=i, metadata={"row": i}))
    return records


def load_json(path: Path) -> list[PageContent]:
    """Accepts a list of objects ({"text"/"content", ...metadata}) or a single object."""
    data = json.loads(path.read_text(encoding="utf-8"))
    items = data if isinstance(data, list) else [data]
    out = []
    for i, item in enumerate(items, start=1):
        if isinstance(item, dict):
            text = item.get("text") or item.get("content") or json.dumps(item, ensure_ascii=False)
            meta = {k: v for k, v in item.items() if k not in ("text", "content") and isinstance(v, (str, int, float, bool))}
        else:
            text, meta = str(item), {}
        out.append(PageContent(text=clean_text(text), source=path.name, page=i, metadata=meta))
    return out


LOADERS = {
    ".pdf": load_pdf,
    ".docx": load_docx,
    ".txt": load_text,
    ".md": load_text,
    ".html": load_html,
    ".htm": load_html,
    ".csv": load_csv,
    ".json": load_json,
}


def load_document(path: Path) -> list[PageContent]:
    ext = path.suffix.lower()
    if ext not in LOADERS:
        raise ValueError(f"Unsupported file type: {ext}. Supported: {sorted(SUPPORTED_EXTENSIONS)}")
    pages = LOADERS[ext](path)
    return [p for p in pages if p.text.strip()]
