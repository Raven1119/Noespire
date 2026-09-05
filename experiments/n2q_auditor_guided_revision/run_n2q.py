"""N2Q runner — bounded auditor-guided proposal revision (task card §10/§18).

Cases:
- replay_n2p_live: §10 frozen replay of the committed N2P live near-miss
  (proposal v1 + real auditor REVISE). ONE fresh revision, then v2 through
  the frozen pipeline (mechanical validation -> new fresh auditor), plus
  independent locality / issue-utilization and proposal audits. No
  NodeSolver re-run.
- erdos67: §18 live treatment from the clean frozen baseline. Identical
  conditions to N2P; the only variable is that AUDITOR_REVISE now allows
  exactly one bounded revision (§19).

    .venv/Scripts/python.exe experiments/n2q_auditor_guided_revision/run_n2q.py \
        --case replay_n2p_live [--force]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

HERE = Path(__file__).resolve().parent
REPO_ROOT = HERE.parents[1]
for path in (
    REPO_ROOT / "src",
    REPO_ROOT / "experiments" / "n2l_closed_book_long_horizon",
    REPO_ROOT / "experiments" / "n2m_horizon_handoff",
    REPO_ROOT / "experiments" / "n2p_mathematical_strategist",
    HERE,
):
    sys.path.insert(0, str(path))

from research.local_refinement import _build_context  # noqa: E402
from research.local_refinement import run_local_redecomposition  # noqa: E402
from research.graph import FactGraph  # noqa: E402
from research.node_solver import NodeSolverConfig  # noqa: E402
from research.obligation import ObligationRegistry  # noqa: E402
from research.scaffold import ProofScaffold  # noqa: E402

import run_experiment as n2l  # noqa: E402  (the N2L runner module)
from closed_book import ClosedBookCodexInvoker, ClosedBookVerifier  # noqa: E402
from fact_audit import FactAuditor, cascade_invalid  # noqa: E402
from handoff import make_solve_error_handoff  # noqa: E402  (N2M module)
from metrics import compute_metrics  # noqa: E402
from proposal_audit import ProposalAuditor, build_audit_packet  # noqa: E402  (N2P)
from strategist import (  # noqa: E402  (N2P)
    MathematicalStrategist,
    PredecidedBuilder,
    compile_to_builder_result,
    parse_strategist_output,
)
from revision_driver import (  # noqa: E402
    _persist_revision_packet,
    run_treatment_with_revision,
)
from reviser import (  # noqa: E402
    LocalityAuditor,
    MathematicalReviser,
    decision_view,
    parse_revision_output,
)
from treatment_driver import _OPERATION  # noqa: E402  (N2P)

BUDGET = n2l.BUDGET  # frozen N2L budgets, unchanged (§18)
PID = n2l.ERDOS67_PROBLEM_ID

N2P_LIVE_SOURCE = (
    REPO_ROOT / "experiments" / "n2p_mathematical_strategist" / "runs" / "erdos67" / "workspace" / PID
)
REPLAY_FRONTIER = "finite_discrepancy"
V1_REFINEMENT = "cut-9de1dd5d5cac.json"  # the committed N2P REVISE record


def _agents(evidence_dir: Path):
    from research.agents import ResearchWorker, StructuralAuditor

    invoker = ClosedBookCodexInvoker(audit_dir=evidence_dir / "invocations")
    worker = ResearchWorker(invoker)
    verifier = ClosedBookVerifier(invoker)
    strategist = MathematicalStrategist(invoker)  # N2P contract, unchanged (§22)
    reviser = MathematicalReviser(invoker)

    def auditor_for(operation: str):
        return StructuralAuditor(invoker, operation=operation)

    return invoker, worker, verifier, strategist, reviser, auditor_for


def _context_for(problem_dir: Path, frontier: str):
    return _build_context(
        scaffold=ProofScaffold(problem_dir / "scaffold.json"),
        graph=FactGraph(problem_dir),
        registry=ObligationRegistry(problem_dir / "obligations.json"),
        problem_id=PID,
        blocked_node_id=frontier,
    )


def run_replay(case_root: Path) -> dict:
    """§10: replay the committed N2P near-miss through one bounded revision."""
    problem_dir = case_root / "workspace" / PID
    problem_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(N2P_LIVE_SOURCE, problem_dir)

    evidence_dir = case_root / "evidence"
    invoker, _, _, _, reviser, auditor_for = _agents(evidence_dir)

    v1_packet = json.loads(
        (problem_dir / "strategist" / f"strategist-001-{REPLAY_FRONTIER}.json")
        .read_text(encoding="utf-8")
    )
    v1 = parse_strategist_output(v1_packet["raw"], blocked_node_id=REPLAY_FRONTIER)
    v1_record = json.loads(
        (problem_dir / "local_refinements" / V1_REFINEMENT).read_text(encoding="utf-8")
    )
    assert v1_record["auditor_verdict"] == "REVISE", "frozen replay requires the REVISE record"
    auditor_reasons = tuple(v1_record["auditor_reasons"])

    context = _context_for(problem_dir, REPLAY_FRONTIER)
    t0 = time.time()
    try:
        revision = reviser.revise(context, v1, auditor_reasons)
    except subprocess.TimeoutExpired:
        # Integration-level honesty (same lesson as N2P's STRATEGIST_TIMEOUT):
        # a reviser call that hits the frozen horizon is recorded, not crashed.
        wall = round(time.time() - t0, 1)
        summary = {
            "case": "replay_n2p_live",
            "frontier": REPLAY_FRONTIER,
            "replay_outcome": "REVISER_TIMEOUT",
            "wall_seconds": wall,
        }
        n2l._dump_workspace_evidence(problem_dir, evidence_dir)
        n2l._write_json(evidence_dir / "summary.json", summary)
        return summary
    packet_path = _persist_revision_packet(
        problem_dir, REPLAY_FRONTIER, 1, reviser.last_prompt, revision
    )

    outcome2 = None
    revision_outcome = "REVISION_NOT_LOCAL"
    error = None
    if revision.repairable:
        try:
            v2_builder = compile_to_builder_result(
                revision.decision, blocked_node_id=REPLAY_FRONTIER
            )
        except ValueError as exc:  # includes OperatorDriftError
            revision_outcome = "REVISION_INVALID"
            error = str(exc)
        else:
            outcome2 = run_local_redecomposition(
                problem_dir,
                problem_id=PID,
                blocked_node_id=REPLAY_FRONTIER,
                builder=PredecidedBuilder(v2_builder, reviser.last_prompt),
                auditor=auditor_for(_OPERATION[v1.operator]),  # fresh session
                operation=_OPERATION[v1.operator],
            )
            revision_outcome = {
                "APPLIED": "REVISION_PASS",
                "AUDITOR_REVISE": "REVISION_STILL_REVISE",
                "AUDITOR_REJECT": "REVISION_REJECTED",
            }.get(outcome2.outcome, "REVISION_INVALID")
    wall = round(time.time() - t0, 1)

    # Independent post-hoc audits (§13/§16/§24) — never fed back.
    locality = None
    proposal_audit = None
    if revision.decision is not None:
        locality = LocalityAuditor(invoker).audit(v1, revision.decision, auditor_reasons)
        proposal_audit = ProposalAuditor(invoker).audit(
            build_audit_packet(context, revision.decision)
        )

    n2l._dump_workspace_evidence(problem_dir, evidence_dir)
    revisions_dir = problem_dir / "revisions"
    if revisions_dir.is_dir():
        shutil.copytree(revisions_dir, evidence_dir / "revisions", dirs_exist_ok=True)
    summary = {
        "case": "replay_n2p_live",
        "source_workspace": str(N2P_LIVE_SOURCE.relative_to(REPO_ROOT)),
        "frontier": REPLAY_FRONTIER,
        "v1_operator": v1.operator,
        "auditor_v1_reasons": list(auditor_reasons),
        "replay_outcome": revision_outcome,
        "error": error,
        "repairable": revision.repairable,
        "not_local_reason": revision.not_local_reason,
        "v2": decision_view(revision.decision) if revision.decision else None,
        "v2_mechanical_errors": list(outcome2.mechanical_errors) if outcome2 else [],
        "v2_auditor_verdict": (
            outcome2.auditor.verdict if outcome2 and outcome2.auditor else None
        ),
        "v2_auditor_reasons": (
            list(outcome2.auditor.reasons) if outcome2 and outcome2.auditor else []
        ),
        "child_node_ids": list(outcome2.child_node_ids) if outcome2 else [],
        "locality_audit": locality,
        "proposal_audit_v2": proposal_audit,
        "revision_packet": str(packet_path),
        "wall_seconds": wall,
    }
    n2l._write_json(evidence_dir / "summary.json", summary)
    return summary


def run_live(case_root: Path, solver_attempts: int = 3) -> dict:
    """§18 live treatment on #67 from the clean frozen baseline; the single
    variable over N2P is the bounded revision on AUDITOR_REVISE."""
    problem_dir, problem = n2l.prepare_erdos67(case_root)
    evidence_dir = case_root / "evidence"
    initial_attempts = n2l._attempt_count(problem_dir)
    invoker, worker, verifier, strategist, reviser, auditor_for = _agents(evidence_dir)

    t0 = time.time()
    result = run_treatment_with_revision(
        problem_dir,
        problem=problem,
        worker=worker,
        verifier=verifier,
        strategist=strategist,
        reviser=reviser,
        auditor_for=auditor_for,
        budget=BUDGET,
        solver_config=NodeSolverConfig(max_attempts_per_obligation=solver_attempts),
        author="n2q-erdos67",
        solve_error_handoff=make_solve_error_handoff(problem.problem_id),
    )
    wall = round(time.time() - t0, 1)

    # Post-hoc independent audits (§13/§16/§24) — never fed back.
    proposal_auditor = ProposalAuditor(invoker)
    locality_auditor = LocalityAuditor(invoker)
    episode_audits = []
    for episode in result.episodes:
        entry = {"blocked_node_id": episode["blocked_node_id"]}
        try:
            entry["proposal_audit_v1"] = proposal_auditor.audit(episode["audit_packet"])
        except Exception as error:
            entry["proposal_audit_v1"] = {"error": f"{type(error).__name__}: {error}"}
        revision = episode.get("revision")
        if revision and revision.get("v2"):
            try:
                v1 = parse_strategist_output(
                    json.loads(
                        Path(episode["strategist_packet"]).read_text(encoding="utf-8")
                    )["raw"],
                    blocked_node_id=episode["blocked_node_id"],
                )
                v2 = parse_revision_output(
                    json.loads(
                        Path(revision["revision_packet"]).read_text(encoding="utf-8")
                    )["raw"],
                    blocked_node_id=episode["blocked_node_id"],
                    expected_operator=v1.operator,
                ).decision
                entry["locality_audit"] = locality_auditor.audit(
                    v1, v2, tuple(episode.get("auditor_reasons", ()))
                )
                entry["proposal_audit_v2"] = proposal_auditor.audit(revision["audit_packet"])
            except Exception as error:
                entry["locality_audit"] = {"error": f"{type(error).__name__}: {error}"}
        episode_audits.append(entry)

    # Post-run independent fact audit (N2L §30, reused unchanged).
    graph = FactGraph(problem_dir)
    fact_auditor = FactAuditor(invoker)
    fact_audits = []
    for fact in graph.list_facts():
        predecessors = [graph.get_fact(pid) for pid in fact.predecessors]
        try:
            fact_audits.append(
                fact_auditor.audit(
                    problem=problem.statement,
                    fact=fact,
                    predecessors=predecessors,
                    target_statement=problem.statement,
                )
            )
        except Exception as error:
            fact_audits.append(
                {
                    "fact_id": fact.fact_id,
                    "statement": fact.statement,
                    "classification": "AUDIT_ERROR",
                    "error": f"{type(error).__name__}: {error}",
                }
            )
    fact_audits = cascade_invalid(graph.list_facts(), fact_audits)

    n2l._dump_workspace_evidence(problem_dir, evidence_dir)
    for name in ("strategist", "revisions"):
        source_dir = problem_dir / name
        if source_dir.is_dir():
            shutil.copytree(source_dir, evidence_dir / name, dirs_exist_ok=True)
    metrics = compute_metrics(
        problem_dir, initial_attempt_count=initial_attempts, wall_seconds=wall
    )
    summary = {
        "case": "erdos67",
        "problem_id": problem.problem_id,
        "stop_reason": result.stop_reason,
        "solve_status": result.solve_status,
        "error": result.error,
        "mutation_episodes": result.mutation_episodes,
        "strategist_calls": result.strategist_calls,
        "revision_calls": result.revision_calls,
        "auditor_calls": result.auditor_calls,
        "horizon_handoffs": result.horizon_handoffs,
        "episodes": list(result.episodes),
        "episode_audits": episode_audits,
        "metrics": metrics,
        "fact_audit": fact_audits,
        "network_retrieval_attempts": n2l._network_attempt_total(case_root),
        "budget": {
            "max_mutation_episodes": BUDGET.max_mutation_episodes,
            "max_solver_attempts": BUDGET.max_solver_attempts,
            "max_builder_proposals": BUDGET.max_builder_proposals,
            "max_auditor_calls": BUDGET.max_auditor_calls,
        },
    }
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
    if case == "replay_n2p_live":
        return run_replay(case_root)
    return run_live(case_root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--case", required=True, choices=("replay_n2p_live", "erdos67"))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    summary = run_case(args.case, args.force)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
