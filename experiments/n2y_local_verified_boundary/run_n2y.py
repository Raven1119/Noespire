"""N2Y runner — local verified boundary Fact dependencies (§13-§17).

Cases:
- frozen_replay (§13-§15, PRIMARY): the real N2V run_02 episode-003 —
  frozen entropy-decrement Strategy Sketch, pre-compilation local state whose
  verified boundary contains the run-derived Fact 4d1b3650dce361cb —
  recompiled by the REAL BoundaryAwarePatchBuilder (N2T prompt + the §11
  boundary disclosure), then the frozen pipeline: REAL N2T FidelityAuditor
  -> SAME Mechanical Validator (now boundary-aware via src/) -> fresh REAL
  Structural Auditor -> N2Q one-round revision on REVISE. The N2W repair
  seam is DISABLED (§25). No NodeSolver in the primary replay (§17 splits
  dependency plumbing from downstream proving).

Negative controls A/B/C (§18-§20: outside-boundary Fact, revoked Fact, OPEN
obligation masquerading as a Fact) and the §16/§17 lineage + supporting-
closure hard invariant are deterministic contract tests in
tests/test_n2y_local_verified_boundary.py (fake worker/verifier, no Codex) —
the task card explicitly permits deterministic fixtures for these; they are
not re-run here against the real model.

    .venv/Scripts/python.exe experiments/n2y_local_verified_boundary/run_n2y.py \
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
from sampler import tree_hash  # noqa: E402  (N2R, read-only)
from patch_builder import FidelityAuditor  # noqa: E402  (N2T, frozen)
from reviser import MathematicalReviser  # noqa: E402  (N2Q, frozen)

from boundary_builder import BoundaryAwarePatchBuilder  # noqa: E402
from two_stage_driver import run_patch_stages  # noqa: E402

PID = n2l.ERDOS67_PROBLEM_ID
# The run-derived verifier-accepted Fact whose citation the run_02 route
# needs (N2V Mechanical FAIL / N2W PARTIAL_STRUCTURAL_CHANGE / N2X
# auditor-demanded dependency — see the N2Y source audit).
RUN02_BOUNDARY_FACT_ID = "4d1b3650dce361cb"


class _TimingBuilder:
    """Instrumentation only: per-call elapsed seconds."""

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


def _premise_refs(patch_nodes) -> list:
    return sorted(
        {
            str(fact_id)
            for node in patch_nodes
            for fact_id in (node.get("premise_fact_ids") or [])
        }
    )


def run_frozen_replay(case_root: Path) -> dict:
    """§13-§15 primary: with boundary Facts legal, does the real run_02
    strategy compile to a mechanically valid, auditor-accepted patch whose
    route cites the needed verified Fact explicitly and legally?"""
    from run_n2w import RUN02_EVIDENCE

    source_hash_before = tree_hash(RUN02_EVIDENCE)
    problem_dir = _copy_run02_workspace(case_root)
    evidence_dir = case_root / "evidence"
    committed, failure, sketch, _ = _load_run02_episode()

    invoker = ClosedBookCodexInvoker(audit_dir=evidence_dir / "invocations")
    builder = _TimingBuilder(BoundaryAwarePatchBuilder(invoker))
    fidelity = FidelityAuditor(invoker)  # N2T, unchanged
    reviser = MathematicalReviser(invoker)  # N2Q, unchanged

    def auditor_for(operation: str):
        from research.agents import StructuralAuditor

        return StructuralAuditor(invoker, operation=operation)  # fresh session

    context = n2u._context_for(problem_dir, RUN02_FRONTIER)
    boundary_ids = sorted(fact.fact_id for fact in context.verified_boundary)

    t0 = time.time()
    episode, evidence, counts = run_patch_stages(
        problem_dir,
        problem_id=PID,
        frontier=RUN02_FRONTIER,
        context=context,
        sketch=sketch,
        gate=_FrozenVerdictGate(committed["gate"]),  # not under test
        fidelity=fidelity,  # REAL content-drift audit
        patch_builder=builder,
        reviser=reviser,
        auditor_for=auditor_for,
        # mechanical_repair stays None: N2W disabled (§25)
    )
    wall = round(time.time() - t0, 1)

    patch_nodes = (evidence.get("patch") or {}).get("new_nodes") or []
    refs = _premise_refs(patch_nodes)
    legal = set(boundary_ids)  # declared problem premise set is empty (N2X audit)
    checks = {
        # §15 primary success criteria.
        "builder_completed": counts["builder"] == 1
        and counts["builder_timeout"] == 0
        and episode["outcome"] != "PATCH_COMPILATION_INVALID",
        "operator_preserved": episode["operator"] == "INSERT_CUT_SET",
        "no_strategy_drift": episode.get("strategy_fidelity") != "STRATEGY_DRIFT",
        "mechanical_pass": episode.get("mechanical_errors") == [],
        "auditor_final_pass": episode["outcome"] == "PATCH_APPLIED",
        # §15: every cited premise is legal (declared ∪ local boundary).
        "all_premise_refs_legal": set(refs) <= legal,
    }
    summary = {
        "case": "frozen_replay",
        "source_evidence": "experiments/n2v_two_stage_replication/runs/run_02/evidence",
        "source_episode": "episode-003-uniform_geometric_mutual_information_budget.json",
        "source_unchanged": source_hash_before == tree_hash(RUN02_EVIDENCE),
        "historical_controls": {
            "n2v_run_02_episode_003": {
                "outcome": "MECHANICAL_FAIL",
                "mechanical_errors": list(failure["mechanical_errors"]),
            },
            "n2w_repair": "PARTIAL_STRUCTURAL_CHANGE (locality gate reject)",
            "n2x_constraint_aware": "Mechanical PASS but auditor demanded the "
            "dependency the operator could not express",
        },
        "frontier": RUN02_FRONTIER,
        "local_verified_boundary_fact_ids": boundary_ids,
        "boundary_fact_needed_by_route": RUN02_BOUNDARY_FACT_ID,
        "boundary_fact_cited": RUN02_BOUNDARY_FACT_ID in refs,
        "premise_fact_refs": refs,
        "outcome": episode["outcome"],
        "episode": episode,
        "counts": counts,
        "patch_builder_calls": builder.calls,
        "patch_builder_seconds": builder.seconds,
        "checks": checks,
        "primary_success": all(checks.values()),
        "deterministic_controls": {
            "control_A_outside_boundary": "tests/test_n2y_local_verified_boundary.py"
            "::test_accepted_fact_outside_local_boundary_rejected",
            "control_B_revoked": "tests/test_n2y_local_verified_boundary.py"
            "::test_revoked_boundary_fact_rejected",
            "control_C_open_obligation": "tests/test_n2y_local_verified_boundary.py"
            "::test_open_obligation_id_cannot_masquerade_as_fact",
            "lineage_and_closure": "tests/test_n2y_local_verified_boundary.py"
            "::test_boundary_fact_dependency_flows_into_admitted_fact_and_closure",
        },
        "wall_seconds": wall,
    }
    n2l._write_json(evidence_dir / "episode.json", {"episode": episode, **evidence})
    (evidence_dir / "workspace").mkdir(parents=True, exist_ok=True)
    n2l._dump_workspace_evidence(problem_dir, evidence_dir / "workspace")
    summary["network_retrieval_attempts"] = n2l._network_attempt_total(case_root)
    n2l._write_json(evidence_dir / "summary.json", summary)
    return summary


def run_lineage_control(case_root: Path) -> dict:
    """§16/§17 end-to-end control on the REAL applied patch: solve the
    boundary-citing child obligation with a fake worker / scripted verifier
    (deterministic, no Codex) and prove the lineage hard invariant —
    the boundary Fact must land in the admitted Fact's predecessors and in
    its supporting closure. Mathematical solvability is NOT under test."""
    from research.fact import CandidateFact
    from research.graph import FactGraph
    from research.obligation import ObligationRegistry
    from research.pipeline import VerificationResult
    from research.problem import ProblemSpec
    from research.scaffold import ProofScaffold, solve_scaffold

    replay_workspace = (
        HERE / "runs" / "frozen_replay" / "workspace"
        / f"let-f-n-1-1-prove-that-for-every-real-nu-ba4576"
    )
    if not replay_workspace.is_dir():
        raise SystemExit("run the frozen_replay case first")
    problem_dir = case_root / "workspace" / replay_workspace.name
    problem_dir.parent.mkdir(parents=True)
    shutil.copytree(replay_workspace, problem_dir)

    scaffold = ProofScaffold(problem_dir / "scaffold.json")
    node_ids = {node.node_id for node in scaffold.list_nodes()}
    child = "single_edge_entropy_potential_inequality"
    if child not in node_ids:
        raise SystemExit(
            f"applied patch does not contain the expected child: {node_ids}"
        )

    class EchoWorker:
        def __init__(self) -> None:
            self.calls = {}

        def propose(self, *, problem, existing_facts, subgoal, repair_context=None):
            goal = subgoal.split("Goal:\n", 1)[1]
            self.calls[goal] = tuple(fact.fact_id for fact in existing_facts)
            return CandidateFact(
                goal, f"scripted proof of {goal}", self.calls[goal]
            )

    class AcceptVerifier:
        def verify(self, problem, candidate, predecessors):
            return VerificationResult(True, "scripted accept")

    worker = EchoWorker()
    target_goal = scaffold.get(scaffold.target_node_id).goal
    result = solve_scaffold(
        scaffold=scaffold,
        problem=ProblemSpec(PID, target_goal),
        registry=ObligationRegistry(problem_dir / "obligations.json"),
        graph=FactGraph(problem_dir),
        author="worker",
        worker=worker,
        verifier=AcceptVerifier(),
    )

    graph = FactGraph(problem_dir)
    child_fact_id = scaffold.get(child).resolved_by_fact_id
    child_fact = graph.get_fact(child_fact_id) if child_fact_id else None
    closure_ids = (
        {fact.fact_id for fact in graph.supporting_closure(child_fact_id)}
        if child_fact_id
        else set()
    )
    child_goal = scaffold.get(child).goal
    checks = {
        "child_resolved": child_fact is not None,
        "worker_saw_boundary_fact_as_premise": RUN02_BOUNDARY_FACT_ID
        in worker.calls.get(child_goal, ()),
        "boundary_fact_in_predecessors": bool(
            child_fact and RUN02_BOUNDARY_FACT_ID in child_fact.predecessors
        ),
        "boundary_fact_in_supporting_closure": RUN02_BOUNDARY_FACT_ID in closure_ids,
    }
    summary = {
        "case": "lineage_control",
        "source_workspace": "runs/frozen_replay/workspace (real applied patch)",
        "solve_status": result.status,
        "child_obligation": child,
        "child_fact_id": child_fact_id,
        "child_fact_predecessors": list(child_fact.predecessors)
        if child_fact
        else [],
        "checks": checks,
        "control_pass": all(checks.values()),
        "network_retrieval_attempts": 0,
    }
    evidence_dir = case_root / "evidence"
    evidence_dir.mkdir(parents=True)
    n2l._write_json(evidence_dir / "summary.json", summary)
    return summary


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
    if case == "lineage_control":
        return run_lineage_control(case_root)
    raise SystemExit(f"unknown case: {case}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--case", required=True, choices=("frozen_replay", "lineage_control")
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    summary = run_case(args.case, args.force)
    printable = {k: v for k, v in summary.items() if k != "episode"}
    print(json.dumps(printable, ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
