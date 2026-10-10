"""Saved results for replay (FR-12): data/cached/{key}.json + index.json (ReplayEntry list)."""
import hashlib
import json
import re
from datetime import datetime

from witness import verdict
from witness.config import settings
from witness.models import PipelineResult, ReplayEntry

_KEY = re.compile(r"[a-z0-9-]{1,80}")  # every key_for() key; anything else ("/", "\", "..") is rejected


def key_for(question: str, answer_text: str | None) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", question.lower()).strip("-")[:50].strip("-") or "q"
    digest = hashlib.sha1((question + (answer_text or "")).encode("utf-8")).hexdigest()[:6]
    return f"{slug}-{digest}"


def _dir():
    return settings.path(settings.CACHE_DIR)


def load_index() -> list[ReplayEntry]:
    try:
        return [ReplayEntry.model_validate(e) for e in json.loads((_dir() / "index.json").read_text("utf-8"))]
    except (OSError, ValueError):  # missing or unreadable index: nothing to replay
        return []


def save_result(result: PipelineResult) -> str:
    """Save a live result (stored with mode "live") and add it to the index; returns its key."""
    key = key_for(result.question, result.answer_text if result.answer_source == "pasted" else None)
    folder = _dir()
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{key}.json").write_text(result.model_copy(update={"mode": "live"}).model_dump_json(indent=2), "utf-8")
    entry = ReplayEntry(key=key, question=result.question, answer_source=result.answer_source,
                        saved_at=datetime.now().isoformat(timespec="seconds"))
    index = [e for e in load_index() if e.key != key] + [entry]
    (folder / "index.json").write_text(json.dumps([e.model_dump() for e in index], indent=2), "utf-8")
    return key


def load_result(key: str) -> PipelineResult | None:
    """The saved result with mode "replay", or None if the key is invalid or not saved."""
    if not _KEY.fullmatch(key):
        return None
    try:
        result = PipelineResult.model_validate_json((_dir() / f"{key}.json").read_text("utf-8"))
    except (OSError, ValueError):
        return None
    return result.model_copy(update={"mode": "replay"})


def missing(question: str, answer_text: str | None) -> PipelineResult:
    """The §5 rule 2 answer when replay has nothing saved: an empty result, HTTP 200."""
    return PipelineResult(question=question, answer_text=answer_text or "",
                          answer_source="pasted" if answer_text else "gemma-4-e2b-local", passages=[], claims=[],
                          verdicts=[], trust=verdict.trust([]), fixed_answer="",
                          timings={k: 0.0 for k in ("retrieve", "generate", "judge_gemma", "judge_nli", "total")},
                          errors=["No saved result for this question."], mode="replay")
