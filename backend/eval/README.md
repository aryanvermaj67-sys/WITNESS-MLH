# Eval labels

`claims.jsonl`: one claim per line, `{"question", "claim", "gold"}`, with `gold` in `supported | unsupported | contradicted`.

**These are DRAFT labels.** A second person must double-check every line against `backend/data/handbook/*.md` before the numbers are used anywhere.

Label rules (same as the judge prompt, REQUIREMENTS.md §9.2):
- supported: a handbook sentence states it.
- contradicted: a handbook sentence states the opposite or a different value.
- unsupported: no handbook sentence says it either way.

The labels were written against the five MLH handbook files only. Re-check the unsupported lines once `event_description.md` is added, because the event description may answer some of them (team size, food, demo length, judges).
