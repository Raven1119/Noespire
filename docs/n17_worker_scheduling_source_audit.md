# N1.7 Worker Scheduling Source Audit

## Scope

This audit covers only the frozen DANUS roster, launch, completion, target-acceptance, and stop seams needed for the N1.7 scheduling ablation. No DANUS or Noespire product source was changed.

## Current Seven-Worker Fan-out

- `baselines/danus/danus/orchestration/cli.py:343` defines the `danus new` default as `high:3,xhigh:4`.
- `baselines/danus/danus/execution/layout.py::parse_roles` expands that role specification to `high`, `high2`, `high3`, `xhigh`, `xhigh2`, `xhigh3`, and `xhigh4`.
- `baselines/danus/danus/execution/scaffold.py:116-153` creates the roster and writes each worker's model, reasoning effort, role, and author to `.role`.
- The historical N1.6 harness assigns all seven workers and calls `danus start <project>` (`experiments/danus_n16_blind/run_once.py:281-323`). `do_start` enumerates every worker directory and launches each (`baselines/danus/danus/orchestration/cli.py:188-197`).

## Roster Configuration Seam

`danus new <project> --roles <role:count>` is the existing roster seam. N1.7 can therefore request `high:1` for Arm B and `high:7` for Arm C without modifying DANUS. The latter creates seven independent worker homes with the same `high` role and reasoning effort. The experiment assigns the identical direct-proof task to every possible B/C worker.

The archived Arm A is not rerun. Its six additional workers used the frozen N1.6 heterogeneous task portfolio and the upstream `high:3,xhigh:4` efforts. B/C deliberately match the first Arm-A `high` direct worker and keep every possible retry identical, as required by the N1.7 prohibition on sequential diversification. Consequently, B and C are strictly matched to each other; comparison with the immutable aggregate Arm A is a policy-package comparison whose historical roster heterogeneity must remain visible in interpretation.

## Completion Collection

- Each detached worker loop records an atomic `.status.json` (`baselines/danus/danus/execution/loop.py::write_status`).
- With `DANUS_MAX_ROUNDS=1`, the loop runs one Codex session, records its return code, and reaches `max_rounds` on the next loop check (`baselines/danus/danus/execution/loop.py::main`).
- N1.6 polls all seven status files and returns only when every worker is terminal (`experiments/danus_n16_blind/run_once.py:140-159`). This guarantees the parallel arm continues waiting even if an exact target was accepted earlier.

## Target Acceptance and Early Stop

`fact_submit` synchronously invokes the verifier and appends a `verification` event; an accepted Fact is written before the worker call returns. N1.6 checks those events for an exact normalized target only after all seven workers terminate (`experiments/danus_n16_blind/run_once.py:388-405`). DANUS has no automatic “accepted target stops remaining workers” hook.

The existing `danus start <project>/<worker>` interface is the sufficient early-stop seam: the N1.7 harness launches one worker, waits for that worker's terminal status, reads the synchronous verification log, and either stops scheduling or launches the next worker. No already-running worker is cancelled because Arm C never has more than one running worker. `danus stop` remains only an error-cleanup mechanism.

## Experiment Implementation

The external harness is confined to `experiments/danus_n17_worker_scheduling/`. It uses native DANUS `new`, `assign`, `start`, `status` files, `finalize`, verifier, Fact Graph, retrieval, memory, and supporting-closure behavior. The only scheduling module exposes two policies:

- Arm B: budget one, always terminate after the first worker.
- Arm C: budget seven, launch strictly sequentially, stop after the first verifier-accepted exact target.

No prompt repair, failure diagnosis, adaptive decomposition, worker specialization, Cut-Set, or product scheduler is introduced.
