# N1.9b Fresh Strictly Matched Scheduling Protocol

Status: **PRE-RUN FROZEN** once the manifest hashes and freeze commit are recorded.

## Causal contract

Every cell creates an independent empty DANUS project with seven configured `high` slots, `gpt-5.6-sol`, high reasoning effort, exact problem bytes, exact assignment bytes, unchanged DANUS verifier, frozen N1.9a wrapper, equal timeouts, and equal tool policy. Only the batches passed to the already-tested N1.8 `run_schedule` module vary.

- A launches slots `(1,2,3,4,5,6,7)` concurrently, cancels none, and waits for all seven terminal states.
- B launches only slot `(1)` and terminates after its verified PASS or FAIL.
- C launches singleton slots in order, advances only after a verified failure, and stops at the first exact accepted target or after slot 7.

All seven TASK files are assigned before any launch. Later C workers receive the same bytes and no orchestrator-injected failure text, hints, diagnosis, or altered effort. They are independent Codex sessions inside the same normal DANUS project, so accepted Fact Graph/global-memory state is project-shared exactly as it is for concurrent A workers. A later C success is therefore a scheduling recovery under unchanged DANUS semantics, not a claim that the worker started from an empty graph. Per-batch fact counts preserve this distinction. Project identifiers may differ; the canonical mathematical initial-state hash must match across arms for each problem.

## Blind and reference contract

Every proof-relevant Codex process uses the byte-identical N1.9a wrapper. The deterministic host orchestrator runs as root so it alone can read private references during audit, while a frozen hash-checked, root-owned shim creates a private mount namespace, hides the parent Noespire `.git` object database, masks the child process's specific WSL interop socket, disables Windows executable interoperability and OpenTelemetry export, then changes to UID/GID `1000:1000` with all supplementary groups cleared and Linux `no_new_privs` set. Keeping the owning UID is required for Codex's chmod-based drvfs runtime protocol; clearing groups removes Docker socket access and `no_new_privs` prevents sudo/setuid escalation. Other `/run/WSL` services remain available so the Codex app-server can initialize. Only a process launched from the exact frozen DANUS verifier-agent directory receives the one additional writable root `runtime/verify-runs`; proof workers receive no extra writable directory. The isolation canary verifies that role-limited output path plus effective identity, group removal, sudo/Docker denial, and Linux/Windows-native parent-Git/history denial. Host Git, Windows interoperability, and the nested frozen DANUS repository are unchanged outside the child namespace. `SEARCH_INTENT_BLOCKED` and mechanically denied outbound attempts pass; any external connection, result, or bytes fail the cell. The frozen N1.9a capability artifact is the precondition gate, and each completed cell receives an automatic live audit.

Plaintext references are committed for reproducibility, moved to the root-only private store before the first mathematical run, read only by deterministic host-side audits, and restored after all cells terminate. Proof projects receive problem statements only.

## Execution and evidence

The counterbalanced order is `ABC`, `BCA`, `CAB`, `ACB`, `BAC`, `CBA`. A mathematical PASS or FAIL is final. At most one replacement is allowed only for a preserved `SYSTEM_INVALID_RUN`. Each valid run preserves input, initial state, effective configuration, wrapper/verifier/worker traces, Fact Graph, supporting closure, token observations, first-target time, and terminal time. Derived metrics are recomputed from raw artifacts.

No N2, Cut-Set, scaffold refinement, failure diagnosis, graph surgery, prompt adaptation, DANUS change, or product scheduling implementation is part of this experiment.
