"""Pre-download the embedding + reranker models (do this at home, not on hackathon Wi-Fi!)."""

from app.config import get_settings

if __name__ == "__main__":
    s = get_settings()
    from fastembed import TextEmbedding
    from fastembed.rerank.cross_encoder import TextCrossEncoder

    print(f"Downloading embedding model {s.embedding_model} ...")
    m = TextEmbedding(model_name=s.embedding_model, cache_dir=str(s.models_cache_dir))
    print("  dim =", len(next(iter(m.embed(["اختبار"])))))
    print(f"Downloading reranker {s.reranker_model} ...")
    r = TextCrossEncoder(model_name=s.reranker_model, cache_dir=str(s.models_cache_dir))
    print("  score =", list(r.rerank("ما هو الطقس", ["الطقس مشمس اليوم", "كرة القدم"])))
    print("Done. Models are cached locally.")
