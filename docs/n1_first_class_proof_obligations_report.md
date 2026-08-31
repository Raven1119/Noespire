# N1 First-Class Proof Obligations Report

## DANUS Reuse Audit

| Component | Source | Decision | Noespire implementation |
| --- | --- | --- | --- |
| Fact schema and content identity | `danus/core/schema.py` | KEEP_EXISTING | `src/research/fact.py` Phase 0A adaptation |
| File-backed Fact Graph | `danus/core/factgraph.py` | KEEP_EXISTING | `src/research/graph.py` |
| Verifier-gated submission | `danus/gateway/server.py::fact_submit` | KEEP_EXISTING | `src/research/pipeline.py::submit_candidate` |
| DANUS worker contract | `agents/contracts/worker.md`, `danus/execution/loop.py` | ADAPT | Existing `ResearchWorker` receives one obligation-specific goal and its exact premise Facts |
| Fresh verifier | `agents/contracts/verifier.md`, `danus/verify/launcher.py` | KEEP_EXISTING | Existing `ResearchVerifier` plus one ephemeral `CodexExec` invocation per verdict |
| Fact persistence | `danus/core/factgraph.py` | KEEP_EXISTING | Existing Fact Markdown persistence |
| Supporting closure | `danus/write_paper/assemble.py` | NOT_NEEDED | Existing closure implementation remains unchanged |
| Memory, retrieval, gateway roles, swarm, orchestration | DANUS runtime modules | NOT_NEEDED | Not introduced for N1 |
| Proof Obligation, Route, Registry | No DANUS first-class equivalent | NEW | `src/research/obligation.py` |
| Obligation execution seam | No direct DANUS equivalent | NEW | `src/research/obligation_execution.py` composes existing worker/verifier/truth modules |

The detailed source comparison is in `docs/n1_danus_reuse_audit.md`. No frozen DANUS source was copied, and Noespire product code has no runtime dependency on `baselines/danus`.

## New Code

- ProofObligation: immutable `O = (premises -> goal)` state with `OPEN`, `RUNNING`, `DISCHARGED`, and a retained-but-unused `REJECTED` enum value. Ordinary candidate or verifier failure returns `RUNNING -> OPEN`.
- Route: explicit route identity plus the obligation IDs belonging to that OR alternative.
- ObligationRegistry: deterministic JSON add/get/list, guarded transitions, exact duplicate protection, accepted-Fact resolution, and reload.
- execution seam: `execute_obligation(...)` loads accepted premises, supplies the complete AND input to the existing worker, validates the returned goal and predecessor identity, submits through the existing verifier gate, and resolves only after the admitted Fact is readable from `FactGraph`.

## Current Execution Policy

- experimental default: `single-worker-first`
- evidence: N1.9b strictly matched scheduling ablation, verdict `SINGLE_WORKER_FIRST_SUPPORTED`
- normal OPEN attempt: exactly one `ResearchWorker.propose(...)` call; no loop, pool, fan-out, or retry exists in `execute_obligation(...)`
- well-formed candidate: exactly one fresh verifier call through `submit_candidate(...)`
- malformed goal/predecessor identity: deterministic rejection before the truth gate, with no verifier cost
- PASS: exactly one content-addressed Fact is admitted and the obligation becomes `DISCHARGED`
- FAIL: FactGraph is unchanged, `resolved_by_fact_id` remains null, the obligation returns to `OPEN`, and no second worker is launched automatically
- later retry: only a new explicit caller invocation; no recovery policy is implied
- Adaptive Cut-Set, GraphPatch, failure classification, and Local Graph Surgery: `NOT IMPLEMENTED`; current diagnostics provide no evidence for a specific automatic escalation policy

## N1.11 Minimal Direct-Proof MVP

- public interface: `solve_problem_once(...)`
- input: `ProblemSpec(problem_id, complete theorem statement, optional accepted premise Fact IDs)`
- root: stable `root:<problem_id>` obligation on route `root`; reusing a problem ID for a different theorem or premise set is rejected mechanically
- execution: delegates one OPEN root to the existing `execute_obligation(...)` single-worker-first seam
- solved result: only reconstructed from a `DISCHARGED` root whose accepted target Fact is readable from `FactGraph`; closure comes directly from `FactGraph.supporting_closure(...)`
- open result: FactGraph unchanged, root `OPEN`, `resolved_by_fact_id` null, and one durable JSON attempt record linking problem, obligation, candidate, verifier verdict, and outcome
- resume: a reloaded solved root returns the existing target and closure with zero worker/verifier calls; a reloaded failed root remains `OPEN` until another explicit call
- source audit: `docs/n111_e2e_mvp_source_audit.md`
- scope: no parser, planner, scheduler, retry loop, failure classifier, Cut-Set, GraphPatch, Local Graph Surgery, Lean, or mapping

## Reused DANUS Infrastructure

- Existing content-addressed `Fact` and file-backed `FactGraph` adaptation.
- Existing verifier-gated `submit_candidate` truth-write path.
- Existing DANUS-derived `ResearchWorker` contract.
- Existing fresh/stateless `ResearchVerifier` contract and ephemeral Codex process adapter.
- Existing Fact persistence and supporting-closure behavior.

## Failure-Semantics Fix

- before: an ordinary verifier FAIL transitioned the obligation from `RUNNING` to terminal-looking `REJECTED`.
- after: verifier FAIL and deterministic candidate-shape rejection both transition `RUNNING -> OPEN` without admitting a Fact or setting `resolved_by_fact_id`.
- reason: a failed proof candidate is evidence only about that attempt, not evidence that the Proof Obligation is false.
- retry control: attempt A fails and leaves the graph unchanged; an explicit attempt B passes, admits exactly one Fact, and transitions the same obligation to `DISCHARGED`.

## Truth-Boundary Verification

- OPEN -> FactGraph: never; registry search state and Fact storage use separate files and interfaces.
- verifier FAIL: FactGraph remains unchanged, `resolved_by_fact_id` remains null, status returns to `OPEN`, and the obligation remains available for a later explicit attempt.
- verifier PASS: exactly one content-addressed Fact is admitted, then the obligation becomes `DISCHARGED`.
- idempotence: executing an already discharged obligation reads back the same admitted Fact without another worker/verifier call or graph write.
- resolution integrity: `resolved_by_fact_id` is set only by `resolve`, which first reads the accepted Fact from `FactGraph` and checks its statement against the obligation goal.

## AND / OR Verification

- AND: one three-premise obligation supplies all F1/F2/F3 Facts jointly to one worker invocation; the admitted target Fact retains all three predecessor IDs.
- OR: obligations with the same goal but distinct `route_id` values remain distinct alternatives. They are not encoded as one target with combined predecessor edges.

## Tests

- command: `wsl -e bash -lc 'cd /mnt/c/Users/wmywb/PycharmProjects/Noespire && PYTHONPATH=src baselines/danus/runtime/venv/bin/python -m unittest discover -s tests -v'`
- passed: 53
- skipped: 1 pre-existing opt-in Phase 0A real-Codex smoke
- failed: 0
- compile check: `baselines/danus/runtime/venv/bin/python -m compileall -q src tests experiments/n1_triangular_sum_smoke/run.py` -> PASS
- single-worker-first controls: worker calls = 1, verifier calls = 1, and verifier FAIL launches no second worker
- N1.11 controls: root/PASS/FAIL/reload semantics, linked attempt evidence, exception recovery, and evidence-write preflight
- deterministic controls: scripted two-premise PASS and FAIL paths both PASS; an explicit FAIL -> OPEN -> retry -> PASS control admits exactly one Fact and ends `DISCHARGED`

## Real Smoke

- problem: frozen Baseline A `triangular_sum`
- accepted premise: archived upstream-verified Fact `30b6f70e453bbdaa`, materialized as Noespire Fact `96607ae530927290`
- worker: `research_worker`, fresh Codex thread `01a047f1-ad80-7260-9776-a740afa790e8`
- verifier: `research_verifier`, independent fresh Codex thread `01a047f4-d60a-7f71-a5dd-949fe19bc577`, verdict accepted
- resulting fact: `7d15fc7567e7dd7f`
- obligation final state: `DISCHARGED`, `resolved_by_fact_id=7d15fc7567e7dd7f`
- FactGraph before/after: 1 / 2 Facts
- token evidence: input 41,924; output 484; reasoning output 243; cached input 0
- wall-clock: 395.006 seconds
- raw evidence: `experiments/n1_triangular_sum_smoke/artifacts/`
- result: PASS

This smoke deliberately tests N1 mechanics, not proof-search performance: its route restates the exact frozen target from one already verifier-accepted Baseline A theorem Fact.

## Frozen Baseline Integrity

- baselines/danus HEAD: `6d92e8d415933ca2ef52fd1a4da73fdfcd418f1c`
- baselines/danus branch: `codex`
- baselines/danus working tree: clean

## Review Gate

- Standards/minimality axis after the failure-semantics fix: PASS, 0 findings.
- N1 specification axis after the failure-semantics fix: PASS, 0 findings.
- Parallel FactGraph/verifier/worker infrastructure introduced: NO.
- Runtime dependency on frozen baseline clone: NO.

## Scope Audit

- Coarse Proof Scaffold: NOT IMPLEMENTED
- Cheap Probe: NOT IMPLEMENTED
- WORKER_READY / TOO_WIDE classifier: NOT IMPLEMENTED
- Cut / Cut-Set / Adaptive refinement: NOT IMPLEMENTED
- GraphPatch / structural auditor: NOT IMPLEMENTED
- Failure classification / obstruction diagnosis / Progress Contract: NOT IMPLEMENTED
- Local Graph Surgery / critical-gap scheduling: NOT IMPLEMENTED
- Semantic obligation dedup / retrieval or memory changes: NOT IMPLEMENTED
- Lean / Cross-DAG / mapping / fidelity: NOT IMPLEMENTED

## Verdict

`N1_VALIDATED`
