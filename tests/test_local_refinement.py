"""N2A — failure-conditioned local redecomposition (audited SPLIT only).

Deterministic tests over stub builder/auditor objects: no Codex, no network,
no Docker. Covers the ``ScaffoldNode.superseded_by`` scheduling exclusion, the
split-proposal parse/normalization contract, the mechanical admission checks,
the history-preserving ``apply_split`` patch, and the
``run_local_redecomposition`` outcome ladder — including that the frozen
NodeSolver/executor path is untouched (children execute through it) and the
FactGraph truth boundary is never crossed (zero facts admitted).
"""

from pathlib import Path
from tempfile import TemporaryDirectory

import json

import pytest

from research.fact import CandidateFact
from research.graph import FactGraph
from research.obligation import ObligationRegistry, ProofObligation
from research.pipeline import VerificationResult
from research.problem import ProblemSpec
from research.scaffold import ProofScaffold, ScaffoldNode, ready_nodes, solve_scaffold


PROBLEM_STATEMENT = "Target theorem T."
BLOCKED_GOAL = "Intermediate lemma M."


class GoalEchoWorker:
    """Echoes the subgoal's ``Goal:\\n<text>`` tail back as the candidate."""

    def __init__(self) -> None:
        self.calls = 0
        self.goals = []

    def propose(self, *, problem, existing_facts, subgoal, repair_context=None):
        self.calls += 1
        goal = subgoal.split("Goal:\n", 1)[1]
        self.goals.append(goal)
        return CandidateFact(
            goal,
            f"A candidate proof of {goal}",
            tuple(fact.fact_id for fact in existing_facts),
        )


class RejectingVerifier:
    def __init__(self, rejected=()) -> None:
        self.rejected = set(rejected)
        self.calls = 0

    def verify(self, problem, candidate, predecessors):
        self.calls += 1
        return VerificationResult(
            candidate.statement not in self.rejected, "scripted verdict"
        )


def scaffold_nodes() -> tuple[ScaffoldNode, ...]:
    return (
        ScaffoldNode("n1", "Base lemma B."),
        ScaffoldNode("mid", BLOCKED_GOAL, depends_on=("n1",)),
        ScaffoldNode("target", PROBLEM_STATEMENT, depends_on=("mid",)),
    )


def make_workspace(root: Path) -> ProofScaffold:
    """Scaffold n1 -> mid -> target; run until mid blocks (verifier rejects it).

    Leaves on disk: n1 resolved (one admitted Fact), mid open with one FAIL
    attempt artifact, target never executed.
    """
    problem = ProblemSpec("p", PROBLEM_STATEMENT)
    scaffold = ProofScaffold.create(
        root / "scaffold.json",
        problem=problem,
        target_node_id="target",
        nodes=scaffold_nodes(),
    )
    result = solve_scaffold(
        scaffold=scaffold,
        problem=problem,
        registry=ObligationRegistry(root / "obligations.json"),
        graph=FactGraph(root),
        author="worker",
        worker=GoalEchoWorker(),
        verifier=RejectingVerifier({BLOCKED_GOAL}),
    )
    assert result.status == "BLOCKED"
    return ProofScaffold(root / "scaffold.json")


def test_ready_nodes_excludes_superseded_nodes() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        scaffold = make_workspace(root)
        registry = ObligationRegistry(root / "obligations.json")

        ready_before = [node.node_id for node in ready_nodes(scaffold, registry)]
        assert ready_before == ["mid"]

        payload = json.loads((root / "scaffold.json").read_text(encoding="utf-8"))
        for item in payload["nodes"]:
            if item["node_id"] == "mid":
                item["superseded_by"] = "split-test"
        (root / "scaffold.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        reloaded = ProofScaffold(root / "scaffold.json")
        assert reloaded.get("mid").superseded_by == "split-test"
        assert reloaded.get("mid").resolved_by_fact_id is None
        assert ready_nodes(reloaded, registry) == []


def test_scaffold_json_without_superseded_by_still_loads() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        scaffold = make_workspace(root)
        payload = json.loads((root / "scaffold.json").read_text(encoding="utf-8"))
        for item in payload["nodes"]:
            item.pop("superseded_by", None)
        (root / "scaffold.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        reloaded = ProofScaffold(root / "scaffold.json")
        assert [node.node_id for node in reloaded.list_nodes()] == ["mid", "n1", "target"]
        assert all(node.superseded_by is None for node in reloaded.list_nodes())
        registry = ObligationRegistry(root / "obligations.json")
        assert [node.node_id for node in ready_nodes(reloaded, registry)] == ["mid"]


from research.local_refinement import (  # noqa: E402
    AuditorResult,
    BuilderResult,
    RedecompositionResult,
    SplitProposal,
    parse_auditor_output,
    parse_builder_output,
    run_local_redecomposition,
    validate_split_proposal,
)


VALID_CHILDREN = (
    {"node_id": "mid-a", "goal": "Part one of M.", "depends_on": [], "premise_fact_ids": []},
    {
        "node_id": "mid-b",
        "goal": "Part two of M.",
        "depends_on": ["mid-a"],
        "premise_fact_ids": [],
    },
)


def split_raw(children=VALID_CHILDREN, obstruction="Both halves failed jointly.", effect="Each half is provable alone.") -> str:
    return json.dumps(
        {
            "outcome": "SPLIT",
            "obstruction": obstruction,
            "expected_effect": effect,
            "new_nodes": list(children),
            "missing_context": "",
        }
    )


class StubBuilder:
    def __init__(self, result: BuilderResult) -> None:
        self.result = result
        self.contexts = []

    def propose(self, context, *, effort=None, timeout=None):
        self.contexts.append(context)
        return self.result


class RaisingBuilder:
    def __init__(self) -> None:
        self.calls = 0

    def propose(self, context, *, effort=None, timeout=None):
        self.calls += 1
        raise RuntimeError("scripted builder crash")


class StubAuditor:
    def __init__(self, result: AuditorResult) -> None:
        self.result = result
        self.calls = []

    def audit(self, context, proposal, *, effort=None, timeout=None):
        self.calls.append((context, proposal))
        return self.result


class RaisingAuditor:
    def __init__(self) -> None:
        self.calls = 0

    def audit(self, context, proposal, *, effort=None, timeout=None):
        self.calls += 1
        raise RuntimeError("scripted auditor crash")


def passing_auditor() -> StubAuditor:
    return StubAuditor(AuditorResult(verdict="PASS", reasons=("looks sound",)))


def split_builder(children=VALID_CHILDREN) -> StubBuilder:
    return StubBuilder(parse_builder_output(split_raw(children), blocked_node_id="mid"))


def scaffold_text(root: Path) -> str:
    return (root / "scaffold.json").read_text(encoding="utf-8")


def attempt_snapshots(root: Path) -> dict:
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted((root / "attempts").glob("attempt-*.json"))
    }


def evidence_files(root: Path) -> list:
    directory = root / "local_refinements"
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.json"))


# --- parse_builder_output / parse_auditor_output ---------------------------


def test_parse_builder_output_extracts_json_from_prose_and_fences() -> None:
    raw = (
        "Here is my decomposition rationale (not part of the output).\n"
        "```json\n" + split_raw() + "\n```\nHope this helps."
    )
    result = parse_builder_output(raw, blocked_node_id="mid")

    assert result.outcome == "SPLIT"
    assert result.raw == raw
    proposal = result.proposal
    assert proposal is not None
    assert proposal.blocked_node_id == "mid"
    assert proposal.proposal_id.startswith("split-")
    assert proposal.obstruction == "Both halves failed jointly."
    assert proposal.expected_effect == "Each half is provable alone."
    assert [child.node_id for child in proposal.children] == ["mid-a", "mid-b"]
    assert proposal.children[1].depends_on == ("mid-a",)


def test_parse_builder_output_proposal_id_is_deterministic() -> None:
    first = parse_builder_output(split_raw(), blocked_node_id="mid")
    second = parse_builder_output(split_raw(), blocked_node_id="mid")
    assert first.proposal.proposal_id == second.proposal.proposal_id


def test_parse_builder_output_malformed_json_is_error_with_raw_retained() -> None:
    result = parse_builder_output("no json here at all")
    assert result.outcome == "ERROR"
    assert result.proposal is None
    assert result.raw == "no json here at all"

    broken = parse_builder_output('{"outcome": "SPLIT", "new_nodes": [')
    assert broken.outcome == "ERROR"


def test_parse_builder_output_unknown_outcome_is_error() -> None:
    result = parse_builder_output(json.dumps({"outcome": "MERGE"}))
    assert result.outcome == "ERROR"


def test_parse_builder_output_non_split_outcomes() -> None:
    result = parse_builder_output(
        json.dumps({"outcome": "NEED_MORE_CONTEXT", "missing_context": "need lemma X"})
    )
    assert result.outcome == "NEED_MORE_CONTEXT"
    assert result.missing_context == "need lemma X"
    assert result.proposal is None


def test_parse_auditor_output_verdicts_reasons_and_checks() -> None:
    raw = json.dumps(
        {
            "verdict": "REVISE",
            "reasons": ["child two restates the blocked goal"],
            "checks": {"target_preserved": True, "children_are_genuinely_narrower": False},
        }
    )
    result = parse_auditor_output(raw)
    assert result.verdict == "REVISE"
    assert result.reasons == ("child two restates the blocked goal",)
    assert result.checks["children_are_genuinely_narrower"] is False

    assert parse_auditor_output(json.dumps({"verdict": "PASS"})).verdict == "PASS"
    assert parse_auditor_output(json.dumps({"verdict": "REJECT"})).verdict == "REJECT"


def test_parse_auditor_output_malformed_or_unknown_is_error() -> None:
    assert parse_auditor_output("not json").verdict == "ERROR"
    assert parse_auditor_output(json.dumps({"verdict": "MAYBE"})).verdict == "ERROR"


# --- validate_split_proposal (mechanical admission) -------------------------


def make_proposal(children=VALID_CHILDREN, blocked_node_id="mid") -> SplitProposal:
    return parse_builder_output(
        split_raw(children), blocked_node_id=blocked_node_id
    ).proposal


def validate(root: Path, proposal: SplitProposal, nodes=None) -> tuple:
    return validate_split_proposal(
        proposal=proposal,
        nodes=tuple(nodes) if nodes is not None else scaffold_nodes(),
        target_node_id="target",
        problem_id="p",
        problem_premise_fact_ids=(),
        obligations=ObligationRegistry(root / "obligations.json"),
    )


def test_valid_proposal_passes_all_mechanical_checks() -> None:
    with TemporaryDirectory() as directory:
        assert validate(Path(directory), make_proposal()) == ()


def test_blocked_node_must_exist_and_not_be_target() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        errors = validate(root, make_proposal(blocked_node_id="ghost"))
        assert any("unknown blocked node" in error for error in errors)
        errors = validate(root, make_proposal(blocked_node_id="target"))
        assert any("target" in error for error in errors)


def test_blocked_node_must_be_open_unresolved_and_not_superseded() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        resolved = ScaffoldNode("mid", BLOCKED_GOAL, depends_on=("n1",), resolved_by_fact_id="f0")
        superseded = ScaffoldNode("mid", BLOCKED_GOAL, depends_on=("n1",), superseded_by="split-old")
        parked = ScaffoldNode("mid", BLOCKED_GOAL, depends_on=("n1",), parked_by="alt-old")
        for node, fragment in (
            (resolved, "resolved"),
            (superseded, "superseded"),
            (parked, "parked"),
        ):
            nodes = (scaffold_nodes()[0], node, scaffold_nodes()[2])
            errors = validate(root, make_proposal(), nodes=nodes)
            assert any(fragment in error for error in errors), (fragment, errors)


def test_at_least_two_children_with_unique_non_colliding_ids() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        errors = validate(root, make_proposal(children=VALID_CHILDREN[:1]))
        assert any("at least two children" in error for error in errors)

        duplicate = (VALID_CHILDREN[0], dict(VALID_CHILDREN[0], goal="Different goal."))
        errors = validate(root, make_proposal(children=duplicate))
        assert any("duplicate child node_id" in error for error in errors)

        colliding = (VALID_CHILDREN[0], dict(VALID_CHILDREN[1], node_id="n1"))
        errors = validate(root, make_proposal(children=colliding))
        assert any("collides" in error for error in errors)


def test_child_goal_must_not_restate_blocked_target_or_existing_goal() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        for leaked in (
            BLOCKED_GOAL,
            "  intermediate   lemma m.",  # whitespace/case-normalized blocked goal
            PROBLEM_STATEMENT,
            "Base lemma B.",
        ):
            children = (dict(VALID_CHILDREN[0], goal=leaked), VALID_CHILDREN[1])
            errors = validate(root, make_proposal(children=children))
            assert any("restates" in error for error in errors), (leaked, errors)


def test_child_goal_must_be_a_proposition_not_an_instruction() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        children = (
            dict(VALID_CHILDREN[0], goal="Now finish the proof of the lemma."),
            VALID_CHILDREN[1],
        )
        errors = validate(root, make_proposal(children=children))
        assert any("instruction" in error for error in errors)


def test_children_are_self_contained_and_premises_are_declared() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        outside_dep = (dict(VALID_CHILDREN[0], depends_on=["n1"]), VALID_CHILDREN[1])
        errors = validate(root, make_proposal(children=outside_dep))
        assert any("non-child" in error for error in errors)

        foreign_premise = (dict(VALID_CHILDREN[0], premise_fact_ids=["fact-x"]), VALID_CHILDREN[1])
        errors = validate(root, make_proposal(children=foreign_premise))
        assert any("premise" in error for error in errors)


def test_cycle_among_children_is_rejected() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        cyclic = (
            dict(VALID_CHILDREN[0], depends_on=["mid-b"]),
            dict(VALID_CHILDREN[1], depends_on=["mid-a"]),
        )
        errors = validate(root, make_proposal(children=cyclic))
        assert any("cycle" in error for error in errors)


def test_executed_downstream_node_fails_closed() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        registry = ObligationRegistry(root / "obligations.json")
        registry.add(ProofObligation("scaffold:p:target", (), PROBLEM_STATEMENT, "scaffold:target"))
        errors = validate(root, make_proposal())
        assert any("already executed" in error for error in errors)


# --- run_local_redecomposition outcome ladder -------------------------------


def run(root: Path, builder, auditor) -> RedecompositionResult:
    return run_local_redecomposition(
        root,
        problem_id="p",
        blocked_node_id="mid",
        builder=builder,
        auditor=auditor,
    )


def test_no_useful_split_leaves_graph_unchanged_and_persists_evidence() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        before = scaffold_text(root)
        builder = StubBuilder(BuilderResult(outcome="NO_USEFUL_SPLIT", raw='{"outcome": "NO_USEFUL_SPLIT"}'))
        auditor = passing_auditor()

        result = run(root, builder, auditor)

        assert result.outcome == "NO_USEFUL_SPLIT"
        assert scaffold_text(root) == before
        assert auditor.calls == []
        (evidence,) = evidence_files(root)
        assert evidence.name.startswith("no-split-")
        payload = json.loads(evidence.read_text(encoding="utf-8"))
        assert payload["outcome"] == "NO_USEFUL_SPLIT"
        assert payload["applied"] is False
        assert payload["builder_raw"] == '{"outcome": "NO_USEFUL_SPLIT"}'
        assert payload["context"]["blocked_node"]["node_id"] == "mid"
        assert payload["context"]["attempts"][0]["verdict"] == "FAIL"
        assert FactGraph(root).list_facts()  # the n1 base fact only
        assert len(FactGraph(root).list_facts()) == 1


def test_need_more_context_leaves_graph_unchanged() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        before = scaffold_text(root)
        auditor = passing_auditor()

        result = run(
            root,
            StubBuilder(BuilderResult(outcome="NEED_MORE_CONTEXT", missing_context="need H0")),
            auditor,
        )

        assert result.outcome == "NEED_MORE_CONTEXT"
        assert scaffold_text(root) == before
        assert auditor.calls == []
        assert len(evidence_files(root)) == 1


def test_builder_error_leaves_graph_unchanged() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        before = scaffold_text(root)

        result = run(root, RaisingBuilder(), passing_auditor())

        assert result.outcome == "BUILDER_ERROR"
        assert scaffold_text(root) == before
        assert len(evidence_files(root)) == 1


def test_mechanically_invalid_split_is_rejected_before_the_auditor() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        before = scaffold_text(root)
        cyclic = (
            dict(VALID_CHILDREN[0], depends_on=["mid-b"]),
            dict(VALID_CHILDREN[1], depends_on=["mid-a"]),
        )
        auditor = passing_auditor()

        result = run(root, split_builder(cyclic), auditor)

        assert result.outcome == "MECHANICAL_REJECT"
        assert any("cycle" in error for error in result.mechanical_errors)
        assert scaffold_text(root) == before
        assert auditor.calls == []
        (evidence,) = evidence_files(root)
        payload = json.loads(evidence.read_text(encoding="utf-8"))
        assert payload["outcome"] == "MECHANICAL_REJECT"
        assert payload["applied"] is False
        assert payload["mechanical_errors"]


@pytest.mark.parametrize("verdict", ("REVISE", "REJECT"))
def test_auditor_revise_and_reject_leave_graph_unchanged(verdict: str) -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        before = scaffold_text(root)
        auditor = StubAuditor(AuditorResult(verdict=verdict, reasons=("not narrower",)))

        result = run(root, split_builder(), auditor)

        assert result.outcome == f"AUDITOR_{verdict}"
        assert scaffold_text(root) == before
        assert len(auditor.calls) == 1
        payload = json.loads(evidence_files(root)[0].read_text(encoding="utf-8"))
        assert payload["auditor_verdict"] == verdict
        assert payload["applied"] is False


def test_auditor_error_leaves_graph_unchanged() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        before = scaffold_text(root)

        result = run(root, split_builder(), RaisingAuditor())

        assert result.outcome == "AUDITOR_ERROR"
        assert scaffold_text(root) == before


def apply_valid_split(root: Path) -> RedecompositionResult:
    builder = split_builder()
    auditor = passing_auditor()
    result = run(root, builder, auditor)
    assert result.outcome == "APPLIED"
    return result


def test_accepted_split_creates_children_and_rewires_downstream_to_sinks() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)

        result = apply_valid_split(root)

        assert result.child_node_ids == ("mid-a", "mid-b")
        reloaded = ProofScaffold(root / "scaffold.json")
        superseded = reloaded.get("mid")
        assert superseded.superseded_by == result.proposal.proposal_id
        assert superseded.resolved_by_fact_id is None
        first = reloaded.get("mid-a")
        second = reloaded.get("mid-b")
        assert first.goal == "Part one of M."
        assert first.depends_on == ()
        assert first.resolved_by_fact_id is None
        assert second.depends_on == ("mid-a",)
        # Only the sink child (mid-b) replaces mid in the target's route.
        assert reloaded.get("target").depends_on == ("mid-b",)

        (evidence,) = evidence_files(root)
        assert evidence.name == f"{result.proposal.proposal_id}.json"
        payload = json.loads(evidence.read_text(encoding="utf-8"))
        assert payload["outcome"] == "APPLIED"
        assert payload["applied"] is True
        assert payload["auditor_verdict"] == "PASS"
        assert payload["mechanical_errors"] == []
        post_ids = {node["node_id"] for node in payload["post_patch_nodes"]}
        assert post_ids == {"n1", "mid", "mid-a", "mid-b", "target"}


def test_accepted_split_preserves_blocked_node_row_and_attempt_history() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        attempts_before = attempt_snapshots(root)

        result = apply_valid_split(root)

        reloaded = ProofScaffold(root / "scaffold.json")
        assert reloaded.get("mid").goal == BLOCKED_GOAL
        assert reloaded.get("mid").depends_on == ("n1",)
        assert attempt_snapshots(root) == attempts_before
        # The split itself admits no Facts and creates no obligations.
        assert len(FactGraph(root).list_facts()) == 1
        registry = ObligationRegistry(root / "obligations.json")
        assert [item.obligation_id for item in registry.list()] == [
            "scaffold:p:mid",
            "scaffold:p:n1",
        ]
        assert result.child_node_ids == ("mid-a", "mid-b")


def test_split_applies_exactly_once_per_blocked_node() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        first = apply_valid_split(root)
        after_first = scaffold_text(root)

        second = run(root, split_builder(), passing_auditor())

        assert second.outcome == "MECHANICAL_REJECT"
        assert any("superseded" in error for error in second.mechanical_errors)
        assert scaffold_text(root) == after_first
        assert first.proposal.proposal_id in scaffold_text(root)


def test_redecomposition_never_touches_the_fact_graph() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        facts_before = [fact.fact_id for fact in FactGraph(root).list_facts()]

        run(root, StubBuilder(BuilderResult(outcome="NO_USEFUL_SPLIT")), passing_auditor())
        apply_valid_split(root)

        assert [fact.fact_id for fact in FactGraph(root).list_facts()] == facts_before


# --- frozen execution path over the patched scaffold ------------------------


def test_children_execute_through_the_unchanged_scaffold_solver() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        apply_valid_split(root)

        worker = GoalEchoWorker()
        result = solve_scaffold(
            scaffold=ProofScaffold(root / "scaffold.json"),
            problem=ProblemSpec("p", PROBLEM_STATEMENT),
            registry=ObligationRegistry(root / "obligations.json"),
            graph=FactGraph(root),
            author="worker",
            worker=worker,
            verifier=RejectingVerifier(),
        )

        assert result.status == "SOLVED"
        assert worker.goals == ["Part one of M.", "Part two of M.", PROBLEM_STATEMENT]
        assert BLOCKED_GOAL not in worker.goals
        assert sorted(fact.statement for fact in FactGraph(root).list_facts()) == [
            "Base lemma B.",
            "Part one of M.",
            "Part two of M.",
            PROBLEM_STATEMENT,
        ]


def test_resume_after_split_never_reruns_superseded_or_resolved_nodes() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        apply_valid_split(root)

        rejecting = RejectingVerifier({"Part two of M."})
        first_worker = GoalEchoWorker()
        first = solve_scaffold(
            scaffold=ProofScaffold(root / "scaffold.json"),
            problem=ProblemSpec("p", PROBLEM_STATEMENT),
            registry=ObligationRegistry(root / "obligations.json"),
            graph=FactGraph(root),
            author="worker",
            worker=first_worker,
            verifier=rejecting,
        )
        assert first.status == "BLOCKED"
        assert first_worker.goals == ["Part one of M.", "Part two of M."]

        second_worker = GoalEchoWorker()
        second = solve_scaffold(
            scaffold=ProofScaffold(root / "scaffold.json"),
            problem=ProblemSpec("p", PROBLEM_STATEMENT),
            registry=ObligationRegistry(root / "obligations.json"),
            graph=FactGraph(root),
            author="worker",
            worker=second_worker,
            verifier=RejectingVerifier(),
        )

        assert second.status == "SOLVED"
        assert second_worker.goals == ["Part two of M.", PROBLEM_STATEMENT]
        assert BLOCKED_GOAL not in first_worker.goals + second_worker.goals


# --- Codex agent adapters (fresh sessions over the CodexInvoker protocol) ---

from research.agents import LocalGraphBuilder, StructuralAuditor  # noqa: E402


class RecordingCodex:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls = []

    def invoke(self, *, prompt, schema, label):
        self.calls.append((prompt, schema, label))
        return self.response


def captured_context(root: Path):
    builder = StubBuilder(BuilderResult(outcome="NO_USEFUL_SPLIT"))
    run(root, builder, passing_auditor())
    return builder.contexts[0]


def test_local_graph_builder_prompt_carries_evidence_and_returns_parsed_split() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        context = captured_context(root)
        codex = RecordingCodex(json.loads(split_raw()))

        result = LocalGraphBuilder(codex).propose(context)

        assert result.outcome == "SPLIT"
        assert result.proposal.blocked_node_id == "mid"
        assert [child.node_id for child in result.proposal.children] == ["mid-a", "mid-b"]
        prompt, schema, label = codex.calls[0]
        assert label == "local_graph_builder"
        assert PROBLEM_STATEMENT in prompt
        assert BLOCKED_GOAL in prompt
        assert "scripted verdict" in prompt  # verifier feedback from the failed attempt
        assert "NOT a proof worker" in prompt
        assert "Downstream intent" in prompt
        assert schema["additionalProperties"] is False


def test_structural_auditor_sees_only_the_permitted_fields() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        context = captured_context(root)
        proposal = parse_builder_output(split_raw(), blocked_node_id="mid").proposal
        codex = RecordingCodex(
            {"verdict": "PASS", "reasons": ["worth attempting"], "checks": {"target_preserved": True}}
        )

        result = StructuralAuditor(codex).audit(context, proposal)

        assert result.verdict == "PASS"
        assert result.reasons == ("worth attempting",)
        prompt, schema, label = codex.calls[0]
        assert label == "structural_auditor"
        assert PROBLEM_STATEMENT in prompt
        assert BLOCKED_GOAL in prompt
        assert "Part one of M." in prompt
        assert "Both halves failed jointly." in prompt  # builder's stated obstruction
        # After-graph: blocked superseded, sink child rewired into the target's route.
        assert "mid-b" in prompt
        # The auditor never sees proof text or candidate text — verdicts and
        # verifier feedback only.
        assert "A candidate proof" not in prompt
        base_fact = FactGraph(root).list_facts()[0]
        assert base_fact.proof not in prompt
        assert schema["additionalProperties"] is False


# --- code-review findings (evidence integrity / orphan guard) ---------------


def test_repeated_identical_proposal_never_overwrites_applied_evidence() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        first = apply_valid_split(root)
        (original,) = [
            path
            for path in evidence_files(root)
            if path.stem == first.proposal.proposal_id
        ]
        original_text = original.read_text(encoding="utf-8")

        second = run(root, split_builder(), passing_auditor())

        assert second.outcome == "MECHANICAL_REJECT"
        assert original.read_text(encoding="utf-8") == original_text
        names = [path.name for path in evidence_files(root)]
        assert len(names) == 2
        assert any(
            name.startswith(f"{first.proposal.proposal_id}-") for name in names
        )
        rejected = json.loads(
            next(
                path
                for path in evidence_files(root)
                if path.stem.startswith(f"{first.proposal.proposal_id}-")
            ).read_text(encoding="utf-8")
        )
        assert rejected["outcome"] == "MECHANICAL_REJECT"
        assert rejected["applied"] is False


def test_blocked_node_without_downstream_consumer_is_rejected() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        nodes = (
            ScaffoldNode("orphan", "Dead-end lemma D."),
            ScaffoldNode("target", PROBLEM_STATEMENT),
        )
        errors = validate(root, make_proposal(blocked_node_id="orphan"), nodes=nodes)
        assert any("no downstream consumer" in error for error in errors)
