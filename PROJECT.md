# WITNESS — Project Details (v2: two machines)

> **AI sounds equally sure when it's right and when it's wrong. WITNESS shows you which is which — line by line, with proof.**

Team project for **Hacktoberfest Hack Day Hamirpur × GDG Ludhiana** at NIT Hamirpur: about 4 hours of building, then a 5-minute demo and Q&A.

| File | For | Contains |
|---|---|---|
| `PROJECT.md` (this) | People | What, why, who, when, demo, Q&A, risks |
| `REQUIREMENTS.md` | Both builders + agents | The exact spec: data model, API, config, rules, prompts, UI spec |
| `AGENTS.md` | AI coding agents | Role-by-role instructions, build order, rules |
| `PROGRESS.md` | Everyone | Live tracker, checkpoints, requests, decisions |
| `contracts/examples/*.json` | Both builders | The exact JSON the API returns, used as mock data and as tests |

---

## 1. What WITNESS is (plain language)

When a chatbot answers from documents, it sometimes **adds things the documents never said** or **says the opposite**, and it sounds just as confident either way.

WITNESS checks the answer **sentence by sentence** against the documents:

| | Meaning |
|---|---|
| 🟢 Supported | The documents say this |
| 🟡 Unsupported | The documents don't mention it |
| 🔴 Contradicted | The documents say the opposite |
| ⚪ Needs review | Our two judges disagree, so a human should look |

Click a sentence → the exact source sentence lights up as proof. **Fix it** → a clean answer with only supported sentences and citations. **Grade any AI** → paste ChatGPT's answer and WITNESS grades it too.

**Example (from our own example data)**
> Q: "Can we start coding before the hackathon day, and what do we need to submit?"
> AI: "You can start building your project a week before the event. 🔴 Projects must be pushed to a public GitHub repository under an open-source license. 🟢 Each team gives a 10-minute presentation. 🔴 Teams also need to submit a video walkthrough. 🟡 The hackathon is hosted at NIT Hamirpur. 🟢"
> Proof for the first line: *"All development work must start at the event."*

---

## 2. Why it can win

| Judges look for | WITNESS |
|---|---|
| Gemma used **through the Gemini API** (Gemma prize rule) | Gemma 4 31B via the Gemini API is the main judge |
| Open-source / open-weight AI is important | Gemma 4 E2B runs locally in LM Studio; an open NLI model is judge 2; Apache-2.0; Agent Skill |
| Clear problem | Everyone has seen AI confidently say something wrong |
| Substantial technical work | Hybrid retrieval, two independent judges, a disagreement rule, evaluation numbers, a full web app |
| Working demo | Pre-tested questions, cached results, replay mode on two machines |

**Three differentiators** (say them in Q&A):
1. **Small model writes, big model checks.** Gemma 4 E2B (local) answers, and Gemma 4 31B (API) verifies. The hallucinations are real, and the checker isn't grading itself.
2. **Two independent judges.** Gemma 31B plus an open NLI model. When they disagree, the line is marked "needs review" instead of getting a confident wrong color.
3. **Grade any AI live,** including ChatGPT, against the event's own rules.

---

## 3. Architecture (two machines)

```
                 MACHINE 1 — ARYAN (backend, projector on demo day)
┌──────────────────────────────────────────────────────────────────────────┐
│ FastAPI server :8000                                                     │
│   /api/check ─► Hybrid retrieval (BM25 + MiniLM, RRF) over the handbook  │
│                ─► Gemma 4 E2B answer (LM Studio, local GPU)              │
│                   (skipped when an answer is pasted)                     │
│                ─► split into claims (with character offsets)             │
│                ─► Judge 1: Gemma 4 31B (Gemini API, ONE call) ──► cloud  │
│                ─► Judge 2: NLI DeBERTa-v3-small (local CPU)              │
│                ─► combine rule ─► trust score ─► fix-it ─► cache         │
│   /api/health /api/demo-questions /api/eval /api/backup-answers          │
│   /api/replay  ·  serves frontend/dist at "/" on demo day                │
└───────────────────────────────▲──────────────────────────────────────────┘
                                │  JSON over HTTP (same hotspot)
                                │  contract = contracts/examples/*.json
┌───────────────────────────────┴──────────────────────────────────────────┐
│ MACHINE 2 — MUDIT (frontend, backup on demo day)                         │
│ React + TypeScript + Vite + Tailwind                                     │
│ Ask · Grade any AI · Results  |  inline highlights · proof panel ·       │
│ trust bar · fix-it · before/after · replay mode · projector mode         │
│ Mock mode = works with no backend from minute 0                          │
└──────────────────────────────────────────────────────────────────────────┘
```

**Why this split can't clash:** the two machines share no code. They only share the JSON shape, which is pinned by real example files. Mudit builds the whole UI against those files. Aryan's server first returns those same files, then replaces them with real results. If the network between laptops fails, integration happens through git: Mudit commits the built app, and Aryan's server serves it.

**RAG framing:** hybrid RAG finds the evidence, and WITNESS adds a **Self-RAG-style reflection step** that checks every claim against the sources. (Say "Self-RAG *style*": the original Self-RAG trains the model itself, while we check after the answer with separate judges.)

---

## 4. Team

| Person | Machine | Owns | In one line |
|---|---|---|---|
| **Aryan** | 1 | `backend/` | All logic, both judges, the API server, cache/replay, eval, Agent Skill |
| **Mudit** | 2 | `frontend/` | A professional, projector-ready React app with mock and replay modes |
| Support (optional) | any | handbook text, backup answers, eval labels, README, slides | Content, demo questions, pitch practice |

---

## 5. Timeline (hours from the start of building)

> **Superseded by phases.** Work is now organised as backend phases B0–B6, frontend phases F0–F5 (UI designed in Stitch) and a joint integration phase I1; every phase ends with an automatic push (`scripts/phase-push.ps1`). See `AGENTS.md §1b` and `PROGRESS.md → Phases and pushes`. The table below is kept as a rough pacing guide only.

| Time | Aryan (backend) | Mudit (frontend) | Checkpoint |
|---|---|---|---|
| 0:00–0:20 | Repo, license, contracts, Pydantic models, **stub server returning the example files** | Vite scaffold, Tailwind, tokens, types, mocks, API client | **0:20:** Mudit's browser reads Aryan's `/api/health` |
| 0:20–1:30 | KB → retrieval → E2B writer → claims → Gemma judge → combine → pipeline | Top bar, ask panel, loading steps, trust bar, inline highlights, proof panel (on mocks) | **1:30:** real live result rendered in the UI |
| 1:30–2:15 | NLI judge, pasted-answer path | Grade any AI, fix-it, before/after, shortcuts, all states | **2:15:** needs-review + grade-any-AI live |
| 2:15–3:00 | Cache + replay, demo questions verified and cached, serve `dist`, real health | Replay mode, sync-replay, projector mode, **release build committed** | **3:00:** app served from Machine 1, live + replay |
| 3:00–3:15 | Eval numbers, Agent Skill (extras) | Eval view, polish (extras) | **3:15: FEATURE FREEZE** |
| 3:15–4:00 | Warm-up, fixes | Final rebuild + commit | Two rehearsals, backup video, submit |

---

## 6. Demo script (5 minutes, on Machine 1)

| Time | Beat | Screen |
|---|---|---|
| 0:00 | "AI answers sound equally sure when they're wrong. Watch." | Empty state with the one-liner |
| 0:20 | Run a pre-tested question about this hackathon's rules | Loading steps → answer appears |
| 0:45 | Lines turn 🔴/🟡; click the red one | Proof panel: both judges + the handbook sentence highlighted |
| 1:45 | **Fix it** | Clean, all-green answer with citation chips; trust bar jumps |
| 2:15 | "Ask WITNESS anything about this hackathon." A judge asks; we paste ChatGPT's answer into **Grade any AI** | ChatGPT graded live |
| 3:15 | Show a ⚪ needs-review case: "When our judges disagree, we don't guess." | Two judge cards side by side |
| 3:45 | Numbers: Gemma only vs NLI only vs both (only if real) | Eval view |
| 4:20 | "E2B writes, 31B checks, an open NLI model double-checks. Apache-2.0, Agent Skill included." | Repo + license |
| 4:45 | Close with the one-liner | — |

If anything freezes: press **R** (replay mode) and keep talking. If Machine 1 dies: Machine 2 runs replay or plays the backup video.

---

## 7. Q&A answers (everyone memorises)

| Question | Answer |
|---|---|
| Doesn't better RAG make this unnecessary? | Better RAG reduces hallucinations but never to zero. WITNESS sits on top of any RAG, and it also *proves* when an answer is trustworthy. |
| Why trust Gemma to check Gemma? | A different, larger model checks, and an independent open NLI model double-checks. Disagreements go to "needs review". |
| This already exists (RAGAS, TruLens…) | Those are developer metrics. WITNESS shows end users line-by-line proof, fixes the answer, and grades any AI live. |
| LLM-as-judge is unreliable | That's why there are two judges, evidence for every verdict, and measured accuracy. |
| Is unsupported the same as false? | No. It means "not in the sources". We say so on screen. |
| What's your accuracy? | Only our own measured numbers on our labelled set; never other papers' numbers. |
| Why open models? | E2B runs on a student laptop, the NLI judge is open, and anyone can audit and re-run everything. |
| Why two machines / why a web app? | It's how a real product works: an API anyone can call, and a UI on top. The Agent Skill uses the same pipeline. |

---

## 8. Failure points and how they're handled

| Risk | Handling |
|---|---|
| Laptops can't reach each other on venue wifi | Same phone hotspot; firewall rule; otherwise mock mode + git integration; demo runs on one machine anyway |
| Contract mismatch between backend and frontend | Frozen example files; backend tests validate them; frontend typecheck imports them |
| E2B answers correctly, so nothing turns red | Hour 2: verify ≥ 4 questions that reliably hallucinate (temperature 0 = repeatable); grade-any-AI backup |
| Checker wrong on stage | Only pre-tested questions in the main demo; disagreement → needs review |
| API limit or wifi down | One Gemini call per check; cached results; replay on both machines; second API key |
| LM Studio slow or crashes | Only E2B loaded; NLI on CPU; warm-up before the slot; replay |
| Highlight on the wrong text | Character offsets + sentence IDs, verified by tests and example files |
| Slow request looks frozen | Animated loading steps with elapsed time; Run disabled while running |
| Off-topic question from a judge | Invite questions about the event rules; backup ChatGPT answers ready |
| Demo build points at the wrong IP | Demo build uses an empty `VITE_API_BASE` (same origin) |
| Integration chaos | Separate folders, frozen contracts, checkpoints at 0:20 / 1:30 / 2:15 / 3:00 |

---

## 9. Rules compliance

- No project code before the event. These documents and example JSON files are planning material; the repo is created at 0:00.
- Public GitHub repo, **Apache-2.0** in the first commit.
- README names **Gemma 4 31B via the Gemini API** (`backend/witness/judge_gemma.py`) and **Gemma 4 E2B** via LM Studio (`backend/witness/generator.py`).
- Agent Skill follows the Agent Skill Open Standard (`SKILL.md` with `name` + `description`).
- Commit every 20–30 minutes so judges can see the work was done on the day.

## 10. Sources to cite

- MLH handbook, Gemma challenge: https://hacktoberfest-handbook.mlh.com/hack-days-partner-modules/partner-challenge-google-gemma
- MLH handbook, Open-Source AI challenge: https://hacktoberfest-handbook.mlh.com/fest-planning-guide/open-source-prize-categories
- Gemma on the Gemini API: https://ai.google.dev/gemma/docs/core/gemma_on_gemini_api
- Agent Skills specification: https://agentskills.io/specification
- Self-RAG (Asai et al., 2023): https://arxiv.org/abs/2310.11511
