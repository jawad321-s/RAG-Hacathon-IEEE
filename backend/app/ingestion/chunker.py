"""Structure-aware recursive chunker.

Strategy (and the answer to the judges' question "why this chunking?"):
- Split on the strongest boundary first: headings / blank lines -> lines ->
  sentences (Arabic + Latin punctuation) -> words. This keeps legal articles,
  FAQ entries and procedure steps intact instead of cutting mid-sentence.
- Target ~900 characters (~150-220 Arabic words): small enough to be precise in
  retrieval, big enough to carry the context the LLM needs to answer.
- 150 character overlap so facts that straddle a boundary are not lost.
- Tables ("[جدول / Table]" blocks) are never split across rows if they fit in one
  chunk; if a table is huge it is split by rows and the header is repeated.
- Each chunk carries source/page/section metadata for citations and filtering.

Tune `chunk_size` / `chunk_overlap` in .env and re-run the evaluation to justify.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field

from .loaders import PageContent

_HEADING = re.compile(
    r"^(#{1,6}\s+.+|(?:المادة|مادة|الفصل|الباب|القسم|البند|Article|Section|Chapter)\s*[\(\[]?[\d٠-٩]+.*)$",
    re.MULTILINE,
)
_SENTENCE_END = re.compile(r"(?<=[\.\!\?؟。؛])\s+")
SEPARATORS = ["\n\n", "\n", "SENTENCE", " "]


@dataclass
class Chunk:
    id: str
    text: str
    metadata: dict = field(default_factory=dict)


def _split(text: str, sep: str) -> list[str]:
    if sep == "SENTENCE":
        return _SENTENCE_END.split(text)
    return text.split(sep)


def _recursive_split(text: str, size: int, seps: list[str]) -> list[str]:
    if len(text) <= size:
        return [text]
    if not seps:
        return [text[i : i + size] for i in range(0, len(text), size)]
    sep, rest = seps[0], seps[1:]
    pieces = [p for p in _split(text, sep) if p.strip()]
    if len(pieces) == 1:
        return _recursive_split(text, size, rest)
    joiner = " " if sep in ("SENTENCE", " ") else sep
    out: list[str] = []
    buf = ""
    for piece in pieces:
        candidate = f"{buf}{joiner}{piece}" if buf else piece
        if len(candidate) <= size:
            buf = candidate
            continue
        if buf:
            out.append(buf)
        if len(piece) > size:
            out.extend(_recursive_split(piece, size, rest))
            buf = ""
        else:
            buf = piece
    if buf:
        out.append(buf)
    return out


def _split_table(table_block: str, size: int) -> list[str]:
    lines = table_block.split("\n")
    title, header, divider, rows = lines[0], lines[1], lines[2], lines[3:]
    head = "\n".join([title, header, divider])
    out, buf = [], []
    for r in rows:
        if buf and len(head) + sum(len(x) + 1 for x in buf) + len(r) > size:
            out.append(head + "\n" + "\n".join(buf))
            buf = []
        buf.append(r)
    if buf:
        out.append(head + "\n" + "\n".join(buf))
    return out


def _add_overlap(pieces: list[str], overlap: int) -> list[str]:
    if overlap <= 0 or len(pieces) < 2:
        return pieces
    out = [pieces[0]]
    for prev, cur in zip(pieces, pieces[1:]):
        tail = prev[-overlap:]
        # start overlap at a word boundary
        sp = tail.find(" ")
        tail = tail[sp + 1 :] if 0 <= sp < len(tail) - 1 else tail
        out.append(f"{tail} … {cur}" if not cur.startswith("[جدول") else cur)
    return out


def _first_heading(text: str) -> str | None:
    """Heading that governs this section (the last one if tiny sections were merged)."""
    found = list(_HEADING.finditer(text))
    if not found or found[0].start() != 0:
        return None
    return found[-1].group(0).lstrip("# ").strip()[:120]


def _split_sections(text: str) -> list[str]:
    """Hard boundaries at headings / legal articles: content of two different
    articles is never merged into one chunk (better precision + cleaner citations).
    Tiny sections (e.g. a heading alone) are glued to the next one."""
    starts = [m.start() for m in _HEADING.finditer(text)]
    if not starts:
        return [text]
    bounds = ([0] if starts[0] > 0 else []) + starts + [len(text)]
    sections = [text[a:b].strip() for a, b in zip(bounds, bounds[1:]) if text[a:b].strip()]
    merged: list[str] = []
    for sec in sections:
        if merged and len(merged[-1]) < 120:
            merged[-1] = f"{merged[-1]}\n\n{sec}"
        else:
            merged.append(sec)
    return merged


_MD_TABLE_HEADER = re.compile(r"^(\|[^\n]*\|)\n(\|\s*:?-{3,}[^\n]*\|)\s*$", re.M)
_H1 = re.compile(r"^#\s+(.+)$", re.M)


def _repeat_table_header(section: str, parts: list[str]) -> list[str]:
    """A long Markdown table split across chunks keeps its header row in every chunk,
    so "| 10100 | الثقافة الاسلامية | 3 |" is still readable as code / name / hours."""
    m = _MD_TABLE_HEADER.search(section)
    if not m:
        return parts
    header = f"{m.group(1)}\n{m.group(2)}"
    return [p if (not p.lstrip().startswith("|") or header in p) else f"{header}\n{p.lstrip()}" for p in parts]


def chunk_pages(pages: list[PageContent], size: int = 900, overlap: int = 150, extra_metadata: dict | None = None) -> list[Chunk]:
    chunks: list[Chunk] = []
    section: str | None = None
    doc_title: str | None = None
    for page in pages:
        # Document title (first "# " heading): prefixed to every chunk so a chunk from the middle
        # of a study plan still says which plan/major it belongs to.
        m = _H1.search(page.text)
        if m:
            doc_title = m.group(1).strip()[:120]
        # Separate tables from prose so tables stay whole.
        blocks = re.split(r"(\[جدول / Table\]\n(?:\|.*\|\n?)+)", page.text)
        pieces: list[tuple[str, str | None]] = []  # (text, section heading in effect)
        for block in blocks:
            if not block.strip():
                continue
            if block.startswith("[جدول / Table]"):
                block = block.strip()
                for t in [block] if len(block) <= size * 1.5 else _split_table(block, size):
                    pieces.append((t, section))
                continue
            for sec in _split_sections(block.strip()):
                heading = _first_heading(sec)
                if heading:
                    section = heading
                parts = _recursive_split(sec, size, SEPARATORS)
                if len(parts) > 1 and _MD_TABLE_HEADER.search(sec):
                    parts = _repeat_table_header(sec, parts)  # table rows: header instead of text overlap
                else:
                    parts = _add_overlap(parts, overlap)
                for part in parts:
                    pieces.append((part, section))

        for idx, (piece, sec_name) in enumerate(pieces):
            meta = {
                "source": page.source,
                "page": page.page if page.page is not None else -1,
                "chunk_index": idx,
                "section": sec_name or "",
                "is_table": piece.startswith("[جدول"),
                "char_len": len(piece),
                **{k: v for k, v in page.metadata.items() if isinstance(v, (str, int, float, bool))},
                **(extra_metadata or {}),
            }
            # Prefix document title + section so the chunk is self-contained for embeddings/LLM.
            labels = [x for x in (doc_title, sec_name) if x and x not in piece[:300]]
            if doc_title and sec_name == doc_title:
                labels = [doc_title] if doc_title not in piece[:300] else []
            text = f"[{' — '.join(labels)}]\n{piece}" if labels else piece
            if doc_title:
                meta["title"] = doc_title
            digest = hashlib.sha1(f"{page.source}|{page.page}|{idx}|{text}".encode()).hexdigest()[:16]
            chunks.append(Chunk(id=digest, text=text, metadata=meta))
    return chunks
