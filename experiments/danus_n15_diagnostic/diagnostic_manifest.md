# DANUS N1.5 Diagnostic Manifest

Status: **PRE-RUN FROZEN**

## Frozen State

- Noespire branch: `noespire-nl-proof-v2`
- Noespire N1 commit/tag: `ca3ca05694ab1d1c86ea7b215d5dca0eec500a89` / `noespire-n1-proof-obligations`
- DANUS path: `baselines/danus`
- DANUS branch/commit: `codex` / `6d92e8d415933ca2ef52fd1a4da73fdfcd418f1c`
- DANUS source, prompts, worker, verifier, strategy, FactGraph, retrieval, and orchestration modified: **NO**
- problem selection and hashes frozen before the first N1.5 worker starts: **YES**

## Development Diagnostic Set

| Order | Problem | Structure | SHA-256 |
| ---: | --- | --- | --- |
| 1 | `putnam-2024-a1` | number-theory classification and modular obstruction | `7dadf7c3b65fc240d2fd20960388560e588599d3f71b3af7466198c0a10064a5` |
| 2 | `putnam-2024-a2` | polynomial composition, divisibility, degree | `0517d18b72174a3151df961bfd5986db34c8ebc21fe85d873e288ac43abebe79` |
| 3 | `putnam-2023-b1` | combinatorial invariant, bijection, path count | `f21221acf68b5de8c7485860936434741da89f7dc2cced7699f3f605a6bbf5bd` |
| 4 | `putnam-2024-b2` | geometric invariant and finite-state uniqueness | `34b0b7eb5f95ee524a7dcb2435b9c457e2c1409ef71065472996f87df52d638e` |

The canonical machine-readable set is `problems/manifest.json`. A statement error discovered after execution begins is labeled `INVALID_PROBLEM`; no problem may be replaced.

## Reference-Proof Firewall

Official reference proofs and evaluator-only outlines are stored only in `analysis/problem_source_research.md`. Only the corresponding `problems/*.md` bytes may be copied into a DANUS `PROBLEM.md`. Reference material must not enter a worker task, master guidance, project memory, Fact Graph, verifier request, or any other DANUS-visible context.

## Runtime Equality with Baseline A

- backend: existing authenticated ChatGPT Codex session; credentials are not recorded
- main/worker/verifier model: `gpt-5.6-sol`
- worker roster: upstream default `high:3,xhigh:4`
- worker efforts: upstream role defaults (`high`, `xhigh`)
- verifier effort: `xhigh`
- maximum rounds: `1`
- round timeout: `14400` seconds
- maximum consecutive failures: `5`
- verifier Codex timeout: `900` seconds
- gateway verifier HTTP timeout: `3600` seconds
- retrieval, tool access, memory, FactGraph, and orchestration: unchanged upstream behavior
- execution: four sequential projects; no concurrent cross-project load

Configuration differences from Baseline A:

1. The diagnostic statements are different by experimental design.
2. Baseline A used problem-specific method assignments. N1.5 freezes one problem-independent seven-role assignment template for all four problems so no task is tuned after observing behavior.
3. Baseline A selected an accepted terminal Fact by operator inspection. N1.5 precommits to a mechanical target rule: among verifier-accepted Facts whose whitespace-normalized statement exactly equals the frozen problem text, select the lexicographically smallest Fact ID. If none exists, no target is finalized and the run is classified unsolved.

## Frozen Worker Assignment Template

Every assignment also requires the worker to submit the theorem statement verbatim from `PROBLEM.md` and to use only verifier-accepted predecessor Facts when genuinely needed.

- `high`: develop a rigorous complete proof directly.
- `high2`: seek an independent alternative proof route.
- `high3`: identify concrete intermediate lemmas or obstructions, prove what is justified, and complete the target if possible.
- `xhigh`: produce a complete quantified proof with assumptions and boundary cases audited.
- `xhigh2`: independently audit promising routes and produce a verifier-ready proof if possible.
- `xhigh3`: seek a structurally distinct proof and record concrete obstructions if blocked.
- `xhigh4`: inspect shared verified state, synthesize the strongest available route, and complete the target if possible.

## Run Protocol

Each problem receives exactly one independent unchanged-DANUS run in the frozen order. There is no multi-seed, best-of-N, retry, problem replacement, prompt edit, manual Fact insertion, or mid-run human guidance. Complete upstream project state, workers, Fact Graph, global/local memory, verifier outputs, stdout/stderr, status, usage, timing, target, and closure are archived under `runs/`.

## Mechanical Metrics Contract

`analysis/analyze_runs.py` reconstructs run metrics and attempt rows only from raw artifacts. It does not classify mathematics. Reliable per-worker tokens are attributed to an attempt only when that worker made exactly one verifier submission in its single round; otherwise the row says `unavailable`. Any requested quantity unsupported by artifacts is also `unavailable`, never estimated.

Offline classifications and counterfactual Cut proposals are produced only after all four runs finish. They never enter DANUS runtime.
