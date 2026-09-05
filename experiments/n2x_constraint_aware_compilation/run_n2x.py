"""N2X runner — mechanical-constraint-aware patch compilation (§8-§16).

Cases:
- frozen_replay (§8-§10, PRIMARY): the real N2V run_02 episode-003 —
  frozen entropy-decrement Strategy Sketch, pre-compilation local state —
  recompiled by the REAL ConstraintAwarePatchBuilder (N2T prompt + the
  deterministic premise environment), then the frozen pipeline: REAL N2T
  FidelityAuditor (§12 content-drift audit) -> SAME Mechanical Validator ->
  fresh REAL Structural Auditor -> N2Q one-round revision on REVISE (§9).
  The N2W repair seam is DISABLED (§2/§15): a Mechanical FAIL is terminal.
  No NodeSolver (§16).
- control_valid (§14): the frozen N2S sample_01 sketch (N2T: mechanically
  valid, AUDITOR_PASS) recompiled once with the same constraints on a fresh
  N2R-snapshot copy — normal compilation must still pass. Fidelity/auditor
  stages are fixtures: the control measures only that constraints do not
  break compilation.

    .venv/Scripts/python.exe experiments/n2x_constraint_aware_compilation/run_n2x.py \
        --case frozen_replay [--force]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import sys
import time

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
for path in (
    REPO_ROOT / "src",
    REPO_ROOT / "experiments" / "n2l_closed_book_long_horizon",
    REPO_ROOT / "experiments" / "n2m_horizon_handoff",
    REPO_ROOT / "experiments" / "n2p_mathematical_strategist",
    REPO_ROOT / "experiments" / "n2q_auditor_guided_revision",
    REPO_ROOT / "experiments" / "n2r_strategist_stability",
    REPO_ROOT / "experiments" / "n2s_strategy_patch_separation",
    REPO_ROOT / "experiments" / "n2t_strategy_patch_compilation",
    REPO_ROOT / "experiments" / "n2u_live_two_stage",
    REPO_ROOT / "experiments" / "n2w_mechanical_patch_repair",
    HERE,
):
    sys.path.insert(0, str(path))

import run_experiment as n2l  # noqa: E402  (the N2L runner module)
import run_n2u as n2u  # noqa: E402  (control fixtures, reused)
from run_n2w import (  # noqa: E402  (N2W runner helpers, reused)
    RUN02_FRONTIER,
    _FrozenVerdictGate,
    _copy_run02_workspace,
    _load_run02_episode,
)
from closed_book import ClosedBookCodexInvoker  # noqa: E402
from sampler import prepare_snapshot, tree_hash  # noqa: E402  (N2R, read-only)
from patch_builder import FidelityAuditor  # noqa: E402  (N2T, frozen)
from reviser import MathematicalReviser  # noqa: E402  (N2Q, frozen)

from constrained_builder import ConstraintAwarePatchBuilder  # noqa: E402
from two_stage_driver import run_patch_stages  # noqa: E402

PID = n2l.ERDOS67_PROBLEM_ID
# The deterministic compilation environment: the exact value the two-stage
# driver hands to run_local_redecomposition (its default) — see source
# audit §1-§3. The validator and the builder cannot drift apart.
PROBLEM_PREMISE_FACT_IDS: tuple = ()

N2T_RUN = (
    REPO_ROOT / "experiments" / "n2t_strategy_patch_compilation"
    / "runs" / "compile_probe"
)


class _TimingBuilder:
    """Instrumentation only: per-call elapsed seconds (§23)."""

    def __init__(self, inner) -> None:
        self._inner = inner
        self.calls = 0
        self.seconds = []

    @property
    def last_prompt(self):
        return getattr(self._inner, "last_prompt", None)

    def compile(self, context, sketch):
        self.calls += 1
        t0 = time.time()
        try:
            return self._inner.compile(context, sketch)
        finally:
            self.seconds.append(round(time.time() - t0, 1))


def _illegal_premise_refs(patch_nodes, declared) -> list:
    """§11: every premise_fact_ids entry outside the declared set — the
    general contract, not just the one historically offending ID."""
    legal = set(declared)
    return sorted(
        {
            str(fact_id)
            for node in patch_nodes
            for fact_id in (node.get("premise_fact_ids") or [])
            if str(fact_id) not in legal
        }
    )


def _real_stack(evidence_dir: Path):
    invoker = ClosedBookCodexInvoker(audit_dir=evidence_dir / "invocations")
    builder = _TimingBuilder(
        ConstraintAwarePatchBuilder(
            invoker, problem_premise_fact_ids=PROBLEM_PREMISE_FACT_IDS
        )
    )
    fidelity = FidelityAuditor(invoker)  # N2T, unchanged (§12)
    reviser = MathematicalReviser(invoker)  # N2Q, unchanged (§9)

    def auditor_for(operation: str):
        from research.agents import StructuralAuditor

        return StructuralAuditor(invoker, operation=operation)  # fresh session

    return invoker, builder, fidelity, reviser, auditor_for


def _persist(case_root: Path, evidence_dir: Path, problem_dir: Path,
             episode: dict, evidence: dict, summary: dict) -> dict:
    n2l._write_json(evidence_dir / "episode.json", {"episode": episode, **evidence})
    (evidence_dir / "workspace").mkdir(parents=True, exist_ok=True)
    n2l._dump_workspace_evidence(problem_dir, evidence_dir / "workspace")
    summary["network_retrieval_attempts"] = n2l._network_attempt_total(case_root)
    n2l._write_json(evidence_dir / "summary.json", summary)
    return summary


def run_frozen_replay(case_root: Path) -> dict:
    """§8-§10 primary: would first-compile constraint disclosure have
    prevented the real run_02 Mechanical FAIL — without strategy, operator,
    or content drift?"""
    from run_n2w import RUN02_EVIDENCE

    source_hash_before = tree_hash(RUN02_EVIDENCE)
    problem_dir = _copy_run02_workspace(case_root)
    evidence_dir = case_root / "evidence"
    committed, failure, sketch, _ = _load_run02_episode()

    invoker, builder, fidelity, reviser, auditor_for = _real_stack(evidence_dir)
    context = n2u._context_for(problem_dir, RUN02_FRONTIER)

    t0 = time.time()
    episode, evidence, counts = run_patch_stages(
        problem_dir,
        problem_id=PID,
        frontier=RUN02_FRONTIER,
        context=context,
        sketch=sketch,
        gate=_FrozenVerdictGate(committed["gate"]),  # not under test
        fidelity=fidelity,  # REAL content-drift audit (§12)
        patch_builder=builder,
        reviser=reviser,
        auditor_for=auditor_for,
        # mechanical_repair stays None: N2W disabled (§2/§15)
    )
    wall = round(time.time() - t0, 1)

    patch_nodes = (evidence.get("patch") or {}).get("new_nodes") or []
    illegal_refs = _illegal_premise_refs(patch_nodes, PROBLEM_PREMISE_FACT_IDS)
    checks = {
        # §10 primary success criteria.
        "builder_completed": counts["builder"] == 1
        and counts["builder_timeout"] == 0
        and episode["outcome"] != "PATCH_COMPILATION_INVALID",
        "operator_preserved": episode["operator"] == "INSERT_CUT_SET",
        "fidelity_acceptable": episode.get("strategy_fidelity")
        in ("FAITHFUL", "PARTIALLY_FAITHFUL"),
        "no_strategy_drift": episode.get("strategy_fidelity") != "STRATEGY_DRIFT",
        "mechanical_pass": episode.get("mechanical_errors") == [],
        "auditor_final_pass": episode["outcome"] == "PATCH_APPLIED",
        # §11: zero illegal premise references (general contract).
        "no_illegal_premise_refs": illegal_refs == [],
        # §24: no semantic load smuggled into other obligations is judged by
        # the fidelity audit (no unrelated new claim / material replacement).
        "no_smuggled_content": all(
            claim.get("status") != "UNRELATED_NEW_CLAIM"
            for claim in (evidence.get("fidelity") or {}).get("claim_fidelity", [])
        ),
    }
    summary = {
        "case": "frozen_replay",
        "source_evidence": "experiments/n2v_two_stage_replication/runs/run_02/evidence",
        "source_episode": "episode-003-uniform_geometric_mutual_information_budget.json",
        "source_unchanged": source_hash_before == tree_hash(RUN02_EVIDENCE),
        "historical_control": {
            "run": "n2v run_02 episode-003",
            "outcome": "MECHANICAL_FAIL",
            "mechanical_errors": list(failure["mechanical_errors"]),
        },
        "frontier": RUN02_FRONTIER,
        "outcome": episode["outcome"],
        "episode": episode,
        "counts": counts,
        "patch_builder_calls": builder.calls,
        "patch_builder_seconds": builder.seconds,
        "illegal_premise_references": illegal_refs,
        "checks": checks,
        "primary_success": all(checks.values()),
        "wall_seconds": wall,
    }
    return _persist(case_root, evidence_dir, problem_dir, episode, evidence, summary)


def run_control_valid(case_root: Path) -> dict:
    """§14 Control B: a sketch whose unconstrained compilation was already
    mechanically valid (N2T sketch_sample_01) must STILL compile to a
    mechanically valid patch under the constraints block."""
    snapshot = prepare_snapshot(n2u.N2R_SNAPSHOT, case_root / "snapshot")
    evidence_dir = case_root / "evidence"
    sketch, sketch_packet = n2u._load_frozen_sketch("sample_01")
    invoker, builder, fidelity, reviser, auditor_for = _real_stack(evidence_dir)
    context = n2u._context_for(snapshot, n2u.FRONTIER)

    t0 = time.time()
    episode, evidence, counts = run_patch_stages(
        snapshot,
        problem_id=PID,
        frontier=n2u.FRONTIER,
        context=context,
        sketch=sketch,
        gate=n2u._FixedGate(),  # not under test (§14)
        fidelity=n2u._FixedFidelity(),  # not under test (§14)
        patch_builder=builder,
        reviser=None,
        # Scripted PASS auditor: the control measures only that constraints
        # do not break compilation (§14) — the auditor stage is not under
        # test here.
        auditor_for=lambda operation: _ScriptedPassAuditor(),
        # mechanical_repair stays None (§15)
    )
    wall = round(time.time() - t0, 1)

    patch_nodes = (evidence.get("patch") or {}).get("new_nodes") or []
    illegal_refs = _illegal_premise_refs(patch_nodes, PROBLEM_PREMISE_FACT_IDS)
    summary = {
        "case": "control_valid",
        "frozen_sketch_packet": str(
            (n2u.N2S_RUN / "sample_01").relative_to(REPO_ROOT)
        ),
        "historical_control": {
            "run": "n2t sketch_sample_01",
            "outcome": "AUDITOR_PASS",
            "mechanical_errors": [],
        },
        "frontier": n2u.FRONTIER,
        "outcome": episode["outcome"],
        "episode": episode,
        "counts": counts,
        "patch_builder_calls": builder.calls,
        "patch_builder_seconds": builder.seconds,
        "illegal_premise_references": illegal_refs,
        "control_pass": episode.get("mechanical_errors") == []
        and illegal_refs == []
        and counts["repair"] == 0,
        "wall_seconds": wall,
    }
    evidence["frozen_sketch_packet"] = sketch_packet
    return _persist(case_root, evidence_dir, snapshot, episode, evidence, summary)


class _ScriptedPassAuditor:
    """Control-B fixture: the Structural Auditor is not under test in §14."""

    def __init__(self) -> None:
        self.calls = 0
        self.last_prompt = None

    def audit(self, context, proposal, *, effort=None, timeout=None):
        from research.local_refinement import AuditorResult

        self.calls += 1
        return AuditorResult(verdict="PASS", reasons=("control fixture",))


def run_case(case: str, force: bool) -> dict:
    case_root = HERE / "runs" / case
    if case_root.exists():
        if not force:
            raise SystemExit(
                f"case dir already exists: {case_root} (pass --force to rerun)"
            )
        shutil.rmtree(case_root)
    case_root.mkdir(parents=True)
    if case == "frozen_replay":
        return run_frozen_replay(case_root)
    return run_control_valid(case_root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--case", required=True, choices=("frozen_replay", "control_valid")
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    summary = run_case(args.case, args.force)
    printable = {k: v for k, v in summary.items() if k != "episode"}
    print(json.dumps(printable, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
