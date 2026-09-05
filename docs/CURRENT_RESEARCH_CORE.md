# Current research core — N3A

The supported research entry is `research.dynamic_run.start_run`, `read_status`,
and `resume_run`, also available through `python -m research.dynamic_run`.
It operates on an existing problem workspace. Creating a top-level scaffold and
frontend integration remain separate concerns.

## Execution and truth boundaries

The default `advance_scaffold_once` scheduler selects each node. NodeSolver uses
at most three proof attempts, capped by the remaining run budget. A rejection
produces failure evidence; a typed `TimeoutExpired` uses the existing horizon
handoff. Both can expose a local refinement frontier. True system errors stop.

Each frontier gets one Strategist decision. A passing Strategy Gate permits the
BoundaryAware Builder, fidelity check, existing mechanical validator, and fresh
Structural Auditor. `REVISE` permits the existing single revision; other terminal
outcomes stop. Accepted patches return to default scheduling. There is no new
operator, strategist resampling, automated parent backtracking, or mathematical
memory. Historical manually prepared backtracking states do not imply an automatic
search capability.

Only ClosedBookVerifier PASS admits a Fact. A Structural PASS authorizes OPEN
obligations, not mathematical truth. Post-run FactAuditor classifications and their
dependency cascade are reporting evidence; they do not change search policy or
silently revoke Facts. Report mathematical progress separately from engineering
recovery. Research verification is distinct from later Lean-kernel verification.

## Durable run contract

The existing graph, registry, attempts, and Fact files remain authoritative. The
additional `dynamic_run/` directory stores:

- `state.json`: run ID, current phase/frontier, original runtime and code digest,
  initial budget consumption, completed frontier identities, and stop reason.
- `steps/`: solver attempt IDs, frozen decision contexts/sketches, stage outcomes,
  patch commit intents, and associated evidence. These records are never inserted
  into a model's mathematical context.
- `calls/`: immutable request reservations and completion/error records. A reserved
  call consumes budget even if its process dies. Confirmed responses are replayed
  only inside their original step/role/attempt scope.
- `invocations/`: raw closed-book Codex evidence for fresh calls.

One OS file lock owns the workspace; process exit releases it. `status` reads
without claiming ownership. External graph edits and simultaneous product execution
are unsupported while a run is active. Active runs fail closed on code/runtime
changes. Resuming an already stopped run only reads its final status.

Recovery reuses completed decisions and attempts. An audited patch has a durable
commit intent containing its exact before/after scaffold. An atomic replacement
applies it once; recovery recognizes an already-written after-state. Fact files
are atomically written and content-addressed; recorded candidate/verifier evidence
reconciles a Fact written before registry/scaffold resolution. History is retained.

A request without a durable completion is recorded as `INTERRUPTED`; recovery
does not infer a proof or resample the missing decision. The same run stops with
its consumed budget intact. Terminal runs are inspectable and idempotent to resume.
The recovery guarantee covers process interruption on a local filesystem, not a
distributed transaction or hardware/storage corruption.

## Budget and validation

The existing default limits are 24 solver attempts, 6 applied mutation episodes,
12 proposal-side calls, and 12 audit-side calls. Proposal-side includes Strategist,
Builder, and Reviser; audit-side includes Gate, Fidelity, and Structural Auditor.
The formal runner enforces caps before each call and clips the final NodeSolver
slice to remaining attempts, avoiding the legacy loop's whole-node/whole-episode
overshoot. No restart replenishes a limit. Post-run Fact audits are separately
counted and bounded to once per newly admitted Fact.

For imported pre-N3A runs, `--consumed FILE` reads explicit cumulative counters:
`solver_attempts`, `mutation_episodes`, `builder_proposals`, and `auditor_calls`.
The old workspace alone cannot reliably reconstruct every historical model call;
the importer must supply the recorded consumption when continuing such a run.

Deterministic tests exercise failure → audited graph refinement → verified Facts,
then compare interrupted/resumed runs against uninterrupted graph and budget
outcomes. They cover completed audit, committed patch, completed node, the gap
between Fact storage and obligation resolution, uncertain calls, horizon handoff,
stage timeouts, budget exhaustion, exclusive ownership, and actual process exit.
Real-run inputs and results stay local under the repository contents policy.

## Module ownership and later direction

`research/refinement/` owns the promoted strategy/compilation/audit composition;
experiment modules retain compatibility imports and historical evaluation harnesses.
The formal entry does not import experiment runners or splice their paths into
`sys.path`. Promoted mathematical prompts and schemas retain their existing text.

The [natural-language v2 design](Noespire_Natural_Language_Proof_Engine_Design_v2.md)
records an earlier plan. The [Dual-DAG design](Dual_DAG_Math_Research_Architecture.md)
preserves the deferred direction: supporting closure → Cross-DAG Compiler → Lean.
Neither document's old implementation-status claims override this current entry.
