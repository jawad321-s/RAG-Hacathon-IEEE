import json

from fastapi.testclient import TestClient


def _client():
    from app.main import app

    return TestClient(app)


def _admin_token(c):
    from app.config import get_settings

    s = get_settings()
    r = c.post("/api/auth/login", json={"email": s.admin_email, "password": s.admin_password})
    assert r.status_code == 200, r.text
    return r.json()["token"]


def test_health_and_public_config(indexed_store):
    with _client() as c:
        assert c.get("/api/health").json()["status"] == "ok"
        cfg = c.get("/api/config/public").json()
        assert cfg["product_name"]


def test_chat_non_stream_with_citations(indexed_store, fake_llm):
    with _client() as c:
        r = c.post("/api/chat", json={"question": "كم ساعة تطوع مطلوبة للتخرج؟", "stream": False})
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["cited"] == [1] and data["sources"] and data["message_id"]


def test_chat_stream_sse(indexed_store, fake_llm):
    with _client() as c:
        with c.stream("POST", "/api/chat", json={"question": "متى تفتح المكتبة؟"}) as r:
            events = [json.loads(line[6:]) for line in r.iter_lines() if line.startswith("data: ")]
    types = [e["type"] for e in events]
    assert types[0] == "sources" and types[-1] == "done" and "token" in types


def test_admin_routes_require_auth(indexed_store):
    with _client() as c:
        assert c.get("/api/analytics").status_code == 401
        token = _admin_token(c)
        r = c.get("/api/analytics", headers={"Authorization": f"Bearer {token}"})
        assert r.status_code == 200 and "kpis" in r.json()


def test_upload_and_delete(indexed_store):
    with _client() as c:
        h = {"Authorization": f"Bearer {_admin_token(c)}"}
        files = {"file": ("note.txt", "سياسة الإجازات: يحق للموظف 14 يوم إجازة سنوية.".encode(), "text/plain")}
        r = c.post("/api/documents/upload", files=files, data={"category": "hr"}, headers=h)
        assert r.status_code == 200 and r.json()["chunks"] >= 1
        assert any(d["source"] == "note.txt" for d in c.get("/api/documents").json()["documents"])
        assert c.delete("/api/documents/note.txt", headers=h).status_code == 200


def test_pii_redaction():
    from app.core.security import redact_pii

    out = redact_pii("رقمي 0599123456 وايميلي a.b@gmail.com")
    assert "0599123456" not in out and "gmail" not in out


def test_answer_language_follows_question():
    """auto: Arabic (incl. dialect) -> Arabic, English -> English; 'ar' forces Arabic."""
    from app.config import get_domain
    from app.generation.generator import build_messages
    from app.generation.prompts import system_prompt

    d = get_domain()
    old = d.answer_language
    try:
        d.answer_language = "auto"
        assert d.answer_lang("How many credit hours is Computer Science?") == "en"
        assert d.answer_lang("قديش ساعة لازم اخلص؟") == "ar"
        assert d.answer_lang("كم ساعة مساق T1111؟") == "ar"
        assert "English only" in system_prompt("en") and d.refusal_message_en in system_prompt("en")
        assert "أجب بالعربية" in system_prompt("ar")
        assert build_messages("How many hours?", [], lang="en")[-1]["content"].endswith("Answer in English.")
        assert d.refusal_for("en") == d.refusal_message_en
        d.answer_language = "ar"
        assert d.answer_lang("How many hours?") == "ar"
        assert "أجب دائماً باللغة العربية" in system_prompt("ar")
    finally:
        d.answer_language = old


def test_utility_calls_use_separate_provider(monkeypatch):
    """Answers go to the main provider; rewrite/translate/judge go to the utility provider."""
    from types import SimpleNamespace

    from app.config import get_settings
    from app.generation.llm import LLM

    s = get_settings()
    monkeypatch.setattr(s, "utility_base_url", "https://utility.example/v1")
    monkeypatch.setattr(s, "llm_mock", False)
    llm = LLM()
    seen = []

    def fake_client(name):
        def create(**kw):
            seen.append((name, kw["model"]))
            msg = SimpleNamespace(content="ok")
            return SimpleNamespace(choices=[SimpleNamespace(message=msg)], model=kw["model"], usage=None)

        return SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))

    llm.client, llm.utility_client = fake_client("main"), fake_client("utility")
    llm.complete([{"role": "user", "content": "x"}])
    llm.complete([{"role": "user", "content": "x"}], utility=True, model="cheap-model")
    assert seen == [("main", s.llm_model), ("utility", "cheap-model")]


def test_free_only_blocks_paid_openrouter_models():
    from app.config import get_settings

    s = get_settings()
    url = "https://openrouter.ai/api/v1"
    assert s.free_only is True
    assert s.paid_model_reason("openai/gpt-4.1-mini", url)
    assert s.paid_model_reason("meta-llama/llama-3.3-70b-instruct:free", url) is None
    assert s.paid_model_reason("gemini-2.5-flash", "https://generativelanguage.googleapis.com/v1beta/openai/") is None


def test_create_drops_rejected_optional_params():
    from types import SimpleNamespace

    from app.generation.llm import LLM

    calls = []

    class BadParam(Exception):
        status_code = 400

    def create(**kw):
        calls.append(sorted(k for k in kw if k not in ("model", "messages")))
        if "reasoning_effort" in kw:
            raise BadParam("unknown parameter")
        return "ok"

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    assert LLM._create(client, {"model": "m", "messages": []}, {"reasoning_effort": "low"}) == "ok"
    assert calls == [["reasoning_effort"], []]
