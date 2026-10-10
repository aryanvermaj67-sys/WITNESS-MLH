"""Smoke check: python -m witness.smoke [--live]

Default (run by scripts/phase-push.ps1 on every push): offline and fast. Validates the data files and the replay cache,
then prints a one-screen summary of the first demo question's CACHED result. Exit 1 if anything is broken.
--live: runs the real pipeline (LM Studio + Gemini + NLI) on the first demo question instead.
"""
import json
import sys

from pydantic import TypeAdapter

from witness import cache
from witness.config import BACKEND, settings
from witness.models import BackupAnswer, DemoQuestion, PipelineResult, ReplayEntry

ICON = {"supported": "OK ", "unsupported": "?? ", "contradicted": "XX ", "needs_review": "!! "}


def check_files() -> tuple[list[DemoQuestion], list[str]]:
    """(demo questions, problems)."""
    problems = []
    data = BACKEND / "data"
    questions = TypeAdapter(list[DemoQuestion]).validate_json((data / "demo_questions.json").read_bytes())
    if (data / "backup_answers.json").exists():
        TypeAdapter(list[BackupAnswer]).validate_json((data / "backup_answers.json").read_bytes())
    index_file = cache._dir() / "index.json"
    entries = TypeAdapter(list[ReplayEntry]).validate_json(index_file.read_bytes()) if index_file.exists() else []
    problems += [f"cache entry {e.key} is listed in index.json but does not load" for e in entries
                 if cache.load_result(e.key) is None]
    problems += [f"demo question {q.id} has no cached result" for q in questions
                 if cache.load_result(cache.key_for(q.question, None)) is None]
    if not questions:
        problems.append("data/demo_questions.json is empty")
    return questions, problems


def summary(result: PipelineResult) -> str:
    lines = [f"[{result.mode}] {result.question}", f"answer: {result.answer_text or '(none)'}",
             f"trust: {result.trust.percent_supported} % supported  ({result.trust.supported} supported, "
             f"{result.trust.unsupported} unsupported, {result.trust.contradicted} contradicted, "
             f"{result.trust.needs_review} needs review)"]
    for c, v in zip(result.claims, result.verdicts):
        lines.append(f"  {ICON[v.label]}{c.id} {v.label:13s} {c.text}  {v.evidence_ids}")
    lines.append("timings: " + ", ".join(f"{k} {v:.2f} s" for k, v in result.timings.items()))
    lines += [f"error: {e}" for e in result.errors]
    return "\n".join(lines)


def live(question: str) -> PipelineResult:
    from witness import judge_nli, pipeline  # model code is imported only for --live
    from witness.kb import load_kb
    from witness.retrieval import Retriever, load_embedder

    passages, titles = load_kb(settings.path(settings.KB_DIR))
    retriever = Retriever(passages, titles, load_embedder(settings.EMBED_MODEL))
    return pipeline.run_pipeline(question, None, retriever, judge_nli.load_model(settings.NLI_MODEL, settings.NLI_DEVICE))


def main(argv: list[str]) -> int:
    try:
        questions, problems = check_files()
    except (OSError, ValueError) as e:
        print(f"SMOKE FAILED: a data file is missing or invalid ({type(e).__name__}: {str(e)[:200]})")
        return 1
    if problems:
        print("SMOKE FAILED:\n" + "\n".join(f"  {p}" for p in problems))
        return 1
    question = questions[0].question
    result = live(question) if "--live" in argv else cache.load_result(cache.key_for(question, None))
    print(summary(result))
    print(f"SMOKE OK: {len(questions)} demo questions, {len(cache.load_index())} cached results"
          + ("" if "--live" in argv else " (offline; --live runs the real pipeline)"))
    return 1 if "--live" in argv and result.errors else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
