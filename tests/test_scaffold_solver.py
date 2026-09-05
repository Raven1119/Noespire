"""Scaffold integration of the bounded NodeSolver repair loop.

``solver_config=None`` keeps the legacy one-shot path byte-identical; a
``NodeSolverConfig`` routes the selected node's execution through
``NodeSolver`` with the same worker/verifier. A repaired node still admits
exactly one verifier-PASS Fact; a node that exhausts its budget blocks the
run with upstream Facts intact and downstream nodes never executed.
"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

from research.fact import CandidateFact
from research.graph import FactGraph
from research.node_solver import NodeSolverConfig
from research.obligation import ObligationRegistry, ObligationStatus
from research.pipeline import VerificationResult
from research.problem import ProblemSpec
from research.scaffold import ProofScaffold, ScaffoldNode, solve_scaffold


class RecordingEchoWorker:
    """Proves whichever goal it is handed; records repair_context per call."""

    def __init__(self) -> None:
        self.calls = 0
        self.goals = []
        self.repair_contexts = []

    def propose(self, *, problem, existing_facts, subgoal, repair_context=None):
        self.calls += 1
        goal = subgoal.split("Goal:\n", 1)[1]
        self.goals.append(goal)
        self.repair_contexts.append(repair_context)
        return CandidateFact(
            statement=goal,
            proof=f"Accepted proof of {goal}",
            predecessors=tuple(fact.fact_id for fact in existing_facts),
        )


class RaisingWorker:
    def __init__(self) -> None:
        self.calls = 0

    def propose(self, *, problem, existing_facts, subgoal, repair_context=None):
        self.calls += 1
        raise RuntimeError("scripted worker crash")


class ScriptedVerifier:
    def __init__(self, verdicts: tuple) -> None:
        self.verdicts = list(verdicts)
        self.calls = 0

    def verify(self, problem, candidate, predecessors):
        accepted, reason = self.verdicts[self.calls]
        self.calls += 1
        return VerificationResult(accepted, reason)


def _make_chain(root: Path):
    graph = FactGraph(root)
    problem = ProblemSpec("p", "Target T.")
    scaffold = ProofScaffold.create(
        root / "scaffold.json",
        problem=problem,
        target_node_id="target",
        nodes=(
            ScaffoldNode("n1", "Lemma one."),
            ScaffoldNode("n2", "Lemma two.", depends_on=("n1",)),
            ScaffoldNode("target", problem.statement, depends_on=("n2",)),
        ),
    )
    registry = ObligationRegistry(root / "obligations.json")
    return graph, problem, scaffold, registry


def _solve(root: Path, worker, verifier, solver_config=None):
    graph, problem, scaffold, registry = _make_chain(root)
    result = solve_scaffold(
        scaffold=scaffold,
        problem=problem,
        registry=registry,
        graph=graph,
        author="worker",
        worker=worker,
        verifier=verifier,
        solver_config=solver_config,
    )
    return result, graph, scaffold, registry


def _verdicts(root: Path):
    return [
        json.loads(path.read_text(encoding="utf-8"))["verdict"]
        for path in sorted((root / "attempts").glob("attempt-*.json"))
    ]


def test_repaired_node_continues_the_run_to_solved() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        worker = RecordingEchoWorker()
        verifier = ScriptedVerifier(
            (
                (True, "accepted"),
                (False, "lemma two has a gap"),
                (True, "accepted on repair"),
                (True, "accepted"),
            )
        )

        result, graph, scaffold, _ = _solve(
            root, worker, verifier, solver_config=NodeSolverConfig(2)
        )

        assert result.status == "SOLVED"
        assert worker.calls == 4
        assert verifier.calls == 4
        assert worker.goals == ["Lemma one.", "Lemma two.", "Lemma two.", "Target T."]
        assert worker.repair_contexts[0] is None
        assert worker.repair_contexts[1] is None
        repair = worker.repair_contexts[2]
        assert repair.verifier_reason == "lemma two has a gap"
        assert repair.attempt_number == 2
        assert repair.max_attempts == 2
        assert worker.repair_contexts[3] is None  # a new node starts at round 1
        assert _verdicts(root) == ["PASS", "FAIL", "PASS", "PASS"]
        assert [advance.attempt_id for advance in result.advances] == [
            "attempt-000001",
            "attempt-000003",  # n2 resolves on its second round
            "attempt-000004",
        ]
        assert sorted(fact.statement for fact in graph.list_facts()) == [
            "Lemma one.",
            "Lemma two.",
            "Target T.",
        ]


def test_exhausted_budget_blocks_with_upstream_facts_intact_and_downstream_untouched() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        worker = RecordingEchoWorker()
        verifier = ScriptedVerifier(
            (
                (True, "accepted"),
                (False, "lemma two rejected"),
                (False, "lemma two still rejected"),
            )
        )

        result, graph, scaffold, registry = _solve(
            root, worker, verifier, solver_config=NodeSolverConfig(2)
        )

        assert result.status == "BLOCKED"
        assert worker.calls == 3  # n1 once, n2 exactly twice, target never
        assert verifier.calls == 3
        assert _verdicts(root) == ["PASS", "FAIL", "FAIL"]
        # Upstream verified Fact persists; downstream node never executes.
        assert [fact.statement for fact in graph.list_facts()] == ["Lemma one."]
        assert scaffold.get("n1").resolved_by_fact_id is not None
        assert scaffold.get("n2").resolved_by_fact_id is None
        assert scaffold.get("target").resolved_by_fact_id is None
        assert registry.get("scaffold:p:n2").status is ObligationStatus.OPEN
        # The target's obligation is never even created.
        assert [item.obligation_id for item in registry.list()] == [
            "scaffold:p:n1",
            "scaffold:p:n2",
        ]


def test_default_solver_config_keeps_one_shot_behavior() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        worker = RecordingEchoWorker()
        verifier = ScriptedVerifier(((True, "accepted"), (False, "rejected")))

        result, _, _, registry = _solve(root, worker, verifier)

        assert result.status == "BLOCKED"
        assert worker.calls == 2  # one attempt per node, no repair round
        assert worker.repair_contexts == [None, None]
        assert _verdicts(root) == ["PASS", "FAIL"]
        assert registry.get("scaffold:p:n2").status is ObligationStatus.OPEN


def test_worker_error_propagates_with_error_evidence_in_solver_mode() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        graph, problem, scaffold, registry = _make_chain(root)
        worker = RaisingWorker()

        try:
            solve_scaffold(
                scaffold=scaffold,
                problem=problem,
                registry=registry,
                graph=graph,
                author="worker",
                worker=worker,
                verifier=ScriptedVerifier(((True, "accepted"),)),
                solver_config=NodeSolverConfig(3),
            )
            raised = None
        except RuntimeError as error:
            raised = error

        assert raised is not None and str(raised) == "scripted worker crash"
        assert worker.calls == 1  # remaining budget not consumed
        assert _verdicts(root) == ["ERROR"]
        assert registry.get("scaffold:p:n1").status is ObligationStatus.OPEN
