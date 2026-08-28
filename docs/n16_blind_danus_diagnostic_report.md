# N1.6 Blind DANUS Diagnostic

## Blind Protocol

- restriction mechanism: unchanged DANUS launched every proof-relevant Codex process through `protocol/codex_blind_wrapper.sh`. The wrapper enforces `approval_policy=never`, network off, built-in web/browser/apps/plugins/subagents off, Matlas on a closed loopback endpoint, removal of `search_arxiv_theorems`, and a directory-level read deny over the N1.6 control tree. Only verifier sessions receive the narrow write permission required by DANUS's existing `runtime/verify-runs/` contract.
- worker capabilities: frozen problem text, worker workspace, local DANUS Fact/Memory MCP, local reasoning, and ordinary non-networked workspace tools. External retrieval and the private reference/source manifest were unavailable.
- verifier capabilities: submitted claim/proof and local verification context; external retrieval was unavailable. The verifier could write only its normal verification output.
- strategy/master capabilities: the N1.5-compatible math path invokes no LLM strategy/master session. The same blind policy was nevertheless tested against a strategy/main launch before mathematics.
- leakage probe: canonical evidence is `experiments/danus_n16_blind/protocol/evidence/capability_probe_20260828T162750Z/summary.json`. Worker, verifier, and strategy/main all exited successfully; web and arXiv-MCP call counts were zero, shell `curl` could not resolve the host, protected reads were denied without secret leakage, local DANUS MCP remained available where applicable, and the verifier output canary succeeded.
- result: **PASS**. `automatic_gate` was `PASS` before any valid mathematical run.

The first attempted cubic run is preserved as `SYSTEM_INVALID_RUN` at `runs/cubic-form-image_20260828T153837Z`. Its original verifier policy could reason but could not persist DANUS's required verdict file, causing 16 HTTP 500 responses and zero verification events. It is excluded from all proof-search metrics. After the external sandbox boundary was fixed, the full capability probe passed again before the one valid cubic run.

## Frozen Runtime

- DANUS: branch `codex`, commit `6d92e8d415933ca2ef52fd1a4da73fdfcd418f1c`.
- model: `gpt-5.6-sol`; upstream worker roster `high:3,xhigh:4`, role efforts unchanged, one round, 14,400-second worker timeout.
- verifier: unchanged DANUS verifier prompt and semantics, fresh stateless service per problem, `gpt-5.6-sol`, `xhigh`, 900-second Codex timeout.
- differences from prior baseline: four new frozen problems; the external blind tool policy; an unreadable experiment-control directory; a fresh isolated verifier service/loopback port per run; verifier-only output-directory write permission. Model, worker count, budgets, Fact Graph, memory, supporting closure, target selection, termination, and DANUS source/prompts were unchanged.

The pre-run diagnostic freeze is commit `3c530a7` (`experiment: freeze N1.6 blind diagnostic`). The external verifier-boundary correction and system-invalid evidence are commit `b51e093` (`experiment: fix N1.6 verifier sandbox boundary`).

## Diagnostic Set

| Problem | Structural rationale | Hash |
| --- | --- | --- |
| `cubic-form-image` | Explicit residue constructions plus an independent divisibility-strengthening argument. | `51109dc012315b93ae138daf3ef059cbb7a1ee5c11f2db53ef7962374d17d632` |
| `period-five-recurrence` | A period-five recurrence reduction, cyclic-orbit count, and fixed-point count. | `2a717f69d7178eb6e7aa35f2e8485b0be801b2263235b06ea71c6ed20cdacbeb` |
| `weighted-binomial-paths` | First-hit path decomposition followed by a global double count. | `6baac13f257def1abcde219c457de62f4610600e64ea453f3ba836288eb2c80a` |
| `reflection-fixed-vector` | Rank-one reflection structure combined with fixed-vector/eigenvalue reasoning. | `0916681243c800579f8f38563c3cd5a6cb9a84c68733d008bd77bb09af91981c` |

All four were selected from official MAA problems using mathematical structure only, converted to self-contained non-source-bearing statements, isolated from their private reference proofs, and committed before the first attempt. None appeared in Baseline A or N1.5.

## Blind Integrity

| Problem | Integrity | Evidence |
| --- | --- | --- |
| `cubic-form-image` | `BLIND_INTEGRITY_PASS` | 7 worker + 7 verifier wrapper launches; 7 HTTP 200, 0 HTTP 500; 21 formal trace files; no retrieval/source/private-path markers; strongest reference overlap 16 contiguous normalized tokens and 1.12% generated 12-gram coverage. |
| `period-five-recurrence` | `BLIND_INTEGRITY_PASS` | 7 + 7 launches; 7 HTTP 200, 0 HTTP 500; 22 trace files; no retrieval/source/private-path markers; strongest overlap 9 tokens and 0% 12-gram coverage. |
| `weighted-binomial-paths` | `BLIND_INTEGRITY_PASS` | 7 + 7 launches; 7 HTTP 200, 0 HTTP 500; 21 trace files; no retrieval/source/private-path markers; strongest overlap 15 tokens and 1.34% 12-gram coverage. |
| `reflection-fixed-vector` | `BLIND_INTEGRITY_PASS` | 7 + 7 launches; 7 HTTP 200, 0 HTTP 500; 21 trace files; no retrieval/source/private-path markers; strongest overlap 5 tokens and 0% 12-gram coverage. |

The exact audit, including every Fact-to-reference overlap measurement, is `analysis/leakage_audit.json`. Capability-probe copies were intentionally excluded from formal-math trace scanning because that probe was required to attempt blocked network/private reads. Expected loopback verifier URLs and Codex sandbox-documentation warnings were allowlisted; there were zero other URL occurrences.

## Results

| Problem | Solved | Attempts | Rejects | Facts | Closure | Tokens | Time |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `cubic-form-image` | yes | 7 | 0 | 7 | 1 | 787,120 | 572.088 s |
| `period-five-recurrence` | yes | 7 | 0 | 7 | 1 | 638,082 | 411.177 s |
| `weighted-binomial-paths` | yes | 7 | 0 | 7 | 1 | 688,673 | 344.963 s |
| `reflection-fixed-vector` | yes | 7 | 0 | 7 | 1 | 617,679 | 324.596 s |
| **Total** | **4/4** | **28** | **0** | **28** | **4** | **2,731,554** | **1,652.824 s** |

Every valid frozen problem was attempted exactly once. All 28 worker attempts reached the verifier once, all 28 were accepted, and all 28 accepted Facts stated the complete target. `analysis/attempt_trace.csv` contains exactly one row per attempt with the required eleven columns. Mechanically computed per-problem `failed_proof_cost` is 0 and `verified_search_waste` is 6/7 (0.8571428571).

## Observed Pathologies

- SEARCH_FAILED: 0 of 28 attempts.
- TOO_WIDE: 0 credible regions. No worker failed to bridge a multi-step target; every worker completed it independently.
- MISSING_LEMMA: 0 credible regions. No failed route exposed a concrete missing `H`.
- verifier rejection: 0 of 28 valid submissions.
- STRATEGY_WASTE: 4 regions, one per problem. Seven premise-free workers each solved the same full target although only one accepted Fact could enter the target closure.
- FULL_PROOF_DUPLICATION: 24 redundant accepted full-target Facts outside the final closure (6 per problem). All 28 attempts are exact target repeats within their respective problem; the nonredundant baseline is one per problem.
- UNKNOWN: 0 regions.

High token use or closure exclusion was not used by itself to label `TOO_WIDE`. The positive evidence for `STRATEGY_WASTE` is stronger: all proofs were verifier-accepted complete target proofs, all had no predecessors, and six of seven per problem were redundant for the final closure.

## Fresh Review

| Region | Classification | Confidence | Evidence |
| --- | --- | --- | --- |
| `cubic-form-image` full run | `STRATEGY_WASTE` | HIGH | Seven accepted premise-free full proofs; six outside closure; direct factorization/construction proof available. |
| `period-five-recurrence` full run | `STRATEGY_WASTE` | HIGH | Seven accepted premise-free full proofs; six outside closure; direct periodicity/counting proof available. |
| `weighted-binomial-paths` full run | `STRATEGY_WASTE` | HIGH | Seven accepted premise-free full proofs; six outside closure; one self-contained double count suffices. |
| `reflection-fixed-vector` full run | `STRATEGY_WASTE` | HIGH | Seven accepted premise-free full proofs; six outside closure; one direct inverse construction suffices. |

Each classification came from a separate fresh Codex subagent launched with `fork_turns=none`. Each reviewer received only one generated review packet containing the problem and local attempt/verifier/closure evidence; it received no private reference, source metadata, other repository context, or downstream architecture hypothesis. Exact packets, outputs, and provenance are under `analysis/review_packets/`, `analysis/fresh_reviews/`, and `analysis/fresh_review_manifest.md`.

## Counterfactual Cuts

None were proposed or run. The frozen protocol permits this step only after a fresh reviewer identifies `TOO_WIDE` or `MISSING_LEMMA` with at least `MEDIUM` confidence. All four independent reviews instead returned `STRATEGY_WASTE / HIGH`. Constructing cuts here would manufacture support absent from the evidence.

## Interpretation

The blind protocol removes the specific N1.5 confound: no proof-relevant session had a working external retrieval path, and post-run traces show no attempted source lookup or reference access. The result is therefore evidence about unchanged DANUS under the intended blind condition.

The 4/4 solve rate alone does not decide the N2 gate. The deciding evidence is the attempt shape: four structurally different, frozen, reference-backed problems produced 28 accepted direct full proofs, no rejections, no failed search, no dependency edges, and no reviewer-supported wide-gap or missing-lemma region. The dominant pathology is redundant parallel completion after the target was already independently solvable, not inability to discover a local proof cut.

This diagnostic is not a universal claim about every theorem distribution. It says that Adaptive Cut-Set is not supported as the next intervention by this valid four-problem blind control.

## N2 Gate

**N2_TARGET_NOT_SUPPORTED**

- blind-integrity PASS runs: 4 across 4 problems;
- diagnostic set: frozen before execution, new, structurally selected, and independently reference-backed;
- traces: complete enough to attribute all 28 attempts, verifier outcomes, Facts, closures, tokens, and durations;
- credible `TOO_WIDE` / `MISSING_LEMMA` regions: 0 across 0 problems;
- concrete permitted local Cut-Sets: 0;
- dominant issue: `STRATEGY_WASTE / FULL_PROOF_DUPLICATION`, confirmed by four fresh reviews at HIGH confidence.

The support threshold—credible cut regions on at least two distinct problems—is not met. The stronger `NOT_SUPPORTED` verdict, rather than `INCONCLUSIVE`, is justified because protocol validity, set validity, and trace adequacy all pass and the observed failure mode is unambiguous.

## Integrity

- DANUS modified: **NO**. Nested repository HEAD remains `6d92e8d415933ca2ef52fd1a4da73fdfcd418f1c`, branch `codex`, working tree clean.
- DANUS prompts modified: **NO**.
- Noespire `src/` modified: **NO**; `git diff noespire-n1-proof-obligations -- src/` is empty.
- problems modified after freeze: **NO**; `git diff 3c530a7 -- experiments/danus_n16_blind/problems` is empty and all four byte hashes match the frozen manifest.
- external solution leakage: **NO** in the four valid runs; all are `BLIND_INTEGRITY_PASS`.
- mathematical reruns: **NO**. The sole repeated problem is the explicitly excluded system-invalid environment attempt followed by its one permitted valid run after a fresh passing capability gate.
- N2 implementation: **NO**.

### Windows nested-cache / ACL-helper correction

The artifact copier had preserved nested worker `.agents` links and `.lake/.git` build/VCS caches. On the Windows parent repository these reparse-point/cache paths triggered Git's ACL helper (`Function not implemented`) while indexing the copied evidence. `run_once.py::copy_project_artifacts` now excludes only `.agents`, `.git`, `.lake`, and `__pycache__` from copied evidence snapshots. Existing copied cache/link entries were removed only from the preserved snapshot after resolving their exact paths; the live frozen DANUS repository and runtime were not altered. The copied run trees now contain no reparse points, nested `.git`, `.lake`, or Gitlink entries, and Git can index them normally. Raw logs remain byte-preserved through `runs/** -text`.

## Next Step

Freeze a separate matched control experiment for the observed duplication pathology—worker-count or sequential early-stop/diversification ablation—before reconsidering Adaptive Cut-Set. Do not implement N2 from this diagnostic.
