# WITNESS frontend handoff

The rendered reference is the Vite application in `src/App.tsx`. Use the **Screen**
control above the product top bar to open each deterministic state.

## Export map

| Screen | Scenario | PNG filename |
|---|---|---|
| 01 | Empty first-load | `01-empty.png` |
| 02 | Loading with estimated steps | `02-loading.png` |
| 03 | Mixed result, contradiction selected | `03-mixed-result.png` |
| 04 | All-supported result | `04-all-green.png` |
| 05 | Judge disagreement, single judge, warning | `05-review-warning.png` |
| 06 | Generation failed | `06-generation-failed.png` |
| 07 | Grade any AI result | `07-grade-any-ai.png` |
| 08 | Replay picker | `08-replay.png` |
| 09 | Backend unreachable | `09-backend-unreachable.png` |
| 10 | Example evaluation | `10-eval-example.png` |
| 11 | Projector mixed result | `11-projector-mixed.png` |
| 12 | Responsive stacked proof | `12-responsive-stacked-proof.png` |

Capture desktop screens at 1920×1080. Screen 12 intentionally forces the same
stacked layout used below 1280 px. The **DS** entry is the rendered token,
component, accessibility, responsive, and motion reference.

## Component inventory

`TopBar`, `Banners`, `AskPanel`, `GradePanel`, `LoadingSteps`, `TrustBar`,
`AnswerView`, `ProofPanel`, `JudgeCard`, `EvidenceList`, `LabelBadge`,
`FixedAnswer`, `BeforeAfter`, `Legend`, `ReplayPicker`, `EvalView`, and
`EmptyState`.

## Interaction contract

- New results select the first non-supported claim; all-supported results select
  the first claim.
- Clicking a claim, pressing Enter while it is focused, or pressing `1`–`9`
  updates only the proof panel.
- `F` toggles Fixed answer, `B` toggles Before/After, `P` toggles Projector,
  `R` toggles Live/Replay, and `Esc` clears the current claim selection.
- Global shortcuts are ignored while focus is in an input, textarea, or select.
- Below 1280 px the complete proof panel follows the answer in document flow.
- Reduced-motion preferences remove nonessential animation and transitions.

## Implementation notes

- All verdict communication uses color, icon, and the exact verdict word.
- Source text remains prose; monospace is reserved for IDs, timestamps, and
  compact metadata.
- Replay and mock states remain useful without a backend.
- No controls imply evidence editing, verdict override, account management,
  uploads, collaboration, or unsupported API behavior.
