# N1.7 Worker Scheduling Matched Ablation Protocol

Status: **PRE-RUN FROZEN**

## Hypothesis

The fixed parallel seven-worker launch is the main source of the N1.6 `24/28 = 85.71%` verified-search waste. A demand-driven direct attempt should retain the observed solve rate while materially reducing workers, verified Facts outside closure, and tokens.

## Frozen Inputs

- Problems: the four byte-identical N1.6 problem files and hashes in `runtime_manifest.json`.
- DANUS: commit `6d92e8d415933ca2ef52fd1a4da73fdfcd418f1c`, clean nested repository.
- Worker model: `gpt-5.6-sol`.
- Worker role and reasoning effort for every new attempt: `high`.
- Worker task: byte-identical `DIRECT_TASK` in `run_once.py`, equal to the N1.6 `high` direct-proof assignment plus its unchanged exact-target suffix.
- Verifier: unchanged DANUS verifier, `gpt-5.6-sol`, `xhigh`.
- Blind policy: exact N1.6 wrapper and canonical passing capability evidence; no external retrieval, source/reference access, web/browser/search, apps/plugins, or subagents; local DANUS Fact/Memory remains available.
- Runtime: one round, 14,400-second worker hard timeout, 900-second verifier Codex timeout, unchanged Fact Graph, retrieval, memory, target equality, and supporting closure.

## Arms

Arm A is the archived N1.6 result and is not rerun: four solved problems, 28 launched workers, 28 accepts, 28 Facts, closure size 4, 24 Facts outside closure, 2,731,554 tokens, and 1,652.824490 seconds.

Arm B (`high:1`) launches exactly one worker per problem. An exact verifier-accepted target solves the run; otherwise the problem is unsolved. A second worker is never launched.

Arm C (`high:7`) creates a maximum roster of seven identical `high` workers. It launches worker `i+1` only after worker `i` reaches a valid terminal state without any accepted exact target. It stops immediately after the first successful completed attempt. Unlaunched workers stay in `created` state.

B and C use one identical role, effort, and task for every possible attempt. No failure text is added to later assignments. Later C workers retain ordinary DANUS access to the shared Fact Graph and memory, but the harness performs no failure diagnosis or repair.

The immutable Arm A used the historical N1.6 `high:3,xhigh:4` diverse roster. The aggregate A comparison is therefore reported with that limitation; B/C do not reproduce that diversification because N1.7 explicitly forbids sequential diversified workers.

## Run Order and Validity

Run the four manifest problems once in Arm-B manifest order, followed by the same four once in Arm-C manifest order. Exactly eight valid mathematical runs are required. No multiseed or mathematical retry is allowed. A run with an environment, launcher, wrapper, verifier-service, timeout-contract, or integrity failure is `SYSTEM_INVALID_RUN`, excluded from mathematical results, and preserved with its evidence.

The exact-target rule is the lexicographically smallest accepted Fact whose whitespace-normalized statement equals the frozen problem bytes. Lack of such a Fact is a valid `DANUS_FAILED_TO_SOLVE` result.

## Metrics

Each result records solved, workers launched, worker attempts, verifier accepts/rejects, verified Fact count, closure size, outside-closure count, exact observed tokens, and scheduling wall clock. Arm C additionally records first-success index, stopped-after-success, and unused budget. Missing token evidence remains `unavailable`; it is never estimated.

Aggregate analysis reports solve rate, mean workers, total and mean tokens, total wall clock, and `outside-closure Facts / verified Facts`, plus reductions or changes relative to Arm A.

## Interpretation Gate

Use exactly one verdict from the task specification. In particular, Arm C has demonstrated value over B only if B fails a problem and a later C worker recovers it. If B and C both solve 4/4, conclude only that single-worker-first is sufficient on this set.

No scheduling semantics in `scheduler.py` or `run_once.py`, no problem bytes, and no arm definition may change after the pre-run freeze commit.
