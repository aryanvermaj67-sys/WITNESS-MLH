# WITNESS — Requirements, Contracts and Interface Spec (v2: two machines)

**This file is the single source of truth.** If code and this file disagree, this file wins until both builders agree to change it. Any change to §4 (data model), §5 (HTTP API) or §6 (config) needs **Aryan + Mudit's OK** and a line in `PROGRESS.md → Decisions`.

Read order for a newcomer: `PROJECT.md` (why) → this file (what, exactly) → `AGENTS.md` (how agents work) → `PROGRESS.md` (where we are).

---

## 0. Two-machine setup at a glance

| | **Machine 1 — Backend** | **Machine 2 — Frontend** |
|---|---|---|
| Owner | **Aryan** | **Mudit** |
| Builds | Everything in `backend/`: knowledge base, retrieval, answer writer, claim splitter, both judges, combine rule, trust score, fix-it, cache/replay, eval, Agent Skill, FastAPI server | Everything in `frontend/`: React + TypeScript + Vite + Tailwind app, professional UI, mock mode, replay mode, projector mode |
| Runs | Python 3.11, LM Studio (Gemma 4 E2B), FastAPI on port 8000, NLI + embedding models on CPU, Gemini API key | Node 20+, Vite dev server on port 5173 |
| Talks to the other | Serves JSON over HTTP at `http://<machine-1-ip>:8000/api/...` | Calls the backend over HTTP; **never** imports backend code |
| Demo day role | **Projector machine.** Serves the built frontend from `frontend/dist` at `http://localhost:8000/` | **Backup machine.** Runs the frontend in replay mode + holds the backup video |

The **only** things shared between the two machines are:
1. The HTTP API in §5.
2. The JSON example files in `contracts/examples/` (frozen at 0:20).
3. These four Markdown files.

Because the frontend only ever sees JSON, both builders can work at full speed in parallel: Mudit builds on the example files from minute 0, Aryan replaces the stub server's example responses with real ones step by step.

---

## 1. Repository layout and ownership

```
witness/                                  (one GitHub repo, branch: main)
├── PROJECT.md  REQUIREMENTS.md  AGENTS.md  PROGRESS.md   shared docs (PROGRESS: own section only)
├── README.md                             Support (Aryan reviews backend parts, Mudit reviews UI parts)
├── LICENSE                               Apache-2.0 (first commit, Aryan)
├── .gitignore                            Aryan (root)
├── contracts/                            SHARED, FROZEN at 0:20
│   └── examples/
│       ├── check_mixed.json              main example: 5 claims, all 3 colors
│       ├── check_all_green.json          everything supported
│       ├── check_review.json             judges disagree + single-judge claim + a warning
│       ├── check_error.json              LM Studio down: no claims, error message
│       ├── check_pasted.json             Grade-any-AI result (answer_source = "pasted")
│       ├── check_replay.json             replay result (mode = "replay")
│       ├── health.json                   GET /api/health
│       ├── demo_questions.json           GET /api/demo-questions
│       ├── eval.json                     GET /api/eval  (is_example = true!)
│       ├── backup_answers.json           GET /api/backup-answers
│       └── replay_index.json             GET /api/replay
├── backend/                              ARYAN ONLY
│   ├── .env.example   requirements.txt   requirements.lock.txt
│   ├── server.py                         FastAPI app (routes in §5)
│   ├── witness/
│   │   ├── __init__.py
│   │   ├── models.py                     Pydantic models (§4)
│   │   ├── config.py                     settings (§6)
│   │   ├── kb.py  retrieval.py  generator.py  claims.py
│   │   ├── judge_gemma.py  judge_nli.py  verdict.py  fixit.py
│   │   ├── cache.py  pipeline.py  smoke.py
│   ├── data/
│   │   ├── handbook/*.md                 knowledge base   (Support writes content, Aryan commits/owns)
│   │   ├── demo_questions.json           verified questions
│   │   ├── backup_answers.json           real copied ChatGPT answers
│   │   └── cached/  *.json + index.json  saved results for replay
│   ├── eval/   claims.jsonl  run_eval.py  results.json
│   ├── skill/witness-verify/  SKILL.md  scripts/verify.py
│   └── tests/  test_models_match_contracts.py  test_pipeline.py  test_judges.py  test_cache.py
└── frontend/                             MUDIT ONLY
    ├── .env.example   package.json   vite.config.ts   tsconfig*.json   index.html
    ├── scripts/sync-replay.mjs           copies backend/data/cached → frontend/public/replay
    ├── public/replay/                    replay copies (index.json + results)
    ├── src/
    │   ├── main.tsx  App.tsx  index.css
    │   ├── types/api.ts                  TypeScript mirror of §4
    │   ├── lib/api.ts                    HTTP client + mock + replay (§8.6)
    │   ├── lib/labels.ts                 label → color/icon/text (§8.2)
    │   ├── mocks/                        copies of contracts/examples/*.json
    │   ├── state/useWitness.ts           app state (useReducer)
    │   └── components/                   (§8.4)
    └── dist/                             production build (committed at 3:00 and at freeze)
```

**Ownership rule:** Aryan writes only in `backend/` (+ root `.gitignore`, `LICENSE`). Mudit writes only in `frontend/`. Support members write only the content files listed for them in `AGENTS.md`. Nobody edits `contracts/` after 0:20 without a recorded decision.

---

## 2. Functional requirements

| ID | Requirement | Owner | Acceptance check |
|---|---|---|---|
| FR-1 | Load the knowledge base from `backend/data/handbook/*.md`; split into passages (~60–150 words, never across headings) and sentences with stable IDs `p{n}` / `p{n}.s{m}` (files sorted by name) | Aryan | ≥ 20 passages; all sentence IDs unique; same IDs on every run |
| FR-2 | Hybrid retrieval: BM25 + MiniLM embeddings merged by reciprocal rank fusion, top `TOP_K=5` | Aryan | Gold passage in top 5 for every demo question |
| FR-3 | Answer writer: Gemma 4 E2B via LM Studio, temperature 0, max 200 tokens, 3–5 sentences, passages only | Aryan | Same question twice → identical answer |
| FR-4 | Grade any AI: accept a pasted answer instead of generating | Aryan + Mudit | `POST /api/check` with `answer_text` → `answer_source="pasted"`, `timings.generate=0` |
| FR-5 | Claim splitter: one claim per sentence; `start`/`end` char offsets into `answer_text`; drop fragments < 4 words | Aryan | `answer_text[start:end] == text` for every claim |
| FR-6 | Judge 1: Gemma 4 31B via Gemini API, **one call for all claims**, label + evidence sentence IDs + one-sentence explanation | Aryan | 5 claims → exactly 1 API call; unknown IDs dropped |
| FR-7 | Judge 2: NLI cross-encoder on CPU, every (sentence, claim) pair of the retrieved passages | Aryan | < 5 s for 5 claims × 5 passages |
| FR-8 | Combine rule (§7) and `single_judge` flag | Aryan | Unit test covers every row |
| FR-9 | Trust score: counts per label + rounded percent supported | Aryan | Matches verdicts |
| FR-10 | Fix-it: supported claims only, each followed by `[first evidence id]`; deterministic, no API call | Aryan | No non-supported claim appears |
| FR-11 | Never crash: every failure becomes a readable string in `errors`; `/api/check` returns HTTP 200 with a complete result (except invalid input → 422) | Aryan | LM Studio off → `check_error.json`-shaped response |
| FR-12 | Cache every successful live result; replay by question (+ answer) key; replay index | Aryan | Replay result identical except `mode="replay"` |
| FR-13 | Health endpoint reports each dependency's status | Aryan | Matches `health.json` shape |
| FR-14 | Serve the frontend build from `frontend/dist` at `/` when present | Aryan | `http://localhost:8000/` shows the app; refresh on any route works |
| FR-15 | Frontend: Ask view, Grade-any-AI view, inline highlighted claims, proof panel, trust bar, fix-it, before/after, eval view, replay mode, projector mode, health pills, error/replay banners | Mudit | All work on every example file in `contracts/examples/` |
| FR-16 | Frontend mock mode (`VITE_USE_MOCK=true`) using `src/mocks/*.json` with 1.5 s fake delay | Mudit | Full UI usable with backend off |
| FR-17 | Frontend replay mode from `public/replay/` when the backend is unreachable | Mudit | Backend off + replay on → recorded results render with a visible "Replay" banner |
| FR-18 | Demo questions: ≥ 4 verified at the event that reliably produce a 🔴 or 🟡 | Aryan + Support | Each run 2× with the same outcome |
| FR-19 | Evaluation: accuracy of Gemma-only, NLI-only and combined on ≥ 40 labelled claims → `eval/results.json` served at `/api/eval` | Aryan + Support | `is_example=false` in the real file |
| FR-20 | Agent Skill `backend/skill/witness-verify/` per Agent Skill Open Standard | Aryan | `SKILL.md` frontmatter has `name` + `description`; script prints JSON |
| FR-21 (stretch) | Hindi questions | Aryan | Tested before showing |

## 3. Non-functional requirements

| ID | Requirement |
|---|---|
| NFR-1 | Live `/api/check` ≤ 30 s end to end; replay < 200 ms |
| NFR-2 | ≤ 1 Gemini API call per check; 0 for fix-it |
| NFR-3 | No secrets in git; the Gemini key exists **only** in `backend/.env` on Machine 1; the frontend never sees it |
| NFR-4 | Models (NLI, embeddings, BM25 index, KB) load once at server start (FastAPI lifespan) |
| NFR-5 | Frontend works at 1920×1080 and 1366×768; projector mode readable from the back of a hall |
| NFR-6 | Accessibility: every label shown as color **+ icon + word**; keyboard usable; visible focus rings |
| NFR-7 | Honesty: replay and example data are always labelled on screen |
| NFR-8 | Apache-2.0; README names Gemma 4 31B (Gemini API) and Gemma 4 E2B (LM Studio, local) with the file paths where each is called |
| NFR-9 | Determinism: same input → same output (temperature 0, stable IDs, stable sort orders) |

---

## 4. Data model (identical in Python and TypeScript)

Backend: Pydantic v2 models in `backend/witness/models.py`. Frontend: TypeScript types in `frontend/src/types/api.ts`. **Field names, types and nullability must match exactly.** `contracts/examples/*.json` are valid instances; both sides test against them.

### Enums
| Name | Values |
|---|---|
| `JudgeLabel` | `"supported"`, `"unsupported"`, `"contradicted"` |
| `FinalLabel` | `"supported"`, `"unsupported"`, `"contradicted"`, `"needs_review"` |
| `JudgeName` | `"gemma"`, `"nli"` |
| `AnswerSource` | `"gemma-4-e2b-local"`, `"pasted"` |
| `Mode` | `"live"`, `"replay"` |

### `Sentence`
| Field | Type | Example |
|---|---|---|
| `id` | string | `"p1.s3"` |
| `text` | string | `"All development work must start at the event."` |

### `Passage`
| Field | Type | Example |
|---|---|---|
| `id` | string | `"p1"` |
| `doc` | string | `"event_description.md"` |
| `text` | string | all sentences joined by single spaces |
| `sentences` | Sentence[] | in order |

### `Claim`
| Field | Type | Rule |
|---|---|---|
| `id` | string | `"c1"`, `"c2"`, … in answer order |
| `text` | string | exact substring of `answer_text` |
| `start` | int | inclusive char offset |
| `end` | int | exclusive char offset |

### `JudgeVerdict`
| Field | Type | Rule |
|---|---|---|
| `claim_id` | string | |
| `judge` | JudgeName | |
| `label` | JudgeLabel | |
| `evidence_ids` | string[] | sentence IDs that exist in `passages`; may be empty |
| `explanation` | string | one sentence; NLI uses `"entailment 0.96"` / `"contradiction 0.93"` / `"no sentence above threshold (entail x, contra y)"` |
| `confidence` | number \| null | Gemma: `null`; NLI: winning probability 0–1, 2 decimals |

### `FinalVerdict`
| Field | Type | Rule |
|---|---|---|
| `claim_id` | string | same order as `claims` |
| `label` | FinalLabel | from §7 |
| `evidence_ids` | string[] | Gemma's evidence first, then NLI's, no duplicates |
| `explanation` | string | Gemma's explanation, else NLI's |
| `gemma` | JudgeVerdict \| null | |
| `nli` | JudgeVerdict \| null | |
| `single_judge` | boolean | true if exactly one judge produced a verdict, or none |

### `TrustScore`
| Field | Type |
|---|---|
| `supported`, `unsupported`, `contradicted`, `needs_review`, `total` | int |
| `percent_supported` | int, `round(100 * supported / total)`, 0 when total = 0 |

### `PipelineResult` (response of `POST /api/check`)
| Field | Type | Rule |
|---|---|---|
| `question` | string | |
| `answer_text` | string | `""` if generation failed |
| `answer_source` | AnswerSource | |
| `passages` | Passage[] | retrieved, rank order |
| `claims` | Claim[] | |
| `verdicts` | FinalVerdict[] | same length and order as `claims` |
| `trust` | TrustScore | |
| `fixed_answer` | string | `""` if nothing supported |
| `timings` | object of string → number | keys: `retrieve`, `generate`, `judge_gemma`, `judge_nli`, `total` (seconds, 2 decimals) |
| `errors` | string[] | human-readable; shown in the UI |
| `mode` | Mode | |

The canonical example is `contracts/examples/check_mixed.json`:
- question: *"Can we start coding before the hackathon day, and what do we need to submit?"*
- 5 claims: c1 🔴 contradicted (both judges), c2 🟢 supported, c3 🔴 contradicted (Gemma) + NLI unsupported, c4 🟡 unsupported, c5 🟢 supported
- trust 2/1/2/0, 40 % supported
- fixed answer keeps c2 and c5 with `[p2.s1]` and `[p1.s1]`

`check_review.json` shows a ⚪ `needs_review` claim (Gemma supported vs NLI contradicted), a `single_judge: true` claim with `gemma: null`, and a non-empty `errors` list. `check_error.json` shows an empty result with an LM Studio error.

### Other response models
| Model | Fields (see the matching example file) |
|---|---|
| `Health` | `status` ("ok"), `version`, `lmstudio` (bool), `gemini_key` (bool), `nli_loaded` (bool), `embeddings_loaded` (bool), `kb_passages` (int), `replay_default` (bool), `models` {`writer`, `judge_1`, `judge_2`: string} |
| `DemoQuestion` | `id`, `question`, `expect` (FinalLabel), `why` |
| `EvalResult` | `is_example` (bool), `note`, `n_claims`, `generated_at` (ISO string), `rows` [{`judge` ("gemma"\|"nli"\|"combined"), `label`, `accuracy` (0–1), `correct`, `n`}], `per_label` {label: {`n`}} |
| `BackupAnswer` | `id`, `question`, `answer`, `source`, `is_example` (bool) |
| `ReplayEntry` | `key`, `question`, `answer_source`, `saved_at` |

---

## 5. HTTP API (Machine 1 → Machine 2)

Base URL: dev `http://<machine-1-ip>:8000`; demo (same origin) `""`. All JSON, UTF-8. CORS: allow all origins, methods `GET, POST, OPTIONS`, header `Content-Type` (hackathon setting; no cookies/credentials).

| Method + path | Request | Response | Notes |
|---|---|---|---|
| `GET /api/health` | — | `Health` | Fast (< 300 ms): checks LM Studio with a 1 s timeout, key presence only (no Gemini call) |
| `GET /api/demo-questions` | — | `DemoQuestion[]` | From `backend/data/demo_questions.json` |
| `POST /api/check` | `{"question": string, "answer_text": string \| null, "mode": "live" \| "replay" \| null}` | `PipelineResult` | See rules below |
| `GET /api/eval` | — | `EvalResult` | 404 `{"detail": "not ready"}` if `eval/results.json` missing; frontend hides the view |
| `GET /api/backup-answers` | — | `BackupAnswer[]` | From `backend/data/backup_answers.json` |
| `GET /api/replay` | — | `ReplayEntry[]` | From `backend/data/cached/index.json` |
| `GET /api/replay/{key}` | — | `PipelineResult` (`mode="replay"`) | 404 if missing |
| `GET /` and any non-`/api` path | — | `frontend/dist/index.html` (SPA fallback) | Only when `frontend/dist` exists |

### `POST /api/check` rules
1. Validation → HTTP 422 with FastAPI's standard error body: `question` 1–500 chars after trimming; `answer_text` ≤ 4000 chars when present.
2. `mode="replay"` → return the cached result for `key_for(question, answer_text)` with `mode="replay"`; if missing, return HTTP 200 with an empty result and `errors=["No saved result for this question."]`, `mode="replay"`.
3. `mode=null` → use `OFFLINE_REPLAY` from config (default live).
4. Live: run the pipeline. **Always HTTP 200** with a complete `PipelineResult`, even when steps fail (failures listed in `errors`).
5. After a live run with ≥ 1 claim and no generation error, save to cache.
6. Concurrency: one live check at a time (a lock); a second request waits. Frontend disables the Run button while running.
7. Server timeout budget: generation 20 s, Gemma call 25 s, total soft limit 60 s (add an error if exceeded, return what exists).

---

## 6. Configuration

### Backend `backend/.env` (template in `backend/.env.example`)
| Name | Default | Notes |
|---|---|---|
| `GEMINI_API_KEY` | (none) | required for judge 1 |
| `GEMINI_MODEL` | `gemma-4-31b-it` | |
| `LMSTUDIO_BASE_URL` | `http://localhost:1234/v1` | |
| `LMSTUDIO_MODEL` | (none) | exact ID LM Studio shows for Gemma 4 E2B |
| `NLI_MODEL` | `cross-encoder/nli-deberta-v3-small` | label order read from the model config |
| `EMBED_MODEL` | `sentence-transformers/all-MiniLM-L6-v2` | |
| `NLI_DEVICE` | `cpu` | keep the GPU for LM Studio |
| `KB_DIR` | `data/handbook` | relative to `backend/` |
| `CACHE_DIR` | `data/cached` | |
| `FRONTEND_DIST` | `../frontend/dist` | |
| `TOP_K` | `5` | |
| `RRF_K` | `60` | |
| `NLI_ENTAIL_THRESHOLD` | `0.70` | |
| `NLI_CONTRA_THRESHOLD` | `0.70` | |
| `GEN_TEMPERATURE` | `0.0` | |
| `GEN_MAX_TOKENS` | `200` | |
| `OFFLINE_REPLAY` | `false` | |
| `HOST` / `PORT` | `0.0.0.0` / `8000` | |

### Frontend `frontend/.env.local` (template in `frontend/.env.example`)
| Name | Dev value | Build-for-demo value |
|---|---|---|
| `VITE_API_BASE` | `http://<machine-1-ip>:8000` | empty (same origin) |
| `VITE_USE_MOCK` | `true` until the network test passes, then `false` | `false` |
| `VITE_REQUEST_TIMEOUT_MS` | `90000` | `90000` |

---

## 7. Combine rule and NLI decision

| Gemma | NLI | Final | `single_judge` |
|---|---|---|---|
| supported | supported | supported | false |
| supported | unsupported | supported | false |
| supported | contradicted | **needs_review** | false |
| unsupported | supported | **needs_review** | false |
| unsupported | unsupported | unsupported | false |
| unsupported | contradicted | **needs_review** | false |
| contradicted | contradicted | contradicted | false |
| contradicted | unsupported | contradicted | false |
| contradicted | supported | **needs_review** | false |
| missing | X | X | true |
| X | missing | X | true |
| missing | missing | **needs_review** | true |

**NLI decision per claim:** score `(premise=sentence, hypothesis=claim)` for every sentence in the retrieved passages, in one batch; softmax; read the label order from `model.config.id2label`.
- `max_contra ≥ NLI_CONTRA_THRESHOLD` and `max_contra > max_entail` → contradicted, evidence = that sentence, confidence = `max_contra`
- else `max_entail ≥ NLI_ENTAIL_THRESHOLD` → supported, evidence = that sentence, confidence = `max_entail`
- else → unsupported, no evidence, confidence = `max(max_entail, max_contra)`

---

## 8. Frontend specification (Mudit)

### 8.1 Stack (fixed)
React 18+, TypeScript, Vite, Tailwind CSS (follow the current official Tailwind + Vite install guide), `lucide-react` (icons), `framer-motion` (animations), `clsx`, `@fontsource/inter`, `@fontsource/jetbrains-mono` (fonts bundled, so they work offline). No other UI or state libraries.

### 8.2 Design system
| Token | Value | Use |
|---|---|---|
| `bg` | `#0B0F14` | page |
| `surface` | `#121821` | cards |
| `surface-2` | `#1A2230` | inputs, nested cards |
| `border` | `#263042` | hairlines |
| `text` | `#E6EDF3` | body |
| `muted` | `#8B98A9` | secondary text |
| `brand` | `#7C9CFF` | logo, primary button, focus ring |
| `supported` | `#22C55E` (tint `#22C55E1F`) | icon `CheckCircle2`, word "Supported" |
| `unsupported` | `#EAB308` (tint `#EAB3081F`) | icon `HelpCircle`, word "Unsupported" |
| `contradicted` | `#EF4444` (tint `#EF44441F`) | icon `XCircle`, word "Contradicted" |
| `needs_review` | `#94A3B8` (tint `#94A3B81F`) | icon `AlertTriangle`, word "Needs review" |

- Fonts: Inter for UI; JetBrains Mono for IDs (`p1.s3`, `c2`) and timings.
- Type scale (normal / projector mode): body 16 / 22 px, answer text 20 / 28 px, headings 24 / 34 px, trust number 48 / 72 px.
- Radius 12 px for cards, 8 px for controls; 8 px spacing grid; no drop shadows except a subtle one on the proof panel.
- Motion: 150–250 ms ease-out; claims fade in one by one (60 ms stagger); nothing loops forever except the loading indicator.

### 8.3 Layout (1920×1080)
```
┌───────────────────────────── Top bar (64 px) ─────────────────────────────┐
│ WITNESS  "Every claim, with proof"   [Backend●][LM Studio●][Gemini●][NLI●] │
│                                       [Live|Replay]  [Projector mode]      │
├──────────────── Left column (60%) ───────────────┬── Right column (40%) ──┤
│ Tabs: [Ask] [Grade any AI] [Results]             │ PROOF PANEL            │
│ Question input + demo question chips + Run       │ Selected claim         │
│ Trust bar: 40% supported  ▇▇▇▇░░ 2·1·2·0         │ Final label badge      │
│ Answer card: inline highlighted claims           │ Judge 1: Gemma 4 31B   │
│ Legend · [Fix it] · [Before/After]               │ Judge 2: NLI (local)   │
│ Fixed answer (when shown) with citation chips    │ Agreement indicator    │
│ Timings footer (mono, small)                     │ Evidence passages with │
│                                                  │ highlighted sentence   │
└──────────────────────────────────────────────────┴────────────────────────┘
Banners above the tabs: errors (amber), replay (blue, always visible in replay), mock (purple, dev only)
```
At widths under 1280 px the proof panel moves below the answer.

### 8.4 Components (file → props → behaviour)
| File | Props | Behaviour |
|---|---|---|
| `components/TopBar.tsx` | `health`, `mode`, `onModeChange`, `projector`, `onProjectorChange` | Status pills: green = ok, red = down, grey = unknown; tooltip with model names from `health.models` |
| `components/Banners.tsx` | `errors`, `mode`, `isMock` | Error list (amber), replay notice (blue), mock notice (purple) |
| `components/AskPanel.tsx` | `demoQuestions`, `onRun`, `running` | Large input, Enter submits, demo chips fill the input, Run disabled while running |
| `components/GradePanel.tsx` | `backupAnswers`, `onRun`, `running` | Question input + big paste box (char counter, 4000 max) + "Load backup answer" select; calls check with `answer_text` |
| `components/LoadingSteps.tsx` | `running`, `startedAt`, `pasted` | 5 steps (Finding evidence → Writing answer → Checking with Gemma 4 31B → Double-checking with NLI → Combining); advances on estimated times (0.3 s, 5 s, 7 s, 1.5 s, 0.2 s), skips "Writing answer" when pasted; elapsed timer; never claims a step is done that the server hasn't confirmed (labelled "estimated") |
| `components/TrustBar.tsx` | `trust` | Big percent supported; segmented bar in label colors; counts with icons |
| `components/AnswerView.tsx` | `result`, `selectedClaimId`, `onSelect`, `plain` | Renders `answer_text`, wrapping each claim's `[start, end)` range in a highlight span (tint background + colored underline + small icon); text between claims stays plain; click/Enter/number key selects; `plain=true` renders without highlights |
| `components/BeforeAfter.tsx` | `result` | Two columns: "Plain AI answer" vs "With WITNESS" |
| `components/FixedAnswer.tsx` | `result`, `onCitationClick` | Shows `fixed_answer`; `[p2.s1]` tokens become citation chips that select the matching claim's evidence; empty → "No supported claims to keep." |
| `components/ProofPanel.tsx` | `result`, `selectedClaimId` | Claim text, final badge, two `JudgeCard`s, agreement line ("Both judges agree" / "Judges disagree, needs human review" / "Only one judge answered"), `EvidenceList` |
| `components/JudgeCard.tsx` | `title`, `subtitle`, `verdict` | Title "Judge 1 · Gemma 4 31B" / subtitle "Gemini API"; "Judge 2 · NLI" / "DeBERTa-v3-small · local"; label badge, explanation, confidence bar (NLI); `null` → "No verdict" in muted text |
| `components/EvidenceList.tsx` | `passages`, `highlightIds`, `label` | Passages containing evidence first, expanded; each sentence a span with its mono ID on hover; evidence sentences highlighted in the label color and scrolled into view; other passages collapsed |
| `components/LabelBadge.tsx` | `label`, `size` | Icon + word + color from `lib/labels.ts` |
| `components/EvalView.tsx` | `evalResult` | Three horizontal bars (Gemma only, NLI only, WITNESS both) with % and `correct/n`; if `is_example` → big "EXAMPLE DATA — not real results" ribbon |
| `components/EmptyState.tsx` | `onTryDemo` | One-liner, 3-step explainer (Ask → Check → Proof), "Try a demo question" |
| `components/Legend.tsx` | — | Four labels with icons and one-line meanings |
| `components/ReplayPicker.tsx` | `entries`, `onPick` | List of recorded questions for replay mode |

### 8.5 State (`state/useWitness.ts`, `useReducer`)
State: `health`, `demoQuestions`, `backupAnswers`, `evalResult`, `replayIndex`, `result`, `selectedClaimId`, `running`, `startedAt`, `tab` (`"ask" | "grade" | "results"`), `showFixed`, `showBeforeAfter`, `mode` (`"live" | "replay"`), `projector`, `requestError` (network/timeout message).
Rules:
- On a new result, auto-select the first claim that is not `supported` (else the first claim).
- `selectedClaimId` changes never trigger a request.
- `projector` and `mode` persist in `localStorage` (wrapped in try/catch).

### 8.6 API client (`lib/api.ts`)
Functions: `getHealth()`, `getDemoQuestions()`, `check(question, answerText?, mode?)`, `getEval()`, `getBackupAnswers()`, `getReplayIndex()`, `getReplay(key)`.
- Base URL from `VITE_API_BASE`; timeout from `VITE_REQUEST_TIMEOUT_MS` via `AbortController`.
- **Mock mode** (`VITE_USE_MOCK=true`): return the matching `src/mocks/*.json` after 1.5 s; `check()` returns `check_pasted.json` when `answerText` is given, otherwise `check_mixed.json`; a hidden dev menu lets you pick any example file.
- **Replay fallback:** if a live request fails with a network error, set `requestError` and offer "Switch to replay". In replay mode, `getReplayIndex()` tries `/api/replay` then falls back to `/replay/index.json` (static, from `public/replay`); `getReplay(key)` likewise falls back to `/replay/{key}.json`.
- Never throw raw errors into components; return typed results or a `{ error: string }` union.

### 8.7 Keyboard shortcuts
`Enter` run (in inputs) · `1–9` select claim · `F` toggle fixed answer · `B` before/after · `P` projector mode · `R` live/replay · `Esc` clear selection. Ignore shortcuts while typing in an input.

### 8.8 States to design (test each with an example file)
| State | Example file |
|---|---|
| Empty (first load) | — |
| Loading | any, with the mock delay |
| Mixed result | `check_mixed.json` |
| All green | `check_all_green.json` |
| Disagreement + single judge + warning | `check_review.json` |
| Generation failed | `check_error.json` |
| Pasted answer | `check_pasted.json` |
| Replay | `check_replay.json` |
| Backend unreachable | stop the backend |
| Eval with example data | `eval.json` (must show the EXAMPLE ribbon) |

---

## 9. Prompts (Aryan)

### 9.1 Answer writer (Gemma 4 E2B, LM Studio, OpenAI-compatible)
System: *"Answer the question using only the passages. Write 3 to 5 short sentences. Do not add citations or lists."*
User: passages as `[p1] text` blocks, then `Question: ...`.
Settings: temperature 0, max_tokens 200. Strip whitespace; collapse newlines into spaces.

### 9.2 Checker (Gemma 4 31B, Gemini API, `google-genai` SDK)
System instruction: *"You are a strict fact-checker. For each claim, decide using ONLY the numbered sentences. supported = a sentence states it. contradicted = a sentence states the opposite or a different value. unsupported = no sentence says it either way. Cite sentence IDs. Return JSON only."*
Content: every retrieved sentence as `p1.s3: text`, then each claim as `c1: text`.
Output: JSON array `[{"claim_id": "c1", "label": "contradicted", "evidence_ids": ["p1.s3"], "explanation": "One short sentence."}]`. Request JSON output with `response_mime_type="application/json"` (+ a response schema if accepted for this model; otherwise rely on the instruction and parse defensively: take the first `[` … last `]`).
Validation: unknown `claim_id` → ignore; unknown evidence IDs → drop; invalid label → that claim is missing; unparseable → `{}` plus an error string.

---

## 10. Networking runbook (dev time)

> Used in **Phase I1** (integration), not earlier: until B5 and F4 are both pushed, the frontend runs on mock data and the backend is tested with `pytest`, the smoke script and `curl`.

1. Both laptops join the **same phone hotspot** (venue wifi often blocks laptop-to-laptop traffic).
2. Machine 1: find the IPv4 address (`ipconfig` on Windows, `ip a` / `ifconfig` elsewhere).
3. Machine 1: allow inbound port 8000 (Windows: when the firewall prompt appears, allow on private networks, or run in an admin PowerShell `New-NetFirewallRule -DisplayName "WITNESS 8000" -Direction Inbound -LocalPort 8000 -Protocol TCP -Action Allow`).
4. Machine 1: `uvicorn server:app --host 0.0.0.0 --port 8000` from `backend/`.
5. Machine 2: open `http://<machine-1-ip>:8000/api/health` in the browser. JSON → set `VITE_API_BASE` and `VITE_USE_MOCK=false`. No JSON → stay in mock mode; integration happens through git (step 6).
6. Integration without a network: Mudit pushes; Aryan pulls; Mudit's committed `frontend/dist` is served by Aryan's server.

## 11. Demo-day serving (Machine 1 = projector)

1. Mudit: `VITE_API_BASE=` (empty) and `VITE_USE_MOCK=false`, run `npm run build`, run `npm run sync-replay`, commit `frontend/dist` and `frontend/public/replay`.
2. Aryan: `git pull`, start LM Studio server, start `uvicorn`, open `http://localhost:8000/`.
3. Machine 2 backup: `npm run preview` with replay mode on + the recorded video ready.

## 12. Dependencies (fixed at 0:00; changes need a decision)

`backend/requirements.txt`:
```
fastapi
uvicorn[standard]
pydantic
python-dotenv
google-genai
openai
rank_bm25
sentence-transformers
torch
numpy
httpx
pytest
```
After installing: `pip freeze > requirements.lock.txt` and commit.

`frontend/package.json` dependencies: `react`, `react-dom`, `lucide-react`, `framer-motion`, `clsx`, `@fontsource/inter`, `@fontsource/jetbrains-mono`; dev: `vite`, `@vitejs/plugin-react`, `typescript`, `@types/react`, `@types/react-dom`, Tailwind packages per the official guide. Commit `package-lock.json`.

## 13. Data files

| File | Content | Written by |
|---|---|---|
| `backend/data/handbook/*.md` | Event description, MLH Gemma challenge page, MLH Open-Source AI challenge page, MLH standard rules; source URL on line 1 of each | Support (content), Aryan (commits) |
| `backend/data/demo_questions.json` | ≥ 4 verified questions (shape of `contracts/examples/demo_questions.json`, `why` filled in honestly) | Aryan + Support |
| `backend/data/backup_answers.json` | 2 real answers copied from ChatGPT at the event, `is_example: false` | Support |
| `backend/data/cached/` | Saved results + `index.json` | generated by the server |
| `backend/eval/claims.jsonl` | ≥ 40 lines `{"question": ..., "claim": ..., "gold": "supported|unsupported|contradicted"}`, roughly balanced | Support writes, Aryan checks |
| `backend/eval/results.json` | Real eval output, `is_example: false` | `run_eval.py` |

## 14. Out of scope

Document upload, accounts, deployment to the cloud, streaming tokens, image/audio input, fine-tuning, activation probes, mobile layout beyond basic stacking.
