from app.retrieval.retriever import reciprocal_rank_fusion, retrieve
from app.retrieval.vectorstore import Hit


def test_rrf_rewards_agreement():
    a = [Hit("x", "", {}), Hit("y", "", {})]
    b = [Hit("y", "", {}), Hit("z", "", {})]
    fused = reciprocal_rank_fusion([a, b], [0.5, 0.5])
    assert fused[0].id == "y"


def test_sample_corpus_indexed(indexed_store):
    assert indexed_store.count() > 5
    sources = {d["source"] for d in indexed_store.list_sources()}
    assert {"student_guide.md", "faq.csv", "fees_2026.docx"} <= sources


def test_bm25_finds_exact_terms(indexed_store):
    r = retrieve("كم سعر الساعة المعتمدة في كلية الهندسة", use_rewrite=False)
    assert any("الهندسة" in h.text for h in r.hits[:3])


def test_metadata_filter(indexed_store):
    r = retrieve("المكتبة", filters={"source": "faq.csv"}, use_rewrite=False)
    assert r.hits and all(h.metadata["source"] == "faq.csv" for h in r.hits)


def test_rbac_category_list_filter(indexed_store):
    r = retrieve("المكتبة", filters={"source": ["faq.csv", "student_guide.md"]}, use_rewrite=False)
    assert r.hits and all(h.metadata["source"] in ("faq.csv", "student_guide.md") for h in r.hits)


def test_embedding_cache_embeds_each_text_once(tmp_path):
    from app.retrieval.embeddings import CachedEmbedder, HashEmbedder

    class Counting(HashEmbedder):
        calls = 0

        def embed_documents(self, texts):
            Counting.calls += len(texts)
            return super().embed_documents(texts)

    e = CachedEmbedder(Counting(), tmp_path / "c.sqlite")
    a = e.embed_documents(["نص أول", "نص ثاني"])
    b = e.embed_documents(["نص ثاني", "نص ثالث"])
    assert Counting.calls == 3 and a[1] == b[0]
