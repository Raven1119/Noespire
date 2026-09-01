from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

from research.fact import CandidateFact, Fact
from research.graph import FactGraph
from research.obligation import ObligationRegistry
from research.pipeline import VerificationResult
from research.problem import ProblemSpec
from research.scaffold_architect import (
    ArchitectConfig,
    ScaffoldArchitect,
    ScaffoldProposal,
    ScaffoldProposalNode,
    StaticScaffoldStatus,
    run_static_scaffold_once,
)


class ScriptedArchitect:
    def __init__(self, proposal: ScaffoldProposal) -> None:
        self.proposal = proposal
        self.calls = 0

    def propose(self, *, problem, allowed_facts, config):
        self.calls += 1
        return self.proposal


class RaisingArchitect:
    def __init__(self) -> None:
        self.calls = 0

    def propose(self, *, problem, allowed_facts, config):
        self.calls += 1
        raise TimeoutError("architect timed out")


class ScriptedWorker:
    def __init__(self, goals: tuple[str, ...]) -> None:
        self.goals = list(goals)
        self.calls = 0

    def propose(self, *, problem, existing_facts, subgoal):
        goal = self.goals[self.calls]
        self.calls += 1
        return CandidateFact(
            statement=goal,
            proof=f"Proof of {goal}",
            predecessors=tuple(fact.fact_id for fact in existing_facts),
        )


class ScriptedVerifier:
    def __init__(self, verdicts: tuple[bool, ...]) -> None:
        self.verdicts = list(verdicts)
        self.calls = 0

    def verify(self, problem, candidate, predecessors):
        accepted = self.verdicts[self.calls]
        self.calls += 1
        return VerificationResult(accepted, "scripted verdict")


class RecordingCodex:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls = []

    def invoke(self, *, prompt, schema, label):
        self.calls.append((prompt, schema, label))
        return self.response


def test_architect_prompt_requests_decomposition_and_omits_fact_proofs() -> None:
    accepted = Fact.create(
        problem_id="p",
        author="verifier",
        statement="Allowed premise A.",
        proof="SECRET_PROOF_MUST_NOT_APPEAR",
    )
    codex = RecordingCodex(
        {
            "nodes": [
                {
                    "node_id": "lemma",
                    "goal": "Lemma H.",
                    "depends_on": [],
                    "premise_fact_ids": [accepted.fact_id],
                },
                {
                    "node_id": "target",
                    "goal": "Target T.",
                    "depends_on": ["lemma"],
                    "premise_fact_ids": [],
                },
            ],
            "target_node_id": "target",
        }
    )

    proposal = ScaffoldArchitect(codex).propose(
        problem=ProblemSpec("p", "Target T.", (accepted.fact_id,)),
        allowed_facts=(accepted,),
        config=ArchitectConfig(require_intermediate=True, max_nodes=4),
    )

    prompt, schema, label = codex.calls[0]
    assert proposal.target_node_id == "target"
    assert label == "scaffold_architect"
    assert "Your task is not to prove the theorem" in prompt
    assert accepted.fact_id in prompt
    assert accepted.statement in prompt
    assert "SECRET_PROOF_MUST_NOT_APPEAR" not in prompt
    assert schema["properties"]["nodes"]["maxItems"] == 4
    assert schema["additionalProperties"] is False


def test_valid_linear_proposal_runs_through_existing_scaffold_executor() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        problem = ProblemSpec("p", "Target T.")
        architect = ScriptedArchitect(
            ScaffoldProposal(
                nodes=(
                    ScaffoldProposalNode("n1", "Lemma H1."),
                    ScaffoldProposalNode("n2", "Lemma H2.", depends_on=("n1",)),
                    ScaffoldProposalNode("target", "Target T.", depends_on=("n2",)),
                ),
                target_node_id="target",
            )
        )
        worker = ScriptedWorker(("Lemma H1.", "Lemma H2.", "Target T."))
        verifier = ScriptedVerifier((True, True, True))
        graph = FactGraph(root)

        result = run_static_scaffold_once(
            scaffold_path=root / "scaffold.json",
            problem=problem,
            allowed_facts=(),
            config=ArchitectConfig(require_intermediate=True, max_nodes=6),
            graph=graph,
            registry=ObligationRegistry(root / "obligations.json"),
            architect=architect,
            author="worker",
            worker=worker,
            verifier=verifier,
        )

        assert result.status is StaticScaffoldStatus.SOLVED
        assert architect.calls == 1
        assert worker.calls == verifier.calls == 3
        assert tuple(fact.statement for fact in graph.supporting_closure(result.target_fact_id)) == (
            "Lemma H1.",
            "Lemma H2.",
            "Target T.",
        )


def test_valid_diamond_waits_for_both_architected_siblings() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        problem = ProblemSpec("p", "Target T.")
        architect = ScriptedArchitect(
            ScaffoldProposal(
                nodes=(
                    ScaffoldProposalNode("left", "Left lemma."),
                    ScaffoldProposalNode("right", "Right lemma."),
                    ScaffoldProposalNode(
                        "target",
                        "Target T.",
                        depends_on=("left", "right"),
                    ),
                ),
                target_node_id="target",
            )
        )
        graph = FactGraph(root)

        result = run_static_scaffold_once(
            scaffold_path=root / "scaffold.json",
            problem=problem,
            allowed_facts=(),
            config=ArchitectConfig(require_intermediate=True),
            graph=graph,
            registry=ObligationRegistry(root / "obligations.json"),
            architect=architect,
            author="worker",
            worker=ScriptedWorker(("Left lemma.", "Right lemma.", "Target T.")),
            verifier=ScriptedVerifier((True, True, True)),
        )

        assert result.status is StaticScaffoldStatus.SOLVED
        target = graph.get_fact(result.target_fact_id)
        assert target.predecessors == tuple(
            sorted(
                fact.fact_id
                for fact in graph.list_facts()
                if fact.statement in {"Left lemma.", "Right lemma."}
            )
        )


@pytest.mark.parametrize(
    "proposal,config,error_text",
    (
        (
            ScaffoldProposal(
                (
                    ScaffoldProposalNode("a", "Lemma A.", depends_on=("target",)),
                    ScaffoldProposalNode("target", "Target T.", depends_on=("a",)),
                ),
                "target",
            ),
            ArchitectConfig(require_intermediate=True),
            "cycle",
        ),
        (
            ScaffoldProposal(
                (
                    ScaffoldProposalNode("lemma", "Lemma H."),
                    ScaffoldProposalNode("target", "Weaker P.", depends_on=("lemma",)),
                ),
                "target",
            ),
            ArchitectConfig(require_intermediate=True),
            "target scaffold goal",
        ),
        (
            ScaffoldProposal(
                (
                    ScaffoldProposalNode("a", "Lemma A."),
                    ScaffoldProposalNode("b", "Lemma B."),
                    ScaffoldProposalNode("target", "Target T.", depends_on=("a", "b")),
                ),
                "target",
            ),
            ArchitectConfig(require_intermediate=True, max_nodes=2),
            "max_nodes",
        ),
        (
            ScaffoldProposal((ScaffoldProposalNode("target", "Target T."),), "target"),
            ArchitectConfig(require_intermediate=True),
            "intermediate",
        ),
        (
            ScaffoldProposal(
                (
                    ScaffoldProposalNode("a", "Target T."),
                    ScaffoldProposalNode("target", "Target T."),
                ),
                "target",
            ),
            ArchitectConfig(),
            "duplicate exact node",
        ),
        (
            ScaffoldProposal(
                (
                    ScaffoldProposalNode("target_copy", "Target T."),
                    ScaffoldProposalNode(
                        "target", "Target T.", depends_on=("target_copy",)
                    ),
                ),
                "target",
            ),
            ArchitectConfig(require_intermediate=True),
            "target theorem as an ancestor",
        ),
    ),
)
def test_invalid_architect_proposal_stops_before_truth_execution(
    proposal, config, error_text
) -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        graph = FactGraph(root)
        architect = ScriptedArchitect(proposal)
        worker = ScriptedWorker(())
        verifier = ScriptedVerifier(())

        result = run_static_scaffold_once(
            scaffold_path=root / "scaffold.json",
            problem=ProblemSpec("p", "Target T."),
            allowed_facts=(),
            config=config,
            graph=graph,
            registry=ObligationRegistry(root / "obligations.json"),
            architect=architect,
            author="worker",
            worker=worker,
            verifier=verifier,
        )

        assert result.status is StaticScaffoldStatus.ARCHITECT_INVALID
        assert error_text in result.error
        assert architect.calls == 1
        assert worker.calls == verifier.calls == 0
        assert graph.list_facts() == []
        assert not (root / "scaffold.json").exists()


def test_architect_cannot_reference_an_unexposed_fact_from_the_graph() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        graph = FactGraph(root)
        allowed = graph.add_fact(
            Fact.create(
                problem_id="p",
                author="seed",
                statement="Allowed A.",
                proof="Accepted premise.",
            )
        )
        hidden = graph.add_fact(
            Fact.create(
                problem_id="p",
                author="seed",
                statement="Hidden B.",
                proof="Accepted but not exposed.",
            )
        )
        architect = ScriptedArchitect(
            ScaffoldProposal(
                (
                    ScaffoldProposalNode(
                        "lemma",
                        "Lemma H.",
                        premise_fact_ids=(hidden.fact_id,),
                    ),
                    ScaffoldProposalNode("target", "Target T.", depends_on=("lemma",)),
                ),
                "target",
            )
        )
        worker = ScriptedWorker(())
        verifier = ScriptedVerifier(())

        result = run_static_scaffold_once(
            scaffold_path=root / "scaffold.json",
            problem=ProblemSpec("p", "Target T.", (allowed.fact_id,)),
            allowed_facts=(allowed,),
            config=ArchitectConfig(require_intermediate=True),
            graph=graph,
            registry=ObligationRegistry(root / "obligations.json"),
            architect=architect,
            author="worker",
            worker=worker,
            verifier=verifier,
        )

        assert result.status is StaticScaffoldStatus.ARCHITECT_INVALID
        assert "outside the allowed set" in result.error
        assert worker.calls == verifier.calls == 0
        assert {fact.fact_id for fact in graph.list_facts()} == {allowed.fact_id, hidden.fact_id}


def test_fake_allowed_fact_id_is_rejected_before_worker() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        fake = Fact("fake", "p", "seed", "Fake.", "Not stored.", ())
        worker = ScriptedWorker(())
        verifier = ScriptedVerifier(())
        result = run_static_scaffold_once(
            scaffold_path=root / "scaffold.json",
            problem=ProblemSpec("p", "Target T.", (fake.fact_id,)),
            allowed_facts=(fake,),
            config=ArchitectConfig(require_intermediate=True),
            graph=FactGraph(root),
            registry=ObligationRegistry(root / "obligations.json"),
            architect=ScriptedArchitect(
                ScaffoldProposal(
                    (
                        ScaffoldProposalNode(
                            "lemma", "Lemma H.", premise_fact_ids=(fake.fact_id,)
                        ),
                        ScaffoldProposalNode("target", "Target T.", depends_on=("lemma",)),
                    ),
                    "target",
                )
            ),
            author="worker",
            worker=worker,
            verifier=verifier,
        )

        assert result.status is StaticScaffoldStatus.ARCHITECT_INVALID
        assert "unknown fact" in result.error
        assert worker.calls == verifier.calls == 0


def test_architect_error_is_distinct_and_writes_no_fact() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        graph = FactGraph(root)
        architect = RaisingArchitect()
        worker = ScriptedWorker(())
        verifier = ScriptedVerifier(())

        result = run_static_scaffold_once(
            scaffold_path=root / "scaffold.json",
            problem=ProblemSpec("p", "Target T."),
            allowed_facts=(),
            config=ArchitectConfig(require_intermediate=True),
            graph=graph,
            registry=ObligationRegistry(root / "obligations.json"),
            architect=architect,
            author="worker",
            worker=worker,
            verifier=verifier,
        )

        assert result.status is StaticScaffoldStatus.ARCHITECT_ERROR
        assert result.error == "TimeoutError: architect timed out"
        assert architect.calls == 1
        assert worker.calls == verifier.calls == 0
        assert graph.list_facts() == []


def test_scaffold_materialization_error_is_a_system_error_not_invalid_proposal() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        scaffold_path = root / "scaffold.json"
        scaffold_path.write_text("occupied", encoding="utf-8")
        worker = ScriptedWorker(())
        verifier = ScriptedVerifier(())

        result = run_static_scaffold_once(
            scaffold_path=scaffold_path,
            problem=ProblemSpec("p", "Target T."),
            allowed_facts=(),
            config=ArchitectConfig(require_intermediate=True),
            graph=FactGraph(root),
            registry=ObligationRegistry(root / "obligations.json"),
            architect=ScriptedArchitect(
                ScaffoldProposal(
                    (
                        ScaffoldProposalNode("lemma", "Lemma H."),
                        ScaffoldProposalNode(
                            "target", "Target T.", depends_on=("lemma",)
                        ),
                    ),
                    "target",
                )
            ),
            author="worker",
            worker=worker,
            verifier=verifier,
        )

        assert result.status is StaticScaffoldStatus.SYSTEM_ERROR
        assert result.validated is not None
        assert "materialization failed" in result.error
        assert worker.calls == verifier.calls == 0


def test_execution_failure_preserves_prior_fact_without_replanning() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        graph = FactGraph(root)
        architect = ScriptedArchitect(
            ScaffoldProposal(
                (
                    ScaffoldProposalNode("lemma", "Lemma H."),
                    ScaffoldProposalNode("target", "Target T.", depends_on=("lemma",)),
                ),
                "target",
            )
        )
        worker = ScriptedWorker(("Lemma H.", "Target T."))
        verifier = ScriptedVerifier((True, False))

        result = run_static_scaffold_once(
            scaffold_path=root / "scaffold.json",
            problem=ProblemSpec("p", "Target T."),
            allowed_facts=(),
            config=ArchitectConfig(require_intermediate=True),
            graph=graph,
            registry=ObligationRegistry(root / "obligations.json"),
            architect=architect,
            author="worker",
            worker=worker,
            verifier=verifier,
        )

        assert result.status is StaticScaffoldStatus.EXECUTION_BLOCKED
        assert architect.calls == 1
        assert worker.calls == verifier.calls == 2
        assert [fact.statement for fact in graph.list_facts()] == ["Lemma H."]
        assert result.execution.advances[-1].node_id == "target"
