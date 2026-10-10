import json

import pytest
from fastapi.testclient import TestClient

import server
from eval import run_eval
from witness import judge_gemma, judge_nli, smoke
from witness.config import BACKEND, settings
from witness.models import EvalResult, JudgeVerdict

from tests.test_pipeline import PASSAGES, FakeRetriever


def fake_verdict(judge, cid, label):
    return JudgeVerdict(claim_id=cid, judge=judge, label=label, evidence_ids=[], explanation="x",
                        confidence=None if judge == "gemma" else 0.9)


def test_summarize_counts_needs_review_as_wrong():
    records = [
        {"gold": "supported", "gemma": "supported", "nli": "supported", "final": "supported"},
        {"gold": "supported", "gemma": "supported", "nli": "contradicted", "final": "needs_review"},
        {"gold": "contradicted", "gemma": "contradicted", "nli": "unsupported", "final": "contradicted"},
        {"gold": "unsupported", "gemma": None, "nli": "unsupported", "final": "unsupported"},
    ]
    result = run_eval.summarize(records)
    rows = {(r.judge, r.label): (r.correct, r.n, r.accuracy) for r in result.rows}
    assert rows[("gemma", "overall")] == (3, 4, 0.75)
    assert rows[("nli", "overall")] == (2, 4, 0.5)
    assert rows[("combined", "overall")] == (3, 4, 0.75)
    assert rows[("combined", "supported")] == (1, 2, 0.5)
    assert rows[("nli", "contradicted")] == (0, 1, 0.0)
    assert result.model_dump()["per_label"] == {"supported": {"n": 2}, "unsupported": {"n": 1}, "contradicted": {"n": 1}}
    assert not result.is_example and result.n_claims == 4 and "DRAFT" in result.note and "1 of 4" in result.note
    EvalResult.model_validate(result.model_dump())


def test_judge_all_batches_by_question_and_combines(monkeypatch):
    calls = []

    def gemma(passages, claims):
        calls.append(len(claims))
        return {c.id: fake_verdict("gemma", c.id, "supported") for c in claims}, []
    monkeypatch.setattr(judge_gemma, "judge", gemma)
    monkeypatch.setattr(judge_nli, "judge", lambda p, cs, m, r: {c.id: fake_verdict("nli", c.id, "contradicted") for c in cs})
    rows = [{"question": "q1", "claim": f"claim {i}", "gold": "supported"} for i in range(12)]
    rows.append({"question": "q2", "claim": "other", "gold": "contradicted"})
    records = run_eval.judge_all(rows, FakeRetriever(), None)
    assert calls == [10, 2, 1]  # <= 10 claims per Gemma call, grouped by question
    assert [r["final"] for r in records] == ["needs_review"] * 13  # supported vs contradicted
    assert records[0]["claim"] == "claim 0" and records[0]["gemma"] == "supported" and records[0]["nli"] == "contradicted"


def test_judge_all_stops_when_gemma_fails(monkeypatch):
    monkeypatch.setattr(judge_gemma, "judge", lambda p, c: ({}, ["Gemma judge did not answer (HTTP 503)."]))
    with pytest.raises(run_eval.GemmaFailed):
        run_eval.judge_all([{"question": "q", "claim": "c", "gold": "supported"}], FakeRetriever(), None)


def test_results_file_validates_and_is_served():
    path = BACKEND / "eval" / "results.json"
    if not path.exists():
        pytest.skip("eval/results.json not generated yet (python -m eval.run_eval)")
    result = EvalResult.model_validate_json(path.read_bytes())
    assert result.is_example is False and result.n_claims == len(path.with_name("claims.jsonl").read_text("utf-8").split("\n")) - 1
    assert TestClient(server.app).get("/api/eval").json() == json.loads(path.read_text("utf-8"))


def test_smoke_passes_on_the_real_cache_and_fails_on_a_broken_one(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(settings, "CACHE_DIR", "data/cached")  # read-only use of the committed replay data
    assert smoke.main([]) == 0 and "SMOKE OK" in capsys.readouterr().out
    (tmp_path / "index.json").write_text('[{"key": "gone-123abc", "question": "q", "answer_source": "pasted", '
                                         '"saved_at": "2026-10-10T12:00:00"}]', "utf-8")
    monkeypatch.setattr(settings, "CACHE_DIR", str(tmp_path))
    assert smoke.main([]) == 1 and "gone-123abc" in capsys.readouterr().out
