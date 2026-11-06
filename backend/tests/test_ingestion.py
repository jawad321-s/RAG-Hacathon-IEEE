from app.ingestion.arabic import clean_text, normalize_for_search, tokenize
from app.ingestion.chunker import chunk_pages
from app.ingestion.loaders import PageContent


def test_normalization_unifies_arabic_variants():
    assert normalize_for_search("أحمد") == normalize_for_search("احمد") == normalize_for_search("إحمد")
    assert normalize_for_search("مدرسة") == normalize_for_search("مدرسه")
    assert normalize_for_search("مُحَمَّد") == "محمد"
    assert normalize_for_search("٢٠٢٦") == "2026"


def test_clean_text_removes_tatweel_and_presentation_forms():
    assert clean_text("العـــربية") == "العربية"
    assert clean_text("ﻧﺸﺮﺓ") == "نشرة"  # PDF presentation forms -> normal letters


def test_tokenize_drops_stopwords_and_strips_al():
    toks = tokenize("ما هي شروط التسجيل في الجامعة؟")
    assert "في" not in toks and "ما" not in toks
    assert "تسجيل" in toks and "جامعه" in toks


def test_chunker_respects_size_and_keeps_metadata():
    text = "\n\n".join(f"## المادة {i}\n" + ("جملة تجريبية طويلة. " * 30) for i in range(1, 6))
    chunks = chunk_pages([PageContent(text=text, source="doc.pdf", page=3)], size=400, overlap=50)
    assert len(chunks) > 5
    assert all(len(c.text) <= 400 + 60 for c in chunks)
    assert all(c.metadata["source"] == "doc.pdf" and c.metadata["page"] == 3 for c in chunks)
    assert chunks[0].metadata["section"].startswith("المادة")
    assert len({c.id for c in chunks}) == len(chunks)


def test_tables_are_kept_whole():
    table = "[جدول / Table]\n| a | b |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |"
    chunks = chunk_pages([PageContent(text="مقدمة قصيرة\n\n" + table, source="t.pdf", page=1)], size=900)
    tables = [c for c in chunks if c.metadata["is_table"]]
    assert len(tables) == 1 and "| 3 | 4 |" in tables[0].text


def test_translate_pages_to_arabic_with_cache(monkeypatch, tmp_path):
    """English pages are translated (once, then served from cache); Arabic pages pass through."""
    from app.generation import llm as llm_mod
    from app.ingestion import translate as tr

    calls = []

    class Fake:
        configured = True

        def complete(self, messages, **kw):
            calls.append(messages[-1]["content"])
            return llm_mod.LLMResult(text="الري بالتنقيط (drip irrigation) يوفر 40% من الماء.", model="fake")

    monkeypatch.setattr(tr, "get_llm", lambda: Fake())
    monkeypatch.setattr(tr, "_cache_path", lambda d: tmp_path / f"{d}.json")
    pages = [
        PageContent(text="Drip irrigation saves 40% of water.", source="fao.pdf", page=3),
        PageContent(text="الزيتون يحتاج إلى ري منتظم.", source="ar.pdf", page=1),
    ]
    out = tr.translate_pages(pages, "ar")
    assert out[0].text.startswith("الري بالتنقيط") and out[0].metadata["translated"] is True
    assert out[0].metadata["original_text"] == "Drip irrigation saves 40% of water."
    assert out[1] is pages[1]
    tr.translate_pages(pages, "ar")
    assert len(calls) == 1  # second run hit the cache

    chunks = chunk_pages(out, size=900)
    assert chunks[0].metadata["translated"] is True and "Drip" in chunks[0].metadata["original_text"]
