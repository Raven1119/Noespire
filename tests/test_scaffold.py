from pathlib import Path
from tempfile import TemporaryDirectory

import json
import pytest

from research.fact import CandidateFact, Fact
from research.graph import FactGraph
from research.obligation import ObligationRegistry, ObligationStatus, ProofObligation
from research.pipeline import VerificationResult
from research.problem import ProblemSpec
from research.scaffold import (
    ProofScaffold,
    ScaffoldNode,
    advance_scaffold_once,
    solve_scaffold,
)


class ScriptedScaffoldWorker:
    def __init__(self, goals: tuple[str, ...]) -> None:
        self.goals = list(goals)
        self.calls = 0

    def propose(self, *, problem, existing_facts, subgoal):
        goal = self.goals[self.calls]
        self.calls += 1
        return CandidateFact(
            statement=goal,
            proof=f"Accepted proof of {goal}",
            predecessors=tuple(fact.fact_id for fact in existing_facts),
        )


class RaisingScaffoldWorker:
    def __init__(self) -> None:
        self.calls = 0

    def propose(self, *, problem, existing_facts, subgoal):
        self.calls += 1
        raise RuntimeError("scripted worker crash")


class ScriptedScaffoldVerifier:
    def __init__(self, verdicts: tuple[bool, ...]) -> None:
        self.verdicts = list(verdicts)
        self.calls = 0

    def verify(self, problem, candidate, predecessors):
        accepted = self.verdicts[self.calls]
        self.calls += 1
        return VerificationResult(accepted, "scripted verdict")


def test_linear_chain_executes_three_distinct_obligations_and_returns_closure() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        graph = FactGraph(root)
        base = graph.add_fact(
            Fact.create(
                problem_id="p",
                author="seed",
                statement="Base F0.",
                proof="Verified base proof.",
            )
        )
        problem = ProblemSpec("p", "Target T.", (base.fact_id,))
        scaffold = ProofScaffold.create(
            root / "scaffold.json",
            problem=problem,
            target_node_id="target",
            nodes=(
                ScaffoldNode("n1", "Intermediate H1.", premise_fact_ids=(base.fact_id,)),
                ScaffoldNode("n2", "Intermediate H2.", depends_on=("n1",)),
                ScaffoldNode("target", problem.statement, depends_on=("n2",)),
            ),
        )
        registry = ObligationRegistry(root / "obligations.json")
        worker = ScriptedScaffoldWorker(("Intermediate H1.", "Intermediate H2.", "Target T."))
        verifier = ScriptedScaffoldVerifier((True, True, True))

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
        assert worker.calls == 3
        assert verifier.calls == 3
        assert len(registry.list()) == 3
        assert tuple(fact.statement for fact in graph.supporting_closure(result.target_fact_id)) == (
            "Base F0.",
            "Intermediate H1.",
            "Intermediate H2.",
            "Target T.",
        )
        attempts = sorted((root / "attempts").glob("attempt-*.json"))
        assert [json.loads(path.read_text(encoding="utf-8"))["verdict"] for path in attempts] == [
            "PASS",
            "PASS",
            "PASS",
        ]
        assert [advance.attempt_id for advance in result.advances] == [
            "attempt-000001",
            "attempt-000002",
            "attempt-000003",
        ]


def test_diamond_unlocks_target_only_after_both_predecessors_are_facts() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        graph = FactGraph(root)
        problem = ProblemSpec("p", "Target T.")
        scaffold = ProofScaffold.create(
            root / "scaffold.json",
            problem=problem,
            target_node_id="target",
            nodes=(
                ScaffoldNode("left", "Left lemma."),
                ScaffoldNode("right", "Right lemma."),
                ScaffoldNode("target", problem.statement, depends_on=("left", "right")),
            ),
        )
        registry = ObligationRegistry(root / "obligations.json")
        worker = ScriptedScaffoldWorker(("Left lemma.", "Right lemma.", "Target T."))
        verifier = ScriptedScaffoldVerifier((True, True, True))

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
        assert scaffold.get("target").resolved_by_fact_id is None
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
        assert scaffold.get("target").resolved_by_fact_id is None
        third = advance_scaffold_once(
            scaffold=scaffold,
            problem=problem,
            registry=registry,
            graph=graph,
            author="worker",
            worker=worker,
            verifier=verifier,
        )

        assert third.status == "SOLVED"
        target = graph.get_fact(third.target_fact_id)
        assert target.predecessors == tuple(
            sorted(
                (
                    scaffold.get("left").resolved_by_fact_id,
                    scaffold.get("right").resolved_by_fact_id,
                )
            )
        )


def test_failed_upstream_node_stops_run_and_keeps_downstream_locked() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        graph = FactGraph(root)
        problem = ProblemSpec("p", "Target T.")
        scaffold = ProofScaffold.create(
            root / "scaffold.json",
            problem=problem,
            target_node_id="target",
            nodes=(
                ScaffoldNode("n1", "Accepted H1."),
                ScaffoldNode("n2", "Rejected H2.", depends_on=("n1",)),
                ScaffoldNode("target", problem.statement, depends_on=("n2",)),
            ),
        )
        registry = ObligationRegistry(root / "obligations.json")
        worker = ScriptedScaffoldWorker(("Accepted H1.", "Rejected H2."))
        verifier = ScriptedScaffoldVerifier((True, False))

        result = solve_scaffold(
            scaffold=scaffold,
            problem=problem,
            registry=registry,
            graph=graph,
            author="worker",
            worker=worker,
            verifier=verifier,
        )

        assert result.status == "BLOCKED"
        assert worker.calls == verifier.calls == 2
        assert scaffold.get("n1").resolved_by_fact_id is not None
        assert scaffold.get("n2").resolved_by_fact_id is None
        assert scaffold.get("target").resolved_by_fact_id is None
        assert [fact.statement for fact in graph.list_facts()] == ["Accepted H1."]
        assert len(registry.list()) == 2


def test_reload_preserves_success_and_explicit_later_call_retries_only_failed_node() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        graph = FactGraph(root)
        problem = ProblemSpec("p", "Target T.")
        scaffold_path = root / "scaffold.json"
        scaffold = ProofScaffold.create(
            scaffold_path,
            problem=problem,
            target_node_id="target",
            nodes=(
                ScaffoldNode("n1", "Accepted H1."),
                ScaffoldNode("n2", "Retry H2.", depends_on=("n1",)),
                ScaffoldNode("target", problem.statement, depends_on=("n2",)),
            ),
        )
        registry_path = root / "obligations.json"
        first_worker = ScriptedScaffoldWorker(("Accepted H1.", "Retry H2."))
        first_verifier = ScriptedScaffoldVerifier((True, False))
        first = solve_scaffold(
            scaffold=scaffold,
            problem=problem,
            registry=ObligationRegistry(registry_path),
            graph=graph,
            author="worker",
            worker=first_worker,
            verifier=first_verifier,
        )
        assert first.status == "BLOCKED"

        resumed = ProofScaffold(scaffold_path)
        second_worker = ScriptedScaffoldWorker(("Retry H2.", "Target T."))
        second_verifier = ScriptedScaffoldVerifier((True, True))
        second = solve_scaffold(
            scaffold=resumed,
            problem=problem,
            registry=ObligationRegistry(registry_path),
            graph=FactGraph(root),
            author="worker",
            worker=second_worker,
            verifier=second_verifier,
        )

        assert second.status == "SOLVED"
        assert second_worker.calls == second_verifier.calls == 2
        assert resumed.get("n1").resolved_by_fact_id == scaffold.get("n1").resolved_by_fact_id
        no_op_worker = ScriptedScaffoldWorker(())
        no_op_verifier = ScriptedScaffoldVerifier(())
        no_op = solve_scaffold(
            scaffold=ProofScaffold(scaffold_path),
            problem=problem,
            registry=ObligationRegistry(registry_path),
            graph=FactGraph(root),
            author="worker",
            worker=no_op_worker,
            verifier=no_op_verifier,
        )
        assert no_op.status == "SOLVED"
        assert no_op_worker.calls == no_op_verifier.calls == 0


def test_resume_reconciles_a_discharged_obligation_without_rerunning_worker() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        graph = FactGraph(root)
        problem = ProblemSpec("p", "Target.")
        scaffold = ProofScaffold.create(
            root / "scaffold.json",
            problem=problem,
            target_node_id="target",
            nodes=(ScaffoldNode("target", "Target."),),
        )
        registry = ObligationRegistry(root / "obligations.json")
        obligation = registry.add(
            ProofObligation("scaffold:p:target", (), "Target.", "scaffold:target")
        )
        registry.transition(obligation.obligation_id, ObligationStatus.RUNNING)
        fact = graph.add_fact(
            Fact.create(
                problem_id="p",
                author="prior worker",
                statement="Target.",
                proof="Previously accepted proof.",
            )
        )
        registry.resolve(obligation.obligation_id, fact.fact_id, graph)
        worker = ScriptedScaffoldWorker(())
        verifier = ScriptedScaffoldVerifier(())

        result = advance_scaffold_once(
            scaffold=scaffold,
            problem=problem,
            registry=registry,
            graph=graph,
            author="worker",
            worker=worker,
            verifier=verifier,
        )

        assert result.status == "SOLVED"
        assert result.execution.executed is False
        assert result.attempt_id is None
        assert scaffold.get("target").resolved_by_fact_id == fact.fact_id
        assert worker.calls == verifier.calls == 0


@pytest.mark.parametrize(
    "nodes,target",
    (
        ((ScaffoldNode("n", "N.", depends_on=("n",)),), "n"),
        ((ScaffoldNode("n", "N.", depends_on=("missing",)),), "n"),
        (
            (
                ScaffoldNode("a", "A.", depends_on=("b",)),
                ScaffoldNode("b", "B.", depends_on=("a",)),
            ),
            "a",
        ),
        ((ScaffoldNode("n", "N."), ScaffoldNode("n", "N again.")), "n"),
        ((ScaffoldNode("n", "N."),), "missing"),
    ),
)
def test_invalid_scaffold_is_rejected_mechanically(nodes, target) -> None:
    with TemporaryDirectory() as directory:
        with pytest.raises(ValueError):
            ProofScaffold.create(
                Path(directory) / "scaffold.json",
                problem=ProblemSpec("p", "N."),
                target_node_id=target,
                nodes=nodes,
            )
        assert not (Path(directory) / "scaffold.json").exists()


def test_unknown_base_fact_is_rejected_before_worker_call() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        problem = ProblemSpec("p", "Target.", ("missing-fact",))
        scaffold = ProofScaffold.create(
            root / "scaffold.json",
            problem=problem,
            target_node_id="target",
            nodes=(ScaffoldNode("target", "Target.", premise_fact_ids=("missing-fact",)),),
        )
        worker = ScriptedScaffoldWorker(("Target.",))
        verifier = ScriptedScaffoldVerifier((True,))

        with pytest.raises(KeyError):
            advance_scaffold_once(
                scaffold=scaffold,
                problem=problem,
                registry=ObligationRegistry(root / "obligations.json"),
                graph=FactGraph(root),
                author="worker",
                worker=worker,
                verifier=verifier,
            )

        assert worker.calls == verifier.calls == 0


def test_new_scaffold_cannot_claim_a_pre_resolved_node() -> None:
    with TemporaryDirectory() as directory:
        with pytest.raises(ValueError, match="pre-resolved"):
            ProofScaffold.create(
                Path(directory) / "scaffold.json",
                problem=ProblemSpec("p", "Target."),
                target_node_id="target",
                nodes=(
                    ScaffoldNode(
                        "target",
                        "Target.",
                        resolved_by_fact_id="unvalidated-fact",
                    ),
                ),
            )


def test_tampered_resolution_with_wrong_predecessors_is_rejected_before_worker() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        graph = FactGraph(root)
        problem = ProblemSpec("p", "Target.")
        scaffold_path = root / "scaffold.json"
        ProofScaffold.create(
            scaffold_path,
            problem=problem,
            target_node_id="target",
            nodes=(
                ScaffoldNode("lemma", "Lemma."),
                ScaffoldNode("target", "Target.", depends_on=("lemma",)),
            ),
        )
        direct_target = graph.add_fact(
            Fact.create(
                problem_id="p",
                author="unrelated worker",
                statement="Target.",
                proof="A direct proof that bypasses the declared lemma.",
            )
        )
        payload = json.loads(scaffold_path.read_text(encoding="utf-8"))
        target = next(node for node in payload["nodes"] if node["node_id"] == "target")
        target["resolved_by_fact_id"] = direct_target.fact_id
        scaffold_path.write_text(json.dumps(payload), encoding="utf-8")
        worker = ScriptedScaffoldWorker(("Lemma.",))
        verifier = ScriptedScaffoldVerifier((True,))

        with pytest.raises(ValueError, match="dependencies|predecessors"):
            advance_scaffold_once(
                scaffold=ProofScaffold(scaffold_path),
                problem=problem,
                registry=ObligationRegistry(root / "obligations.json"),
                graph=graph,
                author="worker",
                worker=worker,
                verifier=verifier,
            )

        assert worker.calls == verifier.calls == 0


def test_worker_exception_records_error_and_reopens_node_for_explicit_retry() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        problem = ProblemSpec("p", "Target.")
        scaffold = ProofScaffold.create(
            root / "scaffold.json",
            problem=problem,
            target_node_id="target",
            nodes=(ScaffoldNode("target", "Target."),),
        )
        registry = ObligationRegistry(root / "obligations.json")
        worker = RaisingScaffoldWorker()

        with pytest.raises(RuntimeError, match="scripted worker crash"):
            advance_scaffold_once(
                scaffold=scaffold,
                problem=problem,
                registry=registry,
                graph=FactGraph(root),
                author="worker",
                worker=worker,
                verifier=ScriptedScaffoldVerifier((True,)),
            )

        assert registry.get("scaffold:p:target").status.value == "OPEN"
        artifact = json.loads(
            (root / "attempts" / "attempt-000001.json").read_text(encoding="utf-8")
        )
        assert artifact["verdict"] == "ERROR"
        assert artifact["error"] == "scripted worker crash"
