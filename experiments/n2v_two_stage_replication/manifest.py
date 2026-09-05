"""N2V drift-control manifest (task card §7/§28).

A plain sha256 manifest over every frozen component the two-stage live
system is composed of, plus the budget values, solver config, problem
statement, and the baseline workspace tree hash. Persisted per run;
equality across runs + a clean git tree demonstrates no component drift.
No framework — one function.
"""

from __future__ import annotations

from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
for path in (
    REPO_ROOT / "src",
    REPO_ROOT / "experiments" / "n2l_closed_book_long_horizon",
    REPO_ROOT / "experiments" / "n2r_strategist_stability",
):
    sys.path.insert(0, str(path))

import run_experiment as n2l  # noqa: E402
from sampler import tree_hash  # noqa: E402  (N2R, read-only)

FROZEN_FILES = (
    "src/research/local_refinement.py",
    "src/research/scaffold.py",
    "src/research/node_solver.py",
    "src/research/graph.py",
    "src/research/obligation.py",
    "src/research/fact.py",
    "src/research/agents.py",
    "src/research/pipeline.py",
    "src/research/problem.py",
    "src/application/codex_isolation.py",
    "experiments/n2l_closed_book_long_horizon/driver.py",
    "experiments/n2l_closed_book_long_horizon/run_experiment.py",
    "experiments/n2l_closed_book_long_horizon/closed_book.py",
    "experiments/n2l_closed_book_long_horizon/fact_audit.py",
    "experiments/n2l_closed_book_long_horizon/metrics.py",
    "experiments/n2m_horizon_handoff/handoff.py",
    "experiments/n2m_horizon_handoff/classification.py",
    "experiments/n2p_mathematical_strategist/strategist.py",
    "experiments/n2p_mathematical_strategist/treatment_driver.py",
    "experiments/n2q_auditor_guided_revision/reviser.py",
    "experiments/n2s_strategy_patch_separation/sketch.py",
    "experiments/n2t_strategy_patch_compilation/patch_builder.py",
    "experiments/n2u_live_two_stage/two_stage_driver.py",
    "experiments/n2u_live_two_stage/run_n2u.py",
)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_manifest(root: Path = REPO_ROOT) -> dict:
    """Hash every frozen input of the N2U live system (§7)."""
    root = Path(root)
    file_hashes = {}
    for rel in FROZEN_FILES:
        path = root / rel
        if not path.is_file():
            raise FileNotFoundError(f"frozen component missing: {rel}")
        file_hashes[rel] = _sha256(path)
    return {
        "file_hashes": file_hashes,
        "budget": asdict(n2l.BUDGET),
        "solver_config": {
            "max_attempts_per_obligation": 3,
            "per_call_timeout_seconds": 600,
        },
        "problem": {
            "problem_id": n2l.ERDOS67_PROBLEM_ID,
            "statement_sha256": hashlib.sha256(
                n2l.ERDOS67_PROBLEM.encode("utf-8")
            ).hexdigest(),
        },
        "baseline_tree_sha256": tree_hash(n2l.ERDOS67_BASELINE),
    }


def manifest_digest(manifest: dict) -> str:
    """One order-independent digest for cross-run comparison."""
    canonical = json.dumps(manifest, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
