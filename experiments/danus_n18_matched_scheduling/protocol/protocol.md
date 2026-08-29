# N1.8 Strictly Matched Scheduling Protocol

Status: **PRE-RUN FROZEN**.

## Causal contract

Every arm creates a fresh empty DANUS project with the same seven `high` workers, `gpt-5.6-sol`, `high` reasoning effort, exact problem bytes, exact `worker_assignment.txt` bytes, unchanged verifier, N1.6 blind wrapper, timeouts, and tool policy. Only the batches passed to `run_schedule` vary.

- A launches `(1,2,3,4,5,6,7)` concurrently and waits for all seven terminal states; it never cancels after early success.
- B launches `(1)` and terminates after that worker, whether it succeeds or fails.
- C launches `(1)`, then one additional singleton batch only after the preceding batch has no exact accepted target, up to seven; it stops after success.

All seven slots are assigned before launch in every arm. Later C workers receive no failure text, diagnosis, feedback, hint, new route, new effort, or different prompt. The canonical initial-state hash excludes only project/run identifiers and is compared across arms for each problem.

## OOD freeze and run order

The six problems and self-contained references were selected before any N1.8 DANUS proof run and without pilot performance. Their hashes and the deterministic 18-run counterbalance are in `runtime_manifest.json`. A valid mathematical failure is final and is not rerun. One replacement is allowed only after one preserved `SYSTEM_INVALID_RUN` environment failure.

## Blind and reference handling

The wrapper is the byte-identical N1.6 wrapper. During every proof-relevant session, plaintext N1.8 references are stored outside the execution workspace. Only their frozen SHA-256 values remain in the manifest. A pre-run capability probe must fail to read both the private storage canary and any in-workspace plaintext reference, while preserving local DANUS access and the N1.6 network/tool restrictions. After all runs and audits, the exact hash-matching references may be restored for repository evidence.

## Evidence and metrics

Each run preserves input, initial state, effective configuration, commands, blind logs, worker state/logs, verifier outputs, Fact Graph, closure, exact tokens when exposed, first-target timestamp, and terminal time. A post-run audit changes only `blind_integrity` from pending to PASS/FAIL. Derived metrics are recomputed from the 18 `result.json` files; raw evidence is immutable.

No N2, Cut-Set, decomposition, failure diagnosis, graph surgery, DANUS source change, or product scheduling code is permitted.
