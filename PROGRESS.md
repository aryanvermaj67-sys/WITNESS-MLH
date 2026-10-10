# PROGRESS.md — WITNESS live tracker (two machines)

**How to use this file**
- Each person edits **only their own section** plus single rows in Requests, Blockers, Decisions and the Integration log.
- Tick a box only when its "done when" condition is true.
- AI agents: read this first; continue from your role's first unchecked task; update it after each task.
- `git pull --rebase` before editing; keep edits small.
- Work is organised in **phases** (B0–B6 backend, F0–F5 frontend, then I1 together). Each phase ends with `.\scripts\phase-push.ps1`; tick the phase in the "Phases and pushes" table first. Task IDs are `BT#` / `FT#`; their Phase column says which phase they belong to. Clock times in this file are only a rough guide.

| Role | Person | Machine |
|---|---|---|
| Backend | **Aryan** | Machine 1 (projector on demo day) |
| Frontend | **Mudit** | Machine 2 (backup on demo day) |
| Support | ________ , ________ | any laptop/phone (content only) |

---

## Status board

| Role | Current task | Status | Last update |
|---|---|---|---|
| Aryan | B2 retrieval core (next) | B1 done; contracts frozen | event day |
| Mudit | | not started | |
| Support | | not started | |

## Phases and pushes

A phase is done only when its **push succeeded** (`.\scripts\phase-push.ps1 -Phase <id> -Message "..."`, see `AGENTS.md §1b`). Tick the phase here first, then run the script, so the tick ships in the same commit. Backend and frontend run in parallel; **no live frontend↔backend testing until I1**.

**Backend (Aryan)**

| Phase | Scope | Gate / done when | Pushed (commit) |
|---|---|---|---|
| B0 | Foundation: repo, LICENSE, `.gitignore`, folders, contracts, requirements, `models.py`, contract test | `pytest -q` green, all examples validate | ☑ `c0473e5` |
| B1 | Stub server: every §5 route returns its example | `curl` each route; contracts frozen | ☑ |
| B2 | Retrieval core: `config`, `kb`, `retrieval`, `claims` | ≥ 20 passages, gold in top 5, offsets exact | ☐ |
| B3 | Live pipeline + judge 1 (`generator`, `judge_gemma`, `verdict`, `fixit`, `pipeline`) | `curl POST /api/check` returns a real, contract-valid result | ☐ |
| B4 | Judge 2 (NLI) + pasted answers | `needs_review` possible; pasted answer graded | ☐ |
| B5 | Cache, replay, demo questions, real health, serve `dist` | Replay round trip passes; all routes real | ☐ |
| B6 | Extras: eval, Agent Skill, smoke | `eval/results.json` real; skill prints JSON | ☐ |

**Frontend (Mudit, UI designed in Stitch)**

| Phase | Scope | Gate / done when | Pushed (commit) |
|---|---|---|---|
| F0 | Foundation: Vite + React + TS + Tailwind, tokens, types, mocks, `lib/api.ts` mock mode | Dev server runs; `npm run typecheck` passes | ☐ |
| F1 | Stitch design: one screen per §8.8 state, exported to `frontend/design/stitch/` | All states exported; tokens match §8.2 | ☐ |
| F2 | Core UI on mocks (components + `useWitness`) | `check_mixed.json` renders; claim click shows evidence | ☐ |
| F3 | Features: Grade any AI, fixed answer, before/after, shortcuts, all states | Every §8.8 state OK on its example | ☐ |
| F4 | Replay mode, `sync-replay`, projector mode, < 1280 px layout | Works with no backend; readable at 150 % | ☐ |
| F5 | Extras: `EvalView`, animations | EXAMPLE ribbon works | ☐ |

**Joint**

| Phase | Scope | Gate / done when | Pushed (commit) |
|---|---|---|---|
| I1 | Integration + release, **starts only after B5 and F4**: network test, switch to live, release build, `dist` served at `:8000` | `http://localhost:8000/` works live and in replay | ☐ |
| Final | Feature freeze, two rehearsals, backup video, README + slides, public repo with LICENSE | Two clean 5-minute runs | ☐ |

---

## Tonight (no project code)

**Aryan (Machine 1)**
- [x] Python 3.11; packages from `REQUIREMENTS.md §12` installed in a test venv (then delete the venv or keep it outside the repo) — done with **Python 3.14.6** + `torch==2.9.1`, venv at `backend/.venv` (gitignore it!); see Decisions
- [x] LM Studio installed; Gemma 4 E2B downloaded and loaded; local server started; exact model ID written down — **`gemma-4-e2b-it`** (Q4_K_M, `lmstudio-community/gemma-4-E2B-it-GGUF`), server `http://localhost:1234/v1`
- [ ] Gemini API key created; Gemma 4 31B tried in AI Studio chat; limits checked at aistudio.google.com/rate-limit; backup key from a teammate
- [x] NLI model and MiniLM embedding model downloaded once (so they're cached) — both load on CPU; NLI `id2label` = {0: contradiction, 1: entailment, 2: neutral}
- [x] Node 20+ installed too (backup way to build the frontend) — Node v24.19.0, npm 11.17.0
- [ ] Windows firewall rule for port 8000 ready (`REQUIREMENTS.md §10`)

**Mudit (Machine 2)**
- [ ] Node 20+ and npm; a throwaway `npm create vite` run to warm the npm cache, then delete it
- [ ] Read `REQUIREMENTS.md §4, §5, §8` and the example files in `contracts/examples/`
- [ ] Sketch the layout from §8.3 on paper

**Support**
- [ ] Copy the event description and the MLH Gemma challenge, Open-Source AI challenge and standard rules pages into text files (with URLs)
- [ ] Draft 20 candidate demo questions

**Everyone**
- [ ] Read `PROJECT.md`; know the 30-second pitch
- [ ] Pack: chargers, HDMI adapter, extension cord, phone hotspot, USB drive

---

## Aryan — Backend (Machine 1)

| # | Task | Done when | Phase | ☐ |
|---|---|---|---|---|
| BT1 | Repo, LICENSE, .gitignore, folders, `contracts/examples/` copied | Pushed | B0 | ☑ |
| BT2 | `requirements.txt`, `.env.example`, venv, lock file | Installed, lock committed | B0 | ☑ |
| BT3 | `models.py` + `test_models_match_contracts.py` | All example files validate | B0 | ☑ |
| BT4 | Stub `server.py` returning example files; CORS | `curl` every route returns its example | B1 | ☑ |
| BT5 | `config.py`, `kb.py` | ≥ 20 passages, stable unique IDs | B2 | ☐ |
| BT6 | `retrieval.py` hybrid BM25 + MiniLM + RRF | Gold passage in top 5 | B2 | ☐ |
| BT7 | `generator.py` via LM Studio | Same answer twice | B3 | ☐ |
| BT8 | `claims.py` with offsets | Offsets slice exactly | B2 | ☐ |
| BT9 | `judge_gemma.py` one call, strict parser | Parser tests pass; 1 call per check | B3 | ☐ |
| BT10 | `verdict.py` combine + trust, `fixit.py` | Every combine row tested | B3 | ☐ |
| BT11 | `pipeline.py` + `/api/check` live | `curl POST /api/check` returns a real, contract-valid result | B3 | ☐ |
| BT12 | `judge_nli.py` | < 5 s CPU; id2label read | B4 | ☐ |
| BT13 | Pasted-answer path verified with `curl` | `answer_source="pasted"`, `timings.generate=0` | B4 | ☐ |
| BT14 | `cache.py`, replay routes, `mode` handling | Round-trip test passes | B5 | ☐ |
| BT15 | Demo questions verified with Support; all cached | ≥ 4 reliable questions | B5 | ☐ |
| BT16 | Serve `frontend/dist` (placeholder `index.html` until I1); real `/api/health` | `/` serves a file from `FRONTEND_DIST`; `/api/*` not swallowed | B5 | ☐ |
| BT17 | (extra) `run_eval.py` → `/api/eval` | `is_example: false` results | B6 | ☐ |
| BT18 | (extra) Agent Skill `witness-verify` | Script prints JSON | B6 | ☐ |
| BT19 | Warm-up script before the slot: one live check | Done 10 min before demo | demo | ☐ |

Notes:
- Machine 1 env (pre-event): `backend/.venv` (Python 3.14.6), `backend/requirements.txt` = §12 verbatim, `backend/requirements.lock.txt` = `pip freeze`. Run tools as `backend\.venv\Scripts\python.exe`. Models cached in `~/.cache/huggingface`. B0 done: LICENSE, `.gitignore`, `.env.example`, `pytest.ini` (`pythonpath = .`), `witness/models.py` (unknown fields are rejected, so contract drift fails the test), contract test. Remote: `https://github.com/aryanvermaj67-sys/WITNESS.git`. `data/`, `eval/`, `skill/` are created in the phase that first puts a file in them (git does not track empty folders). `.env` (copy of `.env.example` + key) is still to create before B3.
- B1 done: `server.py` stub, every §5 route returns its example file (verified with curl against uvicorn on 127.0.0.1:8000, bodies identical to the examples); `/api/check` validates per §5 (422), `/api/replay/{key}` 404s for unknown keys; CORS open; empty lifespan hook. `CheckRequest` lives in `models.py`. Route tests in `tests/test_server.py`. **`contracts/` is frozen from here.** Run: `cd backend; .\.venv\Scripts\python.exe -m uvicorn server:app --host 127.0.0.1 --port 8000`.
- Windows **Smart App Control is ON** on this PC and blocks unsigned DLLs with no cloud reputation (`WinError 4551` / "Application Control policy has blocked this file"). Newest torch 2.14.1 was blocked; torch 2.9.1 loads. If it recurs, do not disable SAC mid-event: tell the team, retry the import once, or pin another established torch version.
- First model download hit a Xet CDN network error; retry with env `HF_HUB_DISABLE_XET=1` worked.
- LM Studio: `LMSTUDIO_MODEL=gemma-4-e2b-it`, `LMSTUDIO_BASE_URL=http://localhost:1234/v1`. Loaded with `lms load gemma-4-e2b-it --identifier gemma-4-e2b-it --gpu max --context-length 8192 --parallel 1 -y` (restart server: `lms server start --port 1234`). `--parallel 1` matters: parallel slots split the context window.
- **Gemma 4 E2B is a reasoning model.** With the spec's `max_tokens=200` it burns the whole budget on `reasoning_content` and returns EMPTY `content` (`finish=length`). Sending `reasoning_effort="none"` (OpenAI client: `extra_body={"reasoning_effort": "none"}`) disables it: real answer in ~36 tokens, ~0.4 s warm, identical across 3 runs at temperature 0. `chat_template_kwargs.enable_thinking=false`, `reasoning_effort=minimal/low` did NOT work. `generator.py` must send it, and must treat empty `content` as a failure.
- Mudit/phone-hotspot note: this PC was on a phone hotspot (~0.7-3.5 MB/s); big downloads need `curl -C -` style resume. Windows reports stale file sizes for files still being written, so don't judge progress by `Length`.

## Mudit — Frontend (Machine 2)

| # | Task | Done when | Phase | ☐ |
|---|---|---|---|---|
| FT1 | Vite + React + TS scaffold, fixed deps, Tailwind, fonts | Dev server runs | F0 | ☐ |
| FT2 | Design tokens, dark base styles | Matches §8.2 | F0 | ☐ |
| FT3 | `types/api.ts` + mocks copied + typed import check | `npm run typecheck` passes | F0 | ☐ |
| FT4 | `lib/api.ts` with mock mode + timeout | Mock results load after 1.5 s | F0 | ☐ |
| FT4b | Stitch design: one screen per §8.8 state, exported to `frontend/design/stitch/` | All states exported; tokens match §8.2 | F1 | ☐ |
| FT5 | Network test with Aryan (deferred to I1; stay in mock mode until then) | `/api/health` visible or git-only agreed | I1 | ☐ |
| FT6 | `TopBar`, `Banners`, `EmptyState`, `Legend`, `LabelBadge` | Render on mocks | F2 | ☐ |
| FT7 | `AskPanel`, `LoadingSteps`, `TrustBar` | Render on mocks | F2 | ☐ |
| FT8 | `AnswerView` inline highlights by offsets | All 5 claims highlighted correctly in `check_mixed` | F2 | ☐ |
| FT9 | `ProofPanel`, `JudgeCard`, `EvidenceList` + `useWitness` | Click claim → correct evidence sentence highlighted | F2 | ☐ |
| FT10 | Switch to live backend (after B5 and F4 are pushed) | A real live result renders correctly | I1 | ☐ |
| FT11 | `GradePanel` + backup answers | Pasted answer graded | F3 | ☐ |
| FT12 | `FixedAnswer` + citation chips, `BeforeAfter`, shortcuts | All work | F3 | ☐ |
| FT13 | Every §8.8 state checked | No broken layout | F3 | ☐ |
| FT14 | Replay mode + `ReplayPicker` + static fallback + `sync-replay` | Works with backend off | F4 | ☐ |
| FT15 | Projector mode + < 1280 px layout | Readable at 150 % zoom | F4 | ☐ |
| FT16 | Release build committed (`VITE_API_BASE` empty) | `http://localhost:8000/` works live and in replay on Machine 1 | I1 | ☐ |
| FT17 | (extra) `EvalView` + animations polish | EXAMPLE ribbon works | F5 | ☐ |
| FT18 | Final rebuild + commit after last fix | `dist` matches the last commit | I1 | ☐ |

Notes:

## Support

| # | Task | Done when | Target | ☐ |
|---|---|---|---|---|
| S1 | Handbook Markdown files with source URLs | ≥ 4 files in `backend/data/handbook/` | 0:40 | ☐ |
| S2 | 20 candidate demo questions | List given to Aryan | 1:30 | ☐ |
| S3 | 2 real ChatGPT backup answers | `backup_answers.json`, `is_example: false` | 2:00 | ☐ |
| S4 | ≥ 40 labelled eval claims, double-checked | `eval/claims.jsonl` | 2:30 | ☐ |
| S5 | README text | Names both Gemma models + file paths; limitations; license | 3:00 | ☐ |
| S6 | 5 slides | Problem · How it works · Demo · Numbers (from `eval/results.json`) · Open-source | 3:15 | ☐ |
| S7 | Q&A practice | Everyone answers `PROJECT.md §8` | 3:45 | ☐ |

Notes:

---

## Requests (one row each)

| Time | From → To | Request | Status |
|---|---|---|---|
| | | | |

## Blockers (stuck > 15 minutes)

| Time | Who | Blocker | Helper | Resolved |
|---|---|---|---|---|
| | | | | |

## Decisions (changes to contracts, API, config or deps need Aryan + Mudit)

| Time | Decision | Agreed by |
|---|---|---|
| 0:00 | Use `REQUIREMENTS.md` v2 and `contracts/examples/` as written | Aryan, Mudit |
| event day | **Phases + automatic push:** work is split into phases (backend B0–B6, frontend F0–F5, joint I1); every phase ends with `scripts/phase-push.ps1` (gate → commit own paths → pull --rebase → push). Time checkpoints are replaced by phases. See `AGENTS.md §1b`. | Aryan |
| event day | **Plan change:** build the backend only today. The frontend is built later with Stitch and integrated afterwards; no live frontend↔backend testing today. The backend is verified on its own (pytest + smoke + curl against `/api/*`), and `contracts/examples/*.json` remain the integration contract for the later UI. Skipped today: network test (§10), the 0:20/1:30/2:15/3:00 integration checkpoints, and the port-8000 firewall rule (only needed for a second machine). | Aryan |
| pre-event | **Proposed:** the answer-writer call (REQUIREMENTS §9.1) adds `reasoning_effort: "none"`; `GEN_MAX_TOKENS` stays 200. Without it Gemma 4 E2B returns empty answers. No contract or API change. | Aryan (proposed; Mudit unaffected) |
| pre-event | **Proposed:** Machine 1 uses Python 3.14.6 (not 3.11) with `torch==2.9.1` pinned in the lock file, because Smart App Control blocks torch 2.14.1; all other §12 packages are unpinned latest. No new dependencies. | Aryan (proposed; Mudit to ack — frontend unaffected) |

## Integration log

| Time | Integration | Result | Issues |
|---|---|---|---|
| | | | |

---

## Demo readiness (check at 3:30)

- [ ] Machine 1 serves the latest build at `http://localhost:8000/`
- [ ] LM Studio server running with Gemma 4 E2B; one warm-up check done
- [ ] Main demo question shows at least one 🔴 or 🟡 every time
- [ ] Clicking a claim highlights the right source sentence
- [ ] Fix it → all-green answer with citation chips
- [ ] Grade any AI works with a real backup ChatGPT answer
- [ ] A ⚪ needs-review example is ready
- [ ] Replay works on Machine 1 with wifi off, and on Machine 2 with the backend off
- [ ] Projector mode on; readable from the back
- [ ] Eval numbers on the slide match `backend/eval/results.json` (`is_example: false`) — or the eval slide is removed
- [ ] README names Gemma 4 31B (Gemini API) and Gemma 4 E2B (LM Studio) with file paths
- [ ] Apache-2.0 LICENSE present; repo public
- [ ] Backup video on Machine 2
- [ ] Everyone can answer `PROJECT.md §8`
