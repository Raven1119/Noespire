"""N2B — INSERT_CUT_SET on the local-refinement seam.

The blocked goal G is preserved verbatim: the builder inserts 2-4 NEW
intermediate propositions (cuts) as OPEN obligations, and ``apply_cut_set``
supersedes the blocked node, appends the cuts, creates a re-routed node
``<blocked>__cut`` carrying G verbatim with the sink cuts as dependencies, and
rewires unexecuted downstream consumers onto it. Execution afterwards is the
untouched frozen ``solve_scaffold``/NodeSolver path; cuts are never admitted
as Facts by the apply step.

Deterministic: stub builders/auditors, fake worker/verifier — no Codex, no
network, no Docker.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

import json

import pytest

from research.fact import CandidateFact, Fact
from research.graph import FactGraph
from research.obligation import ObligationRegistry, ProofObligation
from research.pipeline import VerificationResult
from research.problem import ProblemSpec
from research.scaffold import ProofScaffold, ScaffoldNode, solve_scaffold

from research.local_refinement import (
    AuditorResult,
    BuilderResult,
    CutSetProposal,
    RedecompositionResult,
    SplitProposal,
    parse_builder_output,
    parse_cut_set_output,
    run_local_redecomposition,
    validate_cut_set_proposal,
)


PROBLEM_STATEMENT = "Target theorem T."
BLOCKED_GOAL = "Intermediate lemma M."
REROUTED_NODE_ID = "mid__cut"


class GoalEchoWorker:
    """Echoes the subgoal's ``Goal:\\n<text>`` tail back as the candidate."""

    def __init__(self) -> None:
        self.calls = 0
        self.goals = []
        self.premises_seen = []

    def propose(self, *, problem, existing_facts, subgoal, repair_context=None):
        self.calls += 1
        goal = subgoal.split("Goal:\n", 1)[1]
        self.goals.append(goal)
        self.premises_seen.append(tuple(fact.statement for fact in existing_facts))
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
        ScaffoldNode("mid", BLOCKED_GOAL),
        ScaffoldNode("target", PROBLEM_STATEMENT, depends_on=("mid",)),
    )


def make_workspace(root: Path) -> ProofScaffold:
    """Scaffold mid -> target; mid runs once and is rejected (FAIL evidence)."""
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


VALID_CUTS = (
    {"node_id": "cut-h1", "goal": "Helper proposition H1.", "depends_on": [], "premise_fact_ids": []},
    {
        "node_id": "cut-h2",
        "goal": "Helper proposition H2.",
        "depends_on": ["cut-h1"],
        "premise_fact_ids": [],
    },
)


def cut_raw(children=VALID_CUTS, obstruction="The direct route stalls on the same step.", effect="The cuts bypass the stuck step.") -> str:
    return json.dumps(
        {
            "outcome": "INSERT_CUT_SET",
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
    def propose(self, context, *, effort=None, timeout=None):
        raise RuntimeError("scripted builder crash")


class StubAuditor:
    def __init__(self, result: AuditorResult) -> None:
        self.result = result
        self.calls = []

    def audit(self, context, proposal, *, effort=None, timeout=None):
        self.calls.append((context, proposal))
        return self.result


class RaisingAuditor:
    def audit(self, context, proposal, *, effort=None, timeout=None):
        raise RuntimeError("scripted auditor crash")


def passing_auditor() -> StubAuditor:
    return StubAuditor(AuditorResult(verdict="PASS", reasons=("route looks sound",)))


def cut_builder(children=VALID_CUTS) -> StubBuilder:
    return StubBuilder(parse_cut_set_output(cut_raw(children), blocked_node_id="mid"))


def run_cut(root: Path, builder, auditor, **kwargs) -> RedecompositionResult:
    return run_local_redecomposition(
        root,
        problem_id="p",
        blocked_node_id="mid",
        builder=builder,
        auditor=auditor,
        operation="insert_cut_set",
        **kwargs,
    )


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


# --- parse_cut_set_output ----------------------------------------------------


def test_parse_cut_set_output_extracts_json_from_prose_and_fences() -> None:
    raw = "Reasoning prose first.\n```json\n" + cut_raw() + "\n```\ntrailing prose"
    result = parse_cut_set_output(raw, blocked_node_id="mid")

    assert result.outcome == "INSERT_CUT_SET"
    assert result.raw == raw
    proposal = result.proposal
    assert isinstance(proposal, CutSetProposal)
    assert proposal.blocked_node_id == "mid"
    assert proposal.proposal_id.startswith("cut-")
    assert proposal.obstruction == "The direct route stalls on the same step."
    assert [child.node_id for child in proposal.children] == ["cut-h1", "cut-h2"]
    assert proposal.children[1].depends_on == ("cut-h1",)


def test_parse_cut_set_output_proposal_id_is_deterministic() -> None:
    first = parse_cut_set_output(cut_raw(), blocked_node_id="mid")
    second = parse_cut_set_output(cut_raw(), blocked_node_id="mid")
    assert first.proposal.proposal_id == second.proposal.proposal_id


def test_parse_cut_set_output_malformed_or_unknown_is_error() -> None:
    assert parse_cut_set_output("no json here").outcome == "ERROR"
    assert parse_cut_set_output('{"outcome": "INSERT_CUT_SET", "new_nodes": [').outcome == "ERROR"
    assert parse_cut_set_output(json.dumps({"outcome": "SPLIT"})).outcome == "ERROR"


def test_parse_cut_set_output_decline_outcomes() -> None:
    result = parse_cut_set_output(
        json.dumps({"outcome": "NO_USEFUL_CUT", "missing_context": ""})
    )
    assert result.outcome == "NO_USEFUL_CUT"
    assert result.proposal is None
    result = parse_cut_set_output(
        json.dumps({"outcome": "NEED_MORE_CONTEXT", "missing_context": "need the failed step"})
    )
    assert result.outcome == "NEED_MORE_CONTEXT"
    assert result.missing_context == "need the failed step"


# --- validate_cut_set_proposal (mechanical admission) ------------------------


def make_proposal(children=VALID_CUTS, blocked_node_id="mid") -> CutSetProposal:
    return parse_cut_set_output(cut_raw(children), blocked_node_id=blocked_node_id).proposal


def validate(root: Path, proposal: CutSetProposal, *, nodes=None, premises=(), graph=None) -> tuple:
    return validate_cut_set_proposal(
        proposal=proposal,
        nodes=tuple(nodes) if nodes is not None else scaffold_nodes(),
        target_node_id="target",
        problem_id="p",
        problem_premise_fact_ids=premises,
        obligations=ObligationRegistry(root / "obligations.json"),
        graph=graph if graph is not None else FactGraph(root),
    )


def test_valid_cut_set_passes_all_mechanical_checks() -> None:
    with TemporaryDirectory() as directory:
        assert validate(Path(directory), make_proposal()) == ()


def test_blocked_node_guards_match_the_split_contract() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        errors = validate(root, make_proposal(blocked_node_id="ghost"))
        assert any("unknown blocked node" in error for error in errors)
        errors = validate(root, make_proposal(blocked_node_id="target"))
        assert any("target" in error for error in errors)

        resolved = ScaffoldNode("mid", BLOCKED_GOAL, resolved_by_fact_id="f0")
        superseded = ScaffoldNode("mid", BLOCKED_GOAL, superseded_by="cut-old")
        parked = ScaffoldNode("mid", BLOCKED_GOAL, parked_by="alt-old")
        for node, fragment in (
            (resolved, "resolved"),
            (superseded, "superseded"),
            (parked, "parked"),
        ):
            nodes = (node, scaffold_nodes()[1])
            errors = validate(root, make_proposal(), nodes=nodes)
            assert any(fragment in error for error in errors), (fragment, errors)


def test_blocked_node_without_downstream_consumer_is_rejected() -> None:
    with TemporaryDirectory() as directory:
        orphan_nodes = (
            ScaffoldNode("mid", BLOCKED_GOAL),
            ScaffoldNode("target", PROBLEM_STATEMENT),
        )
        errors = validate(Path(directory), make_proposal(), nodes=orphan_nodes)
        assert any("no downstream consumer" in error for error in errors)


def test_cut_set_size_is_bounded_between_two_and_four() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        errors = validate(root, make_proposal(children=VALID_CUTS[:1]))
        assert any("between 2 and 4" in error for error in errors)
        five = tuple(
            dict(VALID_CUTS[0], node_id=f"cut-h{i}", goal=f"Helper proposition H{i}.")
            for i in range(5)
        )
        errors = validate(root, make_proposal(children=five))
        assert any("between 2 and 4" in error for error in errors)


def test_duplicate_and_colliding_cut_ids_are_rejected() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        duplicate = (VALID_CUTS[0], dict(VALID_CUTS[0], goal="Different helper."))
        errors = validate(root, make_proposal(children=duplicate))
        assert any("duplicate cut node_id" in error for error in errors)

        colliding = (dict(VALID_CUTS[1], node_id="target"), VALID_CUTS[0])
        errors = validate(root, make_proposal(children=colliding))
        assert any("collides" in error for error in errors)

        rerouted_collision = (dict(VALID_CUTS[0], node_id=REROUTED_NODE_ID), VALID_CUTS[1])
        errors = validate(root, make_proposal(children=rerouted_collision))
        assert any("collides" in error for error in errors)

        existing_rerouted = scaffold_nodes() + (ScaffoldNode(REROUTED_NODE_ID, "Occupied."),)
        errors = validate(root, make_proposal(), nodes=existing_rerouted)
        assert any("collides" in error for error in errors)


def test_cut_goal_leakage_duplicates_and_instructions_are_rejected() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        for leaked in (
            BLOCKED_GOAL,
            " intermediate   lemma m.",  # whitespace/case-normalized blocked goal
            PROBLEM_STATEMENT,
        ):
            children = (dict(VALID_CUTS[0], goal=leaked), VALID_CUTS[1])
            errors = validate(root, make_proposal(children=children))
            assert any("restates" in error for error in errors), (leaked, errors)

        same_goal = (VALID_CUTS[0], dict(VALID_CUTS[1], goal=VALID_CUTS[0]["goal"]))
        errors = validate(root, make_proposal(children=same_goal))
        assert any("duplicate cut goal" in error for error in errors)

        instruction = (dict(VALID_CUTS[0], goal="Now complete the proof of M."), VALID_CUTS[1])
        errors = validate(root, make_proposal(children=instruction))
        assert any("instruction" in error for error in errors)


def test_cut_depends_on_must_stay_inside_the_cut_set_and_acyclic() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        dangling = (dict(VALID_CUTS[0], depends_on=["mid"]), VALID_CUTS[1])
        errors = validate(root, make_proposal(children=dangling))
        assert any("non-cut" in error for error in errors)

        cyclic = (
            dict(VALID_CUTS[0], depends_on=["cut-h2"]),
            dict(VALID_CUTS[1], depends_on=["cut-h1"]),
        )
        errors = validate(root, make_proposal(children=cyclic))
        assert any("cycle" in error for error in errors)


def test_cut_base_facts_must_be_declared_and_present_in_the_fact_graph() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        graph = FactGraph(root)
        base = graph.add_fact(
            Fact.create(
                problem_id="p", author="seed", statement="Base fact.", proof="Accepted."
            )
        )
        foreign = graph.add_fact(
            Fact.create(
                problem_id="other", author="seed", statement="Foreign.", proof="Accepted."
            )
        )

        with_premise = (
            dict(VALID_CUTS[0], premise_fact_ids=[base.fact_id]),
            VALID_CUTS[1],
        )
        assert validate(root, make_proposal(children=with_premise), premises=(base.fact_id,)) == ()

        errors = validate(root, make_proposal(children=with_premise), premises=())
        assert any("declared problem premises" in error for error in errors)

        errors = validate(
            root,
            make_proposal(children=with_premise),
            premises=(base.fact_id,),
            graph=FactGraph(root / "empty"),
        )
        assert any("unknown or revoked" in error for error in errors)

        foreign_cut = (dict(VALID_CUTS[0], premise_fact_ids=[foreign.fact_id]), VALID_CUTS[1])
        errors = validate(root, make_proposal(children=foreign_cut), premises=(foreign.fact_id,))
        assert any("another problem" in error for error in errors)


def test_cut_base_fact_that_was_revoked_is_rejected() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        graph = FactGraph(root)
        base = graph.add_fact(
            Fact.create(
                problem_id="p", author="seed", statement="Base fact.", proof="Accepted."
            )
        )
        graph.revoke(base.fact_id, "scripted revocation")
        with_premise = (
            dict(VALID_CUTS[0], premise_fact_ids=[base.fact_id]),
            VALID_CUTS[1],
        )
        errors = validate(root, make_proposal(children=with_premise), premises=(base.fact_id,))
        assert any("unknown or revoked" in error for error in errors)


def test_executed_downstream_node_fails_closed() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        registry = ObligationRegistry(root / "obligations.json")
        registry.add(ProofObligation("scaffold:p:target", (), PROBLEM_STATEMENT, "scaffold:target"))
        errors = validate(root, make_proposal())
        assert any("already executed" in error for error in errors)


# --- run_local_redecomposition(operation="insert_cut_set") -------------------


def test_no_useful_cut_leaves_graph_unchanged_with_no_cut_evidence() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        before = scaffold_text(root)
        auditor = passing_auditor()

        result = run_cut(
            root, StubBuilder(BuilderResult(outcome="NO_USEFUL_CUT", raw='{"outcome": "NO_USEFUL_CUT"}')), auditor
        )

        assert result.outcome == "NO_USEFUL_CUT"
        assert scaffold_text(root) == before
        assert auditor.calls == []
        (evidence,) = evidence_files(root)
        assert evidence.name.startswith("no-cut-")
        payload = json.loads(evidence.read_text(encoding="utf-8"))
        assert payload["outcome"] == "NO_USEFUL_CUT"
        assert payload["applied"] is False
        assert payload["context"]["allowed_operation"] == "INSERT_CUT_SET"


def test_need_more_context_leaves_graph_unchanged() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        before = scaffold_text(root)

        result = run_cut(root, StubBuilder(BuilderResult(outcome="NEED_MORE_CONTEXT")), passing_auditor())

        assert result.outcome == "NEED_MORE_CONTEXT"
        assert scaffold_text(root) == before
        (evidence,) = evidence_files(root)
        assert evidence.name.startswith("no-cut-")


def test_builder_error_leaves_graph_unchanged() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        before = scaffold_text(root)

        result = run_cut(root, RaisingBuilder(), passing_auditor())

        assert result.outcome == "BUILDER_ERROR"
        assert scaffold_text(root) == before


def test_mechanically_invalid_cut_set_is_rejected_before_the_auditor() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        before = scaffold_text(root)
        cyclic = (
            dict(VALID_CUTS[0], depends_on=["cut-h2"]),
            dict(VALID_CUTS[1], depends_on=["cut-h1"]),
        )
        auditor = passing_auditor()

        result = run_cut(root, cut_builder(cyclic), auditor)

        assert result.outcome == "MECHANICAL_REJECT"
        assert any("cycle" in error for error in result.mechanical_errors)
        assert scaffold_text(root) == before
        assert auditor.calls == []
        (evidence,) = evidence_files(root)
        assert evidence.name.startswith("cut-")


@pytest.mark.parametrize("verdict", ("REVISE", "REJECT"))
def test_auditor_revise_and_reject_leave_graph_unchanged(verdict: str) -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        before = scaffold_text(root)
        auditor = StubAuditor(AuditorResult(verdict=verdict, reasons=("cosmetic cuts",)))

        result = run_cut(root, cut_builder(), auditor)

        assert result.outcome == f"AUDITOR_{verdict}"
        assert scaffold_text(root) == before


def test_auditor_error_leaves_graph_unchanged() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        before = scaffold_text(root)

        result = run_cut(root, cut_builder(), RaisingAuditor())

        assert result.outcome == "AUDITOR_ERROR"
        assert scaffold_text(root) == before


def apply_valid_cut_set(root: Path) -> RedecompositionResult:
    result = run_cut(root, cut_builder(), passing_auditor())
    assert result.outcome == "APPLIED"
    return result


def test_applied_cut_set_keeps_goal_verbatim_and_rewires_through_rerouted_node() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)

        result = apply_valid_cut_set(root)

        assert result.child_node_ids == ("cut-h1", "cut-h2", REROUTED_NODE_ID)
        reloaded = ProofScaffold(root / "scaffold.json")
        blocked = reloaded.get("mid")
        assert blocked.superseded_by == result.proposal.proposal_id
        assert blocked.goal == BLOCKED_GOAL
        rerouted = reloaded.get(REROUTED_NODE_ID)
        # The re-routed node carries the blocked goal VERBATIM off the sink cut.
        assert rerouted.goal == BLOCKED_GOAL
        assert rerouted.depends_on == ("cut-h2",)
        assert rerouted.premise_fact_ids == ()
        assert rerouted.resolved_by_fact_id is None
        assert reloaded.get("target").depends_on == (REROUTED_NODE_ID,)
        for cut_id in ("cut-h1", "cut-h2"):
            assert reloaded.get(cut_id).resolved_by_fact_id is None

        (evidence,) = evidence_files(root)
        assert evidence.name == f"{result.proposal.proposal_id}.json"
        payload = json.loads(evidence.read_text(encoding="utf-8"))
        assert payload["outcome"] == "APPLIED"
        assert payload["applied"] is True
        post_ids = {node["node_id"] for node in payload["post_patch_nodes"]}
        assert post_ids == {"mid", "cut-h1", "cut-h2", REROUTED_NODE_ID, "target"}


def test_apply_admits_no_facts_and_preserves_attempts_byte_identical() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        attempts_before = attempt_snapshots(root)

        apply_valid_cut_set(root)

        assert attempt_snapshots(root) == attempts_before
        assert FactGraph(root).list_facts() == []
        registry = ObligationRegistry(root / "obligations.json")
        assert [item.obligation_id for item in registry.list()] == ["scaffold:p:mid"]


def test_second_cut_run_on_same_node_is_rejected_and_evidence_never_overwritten() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        first = apply_valid_cut_set(root)
        first_evidence = Path(first.evidence_path)
        first_content = first_evidence.read_text(encoding="utf-8")
        after_first = scaffold_text(root)

        second = run_cut(root, cut_builder(), passing_auditor())

        assert second.outcome == "MECHANICAL_REJECT"
        assert any("superseded" in error for error in second.mechanical_errors)
        assert scaffold_text(root) == after_first
        assert first_evidence.read_text(encoding="utf-8") == first_content
        assert len(evidence_files(root)) == 2
        assert Path(second.evidence_path) != first_evidence


# --- frozen execution path over the patched scaffold ------------------------


def test_frozen_solver_executes_cuts_then_rerouted_goal_then_target() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        apply_valid_cut_set(root)

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
        assert worker.goals == [
            "Helper proposition H1.",
            "Helper proposition H2.",
            BLOCKED_GOAL,  # the re-routed node carries G verbatim
            PROBLEM_STATEMENT,
        ]
        # B' is proved with the resolved sink cut as its premise Fact.
        assert worker.premises_seen[2] == ("Helper proposition H2.",)
        assert worker.premises_seen[3] == (BLOCKED_GOAL,)
        assert sorted(fact.statement for fact in FactGraph(root).list_facts()) == [
            "Helper proposition H1.",
            "Helper proposition H2.",
            BLOCKED_GOAL,
            PROBLEM_STATEMENT,
        ]


def test_failed_cut_stays_open_and_downstream_never_runs() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        apply_valid_cut_set(root)

        worker = GoalEchoWorker()
        result = solve_scaffold(
            scaffold=ProofScaffold(root / "scaffold.json"),
            problem=ProblemSpec("p", PROBLEM_STATEMENT),
            registry=ObligationRegistry(root / "obligations.json"),
            graph=FactGraph(root),
            author="worker",
            worker=worker,
            verifier=RejectingVerifier({"Helper proposition H2."}),
        )

        assert result.status == "BLOCKED"
        assert worker.goals == ["Helper proposition H1.", "Helper proposition H2."]
        reloaded = ProofScaffold(root / "scaffold.json")
        assert reloaded.get("cut-h1").resolved_by_fact_id is not None
        assert reloaded.get("cut-h2").resolved_by_fact_id is None
        assert reloaded.get(REROUTED_NODE_ID).resolved_by_fact_id is None
        assert reloaded.get("target").resolved_by_fact_id is None
        assert [fact.statement for fact in FactGraph(root).list_facts()] == [
            "Helper proposition H1."
        ]


# --- operation plumbing -------------------------------------------------------


def test_unknown_operation_is_rejected() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        with pytest.raises(ValueError, match="operation"):
            run_local_redecomposition(
                root,
                problem_id="p",
                blocked_node_id="mid",
                builder=cut_builder(),
                auditor=passing_auditor(),
                operation="rewire",
            )


def test_default_operation_stays_split_and_marks_context() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        split_children = (
            {"node_id": "mid-a", "goal": "Part one of M.", "depends_on": [], "premise_fact_ids": []},
            {"node_id": "mid-b", "goal": "Part two of M.", "depends_on": ["mid-a"], "premise_fact_ids": []},
        )
        raw = json.dumps(
            {
                "outcome": "SPLIT",
                "obstruction": "Both halves failed jointly.",
                "expected_effect": "Each half is provable alone.",
                "new_nodes": list(split_children),
                "missing_context": "",
            }
        )
        builder = StubBuilder(parse_builder_output(raw, blocked_node_id="mid"))

        result = run_local_redecomposition(
            root,
            problem_id="p",
            blocked_node_id="mid",
            builder=builder,
            auditor=passing_auditor(),
        )

        assert result.outcome == "APPLIED"
        assert builder.contexts[0].allowed_operation == "SPLIT"
        payload = json.loads(Path(result.evidence_path).read_text(encoding="utf-8"))
        assert payload["context"]["allowed_operation"] == "SPLIT"


def test_evidence_records_exact_builder_and_auditor_inputs() -> None:
    class SentinelBuilder(StubBuilder):
        last_prompt = "BUILDER-PROMPT-SENTINEL"

    class SentinelAuditor(StubAuditor):
        last_prompt = "AUDITOR-PROMPT-SENTINEL"

    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)

        result = run_cut(
            root,
            SentinelBuilder(parse_cut_set_output(cut_raw(), blocked_node_id="mid")),
            SentinelAuditor(AuditorResult(verdict="PASS")),
        )

        payload = json.loads(Path(result.evidence_path).read_text(encoding="utf-8"))
        assert payload["builder_input"] == "BUILDER-PROMPT-SENTINEL"
        assert payload["auditor_input"] == "AUDITOR-PROMPT-SENTINEL"


def test_evidence_inputs_are_null_when_agents_do_not_capture_prompts() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)

        result = run_cut(root, cut_builder(), passing_auditor())

        payload = json.loads(Path(result.evidence_path).read_text(encoding="utf-8"))
        assert payload["builder_input"] is None
        assert payload["auditor_input"] is None


# --- Codex agent adapters in insert_cut_set mode ------------------------------

from research.agents import LocalGraphBuilder, StructuralAuditor  # noqa: E402


CUT_AUDIT_CHECKS = (
    "target_preserved",
    "assumptions_preserved",
    "no_hidden_circularity",
    "each_cut_is_coherent",
    "each_cut_is_genuinely_narrower",
    "cuts_are_not_target_equivalent",
    "cuts_are_not_cosmetic_restatements",
    "route_plausibly_recovers_blocked_goal",
    "cuts_are_meaningful_worker_units",
)


class RecordingCodex:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls = []

    def invoke(self, *, prompt, schema, label):
        self.calls.append((prompt, schema, label))
        return self.response


def captured_context(root: Path):
    builder = StubBuilder(BuilderResult(outcome="NO_USEFUL_CUT"))
    run_cut(root, builder, passing_auditor())
    return builder.contexts[0]


def test_cut_builder_prompt_keeps_goal_verbatim_and_marks_cuts_unverified() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        context = captured_context(root)
        codex = RecordingCodex(json.loads(cut_raw()))

        builder = LocalGraphBuilder(codex, operation="insert_cut_set")
        result = builder.propose(context)

        assert result.outcome == "INSERT_CUT_SET"
        assert isinstance(result.proposal, CutSetProposal)
        assert [child.node_id for child in result.proposal.children] == ["cut-h1", "cut-h2"]
        prompt, schema, label = codex.calls[0]
        assert label == "local_graph_builder"
        # The blocked goal G is shown verbatim and described as re-routed.
        assert BLOCKED_GOAL in prompt
        assert "verbatim" in prompt
        assert "re-routed" in prompt
        # Cuts are invented as UNVERIFIED obligations, never claimed true.
        assert "UNVERIFIED" in prompt
        assert "NO_USEFUL_CUT" in prompt
        assert "NEED_MORE_CONTEXT" in prompt
        # Failure evidence is carried (verifier feedback from the FAIL attempt).
        assert "scripted verdict" in prompt
        # The exact prompt is captured for the evidence bundle.
        assert builder.last_prompt == prompt
        # Strict schema, no bare objects (the N2A bare-checks bug class).
        assert schema["additionalProperties"] is False
        assert schema["properties"]["new_nodes"]["items"]["additionalProperties"] is False
        assert schema["properties"]["outcome"]["enum"] == [
            "INSERT_CUT_SET",
            "NO_USEFUL_CUT",
            "NEED_MORE_CONTEXT",
        ]


def test_cut_auditor_prompt_restricted_fields_and_nine_checks() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        context = captured_context(root)
        proposal = parse_cut_set_output(cut_raw(), blocked_node_id="mid").proposal
        response = {
            "verdict": "PASS",
            "reasons": ["route plausibly recovers the blocked goal"],
            "checks": {name: True for name in CUT_AUDIT_CHECKS},
        }
        codex = RecordingCodex(response)

        auditor = StructuralAuditor(codex, operation="insert_cut_set")
        result = auditor.audit(context, proposal)

        assert result.verdict == "PASS"
        assert result.reasons == ("route plausibly recovers the blocked goal",)
        assert result.checks["cuts_are_not_cosmetic_restatements"] is True
        prompt, schema, label = codex.calls[0]
        assert label == "structural_auditor"
        assert PROBLEM_STATEMENT in prompt
        assert BLOCKED_GOAL in prompt
        assert "The direct route stalls on the same step." in prompt  # obstruction
        assert "The cuts bypass the stuck step." in prompt  # expected_effect
        # After-graph: B superseded, cuts listed, B' carries G verbatim off the
        # sink cut, downstream rewired onto B'.
        assert "SUPERSEDED" in prompt
        assert "cut-h1" in prompt and "cut-h2" in prompt
        assert REROUTED_NODE_ID in prompt
        assert "MUST be REJECTed" in prompt
        # The auditor never sees proof text or candidate text.
        assert "A candidate proof" not in prompt
        # The exact prompt is captured for the evidence bundle.
        assert auditor.last_prompt == prompt
        # Nine enumerated boolean checks, all required, strict objects.
        checks_schema = schema["properties"]["checks"]
        assert checks_schema["additionalProperties"] is False
        assert sorted(checks_schema["required"]) == sorted(CUT_AUDIT_CHECKS)
        assert all(
            checks_schema["properties"][name] == {"type": "boolean"}
            for name in CUT_AUDIT_CHECKS
        )
        assert schema["additionalProperties"] is False


def test_agents_default_operation_is_split_and_unknown_operation_rejected() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        context = captured_context(root)
        codex = RecordingCodex(
            {
                "outcome": "NO_USEFUL_SPLIT",
                "obstruction": "",
                "expected_effect": "",
                "new_nodes": [],
                "missing_context": "",
            }
        )
        builder = LocalGraphBuilder(codex)  # default: N2A split behavior
        result = builder.propose(context)
        assert result.outcome == "NO_USEFUL_SPLIT"
        prompt, schema, label = codex.calls[0]
        assert schema["properties"]["outcome"]["enum"] == [
            "SPLIT",
            "NO_USEFUL_SPLIT",
            "NEED_MORE_CONTEXT",
        ]
        assert builder.last_prompt == prompt

        with pytest.raises(ValueError, match="operation"):
            LocalGraphBuilder(codex, operation="rewire")
        with pytest.raises(ValueError, match="operation"):
            StructuralAuditor(codex, operation="rewire")
