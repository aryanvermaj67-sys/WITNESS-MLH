import json

import pytest

from witness import judge_gemma
from witness.fixit import fixed_answer
from witness.models import Claim, FinalVerdict, JudgeVerdict, Passage, Sentence
from witness.verdict import COMBINE, combine, trust

PASSAGES = [Passage(id="p1", doc="d.md", text="A one. B two.",
                    sentences=[Sentence(id="p1.s1", text="A one."), Sentence(id="p1.s2", text="B two.")])]
CLAIMS = [Claim(id="c1", text="Claim number one here.", start=0, end=22),
          Claim(id="c2", text="Claim number two here.", start=23, end=45)]


def jv(judge, label, evidence=(), explanation="why", cid="c1"):
    return JudgeVerdict(claim_id=cid, judge=judge, label=label, evidence_ids=list(evidence), explanation=explanation,
                        confidence=None if judge == "gemma" else 0.9)


# ---- combine rule (§7): every row -------------------------------------------------------------
@pytest.mark.parametrize("pair,final", sorted(COMBINE.items()))
def test_combine_every_two_judge_row(pair, final):
    v = combine("c1", jv("gemma", pair[0]), jv("nli", pair[1]))
    assert (v.label, v.single_judge) == (final, False)


def test_combine_table_is_complete():
    labels = ("supported", "unsupported", "contradicted")
    assert set(COMBINE) == {(g, n) for g in labels for n in labels}


@pytest.mark.parametrize("label", ["supported", "unsupported", "contradicted"])
def test_combine_single_judge_rows(label):
    assert (combine("c1", jv("gemma", label), None).label, combine("c1", jv("gemma", label), None).single_judge) == (label, True)
    assert (combine("c1", None, jv("nli", label)).label, combine("c1", None, jv("nli", label)).single_judge) == (label, True)


def test_combine_no_judge_needs_review():
    v = combine("c1", None, None)
    assert (v.label, v.single_judge, v.evidence_ids) == ("needs_review", True, [])
    assert v.explanation


def test_combine_evidence_and_explanation_rules():
    v = combine("c1", jv("gemma", "supported", ["p1.s2", "p1.s1"], "gemma says"), jv("nli", "supported", ["p1.s1", "p1.s3"], "nli says"))
    assert v.evidence_ids == ["p1.s2", "p1.s1", "p1.s3"]  # Gemma's first, then NLI's, no duplicates
    assert v.explanation == "gemma says"
    assert combine("c1", None, jv("nli", "supported", ["p1.s1"], "nli says")).explanation == "nli says"


def test_trust_counts_and_percent():
    vs = [combine(f"c{i}", jv("gemma", lab, cid=f"c{i}"), None) for i, lab in
          enumerate(["supported", "supported", "unsupported", "contradicted", "contradicted"], 1)]
    t = trust(vs)
    assert (t.supported, t.unsupported, t.contradicted, t.needs_review, t.total, t.percent_supported) == (2, 1, 2, 0, 5, 40)
    assert trust([]).percent_supported == 0 and trust([]).total == 0


# ---- fix-it (FR-10) ---------------------------------------------------------------------------
def test_fixit_keeps_only_supported_with_first_evidence():
    vs = [combine("c1", jv("gemma", "supported", ["p1.s2", "p1.s1"], cid="c1"), None),
          combine("c2", jv("gemma", "contradicted", ["p1.s1"], cid="c2"), None)]
    assert fixed_answer(CLAIMS, vs) == "Claim number one here. [p1.s2]"
    assert fixed_answer(CLAIMS, [vs[1]]) == ""


def test_fixit_supported_without_evidence_has_no_chip():
    v = combine("c1", jv("gemma", "supported", []), None)
    assert fixed_answer(CLAIMS[:1], [v]) == "Claim number one here."


# ---- Gemma reply parser (§9.2) ----------------------------------------------------------------
GOOD = [{"claim_id": "c1", "label": "contradicted", "evidence_ids": ["p1.s1"], "explanation": " Opposite. "},
        {"claim_id": "c2", "label": "unsupported", "evidence_ids": [], "explanation": "Not stated."}]


def test_parse_clean_json():
    v, err = judge_gemma.parse(json.dumps(GOOD), CLAIMS, PASSAGES)
    assert err is None and set(v) == {"c1", "c2"}
    assert (v["c1"].label, v["c1"].evidence_ids, v["c1"].explanation, v["c1"].judge, v["c1"].confidence) == ("contradicted", ["p1.s1"], "Opposite.", "gemma", None)


def test_parse_json_wrapped_in_prose_and_fences():
    for raw in ("Sure! Here you go:\n" + json.dumps(GOOD) + "\nHope that helps.", "```json\n" + json.dumps(GOOD) + "\n```"):
        v, err = judge_gemma.parse(raw, CLAIMS, PASSAGES)
        assert err is None and set(v) == {"c1", "c2"}


def test_parse_unknown_claim_ids_ignored_and_unknown_evidence_dropped():
    raw = json.dumps([{"claim_id": "c9", "label": "supported", "evidence_ids": [], "explanation": "x"},
                      {"claim_id": "c1", "label": "supported", "evidence_ids": ["p1.s1", "p9.s9", "p1.s1"], "explanation": "x"}])
    v, err = judge_gemma.parse(raw, CLAIMS, PASSAGES)
    assert err is None and set(v) == {"c1"} and v["c1"].evidence_ids == ["p1.s1"]


def test_parse_bad_label_means_that_claim_has_no_verdict():
    raw = json.dumps([{"claim_id": "c1", "label": "maybe", "evidence_ids": [], "explanation": "x"}, GOOD[1]])
    v, err = judge_gemma.parse(raw, CLAIMS, PASSAGES)
    assert err is None and set(v) == {"c2"}


def test_parse_duplicate_claim_first_wins():
    raw = json.dumps([GOOD[0], {**GOOD[0], "label": "supported"}])
    assert judge_gemma.parse(raw, CLAIMS, PASSAGES)[0]["c1"].label == "contradicted"


@pytest.mark.parametrize("raw", ["", "garbage", "[not json]", '{"claim_id": "c1"}', "] [", None, "[1, 2, 3]x"])
def test_parse_garbage_gives_no_verdicts(raw):
    v, err = judge_gemma.parse(raw, CLAIMS, PASSAGES)
    assert v == {}
    if raw != "[1, 2, 3]x":
        assert err


# ---- the Gemini call: one call, retries, never raises -----------------------------------------
class ApiError(Exception):
    def __init__(self, code):
        super().__init__(f"{code} boom")
        self.code = code


class Reply:
    def __init__(self, text):
        self.text = text


class FakeClient:
    def __init__(self, outcomes):
        self.outcomes, self.calls, self.configs = list(outcomes), 0, []
        self.models = self

    def generate_content(self, model, contents, config):
        self.calls += 1
        self.configs.append(config)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return Reply(outcome)


def run_judge(client, clock=None):
    kwargs = {"clock": clock} if clock else {}
    return judge_gemma.judge(PASSAGES, CLAIMS, client=client, sleep=lambda s: None, **kwargs)


def test_judge_makes_exactly_one_call_for_all_claims():
    client = FakeClient([json.dumps(GOOD)])
    v, errors = run_judge(client)
    assert client.calls == 1 and errors == [] and set(v) == {"c1", "c2"}


def test_judge_retries_on_5xx_then_succeeds():
    client = FakeClient([ApiError(500), ApiError(503), json.dumps(GOOD)])
    v, errors = run_judge(client)
    assert client.calls == 3 and errors == [] and set(v) == {"c1", "c2"}


def test_judge_gives_up_with_readable_error_and_no_key():
    client = FakeClient([ApiError(503)] * judge_gemma.MAX_ATTEMPTS)
    v, errors = run_judge(client)
    assert v == {} and client.calls == judge_gemma.MAX_ATTEMPTS
    assert len(errors) == 1 and "did not answer" in errors[0] and "503" in errors[0]


def test_judge_400_retries_once_without_thinking_setting():
    client = FakeClient([ApiError(400), json.dumps(GOOD)])
    v, errors = run_judge(client)
    assert client.calls == 2 and errors == [] and set(v) == {"c1", "c2"}
    assert client.configs[0].thinking_config is not None and client.configs[1].thinking_config is None


def test_judge_other_client_error_is_not_retried():
    client = FakeClient([ApiError(401)])
    v, errors = run_judge(client)
    assert client.calls == 1 and v == {} and errors


def test_judge_stops_when_budget_is_spent():
    ticks = iter([0, 0, 100, 100, 100])  # deadline set at 0+BUDGET, then the clock jumps past it
    client = FakeClient([ApiError(503)] * 4)
    v, errors = run_judge(client, clock=lambda: next(ticks))
    assert client.calls == 1 and v == {} and errors


def test_judge_unreadable_reply_is_an_error_not_a_crash():
    v, errors = run_judge(FakeClient(["no json here"]))
    assert v == {} and len(errors) == 1


def test_judge_skips_the_call_when_there_are_no_claims_or_no_key(monkeypatch):
    client = FakeClient([])
    assert judge_gemma.judge(PASSAGES, [], client=client) == ({}, []) and client.calls == 0
    monkeypatch.setattr(judge_gemma.settings, "GEMINI_API_KEY", judge_gemma.settings.GEMINI_API_KEY.__class__(""))
    v, errors = judge_gemma.judge(PASSAGES, CLAIMS)
    assert v == {} and "key" in errors[0].lower()
