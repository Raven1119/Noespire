# N1.9b Fresh Strictly Matched Scheduling Ablation

## Frozen Conditions

- DANUS: `6d92e8d415933ca2ef52fd1a4da73fdfcd418f1c` (`codex`)
- blind boundary: `6b9d662ec0c33c6e4b19ae4e841e17603f59b2d5` / `noespire-n19a-blind-boundary`
- model: `gpt-5.6-sol`
- role: `high`
- effort: `high`
- prompt hash: `7f66ed3b235377a467c5724b882c7a3b7d01008864fe8ddcece2ef126c2a5284`
- blind-wrapper hash: `852d8c7bdb2157c77fd993ec32fc01416724978fa2fb2d488fc5015b478910cd`
- problems: `ramsey-r33`, `chinese-remainder`, `sperner-antichain`, `vandermonde-determinant`, `p-group-center`, `bipartite-odd-cycle`
- arm order: `ABC`, `BCA`, `CAB`, `ACB`, `BAC`, `CBA`, in the problem order above
- only experimental variable: worker scheduling (`Parallel-7`, `Single-1`, `Sequential-7`)

The six statements, statement hashes, private sources, reference-proof hashes, worker contract, timeouts, verifier, metrics, verdict rules, and counterbalanced order were frozen before the first mathematical worker in commit `bbe605b439df7d06cb88594b3fd1be680a5b5e22`.

## Integrity

- valid cells: 18/18
- blind PASS: 18/18
- blind FAIL: 0
- successful external access: 0
- state isolation: PASS; the aggregate validator found matched initial-state hashes within every problem and a fresh project for every cell
- prompt equality: PASS; every result records the same assignment hash, model, role, effort, tool policy, verifier, and frozen wrapper hash
- execution order: PASS; the 18 valid results exactly match the frozen counterbalanced order
- problem/reference integrity: PASS; all frozen hashes match
- preserved `SYSTEM_INVALID_RUN` evidence: 3 (initial Ramsey/A verifier-output permission failure, interrupted p-group/A, interrupted bipartite/C)
- replacement rule: PASS; each affected cell used at most its one permitted fresh replacement, and no mathematical failure was rerun

## Results

Times are seconds. `Facts` is the verifier-accepted Fact count and `Closure` is the selected target's supporting-closure size.

| Problem | Arm | Solved | Workers | Rejects | Facts | Closure | Tokens | First-target | Total |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| ramsey-r33 | Parallel-7 | yes | 7 | 0 | 7 | 1 | 866,687 | 253.750 | 386.015 |
| ramsey-r33 | Single-1 | yes | 1 | 0 | 1 | 1 | 106,460 | 218.720 | 247.807 |
| ramsey-r33 | Sequential-7 | yes | 1 | 0 | 1 | 1 | 113,147 | 221.317 | 233.751 |
| chinese-remainder | Parallel-7 | yes | 7 | 0 | 7 | 1 | 667,974 | 271.897 | 358.491 |
| chinese-remainder | Single-1 | yes | 1 | 0 | 1 | 1 | 89,257 | 306.843 | 338.151 |
| chinese-remainder | Sequential-7 | yes | 1 | 0 | 1 | 1 | 117,394 | 337.750 | 379.062 |
| sperner-antichain | Parallel-7 | yes | 7 | 0 | 7 | 1 | 736,318 | 265.758 | 335.729 |
| sperner-antichain | Single-1 | yes | 1 | 0 | 1 | 1 | 131,033 | 320.725 | 347.030 |
| sperner-antichain | Sequential-7 | yes | 1 | 0 | 1 | 1 | 89,030 | 311.524 | 330.125 |
| vandermonde-determinant | Parallel-7 | yes | 7 | 0 | 7 | 1 | 734,936 | 242.363 | 352.133 |
| vandermonde-determinant | Single-1 | yes | 1 | 0 | 1 | 1 | 66,879 | 281.806 | 303.627 |
| vandermonde-determinant | Sequential-7 | yes | 1 | 0 | 1 | 1 | 129,610 | 250.727 | 287.281 |
| p-group-center | Parallel-7 | yes | 7 | 0 | 7 | 1 | 799,390 | 357.503 | 459.291 |
| p-group-center | Single-1 | yes | 1 | 0 | 1 | 1 | 127,037 | 274.772 | 286.080 |
| p-group-center | Sequential-7 | yes | 1 | 0 | 2 | 1 | 195,640 | 258.609 | 492.746 |
| bipartite-odd-cycle | Parallel-7 | yes | 7 | 0 | 7 | 1 | 774,199 | 336.096 | 472.555 |
| bipartite-odd-cycle | Single-1 | yes | 1 | 0 | 1 | 1 | 132,669 | 312.933 | 345.453 |
| bipartite-odd-cycle | Sequential-7 | yes | 1 | 0 | 2 | 2 | 146,105 | 488.794 | 532.380 |

## Aggregate

| Metric | Parallel-7 | Single-1 | Sequential-7 |
| --- | ---: | ---: | ---: |
| solved | 6/6 | 6/6 | 6/6 |
| workers launched | 42 | 6 | 6 |
| verifier accepts / rejects | 42 / 0 | 6 / 0 | 8 / 0 |
| verified Facts | 42 | 6 | 8 |
| supporting closure | 6 | 6 | 7 |
| Facts outside closure | 36 | 0 | 1 |
| verified search waste | 85.71% | 0.00% | 12.50% |
| total tokens | 4,579,504 | 653,335 | 790,926 |
| mean first-target latency | 287.895 | 285.967 | 311.454 |
| mean terminal latency | 394.036 | 311.358 | 375.891 |
| summed terminal time | 2,364.214 | 1,868.148 | 2,255.345 |

Relative to Parallel-7, Single-1 reduced launched workers by 85.71% and tokens by 85.73%. Sequential-7 reduced launched workers by 85.71% and tokens by 82.73%.

## First-Worker Failures

- count: 0/6 Sequential-7 cells
- later recoveries: 0
- all six Sequential-7 cells stopped after worker 1 succeeded
- `SEQUENTIAL_RECOVERY_SUPPORTED` is therefore not available from this experiment

## Scheduling Effects

- solve rate: all three arms solved all six problems; Parallel-7 supplied no solve-rate advantage
- compute: Parallel-7 used 42 workers and 4,579,504 tokens, versus 6 workers and 653,335 tokens for Single-1
- waste: Parallel-7 produced 36 verified Facts outside the selected closures; Single-1 produced none
- first-target latency: Parallel-7's mean (287.895 s) was effectively tied with Single-1 (285.967 s), and was 23.559 s faster than Sequential-7; this does not compensate for its roughly sevenfold token cost versus Single-1
- terminal latency: Single-1 had the lowest mean terminal latency (311.358 s); Parallel-7 was 394.036 s and Sequential-7 was 375.891 s
- sequential escalation: not exercised because every first worker passed; conditional escalation remains untested rather than disproved

## Verdict

`SINGLE_WORKER_FIRST_SUPPORTED`

## Interpretation

Under identical problem state, assignment, model, reasoning effort, verifier, timeout, and blind tool boundary, one direct worker retained Parallel-7's 6/6 solve rate while using 85.73% fewer tokens and producing no verified search waste. Parallelism did not improve mean first-target latency and did not rescue any problem that Single-1 or Sequential-7 failed.

The evidence supports one direct worker as the default first action for this problem regime. It does not support `SEQUENTIAL_RECOVERY_SUPPORTED`, because no first-worker failure occurred, and it does not support `PARALLEL_REDUNDANCY_SUPPORTED`, because Parallel-7 had neither a solve-rate advantage nor a compensating latency advantage.

## Integrity

- DANUS modified: no; HEAD is `6d92e8d415933ca2ef52fd1a4da73fdfcd418f1c` and its working tree is clean
- Noespire `src/` modified: no; `git diff noespire-n1-proof-obligations -- src/` is empty
- external access: none succeeded across the 18 full blind audits
- problems modified after freeze: no; aggregate validation matched every frozen problem hash
- reference proofs: absent from proof workspaces during execution, restored only after all 18 valid cells, and rechecked against all six frozen hashes
- raw evidence: retained for all 18 valid cells and all three invalid attempts
- Windows cache/ACL hygiene: every N1.9b `project_artifacts` snapshot excludes `.agents`, `.git`, `.lake`, and `__pycache__`; an exact scan of all such snapshots found zero matching directories. The one empty nested `.git` cache outside the independently ignored DANUS repository was removed, and Windows `rg --files` completed with exit 0 and no ACL/helper error.

## Next Step

Adopt one direct worker first as the experimental default. Study conditional escalation only in a separately pre-registered set of naturally occurring first-worker failures; do not implement N2 from this result alone.
