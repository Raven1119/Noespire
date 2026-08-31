# N1.11 End-to-End MVP Source Audit

## Existing product path

1. **Problem input:** no problem- or project-level input object exists under `src/research/`. Problem identity and statement are currently passed as separate strings to execution functions.
2. **Root creation:** no seam currently creates a root `ProofObligation` from a complete theorem statement. Callers construct obligations directly.
3. **Registry persistence:** `ObligationRegistry` stores all obligations in one JSON file. Every add or state transition rewrites a temporary file and atomically replaces the registry file. Reload reconstructs `ProofObligation` values, including `OPEN` and `DISCHARGED` state.
4. **Failure evidence:** `CodexExec` can persist worker and verifier invocation JSON, including prompts, events, results, and errors. Those artifacts do not carry a stable `problem_id`/`obligation_id` association, and deterministic adapters do not emit them. N1.11 therefore needs one thin attempt record that links the problem, root obligation, candidate, verifier verdict, and outcome; it does not need a new persistence abstraction.
5. **Supporting closure:** `FactGraph.supporting_closure(target_fact_id)` already loads the accepted target and returns its predecessor closure in deterministic dependency order. It should be called directly after successful root discharge.

## Existing modules to reuse

- `Fact` / `FactGraph`: accepted truth, same-problem predecessor validation, content addressing, persistence, and supporting closure.
- `ProofObligation` / `ObligationRegistry`: unverified search state, stable persistence, duplicate protection, state transitions, and resolution against an existing Fact.
- `execute_obligation`: the frozen single-worker-first attempt, candidate identity checks, verifier gate, PASS discharge, FAIL-to-OPEN behavior, and idempotent reads of a discharged obligation.
- `ResearchWorker` / `Verifier`: existing worker and fresh-verifier seams.

## Minimal additions

- `ProblemSpec`: the complete natural-language theorem plus optional accepted premise Fact IDs.
- A stable root identity, `root:<problem_id>`, with route `root`.
- `solve_problem_once(...)`: one Python-level interface that creates or reloads the root, delegates at most one attempt to `execute_obligation`, returns either `SOLVED` or `OPEN`, and derives a solved result from the existing supporting closure.
- A JSON attempt artifact for each executed attempt. It records evidence only; it does not classify failure or schedule another attempt.

No parser, planner, scheduler, retry loop, graph representation, or failure-recovery policy is required.
