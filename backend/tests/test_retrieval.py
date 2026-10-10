import json

import pytest

from witness.claims import split_claims
from witness.config import BACKEND, settings
from witness.kb import load_kb
from witness.retrieval import Retriever, load_embedder

KB_DIR = settings.path(settings.KB_DIR)

# question -> phrases; a passage containing any of them answers the question (gold)
GOLD = {
    # the 3 verified demo questions (data/demo_questions.json, Phase B5)
    "Can we start working on our project before the event?": ("All development work must start at the event.",),
    "Can we still submit our project after demos have started?": ("close them at the project deadline, before demos begin",),
    "Does an agent skill entry have to follow a particular standard?": ("An agent skill must comply with the Agent Skill Open Standard.",),
    # earlier candidates, kept as retrieval checks
    "How long does a Hacktoberfest Hack Day run?": ("Hacktoberfest Hack Days run for 3 to 12 hours",),
    "Can someone who graduated from university last year still take part as a student?": ("graduated within the last 12 months",),
    "What counts as a small language model for the open-source AI challenge?": ("10 billion parameters or fewer",),
    "What do judges check before choosing the Gemma challenge winner?": ("actually uses a Gemma model through the Gemini API",),
    "How long can the demo video be at MLH digital events?": ("2 minute or less demo video",),
}

def test_kb_passages_and_stable_ids():
    passages, titles = load_kb(KB_DIR)
    assert len(passages) >= 20
    ids = [s.id for p in passages for s in p.sentences]
    assert len(ids) == len(set(ids))
    assert all(s.id.startswith(p.id + ".s") for p in passages for s in p.sentences)
    assert all(p.text == " ".join(s.text for s in p.sentences) for p in passages)
    assert all(len(p.text.split()) <= 150 for p in passages)
    assert set(titles) == {p.id for p in passages}
    assert load_kb(KB_DIR) == (passages, titles)


@pytest.fixture(scope="module")
def retriever():
    passages, titles = load_kb(KB_DIR)
    return Retriever(passages, titles, load_embedder(settings.EMBED_MODEL))


def test_gold_passage_in_top_k(retriever):
    demo = [q["question"] for q in json.loads((BACKEND / "data" / "demo_questions.json").read_text("utf-8"))]
    assert set(demo) <= set(GOLD), "every demo question needs a gold passage here (FR-2)"
    for question, phrases in GOLD.items():
        top = retriever.search(question, settings.TOP_K, settings.RRF_K)
        assert len(top) == settings.TOP_K
        assert any(ph in p.text for p in top for ph in phrases), (question, [p.id for p in top])
    # same question twice -> same passages (NFR-9)
    assert retriever.search(demo[0], 5, 60) == retriever.search(demo[0], 5, 60)


def test_claim_offsets_slice_exactly():
    answer = ("  No, you cannot start early.\nAll development work must start at the event!  Teams must push to a "
              "public GitHub repo, e.g. GitHub. Short one. 1. Demos last 5 minutes? - Bullet claims count as well.")
    claims = split_claims(answer)
    assert [c.text for c in claims] == [
        "No, you cannot start early.",
        "All development work must start at the event!",
        "Teams must push to a public GitHub repo, e.g. GitHub.",
        "Demos last 5 minutes?",
        "Bullet claims count as well.",
    ]
    assert all(answer[c.start:c.end] == c.text for c in claims)
    assert [c.id for c in claims] == ["c1", "c2", "c3", "c4", "c5"]
    assert split_claims("") == []
