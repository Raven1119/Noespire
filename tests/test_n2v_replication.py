"""N2V two-stage replication — minimal contract tests (task card §30).

Replication-only: the N2V runner must reuse the frozen N2U system
byte-identical, start every run from the clean baseline, keep budgets and
prompts unchanged, and the aggregate must never count INVALID (cascaded)
downstream progress.
"""

from __future__ import annotations

import sys
from pathlib import Path
from tempfile import TemporaryDirectory

REPO_ROOT = Path(__file__).resolve().parents[1]
for rel in (
    "src",
    "experiments/n2l_closed_book_long_horizon",
    "experiments/n2m_horizon_handoff",
    "experiments/n2p_mathematical_strategist",
    "experiments/n2q_auditor_guided_revision",
    "experiments/n2r_strategist_stability",
    "experiments/n2s_strategy_patch_separation",
    "experiments/n2t_strategy_patch_compilation",
    "experiments/n2u_live_two_stage",
    "experiments/n2v_two_stage_replication",
):
    sys.path.insert(0, str(REPO_ROOT / rel))

import run_experiment as n2l  # noqa: E402
import run_n2u  # noqa: E402  (frozen N2U runner)
from sampler import tree_hash  # noqa: E402  (N2R, read-only)
import two_stage_driver  # noqa: E402  (frozen N2U driver)

import aggregate as n2v_aggregate  # noqa: E402
import manifest as n2v_manifest  # noqa: E402
import run_n2v  # noqa: E402


# --- §30.2/3/4: frozen system identity ---------------------------------------


def test_runner_reuses_frozen_n2u_system() -> None:
    """§29: no copied driver — N2V calls the N2U runner itself."""
    assert run_n2v.n2u.run_live is run_n2u.run_live
    assert run_n2v.n2u.BUDGET is n2l.BUDGET  # §4 budgets unchanged
    assert set(two_stage_driver._OPERATION) == {
        "SPLIT", "INSERT_CUT_SET", "ADD_ALTERNATIVE_ROUTE",
    }  # §3 no new operator
    # §3 no resampling: the gate vocabulary and K=1 driver are the frozen ones.
    assert two_stage_driver.GATE_PASS_CLASSES == ("USEFUL_STRATEGY", "PLAUSIBLE_STRATEGY")


def test_manifest_deterministic_and_covers_frozen_components() -> None:
    """§7: manifest covers every frozen component file and is stable."""
    m1 = n2v_manifest.build_manifest()
    m2 = n2v_manifest.build_manifest()
    assert m1 == m2
    assert n2v_manifest.manifest_digest(m1) == n2v_manifest.manifest_digest(m2)
    assert set(m1["file_hashes"]) == set(n2v_manifest.FROZEN_FILES)
    assert m1["budget"] == {
        "max_mutation_episodes": 6,
        "max_solver_attempts": 24,
        "max_builder_proposals": 12,
        "max_auditor_calls": 12,
    }
    assert m1["solver_config"] == {
        "max_attempts_per_obligation": 3,
        "per_call_timeout_seconds": 600,
    }
    # N2U driver/runner files are part of the manifest (prompt drift control).
    assert "experiments/n2u_live_two_stage/two_stage_driver.py" in m1["file_hashes"]
    assert "experiments/n2s_strategy_patch_separation/sketch.py" in m1["file_hashes"]


def test_fresh_run_starts_from_clean_baseline(tmp_path) -> None:
    """§30.1: prepare copies its supplied baseline byte-for-byte."""
    from experiment_fixtures import failed_baseline
    from research.problem import ProblemSpec

    baseline = failed_baseline(
        tmp_path / "baseline", ProblemSpec(n2l.ERDOS67_PROBLEM_ID, n2l.ERDOS67_PROBLEM))
    before = tree_hash(baseline)
    problem_dir, problem = n2l.prepare_erdos67(tmp_path / "run", baseline_dir=baseline)
    assert problem.problem_id == n2l.ERDOS67_PROBLEM_ID
    assert tree_hash(problem_dir) == before == tree_hash(baseline)


# --- §30.7/8: aggregate correctness -------------------------------------------


def _summary(
    *,
    handoffs=1,
    mutations=1,
    frontiers=("a",),
    audit=(),
    episodes=1,
    solver_attempts=4,
    stop="AUDIT_BUDGET_EXHAUSTED-like",
) -> dict:
    eps = [
        {
            "blocked_node_id": f,
            "outcome": "PATCH_APPLIED",
            "operator": "INSERT_CUT_SET",
            "strategy_fidelity": "FAITHFUL",
            "operator_check": "OPERATOR_PRESERVED",
            "auditor_verdict": "PASS",
        }
        for f in frontiers
    ]
    return {
        "stop_reason": stop,
        "horizon_handoffs": handoffs,
        "mutation_episodes": mutations,
        "strategist_calls": episodes,
        "strategist_timeouts": 0,
        "gate_calls": episodes,
        "gate_rejects": 0,
        "patch_builder_calls": episodes,
        "patch_builder_timeouts": 0,
        "fidelity_calls": episodes,
        "auditor_calls": episodes,
        "revision_calls": 0,
        "episodes": eps,
        "fact_audit": [
            {"fact_id": fid, "classification": cls} for fid, cls in audit
        ],
        "metrics": {
            "fact_count": len(audit),
            "verified_reasoning_depth": 1 if audit else 0,
            "solver_attempts_during_run": solver_attempts,
            "verifier_rejections": 0,
            "external_authority_rejections": 0,
            "system_errors": 0,
            "facts": [
                {"fact_id": fid, "statement": "...", "predecessors": []}
                for fid, _ in audit
            ],
        },
        "budget": {
            "max_mutation_episodes": 6,
            "max_solver_attempts": 24,
            "max_builder_proposals": 12,
            "max_auditor_calls": 12,
        },
        "network_retrieval_attempts": 0,
        "wall_seconds": 1.0,
    }


def test_replication_criteria_mechanical() -> None:
    """§9: all six checks required; an INVALID fact fails the run."""
    good = _summary(audit=(("f1", "SUBSTANTIVE"),))
    ok, checks = n2v_aggregate.replicated_long_horizon_progress(good)
    assert ok and all(checks.values())

    no_handoff = _summary(handoffs=0, audit=(("f1", "SUBSTANTIVE"),))
    ok, checks = n2v_aggregate.replicated_long_horizon_progress(no_handoff)
    assert not ok and not checks["horizon_handoff>=1"]

    invalid = _summary(audit=(("f1", "SUBSTANTIVE"), ("f2", "INVALID")))
    ok, checks = n2v_aggregate.replicated_long_horizon_progress(invalid)
    assert not ok and not checks["zero_invalid_supporting_facts"]

    trivial_only = _summary(audit=(("f1", "TRIVIAL"),))
    ok, _ = n2v_aggregate.replicated_long_horizon_progress(trivial_only)
    assert not ok


def test_multi_stage_and_aggregate_verdict() -> None:
    """§10/§22/§23: multi-stage strength and the aggregate gates."""
    strong = _summary(
        mutations=2,
        frontiers=("a", "b"),
        audit=(("f1", "SUBSTANTIVE"), ("f2", "SUBSTANTIVE")),
        episodes=2,
    )
    assert n2v_aggregate.multi_stage_replication(strong)
    weak = _summary(audit=(("f1", "SUBSTANTIVE"),))
    assert not n2v_aggregate.multi_stage_replication(weak)

    result = n2v_aggregate.aggregate(
        {"run_01_n2u": strong, "run_02": strong, "run_03": weak}
    )
    assert result["replicated_count"] == 3
    assert result["replication_supported"] is True
    # §23 STRONG: 3/3 replicated AND multi-stage on 2/3 (run_01, run_02).
    assert result["stability"] == "STRONG"

    only_run1 = n2v_aggregate.aggregate(
        {
            "run_01_n2u": strong,
            "run_02": _summary(handoffs=0, mutations=0, frontiers=(), audit=(), episodes=0),
            "run_03": _summary(handoffs=0, mutations=0, frontiers=(), audit=(), episodes=0),
        }
    )
    assert only_run1["replication_supported"] is False
    assert only_run1["stability"] == "LOW"


def test_precise_stop_reason_splits_budgets() -> None:
    """§19: BUDGET_EXHAUSTED must name the binding budget."""
    audit_bound = _summary(stop="BUDGET_EXHAUSTED")
    audit_bound["gate_calls"] = 4
    audit_bound["fidelity_calls"] = 4
    audit_bound["auditor_calls"] = 6
    assert n2v_aggregate.precise_stop_reason(audit_bound) == "AUDIT_BUDGET_EXHAUSTED"

    mutation_bound = _summary(stop="BUDGET_EXHAUSTED", mutations=6)
    assert (
        n2v_aggregate.precise_stop_reason(mutation_bound) == "MUTATION_BUDGET_EXHAUSTED"
    )

    solved = _summary(stop="TARGET_SOLVED")
    assert n2v_aggregate.precise_stop_reason(solved) == "TARGET_SOLVED"


def test_aggregate_never_counts_invalid_downstream() -> None:
    """§30.8: cascaded INVALID facts contribute neither to substantive
    counts nor to closure size."""
    summary = _summary(
        audit=(("f1", "SUBSTANTIVE"), ("f2", "INVALID")),
        mutations=2,
        frontiers=("a", "b"),
        episodes=2,
    )
    summary["metrics"]["facts"] = [
        {"fact_id": "f1", "statement": "...", "predecessors": []},
        {"fact_id": "f2", "statement": "...", "predecessors": ["f1"]},
    ]
    substantive, _, invalid = n2v_aggregate.fact_classes(summary)
    assert substantive == ["f1"] and invalid == ["f2"]
    assert n2v_aggregate.supporting_closure_size(summary) == 1
    assert not n2v_aggregate.multi_stage_replication(summary)
