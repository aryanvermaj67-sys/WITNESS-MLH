import time

import numpy as np
import pytest

from witness import judge_nli
from witness.config import settings
from witness.kb import load_kb
from witness.models import Claim, Passage, Sentence
from witness.retrieval import Retriever, load_embedder

S = {f"p1.s{i}": f"Sentence {i}." for i in range(1, 5)}
PASSAGES = [Passage(id="p1", doc="d.md", text=" ".join(S.values()),
                    sentences=[Sentence(id=i, text=t) for i, t in S.items()])]
NEUTRAL = (0.05, 0.05, 0.90)  # (contradiction, entailment, neutral) probabilities

# claim -> [(sentence id, similarity, probabilities)] as related() would return them
CASES = {
    "entailment beats a related contradiction": [("p1.s1", 0.90, (0.02, 0.96, 0.02)), ("p1.s2", 0.90, (0.99, 0.005, 0.005))],
    "unrelated contradiction is ignored": [("p1.s1", 0.80, (0.10, 0.20, 0.70)), ("p1.s3", 0.30, (0.999, 0.0005, 0.0005))],
    "related contradiction counts": [("p1.s2", 0.60, (0.999, 0.0005, 0.0005)), ("p1.s1", 0.20, NEUTRAL)],
    "similarity exactly at the gate": [("p1.s2", 0.55, (0.93, 0.02, 0.05))],
    "similarity just under the gate": [("p1.s2", 0.54, (0.93, 0.02, 0.05))],
    "nothing related, nothing entailed": [("p1.s4", 0.10, (0.31, 0.10, 0.59))],
    "entailment below threshold": [("p1.s1", 0.90, (0.20, 0.65, 0.15))],
}


class FakeModel:
    """Fixed logits; its label order differs from the real model, so the judge must read id2label."""
    class config:
        id2label = {"0": "neutral", "1": "CONTRADICTION", "2": "entailment"}

    def __init__(self):
        self.calls = []

    def predict(self, pairs, **kw):
        self.calls.append(list(pairs))
        out = []
        for premise, claim in pairs:
            c, e, n = next(p for sid, _, p in CASES[claim] if S[sid] == premise)
            out.append(np.log([n, c, e]) + 3.0)  # logits: any constant shift gives the same softmax
        return np.array(out)


def fake_related(text, sentence_ids, k):
    assert sentence_ids == list(S)  # the judge offers every retrieved sentence
    return [(sid, sim) for sid, sim, _ in CASES[text]][:k]


def claims(*texts):
    return [Claim(id=f"c{i}", text=t, start=0, end=len(t)) for i, t in enumerate(texts, 1)]


@pytest.fixture(autouse=True)
def nli_settings(monkeypatch):
    for name, value in [("NLI_ENTAIL_THRESHOLD", 0.70), ("NLI_CONTRA_THRESHOLD", 0.70),
                        ("NLI_RELATED_K", 3), ("NLI_RELATED_MIN_SIM", 0.55)]:
        monkeypatch.setattr(settings, name, value)


def test_decision_rule_one_batch_and_strings():
    model = FakeModel()
    out = judge_nli.judge(PASSAGES, claims(*CASES), model, fake_related)
    got = {c: (v.label, v.evidence_ids, v.confidence, v.explanation) for c, v in out.items()}
    assert got == {
        "c1": ("supported", ["p1.s1"], 0.96, "entailment 0.96"),  # entailment is checked first
        "c2": ("unsupported", [], 0.2, "no sentence above threshold (entail 0.20, contra 0.10)"),  # s3: sim 0.30
        "c3": ("contradicted", ["p1.s2"], 1.0, "contradiction 1.00"),
        "c4": ("contradicted", ["p1.s2"], 0.93, "contradiction 0.93"),  # >= gate counts
        "c5": ("unsupported", [], 0.02, "no sentence above threshold (entail 0.02, contra 0.00)"),
        "c6": ("unsupported", [], 0.1, "no sentence above threshold (entail 0.10, contra 0.00)"),
        "c7": ("unsupported", [], 0.65, "no sentence above threshold (entail 0.65, contra 0.20)"),
    }
    assert all(v.judge == "nli" and v.claim_id == c for c, v in out.items())
    assert len(model.calls) == 1  # one batch for all claims, only the related pairs
    assert len(model.calls[0]) == sum(len(v) for v in CASES.values())
    assert model.calls[0][0] == (S["p1.s1"], "entailment beats a related contradiction")  # (premise, hypothesis)


def test_k_is_passed_and_respected(monkeypatch):
    monkeypatch.setattr(settings, "NLI_RELATED_K", 1)
    seen, model = [], FakeModel()

    def spy(text, ids, k):
        seen.append(k)
        return fake_related(text, ids, k)
    out = judge_nli.judge(PASSAGES, claims("entailment beats a related contradiction"), model, spy)
    assert seen == [1] and len(model.calls[0]) == 1 and out["c1"].label == "supported"


def test_failures_return_empty():
    class Broken(FakeModel):
        def predict(self, pairs, **kw):
            raise RuntimeError("boom")
    one = claims("related contradiction counts")
    assert judge_nli.judge(PASSAGES, one, Broken(), fake_related) == {}
    assert judge_nli.judge(PASSAGES, one, None, fake_related) == {}
    assert judge_nli.judge(PASSAGES, one, FakeModel(), None) == {}
    assert judge_nli.judge([], one, FakeModel(), fake_related) == {}
    assert judge_nli.judge(PASSAGES, [], FakeModel(), fake_related) == {}


def test_retriever_related_top_k_by_cosine():
    vectors = {"A.": [1.0, 0.0], "B.": [0.6, 0.8], "C.": [0.0, 1.0], "D.": [0.6, 0.8], "q": [1.0, 0.0]}

    class FakeEmbedder:
        def encode(self, x, normalize_embeddings=True):
            vec = lambda t: np.array(vectors.get(t, [0.0, 0.0]))
            return vec(x) if isinstance(x, str) else np.array([vec(t) for t in x])
    sents = [Sentence(id=f"p1.s{i}", text=t) for i, t in enumerate(["A.", "B.", "C.", "D."], 1)]
    passages = [Passage(id="p1", doc="d.md", text="A. B. C. D.", sentences=sents)]
    r = Retriever(passages, {"p1": "t"}, FakeEmbedder())
    got = r.related("q", ["p1.s3", "p1.s4", "p1.s2", "p1.s1"], 2)
    assert [(i, round(s, 2)) for i, s in got] == [("p1.s1", 1.0), ("p1.s4", 0.6)]  # tie B/D: given order


# ---- real cached models (offline) --------------------------------------------------------------
@pytest.fixture(scope="module")
def real():
    try:
        model = judge_nli.load_model(settings.NLI_MODEL, settings.NLI_DEVICE)
        passages, titles = load_kb(settings.path(settings.KB_DIR))
        return model, Retriever(passages, titles, load_embedder(settings.EMBED_MODEL))
    except Exception as e:
        pytest.skip(f"NLI or MiniLM model is not in the local Hugging Face cache ({type(e).__name__}); "
                    "download them once with network access to run this test.")


def test_real_model_contradiction_and_entailment(real):
    model, _ = real
    rule = "All development work must start at the event."
    passages = [Passage(id="p1", doc="d.md", text=rule, sentences=[Sentence(id="p1.s1", text=rule)])]
    out = judge_nli.judge(passages, claims("You can start building a week before the event.",
                                           "Development work has to begin at the event."), model,
                          lambda text, ids, k: [("p1.s1", 1.0)])
    assert (out["c1"].label, out["c1"].evidence_ids) == ("contradicted", ["p1.s1"]), out["c1"]
    assert (out["c2"].label, out["c2"].evidence_ids) == ("supported", ["p1.s1"]), out["c2"]


def test_real_kb_claims_and_speed(real):
    model, retriever = real
    passages = retriever.search("Can we start working on our project before the event?", settings.TOP_K, settings.RRF_K)
    expected = {
        "All development work must start at the event.": "supported",
        "Each team gives a 10-minute demo.": "contradicted",
        "Pizza is served at midnight for every team.": "unsupported",
        "Projects must be pushed to a public GitHub repository under an open-source license.": "supported",
        "Teams must stop hacking once the time is up.": "supported",  # 5th claim for the 5-claim timing
    }
    cs = claims(*expected)
    judge_nli.judge(passages, cs[:1], model, retriever.related)  # warm-up
    t = time.perf_counter()
    out = judge_nli.judge(passages, cs, model, retriever.related)
    seconds = time.perf_counter() - t
    print(f"\nNLI: 5 claims x {len(passages)} passages scored in {seconds:.2f} s on {settings.NLI_DEVICE}")
    got = {c.text: (out[c.id].label, out[c.id].explanation, out[c.id].evidence_ids) for c in cs}
    assert {k: v[0] for k, v in got.items()} == expected, got
    assert seconds < 1.0
