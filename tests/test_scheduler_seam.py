from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory

from research.fact import CandidateFact
from research.graph import FactGraph
from research.obligation import ObligationRegistry
from research.pipeline import VerificationResult
from research.problem import ProblemSpec
from research.scaffold import (
    ProofScaffold,
    ScaffoldNode,
    advance_scaffold_once,
    ready_nodes,
    solve_scaffold,
)


class RecordingEchoWorker:
    """Proves whichever goal it is handed and records execution order."""

    def __init__(self) -> None:
        self.calls = 0
        self.goals = []

    def propose(self, *, problem, existing_facts, subgoal):
        self.calls += 1
        goal = subgoal.split("Goal:\n", 1)[1]
        self.goals.append(goal)
        return CandidateFact(
            statement=goal,
            proof=f"Accepted proof of {goal}",
            predecessors=tuple(fact.fact_id for fact in existing_facts),
        )


class AcceptAllVerifier:
    def __init__(self) -> None:
        self.calls = 0

    def verify(self, problem, candidate, predecessors):
        self.calls += 1
        return VerificationResult(True, "accepted")


class LastReadyScheduler:
    def select(self, ready):
        return ready[-1] if ready else None


class DeferringScheduler:
    def select(self, ready):
        return None


def _make_diamond(root: Path):
    graph = FactGraph(root)
    problem = ProblemSpec("p", "Target T.")
    scaffold_path = root / "scaffold.json"
    scaffold = ProofScaffold.create(
        scaffold_path,
        problem=problem,
        target_node_id="target",
        nodes=(
            ScaffoldNode("left", "Left lemma."),
            ScaffoldNode("right", "Right lemma."),
            ScaffoldNode("target", problem.statement, depends_on=("left", "right")),
        ),
    )
    registry = ObligationRegistry(root / "obligations.json")
    return graph, problem, scaffold_path, scaffold, registry


def test_ready_nodes_returns_ready_set_in_deterministic_node_id_order() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        graph, problem, _, scaffold, registry = _make_diamond(root)
        worker = RecordingEchoWorker()
        verifier = AcceptAllVerifier()

        assert [node.node_id for node in ready_nodes(scaffold, registry)] == ["left", "right"]

        first = advance_scaffold_once(
            scaffold=scaffold,
            problem=problem,
            registry=registry,
            graph=graph,
            author="worker",
            worker=worker,
            verifier=verifier,
        )
        assert first.node_id == "left"
        assert [node.node_id for node in ready_nodes(scaffold, registry)] == ["right"]

        second = advance_scaffold_once(
            scaffold=scaffold,
            problem=problem,
            registry=registry,
            graph=graph,
            author="worker",
            worker=worker,
            verifier=verifier,
        )
        assert second.node_id == "right"
        assert [node.node_id for node in ready_nodes(scaffold, registry)] == ["target"]


def test_default_scheduler_executes_first_ready_node_in_sorted_order() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        graph, problem, _, scaffold, registry = _make_diamond(root)
        worker = RecordingEchoWorker()
        verifier = AcceptAllVerifier()

        result = solve_scaffold(
            scaffold=scaffold,
            problem=problem,
            registry=registry,
            graph=graph,
            author="worker",
            worker=worker,
            verifier=verifier,
        )

        assert result.status == "SOLVED"
        assert worker.goals == ["Left lemma.", "Right lemma.", "Target T."]


def test_injected_scheduler_changes_selection_without_touching_execution() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        graph, problem, _, scaffold, registry = _make_diamond(root)
        worker = RecordingEchoWorker()
        verifier = AcceptAllVerifier()

        result = solve_scaffold(
            scaffold=scaffold,
            problem=problem,
            registry=registry,
            graph=graph,
            author="worker",
            worker=worker,
            verifier=verifier,
            scheduler=LastReadyScheduler(),
        )

        assert result.status == "SOLVED"
        assert worker.goals == ["Right lemma.", "Left lemma.", "Target T."]
        assert scaffold.get("left").resolved_by_fact_id is not None
        assert scaffold.get("right").resolved_by_fact_id is not None
        assert scaffold.get("target").resolved_by_fact_id == result.target_fact_id
        assert len(registry.list()) == 3


def test_resolution_only_writes_resolved_by_fact_id() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        graph, problem, scaffold_path, scaffold, registry = _make_diamond(root)
        created = {node.node_id: node for node in scaffold.list_nodes()}
        worker = RecordingEchoWorker()
        verifier = AcceptAllVerifier()

        advance = advance_scaffold_once(
            scaffold=scaffold,
            problem=problem,
            registry=registry,
            graph=graph,
            author="worker",
            worker=worker,
            verifier=verifier,
        )
        assert advance.node_id == "left"

        reloaded = ProofScaffold(scaffold_path)
        for node in reloaded.list_nodes():
            before = asdict(created[node.node_id])
            after = asdict(node)
            before.pop("resolved_by_fact_id")
            after.pop("resolved_by_fact_id")
            assert before == after
        assert created["left"].resolved_by_fact_id is None
        assert reloaded.get("left").resolved_by_fact_id is not None
        assert reloaded.get("right").resolved_by_fact_id is None
        assert reloaded.get("target").resolved_by_fact_id is None


def test_scheduler_returning_none_blocks_without_executing() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        graph, problem, _, scaffold, registry = _make_diamond(root)
        worker = RecordingEchoWorker()
        verifier = AcceptAllVerifier()

        result = advance_scaffold_once(
            scaffold=scaffold,
            problem=problem,
            registry=registry,
            graph=graph,
            author="worker",
            worker=worker,
            verifier=verifier,
            scheduler=DeferringScheduler(),
        )

        assert result.status == "BLOCKED"
        assert result.node_id is None
        assert result.execution is None
        assert worker.calls == verifier.calls == 0
        assert len(registry.list()) == 0
