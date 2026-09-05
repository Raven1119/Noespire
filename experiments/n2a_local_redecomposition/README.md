# N2A — Local Redecomposition Experiment

Failure-conditioned local redecomposition (SPLIT only). When a scaffold node is
blocked by recorded failed attempts, a fresh Codex LocalGraphBuilder proposes a
self-contained split into narrower children; a fresh Codex StructuralAuditor
must PASS before the single history-preserving patch (`apply_split`) runs. The
frozen NodeSolver/executor and the FactGraph truth boundary are untouched.
Source audit: `docs/n2a_local_redecomposition_source_audit.md`.

## Cases

- `control_a` — deterministic (no model): stub SPLIT + fake worker/verifier;
  proves the machinery end-to-end.
- `control_b` — real builder/auditor on a repair-sized local gap; expectation:
  NO_USEFUL_SPLIT or auditor rejection (recorded, not asserted).
- `control_c` — real builder/auditor on a degenerate target-restatement node;
  expectation: genuine split, auditor PASS, frozen solver continues (budget 3).
- `erdos67` — real builder/auditor on the frozen #67 baseline workspace
  (blocked node `finite_discrepancy`), copied unmodified from `workspaces/`.

## Run (repo root, Git Bash)

```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe \
    experiments/n2a_local_redecomposition/run_experiment.py --case control_a [--force]
```

Real cases require the Docker isolation backend (`IsolatedCodexInvoker`
defaults, 600s). An existing `runs/<case>/` dir fails the run unless `--force`.

## Evidence layout

```
runs/<case>/workspace/<problem_id>/   live workspace (scaffold/obligations/attempts/facts)
runs/<case>/evidence/                 scaffold.json, obligations.json, attempts/, facts/,
                                      local_refinements/, summary.json
```

`summary.json` records outcome, proposal, auditor verdict, per-node resolution,
facts admitted, verdict sequences, per-phase wall seconds; `obstruction_recurred`
for erdos67 is filled manually. The summary is also printed to stdout.
