import time

import pytest
from fastapi.testclient import TestClient

import server
from witness import cache, generator, judge_gemma
from witness.config import settings
from witness.models import Health, PipelineResult

from tests.test_pipeline import ANSWER, FakeNLI, FakeRetriever, gemma_verdicts


@pytest.fixture
def client(monkeypatch):
    # both model clients mocked: no LM Studio, no Gemini
    monkeypatch.setattr(generator, "generate", lambda q, p: (ANSWER, None))
    monkeypatch.setattr(judge_gemma, "judge", gemma_verdicts)
    monkeypatch.setattr(server.app.state, "retriever", FakeRetriever(), raising=False)
    monkeypatch.setattr(server.app.state, "nli", FakeNLI(), raising=False)
    return TestClient(server.app)


def test_key_is_stable_and_safe():
    k = cache.key_for("Can we start coding before the hackathon day, and what do we need to submit?", None)
    assert k == cache.key_for("Can we start coding before the hackathon day, and what do we need to submit?", "")
    assert k.startswith("can-we-start-coding-before-the-hackathon-day-and-w") and len(k) <= 50 + 7
    assert k != cache.key_for("Can we start coding before the hackathon day, and what do we need to submit?", "pasted")
    assert cache.key_for("¿¿??", None).startswith("q-")


def test_save_load_index_and_bad_keys(client):
    live = client.post("/api/check", json={"question": "Can we start early?"}).json()  # live run saves itself
    key = cache.key_for("Can we start early?", None)
    loaded = cache.load_result(key)
    assert loaded.mode == "replay" and loaded.model_dump() == {**live, "mode": "replay"}
    assert [e.key for e in cache.load_index()] == [key]
    client.post("/api/check", json={"question": "Can we start early?"})  # same key again: replaced, not duplicated
    client.post("/api/check", json={"question": "Can we start early?", "answer_text": ANSWER})
    index = cache.load_index()
    assert [e.answer_source for e in index] == ["gemma-4-e2b-local", "pasted"] and len({e.key for e in index}) == 2
    for bad in ["../server", "..", "a/b", "a\\b", "index", "UPPER"]:
        assert cache.load_result(bad) is None, bad
    assert client.get("/api/replay/..%2F..%2Fserver").status_code == 404


def test_replay_round_trip_and_missing(client):
    q = {"question": "Can we start early?"}
    assert client.post("/api/check", json={**q, "mode": "replay"}).json()["errors"] == ["No saved result for this question."]
    live = client.post("/api/check", json=q).json()
    t = time.perf_counter()
    replay = client.post("/api/check", json={**q, "mode": "replay"})
    ms = (time.perf_counter() - t) * 1000
    print(f"\nreplay /api/check answered in {ms:.1f} ms")
    assert replay.status_code == 200 and replay.json() == {**live, "mode": "replay"} and ms < 200
    entries = client.get("/api/replay").json()
    assert client.get(f"/api/replay/{entries[0]['key']}").json() == {**live, "mode": "replay"}

    missing = client.post("/api/check", json={"question": "Never asked?", "answer_text": "x", "mode": "replay"})
    body = PipelineResult.model_validate(missing.json())
    assert missing.status_code == 200 and body.mode == "replay" and body.claims == [] and body.answer_source == "pasted"


def test_offline_replay_default_and_failed_save(client, monkeypatch):
    monkeypatch.setattr(settings, "OFFLINE_REPLAY", True)
    assert client.post("/api/check", json={"question": "q"}).json()["mode"] == "replay"  # mode null -> replay
    monkeypatch.setattr(settings, "OFFLINE_REPLAY", False)

    def broken(result):
        raise OSError("disk full")
    monkeypatch.setattr(cache, "save_result", broken)
    r = client.post("/api/check", json={"question": "q"})
    assert r.status_code == 200 and r.json()["errors"] == ["This result could not be saved for replay (OSError)."]


def test_generation_error_is_not_cached(client, monkeypatch):
    monkeypatch.setattr(generator, "generate", lambda q, p: ("", "LM Studio is not reachable."))
    client.post("/api/check", json={"question": "q"})
    assert cache.load_index() == []


def test_health_shape_and_speed(client):
    t = time.perf_counter()
    r = client.get("/api/health")
    ms = (time.perf_counter() - t) * 1000
    print(f"\n/api/health answered in {ms:.1f} ms")
    h = Health.model_validate(r.json())
    assert ms < 300 and h.status == "ok" and h.nli_loaded and h.embeddings_loaded and h.kb_passages == 1
    assert h.replay_default == settings.OFFLINE_REPLAY and settings.GEMINI_MODEL in h.models.judge_1
    assert "api_key" not in r.text.lower() and "AIza" not in r.text  # never the key itself


def test_spa_fallback_never_swallows_api(client, monkeypatch, tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<p>placeholder app</p>", "utf-8")
    (tmp_path / "assets" / "app.js").write_text("console.log(1)", "utf-8")
    (tmp_path.parent / "secret.txt").write_text("outside", "utf-8")
    monkeypatch.setattr(settings, "FRONTEND_DIST", str(tmp_path / "missing"))
    assert client.get("/").status_code == 404  # no build: nothing served at /
    monkeypatch.setattr(settings, "FRONTEND_DIST", str(tmp_path))
    assert "placeholder" in client.get("/").text
    assert "placeholder" in client.get("/results/c3").text  # SPA fallback
    assert client.get("/assets/app.js").text == "console.log(1)"
    assert "outside" not in client.get("/..%2Fsecret.txt").text
    for path in ["/api/nope", "/api", "/api/replay/nope"]:
        r = client.get(path)
        assert r.status_code == 404 and r.headers["content-type"] == "application/json", path
    assert client.get("/api/demo-questions").status_code == 200
