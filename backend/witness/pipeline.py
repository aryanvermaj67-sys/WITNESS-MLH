"""Pipeline: retrieve → generate (skipped for pasted answers) → claims → judges → combine → trust → fix-it (FR-11).

Every step is wrapped: a failure becomes a readable string in `errors`, never an exception (§5 rule 4).
Judge/generator functions are looked up on their modules at call time, so tests can replace them.
"""
import threading
import time

from witness import cache, fixit, generator, judge_gemma, judge_nli, verdict
from witness.claims import split_claims
from witness.config import settings
from witness.models import PipelineResult

SOFT_LIMIT = 60.0  # seconds (§5 rule 7)
_LOCK = threading.Lock()  # one live check at a time; a second request waits (§5 rule 6)


def run_pipeline(question: str, answer_text: str | None, retriever, nli_model=None) -> PipelineResult:
    with _LOCK:
        return _run(question, answer_text, retriever, nli_model)


def _run(question, answer_text, retriever, nli_model) -> PipelineResult:
    started, errors, timings = time.perf_counter(), [], {"retrieve": 0.0, "generate": 0.0, "judge_gemma": 0.0, "judge_nli": 0.0}

    def timed(name, label, fn, fallback):
        t = time.perf_counter()
        try:
            return fn()
        except Exception as e:  # the step's own failure is reported once, here
            errors.append(f"The {label} step failed ({type(e).__name__}).")
            return fallback
        finally:
            timings[name] = round(time.perf_counter() - t, 2)

    passages = timed("retrieve", "search", lambda: retriever.search(question, settings.TOP_K, settings.RRF_K), [])

    pasted, gen_error = bool(answer_text), None
    if pasted:
        answer = answer_text
    else:
        answer, gen_error = timed("generate", "answer writer", lambda: generator.generate(question, passages), ("", None))
        if gen_error:
            errors.append(gen_error)

    claims = split_claims(answer) if answer else []
    gemma, gemma_errors = timed("judge_gemma", "Gemma judge", lambda: judge_gemma.judge(passages, claims), ({}, []))
    errors += gemma_errors
    nli = timed("judge_nli", "NLI judge", lambda: judge_nli.judge(passages, claims, nli_model, getattr(retriever, "related", None)), None)
    if nli is None:  # it crashed; timed() already reported it
        nli = {}
    elif claims and passages and not nli:  # judge_nli never raises: {} means it could not judge
        errors.append("The NLI judge returned no verdicts" + (" (model not loaded)." if nli_model is None else "."))

    verdicts = [verdict.combine(c.id, gemma.get(c.id), nli.get(c.id)) for c in claims]
    total = time.perf_counter() - started
    if total > SOFT_LIMIT:
        errors.append(f"The check took {total:.0f} s, longer than the {SOFT_LIMIT:.0f} s limit.")
    result = PipelineResult(
        question=question, answer_text=answer, answer_source="pasted" if pasted else "gemma-4-e2b-local",
        passages=passages, claims=claims, verdicts=verdicts, trust=verdict.trust(verdicts),
        fixed_answer=fixit.fixed_answer(claims, verdicts), timings={**timings, "total": round(total, 2)},
        errors=errors, mode="live")
    if claims and not gen_error:  # §5 rule 5
        try:
            cache.save_result(result)
        except Exception as e:  # a failed save never breaks the response
            result.errors.append(f"This result could not be saved for replay ({type(e).__name__}).")
    return result
