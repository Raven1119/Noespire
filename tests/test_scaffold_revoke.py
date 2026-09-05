"""§12 revoke/consistency checks: a revoked resolved Fact must not keep being
treated as valid resolved truth. The system fails closed (KeyError) — no
dynamic graph refinement is introduced here.
"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from application.problem_index import ProblemIndex
from application.proof_execution import STATIC_SCAFFOLD, is_problem_solved
from application.workspace_read_model import build_problem_list, build_read_model
from research.fact import CandidateFact, Fact
from research.graph import FactGraph
from research.obligation import ObligationRegistry
from research.pipeline import VerificationResult
from research.problem import ProblemSpec
from research.scaffold import ProofScaffold, ScaffoldNode, solve_scaffold


class _GoalEchoWorker:
    """Echoes the node's goal; solve order is lemma then target."""

    def __init__(self, goals):
        self._goals = list(goals)

    def propose(self, *, problem, existing_facts, subgoal):
        goal = self._goals.pop(0)
        return CandidateFact(
            statement=goal,
            proof=f"Accepted proof of {goal}",
            predecessors=tuple(fact.fact_id for fact in existing_facts),
        )


class _AcceptAllVerifier:
    def verify(self, problem, candidate, predecessors):
        return VerificationResult(True, "accepted")


def _solved_workspace(root: Path, problem_id: str = "p"):
    """Build a lemma→target scaffold workspace and solve it with fakes."""
    problem_dir = root / problem_id
    problem_dir.mkdir(parents=True, exist_ok=True)
    graph = FactGraph(problem_dir)
    problem = ProblemSpec(problem_id, "Target T.")
    scaffold = ProofScaffold.create(
        problem_dir / "scaffold.json",
        problem=problem,
        target_node_id="target",
        nodes=(
            ScaffoldNode("lemma", "Lemma L."),
            ScaffoldNode("target", "Target T.", depends_on=("lemma",)),
        ),
    )
    registry = ObligationRegistry(problem_dir / "obligations.json")
    result = solve_scaffold(
        scaffold=scaffold,
        problem=problem,
        registry=registry,
        graph=graph,
        author="worker",
        worker=_GoalEchoWorker(["Lemma L.", "Target T."]),
        verifier=_AcceptAllVerifier(),
    )
    assert result.status == "SOLVED"
    lemma_id = scaffold.get("lemma").resolved_by_fact_id
    target_id = scaffold.get("target").resolved_by_fact_id
    return problem_dir, graph, problem, lemma_id, target_id


def test_revoke_of_lemma_cascades_to_target_and_preserves_history() -> None:
    with TemporaryDirectory() as directory:
        problem_dir, graph, _, lemma_id, target_id = _solved_workspace(Path(directory))

        revoked = graph.revoke(lemma_id, "post-hoc audit: lemma proof flawed")

        assert revoked == [lemma_id, target_id]
        assert (problem_dir / "_revoked" / f"{lemma_id}.md").is_file()
        assert (problem_dir / "_revoked" / f"{target_id}.md").is_file()
        log = [
            json.loads(line)
            for line in (problem_dir / "revocation_log.jsonl")
            .read_text(encoding="utf-8")
            .splitlines()
        ]
        assert [(r["fact_id"], r["revoked_as_dependent_of"]) for r in log] == [
            (lemma_id, None),
            (target_id, lemma_id),
        ]


def test_revoked_fact_cannot_support_new_fact_and_vanishes_from_reads() -> None:
    with TemporaryDirectory() as directory:
        _, graph, _, lemma_id, target_id = _solved_workspace(Path(directory))
        graph.revoke(lemma_id, "audit")

        with pytest.raises(ValueError, match="predecessor_revoked"):
            graph.add_fact(
                Fact.create(
                    problem_id="p",
                    author="worker",
                    statement="New claim.",
                    proof="...",
                    predecessors=(lemma_id,),
                )
            )
        with pytest.raises(KeyError):
            graph.get_fact(target_id)
        assert graph.list_facts() == []


def test_solved_check_fails_closed_after_revoke() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        problem_dir, graph, _, lemma_id, _ = _solved_workspace(root)
        assert is_problem_solved(problem_dir, "p", STATIC_SCAFFOLD) is True

        graph.revoke(lemma_id, "audit")

        with pytest.raises(KeyError):
            is_problem_solved(problem_dir, "p", STATIC_SCAFFOLD)


def test_resume_fails_closed_after_revoke() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        problem_dir, graph, problem, lemma_id, _ = _solved_workspace(root)
        graph.revoke(lemma_id, "audit")

        with pytest.raises(KeyError):
            solve_scaffold(
                scaffold=ProofScaffold(problem_dir / "scaffold.json"),
                problem=problem,
                registry=ObligationRegistry(problem_dir / "obligations.json"),
                graph=FactGraph(problem_dir),
                author="worker",
                worker=_GoalEchoWorker([]),
                verifier=_AcceptAllVerifier(),
            )


def test_read_model_fails_closed_after_revoke() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        entry = ProblemIndex(root).add("Target T.")
        problem_dir, graph, _, lemma_id, _ = _solved_workspace(root, entry.problem_id)
        assert build_read_model(root, entry.problem_id)["status"] == "SOLVED"
        assert build_problem_list(root)[0]["status"] == "SOLVED"

        graph.revoke(lemma_id, "audit")

        with pytest.raises(KeyError):
            build_read_model(root, entry.problem_id)
        with pytest.raises(KeyError):
            build_problem_list(root)
