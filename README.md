# WITNESS

**Every claim, with proof.** WITNESS checks an AI answer sentence by sentence against source documents. Each claim is marked 🟢 supported, 🟡 unsupported, 🔴 contradicted or ⚪ needs review, and links to the exact source sentence as proof.

> Draft README. Work in progress during the hackathon.

## How it works

1. **Retrieve**: hybrid search (BM25 + MiniLM embeddings, reciprocal rank fusion) finds the relevant handbook passages.
2. **Answer**: Gemma 4 E2B, running locally in LM Studio, writes a short answer from those passages. You can also paste any AI's answer instead.
3. **Split**: the answer is split into one claim per sentence.
4. **Judge**: two independent judges label each claim:
   - Judge 1: Gemma 4 31B through the Gemini API (one call for all claims).
   - Judge 2: an NLI cross-encoder (`cross-encoder/nli-deberta-v3-small`) running locally on CPU.
5. **Combine**: when the judges disagree, the claim is marked "needs review" instead of guessing.
6. **Fix it**: a corrected answer keeps only the supported claims, each with its source sentence ID.

## Models used

| Model | Role | Where it is called |
|---|---|---|
| Gemma 4 31B (`gemma-4-31b-it`), via the Gemini API | Judge 1 (fact-checker) | `backend/witness/judge_gemma.py` |
| Gemma 4 E2B (`gemma-4-e2b-it`), via LM Studio, local | Answer writer | `backend/witness/generator.py` |

## Run the backend

Requires Python 3.11+ and LM Studio serving Gemma 4 E2B at `http://localhost:1234/v1`.

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
copy .env.example .env        # then add your GEMINI_API_KEY
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m uvicorn server:app --host 0.0.0.0 --port 8000
```

Then open `http://localhost:8000/api/health`. The API is described in `REQUIREMENTS.md §5`.

## Knowledge base

`backend/data/handbook/*.md`: pages copied from the MLH Hacktoberfest Host Handbook and the MLH Standard Hackathon Rules. The source URL is on line 1 of each file.

## License

Apache-2.0, see `LICENSE`.
