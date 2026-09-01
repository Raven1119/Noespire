# N1.14P Static Multi-Node Production Wiring — Source Audit

Pre-implementation audit for wiring the validated static scaffold path
(N1.13 Architect → N1.12 executor) into the product. Base:
`ab171d5d92a12231d631b970a8aa6368e5bce64b` (tag `noespire-n114-frontend-sync`).
Integration only — no new proof-search algorithm.

## 1. Existing research-core seams (reused, not duplicated)

All verified by reading source; nothing here changes behaviorally.

- **Architect**: `ScaffoldArchitect(codex: CodexInvoker).propose(*, problem,
  allowed_facts, config) -> ScaffoldProposal`
  (`src/research/scaffold_architect.py`). `CodexInvoker` is a Protocol:
  `invoke(*, prompt, schema, label)` (`src/research/agents.py:39`).
- **Mechanical admission**: `validate_scaffold_proposal(...)` /
  `materialize_scaffold(path, *, problem, validated)` — pure validation and
  persistence of `scaffold.json`; writes no Facts.
- **One-shot composition**: `run_static_scaffold_once(*, scaffold_path,
  problem, allowed_facts, config, graph, registry, architect, author, worker,
  verifier) -> StaticScaffoldResult` with status ∈ {ARCHITECT_ERROR,
  ARCHITECT_INVALID, SYSTEM_ERROR, EXECUTION_BLOCKED, SOLVED}. Reusable
  verbatim for the first start of a scaffold-mode problem.
- **Resume**: `solve_scaffold(...)` over a loaded `ProofScaffold(path)`
  skips resolved nodes, retries the unresolved ready node, never re-plans —
  this IS the manual-retry semantics the task freezes (task §6). Verified in
  N1.12 resume tests.
- **Per-node execution**: `advance_scaffold_once` materializes
  `scaffold:<problem_id>:<node_id>` obligations and runs the unchanged
  `execute_obligation_with_evidence` gate (statement equality, predecessor
  equality, one worker, one fresh verifier, Fact admission only on PASS).
- **Truth vs search state**: Facts live only in `FactGraph`;
  `scaffold.json` holds search state; `resolved_by_fact_id` is written only
  after verifier-gated admission. Supporting closure comes from
  `FactGraph.supporting_closure(target_fact_id)` over actual Fact
  predecessor edges — never from scaffold edges.
- **Attempt evidence**: `attempts/attempt-NNNNNN.json` already carries
  `obligation_id` (`src/research/attempt.py:139`), so attempt ↔ obligation
  ↔ scaffold-node attribution needs no core change.

## 2. Application seams to extend

- `src/application/execution.py` — `ExecutionService`: claim table,
  worker/verifier DI factories (production default: `ResearchWorker` /
  `ResearchVerifier` over fresh `IsolatedCodexInvoker`, fail-closed),
  `_LoggingWorker`/`_LoggingVerifier` adapters (WORKER_INVOKED /
  VERIFIER_INVOKED appended BEFORE the inner call, frozen ordering),
  ATTEMPT_FINISHED on return/exception, startup recovery.
- `IsolatedCodexInvoker` already implements `CodexInvoker`
  (`invoke(*, prompt, schema, label)`), so the production Architect factory
  is `ScaffoldArchitect(IsolatedCodexInvoker())` — same isolation boundary,
  fresh container per invocation.
- `src/application/workspace_read_model.py` — root-only status derivation;
  per-attempt projection from `attempts/*.json` + `_execution_log.jsonl`.
- `src/application/http.py` — thin adapter; no new endpoints needed.

## 3. The broken assumption (task §9)

Current correlation is snapshot-based: `_new_attempt_id()` = the single
attempt id not in the pre-execution before-set. It assumes **one execution →
at most one attempt** (true for `solve_problem_once`). A multi-node product
run creates N node attempts, so:

- at WORKER_INVOKED/VERIFIER_INVOKED time for node k>1, "ids − before-set"
  yields k ids → `_new_attempt_id` returns None (ambiguous);
- one ATTEMPT_FINISHED cannot carry per-node outcomes.

**Fix design (application-side only)**: the active execution tracks an
attributed-set; each adapter invocation attributes exactly the one new
attempt file written by core `_start_attempt` immediately before the worker
call. At execution finish, one ATTEMPT_FINISHED is appended **per attributed
node attempt** (outcome derived from that attempt's persisted verdict + its
VERIFIER_INVOKED provenance — same taxonomy as today: PASS /
FRESH_VERIFIER_REJECT / CONTRACT_GUARD / RUNTIME_ERROR). The read model's
per-attempt ATTEMPT_FINISHED lookup is unchanged. `ScaffoldResult.advances`
carries explicit per-node `attempt_id`s as the after-the-fact cross-check —
correlation never relies on filename timing.

## 4. Execution-mode detection (task §5)

Mechanical, per workspace:

```text
scaffold.json exists          → STATIC_SCAFFOLD (load failure = error, fail closed)
else root:<id> obligation     → LEGACY_DIRECT
else (fresh problem)          → STATIC_SCAFFOLD
```

Legacy workspaces never grow a scaffold (legacy path never calls the
Architect); scaffold workspaces never grow a root obligation. No migration,
no evidence rewrite.

## 5. Product execution orchestration (new thin module)

New `src/application/proof_execution.py`:

- `detect_execution_mode(problem_dir, problem_id)`
- `is_problem_solved(problem_dir, problem_id, mode)` — scaffold: target node
  `resolved_by_fact_id` + Fact exists; legacy: root DISCHARGED. Drives the
  409 `already_solved` claim check.
- `run_product_execution(...)` —
  - LEGACY_DIRECT → `solve_problem_once()` (unchanged);
  - STATIC_SCAFFOLD, no scaffold yet → `run_static_scaffold_once()`
    (Architect exactly once, validate, materialize, execute);
  - STATIC_SCAFFOLD, scaffold exists → `solve_scaffold()` resume (zero
    Architect calls, zero resolved-node re-execution).
- Architect config: `ArchitectConfig()` production default
  (`require_intermediate=False`, `max_nodes=6`), matching the N1.13 product
  allowance for a single target node.

No scheduler, validation, verifier-gate, or Architect logic is copied; the
module composes public research APIs.

## 6. Architect failure + execution-level evidence

Architect-stage failures produce no node attempts. They are recorded as
`ATTEMPT_FINISHED` with `attempt_id = null` and
`outcome_stage ∈ {ARCHITECT_ERROR, ARCHITECT_INVALID, SYSTEM_ERROR}` (plus
`error` string) — extending the existing Slice-3 rule for pre-attempt
failures, not a new taxonomy. An `ARCHITECT_INVOKED` event appended BEFORE
the Architect call preserves crash provenance; startup recovery completes an
orphan as `ATTEMPT_FINISHED(attempt_id=null, outcome_stage=INTERRUPTED,
recovered=true)`.

Read model gains `last_execution_failure: {outcome_stage, error,
finished_at} | null` — the latest execution-level finish record, null when a
later per-attempt finish supersedes it. This also surfaces today-invisible
pre-attempt runtime failures (e.g. isolation unavailable) — an honesty
improvement, additive only.

After ARCHITECT_ERROR/ARCHITECT_INVALID the problem stays OPEN; no scaffold,
no Facts. The next manual Retry takes the "no scaffold" branch and invokes a
fresh Architect (task §7) — user-driven, not automatic.

## 7. Recovery extension (task §23.J)

`recover_stale_running` currently inspects only the root obligation. For
scaffold workspaces a crash can leave a `scaffold:*` obligation RUNNING —
which would otherwise block resume forever (`advance_scaffold_once` excludes
RUNNING obligations from ready). Extension: iterate **all** registry
obligations; per stale RUNNING obligation, apply the existing per-attempt
logic using that obligation's latest attempt (attempt JSON carries
`obligation_id`). The discharged-crash-window case
(`_try_recover_discharged`) works unchanged via `registry.resolve`; the
subsequent DISCHARGED-obligation/scaffold-write window is reconciled by
`solve_scaffold` itself on the next run (N1.12 resume semantics — DISCHARGED
obligations are not re-executed). Residual-RUNNING-attempt and
finish-record completion steps already iterate all attempts.

## 8. Read-model projection (task §§12–16)

Additive fields only:

- `execution_mode: "LEGACY_DIRECT" | "STATIC_SCAFFOLD"`.
- Status (scaffold mode): SOLVED iff target node resolved + Fact exists;
  RUNNING iff live execution (or pre-recovery residual RUNNING, same rule as
  legacy); else OPEN. ERROR stays display-level only.
- `target_fact` / `supporting_closure`: scaffold mode resolves the target
  node's Fact, then `FactGraph.supporting_closure` — Fact predecessor edges
  only, never scaffold edges.
- `proof_structure` (null in legacy mode): `{target_node_id, nodes:[...]}`
  with per-node `node_id`, `statement` (goal), `dependency_node_ids`,
  `resolved_fact_id`, `latest_attempt_id` (last attempt with
  `obligation_id == scaffold:<pid>:<node>`), and projected `state`:
  VERIFIED (resolved) > RUNNING (live/residual RUNNING attempt on its
  obligation) > BLOCKED (latest attempt FAIL/ERROR) > READY (deps resolved)
  > PLANNED. Projection only — never an authority.
- `attempts[]` += `obligation_id`, `scaffold_node_id` (parsed server-side;
  the frontend never parses obligation ids).
- `obligation`: legacy root payload unchanged; null in scaffold mode (node
  state lives in `proof_structure`).

## 9. Frontend sync (minimal, task §§17–21)

- `types.ts`: mirror the additive fields.
- Attempts tab: static **Proof plan** list at top (glyph + node goal via
  MathText + state label; no graph library); attempt cards show node
  attribution ("Proof node: <goal>") when `scaffold_node_id` is set;
  execution-level failure panel (Architect error/invalid, pre-attempt
  runtime/interrupted) from `last_execution_failure`.
- RUNNING: when one node projects RUNNING, "Proving/Checking <goal>…" with
  the existing phase-inferred marker; otherwise the conservative generic
  copy. No guessing.
- Proof tab: unchanged — real multi-Fact closures render through the
  existing Slice-4 renderer.
- Search-state/truth separation unchanged: only nodes with a real
  `resolved_fact_id` render as verified.

## 10. What is NOT introduced

No Cheap Probe, Adaptive Cut, GraphPatch, Local Graph Surgery, automatic
retry/repair, OR search, fan-out, iterative Architect, verifier→Architect
feedback, Lean, Cross-DAG, graph editor, second proof-graph store, new
failure taxonomy, new endpoints.

## 11. Risks

- **Correlation under multi-attempt execution** — mitigated by the
  attributed-set design + per-attempt ATTEMPT_FINISHED + advances
  cross-check (§3).
- **Recovery of scaffold RUNNING obligations** — mitigated by iterating the
  full registry with per-obligation attempt binding (§7).
- **Legacy regression** — mitigated by keeping the legacy path byte-for-byte
  and gating new behavior on `execution_mode`; full Slice 1–5 test suite is
  the regression boundary.
