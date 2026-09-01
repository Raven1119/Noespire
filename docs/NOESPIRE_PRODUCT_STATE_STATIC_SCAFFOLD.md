# Noespire Product State — Static Scaffold Wiring (N1.14P)

Canonical state after wiring the validated static multi-node proof path into
the product. Base: `ab171d5d92a12231d631b970a8aa6368e5bce64b`
(`noespire-n114-frontend-sync`). Design evidence:
`docs/n114p_static_scaffold_product_wiring_source_audit.md`.

## Core

Unchanged — **zero diff under `src/research/`**. The product composes the
validated public APIs only:

- N1.12 `solve_scaffold` / `ProofScaffold` (multi-node execution, resume);
- N1.13 `run_static_scaffold_once` / `ScaffoldArchitect` /
  `validate_scaffold_proposal` / `materialize_scaffold`;
- N1.14 obligation-local verifier (live in both modes).

## Application

- New thin module `src/application/proof_execution.py`: mechanical
  execution-mode detection, mode-aware solved check, and
  `run_product_execution` composing the research APIs. No scheduler,
  validation, verifier-gate, or Architect logic is copied.
- `ExecutionService` gains `architect_factory` (production default:
  `ScaffoldArchitect(IsolatedCodexInvoker())` — same Docker isolation
  boundary, fresh container per invocation, fail-closed). The factory is only
  invoked for a first scaffold-mode start; legacy and resume executions never
  build an Architect.
- Attempt correlation is snapshot-plus-attribution: one product execution ↔
  zero or more node attempts, each adapter invocation attributing the one new
  attempt file; one `ATTEMPT_FINISHED` per node attempt; architect-stage
  failures recorded as execution-level `ATTEMPT_FINISHED(attempt_id=null)`.
- Startup recovery covers ALL RUNNING obligations (not only root) and
  completes orphan `ARCHITECT_INVOKED` events as execution-level INTERRUPTED
  finishes. Idempotent.

## Execution semantics (frozen)

Mode detection per workspace:

```text
scaffold.json exists          → STATIC_SCAFFOLD (corrupt → raise, fail closed)
else root:<id> obligation     → LEGACY_DIRECT
else (fresh problem)          → STATIC_SCAFFOLD
```

- New problem: Architect exactly once → mechanical validation → persisted
  `scaffold.json` → N1.12 executor. Architect config: `ArchitectConfig()`
  (single-node scaffolds allowed, max 6 nodes).
- Architect failure (ARCHITECT_ERROR / ARCHITECT_INVALID / SYSTEM_ERROR):
  no scaffold, no worker/verifier calls, no Facts; problem stays OPEN;
  execution-level failure evidence persisted.
- `solve_scaffold` stops at the first blocked node; upstream Facts persist;
  downstream nodes never execute.

## Manual Retry semantics (frozen)

Retry resumes the SAME persisted scaffold: zero Architect calls, zero
resolved-node re-execution, the blocked ready node executes again. Only after
an architect-stage failure (no scaffold exists) does Retry invoke a fresh
Architect. Retry is never automatic and never a replan.

## Persistence

```text
workspaces/<problem_id>/
├── scaffold.json          # research-owned search state (scaffold mode)
├── obligations.json       # research-owned obligation registry
├── attempts/              # research-owned per-node attempt evidence
├── facts/                 # verified truth (verifier-gated only)
└── _execution_log.jsonl   # application-owned execution events
```

No second proof graph. Truth boundary: `scaffold.json` = search state;
`FactGraph` = verified truth; supporting closure derives from Fact
predecessor edges only.

## REST contract (additive)

`GET /api/problems/{id}` gains:

- `execution_mode: "LEGACY_DIRECT" | "STATIC_SCAFFOLD"`;
- `proof_structure: null | {target_node_id, nodes[]}` — per node: `node_id`,
  `statement`, `dependency_node_ids`, `resolved_fact_id`,
  `latest_attempt_id`, `state` ∈ VERIFIED/RUNNING/BLOCKED/READY/PLANNED
  (projection, never authority);
- `attempts[]` += `obligation_id`, `scaffold_node_id` (server-parsed);
- `last_execution_failure: null | {outcome_stage, error, finished_at}` —
  ARCHITECT_ERROR / ARCHITECT_INVALID / SYSTEM_ERROR / RUNTIME_ERROR /
  INTERRUPTED;
- `obligation`: null in scaffold mode (legacy payload unchanged).

Status: SOLVED iff target node resolved + Fact exists; RUNNING iff live
execution or unrecovered residual RUNNING; else OPEN. ERROR stays
display-level. No new endpoints; 202/409 mappings unchanged.

## Frontend

- Attempts tab: static **Proof plan** list (topo-ordered, state glyphs,
  `LLM-verified` only on VERIFIED nodes, Target tag); per-attempt node
  attribution ("Proof node: …"); execution-level failure panel.
- PASS attempts render as the accepted historical artifact regardless of
  problem status: "became the target Fact" (legacy/target node) vs "became a
  verified Fact" (intermediate node).
- RUNNING: node-specific copy only when exactly one node projects RUNNING,
  with the phase-inferred marker; conservative generic copy otherwise.
- Proof tab unchanged — real multi-Fact closures render through the existing
  document/closure/navigation components.

## Legacy compatibility

Pre-N1.14P workspaces are byte-identical in behavior: same log events, same
payload semantics, same status derivation. Verified by the unmodified legacy
test suite and a live read-model check over the existing `workspaces/` root
(both legacy SOLVED problems report SOLVED / LEGACY_DIRECT /
`proof_structure: null` / single-Fact closure).

## Known gaps

- Production Architect allows a single-node scaffold
  (`require_intermediate=False`); a trivial problem may legitimately solve as
  one node.
- Token usage / Codex thread ids are NOT captured on the production path
  (the isolation invoker does not persist audit artifacts); execution
  evidence is the log + workspace files.
- A corrupt `scaffold.json` fails closed — including taking down the whole
  Home list (`_summarize` detects mode per workspace). Deliberate, but a
  per-row degradation may be revisited.
- No automatic retry, repair, Adaptive Cut, Cheap Probe, GraphPatch, OR
  search, fan-out, iterative Architect, Lean, Cross-DAG, or graph view.

## Tests

- Backend: `pytest -q tests/` → **263 passed, 4 skipped** (Docker online;
  261/6 with daemon offline — environment-dependent skip count only).
  Includes 22 new tests: §23 A–J execution semantics, read-model
  projections, correlation, recovery; recovery/execution files run 5× green.
  One environment-dependent legacy test fix: a test creating a fresh problem
  on the direct path now pre-creates the root obligation (legacy shape),
  matching the frozen mode-detection rule.
- Frontend: `npm test` → **109 passed** (95 legacy + 14 new scaffold tests);
  `tsc --noEmit` clean; `npm run build` clean.

## Real production smoke (HTTP path, real Codex, Docker-isolated)

2026-09-01, fresh smoke root, uvicorn + default production factories:

```text
POST /api/problems  "For every positive integer n, the sum of the first n
                     odd positive integers equals n^2."  → 201
POST /attempts      → 202
```

Observed (`workspaces-n114p-smoke/`):

- ARCHITECT_INVOKED ×1; 3-node scaffold persisted
  (`base_case`, `inductive_step`, `target`);
- WORKER_INVOKED ×3 / VERIFIER_INVOKED ×3, strict alternation, one
  `execution_id`, per-attempt attribution correct;
- ATTEMPT_FINISHED ×3, all PASS; target Fact with exactly the two lemma
  Facts as predecessors; supporting closure size 3;
- read model: `status=SOLVED`, `execution_mode=STATIC_SCAFFOLD`, all nodes
  VERIFIED; live RUNNING observation mid-run showed `base_case` RUNNING /
  `inductive_step` READY / `target` PLANNED with phase hint `generating`;
- wall clock ≈ 2 min 20 s (architect ~25 s + 3 node executions);
- each invocation ran in a fresh isolated container (per-invocation
  isolation); thread-level ids are not captured on the production path.

Controlled BLOCKED case over real HTTP: not stably constructible without
scripting the worker (the production path uses real agents); BLOCKED and
retry-resume semantics are covered by deterministic tests (§23 C/D) with the
same code path.

## Audit (task §30)

1. N1.12 scheduler copied: NO (composes `solve_scaffold`).
2. Architect logic copied: NO (composes `run_static_scaffold_once`).
3. Application changed mathematical semantics: NO (zero `src/research/`
   diff; statement/predecessor/verifier gates untouched).
4. Scaffold state vs Fact truth confusion: NO (closure from Fact edges;
   `proof_structure` documented as projection).
5. Manual Retry secretly replans: NO (architect factory only when no
   `scaffold.json`; deterministic test pins zero Architect calls on retry).
6. Legacy workspaces migrated/broken: NO (tests + live check).
7. One execution ↔ many attempts correlation: CORRECT (attribution set +
   per-attempt finish + smoke evidence).
8. Crash recovery: all-obligation scan + architect-orphan completion;
   idempotence tested.
9. Frontend reads core storage: NO (REST only).
10. UI shows nonexistent Adaptive Cut/auto-retry: NO (copy audit).

Browser visual audit: not performed (no browser tooling in this
environment); component-level rendering is pinned by 109 jsdom tests, and
the live RUNNING/SOLVED read-model states above match the tested fixtures.

## Verdict

`STATIC_SCAFFOLD_PRODUCT_WIRING_VALIDATED`
