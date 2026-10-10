---
name: witness-verify
description: "Use when you need to check whether an answer is supported by source documents: WITNESS splits the answer into one claim per sentence and labels each claim supported, unsupported, contradicted or needs_review, with the exact source sentence IDs as evidence."
---

# witness-verify

Checks an answer against the WITNESS knowledge base (`backend/data/handbook/*.md`) sentence by sentence and prints the
full result as JSON.

## When to use

- You have a question and an answer (yours, or another AI's) and need to know which sentences the sources support.
- You want evidence: every verdict cites sentence IDs such as `p7.s1` that point into the retrieved passages.

## How to run

From the `backend/` folder of the WITNESS repository:

```
.venv/Scripts/python skill/witness-verify/scripts/verify.py "Can we start working on our project before the event?"
.venv/Scripts/python skill/witness-verify/scripts/verify.py "Can we reuse old code?" --answer "Yes, any old code is fine."
```

- Without `--answer`, the local writer model answers the question first, then the answer is checked.
- With `--answer`, the given text is checked as it is (nothing is generated).

## Output

One JSON object (the `PipelineResult` from `REQUIREMENTS.md §4`) on stdout:

- `claims`: one per sentence, with `start`/`end` character offsets into `answer_text`.
- `verdicts`: per claim, the final `label`, `evidence_ids`, `explanation`, and both judges' verdicts (`gemma`, `nli`).
- `trust`: counts per label and `percent_supported`.
- `fixed_answer`: only the supported claims, each followed by its first evidence ID.
- `errors`: readable problems (a judge or the writer not reachable). The script still prints a full result.

## What it needs

- The project's Python environment (`backend/.venv`, packages from `backend/requirements.txt`).
- `backend/.env` with `GEMINI_API_KEY` for judge 1 (Gemma 4 via the Gemini API). Without it, claims are judged by the
  local NLI model only and `errors` says so.
- The NLI model (`cross-encoder/nli-deberta-v3-small`) and the embedding model (`sentence-transformers/all-MiniLM-L6-v2`)
  in the local Hugging Face cache; they run on CPU.
- LM Studio serving Gemma 4 E2B at `LMSTUDIO_BASE_URL` (default `http://localhost:1234/v1`), only when no `--answer` is
  given.

Like the server, each run that produces claims is also saved to `backend/data/cached/` for replay.
