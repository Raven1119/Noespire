"""N2P mathematical local strategist — experiment runner CLI.

Research-layer only. Treatment (§2/§21): the fixed SPLIT→CUT→ALT escalation
is replaced by one fresh Mathematical Local Strategist decision per frontier
(K=1); the chosen operator executes through the frozen
`run_local_redecomposition` pipeline unchanged. Historical control: N2M/N2N
#67 evidence (§25) — no new control runs.

Cases:

- replay_state_a: §14 State A — N2M's committed post-timeout #67 workspace
  (theorem-strength failure; local_refinements/ stripped so the strategist
  sees the same first-decision state the fixed-escalation builders saw).
  One strategist decision + frozen validation/audit + independent proposal
  audit. No NodeSolver re-run.
- replay_state_b: §14 State B — N2N's committed final #67 workspace
  (3 verified Facts; frontier uniform_finite_torus_energy_certificate).
  Same single-decision replay.
- erdos67: live treatment from the byte-identical frozen baseline workspace
  (§21): same model/timeout/closed-book/operators/budgets as N2M/N2N; the
  only change is unified operator selection.

Usage (repo root, Git Bash; console is GBK so force UTF-8):

    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe \
        experiments/n2p_mathematical_strategist/run_n2p.py --case replay_state_a [--force]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import time

REPO_ROOT = Path(__file__).resolve().parents[2]
N2L_DIR = REPO_ROOT / "experiments" / "n2l_closed_book_long_horizon"
N2M_DIR = REPO_ROOT / "experiments" / "n2m_horizon_handoff"
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(N2L_DIR))
sys.path.insert(0, str(N2M_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

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
from proposal_audit import ProposalAuditor, build_audit_packet  # noqa: E402
from strategist import MathematicalStrategist, PredecidedBuilder, compile_to_builder_result  # noqa: E402
from treatment_driver import _OPERATION, _persist_strategist_packet, run_treatment  # noqa: E402

HERE = Path(__file__).resolve().parent
BUDGET = n2l.BUDGET  # frozen N2L budgets, unchanged (§21)
PID = n2l.ERDOS67_PROBLEM_ID

STATE_A_SOURCE = (
    REPO_ROOT / "experiments" / "n2m_horizon_handoff" / "runs" / "erdos67" / "workspace" / PID
)
STATE_A_FRONTIER = "finite_discrepancy"
STATE_B_SOURCE = (
    REPO_ROOT
    / "experiments"
    / "n2n_failure_provenance"
    / "runs"
    / "erdos67"
    / "workspace"
    / PID
)
STATE_B_FRONTIER = "uniform_finite_torus_energy_certificate"


def _agents(evidence_dir: Path):
    from research.agents import ResearchWorker, StructuralAuditor

    invoker = ClosedBookCodexInvoker(audit_dir=evidence_dir / "invocations")
    worker = ResearchWorker(invoker)
    verifier = ClosedBookVerifier(invoker)
    strategist = MathematicalStrategist(invoker)

    def auditor_for(operation: str):
        return StructuralAuditor(invoker, operation=operation)

    return invoker, worker, verifier, strategist, auditor_for


def run_replay(case: str, case_root: Path) -> dict:
    """§14 frozen-state replay: ONE strategist decision on a committed real
    #67 state; frozen validation + structural audit run; independent
    proposal audit follows. No NodeSolver re-run (§14)."""
    source, frontier = {
        "replay_state_a": (STATE_A_SOURCE, STATE_A_FRONTIER),
        "replay_state_b": (STATE_B_SOURCE, STATE_B_FRONTIER),
    }[case]
    problem_dir = case_root / "workspace" / PID
    problem_dir.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, problem_dir)
    if case == "replay_state_a":
        # Strip N2M's escalation OUTCOMES (not mathematical state) so the
        # strategist faces the same first-decision state (source audit §5).
        for name in ("local_refinements", "long_horizon_journal.jsonl"):
            path = problem_dir / name
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()

    evidence_dir = case_root / "evidence"
    invoker, _, _, strategist, auditor_for = _agents(evidence_dir)
    context = _build_context(
        scaffold=ProofScaffold(problem_dir / "scaffold.json"),
        graph=FactGraph(problem_dir),
        registry=ObligationRegistry(problem_dir / "obligations.json"),
        problem_id=PID,
        blocked_node_id=frontier,
    )
    t0 = time.time()
    try:
        decision = strategist.strategize(context)
    except subprocess.TimeoutExpired:
        # §34 SYSTEM_LIMIT: the strategist invocation itself hit the frozen
        # 600s horizon before producing any structured decision. That is a
        # graph-layer execution limit, not a mathematical verdict — record it
        # honestly instead of crashing the replay runner (integration fix,
        # §20). The invocation artifact is already persisted by CodexExec.
        wall = round(time.time() - t0, 1)
        summary = {
            "case": case,
            "source_workspace": str(source.relative_to(REPO_ROOT)),
            "frontier": frontier,
            "replay_outcome": "STRATEGIST_TIMEOUT",
            "operator": None,
            "strategist_packet": None,
            "proposal_audit": None,
            "wall_seconds": wall,
        }
        n2l._dump_workspace_evidence(problem_dir, evidence_dir)
        n2l._write_json(evidence_dir / "summary.json", summary)
        return summary
    packet_path = _persist_strategist_packet(
        problem_dir, frontier, 1, strategist.last_prompt, decision
    )
    outcome = None
    if decision.operator != "DECLINE":
        operation = _OPERATION[decision.operator]
        outcome = run_local_redecomposition(
            problem_dir,
            problem_id=PID,
            blocked_node_id=frontier,
            builder=PredecidedBuilder(
                compile_to_builder_result(decision, blocked_node_id=frontier),
                strategist.last_prompt,
            ),
            auditor=auditor_for(operation),
            operation=operation,
        )
    wall = round(time.time() - t0, 1)

    auditor = ProposalAuditor(invoker)
    # The context object was built BEFORE the mutation ran, so the audit
    # sees exactly what the strategist saw.
    audit = auditor.audit(build_audit_packet(context, decision))

    n2l._dump_workspace_evidence(problem_dir, evidence_dir)
    if (problem_dir / "strategist").is_dir():
        shutil.copytree(problem_dir / "strategist", evidence_dir / "strategist", dirs_exist_ok=True)
    summary = {
        "case": case,
        "source_workspace": str(source.relative_to(REPO_ROOT)),
        "frontier": frontier,
        "replay_outcome": (
            "STRATEGIST_DECLINED"
            if decision.operator == "DECLINE"
            else (outcome.outcome if outcome else None)
        ),
        "operator": decision.operator,
        "obstruction": decision.obstruction,
        "mathematical_idea": decision.mathematical_idea,
        "why_this_reduces_difficulty": decision.why_this_reduces_difficulty,
        "decline_reason": decision.decline_reason,
        "patch": [dict(node) for node in decision.new_nodes],
        "redecomposition_outcome": outcome.outcome if outcome else None,
        "mechanical_errors": list(outcome.mechanical_errors) if outcome else [],
        "structural_auditor_verdict": (
            outcome.auditor.verdict if outcome and outcome.auditor else None
        ),
        "child_node_ids": list(outcome.child_node_ids) if outcome else [],
        "proposal_audit": audit,
        "strategist_packet": str(packet_path),
        "wall_seconds": wall,
    }
    n2l._write_json(evidence_dir / "summary.json", summary)
    return summary


def run_live(case_root: Path, solver_attempts: int = 3) -> dict:
    """§21 live treatment on #67 from the clean frozen baseline."""
    problem_dir, problem = n2l.prepare_erdos67(case_root)
    evidence_dir = case_root / "evidence"
    initial_attempts = n2l._attempt_count(problem_dir)
    invoker, worker, verifier, strategist, auditor_for = _agents(evidence_dir)

    t0 = time.time()
    result = run_treatment(
        problem_dir,
        problem=problem,
        worker=worker,
        verifier=verifier,
        strategist=strategist,
        auditor_for=auditor_for,
        budget=BUDGET,
        solver_config=NodeSolverConfig(max_attempts_per_obligation=solver_attempts),
        author="n2p-erdos67",
        solve_error_handoff=make_solve_error_handoff(problem.problem_id),
    )
    wall = round(time.time() - t0, 1)

    # Independent post-hoc proposal audits (§16) — never fed back. Uses the
    # decision-time audit packet the driver snapshotted into each episode.
    proposal_auditor = ProposalAuditor(invoker)
    proposal_audits = []
    for episode in result.episodes:
        try:
            audit = proposal_auditor.audit(episode["audit_packet"])
            audit["blocked_node_id"] = episode["blocked_node_id"]
        except Exception as error:
            audit = {
                "blocked_node_id": episode["blocked_node_id"],
                "error": f"{type(error).__name__}: {error}",
            }
        proposal_audits.append(audit)

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
    if (problem_dir / "strategist").is_dir():
        shutil.copytree(problem_dir / "strategist", evidence_dir / "strategist", dirs_exist_ok=True)
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
        "auditor_calls": result.auditor_calls,
        "horizon_handoffs": result.horizon_handoffs,
        "episodes": list(result.episodes),
        "proposal_audits": proposal_audits,
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
    if case in ("replay_state_a", "replay_state_b"):
        return run_replay(case, case_root)
    return run_live(case_root)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--case",
        required=True,
        choices=("replay_state_a", "replay_state_b", "erdos67"),
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    summary = run_case(args.case, args.force)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
