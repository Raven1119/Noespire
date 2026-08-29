# N1.7 Worker Scheduling Matched Ablation

## Source Audit

- current worker fan-out: `danus new` defaults to `high:3,xhigh:4`; the historical N1.6 harness assigned all seven workers, called `danus start <project>`, and waited until all seven status files were terminal before inspecting accepted target Facts.
- configuration seam: the existing `danus new --roles` roster control supports `high:1` and `high:7`; `danus start <project>/<worker>` launches one selected worker without changing DANUS.
- early-stop seam: DANUS has no accepted-target hook that automatically stops a roster. The experiment waits for one worker's terminal status, reads the synchronous verifier trace, and launches the next worker only when no exact accepted target exists. No already-running worker needs cancellation.
- experiment implementation: `experiments/danus_n17_worker_scheduling/scheduler.py` and `run_once.py` are an external experiment-only harness. Arm B uses `high:1`. Arm C creates `high:7`, assigns the byte-identical direct-proof task to all seven, and starts them strictly one at a time. No code entered `src/` or frozen DANUS.

The detailed seam evidence is in `docs/n17_worker_scheduling_source_audit.md`. Arm B and C are strictly matched to one another. Archived Arm A used the N1.6 `high:3,xhigh:4` heterogeneous roster and seven frozen task assignments; B/C match its first `high` direct worker but intentionally do not reproduce diversified retries, which this task forbids. The A comparison therefore evaluates the historical parallel policy package against demand-driven identical direct attempts, not the isolated effect of any particular extra role.

## Frozen Conditions

- problems: the four byte-identical N1.6 problems: `cubic-form-image` (`51109d…632`), `period-five-recurrence` (`2a717f…beb`), `weighted-binomial-paths` (`6baac1…80a`), and `reflection-fixed-vector` (`091668…81c`).
- model: `gpt-5.6-sol`; every B/C proof worker used role/effort `high`, one round, and the exact N1.6 `high` direct-proof assignment.
- verifier: unchanged DANUS verifier, `gpt-5.6-sol` / `xhigh`, 900-second Codex timeout, fresh stateless service per run.
- blind policy: unchanged N1.6 wrapper SHA-256 `fa3e48…e96a` and canonical capability gate `PASS`; external retrieval, reference/source reads, web/browser/search, apps/plugins, and subagents were unavailable, while local DANUS Fact/Memory remained available.
- DANUS commit: `6d92e8d415933ca2ef52fd1a4da73fdfcd418f1c`.

The pre-run freeze is commit `a7579fb` (`experiment: freeze N1.7 worker scheduling ablation`). Before the first valid run, excluded attempt `cubic-form-image_20260829T150856Z` exposed an ambient `VERIFIER_RESULTS_DIR` omission. Commit `3e4acc0` pins the verifier to its already-frozen `runtime/verify-runs` write scope; it changes no scheduling, task, model, verifier, or mathematical semantics. Full evidence and the red/green regression are recorded in `protocol/verifier_results_boundary_correction.md`.

## Results

| Problem | Arm | Solved | Workers | Accepts | Rejects | Facts | Closure | Outside | Tokens | Time |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `cubic-form-image` | A Parallel-7 | yes | 7 | 7 | 0 | 7 | 1 | 6 | 787,120 | 572.088 s |
| `cubic-form-image` | B Single | yes | 1 | 1 | 0 | 1 | 1 | 0 | 139,073 | 411.019 s |
| `cubic-form-image` | C Sequential | yes | 1 | 1 | 0 | 1 | 1 | 0 | 93,937 | 361.343 s |
| `period-five-recurrence` | A Parallel-7 | yes | 7 | 7 | 0 | 7 | 1 | 6 | 638,082 | 411.177 s |
| `period-five-recurrence` | B Single | yes | 1 | 2 | 0 | 2 | 1 | 1 | 138,652 | 546.475 s |
| `period-five-recurrence` | C Sequential | yes | 1 | 1 | 0 | 1 | 1 | 0 | 113,733 | 315.710 s |
| `weighted-binomial-paths` | A Parallel-7 | yes | 7 | 7 | 0 | 7 | 1 | 6 | 688,673 | 344.963 s |
| `weighted-binomial-paths` | B Single | yes | 1 | 1 | 0 | 1 | 1 | 0 | 84,442 | 310.880 s |
| `weighted-binomial-paths` | C Sequential | yes | 1 | 1 | 0 | 1 | 1 | 0 | 66,452 | 225.663 s |
| `reflection-fixed-vector` | A Parallel-7 | yes | 7 | 7 | 0 | 7 | 1 | 6 | 617,679 | 324.596 s |
| `reflection-fixed-vector` | B Single | yes | 1 | 1 | 0 | 1 | 1 | 0 | 80,934 | 285.683 s |
| `reflection-fixed-vector` | C Sequential | yes | 1 | 1 | 0 | 1 | 1 | 0 | 90,321 | 300.729 s |

All eight new valid runs are `BLIND_INTEGRITY_PASS`. Arm C's first-success index was 1 for every problem, `stopped_after_success` was true in every run, and each run left six workers unused.

## Aggregate

| Metric | A Parallel-7 | B Single | C Sequential |
| --- | ---: | ---: | ---: |
| valid runs | 4 | 4 | 4 |
| solved / solve rate | 4 / 100% | 4 / 100% | 4 / 100% |
| workers launched | 28 | 4 | 4 |
| mean workers/problem | 7.0 | 1.0 | 1.0 |
| worker attempts | 28 | 4 | 4 |
| verifier accepts / rejects | 28 / 0 | 5 / 0 | 4 / 0 |
| verified Facts | 28 | 5 | 4 |
| supporting closure | 4 | 4 | 4 |
| Facts outside closure | 24 | 1 | 0 |
| verified-search-waste | 85.714% | 20.000% | 0.000% |
| total tokens | 2,731,554 | 443,101 | 364,443 |
| mean tokens/problem | 682,888.50 | 110,775.25 | 91,110.75 |
| total wall clock | 1,652.824 s | 1,554.057 s | 1,203.444 s |
| Arm-C unused worker budget | — | — | 24/28 |

Exact inputs and derived values are in `analysis/aggregate.json`. Tokens are observed from complete worker and verifier logs; none were estimated.

## Arm B

Arm B retained the full 4/4 solve rate with exactly one launched worker and one worker attempt per problem. It used 443,101 tokens, 83.778% fewer than Arm A, while eliminating 24 of 28 worker launches relative to A.

Three problems produced exactly one accepted target Fact. `period-five-recurrence` produced two independently accepted exact-target Facts inside the same single worker session; one entered the final closure and one remained outside. Thus fixed seven-worker fan-out is the dominant observed source of verified-search waste, but it is not the only possible duplication source: one autonomous worker can resubmit an already-solved target within its session.

## Arm C

Arm C also solved 4/4. Every problem succeeded at worker index 1, stopped immediately after that completed attempt, and left six of seven worker slots unused. It launched 4 workers instead of Arm A's 28, used 364,443 tokens, and produced no verified Fact outside the final closures.

No C run exercised worker 2 or later. The experiment therefore validates the early-stop mechanism and the sufficiency of single-worker-first on this set; it does not supply positive evidence that sequential retry recovers failures.

## Matched Comparison

- solve-rate change: B vs A `0 pp`; C vs A `0 pp`.
- token reduction: B vs A `83.778%`; C vs A `86.658%`.
- worker reduction: B vs A `85.714%`; C vs A `85.714%`.
- waste reduction: B vs A `65.714 percentage points` (`76.667%` relative); C vs A `85.714 percentage points` (`100%` relative).
- wall-clock change: B vs A `-5.976%` (`-98.767 s`); C vs A `-27.189%` (`-449.380 s`).

B and C realized the same scheduling path—one direct worker per problem. Their token and wall-clock difference is independent stochastic run variation, not evidence that an unexercised sequential escalation policy is better than fixed single-worker execution.

## Interpretation

Q1: **Yes.** Arm B retained 4/4. On this diagnostic distribution, the six additional Arm-A workers contributed no observable solve-rate benefit.

Q2: **Yes.** Arm C retained Arm A's 4/4 while launching 4 rather than 28 workers. This directly supports progressive or conditional compute allocation and confirms that the external early-stop seam works.

Q3: **No demonstrated incremental value over Arm B.** Arm B had no failed problem, and Arm C never used a later worker. Since B = C = 4/4, the supported statement is only: **single-worker-first policy is sufficient on this set**. Sequential escalation remains untested as a recovery mechanism.

The conclusion is distribution-specific. The archived A roster's heterogeneous extra roles also mean this result supports removal of the historical parallel policy package; it does not rank worker specialties or reasoning efforts, which were intentionally outside scope.

## Verdict

**DEMAND_DRIVEN_EXECUTION_SUPPORTED**

B and C each retained 4/4 while reducing worker launches by 85.714%, tokens by more than 83%, and verified-search waste by at least 76.667% relative. The evidence supports a default direct attempt with additional compute allocated only after failure. It does not separately support sequential escalation, diversification, or any N2/Cut-Set mechanism.

## Integrity

- DANUS modified: **NO**. Nested HEAD is `6d92e8d415933ca2ef52fd1a4da73fdfcd418f1c` and the working tree is clean.
- prompts modified: **NO** DANUS worker contract, verifier prompt, or source prompt changed. Every B/C assignment reuses the exact N1.6 `high` direct-worker task; no failure text or diversified retry task was added.
- problems modified: **NO**. All eight result hashes equal the pre-run manifest.
- blind integrity: **PASS, 8/8**. Both audit summaries report 4 pass / 0 fail, zero external calls, zero completed search events, zero unexpected URLs, and zero suspicious reference overlaps.
- Noespire src modified: **NO**. `git diff noespire-n1-proof-obligations -- src/` is empty.
- invalid environment attempt: one preserved `SYSTEM_INVALID_RUN`, excluded from all metrics. Its five misdirected launcher logs were byte-preserved before the generated nested source directory was removed; the correction occurred before the first valid run and changed no scheduling semantics.
- forbidden work: no N2, Cut-Set, Proof Scaffold refinement, failure-driven decomposition, product scheduler, or DANUS algorithm change was implemented.

## Next Step

Freeze a harder out-of-sample diagnostic set that produces genuine first-worker failures, then test whether identical-worker sequential escalation recovers them more cheaply than Parallel-7.
