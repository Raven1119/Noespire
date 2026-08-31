# frontend-workspace-v1 — THROWAWAY PROTOTYPE

**This is disposable prototype code.** It answers exactly one question (the
"O1 layout question"):

> How should the Problem Workspace layout divide Proof / Attempts content
> across its three states (SOLVED / OPEN / RUNNING)?

Three structurally different workspace layouts are rendered from the same mock
data, switchable at runtime. Nothing here is production code: no backend
calls, no persistence, no tests, no dark mode. Do not fold this directory into
`src/`; capture the winning layout decision and delete.

## Run

```bash
cd prototypes/frontend-workspace-v1
npm install
npm run dev      # start command — opens on http://localhost:5173
```

## URLs

- Home (problem list): `http://localhost:5173/`
- Workspace, variant A: `http://localhost:5173/?problem=sum-first-n-odd&variant=A`
- Any of the six problems: `sum-first-n-odd` (SOLVED), `even-perfect-triangular`
  (OPEN, verification rejection), `even-perfect-triangular-mersenne` (OPEN,
  contract failure, fork of the previous), `twin-primes-infinite` (OPEN,
  runtime error), `prime-1mod4-two-squares` (RUNNING, pre-candidate),
  `harmonic-noninteger` (RUNNING, post-candidate).
- `?variant=A|B|C` on any workspace URL; `←` / `→` cycle variants (ignored
  while an input is focused); the floating bottom pill shows the current
  variant and is rendered only in dev builds.

## The three variants

- **A — "Status stage"**: no tabs. One central canvas morphs entirely by
  state: SOLVED shows the proof document + supporting closure; OPEN shows the
  latest attempt (candidate + failure evidence) with earlier attempts behind a
  collapsed "Attempt history" toggle at the bottom; RUNNING shows only a phase
  indicator. The header is the only constant.
- **B — "Explicit tabs"**: persistent `Proof | Attempts` tab bar (plus a
  disabled `Graph — future` tab to test additive extensibility, ADR-0002).
  State picks the *default* tab (SOLVED→Proof, OPEN/RUNNING→Attempts with a
  "current attempt" banner), but the user can switch freely; the Proof tab of
  an OPEN problem shows an honest "No verified proof yet" empty state.
- **C — "Document + evidence rail"**: the proof document (or its empty state)
  always owns the center; a persistent ~260px left rail lists the attempt
  timeline newest-first with expandable entries. State changes only the center
  document area, never the layout.

## What is mocked and how

`src/fixtures.ts` mirrors the real backend schemas exactly — `ProblemSpec`,
`ProofObligation`, `Fact`, and the attempt-evidence JSON
(`candidate_artifact` / `verifier_artifact` / `verdict` / `error`) from
`src/research/`. The only invented layers are `WorkspaceModel`, the ADR-0005
read-model aggregate (facts + closure + attempts + lineage + a display-only
`last_activity` string), and the prototype-only `failureSource` field on
attempt evidence described below.

## Prototype-only shortcuts

- **Failure origin uses a prototype-only read-model field.** Current backend
  limitation: attempt evidence does not encode whether a FAIL originated from
  the obligation contract guard or the fresh verifier; both persist
  `verifier_artifact.accepted=false` (the guard's reason, e.g. "candidate
  statement does not match obligation goal", is a synthetic
  `VerificationResult` written into the attempt JSON —
  `src/research/obligation_execution.py:93-106`, `problem.py:134-141`). This
  prototype distinguishes them via a prototype-only `failureSource` read-model
  field (`contract_guard | fresh_verifier | runtime`). A production
  application layer that needs faithful classification would require explicit
  failure-origin / outcome-stage information in the evidence (candidate
  shapes: `failure_source: CONTRACT_GUARD | FRESH_VERIFIER | RUNTIME`, or
  `outcome_stage`) — future discussion only, not implemented here.
- **In-text Fact references use `[[fact:<id>|<label>]]` markup** embedded in
  fixture proof strings, rendered as clickable math references. Clicking one
  swaps the document in place (chosen over the drawer, which is reserved for
  machine metadata); a "← Back to main theorem" crumb appears.
- **Elapsed time is session-scoped** (starts when the workspace opens,
  "MM:SS on this page") per ADR-0003; fixtures carry no timestamps.
- **Tooltips are native `title` attributes** (e.g. disabled Retry → "already
  running"). All actions (Retry, Revise & Fork, Archive) are stubs that
  `console.log` and show a "prototype stub" toast.
- **Attempt numbering in the UI ("Attempt 2") is list position**, not the
  `attempt-NNNNNN` id — raw ids appear only in the Inspector.
- URL state is hand-rolled `URLSearchParams` + `pushState`; no router.

## Deliberately not implemented

- Graph view (the disabled tab in B marks the future extension point only).
- Real retry / fork / archive behavior; any mutation whatsoever.
- Timestamps, durations, token/cost metrics on attempts (the backend evidence
  schema does not record them).
- Premise selection, multi-obligation scaffolds, routes — unsupported by the
  current backend (see `docs/kimi_noespire_project_understanding.md` §13).
- Streaming/progress beyond the two inferred RUNNING phases; dark mode; tests.
