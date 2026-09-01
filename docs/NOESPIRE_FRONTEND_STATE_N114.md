# Noespire Frontend State — N1.14 Checkpoint

Canonical checkpoint for re-entering frontend work. Companion documents:
`docs/frontend_n114_sync_source_audit.md` (evidence) and
`docs/frontend_n114_sync_spec.md` (amendments to the frozen V1 spec).

## Product state

- Branch: `noespire-nl-proof-v2`
- Base HEAD (Slice 5 freeze): `aea39dad234c7fb7b3ad45ae9a69037054336067`
- Final checkpoint commit: the commit introducing this file, tagged
  `noespire-n114-frontend-sync` (SHA recorded in the task's final report)
- Date: 2026-09-01
- Dev entry: `python -m application.dev` (backend 127.0.0.1:8173, Vite 5173)

## Research capabilities (validated, frozen)

- **N1.12** multi-node scaffold execution — `MULTI_NODE_EXECUTION_VALIDATED`.
  Predefined AND-DAG of `ScaffoldNode`s materializes into ordinary
  obligations; one deterministic ready node at a time; verifier-gated Fact
  admission; real-Codex smoke produced a 3-Fact supporting closure.
- **N1.13** Static Scaffold Architect — `STATIC_SCAFFOLD_ARCHITECT_VALIDATED`.
  One fresh, one-shot, blind Architect proposes a strict AND-DAG; mechanical
  validation freezes it before the unchanged N1.12 executor runs. No retry,
  repair, or replan.
- **N1.14** obligation-local verifier — `OBLIGATION_LOCAL_VERIFIER_VALIDATED`.
  The verifier judges exactly the candidate statement (Problem = background
  only). Prompt-only change; root-obligation behavior unchanged.

## Product-reachable capabilities

| Capability | Core | Validated | Application | Frontend |
| --- | --- | --- | --- | --- |
| direct root attempt | ✓ | ✓ | ✓ | ✓ |
| multi-node scaffold | ✓ | ✓ | ✗ | ✗ |
| Static Architect | ✓ | ✓ | ✗ | ✗ |
| obligation-local verifier | ✓ | ✓ | ✓ (root usage) | ✓ (root only) |
| multi-Fact closure | ✓ | ✓ | read-model-ready; production creates single-Fact only | renderer ✓, unreachable |
| manual retry | ✓ | ✓ | ✓ | ✓ |
| automatic retry / repair | ✗ | ✗ | ✗ | ✗ |

The only execution path the product exposes is
`POST /api/problems/{id}/attempts → ExecutionService → solve_problem_once()`.
Nothing under `src/application/` references scaffold or Architect code.

## Current UI

- **Home**: problem list (status, display status, attempt count, lineage
  link, last activity), archived hidden by default behind "Show archived",
  Create Problem.
- **Create**: statement-only form → new OPEN workspace.
- **Workspace**: header (statement, status badge, `LLM-verified` when SOLVED,
  Derived-from link, Archive/Unarchive, Revise & Fork, Inspector) + tabs
  `Proof | Attempts`. Default tab: SOLVED→Proof, else Attempts; user tab
  choice survives polling/state transitions.
- **Proof**: SOLVED → Proof Document (serif, KaTeX, named Fact references,
  in-place Fact navigation) + topo-ordered Supporting closure; unsolved →
  "No verified proof yet".
- **Attempts**: newest-first, latest expanded; candidates in the
  unverified register (dashed/amber); PASS attempts keep the candidate as the
  accepted historical artifact; failure panels by class.
- **Inspector**: overlay drawer (scrim, X, Esc) for Problem / Fact /
  Attempt machine metadata + raw JSON.
- **Fork**: dialog prefilled with the current statement → 201 → navigate to
  child (OPEN, 0 attempts, Derived-from link). Allowed in any status.
- **Archive**: metadata-only, idempotent, orthogonal to proof status.

## REST contract (authoritative fields)

- `GET /api/problems` → `{problems: ProblemSummary[]}`: `problem_id`,
  `statement`, `status`, `display_status`, `attempt_count`, `derived_from`,
  `archived`, `last_activity`.
- `POST /api/problems` `{statement}` → 201 `CreateProblemResponse`;
  blank → 400.
- `GET /api/problems/{id}` → `WorkspaceReadModel`: plus `obligation`
  (nullable), `attempts[]` (`attempt_id`, `verdict`, `failure_class`,
  `candidate`, `verifier`, `error`, `started_at`, `finished_at`,
  `verifier_called?`), `target_fact`, `supporting_closure`,
  `running_phase_hint`, `live` (RUNNING only).
- `POST /api/problems/{id}/attempts` → 202; 409 `already_running` /
  `already_solved`.
- `POST /api/problems/{id}/fork` `{statement}` → 201; 404 unknown parent,
  400 blank.
- `POST /api/problems/{id}/archive` `{archived}` → 200; 404 unknown;
  idempotent.

## State semantics

- `OPEN` / `RUNNING` / `SOLVED` derive from the root obligation + the live
  execution table + per-attempt recovery binding; `display_status` adds
  `ERROR` when the latest attempt is a runtime error (obligation truth stays
  OPEN).
- Failure classes: `contract` (guard rejected, verifier never called),
  `rejection` (fresh verifier rejected), `runtime` (infrastructure),
  `interrupted` (crash; `verifier_called` from orphan VERIFIER_INVOKED
  correlation).
- Search state (obligations, candidates, proposals) is never rendered as
  truth; only Facts are `LLM-verified` (blue-cyan; green reserved for a
  future kernel state).
- Retry is manual only. No automatic retry, repair, Adaptive Cut, GraphPatch,
  or fan-out exists anywhere in the system.

## Known gaps

- **Architect/scaffold not product-wired** (the integration gap): validated
  core capabilities with no application entry point. Wiring is a separate
  task; the read-model projection gate is frozen in
  `docs/frontend_n114_sync_spec.md` §8.
- **Scaffold workspaces not representable**: a workspace containing only
  `scaffold:*` obligations would render OPEN with unattributed attempts.
  Unreachable through the product today.
- **Multi-Fact closure unreachable in production**: `POST /api/problems`
  accepts no premise Facts, so production closures are single-Fact; the
  multi-Fact renderer is forward-compatible only.
- Adaptive Cut / Cheap Probe / Local Graph Surgery / automatic retry: not
  implemented (design hypotheses, some experimentally unsupported).
- Lean / Cross-DAG: deferred, not product-wired.
- Graph view/editor: not implemented (ADR-0002: future view inside the
  Workspace, promoted only when multi-obligation scaffolds arrive).

## Validation

- Backend: `pytest -q tests/` → **241 passed, 4 skipped** (matches the N1.14
  report; skips are Docker-dependent tests with the daemon offline).
- Frontend: `npm test` → **95 passed (11 files)**; `npm run typecheck`
  (tsc --noEmit) clean; `npm run build` ✓.
- Dev smoke: `python -m application.dev` — backend `/api/problems` served
  real workspaces (incl. one SOLVED, closure size 1, 1 attempt), Vite
  frontend HTTP 200, `/api` proxy verified; clean shutdown.
- Browser visual audit: not performed by the agent (no browser tooling);
  component-level rendering is covered by the 95 jsdom tests against
  production-shaped fixtures. A human pass over Home / OPEN / RUNNING /
  SOLVED / Inspector is recommended before any public demo.

## Audit verdict

Axis A (architecture/state correctness): no blockers — the UI claims no
unwired capability, search/truth separation holds, the frontend reaches the
core only through REST, status derivation and retry semantics are honest, and
N1.14 verifier semantics are correctly represented for the root-only product
path. Recorded gaps above are integration gaps, not defects.

Axis B (UX): no new findings beyond the frozen Slice 4/5 audits; copy,
failure taxonomy, running-state honesty, and Inspector behavior conform to
CONTEXT.md and ADR-0001…0005.

`FRONTEND_N114_SYNC_AUDIT_PASS`
