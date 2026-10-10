import json
from pathlib import Path

import pytest
from pydantic import TypeAdapter

from witness.models import BackupAnswer, DemoQuestion, EvalResult, Health, PipelineResult, ReplayEntry

EXAMPLES = Path(__file__).resolve().parents[2] / "contracts" / "examples"

SCHEMAS = {
    "health.json": Health,
    "demo_questions.json": list[DemoQuestion],
    "eval.json": EvalResult,
    "backup_answers.json": list[BackupAnswer],
    "replay_index.json": list[ReplayEntry],
}


def schema_for(name):
    return PipelineResult if name.startswith("check_") else SCHEMAS[name]


@pytest.mark.parametrize("path", sorted(EXAMPLES.glob("*.json")), ids=lambda p: p.name)
def test_example_validates(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    parsed = TypeAdapter(schema_for(path.name)).validate_python(data)
    if isinstance(parsed, PipelineResult):
        # §4 rules the frontend relies on
        assert [v.claim_id for v in parsed.verdicts] == [c.id for c in parsed.claims]
        assert all(parsed.answer_text[c.start:c.end] == c.text for c in parsed.claims)


def test_all_examples_found():
    # a wrong path would make the parametrized test above collect nothing and pass
    assert len(list(EXAMPLES.glob("*.json"))) == 11
