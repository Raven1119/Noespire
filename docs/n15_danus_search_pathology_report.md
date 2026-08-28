# N1.5 DANUS Search-Pathology Diagnostic

## Frozen State

- Noespire N1: `ca3ca05694ab1d1c86ea7b215d5dca0eec500a89`, tag `noespire-n1-proof-obligations`
- pre-run diagnostic-set commit: `7aa8ad0f79dcb8015034b4a9f467be7400eeae7b`
- DANUS: branch `codex`, commit `6d92e8d415933ca2ef52fd1a4da73fdfcd418f1c`
- model/verifier: worker model `gpt-5.6-sol`; verifier model `gpt-5.6-sol`, effort `xhigh`
- common runtime: seven workers (`high:3,xhigh:4`), one round, 14,400-second worker timeout, 900-second verifier Codex timeout, unchanged retrieval/tools/memory/FactGraph/orchestration
- configuration differences from Baseline A: different problem statements; one frozen problem-independent seven-role assignment template instead of Baseline A's problem-specific method assignments; lexicographically smallest accepted exact-target Fact selected mechanically instead of operator selection

The problem set and its hashes were committed before the first worker started. Four projects were then run sequentially, exactly once each, with no retry, best-of-N, replacement, manual Fact, prompt edit, or mid-run guidance.

## Diagnostic Set

| Problem | Source | Structural rationale | Hash |
| --- | --- | --- | --- |
| `putnam-2024-a1` | MAA 2024, A1 | Primitive reduction, parity, modular obstruction, exceptional exponent | `7dadf7c3b65fc240d2fd20960388560e588599d3f71b3af7466198c0a10064a5` |
| `putnam-2024-a2` | MAA 2024, A2 | Polynomial composition, divisibility, degree comparison, sufficiency | `0517d18b72174a3151df961bfd5986db34c8ebc21fe85d873e288ac43abebe79` |
| `putnam-2023-b1` | MAA 2023, B1 | Invariant representation, converse reachability, lattice-path count | `f21221acf68b5de8c7485860936434741da89f7dc2cced7699f3f605a6bbf5bd` |
| `putnam-2024-b2` | MAA 2024, B2 | Geometric invariants, finite-state reduction, congruence uniqueness | `34b0b7eb5f95ee524a7dcb2435b9c457e2c1409ef71065472996f87df52d638e` |

The exact statements, authoritative URLs, selection rationale, and evaluator-only reference sources are frozen in `experiments/danus_n15_diagnostic/problems/manifest.json`.

## Run Results

Here “Attempts” means worker sessions, matching the frozen mechanical metric. B2 has eight attempt-table rows because one worker made two verifier submissions while another made none.

| Problem | Solved | Attempts | Accepts | Rejects | Facts | Closure | Outside | Tokens | Wall-clock |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `putnam-2024-a1` | yes | 7 | 7 | 0 | 7 | 1 | 6 | 899,738 | 469.064 s |
| `putnam-2024-a2` | yes | 7 | 7 | 0 | 7 | 1 | 6 | 853,553 | 388.491 s |
| `putnam-2023-b1` | yes | 7 | 7 | 0 | 7 | 1 | 6 | 1,089,160 | 725.429 s |
| `putnam-2024-b2` | yes | 7 | 7 | 0 | 7 | 1 | 6 | 1,097,110 | 670.656 s |
| **Total** | **4/4** | **28** | **28** | **0** | **28** | **4** | **24** | **3,939,561** | **2,253.640 s** |

Raw immutable run copies are preserved locally under `experiments/danus_n15_diagnostic/runs/`. The complete fact graph, project state, worker traces, verifier outputs, closure, stdout/stderr, usage, wall time, and termination result exist for every run. The raw directories are intentionally ignored by the parent repository rather than vendored as product source.

## Attempt-Level Findings

The factual 29-row table is `experiments/danus_n15_diagnostic/analysis/attempt_trace.csv`.

### `putnam-2024-a1`

- observed behavior: all seven workers submitted the full theorem and all passed; no predecessor Fact was used
- expensive regions: no failed or rejected region; worker usage ranged from 66,204 to 119,276 tokens
- repeated routes: six exact target statements and one near-identical formatting variant
- unused verified facts: six target-proof alternatives lie outside the mechanically selected one-node closure
- classification: `DIRECTLY_SOLVABLE`; token cost alone does not justify `TOO_WIDE`

### `putnam-2024-a2`

- observed behavior: seven full-target submissions, all accepted, with no predecessor Facts
- expensive regions: no failed or rejected region; worker usage ranged from 47,598 to 126,219 tokens
- repeated routes: one exact-target group of seven
- unused verified facts: six accepted target-proof alternatives outside closure
- classification: `DIRECTLY_SOLVABLE`

### `putnam-2023-b1`

- observed behavior: seven full-target submissions, all accepted, with no predecessor Facts
- expensive regions: `xhigh2` used 193,422 tokens and `xhigh3` used 145,830, but both passed; there is no concrete failed dependency or missing claim
- repeated routes: one exact-target group of seven
- unused verified facts: six accepted target-proof alternatives outside closure
- classification: `DIRECTLY_SOLVABLE`; the trace supports proof-portfolio duplication, not a wide-gap diagnosis

### `putnam-2024-b2`

- observed behavior: six accepted full-target Facts and one accepted intermediate Fact; five workers submitted one target, `high2` submitted the intermediate plus a target depending on it, and `xhigh3` made no submission
- expensive regions: `xhigh3` used 136,890 tokens, completed a local direct route according to its trace, found an existing accepted target, and intentionally avoided another submission; this is not verifier failure
- repeated routes: six accepted target statements plus the explicit non-submitted duplicate route
- unused verified facts: five target alternatives and the useful intermediate lie outside the selected self-contained target closure
- intermediate structure: `66e0f3ce87e4696d` proves that fixed ordered sides and positive area admit at most two congruence classes; target Fact `9cf65343d0b09f0b` uses it as its only predecessor
- classification: both the verified two-step route and the no-submit route are `DIRECTLY_SOLVABLE`; the intermediate was created, verified, and used in the same round, so it is not evidence of a persistent missing lemma

## Fresh Diagnostic Review

Fresh reviewers saw only frozen local packets, not the repository, the aggregate hypothesis, or the desired gate outcome.

| Region | Classification | Confidence | Evidence |
| --- | --- | --- | --- |
| B2 `high2` intermediate and dependent target | `DIRECTLY_SOLVABLE` | HIGH | Both claims passed in one round; the intermediate has an observed downstream use and no predecessor |
| B1 high-cost direct attempts | `DIRECTLY_SOLVABLE` | HIGH | Seven no-predecessor target proofs passed; token totals alone show neither a wide gap nor a missing lemma |
| B2 `xhigh3` non-submission | `DIRECTLY_SOLVABLE` | MEDIUM | Trace reports a complete direct proof deliberately not submitted after target reuse; no verifier failure occurred |

No fresh review classified a region as `TOO_WIDE`, `MISSING_LEMMA`, or `BAD_DEPENDENCY`.

## Counterfactual Cut Analysis

There is no HIGH or MEDIUM-HIGH `TOO_WIDE`/`MISSING_LEMMA` region, so no pathology-qualified counterfactual Cut-Set is proposed or run.

B2 nevertheless supplies one useful structural control: a worker voluntarily used the following successful decomposition.

Original:

```text
partner relation and an initial convex quadrilateral
→ no infinite sequence of pairwise noncongruent partners
```

Observed successful decomposition:

```text
partner relation
→ H1: side-length multiset and area are invariant

fixed ordered side lengths + positive area
→ H2: at most two congruence classes

{H1, H2} + finitely many cyclic orders
→ finitely many congruence classes
→ target
```

Observed obstruction addressed: the potentially continuous family is reduced to finitely many congruence classes. This shows that a local intermediate boundary can be mathematically meaningful. It does **not** show that DANUS needed an external Cut intervention: the unchanged worker generated and verified `H2` and the target in the same round.

High-confidence Cut-Set-compatible pathology regions: **0**.

## Aggregate Pathologies

- `TOO_WIDE`: 0 supported regions
- `MISSING_LEMMA`: 0 supported regions
- `BAD_DEPENDENCY`: 0 supported regions
- `STRATEGY_WASTE`: no individual outside-closure Fact is automatically classified as waste; the cross-problem pattern is redundant full-target portfolio work and duplicate verification
- repeated targets/routes: 4 exact/near target groups; 23 accepted full-target Facts beyond the four selected targets; one additional explicit non-submitted duplicate route
- other: substantive reference-access contamination occurred on all 4 problems
- failed-proof-cost: A1 `0.0`, A2 `0.0`, B1 `0.0`, B2 `unavailable`; aggregate `unavailable`. B2's no-submit worker cannot honestly be called a failed attempt, and per-submission attribution for the two-submit worker is unavailable
- verified-search-waste: mechanically `24/28 = 85.71%`; this is the outside-closure ratio, not a semantic waste verdict. Of those 24 Facts, 23 are alternative accepted full-target proofs and one is B2's genuinely used intermediate from a non-selected proof route

## Reference-Proof Firewall Audit

The evaluator did not place its offline reference outlines in any DANUS project. However, unchanged DANUS retained web retrieval, and at least one worker on **every problem** found or read a problem-specific official solution during execution. Examples include A1 downloading and extracting a solutions PDF, A2 confirming the official reduction, B1 changing presentation after reading the official path method, and B2 reading the official finite-representation proof.

Therefore the firewall failed in substance even though the input packaging was correct. These runs measure unchanged Baseline A DANUS with its normal retrieval access; they do not constitute a blind test of independent proof discovery. The detailed trace citations are in `experiments/danus_n15_diagnostic/analysis/reference_access_audit.md`. The set was not changed and no problem was rerun after this discovery.

## Research Interpretation

Under the frozen conditions, unchanged DANUS did not exhibit verifier-visible proof-search failure: it solved all four problems in one round, produced 28 accepted Facts, and received zero rejections. The observable inefficiency was parallel workers repeatedly completing the whole target, not workers repeatedly failing at a concrete wide claim or waiting on a missing lemma. B2 shows that DANUS can create a useful intermediate Fact organically, but also that mechanical selection of another self-contained target can make that useful Fact appear “outside closure.”

This evidence cannot establish that wide-gap pathology is absent. Official-solution retrieval contaminated all four problems, and the traces do not separate independent discovery cost from solution-guided completion. The experiment therefore diagnoses orchestration/retrieval confounds more clearly than an Adaptive Cut-Set opportunity.

## N2 Gate

`N2_TARGET_INCONCLUSIVE`

Evidence:

- the support threshold is not met: there are zero HIGH or MEDIUM-HIGH `TOO_WIDE`/`MISSING_LEMMA` regions across zero problems
- all 28 verifier calls passed, so there is no recurring verifier-visible obstruction to align with a Cut
- B2 contains one meaningful two-step proof structure, but it was solved inside one unchanged worker round and is not a failure region
- official-solution access on all four problems prevents a strong negative conclusion from the 4/4 solve rate
- cost attribution is incomplete for the only no-submit worker and the two-submit worker

This verdict is not `N2_TARGET_SUPPORTED`, because the explicit gate is unmet. It is not `N2_TARGET_NOT_SUPPORTED`, because the contaminated reference-access condition prevents this small set from ruling out the hypothesized pathology.

## Integrity

- problems frozen before runs: **YES**, commit `7aa8ad0f79dcb8015034b4a9f467be7400eeae7b`
- problem statements changed or replaced after first run: **NO**
- runs per problem: **exactly one**
- raw trace evidence preserved: **YES**
- DANUS modified: **NO**
- DANUS prompts modified: **NO**
- DANUS final HEAD: `6d92e8d415933ca2ef52fd1a4da73fdfcd418f1c`
- DANUS working tree: **clean**
- Noespire `src/` modified relative to `noespire-n1-proof-obligations`: **NO**
- N1 tag changed: **NO**
- manual Facts, mid-run guidance, retries, or post-hoc problem replacement: **NO**
- reference proofs entered worker context: **YES, through unchanged worker web retrieval; not through evaluator input injection**
- N2 runtime/product implementation: **NONE**
- Noespire deterministic tests: **26 passed, 1 real-Codex smoke skipped by its opt-in guard**
- N1.5 mechanical replay: **PASS**, 4 runs and 29 attempt rows
- Baseline A analyzer compatibility replay: **PASS**, 3 runs and 21 attempt rows

Validation commands:

```text
wsl -e python3 experiments/.../analyze_runs.py experiments/.../runs --expect-runs 4 --output-dir experiments/.../analysis
wsl -e python3 experiments/.../analyze_runs.py experiments/danus_baseline_a/runs --expect-runs 3
python -m py_compile experiments/danus_n15_diagnostic/run_once.py experiments/danus_n15_diagnostic/analysis/analyze_runs.py
wsl -e bash -lc "PYTHONPATH=src python3 -m unittest discover -s tests -v"
git diff noespire-n1-proof-obligations -- src/
git -C baselines/danus status --porcelain=v1
git -C baselines/danus rev-parse HEAD
```

## Next Step

Before deciding on N2, freeze a new blind diagnostic protocol that keeps the same unchanged proof algorithm but prevents problem-specific solution retrieval, then repeat on a newly frozen set not visible during protocol design. Do not implement Adaptive Cut-Set from the present evidence.
