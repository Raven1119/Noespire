# N1.14 Obligation-Local Verifier Report

## Verdict

`OBLIGATION_LOCAL_VERIFIER_VALIDATED`

The verifier now judges exactly the supplied candidate statement from its proof and declared accepted predecessors. The complete Problem remains available as background context but is no longer treated as an additional conclusion for intermediate obligations.

## Scope

N1.14 makes one product-code semantic change: the `ResearchVerifier` prompt contract. Its public API remains:

```python
verify(problem, candidate, predecessors)
```

No `current_goal` field or mode flag was added because `candidate.statement` already names the claim under review. `ResearchWorker`, `execute_obligation()`, `submit_candidate()`, `FactGraph`, `solve_problem_once()`, the scaffold scheduler, and `StaticScaffoldArchitect` were not changed for N1.14.

The engineering skills constrained the result as follows:

- codebase-design located the existing deep seam at `ResearchVerifier.verify()` and retained the deterministic guards around it;
- TDD first produced three expected prompt-contract failures, then covered intermediate, root, mathematical-error, insufficient-proof, missing-assumption, and predecessor-misuse behavior;
- Ponytail kept the implementation to a prompt-only adaptation instead of adding duplicate obligation state or another verifier abstraction;
- code-review was used as the final Standards/Spec gate.

## Source Audit Conclusion

The N1.13 false negative came from prompt ambiguity, not missing runtime state. The old prompt presented the full theorem as `Problem` but did not tell the verifier that a candidate could be an intermediate lemma.

The existing truth boundary was already correct:

```text
Candidate
-> execute_obligation() statement/predecessor equality guards
-> submit_candidate()
-> fresh ResearchVerifier
-> PASS
-> FactGraph
```

`execute_obligation()` continues to require exact normalized statement equality and exact predecessor-ID equality. It loads only accepted same-problem Facts, and a verifier rejection reopens the obligation without admitting a Fact. The full source decision record is in `docs/n114_obligation_local_verifier_source_audit.md`.

## Implementation

The new verifier contract states that:

- the complete Problem is background context only;
- the candidate may be an intermediate lemma;
- the proof must establish exactly the candidate statement from the supplied accepted predecessors;
- the candidate need not prove the complete Problem unless its own statement is the complete Problem;
- supplied predecessors must be collectively sufficient, and every declared predecessor must be provided and genuinely used;
- false statements, insufficient proofs, missing assumptions, circular arguments, unsupported inferences, unknown predecessor IDs, and insufficient or unused predecessors remain rejection conditions.

Root semantics require no branch: in `solve_problem_once()`, the candidate statement is the full theorem, so the same local rule still verifies the entire target.

## Deterministic Tests

| Requirement | Evidence | Result |
| --- | --- | --- |
| A. Correct intermediate | Contract identifies `candidate.statement`, not the different global Problem, as the verification target | PASS |
| B. Root theorem | Structured ACCEPT and REJECT verdicts are preserved when candidate equals Problem | PASS, 2 subtests |
| C. False intermediate | Mathematical correctness remains an explicit condition and REJECT is preserved | PASS |
| D. Insufficient proof | Prompt requires the proof to establish exactly the candidate statement | PASS |
| E. Missing assumption | Missing assumptions remain an explicit rejection condition | PASS |
| F. Predecessor misuse | Supplied predecessors must be collectively sufficient and each must be genuinely used; unsupported inference is rejected | PASS |
| G. Direct N1.11 regression | Existing `tests/test_problem.py` and full product suite | PASS |
| H. N1.12/N1.13 regression | Existing scaffold, Architect, obligation, and experiment tests | PASS |

TDD sequence:

1. Before the implementation change: `3 failed, 4 passed, 2 subtests passed` in `tests/test_verifier_contract.py`; all failures were missing scope/strictness clauses.
2. After the prompt-only change: `7 passed, 2 subtests passed`.
3. Final N1.14 focused suite: `11 passed, 2 subtests passed`.
4. Final product suite: `241 passed, 4 skipped, 1 warning, 42 subtests passed`.

## Frozen Real Verifier Ablation

Authoritative post-review protocol: `n114-obligation-local-verifier-v2`.

- Model: `gpt-5.6-sol`
- Reasoning effort: `medium`
- Codex CLI: `0.151.0-alpha.7.2`
- One fresh ephemeral blind verifier session per packet
- No ResearchWorker or Architect calls
- No retry

| Packet | Control | Old | New | Expected | Input | Output | Reasoning | Wall (s) | Thread |
| --- | --- | --- | --- | --- | ---: | ---: | ---: | ---: | --- |
| P1 | N1.13 correct divisibility-by-2 lemma | REJECT | ACCEPT | ACCEPT | 9,313 | 102 | 21 | 9.135 | `01a05ced-7662-7322-984d-fb1b328b7e9a` |
| P2 | N1.13 accepted factorization lemma | ACCEPT | ACCEPT | ACCEPT | 9,429 | 114 | 42 | 8.500 | `01a05ced-9a0c-7071-8b2b-ac10de168847` |
| N1 | False divisibility-by-4 lemma | not recorded | REJECT | REJECT | 9,277 | 122 | 30 | 9.091 | `01a05ced-bb38-7d91-8239-43c33790338a` |
| N2 | True residue lemma with only one case proved | not recorded | REJECT | REJECT | 9,290 | 75 | 0 | 7.532 | `01a05ced-dec3-7e52-9334-13f6f53de47d` |

Packet false positives: `0`. Packet false negatives: `0`. All four thread IDs are nonempty and distinct. Frozen-source checks parse each cited N1.13 verifier audit and require exact equality for the global Problem, candidate, predecessor Facts, old verdict, and old reason; the persisted attempt and audit verdict must also agree. The E2E scaffold must equal the frozen N1.13 validated scaffold.

## Frozen Scaffold E2E

Only after all four packets passed, the unchanged N1.13 integer-divisibility scaffold was executed with preregistered scripted candidates and the real obligation-local verifier:

```text
divisible_by_2 -> accepted Fact
divisible_by_3 -> accepted Fact
both Facts -> target unlocked -> accepted target Fact
```

Results:

- status: `SOLVED`
- Architect calls: `0`
- scripted worker calls: `3`
- fresh real verifier calls: `3`
- attempt verdicts: `PASS`, `PASS`, `PASS`
- Facts admitted: `3`
- target Fact: `4f6ccd5f5fae457f`
- supporting closure size: `3`
- retry/repair/Adaptive Cut: `0`
- E2E verifier threads: `01a05ced-fc5d-74c1-8151-dcf1dcce6e0e`, `01a05cee-216b-7ef0-a821-32763c356f50`, and `01a05cee-400b-78d0-80a1-38f3f63da9c0`
- all three E2E verifier thread IDs were fresh and distinct from the packet threads

The scripted worker was used deliberately to isolate verifier semantics; this E2E is not a claim about stochastic worker quality.

## Preserved Pre-Review Evidence

The first v1 E2E preflight exposed a deterministic experiment-harness error before any verifier call: the scripted worker indexed candidates by a bare goal while the existing runtime passes a fixed instruction wrapper containing `Goal:`. The failed artifact is preserved at `experiments/n114_obligation_local_verifier/pre_review_e2e_run/result.json` with `verifier_calls = 0` and `facts_admitted = 0`. Its successful harness-only resume is preserved under `pre_review_e2e_resumed_run/`.

Final review then clarified collective predecessor sufficiency, which changed the actual verifier prompt. The entire v1 aggregate, results, protocol, and audits were therefore archived under `pre_review_*` and were not claimed as evidence for the revised code. The v2 protocol ran once from fresh evidence locations with all four packets followed by one direct E2E. This was an engineering review iteration, not an automatic proof/verifier retry policy.

## Aggregate Metrics

- Input tokens: `65,678`
- Output tokens: `672`
- Reasoning tokens: `116`
- Recorded verifier wall time: `59.972 s`
- Real verifier sessions: `7`, all fresh
- False positives: `0`
- False negatives: `0`

Raw prompts, structured outputs, commands, usage, and thread IDs are retained under `experiments/n114_obligation_local_verifier/codex_audits/`. Aggregate results are in `aggregate.json`; packet and E2E linkage is in `results.json`.

## Validation Commands

```text
python -m py_compile experiments/n114_obligation_local_verifier/run.py
python -m pytest tests/test_verifier_contract.py -q
python -m pytest -q tests/test_n114_experiment.py tests/test_verifier_contract.py
python -m pytest -q tests
python experiments/n114_obligation_local_verifier/run.py
```

The archived v1 harness-only recovery used `--resume-e2e-after-harness-error`; the authoritative v2 run did not use that option.

## Review Gate

The parallel Standards/Spec review found and resolved four material audit points before the final v2 run:

- the root regression now asserts the conditional full-Problem clause and exact root statement placement;
- predecessor wording now requires collective sufficiency rather than implying that each Fact must prove the claim alone;
- P1/P2 provenance now authenticates the complete cited verifier packet against both the frozen attempt and audit;
- observed target unlock evidence is derived from the actual advance sequence instead of being unconditional.

The source-audit attribution for exception recovery and the v1/v2 evidence/version distinction were also corrected. Final Spec review: PASS. Final Standards review: PASS.

A bare repository-root `pytest -q` is not the Noespire product-suite boundary: it also collects the independent nested DANUS repository and archived experiment trees. On Windows that collection stops on DANUS optional `mcp`/`fcntl` dependencies and duplicate historical test-module names. The canonical product command `pytest -q tests` passed.

## Scope Audit

- FactGraph admission and supporting-closure semantics: unchanged.
- Statement and predecessor equality guards: unchanged.
- Worker prompt: unchanged.
- Architect/scaffold implementation: unchanged.
- Direct root orchestration: unchanged.
- No retry, repair, GraphPatch, Adaptive Cut, Lean, mapping, or new provider abstraction was added.
- Frozen N1.13 evidence and frozen DANUS repository `6d92e8d415933ca2ef52fd1a4da73fdfcd418f1c` remain unchanged.

## Acceptance

All N1.14 acceptance checks in `aggregate.json` are true.

`OBLIGATION_LOCAL_VERIFIER_VALIDATED`
