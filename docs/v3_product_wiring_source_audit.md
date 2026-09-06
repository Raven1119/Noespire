# Proof Core v3 → Product Wiring: Source Audit

Date: 2026-07-19. Branch under audit: `v3-product-wiring` (created from
`0b7e5418f87407b1a4e0e0141d2be7f7fc755d64`, the `proof-core-v3` tip).

Scope: connect the validated Proof Core v3 to the existing Noespire
application + frontend. This audit establishes the actual contracts on both
sides and the minimal wiring seam. No proof-core mathematics is changed.

## 1. What the v3 core actually exposes

### 1.1 Run entry points (`src/research/dynamic_run.py`)

```python
start_run(problem_dir, *, budget=LongHorizonBudget(), consumed=None,
          solver_attempts=3, invoker=None, on_event=None)
resume_run(problem_dir, *, invoker=None, on_event=None)
read_status(problem_dir)   # read-only; no Docker, no model calls
```

CLI equivalent: `python -m research.dynamic_run run|status|resume WORKSPACE`.

Hard contracts found in code:

- `start_run` requires an existing `proof_graph.json`
  (`dynamic_run.py:87-88`); it does NOT create one.
- A second `start_run` on a workspace with `dynamic_run/state.json` raises
  (`dynamic_run.py:92-93`): one run per workspace, ever.
- `resume_run` on a `STOPPED` run is a read-only no-op
  (`dynamic_run.py:114-115`). A stopped run cannot make further progress
  within the core contract.
- `resume_run` refuses when `code_digest` changed (`dynamic_run.py:116-117`)
  — the digest covers `src/research/*.py` and
  `src/application/codex_isolation.py`. Any application wiring MUST NOT edit
  research sources, or every persisted v3 run becomes non-resumable.
- `resume_run` pins the invoker kind: a run started with an injected
  invoker requires one on resume; a real run rejects one
  (`dynamic_run.py:118-121`).
- Workspace-level exclusivity is OS-enforced by `run_lock`
  (`run_storage.py:27-57`); contention raises
  `RuntimeError("research workspace already has an active writer")`.

### 1.2 Run state (`dynamic_run/state.json`, schema_version 3)

`run_id`, `phase` (SELECT / SOLVE / STRATEGY / PATCH / FACT_AUDIT /
STOPPED), `step`, `frontier` (obligation id), `route_id`, `stop_reason`,
`budget`, consumed-usage anchors, `code_digest`, `fact_audits`, `error`.
`stop_reason` values: TARGET_SOLVED, TARGET_REFUTED, FRONTIER_EXHAUSTED,
BUDGET_EXHAUSTED, SYSTEM_ERROR, ATTENTION_LIMIT, STRATEGIST_TIMEOUT,
STRATEGIST_DECLINE, INTERRUPTED, plus PATCH-stage outcomes used as stop
reasons. There is no "pause" state — a run is either live (phase ≠
STOPPED), terminally STOPPED, or mid-crash (phase ≠ STOPPED, no live
writer).

`read_status` additionally returns `consumed`, `ready` (frontiers),
`current_attempt` (from the active step's `solver.json`), `facts`.

### 1.3 ProofGraph (`src/research/proof_graph.py`)

- `ProofGraph.create(root, problem_id=..., target=ProofObligation.create(...),
  routes=(...))` — the public constructor for a fresh graph. A new problem is
  exactly: one OPEN target obligation + one DIRECT route with no
  prerequisites (this is what `tests/test_dynamic_run.py::workspace` builds).
- Obligations: `truth_state` OPEN / DISCHARGED / REFUTED, plus
  `resolved_fact_id`, `resolved_route_id`, `refutation_id`. `statement`
  includes context.
- Routes: `kind` DIRECT / SPLIT / CUT / ALTERNATIVE; persistent `lifecycle`
  OPEN / EXHAUSTED (with `exhaustion_attempt_ids` + `exhaustion_reason`);
  `origin_patch_id` provenance.
- `route_state(route_id)` derives READY / WAITING / IMPOSSIBLE / EXHAUSTED
  (`proof_graph.py:220-227`) — backend computes this; the frontend must not.
- `frontiers()` returns target-reachable `Frontier(kind=PROOF|STRUCTURAL,
  obligation_id, route_id)`, structural first (`proof_graph.py:229-250`).
- `supporting_closure()` — target Fact closure via FactGraph predecessors
  (search structure is never used as proof dependency).
- Load/save validate everything fail-closed (identity, truth links, route
  evidence, DAG acyclicity, Fact lineage).

### 1.4 Attempt records (`attempts/attempt-*.json`, written by
`src/research/proof_execution.py`)

v3 schema — NOT the legacy `verdict` schema:

```json
{"attempt_id", "obligation_id", "route_id",
 "outcome": "RUNNING | NO_RESULT | PROOF_REJECTED | COUNTEREXAMPLE_REJECTED
            | TIMEOUT | ERROR | INTERRUPTED | FACT_ADMITTED
            | REFUTATION_ADMITTED",
 "candidate": {"kind", "statement", "proof", "counterexample", "reason",
               "predecessors"},
 "verification": {...}, "fact_id", "refutation_id", "reason"}
```

The legacy read model keys (`verdict`, `candidate_artifact`,
`verifier_artifact`, `error`) do not exist. Any shared reader must branch.

### 1.5 Refutations (`src/research/refutation.py`)

`RefutationStore(root)` — `list()` / `get(id)`; admission requires all four
independent RefutationVerifier checks. Refutations live outside the Fact
DAG. Fields: `refutation_id`, `obligation_id`, `context`, `goal`,
`counterexample`, `verification_evidence` (incl. `reason`), `provenance`.

### 1.6 GraphPatch / refinement history (`src/research/proof_patch.py`,
`refinement/route_driver.py`)

- Applied patches: `proof_graph.json.applied_patches` maps
  `patch_id → {target_obligation_id, operator}` (key-sorted, so NOT in
  application order).
- Full evidence: `graph_patches/<patch_id>/approved.json` —
  `{patch: {obligations: [goals...], routes: [...]}, approval, ...}`.
- Application ORDER is recoverable from `dynamic_run/steps/NNNNNN/patch.json`
  (`{"outcome": "PATCH_APPLIED", "patch_id": ...}`); step dirs are numbered.
- The strategist's "why" (obstruction / idea) lives in
  `steps/NNNNNN/sketch.json` as raw model output. The read model exposes the
  durable, already-validated record (operator, target, child goals, route
  exhaustion reasons) and does not re-parse model prose.

### 1.7 Isolation boundary

`SolInvoker → ClosedBookCodexInvoker → IsolatedCodexInvoker`
(`run_invocations.py:77-82`, `closed_book.py`): real v3 runs execute inside
the same Docker-isolated, fail-closed Codex container as the current
product (image `noespire-codex-isolated:local`), with closed-book options.
No new isolation surface. `real_runtime()` requires Docker at run start;
without Docker the run fails before any model call.

## 2. What the current application actually does

(`src/application/`, identical on both branches — verified by empty
`git diff noespire-nl-proof-v2 proof-core-v3 -- src/application/ frontend/`.)

- `http.py` — thin FastAPI adapter; POST `/api/problems/{id}/attempts`
  returns 202 / 409 `already_solved` / 409 `already_running` / 404.
- `execution.py` — `ExecutionService`: claim table (one live execution per
  problem), background thread, `worker_factory`/`verifier_factory`/
  `architect_factory` DI seams, logging adapters writing
  `_execution_log.jsonl`, startup `recover_stale_running()`.
- `proof_execution.py` — mode detection (`LEGACY_DIRECT` if
  `root:<problem_id>` obligation, `STATIC_SCAFFOLD` if `scaffold.json`,
  default `STATIC_SCAFFOLD` for fresh problems), `is_problem_solved`,
  `run_product_execution` composing public research APIs.
- `workspace_read_model.py` — the single REST aggregate; projections for
  legacy + scaffold modes; per-attempt `obligation_id`/`scaffold_node_id`
  resolved server-side.

### 2.1 Compatibility hazards found (must be handled by the wiring)

1. `execution.py` recovery helpers read `raw["verdict"]` from every
   `attempts/attempt-*.json` — KeyError on v3 attempt files
   (`_recover_residual_running_attempts`, `_complete_missing_finish_records`).
2. `workspace_read_model._project_attempt` reads legacy-only keys —
   KeyError on v3 attempts.
3. `current_attempt_id` reads `verdict == "RUNNING"` — v3 uses
   `outcome == "RUNNING"`.
4. v3 workspaces have no `obligations.json` / `scaffold.json`; all
   registry/scaffold projections must branch away.

## 3. Minimal wiring seam (decided)

Mode detection becomes three-way, fresh problems default to v3:

```text
proof_graph.json present            → DYNAMIC_PROOF_V3 (load = validate)
scaffold.json present               → STATIC_SCAFFOLD
root:<id> obligation present        → LEGACY_DIRECT
otherwise (fresh problem)           → DYNAMIC_PROOF_V3
```

Execution, per user Start/Retry click (one claim, one core call):

```text
no proof_graph.json
    → ProofGraph.create(target obligation from statement + one DIRECT route)
    → start_run(invoker)
state.json phase != STOPPED
    → resume_run(invoker)              (crash recovery; write-ahead calls
                                        make re-entry non-duplicating)
STOPPED + target DISCHARGED
    → blocked earlier by is_problem_solved → 409 already_solved
STOPPED + any other reason
    → 409 run_stopped (terminal; no core API can advance it)
```

Application composes only `ProofGraph.create`, `start_run`, `resume_run`,
`read_status`, `ProofGraph` reads, `FactGraph`, `RefutationStore`. No
scheduler/strategy/verifier logic is copied.

DI seam: `ExecutionService(dynamic_invoker_factory=...)`; production
default `None` → core builds `SolInvoker` (Docker-isolated). Tests inject a
scripted invoker — the same seam `tests/test_dynamic_run.py` uses.

## 4. Status mapping (product ← v3)

| v3 state                                   | product status | notes |
|--------------------------------------------|----------------|-------|
| target DISCHARGED + Fact exists            | SOLVED         | fail-closed Fact check |
| live execution claim                       | RUNNING        | app claim table, authoritative |
| phase ≠ STOPPED, no live execution         | OPEN           | crashed run; resumable via Retry → resume_run. `dynamic.phase` tells the UI it was interrupted |
| STOPPED, target REFUTED / exhausted / etc. | OPEN           | `dynamic.stop_reason` carries the truth; Retry → 409 run_stopped |
| latest attempt outcome ERROR               | display ERROR  | same display-only rule as legacy |

## 5. Read-model projection (backend computes all graph semantics)

New top-level keys on the workspace aggregate (null/absent in old modes;
old keys unchanged):

- `execution_mode`: gains `"DYNAMIC_PROOF_V3"`.
- `dynamic`: `{run_id, phase, stop_reason, error, frontier_obligation_id,
  current_attempt_id}` — null before the first run.
- `proof_graph`: `{target_obligation_id, obligations: [{obligation_id,
  goal, context, statement, truth_state, resolved_fact_id,
  resolved_route_id, refutation_id, latest_attempt_id}], routes:
  [{route_id, target_obligation_id, prerequisite_obligation_ids,
  support_fact_ids, kind, lifecycle, derived_state, exhaustion_reason,
  origin_patch_id}], frontiers: [{kind, obligation_id, route_id}]}`.
- `refutations`: `[{refutation_id, obligation_id, goal, counterexample,
  reason}]`.
- `patches`: ordered `[{step, patch_id, operator, target_obligation_id,
  obligation_goals}]` from `steps/*/patch.json` + `approved.json`.
- `attempts`: v3 attempts mapped into the existing Attempt envelope
  (`outcome` preserved verbatim; `verdict` mapped PASS/FAIL/ERROR/RUNNING
  for shared display plumbing; `obligation_goal`, `route_id`, `fact_id`,
  `refutation_id` added server-side).
- `target_fact` / `supporting_closure`: from `ProofGraph.supporting_closure()`
  (Fact predecessors, never route edges).

The frontend never parses ids, never infers AND/OR or route viability, and
never reads core files.

## 6. Known core-contract gaps (to report, not to fix here)

1. **No re-run API**: a STOPPED run is terminal (`start_run` refuses,
   `resume_run` no-ops). Product Retry on an exhausted/stopped workspace is
   blocked with 409 `run_stopped`; the existing Revise & Fork path is the
   product-level answer. A core "new run / budget top-up" API would be a v3
   change requiring its own decision.
2. **code_digest coupling**: resumability of every persisted v3 run depends
   on byte-identical `src/research/*.py` + `application/codex_isolation.py`.
   Any later research-code edit orphans live workspaces (resume refuses).
   This wiring touches none of those files.
3. **Interruption costs a route attempt**: an attempt left RUNNING by a
   kill is marked INTERRUPTED on resume and occupies one of the route's
   bounded attempts (`proof_execution.py` replay loop). Core semantics;
   surfaced here only for UI honesty (attempts list can show INTERRUPTED).

## 7. Explicitly out of scope (task card)

No prompt/semantics/scheduler/budget changes, no new operators, no graph
canvas/library, no WebSocket, no WebGL. Old workspaces (LEGACY_DIRECT,
STATIC_SCAFFOLD) remain readable and executable; no migration.
