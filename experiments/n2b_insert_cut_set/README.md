# N2B — INSERT_CUT_SET Experiment

Failure-conditioned local redecomposition, cut-set variant. The blocked goal G
is preserved verbatim: a fresh Codex LocalGraphBuilder inserts 2-4 NEW
intermediate propositions (cuts) as UNVERIFIED obligations; a fresh Codex
StructuralAuditor must PASS before the single history-preserving patch
(`apply_cut_set`) supersedes the blocked node, appends the cuts, creates
`<blocked>__cut` carrying G verbatim off the sink cuts, and rewires unexecuted
downstream consumers. Frozen NodeSolver/executor and FactGraph truth boundary
untouched. Source audit: `docs/n2b_insert_cut_set_source_audit.md`.

## Cases (all real: Docker-isolated Codex, 600s defaults)

- `control_a` — obvious missing lemma (n^3 - n divisible by 6); expectation
  (recorded): INSERT_CUT_SET + auditor PASS + frozen solver SOLVED.
- `control_b` — worker-ready obligation with an arithmetic-slip FAIL;
  expectation (recorded): NO_USEFUL_CUT.
- `control_c` — FALSE target (n=2 counterexample recorded); the runner asserts
  solve_status != SOLVED and that no admitted Fact equals the false statement.
- `erdos67` — frozen #67 baseline copied unmodified from `workspaces/`
  (blocked node `finite_discrepancy`); `obstruction_recurred` filled manually.

## Run (repo root, Git Bash)

```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe \
    experiments/n2b_insert_cut_set/run_experiment.py --case control_a [--force]
```

## Evidence layout

```
runs/<case>/workspace/<problem_id>/   live workspace (scaffold/obligations/attempts/facts)
runs/<case>/evidence/                 scaffold.json, obligations.json, attempts/, facts/,
                                      local_refinements/, summary.json
```

`summary.json`: outcome, proposal (cuts), auditor verdict, rerouted node,
per-node resolution, facts admitted, verdict sequences, per-phase wall seconds.
An existing `runs/<case>/` dir fails the run unless `--force`.
