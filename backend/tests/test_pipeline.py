import pytest
from fastapi.testclient import TestClient

import server
from witness import generator, judge_gemma, judge_nli, pipeline
from witness.models import JudgeVerdict, Passage, PipelineResult, Sentence

PASSAGES = [Passage(id="p1", doc="d.md", text="All development work must start at the event. Each team gives a 5-minute demo.",
                    sentences=[Sentence(id="p1.s1", text="All development work must start at the event."),
                               Sentence(id="p1.s2", text="Each team gives a 5-minute demo.")])]
ANSWER = "You can start a week early. Each team gives a 5-minute demo."


class FakeRetriever:
    def search(self, query, top_k, rrf_k):
        return PASSAGES


def gemma_verdicts(passages, claims):
    labels = {"c1": ("contradicted", ["p1.s1"]), "c2": ("supported", ["p1.s2"])}
    return {c.id: JudgeVerdict(claim_id=c.id, judge="gemma", label=labels[c.id][0], evidence_ids=labels[c.id][1],
                               explanation="because", confidence=None) for c in claims}, []


@pytest.fixture
def live(monkeypatch):
    monkeypatch.setattr(generator, "generate", lambda q, p: (ANSWER, None))
    monkeypatch.setattr(judge_gemma, "judge", gemma_verdicts)


def test_full_run(live):
    r = pipeline.run_pipeline("Can we start early?", None, FakeRetriever())
    assert (r.mode, r.answer_source, r.errors) == ("live", "gemma-4-e2b-local", [])
    assert all(r.answer_text[c.start:c.end] == c.text for c in r.claims) and len(r.claims) == 2
    assert [v.claim_id for v in r.verdicts] == [c.id for c in r.claims]
    assert [v.label for v in r.verdicts] == ["contradicted", "supported"] and all(v.single_judge for v in r.verdicts)  # NLI is a stub until B4
    assert (r.trust.supported, r.trust.contradicted, r.trust.total, r.trust.percent_supported) == (1, 1, 2, 50)
    assert r.fixed_answer == "Each team gives a 5-minute demo. [p1.s2]"
    assert set(r.timings) == {"retrieve", "generate", "judge_gemma", "judge_nli", "total"}
    PipelineResult.model_validate(r.model_dump())


def test_pasted_answer_skips_generation(monkeypatch):
    def boom(*a):
        raise AssertionError("generation must be skipped for a pasted answer")
    monkeypatch.setattr(generator, "generate", boom)
    monkeypatch.setattr(judge_gemma, "judge", gemma_verdicts)
    r = pipeline.run_pipeline("q", ANSWER, FakeRetriever())
    assert (r.answer_source, r.answer_text, r.timings["generate"]) == ("pasted", ANSWER, 0.0)
    assert len(r.claims) == 2 and r.errors == []


def test_lm_studio_unreachable_gives_a_result_with_an_error(monkeypatch):
    class Down:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    raise ConnectionError("refused")
    # the real generator, with an OpenAI client that cannot connect, through the real pipeline
    monkeypatch.setattr(generator, "OpenAI", lambda **kw: Down())
    r = pipeline.run_pipeline("q", None, FakeRetriever())
    assert r.answer_text == "" and r.claims == [] and r.verdicts == [] and r.trust.total == 0 and r.fixed_answer == ""
    assert len(r.errors) == 1 and "LM Studio is not reachable" in r.errors[0]
    assert r.passages == PASSAGES  # retrieval still worked


def test_writer_timeout_and_http_errors_get_their_own_messages(monkeypatch):
    import httpx
    import openai

    def failing(exc):
        class C:
            class chat:
                class completions:
                    @staticmethod
                    def create(**kw):
                        raise exc
        return C()

    req = httpx.Request("POST", "http://localhost:1234/v1/chat/completions")
    answer, error = generator.generate("q", PASSAGES, client=failing(openai.APITimeoutError(request=req)))
    assert answer == "" and "did not answer within" in error and "loading" in error
    resp = httpx.Response(404, request=req)
    answer, error = generator.generate("q", PASSAGES, client=failing(openai.NotFoundError("no model", response=resp, body=None)))
    assert answer == "" and "HTTP 404" in error
    answer, error = generator.generate("q", PASSAGES, client=failing(ConnectionError("refused")))
    assert answer == "" and "not reachable" in error


def test_empty_writer_answer_is_an_error(monkeypatch):
    class Empty:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    class Msg: content = ""
                    class Choice: message = Msg()
                    class Reply: choices = [Choice()]
                    return Reply()
    monkeypatch.setattr(generator, "OpenAI", lambda **kw: Empty())
    r = pipeline.run_pipeline("q", None, FakeRetriever())
    assert r.claims == [] and "empty answer" in r.errors[0]


def test_writer_call_sends_the_required_settings(monkeypatch):
    seen = {}

    class Spy:
        class chat:
            class completions:
                @staticmethod
                def create(**kw):
                    seen.update(kw)
                    class Msg: content = " Line one.\n\n Line two. "
                    class Choice: message = Msg()
                    class Reply: choices = [Choice()]
                    return Reply()
    answer, error = generator.generate("What?", PASSAGES, client=Spy())
    assert (answer, error) == ("Line one. Line two.", None)
    assert seen["extra_body"] == {"reasoning_effort": "none"} and seen["temperature"] == 0 and seen["max_tokens"] == 200
    assert seen["messages"][1]["content"] == f"[p1] {PASSAGES[0].text}\n\nQuestion: What?"


def test_gemini_failure_keeps_the_result_and_flags_every_claim(monkeypatch):
    monkeypatch.setattr(generator, "generate", lambda q, p: (ANSWER, None))
    monkeypatch.setattr(judge_gemma, "judge", lambda p, c: ({}, ["Gemma judge did not answer (HTTP 503)."]))
    r = pipeline.run_pipeline("q", None, FakeRetriever())
    assert len(r.claims) == 2 and r.errors == ["Gemma judge did not answer (HTTP 503)."]
    assert all(v.label == "needs_review" and v.single_judge for v in r.verdicts)
    assert r.trust.needs_review == 2 and r.fixed_answer == ""


def test_a_crashing_step_is_caught(monkeypatch):
    monkeypatch.setattr(generator, "generate", lambda q, p: (ANSWER, None))
    monkeypatch.setattr(judge_gemma, "judge", lambda p, c: 1 / 0)
    monkeypatch.setattr(judge_nli, "judge", lambda p, c: 1 / 0)
    r = pipeline.run_pipeline("q", None, FakeRetriever())
    assert len(r.errors) == 2 and len(r.verdicts) == 2


# ---- HTTP: /api/check always answers 200 with a full PipelineResult -----------------------------
def test_check_endpoint_live_pasted_and_replay(live):
    server.app.state.retriever = FakeRetriever()
    client = TestClient(server.app)
    live_res = client.post("/api/check", json={"question": "q"})
    assert live_res.status_code == 200 and live_res.json()["answer_source"] == "gemma-4-e2b-local"
    assert PipelineResult.model_validate(live_res.json())
    pasted = client.post("/api/check", json={"question": "q", "answer_text": ANSWER}).json()
    assert pasted["answer_source"] == "pasted" and pasted["timings"]["generate"] == 0
    assert client.post("/api/check", json={"question": "q", "mode": "replay"}).json()["mode"] == "replay"


def test_check_endpoint_without_a_loaded_index_is_still_200(live):  # `live` mocks both model clients: no network in tests
    if hasattr(server.app.state, "retriever"):
        del server.app.state.retriever
    r = TestClient(server.app).post("/api/check", json={"question": "q", "answer_text": ANSWER})
    assert r.status_code == 200 and r.json()["errors"] and r.json()["passages"] == []
