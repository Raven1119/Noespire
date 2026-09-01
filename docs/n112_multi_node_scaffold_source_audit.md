# N1.12 Multi-Node Scaffold Source Audit

## Scope and frozen inputs

- Product baseline: `noespire-nl-proof-mvp` plus the current application/frontend commits on `noespire-nl-proof-v2`.
- Frozen DANUS baseline: `6d92e8d415933ca2ef52fd1a4da73fdfcd418f1c`, clean and unchanged.
- This slice adds one predefined AND-DAG execution path. It does not add scaffold generation, retries, parallelism, failure classification, Cut-Set refinement, graph mutation, or frontend behavior.

## Decisions

| Area | Decision | Evidence and N1.12 use |
| --- | --- | --- |
| `Fact` and content identity | KEEP_EXISTING | A scaffold claim becomes a Fact only through the existing verifier gate. No future Fact IDs are fabricated. |
| `FactGraph` persistence and `supporting_closure()` | KEEP_EXISTING | Accepted node results use ordinary predecessor Fact IDs; the final proof subgraph is derived only from the target Fact. |
| `submit_candidate()` and fresh verifier seam | KEEP_EXISTING | Truth admission and one verifier decision per well-formed candidate remain unchanged. |
| `ResearchWorker` / `ResearchVerifier` / `CodexExec` | KEEP_EXISTING | Each node attempt delegates to the existing one-worker, one-ephemeral-verifier path. |
| `ProofObligation.premises` | KEEP_EXISTING | It continues to mean accepted Fact IDs only. It is not widened to include scaffold-node references. |
| `execute_obligation()` | KEEP_EXISTING | A ready scaffold node is materialized into an ordinary obligation and executed once. No loop or retry is added inside this function. |
| `ObligationRegistry` | ADAPT BY COMPOSITION | It persists each materialized node obligation and its OPEN/RUNNING/DISCHARGED state without schema changes. |
| N1.11 attempt evidence | ADAPT | The same candidate/verifier/error evidence behavior is shared by direct-root and scaffold-node attempts rather than duplicated. |
| `ProblemSpec` / `solve_problem_once()` | KEEP_EXISTING | The direct-proof public path and its application callers remain behaviorally unchanged. |
| Scaffold node/state store | NEW | A thin JSON layer stores node ID, full goal, scaffold dependencies, verified base-Fact inputs, and resolved Fact ID. It is search state, never truth. |
| Deterministic node advance | NEW | `advance_scaffold_once()` selects the lexicographically first ready unresolved node and performs at most one node attempt. |
| Whole-scaffold helper | NEW | `solve_scaffold()` repeatedly advances distinct ready nodes, stopping immediately on target resolution or the first blocked/failed advance. |

## Why the current product path is root-only

`solve_problem_once()` constructs one stable `root:<problem_id>` obligation whose goal is the complete theorem statement, then calls `execute_obligation()` at most once. It has no persisted object representing intermediate claims or dependencies between unresolved claims, so there is nothing to unlock after the root attempt.

## Why obligation premises cannot represent future nodes

`execute_obligation()` immediately loads every premise with `FactGraph.get_fact(fact_id)` and later requires the candidate predecessor set to equal those same IDs. This is the truth boundary: every obligation premise is already accepted. A scaffold dependency such as `H1 -> H2` exists before `H1` has a Fact ID, so putting `H1` into `ProofObligation.premises` would either fail lookup or counterfeit future truth. N1.12 must resolve scaffold dependencies to actual accepted Fact IDs only when a node becomes ready.

## Modules that must remain unchanged in meaning

- `fact.py`, `graph.py`, and `pipeline.py`: accepted truth, content addressing, predecessor integrity, verification gate, and supporting closure.
- `obligation.py`: `premises` remains accepted Fact IDs; ordinary failure remains OPEN; DISCHARGED requires a real Fact.
- `obligation_execution.py`: one worker attempt and at most one verifier decision, with no retry/fan-out.
- `problem.py`: stable direct-root semantics, attempt evidence, and reload behavior.
- `agents.py`: fresh Codex invocation behavior and audit artifacts.

## DANUS reuse assessment

DANUS provides the already-adapted Fact Graph, worker contract, verifier gate, and durable worker artifacts. Its orchestration layer launches a configured worker pool and each worker runs repeated continuation rounds until stopped; that is intentionally broader than N1.12 and would violate the one-ready-node-at-a-time/no-automatic-retry scope. No DANUS scheduler or process infrastructure should be copied. A small deterministic selector over persisted scaffold state is the required new code.
