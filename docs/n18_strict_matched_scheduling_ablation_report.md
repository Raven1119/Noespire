# N1.8 Strictly Matched Worker-Scheduling Ablation

## Causal Fix from N1.7

- previous confound: N1.7 Arm A combined parallel launch with a heterogeneous `high:3,xhigh:4` roster and heterogeneous assignments, while B/C used identical `high` direct-proof workers.
- N1.8 control: every arm configured the same seven `high` workers with byte-identical assignments, model, effort, verifier, tools, blind wrapper, timeout, problem, and fresh initial state. Only launch scheduling differed.

## Frozen Conditions

- DANUS: `6d92e8d415933ca2ef52fd1a4da73fdfcd418f1c`
- model: `gpt-5.6-sol`
- role: `high`
- reasoning effort: `high`
- worker prompt hash: `7f66ed3b235377a467c5724b882c7a3b7d01008864fe8ddcece2ef126c2a5284`
- blind wrapper hash: `fa3e48e3603a747e744367e1cdfaecbc81c30fe015290119c2e59ec6147de96a`
- problems: Vieta jumping square, Hall marriage, primitive Pythagorean triples, Ceva concurrency, monotone subsequence, and Eulerian circuit; all six problem and reference hashes were frozen before the first proof worker.
- arm order: `P1 A-B-C`, `P2 B-C-A`, `P3 C-A-B`, `P4 A-C-B`, `P5 B-A-C`, `P6 C-B-A`.
- arms: A = parallel-7 and wait for all; B = single-1; C = sequential up to 7 with early stop after exact-target acceptance.

## Results

All 18 result-bearing executions solved their theorem. Three Arm A executions failed the post-run blind-integrity audit and therefore are not valid causal observations. Times are seconds.

| Problem | Arm | Solved | Workers | Accepts | Rejects | Facts | Closure | Tokens | First-target time | Total time | Blind integrity |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |
| Vieta jumping square | A | yes | 7 | 7 | 0 | 7 | 1 | 651,335 | 298.059 | 385.670 | FAIL |
| Vieta jumping square | B | yes | 1 | 1 | 0 | 1 | 1 | 98,669 | 322.756 | 343.714 | PASS |
| Vieta jumping square | C | yes | 1 | 1 | 0 | 1 | 1 | 158,625 | 382.987 | 430.756 | PASS |
| Hall marriage | A | yes | 7 | 7 | 0 | 7 | 1 | 704,215 | 313.082 | 465.226 | FAIL |
| Hall marriage | B | yes | 1 | 1 | 0 | 1 | 1 | 58,738 | 286.704 | 321.070 | PASS |
| Hall marriage | C | yes | 1 | 1 | 0 | 1 | 1 | 72,949 | 258.946 | 297.749 | PASS |
| Primitive Pythagorean triples | A | yes | 7 | 7 | 0 | 7 | 1 | 757,405 | 246.391 | 433.292 | FAIL |
| Primitive Pythagorean triples | B | yes | 1 | 1 | 0 | 1 | 1 | 81,803 | 242.592 | 275.971 | PASS |
| Primitive Pythagorean triples | C | yes | 1 | 1 | 0 | 1 | 1 | 85,073 | 300.349 | 328.225 | PASS |
| Ceva concurrency | A | yes | 7 | 8 | 0 | 8 | 1 | 637,987 | 281.497 | 483.211 | PASS |
| Ceva concurrency | B | yes | 1 | 1 | 0 | 1 | 1 | 70,706 | 300.466 | 317.817 | PASS |
| Ceva concurrency | C | yes | 1 | 1 | 0 | 1 | 1 | 96,736 | 333.759 | 372.223 | PASS |
| Monotone subsequence | A | yes | 7 | 7 | 0 | 7 | 1 | 580,290 | 215.396 | 332.312 | PASS |
| Monotone subsequence | B | yes | 1 | 1 | 0 | 1 | 1 | 77,687 | 231.326 | 268.170 | PASS |
| Monotone subsequence | C | yes | 1 | 1 | 0 | 1 | 1 | 86,015 | 259.724 | 304.063 | PASS |
| Eulerian circuit | A | yes | 7 | 7 | 0 | 7 | 1 | 688,139 | 301.749 | 397.315 | PASS |
| Eulerian circuit | B | yes | 1 | 1 | 0 | 1 | 1 | 82,926 | 300.750 | 320.207 | PASS |
| Eulerian circuit | C | yes | 1 | 1 | 0 | 1 | 1 | 88,034 | 350.663 | 366.721 | PASS |

## Aggregate

These are descriptive aggregates over all 18 result-bearing executions. Because three A executions failed blind integrity, the A/B/C aggregate is not promoted as a valid causal comparison.

| Metric | Parallel-7 | Single-1 | Sequential-7 |
| --- | ---: | ---: | ---: |
| Result-bearing runs | 6 | 6 | 6 |
| Blind-integrity PASS | 3 | 6 | 6 |
| Solved | 6/6 | 6/6 | 6/6 |
| Workers launched | 42 | 6 | 6 |
| Verifier calls | 43 | 6 | 6 |
| Accepts / rejects | 43 / 0 | 6 / 0 | 6 / 0 |
| Verified facts | 43 | 6 | 6 |
| Supporting closure size | 6 | 6 | 6 |
| Facts outside closure | 37 | 0 | 0 |
| Verified-search waste | 86.05% | 0% | 0% |
| Worker tokens | 2,626,242 | 286,297 | 359,601 |
| Verifier tokens | 1,393,129 | 184,232 | 227,831 |
| Total tokens | 4,019,371 | 470,529 | 587,432 |
| Mean first-target time | 276.029 | 280.766 | 314.405 |
| Mean terminal time | 416.171 | 307.825 | 349.956 |

Nominally, B reduced launched workers by 85.71% and total tokens by 88.29% relative to A; C reduced workers by 85.71% and tokens by 85.38%. These reductions are not a causal conclusion because the integrity gate failed.

## First-Worker Failures

- count: `0/6` in Arm C.
- problems: none.
- later recoveries: none; every C run stopped after worker 1 passed.
- implication: the observed executions are consistent with single-worker sufficiency, but sequential recovery was not tested by this set.

## Matched Causal Comparison

- solve rate: nominally `6/6` in A, B, and C.
- token cost: nominally 4,019,371 / 470,529 / 587,432 for A/B/C.
- worker cost: nominally 42 / 6 / 6 workers for A/B/C.
- waste: nominally 86.05% / 0% / 0% outside-closure Fact ratio for A/B/C.
- latency: A had the lowest mean first-target time, while B had the lowest mean terminal time.
- causal status: invalid. Only 15/18 executions passed the frozen blind audit, with all three failures in Arm A.

## Interpretation

- parallel robustness: no extra solve was observed; the comparison cannot establish its absence because three A cells are integrity-invalid.
- single-worker sufficiency: all six B runs and every C worker 1 solved, but the strict `SINGLE_WORKER_SUFFICIENT_ON_SET` verdict is withheld because the matched integrity gate failed.
- sequential recovery: untested; no C worker 1 failed.
- integrity failure: Hall-A and primitive-Pythagorean-A recorded completed-search event types even though their traces say the tool was unavailable and no external result was used. Vieta-A additionally attempted an exact-problem Bohrium `curl`; DNS resolution failed and no result was retrieved, but the frozen audit treats the outbound call itself as a violation.
- system-invalid evidence: the three blind-failed result directories carry deterministic `SYSTEM_INVALID_RUN` sidecars and are not eligible for replacement. Separately, the first P1-A attempt was invalidated by the completion-collector roster bug, and the first P6-A attempt was invalidated by a Codex usage-limit error; each execution-invalid pair was replaced once. All five invalidity records remain preserved, while the two attempts without results are excluded from the table.

## Verdict

`INCONCLUSIVE`

The frozen rule reserves this verdict for integrity failure, sample invalidity, runtime mismatch, or insufficient valid arms. This experiment has three blind-integrity failures and therefore does not satisfy the 18-valid-run stop condition.

Repository state: **BLOCKED** for promotion of an N1.8 scheduling conclusion.

## Integrity

- prompt equality: PASS; all runtime `TASK.md` hashes equal the frozen assignment hash.
- model equality: PASS; every arm used `gpt-5.6-sol`.
- effort equality: PASS; every worker used `high`.
- initial-state equality: PASS within each problem across A/B/C.
- counterbalanced order: PASS for the 18 result-bearing executions.
- raw-metric derivation: PASS; solved state, worker/verifier tokens, attempts, verifier outcomes, Facts, closure, targets, and first-target times were recomputed from preserved artifacts and matched every `result.json`.
- blind integrity: FAIL; 15 PASS, 3 FAIL, 0 suspicious reference overlaps.
- problem freeze: PASS; six problem and reference hashes match the pre-run manifest.
- DANUS modified: no; frozen upstream remains clean at `6d92e8d415933ca2ef52fd1a4da73fdfcd418f1c`.
- Noespire src modified: no.

## Next Step

Strengthen the blind wrapper so shell-level outbound network attempts are impossible and auditable before execution, then freeze a new OOD set for a fresh matched scheduling ablation. Do not reuse or rerun these six problems for verdict selection.
