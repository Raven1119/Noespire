"""N2C — ADD_ALTERNATIVE_ROUTE on the local-refinement seam.

The blocked node B (goal G, direct route R1) is PARKED — retained as
route-of-record with its row, obligation, and all attempts byte-identical —
and a new route R2 is added: 2-4 NEW intermediate obligations H1..Hk plus a
re-routed node ``<blocked>__alt`` carrying G VERBATIM with the sink new nodes
as dependencies. Execution afterwards is the untouched frozen
``solve_scaffold``/NodeSolver path; nothing is admitted as a Fact by apply.

Deterministic: stub builders/auditors, fake worker/verifier — no Codex, no
network, no Docker.
"""

from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

import json

import pytest

from research.fact import CandidateFact, Fact
from research.graph import FactGraph
from research.obligation import ObligationRegistry, ProofObligation
from research.pipeline import VerificationResult
from research.problem import ProblemSpec
from research.scaffold import ProofScaffold, ScaffoldNode, ready_nodes, solve_scaffold

from research.local_refinement import (
    AlternativeRouteProposal,
    AuditorResult,
    BuilderResult,
    RedecompositionResult,
    parse_alternative_route_output,
    run_local_redecomposition,
    validate_alternative_route_proposal,
)


PROBLEM_STATEMENT = "Target theorem T."
BLOCKED_GOAL = "Intermediate lemma M."
REROUTED_NODE_ID = "mid__alt"
SIDE_GOAL = "Unrelated side lemma S."
SIDE_PROOF = "SECRET-UNRELATED-PROOF-TEXT"


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


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def scaffold_nodes() -> tuple[ScaffoldNode, ...]:
    return (
        ScaffoldNode("mid", BLOCKED_GOAL),
        ScaffoldNode("target", PROBLEM_STATEMENT, depends_on=("mid",)),
    )


def make_workspace(root: Path, *, premise_fact_ids=()) -> ProofScaffold:
    """Scaffold mid -> target; mid runs once and is rejected (FAIL evidence)."""
    problem = ProblemSpec("p", PROBLEM_STATEMENT)
    scaffold = ProofScaffold.create(
        root / "scaffold.json",
        problem=problem,
        target_node_id="target",
        nodes=(replace(scaffold_nodes()[0], premise_fact_ids=premise_fact_ids), scaffold_nodes()[1]),
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


def make_workspace_with_sibling(root: Path) -> ProofScaffold:
    """Adds a resolved sibling branch (``side``) with an accepted Fact that is
    unrelated to the blocked node's local region."""
    problem = ProblemSpec("p", PROBLEM_STATEMENT)
    scaffold = ProofScaffold.create(
        root / "scaffold.json",
        problem=problem,
        target_node_id="target",
        nodes=(
            ScaffoldNode("mid", BLOCKED_GOAL),
            ScaffoldNode("side", SIDE_GOAL),
            ScaffoldNode("target", PROBLEM_STATEMENT, depends_on=("mid", "side")),
        ),
    )
    graph = FactGraph(root)
    side_fact = graph.add_fact(
        Fact.create(problem_id="p", author="worker", statement=SIDE_GOAL, proof=SIDE_PROOF)
    )
    scaffold.resolve("side", side_fact.fact_id, graph)
    result = solve_scaffold(
        scaffold=scaffold,
        problem=problem,
        registry=ObligationRegistry(root / "obligations.json"),
        graph=graph,
        author="worker",
        worker=GoalEchoWorker(),
        verifier=RejectingVerifier({BLOCKED_GOAL}),
    )
    assert result.status == "BLOCKED"
    return ProofScaffold(root / "scaffold.json")


VALID_ALTS = (
    {"node_id": "alt-h1", "goal": "Helper proposition H1.", "depends_on": [], "premise_fact_ids": []},
    {
        "node_id": "alt-h2",
        "goal": "Helper proposition H2.",
        "depends_on": ["alt-h1"],
        "premise_fact_ids": [],
    },
)


def alt_raw(children=VALID_ALTS, obstruction="The direct computation stalls.", exhausted="R1 has no further honest step.", effect="R2 reaches G by a different mechanism.") -> str:
    return json.dumps(
        {
            "outcome": "ADD_ALTERNATIVE_ROUTE",
            "obstruction": obstruction,
            "why_current_route_is_exhausted": exhausted,
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
    return StubAuditor(AuditorResult(verdict="PASS", reasons=("route looks different",)))


def alt_builder(children=VALID_ALTS) -> StubBuilder:
    return StubBuilder(
        parse_alternative_route_output(alt_raw(children), blocked_node_id="mid")
    )


def run_alt(root: Path, builder, auditor, **kwargs) -> RedecompositionResult:
    return run_local_redecomposition(
        root,
        problem_id="p",
        blocked_node_id="mid",
        builder=builder,
        auditor=auditor,
        operation="add_alternative_route",
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


# --- parked scheduling semantics (scaffold.py) --------------------------------


def test_ready_nodes_excludes_parked_nodes() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        scaffold = make_workspace(root)
        registry = ObligationRegistry(root / "obligations.json")
        assert [node.node_id for node in ready_nodes(scaffold, registry)] == ["mid"]

        payload = json.loads(scaffold_text(root))
        for item in payload["nodes"]:
            if item["node_id"] == "mid":
                item["parked_by"] = "alt-test"
        (root / "scaffold.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        reloaded = ProofScaffold(root / "scaffold.json")
        assert reloaded.get("mid").parked_by == "alt-test"
        assert reloaded.get("mid").superseded_by is None
        assert reloaded.get("mid").resolved_by_fact_id is None
        assert ready_nodes(reloaded, registry) == []


def test_scaffold_json_without_parked_by_still_loads() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        payload = json.loads(scaffold_text(root))
        for item in payload["nodes"]:
            item.pop("parked_by", None)
        (root / "scaffold.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

        reloaded = ProofScaffold(root / "scaffold.json")
        assert all(node.parked_by is None for node in reloaded.list_nodes())


# --- parse_alternative_route_output -------------------------------------------


def test_parse_alternative_route_output_extracts_json_from_prose_and_fences() -> None:
    raw = "Route reasoning prose.\n```json\n" + alt_raw() + "\n```\ntrailing"
    result = parse_alternative_route_output(raw, blocked_node_id="mid")

    assert result.outcome == "ADD_ALTERNATIVE_ROUTE"
    assert result.raw == raw
    proposal = result.proposal
    assert isinstance(proposal, AlternativeRouteProposal)
    assert proposal.blocked_node_id == "mid"
    assert proposal.target_node_id == "mid"
    assert proposal.proposal_id.startswith("alt-")
    assert proposal.failed_route_summary == "R1 has no further honest step."
    assert proposal.obstruction == "The direct computation stalls."
    assert [child.node_id for child in proposal.children] == ["alt-h1", "alt-h2"]
    assert proposal.children[1].depends_on == ("alt-h1",)


def test_parse_alternative_route_output_proposal_id_is_deterministic() -> None:
    first = parse_alternative_route_output(alt_raw(), blocked_node_id="mid")
    second = parse_alternative_route_output(alt_raw(), blocked_node_id="mid")
    assert first.proposal.proposal_id == second.proposal.proposal_id


def test_parse_alternative_route_output_malformed_or_unknown_is_error() -> None:
    assert parse_alternative_route_output("no json here").outcome == "ERROR"
    assert (
        parse_alternative_route_output('{"outcome": "ADD_ALTERNATIVE_ROUTE", "new_nodes": [').outcome
        == "ERROR"
    )
    assert parse_alternative_route_output(json.dumps({"outcome": "SPLIT"})).outcome == "ERROR"


def test_parse_alternative_route_output_decline_outcomes() -> None:
    result = parse_alternative_route_output(
        json.dumps({"outcome": "NO_USEFUL_ROUTE", "missing_context": ""})
    )
    assert result.outcome == "NO_USEFUL_ROUTE"
    assert result.proposal is None
    result = parse_alternative_route_output(
        json.dumps({"outcome": "NEED_MORE_CONTEXT", "missing_context": "need the failed step"})
    )
    assert result.outcome == "NEED_MORE_CONTEXT"
    assert result.missing_context == "need the failed step"


# --- validate_alternative_route_proposal (mechanical admission) ----------------


def make_proposal(children=VALID_ALTS, blocked_node_id="mid") -> AlternativeRouteProposal:
    return parse_alternative_route_output(
        alt_raw(children), blocked_node_id=blocked_node_id
    ).proposal


def validate(root: Path, proposal: AlternativeRouteProposal, *, nodes=None, premises=(), boundary=(), graph=None) -> tuple:
    return validate_alternative_route_proposal(
        proposal=proposal,
        nodes=tuple(nodes) if nodes is not None else scaffold_nodes(),
        target_node_id="target",
        problem_id="p",
        problem_premise_fact_ids=premises,
        obligations=ObligationRegistry(root / "obligations.json"),
        graph=graph if graph is not None else FactGraph(root),
        allowed_boundary_fact_ids=boundary,
    )


def test_valid_alternative_route_passes_all_mechanical_checks() -> None:
    with TemporaryDirectory() as directory:
        assert validate(Path(directory), make_proposal()) == ()


def test_blocked_node_guards_including_not_parked() -> None:
    from dataclasses import replace

    with TemporaryDirectory() as directory:
        root = Path(directory)
        errors = validate(root, make_proposal(blocked_node_id="ghost"))
        assert any("unknown blocked node" in error for error in errors)

        proposal = make_proposal(blocked_node_id="target")
        errors = validate(root, proposal)
        assert any("target" in error for error in errors)

        resolved = ScaffoldNode("mid", BLOCKED_GOAL, resolved_by_fact_id="f0")
        superseded = ScaffoldNode("mid", BLOCKED_GOAL, superseded_by="split-old")
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


def test_mutation_boundary_must_match_the_blocked_node() -> None:
    from dataclasses import replace

    with TemporaryDirectory() as directory:
        root = Path(directory)
        wrong = replace(make_proposal(), target_node_id="other")
        errors = validate(root, wrong)
        assert any("boundary" in error for error in errors)


def test_new_node_count_is_bounded_between_two_and_four() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        errors = validate(root, make_proposal(children=VALID_ALTS[:1]))
        assert any("between 2 and 4" in error for error in errors)
        five = tuple(
            dict(VALID_ALTS[0], node_id=f"alt-h{i}", goal=f"Helper proposition H{i}.")
            for i in range(5)
        )
        errors = validate(root, make_proposal(children=five))
        assert any("between 2 and 4" in error for error in errors)


def test_duplicate_and_colliding_new_ids_are_rejected() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        duplicate = (VALID_ALTS[0], dict(VALID_ALTS[0], goal="Different helper."))
        errors = validate(root, make_proposal(children=duplicate))
        assert any("duplicate" in error for error in errors)

        colliding = (dict(VALID_ALTS[1], node_id="target"), VALID_ALTS[0])
        errors = validate(root, make_proposal(children=colliding))
        assert any("collides" in error for error in errors)

        rerouted_collision = (dict(VALID_ALTS[0], node_id=REROUTED_NODE_ID), VALID_ALTS[1])
        errors = validate(root, make_proposal(children=rerouted_collision))
        assert any("collides" in error for error in errors)

        existing_rerouted = scaffold_nodes() + (ScaffoldNode(REROUTED_NODE_ID, "Occupied."),)
        errors = validate(root, make_proposal(), nodes=existing_rerouted)
        assert any("collides" in error for error in errors)


def test_new_goal_leakage_duplicates_and_instructions_are_rejected() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        for leaked in (
            BLOCKED_GOAL,
            " intermediate   lemma m.",  # whitespace/case-normalized blocked goal
            PROBLEM_STATEMENT,
        ):
            children = (dict(VALID_ALTS[0], goal=leaked), VALID_ALTS[1])
            errors = validate(root, make_proposal(children=children))
            assert any("restates" in error for error in errors), (leaked, errors)

        same_goal = (VALID_ALTS[0], dict(VALID_ALTS[1], goal=VALID_ALTS[0]["goal"]))
        errors = validate(root, make_proposal(children=same_goal))
        assert any("duplicate" in error and "goal" in error for error in errors)

        instruction = (dict(VALID_ALTS[0], goal="Now finish the proof of M."), VALID_ALTS[1])
        errors = validate(root, make_proposal(children=instruction))
        assert any("instruction" in error for error in errors)


def test_new_nodes_must_not_reference_any_existing_node() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        dangling = (dict(VALID_ALTS[0], depends_on=["mid"]), VALID_ALTS[1])
        errors = validate(root, make_proposal(children=dangling))
        assert any("outside the new route" in error for error in errors)

        cyclic = (
            dict(VALID_ALTS[0], depends_on=["alt-h2"]),
            dict(VALID_ALTS[1], depends_on=["alt-h1"]),
        )
        errors = validate(root, make_proposal(children=cyclic))
        assert any("cycle" in error for error in errors)


def test_premise_facts_must_be_declared_present_accepted_and_same_problem() -> None:
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
        revoked = graph.add_fact(
            Fact.create(
                problem_id="p", author="seed", statement="Revoked base.", proof="Accepted."
            )
        )
        graph.revoke(revoked.fact_id, "scripted revocation")

        with_premise = (dict(VALID_ALTS[0], premise_fact_ids=[base.fact_id]), VALID_ALTS[1])
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

        revoked_cut = (dict(VALID_ALTS[0], premise_fact_ids=[revoked.fact_id]), VALID_ALTS[1])
        errors = validate(root, make_proposal(children=revoked_cut), premises=(revoked.fact_id,))
        assert any("unknown or revoked" in error for error in errors)

        foreign_cut = (dict(VALID_ALTS[0], premise_fact_ids=[foreign.fact_id]), VALID_ALTS[1])
        errors = validate(root, make_proposal(children=foreign_cut), premises=(foreign.fact_id,))
        assert any("another problem" in error for error in errors)


def test_executed_downstream_node_fails_closed() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        registry = ObligationRegistry(root / "obligations.json")
        registry.add(ProofObligation("scaffold:p:target", (), PROBLEM_STATEMENT, "scaffold:target"))
        errors = validate(root, make_proposal())
        assert any("already executed" in error for error in errors)


@pytest.mark.parametrize("kind, expected", (
    ("unrelated", "permitted local boundary"),
    ("revoked", "unknown or revoked"),
    ("unverified", "unknown or revoked"),
    ("foreign", "another problem"),
))
def test_alt_boundary_permission_does_not_admit_invalid_facts(tmp_path, kind, expected) -> None:
    graph = FactGraph(tmp_path)
    fact = Fact.create(
        problem_id="other" if kind == "foreign" else "p",
        author="worker", statement="Proposed boundary F.", proof="Candidate proof."
    )
    if kind != "unverified":
        graph.add_fact(fact)
    if kind == "revoked":
        graph.revoke(fact.fact_id, "Rejected after audit")
    children = (dict(VALID_ALTS[0], premise_fact_ids=[fact.fact_id]), VALID_ALTS[1])
    errors = validate(
        tmp_path, make_proposal(children), graph=graph,
        boundary=() if kind == "unrelated" else (fact.fact_id,),
    )
    assert any(expected in error for error in errors), errors


def test_alt_context_does_not_authorize_a_resolved_unrelated_sibling(tmp_path) -> None:
    make_workspace_with_sibling(tmp_path)
    sibling_fact = FactGraph(tmp_path).list_facts()[0]
    auditor = passing_auditor()
    before = scaffold_text(tmp_path)
    children = (dict(VALID_ALTS[0], premise_fact_ids=[sibling_fact.fact_id]), VALID_ALTS[1])

    rejected = run_alt(tmp_path, alt_builder(children), auditor)

    assert rejected.outcome == "MECHANICAL_REJECT"
    assert any("permitted local boundary" in error for error in rejected.mechanical_errors)
    assert auditor.calls == []
    assert scaffold_text(tmp_path) == before


# --- run_local_redecomposition(operation="add_alternative_route") ---------------


def test_no_useful_route_leaves_graph_unchanged_with_no_route_evidence() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        before = scaffold_text(root)
        auditor = passing_auditor()

        result = run_alt(
            root,
            StubBuilder(BuilderResult(outcome="NO_USEFUL_ROUTE", raw='{"outcome": "NO_USEFUL_ROUTE"}')),
            auditor,
        )

        assert result.outcome == "NO_USEFUL_ROUTE"
        assert scaffold_text(root) == before
        assert auditor.calls == []
        (evidence,) = evidence_files(root)
        assert evidence.name.startswith("no-route-")
        payload = json.loads(evidence.read_text(encoding="utf-8"))
        assert payload["outcome"] == "NO_USEFUL_ROUTE"
        assert payload["applied"] is False
        assert payload["context"]["allowed_operation"] == "ADD_ALTERNATIVE_ROUTE"


def test_need_more_context_leaves_graph_unchanged() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        before = scaffold_text(root)

        result = run_alt(root, StubBuilder(BuilderResult(outcome="NEED_MORE_CONTEXT")), passing_auditor())

        assert result.outcome == "NEED_MORE_CONTEXT"
        assert scaffold_text(root) == before
        (evidence,) = evidence_files(root)
        assert evidence.name.startswith("no-route-")


def test_builder_error_leaves_graph_unchanged() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        before = scaffold_text(root)

        result = run_alt(root, RaisingBuilder(), passing_auditor())

        assert result.outcome == "BUILDER_ERROR"
        assert scaffold_text(root) == before


def test_mechanically_invalid_route_is_rejected_before_the_auditor() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        before = scaffold_text(root)
        cyclic = (
            dict(VALID_ALTS[0], depends_on=["alt-h2"]),
            dict(VALID_ALTS[1], depends_on=["alt-h1"]),
        )
        auditor = passing_auditor()

        result = run_alt(root, alt_builder(cyclic), auditor)

        assert result.outcome == "MECHANICAL_REJECT"
        assert any("cycle" in error for error in result.mechanical_errors)
        assert scaffold_text(root) == before
        assert auditor.calls == []
        (evidence,) = evidence_files(root)
        assert evidence.name.startswith("alt-")


@pytest.mark.parametrize("verdict", ("REVISE", "REJECT"))
def test_auditor_revise_and_reject_leave_graph_unchanged(verdict: str) -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        before = scaffold_text(root)
        auditor = StubAuditor(AuditorResult(verdict=verdict, reasons=("cosmetic route",)))

        result = run_alt(root, alt_builder(), auditor)

        assert result.outcome == f"AUDITOR_{verdict}"
        assert scaffold_text(root) == before


def test_auditor_error_leaves_graph_unchanged() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        before = scaffold_text(root)

        result = run_alt(root, alt_builder(), RaisingAuditor())

        assert result.outcome == "AUDITOR_ERROR"
        assert scaffold_text(root) == before


def apply_valid_route(root: Path) -> RedecompositionResult:
    result = run_alt(root, alt_builder(), passing_auditor())
    assert result.outcome == "APPLIED"
    return result


def test_boundary_fact_is_admitted_through_alt_and_retained_in_fact_closure(tmp_path) -> None:
    graph = FactGraph(tmp_path)
    boundary = graph.add_fact(Fact.create(
        problem_id="p", author="worker", statement="Run-derived boundary F.", proof="Accepted."
    ))
    make_workspace(tmp_path, premise_fact_ids=(boundary.fact_id,))
    children = (dict(VALID_ALTS[0], premise_fact_ids=[boundary.fact_id]), VALID_ALTS[1])
    auditor = passing_auditor()

    applied = run_alt(tmp_path, alt_builder(children), auditor)

    assert applied.outcome == "APPLIED", applied.mechanical_errors
    assert [fact.fact_id for fact in graph.list_facts()] == [boundary.fact_id]
    assert auditor.calls[0][0].verified_boundary == (boundary,)
    worker = GoalEchoWorker()
    solved = solve_scaffold(
        scaffold=ProofScaffold(tmp_path / "scaffold.json"),
        problem=ProblemSpec("p", PROBLEM_STATEMENT),
        registry=ObligationRegistry(tmp_path / "obligations.json"),
        graph=graph, author="worker", worker=worker, verifier=RejectingVerifier(),
    )
    assert solved.status == "SOLVED"
    by_statement = {fact.statement: fact for fact in graph.list_facts()}
    helper = by_statement[VALID_ALTS[0]["goal"]]
    assert helper.predecessors == (boundary.fact_id,)
    assert boundary.statement in worker.premises_seen[worker.goals.index(helper.statement)]
    closure_ids = {fact.fact_id for fact in graph.supporting_closure(by_statement[PROBLEM_STATEMENT].fact_id)}
    assert {boundary.fact_id, helper.fact_id}.issubset(closure_ids)


def test_applied_route_parks_blocked_node_and_keeps_goal_verbatim() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)

        result = apply_valid_route(root)

        assert result.child_node_ids == ("alt-h1", "alt-h2", REROUTED_NODE_ID)
        reloaded = ProofScaffold(root / "scaffold.json")
        blocked = reloaded.get("mid")
        # PARKED, not superseded: the route-of-record row is retained.
        assert blocked.parked_by == result.proposal.proposal_id
        assert blocked.superseded_by is None
        assert blocked.goal == BLOCKED_GOAL
        assert blocked.resolved_by_fact_id is None
        rerouted = reloaded.get(REROUTED_NODE_ID)
        assert rerouted.goal == BLOCKED_GOAL  # G verbatim on route R2
        assert rerouted.depends_on == ("alt-h2",)
        assert rerouted.premise_fact_ids == ()
        assert rerouted.resolved_by_fact_id is None
        assert reloaded.get("target").depends_on == (REROUTED_NODE_ID,)
        for node_id in ("alt-h1", "alt-h2"):
            assert reloaded.get(node_id).resolved_by_fact_id is None

        (evidence,) = evidence_files(root)
        assert evidence.name == f"{result.proposal.proposal_id}.json"
        payload = json.loads(evidence.read_text(encoding="utf-8"))
        assert payload["outcome"] == "APPLIED"
        assert payload["applied"] is True
        post_ids = {node["node_id"] for node in payload["post_patch_nodes"]}
        assert post_ids == {"mid", "alt-h1", "alt-h2", REROUTED_NODE_ID, "target"}


def test_apply_admits_no_facts_and_preserves_attempts_byte_identical() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        attempts_before = attempt_snapshots(root)

        apply_valid_route(root)

        assert attempt_snapshots(root) == attempts_before
        assert FactGraph(root).list_facts() == []
        registry = ObligationRegistry(root / "obligations.json")
        assert [item.obligation_id for item in registry.list()] == ["scaffold:p:mid"]


def test_second_route_run_is_rejected_as_parked_and_evidence_never_overwritten() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        first = apply_valid_route(root)
        first_evidence = Path(first.evidence_path)
        first_content = first_evidence.read_text(encoding="utf-8")
        after_first = scaffold_text(root)

        second = run_alt(root, alt_builder(), passing_auditor())

        assert second.outcome == "MECHANICAL_REJECT"
        assert any("parked" in error for error in second.mechanical_errors)
        assert scaffold_text(root) == after_first
        assert first_evidence.read_text(encoding="utf-8") == first_content
        assert len(evidence_files(root)) == 2
        assert Path(second.evidence_path) != first_evidence


def test_unrelated_graph_regions_stay_byte_identical() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace_with_sibling(root)
        facts_before = {
            path.name: path.read_text(encoding="utf-8")
            for path in sorted((root / "facts").glob("*.md"))
        }
        side_row_before = next(
            node for node in json.loads(scaffold_text(root))["nodes"] if node["node_id"] == "side"
        )

        result = apply_valid_route(root)

        assert result.outcome == "APPLIED"
        facts_after = {
            path.name: path.read_text(encoding="utf-8")
            for path in sorted((root / "facts").glob("*.md"))
        }
        assert facts_after == facts_before
        side_row_after = next(
            node for node in json.loads(scaffold_text(root))["nodes"] if node["node_id"] == "side"
        )
        assert side_row_after == side_row_before


# --- frozen execution path over the patched scaffold ---------------------------


def test_frozen_solver_executes_new_route_then_rerouted_goal_then_target() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        apply_valid_route(root)

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
        # B' is proved with the resolved sink new node as its premise Fact.
        assert worker.premises_seen[2] == ("Helper proposition H2.",)
        assert worker.premises_seen[3] == (BLOCKED_GOAL,)
        assert sorted(fact.statement for fact in FactGraph(root).list_facts()) == [
            "Helper proposition H1.",
            "Helper proposition H2.",
            BLOCKED_GOAL,
            PROBLEM_STATEMENT,
        ]


def test_failed_new_node_stays_open_and_downstream_never_runs() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        apply_valid_route(root)

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
        assert reloaded.get("alt-h1").resolved_by_fact_id is not None
        assert reloaded.get("alt-h2").resolved_by_fact_id is None
        assert reloaded.get(REROUTED_NODE_ID).resolved_by_fact_id is None
        assert reloaded.get("target").resolved_by_fact_id is None
        # The parked route-of-record still carries its unresolved goal.
        assert reloaded.get("mid").resolved_by_fact_id is None
        assert [fact.statement for fact in FactGraph(root).list_facts()] == [
            "Helper proposition H1."
        ]


# --- refinement history (previous_refinement_summary) ---------------------------


def test_previous_refinement_summary_is_built_from_local_refinements() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        _write_json(
            root / "local_refinements" / "split-deadbeefcafe.json",
            {
                "blocked_node_id": "mid",
                "outcome": "APPLIED",
                "proposal": {"obstruction": "Both halves failed jointly."},
            },
        )
        _write_json(
            root / "local_refinements" / "no-cut-20260902T000000000000.json",
            {
                "blocked_node_id": "mid",
                "outcome": "NO_USEFUL_CUT",
                "missing_context": "need the local gap",
            },
        )

        builder = alt_builder()
        run_alt(root, builder, passing_auditor())

        summary = builder.contexts[0].previous_refinement_summary
        assert summary is not None
        assert "[split] APPLIED" in summary
        assert "Both halves failed jointly." in summary
        assert "[no-cut] NO_USEFUL_CUT" in summary
        assert "need the local gap" in summary


def test_refinement_history_is_filtered_to_the_blocked_node() -> None:
    """Context locality: another obligation's refinement evidence never leaks in."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        _write_json(
            root / "local_refinements" / "split-deadbeefcafe.json",
            {
                "blocked_node_id": "mid",
                "outcome": "APPLIED",
                "proposal": {"obstruction": "Both halves failed jointly."},
            },
        )
        _write_json(
            root / "local_refinements" / "alt-20260902T000000000000.json",
            {
                "blocked_node_id": "other-node",
                "outcome": "APPLIED",
                "proposal": {"obstruction": "Unrelated obstruction from another obligation."},
            },
        )

        builder = alt_builder()
        run_alt(root, builder, passing_auditor())

        summary = builder.contexts[0].previous_refinement_summary
        assert summary is not None
        assert "[split] APPLIED" in summary
        assert "Both halves failed jointly." in summary
        assert "other-node" not in summary
        assert "Unrelated obstruction" not in summary


def test_decline_history_falls_back_to_builder_raw_reasons() -> None:
    """N2A/N2B decline evidence has no normalized proposal/missing_context;
    the reasons live in the raw builder output JSON."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        _write_json(
            root / "local_refinements" / "no-split-20260901T000000000000.json",
            {
                "blocked_node_id": "mid",
                "outcome": "NEED_MORE_CONTEXT",
                "builder_raw": json.dumps(
                    {
                        "outcome": "NEED_MORE_CONTEXT",
                        "obstruction": "failures establish only equivalence",
                        "missing_context": "no verified predecessor facts",
                    }
                ),
            },
        )

        builder = alt_builder()
        run_alt(root, builder, passing_auditor())

        summary = builder.contexts[0].previous_refinement_summary
        assert summary is not None
        assert "[no-split] NEED_MORE_CONTEXT" in summary
        assert "failures establish only equivalence" in summary
        assert "missing: no verified predecessor facts" in summary


def test_previous_refinement_summary_is_none_without_history() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        builder = alt_builder()
        run_alt(root, builder, passing_auditor())
        assert builder.contexts[0].previous_refinement_summary is None


# --- Codex agent adapters in add_alternative_route mode -----------------------

from research.agents import LocalGraphBuilder, StructuralAuditor  # noqa: E402


ALT_AUDIT_CHECKS = (
    "target_preserved",
    "assumptions_preserved",
    "no_hidden_circularity",
    "new_route_is_materially_different",
    "new_route_is_not_cosmetic_reformulation",
    "new_intermediates_are_coherent",
    "new_intermediates_are_genuinely_narrower",
    "route_plausibly_recovers_target_obligation",
    "route_is_mathematically_meaningful",
)


class RecordingCodex:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls = []

    def invoke(self, *, prompt, schema, label):
        self.calls.append((prompt, schema, label))
        return self.response


def captured_context(root: Path, *, with_sibling: bool = False):
    if with_sibling:
        make_workspace_with_sibling(root)
    else:
        make_workspace(root)
    builder = StubBuilder(BuilderResult(outcome="NO_USEFUL_ROUTE"))
    run_alt(root, builder, passing_auditor())
    return builder.contexts[0]


def test_alt_builder_prompt_demands_materially_different_route() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        context = captured_context(root)
        codex = RecordingCodex(json.loads(alt_raw()))

        builder = LocalGraphBuilder(codex, operation="add_alternative_route")
        result = builder.propose(context)

        assert result.outcome == "ADD_ALTERNATIVE_ROUTE"
        assert isinstance(result.proposal, AlternativeRouteProposal)
        assert [child.node_id for child in result.proposal.children] == ["alt-h1", "alt-h2"]
        assert result.proposal.failed_route_summary == "R1 has no further honest step."
        prompt, schema, label = codex.calls[0]
        assert label == "local_graph_builder"
        # The blocked goal G is shown verbatim and described as re-routed.
        assert BLOCKED_GOAL in prompt
        assert "verbatim" in prompt
        assert "re-routed" in prompt
        # The current route is exhausted; the new route must differ materially.
        assert "exhausted" in prompt
        # New route obligations are UNVERIFIED, never claimed true.
        assert "UNVERIFIED" in prompt
        assert "NO_USEFUL_ROUTE" in prompt
        assert "NEED_MORE_CONTEXT" in prompt
        # Failure evidence is carried (verifier feedback from the FAIL attempt).
        assert "scripted verdict" in prompt
        # No prior refinement history in this workspace.
        assert "Prior refinement outcomes" not in prompt
        # The exact prompt is captured for the evidence bundle.
        assert builder.last_prompt == prompt
        # Strict schema, no bare objects (the N2A bare-checks bug class).
        assert schema["additionalProperties"] is False
        assert schema["properties"]["new_nodes"]["items"]["additionalProperties"] is False
        assert schema["properties"]["outcome"]["enum"] == [
            "ADD_ALTERNATIVE_ROUTE",
            "NO_USEFUL_ROUTE",
            "NEED_MORE_CONTEXT",
        ]
        assert "why_current_route_is_exhausted" in schema["required"]


def test_alt_builder_prompt_renders_prior_refinement_history() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        _write_json(
            root / "local_refinements" / "split-deadbeefcafe.json",
            {
                "blocked_node_id": "mid",
                "outcome": "APPLIED",
                "proposal": {"obstruction": "Both halves failed jointly."},
            },
        )
        builder = StubBuilder(BuilderResult(outcome="NO_USEFUL_ROUTE"))
        run_alt(root, builder, passing_auditor())
        context = builder.contexts[0]
        codex = RecordingCodex(json.loads(alt_raw()))

        LocalGraphBuilder(codex, operation="add_alternative_route").propose(context)

        prompt, _, _ = codex.calls[0]
        assert "Prior refinement outcomes" in prompt
        assert "[split] APPLIED" in prompt


def test_alt_builder_prompt_stays_local_to_the_blocked_region() -> None:
    """Context locality: the sibling branch's goal/proof text never leaks in."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        context = captured_context(root, with_sibling=True)
        codex = RecordingCodex(json.loads(alt_raw()))

        builder = LocalGraphBuilder(codex, operation="add_alternative_route")
        result = builder.propose(context)

        assert result.outcome == "ADD_ALTERNATIVE_ROUTE"
        prompt, _, _ = codex.calls[0]
        assert SIDE_GOAL not in prompt
        assert SIDE_PROOF not in prompt
        assert BLOCKED_GOAL in prompt


def test_alt_auditor_prompt_restricted_fields_and_nine_checks() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        context = captured_context(root)
        proposal = parse_alternative_route_output(alt_raw(), blocked_node_id="mid").proposal
        response = {
            "verdict": "PASS",
            "reasons": ["route R2 is a materially different architecture"],
            "checks": {name: True for name in ALT_AUDIT_CHECKS},
        }
        codex = RecordingCodex(response)

        auditor = StructuralAuditor(codex, operation="add_alternative_route")
        result = auditor.audit(context, proposal)

        assert result.verdict == "PASS"
        assert result.reasons == ("route R2 is a materially different architecture",)
        assert result.checks["new_route_is_materially_different"] is True
        prompt, schema, label = codex.calls[0]
        assert label == "structural_auditor"
        assert PROBLEM_STATEMENT in prompt
        assert BLOCKED_GOAL in prompt
        assert "The direct computation stalls." in prompt  # obstruction
        assert "R2 reaches G by a different mechanism." in prompt  # expected_effect
        # After-graph: B PARKED (route-of-record), new nodes listed, B' carries
        # G verbatim off the sink new node, downstream rewired onto B'.
        assert "PARKED" in prompt
        assert "SUPERSEDED" not in prompt
        assert "alt-h1" in prompt and "alt-h2" in prompt
        assert REROUTED_NODE_ID in prompt
        assert "MUST be REJECTed" in prompt
        # The auditor never sees proof text or candidate text.
        assert "A candidate proof" not in prompt
        # No prior refinement history in this workspace.
        assert "Prior refinement outcomes" not in prompt
        # The exact prompt is captured for the evidence bundle.
        assert auditor.last_prompt == prompt
        # Nine enumerated boolean checks, all required, strict objects.
        checks_schema = schema["properties"]["checks"]
        assert checks_schema["additionalProperties"] is False
        assert sorted(checks_schema["required"]) == sorted(ALT_AUDIT_CHECKS)
        assert all(
            checks_schema["properties"][name] == {"type": "boolean"}
            for name in ALT_AUDIT_CHECKS
        )
        assert schema["additionalProperties"] is False


def test_alt_auditor_prompt_renders_prior_refinement_history() -> None:
    """§21: the auditor sees the N2A/N2B outcomes for this obligation."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        _write_json(
            root / "local_refinements" / "no-cut-20260902T000000000000.json",
            {
                "blocked_node_id": "mid",
                "outcome": "NO_USEFUL_CUT",
                "missing_context": "no credible cut along the compactness route",
            },
        )
        builder = StubBuilder(BuilderResult(outcome="NO_USEFUL_ROUTE"))
        run_alt(root, builder, passing_auditor())
        context = builder.contexts[0]
        assert context.previous_refinement_summary is not None
        proposal = parse_alternative_route_output(alt_raw(), blocked_node_id="mid").proposal
        response = {
            "verdict": "REJECT",
            "reasons": ["route is R1 in disguise"],
            "checks": {name: False for name in ALT_AUDIT_CHECKS},
        }
        codex = RecordingCodex(response)

        StructuralAuditor(codex, operation="add_alternative_route").audit(context, proposal)

        prompt, _, _ = codex.calls[0]
        assert "Prior refinement outcomes on this obligation" in prompt
        assert "[no-cut] NO_USEFUL_CUT" in prompt
        assert "no credible cut along the compactness route" in prompt


def test_split_and_cut_prompts_do_not_render_refinement_history() -> None:
    """N2A/N2B prompt regression: prior-history rendering is alt-route only."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        _write_json(
            root / "local_refinements" / "alt-deadbeefcafe.json",
            {
                "blocked_node_id": "mid",
                "outcome": "APPLIED",
                "proposal": {"obstruction": "R1 exhausted."},
            },
        )
        builder = StubBuilder(BuilderResult(outcome="NO_USEFUL_ROUTE"))
        run_alt(root, builder, passing_auditor())
        context = builder.contexts[0]
        assert context.previous_refinement_summary is not None
        split_response = {
            "outcome": "NO_USEFUL_SPLIT",
            "obstruction": "",
            "expected_effect": "",
            "new_nodes": [],
            "missing_context": "",
        }
        cut_response = {
            "outcome": "NO_USEFUL_CUT",
            "obstruction": "",
            "expected_effect": "",
            "new_nodes": [],
            "missing_context": "",
        }

        split_codex = RecordingCodex(split_response)
        LocalGraphBuilder(split_codex).propose(context)  # default: N2A split
        split_prompt = split_codex.calls[0][0]
        assert "Prior refinement outcomes" not in split_prompt

        cut_codex = RecordingCodex(cut_response)
        LocalGraphBuilder(cut_codex, operation="insert_cut_set").propose(context)
        cut_prompt = cut_codex.calls[0][0]
        assert "Prior refinement outcomes" not in cut_prompt
