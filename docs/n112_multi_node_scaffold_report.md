# N1.12 Minimal Multi-Node Proof Scaffold Execution

## Verdict

`MULTI_NODE_EXECUTION_VALIDATED`

This result establishes only that one predefined natural-language AND-DAG can execute through distinct verifier-gated nodes and produce a multi-Fact supporting closure. It does not compare this route with direct proof, DANUS, or any adaptive decomposition policy.

## Files Changed

- `src/research/scaffold.py`: predefined scaffold state, structural validation, deterministic one-node advance, materialization, resume, and thin solve helper.
- `src/research/attempt.py`: shared N1.11-compatible PASS/FAIL/ERROR attempt evidence around one ordinary obligation execution.
- `src/research/problem.py`: direct-root execution now delegates to the shared attempt wrapper; its public result and behavior are unchanged.
- `tests/test_scaffold.py`: deterministic linear, diamond, failure, resume, recovery, and mechanical-rejection tests.
- `experiments/n112_multi_node_scaffold_smoke/`: frozen input, reproducible runner, real Codex evidence, and one preserved environment-failure attempt.
- `docs/n112_multi_node_scaffold_source_audit.md`: pre-implementation reuse and boundary audit.
- `docs/Noespire_Natural_Language_Proof_Engine_Design_v2.md`: current implementation/evidence status only.

No frontend, Lean, DANUS baseline, retrieval, memory, or database code changed.

## New APIs

Public scaffold seam:

- `ScaffoldNode(node_id, goal, depends_on=(), premise_fact_ids=(), resolved_by_fact_id=None)`
- `ProofScaffold.create(...)`, `ProofScaffold(path)`, `get()`, `list_nodes()`, and `resolve()`
- `advance_scaffold_once(...) -> ScaffoldAdvanceResult`
- `solve_scaffold(...) -> ScaffoldResult`

Internal shared evidence seam:

- `execute_obligation_with_evidence(...) -> AttemptExecutionResult`

`ProofObligation`, `execute_obligation()`, `FactGraph`, `submit_candidate()`, and `solve_problem_once()` retain their prior contracts.

## State Model

The scaffold JSON is proof-search state, not mathematical truth. Each node stores:

```text
node_id
goal
depends_on                 # scaffold node IDs, including unresolved nodes
premise_fact_ids           # existing accepted base Fact IDs only
resolved_by_fact_id | null # written only after verifier-gated admission
```

The `ObligationRegistry` separately stores each materialized node execution. The Fact Graph remains unchanged and contains only verifier-accepted Facts. `ProofObligation.premises` still contains only accepted Fact IDs; it never stores scaffold node IDs or fabricated future Fact IDs.

## Ready-Node Semantics

Before any Codex call, the runtime mechanically validates:

- scaffold/problem/target agreement;
- unique node IDs;
- known target;
- no self-dependency, dangling dependency, or cycle;
- every base Fact is a declared problem premise, exists, and belongs to the same problem;
- every persisted resolution points to an existing Fact with the matching problem and statement.
- every persisted resolution has all declared scaffold dependencies resolved and its Fact predecessors exactly equal the materialized base/dependency Fact IDs.

A node is ready exactly when it is unresolved, all `depends_on` nodes have real resolved Fact IDs, and its materialized obligation is not RUNNING. `advance_scaffold_once()` sorts ready nodes by `node_id`, selects the first, executes at most that one node, persists, and returns. `solve_scaffold()` is only a loop over this public single-step seam and stops on the first BLOCKED result or on SOLVED.

## Materialization Semantics

For a ready node, runtime constructs one stable ordinary obligation:

```text
obligation_id = scaffold:<problem_id>:<node_id>
premises      = accepted base Fact IDs + accepted Facts resolving depends_on
goal          = node.goal
route_id      = scaffold:<node_id>
```

The existing `execute_obligation()` then enforces statement equality, exact predecessor equality, one worker attempt, at most one verifier decision, and Fact admission only on PASS. The target proof subgraph is computed only by `FactGraph.supporting_closure(target_fact_id)` over actual Fact predecessor edges; scaffold edges are not copied into the truth graph.

## Failure Semantics

- A malformed candidate or verifier FAIL leaves the node unresolved and creates no Fact.
- `solve_scaffold()` stops immediately at that failed node, so downstream nodes do not execute and the same node is not retried within the call.
- Already accepted siblings/upstream nodes and their scaffold mappings remain durable.
- Worker/verifier exceptions produce an ERROR attempt artifact, restore a RUNNING obligation to OPEN, and propagate the exception.
- There is no automatic retry, decomposition, scaffold mutation, architect call, classifier, fan-out, or graph surgery.

An explicit later caller may invoke the scheduler again; that is the only retry seam in N1.12.

## Resume Semantics

Reloading `ProofScaffold`, `ObligationRegistry`, and `FactGraph` from disk:

- validates that every recorded resolution still names a real matching Fact;
- rejects pre-resolved nodes at new-scaffold creation and rejects persisted mappings whose predecessor edges bypass the declared scaffold;
- never reruns an already resolved node;
- preserves accepted upstream work after a downstream failure;
- permits a new explicit call to retry the unresolved failed node;
- reconciles a DISCHARGED ordinary obligation into scaffold state without a worker/verifier call if a process stopped between those two durable writes;
- returns SOLVED with zero model calls when the target is already resolved.

No event-sourcing or second graph store was introduced.

## Deterministic Tests

TDD progression began with a missing `research.scaffold` import, then added the public scaffold seam and failure/resume evidence until the focused suite passed.

Commands and final results:

```text
pytest -q tests/test_scaffold.py
14 passed in 0.17s

pytest -q tests/test_scaffold.py tests/test_problem.py
39 passed in 0.33s

pytest -q tests
214 passed, 4 skipped, 1 warning, 40 subtests passed in 8.43s

python -m py_compile src/research/attempt.py src/research/scaffold.py experiments/n112_multi_node_scaffold_smoke/run.py
PASS
```

Coverage includes:

- linear `F0 -> H1 -> H2 -> Target`: three obligations, three worker/verifier calls, four-Fact closure including F0;
- diamond: target remains locked until both siblings resolve and receives both actual Fact IDs;
- upstream PASS followed by FAIL: upstream retained, failed/downstream claims absent from FactGraph;
- process reload and explicit retry: resolved H1 is not re-executed; resolved target is a zero-call no-op;
- DISCHARGED/scaffold write-window recovery without model re-execution;
- cycle, self-dependency, dangling dependency, duplicate node ID, unknown target, and unknown base Fact rejection before worker invocation;
- new-scaffold pre-resolution and tampered same-statement/wrong-predecessor resolution rejection before worker invocation;
- shared attempt PASS/FAIL/ERROR evidence and direct N1.11 regression coverage.

A bare repository-root `pytest -q` is not the product-suite command: it also collects frozen nested DANUS and archived experiment tests, which have unrelated optional Unix/MCP dependencies and duplicate test-module names on Windows. The scoped `tests/` suite above is the applicable Noespire validation.

## Real Codex Smoke

Command:

```text
C:\Users\wmywb\miniconda3\python.exe experiments\n112_multi_node_scaffold_smoke\run.py
```

Frozen predefined route:

```text
n1_base_case:       prove the n = 1 base case
        -> Fact c01d8d0ce1716e1e
n2_induction_step:  prove S_k = k^2 implies S_(k+1) = (k+1)^2
        -> Fact f77b1e0364de7558
target:             use both Facts in mathematical induction
        -> Fact 839d7d86a7fa67a8
```

Observed result:

- result: PASS;
- advances: `ADVANCED`, `ADVANCED`, `SOLVED`;
- attempts: 3, all PASS;
- Codex invocations: 6 in strict worker/verifier alternation;
- fresh thread IDs: 6/6 distinct;
- final Facts: 3;
- target predecessors: `c01d8d0ce1716e1e`, `f77b1e0364de7558`;
- target: `839d7d86a7fa67a8`;
- supporting closure: `c01d8d0ce1716e1e`, `f77b1e0364de7558`, `839d7d86a7fa67a8` (size 3);
- Codex version: `codex-cli 0.151.0-alpha.7.2`;
- token evidence: 127,251 input, 1,426 output, 708 reasoning-output, 0 cached-input;
- wall clock: 1,147.819 seconds;
- error: none.

All frozen evidence is under `experiments/n112_multi_node_scaffold_smoke/artifacts/`:

- `input.json`, `initial_facts.json`, `scaffold_initial.json`;
- `state/attempts/attempt-000001..000003.json`;
- `codex_audits/001..006_*.json`, including prompts, results, events, thread IDs, and usage;
- `state/scaffold.json`, `state/obligations.json`, and raw `state/facts/*.md`;
- `scaffold_final.json`, `facts_final.json`, `supporting_closure.json`, and `result.json`.

The final verifier used a superscript character in its reason. On the Windows GBK console, the original runner raised `UnicodeEncodeError` while printing after it had already written the complete PASS result and every artifact. The runner now emits an ASCII-escaped console summary. A separate read-only artifact check validated PASS, all three advance/verdict values, six distinct threads, closure size three, and the target's exact two predecessor IDs.

Two older runs remain clearly separated from the verdict:

- `arithmetic_case_pass_20260901T095927Z/` is a mechanically successful three-node run that final review correctly rejected as too trivially direct-solvable; it is historical evidence only.
- `failed_attempt_20260901T094836Z/` is the first restricted-network launch. It timed out before a candidate, produced one ERROR attempt, restored the obligation to OPEN, wrote no Fact, and launched no downstream node.

The runtime itself automatically retried neither run.

## Known Limitations

- The scaffold is predefined by the caller; N1.12 does not discover, parse, score, or repair it.
- There is one AND-DAG route only and one deterministic node at a time; no OR routes or parallel execution.
- A failed node remains unresolved until a caller explicitly invokes the scheduler again; there is no policy for whether or when to do so.
- Verification is a fresh LLM verdict, clearly not Lean, kernel verification, or a benchmark superiority result.
- No Adaptive Cut-Set, Cheap Probe, failure classifier, GraphPatch, Local Graph Surgery, critical-gap scheduling, semantic deduplication, or retrieval change is implemented.

## Scope Check

- Unverified scaffold claims in FactGraph: NO.
- Future scaffold references in `ProofObligation.premises`: NO.
- Downstream execution before accepted dependencies: NO.
- Automatic retry or fan-out: NO.
- Resolved-node re-execution: NO.
- Direct-proof semantic change: NO (shared evidence implementation only; regression suite green).
- DANUS baseline mutation: NO.
- Lean or frontend change: NO.

## Review Gate

Final parallel review against fixed point `aea39dad234c7fb7b3ad45ae9a69037054336067`:

- Standards axis: PASS, no remaining blocker/high/medium/low findings.
- N1.12 specification axis: PASS, no remaining blocker/high/medium/low findings.

The first review found two high issues: persisted mappings could bypass scaffold predecessors, and the arithmetic smoke was too direct-solvable. The implementation now enforces exact materialized predecessors with negative tests, and the final smoke uses separate induction base/step Facts jointly at the target. Both reviewers explicitly accepted the fixes and the final `MULTI_NODE_EXECUTION_VALIDATED` verdict.

One review rerun observed `212 passed, 6 skipped` while Docker-dependent tests were unavailable; the recorded final product run in this report observed `214 passed, 4 skipped`. Neither run had a test failure, and the difference is only the existing environment-dependent skip count.
