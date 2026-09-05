"""N2M horizon handoff — experiment runner CLI.

Research-layer only. Everything except the handoff wiring is reused from
N2L: closed-book surface, fixtures, budgets, metrics, fact audit. The only
new behavior (task card §2): a typed 600 s invocation timeout on the solve
path is LOCAL_HORIZON_EXHAUSTED — obligation stays OPEN, graph escalation
eligible — instead of SYSTEM_ERROR stop.

Cases:

- control_a_fake: deterministic forced-horizon fixture (§25A) — stub worker
  times out on the first node, CUT applies, children solve, target SOLVED.
  No Docker, no model.
- control_b_real: ordinary theorem (N2L control_a fixture), real closed-book
  agents. Expectation: first-round PASS, handoff never fires (§25B).
- control_c_fake: deterministic infrastructure error (§25C) — stub worker
  raises a non-timeout exception; driver must stop SYSTEM_ERROR with zero
  graph-operator calls. No Docker, no model.
- erdos67: byte-identical frozen baseline workspace, identical conditions
  to N2L (same theorem/model/timeout/budgets/closed-book), sole change is
  the handoff (§26).

Usage (repo root, Git Bash; console is GBK so force UTF-8):

    PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe \
        experiments/n2m_horizon_handoff/run_n2m.py --case control_a_fake [--force]
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
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(N2L_DIR))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from research.fact import CandidateFact  # noqa: E402
from research.node_solver import NodeSolverConfig  # noqa: E402
from research.pipeline import VerificationResult  # noqa: E402

import run_experiment as n2l  # noqa: E402  (the N2L runner module)
from driver import run_long_horizon  # noqa: E402
from fact_audit import FactAuditor, cascade_invalid  # noqa: E402
from handoff import make_solve_error_handoff  # noqa: E402
from metrics import compute_metrics  # noqa: E402

HERE = Path(__file__).resolve().parent
BUDGET = n2l.BUDGET  # frozen N2L budgets, unchanged (§17)


# --- deterministic fake agents (controls A/C) ------------------------------------


class TimeoutOnceWorker:
    """Times out (typed 600 s TimeoutExpired) on the first proposal for each
    goal in ``timeout_goals``; echoes the goal as the candidate otherwise."""

    def __init__(self, timeout_goals=()) -> None:
        self.timeout_goals = set(timeout_goals)
        self.timed_out = set()

    def propose(self, *, problem, existing_facts, subgoal, repair_context=None):
        goal = subgoal.split("Goal:\n", 1)[1]
        if goal in self.timeout_goals and goal not in self.timed_out:
            self.timed_out.add(goal)
            raise subprocess.TimeoutExpired(cmd=["docker", "run"], timeout=600)
        return CandidateFact(
            goal,
            f"A candidate proof of {goal}",
            tuple(fact.fact_id for fact in existing_facts),
        )


class InfrastructureErrorWorker:
    def propose(self, *, problem, existing_facts, subgoal, repair_context=None):
        raise RuntimeError("scripted infrastructure failure: docker daemon unavailable")


class AcceptingVerifier:
    def verify(self, problem, candidate, predecessors):
        return VerificationResult(True, "scripted accept")


class DecliningBuilder:
    def __init__(self, operation: str) -> None:
        self.operation = operation

    def propose(self, context, *, effort=None, timeout=None):
        from research.local_refinement import BuilderResult

        return BuilderResult(
            outcome={
                "split": "NO_USEFUL_SPLIT",
                "insert_cut_set": "NO_USEFUL_CUT",
                "add_alternative_route": "NO_USEFUL_ROUTE",
            }[self.operation]
        )


class PassingAuditor:
    def __init__(self) -> None:
        self.calls = 0

    def audit(self, context, proposal, *, effort=None, timeout=None):
        from research.local_refinement import AuditorResult

        self.calls += 1
        return AuditorResult(verdict="PASS", reasons=("scripted pass",))


def _cut_builder_result(blocked_node_id: str):
    from research.local_refinement import parse_cut_set_output

    raw = json.dumps(
        {
            "outcome": "INSERT_CUT_SET",
            "obstruction": "The direct route stalled at the local horizon.",
            "expected_effect": "Two helper obligations split the gap.",
            "new_nodes": [
                {"node_id": "h1", "goal": "Helper lemma one.", "depends_on": [],
                 "premise_fact_ids": []},
                {"node_id": "h2", "goal": "Helper lemma two.", "depends_on": ["h1"],
                 "premise_fact_ids": []},
            ],
            "missing_context": "",
        }
    )
    return parse_cut_set_output(raw, blocked_node_id=blocked_node_id)


# --- cases ------------------------------------------------------------------------


def _fake_workspace(case_root: Path, problem_id: str, statement: str, node_id: str):
    from research.obligation import ObligationRegistry
    from research.problem import ProblemSpec
    from research.scaffold import ProofScaffold, ScaffoldNode

    problem = ProblemSpec(problem_id, statement)
    problem_dir = case_root / "workspace" / problem_id
    problem_dir.mkdir(parents=True, exist_ok=False)
    ProofScaffold.create(
        problem_dir / "scaffold.json",
        problem=problem,
        target_node_id="target",
        nodes=(
            ScaffoldNode(node_id, statement),
            ScaffoldNode("target", statement, depends_on=(node_id,)),
        ),
    )
    ObligationRegistry(problem_dir / "obligations.json")  # created by solve
    return problem_dir, problem


def run_control_a_fake(case_root: Path) -> dict:
    """§25A: forced horizon on the first node; CUT takes over; progress."""
    problem_dir, problem = _fake_workspace(
        case_root, "n2m-control-a-timeout", "Lemma M implies theorem T.", "mid"
    )
    builder_results = {
        "split": None,  # declines
        "insert_cut_set": _cut_builder_result("mid"),
    }

    def builder_for(operation: str):
        result = builder_results.get(operation)
        if result is None:
            return DecliningBuilder(operation)

        class _Stub:
            def propose(self, context, *, effort=None, timeout=None):
                return result

        return _Stub()

    auditor = PassingAuditor()
    result = run_long_horizon(
        problem_dir,
        problem=problem,
        worker=TimeoutOnceWorker(timeout_goals={"Lemma M implies theorem T."}),
        verifier=AcceptingVerifier(),
        builder_for=builder_for,
        auditor_for=lambda operation: auditor,
        budget=BUDGET,
        author="n2m-control-a",
        solve_error_handoff=make_solve_error_handoff(problem.problem_id),
    )
    summary = {
        "case": "control_a_fake",
        "stop_reason": result.stop_reason,
        "horizon_handoffs": result.horizon_handoffs,
        "mutation_episodes": result.mutation_episodes,
        "builder_proposals": result.builder_proposals,
        "auditor_calls": result.auditor_calls,
        "solver_attempts": result.solver_attempts,
        "episodes": list(result.episodes),
    }
    # Contract (§25A): handoff fired once, an operator applied, solved.
    assert result.horizon_handoffs == 1
    assert result.stop_reason == "TARGET_SOLVED"
    assert result.mutation_episodes == 1
    (case_root / "evidence").mkdir(parents=True, exist_ok=True)
    n2l._dump_workspace_evidence(problem_dir, case_root / "evidence")
    n2l._write_json(case_root / "evidence" / "summary.json", summary)
    return summary


def run_control_c_fake(case_root: Path) -> dict:
    """§25C: infrastructure error -> SYSTEM_ERROR stop, zero operators."""
    problem_dir, problem = _fake_workspace(
        case_root, "n2m-control-c-infra", "Any theorem.", "mid"
    )
    requested = []

    def builder_for(operation: str):
        requested.append(operation)
        return DecliningBuilder(operation)

    result = run_long_horizon(
        problem_dir,
        problem=problem,
        worker=InfrastructureErrorWorker(),
        verifier=AcceptingVerifier(),
        builder_for=builder_for,
        auditor_for=lambda operation: PassingAuditor(),
        budget=BUDGET,
        author="n2m-control-c",
        solve_error_handoff=make_solve_error_handoff(problem.problem_id),
    )
    summary = {
        "case": "control_c_fake",
        "stop_reason": result.stop_reason,
        "error": result.error,
        "horizon_handoffs": result.horizon_handoffs,
        "builder_proposals": result.builder_proposals,
        "operators_requested": requested,
    }
    # Contract (§25C): stops as SYSTEM_ERROR; no graph operator invoked.
    assert result.stop_reason == "SYSTEM_ERROR"
    assert result.horizon_handoffs == 0
    assert requested == []
    (case_root / "evidence").mkdir(parents=True, exist_ok=True)
    n2l._dump_workspace_evidence(problem_dir, case_root / "evidence")
    n2l._write_json(case_root / "evidence" / "summary.json", summary)
    return summary


def _run_real_case(case: str, case_root: Path, solver_attempts: int = 3) -> dict:
    """Real closed-book run with the N2M handoff wired in. Identical
    conditions to N2L (§26); the handoff is the only new behavior."""
    if case == "control_b_real":
        problem_dir, problem = n2l.prepare_control_a(case_root)
    elif case == "erdos67":
        problem_dir, problem = n2l.prepare_erdos67(case_root)
    else:  # pragma: no cover
        raise SystemExit(f"unknown real case: {case}")
    evidence_dir = case_root / "evidence"
    initial_attempts = n2l._attempt_count(problem_dir)

    invoker, worker, verifier, builder_for, auditor_for = n2l._agents(evidence_dir)
    t0 = time.time()
    result = run_long_horizon(
        problem_dir,
        problem=problem,
        worker=worker,
        verifier=verifier,
        builder_for=builder_for,
        auditor_for=auditor_for,
        budget=BUDGET,
        solver_config=NodeSolverConfig(max_attempts_per_obligation=solver_attempts),
        author=f"n2m-{case}",
        solve_error_handoff=make_solve_error_handoff(problem.problem_id),
    )
    wall = round(time.time() - t0, 1)

    # Post-run independent fact audit (N2L §30, reused unchanged).
    from research.graph import FactGraph

    graph = FactGraph(problem_dir)
    auditor = FactAuditor(invoker)
    fact_audits = []
    for fact in graph.list_facts():
        predecessors = [graph.get_fact(pid) for pid in fact.predecessors]
        try:
            fact_audits.append(
                auditor.audit(
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
    metrics = compute_metrics(
        problem_dir, initial_attempt_count=initial_attempts, wall_seconds=wall
    )
    summary = {
        "case": case,
        "problem_id": problem.problem_id,
        "stop_reason": result.stop_reason,
        "solve_status": result.solve_status,
        "error": result.error,
        "mutation_episodes": result.mutation_episodes,
        "builder_proposals": result.builder_proposals,
        "auditor_calls": result.auditor_calls,
        "horizon_handoffs": result.horizon_handoffs,
        "episodes": list(result.episodes),
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

    if case == "control_b_real":
        # §25B invariant: with the handoff wired, every solve-path timeout
        # must produce exactly one handoff; no timeout → zero handoffs.
        # (A non-timeout exception stops SYSTEM_ERROR before this line.)
        timeout_attempts = metrics["system_errors"]
        assert result.horizon_handoffs == timeout_attempts
    return summary


def run_case(case: str, force: bool, solver_attempts: int = 3) -> dict:
    case_root = HERE / "runs" / case
    if case_root.exists():
        if not force:
            raise SystemExit(
                f"case dir already exists: {case_root} (pass --force to rerun)"
            )
        shutil.rmtree(case_root)
    case_root.mkdir(parents=True)
    if case == "control_a_fake":
        return run_control_a_fake(case_root)
    if case == "control_c_fake":
        return run_control_c_fake(case_root)
    return _run_real_case(case, case_root, solver_attempts=solver_attempts)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--case",
        required=True,
        choices=("control_a_fake", "control_b_real", "control_c_fake", "erdos67"),
    )
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    summary = run_case(args.case, args.force)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
