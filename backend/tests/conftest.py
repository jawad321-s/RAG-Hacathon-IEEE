import os
import shutil
import tempfile
from pathlib import Path

import pytest

_TMP = Path(tempfile.mkdtemp(prefix="rag-test-"))
os.environ.update(
    {
        "APP_ENV": "test",
        "EMBEDDING_PROVIDER": "hash",
        "USE_RERANKER": "false",
        "USE_QUERY_REWRITE": "false",
        "OPENROUTER_API_KEY": "test-key",
        "DATA_DIR": str(_TMP),
        "CHROMA_DIR": str(_TMP / "chroma"),
        "UPLOADS_DIR": str(_TMP / "uploads"),
        "SQLITE_URL": f"sqlite:///{_TMP / 'test.db'}",
        "COLLECTION_NAME": "test",
        "RATE_LIMIT_PER_MINUTE": "1000",
    }
)

SAMPLE_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "sample"


@pytest.fixture(scope="session")
def indexed_store():
    from app.ingestion.pipeline import ingest_directory
    from app.retrieval.vectorstore import get_store

    get_store().reset()
    ingest_directory(SAMPLE_DIR)
    yield get_store()


@pytest.fixture
def fake_llm(monkeypatch):
    """Replace OpenRouter with a deterministic fake that cites source [1]."""
    from app.generation import llm as llm_mod

    class Fake:
        configured = True

        def complete(self, messages, **kw):
            return llm_mod.LLMResult(text="الإجابة من المصدر [1].", model="fake", prompt_tokens=100, completion_tokens=10)

        def stream(self, messages, model=None):
            for t in ["الإجابة ", "من المصدر ", "[1]."]:
                yield t, None
            yield "", {"model": "fake", "prompt_tokens": 100, "completion_tokens": 10, "latency_ms": 5}

    fake = Fake()
    monkeypatch.setattr(llm_mod, "get_llm", lambda: fake)
    import app.generation.generator as gen

    monkeypatch.setattr(gen, "get_llm", lambda: fake)
    return fake


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP, ignore_errors=True)
