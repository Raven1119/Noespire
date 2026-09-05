# Noespire State — DANUS-Level Proposition Core (Frozen)

**Status:** frozen. Verdict: `DANUS_LEVEL_PROPOSITION_CORE_VALIDATED`
(with the documented Case C/D caveat — see below).
**Base:** `noespire-nl-proof-v2` @ `0428c9dc832301e23e0ce31caf90f049cc6e4723`
(`noespire-static-scaffold-product`) + this change set.
**Evidence:** `docs/danus_proposition_core_reuse_audit.md`,
`docs/danus_proposition_core_implementation_report.md`,
`docs/danus_proposition_core_real_validation.md`,
`docs/danus_proposition_core_failure_observations.md`,
`experiments/danus_proposition_core_validation/`.
Supersedes the "no automatic repair" gap of
`docs/NOESPIRE_PRODUCT_STATE_STATIC_SCAFFOLD.md` (see its supersession note);
everything else in that document still holds.

## Frozen contracts

### Node Solver contract

- `NodeSolver.solve_obligation(...)` (src/research/node_solver.py) runs the
  bounded verifier-guided repair loop for one existing obligation:
  SOLVED / BLOCKED / ERROR, with `attempt_ids` and the last failure reason.
- `execute_obligation` stays single-attempt; the loop lives only in
  `NodeSolver`. Each round is one `execute_obligation_with_evidence` call with
  its own durable `attempts/attempt-%06d.json` artifact.
- Round 1 invokes the worker in the legacy one-shot shape; rounds ≥ 2 carry
  `RepairContext(previous_statement, previous_proof, verifier_reason,
  attempt_number, max_attempts)` (src/research/pipeline.py).

### Repair semantics

- **Bounded:** `NodeSolverConfig.max_attempts_per_obligation ≥ 1`.
  Product default **3** (`ExecutionService`); research default **1**
  (= legacy one-shot). Frozen after real evidence (§17 of the validation
  report): 51/51 provable obligations needed one attempt; the only
  multi-round case was unprovable at any budget.
- PASS → exactly one verifier-admitted Fact; FAIL → never a Fact; budget
  exhausted → BLOCKED, obligation stays OPEN. **BLOCKED ≠ statement false.**
- Worker/verifier exception → ERROR, stops immediately, does not burn budget.
- Contract-guard mismatch counts as a failed round without calling the
  verifier; its reason feeds the next repair context.

### Fact truth boundary

- Only verifier PASS admits a Fact. The verifier is fresh and
  obligation-local (N1.14), never sees repair policy, never mutates state.
- `FactGraph` is the only verified-truth store: content-addressed,
  predecessor existence + same-problem + **revoked-predecessor guard**;
  `descendants()`; cascade `revoke()` moving files to `_revoked/` with a
  per-fact `revocation_log.jsonl` record (historical record preserved).
- Revoked resolved Facts make solved checks / resume / read models **fail
  closed** (KeyError). No dynamic refinement on revoke (out of scope).

### Scheduler seam

- `ready_nodes(scaffold, registry)` is the public readiness query;
  `ScaffoldScheduler` Protocol + `FirstReadyScheduler` (default = legacy
  `ready[0]`). The executor receives the selected node and knows nothing
  about selection policy. Schedulers are replaceable without touching the
  Node Solver.

### Attempt semantics

- One attempt artifact per worker/verifier round; attempts are never merged
  or overwritten. Application correlation stays snapshot-plus-attribution;
  one `ATTEMPT_FINISHED` per attempt; strictly sequential rounds guarantee
  one-RUNNING-at-a-time.

### Resume semantics

- `solve_scaffold` resumes the persisted scaffold; already-resolved nodes
  never re-execute; a DISCHARGED obligation short-circuits without a worker
  call. Manual Retry (product): same scaffold, zero Architect calls, the
  blocked obligation gets a fresh bounded solve session, attempt IDs
  continue. Retry is never automatic and never a replan.
- Persisted node mathematical semantics (`goal`, `depends_on`,
  `premise_fact_ids`) are immutable after creation; only
  `resolved_by_fact_id` is ever written, only via `ProofScaffold.resolve`.

### Legacy compatibility

LEGACY_DIRECT workspaces are behavior-identical: one-shot worker/verifier,
no scaffold creation, same read-model semantics (validated in the real path,
Case G).

## Product behavior (validated in the real path, 2026-09-02)

14 provable theorems SOLVED end-to-end (incl. Lagrange four-squares, 6
nodes); a false statement correctly BLOCKED with bounded repair and complete
evidence; manual Retry semantics confirmed; legacy path confirmed.
Full case table: `docs/danus_proposition_core_real_validation.md`.

**Case C/D caveat (explicit):** a natural verifier FAIL on a provable
obligation was not observable — 51/51 obligations passed on attempt 1 across
11 attempted theorem types. FAIL→repair→PASS is pinned deterministically;
the repair loop's real-path execution is validated via Cases E/F. This is a
model-capability finding, not a defect; it is the primary datum of
`docs/danus_proposition_core_failure_observations.md`.

## Known limitations

- Repair-success never observed in the real path (caveat above).
- Token/thread metadata not captured on the production path.
- Real multi-node BLOCKED (upstream persistence / downstream locking under
  repair exhaustion) is validated deterministically only.
- `descendants`/`revoke` are scan-based (MVP scale).

## Explicit out-of-scope (unchanged; future phases)

Adaptive Cut, Cheap Probe, Failure Diagnoser, GraphPatch, Local Graph
Surgery, Progress Contract, Graph Revision, **full OR search**, route
parking/revival, critical-gap scheduling, parallel siblings, project memory,
persistent research loop, literature search, Lean, Cross-DAG.

**Future search representation (seam reserved, not implemented):** a
Proof-Obligation Hypergraph with AND/OR route semantics — one route's
prerequisites are conjunctive (AND); alternative routes to the same
obligation are disjunctive (OR). The current scaffold keeps one route per
node; `ScaffoldNode.depends_on` is documented as the node's current route and
`research.obligation.Route`/`route_id` is the nominal seam. The next phase
MUST be designed from `docs/danus_proposition_core_failure_observations.md`.

## Architecture decision — local verified boundary dependencies (N2Y, 2026-09-05)

> A Proof Obligation may depend on verifier-accepted Facts in its permitted
> local boundary, regardless of whether those Facts were original problem
> premises or were derived earlier in the same research run.

Concretely, `ScaffoldNode.premise_fact_ids` (and the resulting
`ProofObligation.premises` / `Fact.predecessors`) means **proof
predecessors**, not "original problem premises". For `INSERT_CUT_SET` the
legal set is `declared_problem_premise_fact_ids ∪
local_verified_boundary_fact_ids`, where the boundary is the mechanically
constructed `LocalRefinementContext.verified_boundary` (accepted, not
revoked, same problem) — never the whole FactGraph. A verified boundary Fact
is not a new assumption; the truth boundary is unchanged (only Verifier PASS
admits Facts). SPLIT and ADD_ALTERNATIVE_ROUTE premise semantics are
unchanged. Evidence: `docs/n2y_local_verified_boundary_dependencies_report.md`
(`LOCAL_VERIFIED_BOUNDARY_DEPENDENCIES_SUPPORTED`).

## Architecture decision — alternative-route boundary Facts (N2AG)

The user-authorized N2AG change extends the N2Y dependency contract to
`ADD_ALTERNATIVE_ROUTE`. This supersedes only the ALT restriction in the
N2Y decision above; SPLIT remains unchanged. N2Z's protocol and CUT-specific
measurement code describe its earlier experiment, not the current ALT
admission contract.

The permitted premise set for an alternative-route child is now
`declared_problem_premise_fact_ids ∪ local_verified_boundary_fact_ids`.
The caller supplies the mechanically constructed local boundary; a cited
Fact must still exist as accepted, not revoked, and belong to the same
problem. An unrelated Fact elsewhere in the graph is not authorized merely
because it is accepted. No new Fact fields or truth-admission rules are
introduced. New proof Facts retain their actual predecessors and supporting
closure through the existing execution path.

The reason for this extension is to express a replacement mathematical
route that uses already established local knowledge. A targeted frozen
ALT replay exercised admission, structural audit, apply, and downstream
proof execution; deterministic regression tests cover invalid boundary
references and preservation of Fact lineage. These validate expression and
execution support, not the truth or solvability of every proposed route.
Per-run outputs and reports are retained locally outside new commits.

Returning from a false child to its parent was a manually prepared
experimental state. This decision does not introduce automatic
counterexample-driven backtracking, new operators, prompt changes, retries,
or a larger budget.

## Regression at freeze

- Backend: **301 passed, 4 skipped** (skips environment-dependent).
- Frontend: **109 passed**, `tsc --noEmit` clean, `npm run build` clean.
- Real proof smoke suite: see case table in the validation report.
