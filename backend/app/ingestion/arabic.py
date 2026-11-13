"""Arabic text normalization.

Two levels:
- `clean_text`      : light cleaning applied to stored chunk text (what the user sees).
- `normalize_for_search`: aggressive normalization used ONLY for BM25 tokens and
  query matching, so "أحمد / احمد / إحمد" and "مدرسة / مدرسه" match each other.
"""

from __future__ import annotations

import re
import unicodedata

_TASHKEEL = re.compile(r"[ؐ-ًؚ-ٰٟۖ-ۭ]")
_TATWEEL = "ـ"
_ALEF_VARIANTS = re.compile(r"[إأآٱ]")
_MULTI_SPACE = re.compile(r"[ \t ]+")
_MULTI_NEWLINE = re.compile(r"\n{3,}")
_ARABIC_CHAR = re.compile(r"[؀-ۿ]")
_TOKEN = re.compile(r"[A-Za-z0-9_\u0621-\u064A\u0660-\u0669\u0671-\u06D3]+")
_ARABIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹", "01234567890123456789")

# Small Arabic + English stopword list for BM25 (keeps index focused on content words).
STOPWORDS = {
    # Arabic
    "في", "من", "على", "الى", "إلى", "عن", "مع", "هذا", "هذه", "ذلك", "تلك", "التي",
    "الذي", "الذين", "ما", "ماذا", "هل", "او", "أو", "ثم", "كل", "كان", "كانت", "قد",
    "لا", "لم", "لن", "ان", "أن", "إن", "هو", "هي", "هم", "انا", "نحن", "انت", "به",
    "بها", "له", "لها", "عند", "بعد", "قبل", "بين", "حتى", "اذا", "إذا", "كيف", "لماذا",
    "اي", "أي", "و", "ف", "ب", "ل", "يا", "شو", "ايش", "وين", "ليش", "كيفية", "هناك",
    # English
    "the", "a", "an", "of", "to", "in", "on", "for", "and", "or", "is", "are", "was",
    "be", "what", "how", "why", "when", "where", "which", "who", "with", "by", "it",
    "this", "that", "do", "does", "can", "i", "you", "my", "your",
}


def is_arabic(text: str, threshold: float = 0.3) -> bool:
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return False
    return sum(1 for c in letters if _ARABIC_CHAR.match(c)) / len(letters) >= threshold


def clean_text(text: str) -> str:
    """Light cleaning safe for display: unicode NFKC, remove tatweel, fix whitespace."""
    text = unicodedata.normalize("NFKC", text)
    text = text.replace(_TATWEEL, "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Remove soft hyphens / zero-width chars that PDFs love to inject.
    text = re.sub(r"[­​-‏‪-‮⁦-⁩﻿]", "", text)
    text = _MULTI_SPACE.sub(" ", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    text = _MULTI_NEWLINE.sub("\n\n", text)
    return text.strip()


def normalize_for_search(text: str) -> str:
    """Aggressive normalization for lexical matching (never shown to users)."""
    text = clean_text(text).lower()
    text = _TASHKEEL.sub("", text)
    text = _ALEF_VARIANTS.sub("ا", text)
    text = text.replace("ى", "ي").replace("ة", "ه").replace("ؤ", "و").replace("ئ", "ي")
    text = text.translate(_ARABIC_DIGITS)
    return text


def _light_stem(token: str) -> str:
    """Very light Arabic prefix stripping (ال, وال, بال, كال, فال, لل)."""
    for prefix in ("وال", "بال", "كال", "فال", "لل", "ال"):
        if token.startswith(prefix) and len(token) - len(prefix) >= 2:
            return token[len(prefix):]
    return token


def tokenize(text: str) -> list[str]:
    """Tokenizer used by BM25 for both documents and queries."""
    tokens = _TOKEN.findall(normalize_for_search(text))
    return [_light_stem(t) for t in tokens if t not in STOPWORDS and len(t) > 1]
