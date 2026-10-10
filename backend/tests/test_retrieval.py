import json

import pytest

from witness.claims import split_claims
from witness.config import BACKEND, settings
from witness.kb import load_kb
from witness.retrieval import Retriever, load_embedder

KB_DIR = settings.path(settings.KB_DIR)

# demo question id -> phrases; a passage containing any of them answers the question (gold)
GOLD = {
    # q1 is answered by three sources; for this wording the event rule itself ranks ~9th (see PROGRESS, B5 note)
    "q1": ("All development work must start at the event.",
           "All work on a project should be done during the period of the hackathon.",
           "project-specific work happens during the Hack Day"),
    "q2": ("Hacktoberfest Hack Days run for 3 to 12 hours",),
    "q3": ("graduated within the last 12 months",),
    "q10": ("10 billion parameters or fewer",),
    "q11": ("actually uses a Gemma model through the Gemini API",),
    "q17": ("2 minute or less demo video",),
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
    questions = {q["id"]: q["question"] for q in json.loads((BACKEND / "data" / "demo_questions.json").read_text("utf-8"))}
    for qid, phrases in GOLD.items():
        top = retriever.search(questions[qid], settings.TOP_K, settings.RRF_K)
        assert len(top) == settings.TOP_K
        assert any(ph in p.text for p in top for ph in phrases), (qid, [p.id for p in top])
    # same question twice -> same passages (NFR-9)
    assert retriever.search(questions["q1"], 5, 60) == retriever.search(questions["q1"], 5, 60)


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
