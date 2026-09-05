"""N2Y — local verified boundary Fact dependencies for INSERT_CUT_SET.

``premise_fact_ids`` on a cut are proof predecessors. N2Y widens the legal
set from "declared problem premises only" to "declared problem premises UNION
verifier-accepted Facts on the current local refinement boundary". Truth
boundary is unchanged: only verifier-accepted, non-revoked, same-problem
Facts qualify, and predecessor lineage flows into the admitted FactGraph
exactly as before. SPLIT / ADD_ALTERNATIVE_ROUTE semantics are untouched.

Deterministic: stub builders/auditors, fake worker/verifier — no Codex, no
network, no Docker.
"""

from pathlib import Path
from tempfile import TemporaryDirectory

import json

from research.fact import CandidateFact, Fact
from research.graph import FactGraph
from research.obligation import ObligationRegistry
from research.pipeline import VerificationResult
from research.problem import ProblemSpec
from research.scaffold import ProofScaffold, ScaffoldNode, solve_scaffold

from research.local_refinement import (
    AuditorResult,
    BuilderResult,
    CutSetProposal,
    parse_cut_set_output,
    run_local_redecomposition,
    validate_cut_set_proposal,
)


PROBLEM_STATEMENT = "Target theorem T."
BLOCKED_GOAL = "Intermediate lemma M."

VALID_CUTS = (
    {"node_id": "cut-h1", "goal": "Helper proposition H1.", "depends_on": [], "premise_fact_ids": []},
    {"node_id": "cut-h2", "goal": "Helper proposition H2.", "depends_on": ["cut-h1"], "premise_fact_ids": []},
)


def scaffold_nodes() -> tuple[ScaffoldNode, ...]:
    return (
        ScaffoldNode("mid", BLOCKED_GOAL),
        ScaffoldNode("target", PROBLEM_STATEMENT, depends_on=("mid",)),
    )


def cut_raw(children=VALID_CUTS) -> str:
    return json.dumps(
        {
            "outcome": "INSERT_CUT_SET",
            "obstruction": "The direct route stalls on the same step.",
            "expected_effect": "The cuts bypass the stuck step.",
            "new_nodes": list(children),
            "missing_context": "",
        }
    )


def make_proposal(children=VALID_CUTS) -> CutSetProposal:
    return parse_cut_set_output(cut_raw(children), blocked_node_id="mid").proposal


def validate(
    root: Path,
    proposal: CutSetProposal,
    *,
    premises=(),
    boundary=(),
    graph=None,
) -> tuple:
    return validate_cut_set_proposal(
        proposal=proposal,
        nodes=scaffold_nodes(),
        target_node_id="target",
        problem_id="p",
        problem_premise_fact_ids=premises,
        obligations=ObligationRegistry(root / "obligations.json"),
        graph=graph if graph is not None else FactGraph(root),
        allowed_boundary_fact_ids=boundary,
    )


def add_fact(graph: FactGraph, statement: str, problem_id: str = "p") -> Fact:
    return graph.add_fact(
        Fact.create(problem_id=problem_id, author="worker", statement=statement, proof="Accepted.")
    )


# --- validator contract ------------------------------------------------------


def test_declared_problem_premise_fact_still_allowed() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        graph = FactGraph(root)
        base = add_fact(graph, "Base fact.")
        boundary_fact = add_fact(graph, "Boundary fact.")
        children = (
            dict(VALID_CUTS[0], premise_fact_ids=[base.fact_id]),
            VALID_CUTS[1],
        )
        errors = validate(
            root,
            make_proposal(children),
            premises=(base.fact_id,),
            boundary=(boundary_fact.fact_id,),
            graph=graph,
        )
        assert errors == ()


def test_accepted_local_boundary_fact_allowed() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        graph = FactGraph(root)
        derived = add_fact(graph, "Run-derived verified fact.")
        children = (
            dict(VALID_CUTS[0], premise_fact_ids=[derived.fact_id]),
            VALID_CUTS[1],
        )
        errors = validate(root, make_proposal(children), boundary=(derived.fact_id,), graph=graph)
        assert errors == ()


def test_accepted_fact_outside_local_boundary_rejected() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        graph = FactGraph(root)
        outsider = add_fact(graph, "Accepted but outside the local boundary.")
        children = (
            dict(VALID_CUTS[0], premise_fact_ids=[outsider.fact_id]),
            VALID_CUTS[1],
        )
        errors = validate(root, make_proposal(children), graph=graph)
        assert any("local boundary" in error or "declared problem premises" in error for error in errors)


def test_revoked_boundary_fact_rejected() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        graph = FactGraph(root)
        revoked = add_fact(graph, "Fact later revoked.")
        graph.revoke(revoked.fact_id, "scripted revocation")
        children = (
            dict(VALID_CUTS[0], premise_fact_ids=[revoked.fact_id]),
            VALID_CUTS[1],
        )
        errors = validate(root, make_proposal(children), boundary=(revoked.fact_id,), graph=graph)
        assert any("unknown or revoked" in error for error in errors)


def test_nonexistent_boundary_fact_rejected() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        children = (
            dict(VALID_CUTS[0], premise_fact_ids=["f" * 16]),
            VALID_CUTS[1],
        )
        errors = validate(root, make_proposal(children), boundary=("f" * 16,))
        assert any("unknown or revoked" in error for error in errors)


def test_open_obligation_id_cannot_masquerade_as_fact() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        obligation_id = "obligation:mid"
        children = (
            dict(VALID_CUTS[0], premise_fact_ids=[obligation_id]),
            VALID_CUTS[1],
        )
        # Not on the boundary: rejected as outside the permitted set.
        errors = validate(root, make_proposal(children))
        assert any("local boundary" in error or "declared problem premises" in error for error in errors)
        # Even if a caller wrongly lists it as a boundary id, it is not a Fact.
        errors = validate(root, make_proposal(children), boundary=(obligation_id,))
        assert any("unknown or revoked" in error for error in errors)


def test_depends_on_still_restricted_to_sibling_cuts() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        children = (
            dict(VALID_CUTS[0], depends_on=["mid"]),
            VALID_CUTS[1],
        )
        errors = validate(root, make_proposal(children))
        assert any("non-cut node" in error for error in errors)


# --- run_local_redecomposition plumbing --------------------------------------


class GoalEchoWorker:
    def __init__(self) -> None:
        self.goals = []
        self.premises_seen = []

    def propose(self, *, problem, existing_facts, subgoal, repair_context=None):
        goal = subgoal.split("Goal:\n", 1)[1]
        self.goals.append(goal)
        self.premises_seen.append(tuple(fact.fact_id for fact in existing_facts))
        return CandidateFact(
            goal,
            f"A candidate proof of {goal}",
            tuple(fact.fact_id for fact in existing_facts),
        )


class ScriptedVerifier:
    def __init__(self, rejected=()) -> None:
        self.rejected = set(rejected)

    def verify(self, problem, candidate, predecessors):
        return VerificationResult(
            candidate.statement not in self.rejected, "scripted verdict"
        )


class StubBuilder:
    def __init__(self, result: BuilderResult) -> None:
        self.result = result

    def propose(self, context, *, effort=None, timeout=None):
        return self.result


class StubAuditor:
    def __init__(self, result: AuditorResult) -> None:
        self.result = result

    def audit(self, context, proposal, *, effort=None, timeout=None):
        return self.result


def make_boundary_workspace(root: Path) -> Fact:
    """Scaffold mid -> target where mid already stands on run-derived Fact F
    (NOT a declared problem premise); mid attempts once and is rejected, so F
    lands on the local verified boundary of the refinement context."""
    problem = ProblemSpec("p", PROBLEM_STATEMENT)
    graph = FactGraph(root)
    derived = add_fact(graph, "Run-derived verified fact F.")
    scaffold = ProofScaffold.create(
        root / "scaffold.json",
        problem=problem,
        target_node_id="target",
        nodes=(
            ScaffoldNode("mid", BLOCKED_GOAL, premise_fact_ids=(derived.fact_id,)),
            ScaffoldNode("target", PROBLEM_STATEMENT, depends_on=("mid",)),
        ),
    )
    result = solve_scaffold(
        scaffold=scaffold,
        problem=problem,
        registry=ObligationRegistry(root / "obligations.json"),
        graph=graph,
        author="worker",
        worker=GoalEchoWorker(),
        verifier=ScriptedVerifier({BLOCKED_GOAL}),
    )
    assert result.status == "BLOCKED"
    return derived


def apply_boundary_cut(root: Path, derived: Fact) -> None:
    children = (
        VALID_CUTS[0],
        dict(VALID_CUTS[1], premise_fact_ids=[derived.fact_id]),
    )
    builder = StubBuilder(
        BuilderResult(
            "INSERT_CUT_SET",
            proposal=parse_cut_set_output(cut_raw(children), blocked_node_id="mid").proposal,
            raw=cut_raw(children),
        )
    )
    result = run_local_redecomposition(
        root,
        problem_id="p",
        blocked_node_id="mid",
        builder=builder,
        auditor=StubAuditor(AuditorResult("PASS")),
        operation="insert_cut_set",
    )
    assert result.outcome == "APPLIED", result.mechanical_errors


def test_redecomposition_passes_verified_boundary_to_cut_validator() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        derived = make_boundary_workspace(root)
        # No declared problem premises: only the boundary plumbing can admit F.
        apply_boundary_cut(root, derived)


# --- end-to-end lineage / closure --------------------------------------------


def test_boundary_fact_dependency_flows_into_admitted_fact_and_closure() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        derived = make_boundary_workspace(root)
        apply_boundary_cut(root, derived)

        worker = GoalEchoWorker()
        result = solve_scaffold(
            scaffold=ProofScaffold(root / "scaffold.json"),
            problem=ProblemSpec("p", PROBLEM_STATEMENT),
            registry=ObligationRegistry(root / "obligations.json"),
            graph=FactGraph(root),
            author="worker",
            worker=worker,
            verifier=ScriptedVerifier(),
        )
        assert result.status == "SOLVED"

        graph = FactGraph(root)
        by_statement = {fact.statement: fact for fact in graph.list_facts()}
        h2 = by_statement["Helper proposition H2."]
        # Hard invariant: the verified boundary Fact is a recorded predecessor.
        assert derived.fact_id in h2.predecessors
        # The worker actually saw F as a premise while solving cut-h2.
        h2_call = worker.goals.index("Helper proposition H2.")
        assert derived.fact_id in worker.premises_seen[h2_call]
        # Supporting closure of the downstream chain contains F.
        target_fact = by_statement[PROBLEM_STATEMENT]
        closure = graph.supporting_closure(target_fact.fact_id)
        closure_ids = {fact.fact_id for fact in closure}
        assert derived.fact_id in closure_ids
        assert h2.fact_id in closure_ids
