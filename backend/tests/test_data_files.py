import json
from pathlib import Path

from pydantic import TypeAdapter

from witness.models import DemoQuestion

BACKEND = Path(__file__).resolve().parents[1]


def test_handbook_files_start_with_url():
    files = sorted((BACKEND / "data" / "handbook").glob("*.md"))
    assert len(files) >= 4
    for f in files:
        assert f.read_text(encoding="utf-8").splitlines()[0].startswith("https://"), f.name


def test_demo_questions_match_contract():
    TypeAdapter(list[DemoQuestion]).validate_json((BACKEND / "data" / "demo_questions.json").read_bytes())


def test_eval_claims():
    lines = (BACKEND / "eval" / "claims.jsonl").read_text(encoding="utf-8").splitlines()
    rows = [json.loads(l) for l in lines if l.strip()]
    assert len(rows) >= 40
    assert all(set(r) == {"question", "claim", "gold"} for r in rows)
    assert {r["gold"] for r in rows} == {"supported", "unsupported", "contradicted"}
