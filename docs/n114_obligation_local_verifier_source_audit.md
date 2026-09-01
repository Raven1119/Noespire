# N1.14 Obligation-Local Verifier Source Audit

## Scope and frozen inputs

- Product branch: `noespire-nl-proof-v2`, using the validated N1.13 working tree as the implementation baseline.
- Frozen DANUS baseline: `6d92e8d415933ca2ef52fd1a4da73fdfcd418f1c`; it remains an unchanged reference repository.
- Frozen regression evidence: the N1.13 divisibility run rejected a correct parity lemma only because it did not prove the complete root theorem. N1.14 must preserve that evidence unchanged and test the corrected verifier in a separate experiment directory.
- This slice changes verifier scope only. It adds no worker behavior, scaffold search, retry, repair, adaptive cut, graph patch, Architect feedback, or new model/provider path.

## Why the verifier confused an intermediate obligation with the root theorem

`ResearchVerifier.verify(problem, candidate, predecessors)` already receives all data required for an obligation-local decision, but its prompt labels the full theorem only as `Problem` and never states the role of that field. In N1.13, the verifier therefore treated the root theorem as the required conclusion and rejected a candidate whose statement and proof correctly established the current parity obligation.

The ambiguity is confined to the verifier prompt. The worker prompt already distinguishes `Problem` from `Current subgoal`, while the verifier receives the same candidate statement under `Candidate` but lacks the corresponding scope instruction.

## Existing deterministic guards

Before a scaffold candidate reaches `ResearchVerifier`, `execute_obligation()` mechanically enforces:

- normalized candidate statement equality with the current obligation goal;
- exact normalized predecessor-ID equality with the obligation's materialized premises;
- existence of every predecessor as an accepted Fact for the same problem;
- reopening after a deterministic mismatch or verifier rejection.

The `execute_obligation_with_evidence()` wrapper in `attempt.py` additionally records execution errors and restores a still-RUNNING obligation to OPEN. Bare `execute_obligation()` does not own that exception-recovery behavior.

`submit_candidate()` then supplies the verifier only the declared accepted predecessor Facts and creates a new Fact only after `VerificationResult.accepted` is true. `FactGraph.add_fact()` remains the truth-store boundary, and scaffold dependencies become predecessor IDs only after their nodes have resolved to accepted Facts.

These guards prevent statement substitution, undeclared or future predecessors, and verifier bypass. They do not decide mathematical truth; that remains the fresh verifier's responsibility.

## Minimal change decision

| Area | Decision | N1.14 use |
| --- | --- | --- |
| `ResearchVerifier.verify(problem, candidate, predecessors)` | ADAPT PROMPT ONLY | State explicitly that the full Problem is background context, while the exact candidate statement is the claim being verified using only its proof and supplied accepted predecessors. Preserve strict rejection criteria. |
| `ResearchVerifier` API | KEEP EXISTING | `candidate.statement` already identifies the current claim. Adding `current_goal` would duplicate data and create a second source of truth. |
| `submit_candidate()` and `FactGraph` admission | KEEP EXISTING | A verifier PASS remains mandatory before any candidate becomes an accepted Fact. |
| `execute_obligation()` | KEEP EXISTING | Existing statement and predecessor equality checks define the deterministic obligation boundary. |
| `solve_problem_once()` | KEEP EXISTING | The direct-root candidate statement equals the full Problem, so obligation-local verification preserves root-only behavior. |
| `solve_scaffold()` and scheduler | KEEP EXISTING | Ready-node selection, dependency materialization, stop-on-failure behavior, and supporting closure do not change. |
| `ResearchWorker` and `StaticScaffoldArchitect` | KEEP EXISTING | N1.14 changes neither proposal generation nor decomposition. |
| Contract tests and isolated verifier ablation | NEW | Tests freeze the prompt/adapter contract; four fresh blind verifier packets measure the mathematical scope correction without a worker or Architect. |

## Verification truth boundary

The boundary remains:

```text
candidate
-> deterministic statement/predecessor guards
-> fresh obligation-local ResearchVerifier
-> PASS
-> FactGraph
```

The full Problem may help interpret notation and assumptions shared by the current proof task, but it is not an additional conclusion the candidate must prove. The verifier must judge exactly the candidate statement and reject a false statement, an insufficient or circular proof, missing assumptions, or unsupported/misused predecessors. Multiple predecessors need to be collectively sufficient; no predecessor is required to establish the candidate alone.

## Root-problem semantics

No special root mode is needed. For `solve_problem_once()`, the root obligation goal and candidate statement are the complete theorem, so the same obligation-local rule asks the verifier to prove the full theorem. For a scaffold node, the candidate statement is the smaller current obligation, so the same rule asks only for that claim. One interface therefore covers both cases without a mode flag or duplicated verifier.

## Expected unaffected paths

- `ResearchWorker.propose()` continues to solve the exact supplied subgoal once.
- `StaticScaffoldArchitect` still emits one frozen proposal and never receives verifier feedback.
- N1.12 scheduling still selects one ready node at a time and stops at the first blocked result.
- N1.11 attempt persistence still records candidate/verifier artifacts and PASS/FAIL/ERROR.
- Supporting closure still derives solely from accepted Fact predecessor edges.

The appropriate engineering seam is therefore a prompt-only adaptation plus tests and frozen experiment evidence.
