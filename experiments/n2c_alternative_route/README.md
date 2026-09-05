# N2C — ADD_ALTERNATIVE_ROUTE Experiment

Failure-conditioned local redecomposition, alternative-route variant. The
current route R1 to blocked goal G is EXHAUSTED: a fresh Codex
LocalGraphBuilder proposes a materially different route R2 (2-4 NEW
obligations); a fresh Codex StructuralAuditor must PASS before the single
history-preserving patch (`apply_alternative_route`) PARKS the blocked node as
route-of-record, appends R2's nodes, creates `<blocked>__alt` carrying G
verbatim off the sink new nodes, and rewires unexecuted downstream consumers.
Frozen NodeSolver/executor and FactGraph truth boundary untouched. Source
audit: `docs/n2c_add_alternative_route_source_audit.md`.

## Cases (all real: Docker-isolated Codex, 600s defaults)

- `control_a` — obvious alternative strategy (irrational a,b with a^b
  rational; explicit-witness FAIL recorded); expectation (recorded):
  nonconstructive sqrt(2)^sqrt(2) case-analysis route, auditor PASS, SOLVED.
- `control_b` — route still reasonable (triangular-sum induction, fixable
  algebra-slip FAIL); expectation (recorded): NO_USEFUL_ROUTE.
- `control_c` — FALSE target (n^2+n+41 prime; n=40 counterexample recorded);
  the runner asserts solve_status != SOLVED and no admitted Fact equals it.- `erdos67` — frozen #67 baseline copied unmodified (blocked node
  `finite_discrepancy`) plus its own N2A/N2B `local_refinements/` history;
  `obstruction_recurred` filled manually.

## Run (repo root, Git Bash) — evidence in `runs/<case>/{workspace,evidence}/`

```bash
PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe \
    experiments/n2c_alternative_route/run_experiment.py --case control_a [--force]
```
