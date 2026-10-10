# Eval labels

`claims.jsonl`: one claim per line, `{"question", "claim", "gold"}`, with `gold` in `supported | unsupported | contradicted`.

**These are DRAFT labels.** A second person must double-check every line against `backend/data/handbook/*.md` before the numbers are used anywhere.

Label rules (same as the judge prompt, REQUIREMENTS.md §9.2):
- supported: a handbook sentence states it.
- contradicted: a handbook sentence states the opposite or a different value.
- unsupported: no handbook sentence says it either way.

The labels were first written against the five MLH handbook files.

## Re-check against `event_description.md`

Changed:
- "Each team's demo is limited to three minutes.": unsupported → **contradicted** ("Present a quick 5-minute live demo of what your team built.").

Checked, unchanged:
- Already supported, and the event text agrees: all work during the hackathon ("All development work must start at the event."); public GitHub repository ("Push your project to a public GitHub repository under an open-source license.").
- Already contradicted, and the event text agrees: two-day Hack Day ("one-day in-person mini hackathon").
- "Teams can use an idea they had before the event." stays supported (MLH rule 7). "Come with fresh ideas, enthusiasm, and curiosity not pre-existing code!" contrasts ideas with code; it does not forbid earlier ideas. A reviewer may disagree, so check this line.
- Still unsupported, because the event text is silent: team size, wifi, food, programming language, when winners are announced, who the judges are, Gemma 4 size, minimum age ("Who Can Attend?" names groups, not an age), certificates, unit tests, cloud credits, badge shipping time, number of Gemma models.

Counts now: 14 supported, 15 contradicted, 13 unsupported.

`backend/data/demo_questions.json` was checked too: no `expect` changed. No candidate asks about demo length or who can attend; the event text agrees with the guesses for q1 (start at the event), q13 (public GitHub repo, open-source license) and q14 (in person).
