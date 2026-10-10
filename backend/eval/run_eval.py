"""Judge accuracy on the labelled claims (FR-19). Run from backend/: python -m eval.run_eval
Needs the Gemini key (judge 1) and the cached NLI + MiniLM models; LM Studio is not used.

For each line of eval/claims.jsonl: retrieve with the claim's question, run both judges, compare with `gold`.
Claims are grouped by question (same passages, like the real pipeline), at most 10 per Gemma call.
Combined = the final label after the combine rule; needs_review counts as NOT correct.
"""
import json
import sys
from datetime import datetime
from pathlib import Path

from witness import judge_gemma, judge_nli, verdict
from witness.config import BACKEND, settings
from witness.models import Claim, EvalResult

CLAIMS = BACKEND / "eval" / "claims.jsonl"
RESULTS = BACKEND / "eval" / "results.json"
GOLD_LABELS = ("supported", "unsupported", "contradicted")
BATCH = 10


class GemmaFailed(Exception):
    pass


def judge_all(rows: list[dict], retriever, nli_model) -> list[dict]:
    """One record per row: {question, claim, gold, gemma, nli, final} (labels; None when a judge gave no verdict)."""
    records = [dict(r, gemma=None, nli=None, final=None) for r in rows]
    by_question: dict[str, list[int]] = {}
    for i, r in enumerate(rows):
        by_question.setdefault(r["question"], []).append(i)
    for question, indexes in by_question.items():
        passages = retriever.search(question, settings.TOP_K, settings.RRF_K)
        for start in range(0, len(indexes), BATCH):
            batch = indexes[start:start + BATCH]
            claims = [Claim(id=f"c{n}", text=rows[i]["claim"], start=0, end=len(rows[i]["claim"]))
                      for n, i in enumerate(batch, 1)]
            gemma, errors = judge_gemma.judge(passages, claims)
            if errors and not gemma:  # judge_gemma already retried: stop instead of hammering the API
                raise GemmaFailed(f"{question!r}: {errors}")
            nli = judge_nli.judge(passages, claims, nli_model, retriever.related)
            for c, i in zip(claims, batch):
                g, n = gemma.get(c.id), nli.get(c.id)
                records[i].update(gemma=g and g.label, nli=n and n.label, final=verdict.combine(c.id, g, n).label)
    return records


def summarize(records: list[dict]) -> EvalResult:
    rows = []
    for judge, name in (("gemma", "gemma"), ("nli", "nli"), ("combined", "final")):
        for label in ("overall", *GOLD_LABELS):
            subset = [r for r in records if label == "overall" or r["gold"] == label]
            correct = sum(r[name] == r["gold"] for r in subset)
            rows.append({"judge": judge, "label": label, "accuracy": round(correct / len(subset), 3) if subset else 0.0,
                         "correct": correct, "n": len(subset)})
    review = sum(r["final"] == "needs_review" for r in records)
    missing = sum(r["gemma"] is None for r in records)
    note = (f"Gold labels are DRAFT: not yet double-checked by a second person. Combined: {review} of {len(records)} "
            f"claims ended as needs_review and count as not correct. Judge 1 {settings.GEMINI_MODEL}"
            f"{f' ({missing} claims without a Gemma verdict)' if missing else ''}, judge 2 {settings.NLI_MODEL}; "
            f"evidence = top {settings.TOP_K} passages retrieved with each claim's question.")
    return EvalResult(is_example=False, note=note, n_claims=len(records),
                      generated_at=datetime.now().isoformat(timespec="seconds"), rows=rows,
                      per_label={label: {"n": sum(r["gold"] == label for r in records)} for label in GOLD_LABELS})


def main() -> int:
    from witness.kb import load_kb
    from witness.retrieval import Retriever, load_embedder

    rows = [json.loads(line) for line in CLAIMS.read_text("utf-8").splitlines() if line.strip()]
    passages, titles = load_kb(settings.path(settings.KB_DIR))
    retriever = Retriever(passages, titles, load_embedder(settings.EMBED_MODEL))
    try:
        records = judge_all(rows, retriever, judge_nli.load_model(settings.NLI_MODEL, settings.NLI_DEVICE))
    except GemmaFailed as e:
        print(f"STOPPED: the Gemma judge failed after its retries, results.json not written.\n{e}")
        return 1
    result = summarize(records)
    RESULTS.write_text(result.model_dump_json(indent=2) + "\n", "utf-8")

    print(f"WITNESS eval: {result.n_claims} claims, judge 1 {settings.GEMINI_MODEL} -> {RESULTS.name}")
    print(f"{'judge':10s}" + "".join(f"{label:>16s}" for label in ("overall", *GOLD_LABELS)))
    for judge in ("gemma", "nli", "combined"):
        cells = [r for r in result.rows if r.judge == judge]
        print(f"{judge:10s}" + "".join(f"{f'{r.accuracy:.0%} ({r.correct}/{r.n})':>16s}" for r in cells))
    print(result.note)
    print("\nWrong (gold | gemma | nli | combined):")
    for r in records:
        if r["final"] != r["gold"] or r["gemma"] != r["gold"] or r["nli"] != r["gold"]:
            print(f"  {r['gold']:12s} | {str(r['gemma']):12s} | {str(r['nli']):12s} | {str(r['final']):12s} | {r['claim']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
