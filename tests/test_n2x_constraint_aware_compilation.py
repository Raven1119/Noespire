"""N2X mechanical-constraint-aware patch compilation — contract tests (§22).

Single variable over the frozen N2U/N2V pipeline: the Patch Builder receives
the deterministic compilation environment the Mechanical Validator will
enforce (the declared problem-premise Fact ID set) at FIRST compile time.
No repair, no resampling, no new operator, no validator change, no strategy
change, no NodeSolver.

All tests are model-free: fake codex / scripted components.
"""

from __future__ import annotations

import inspect
import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

REPO_ROOT = Path(__file__).resolve().parents[1]
for rel in (
    "src",
    "experiments/n2l_closed_book_long_horizon",
    "experiments/n2m_horizon_handoff",
    "experiments/n2p_mathematical_strategist",
    "experiments/n2q_auditor_guided_revision",
    "experiments/n2r_strategist_stability",
    "experiments/n2s_strategy_patch_separation",
    "experiments/n2t_strategy_patch_compilation",
    "experiments/n2u_live_two_stage",
    "experiments/n2w_mechanical_patch_repair",
    "experiments/n2x_constraint_aware_compilation",
):
    sys.path.insert(0, str(REPO_ROOT / rel))

from research.graph import FactGraph  # noqa: E402
from research.local_refinement import (  # noqa: E402
    AuditorResult,
    run_local_redecomposition,
    validate_cut_set_proposal,
)
from research.obligation import ObligationRegistry  # noqa: E402
from research.problem import ProblemSpec  # noqa: E402
from research.scaffold import ProofScaffold, ScaffoldNode  # noqa: E402

import patch_builder as n2t_patch_builder  # noqa: E402  (N2T, frozen)
from patch_builder import (  # noqa: E402
    PATCH_SCHEMA,
    PatchBuildResult,
    parse_patch_build_output,
    patch_builder_prompt,
)
import constrained_builder as n2x  # noqa: E402  (module under test)
from constrained_builder import (  # noqa: E402
    ConstraintAwarePatchBuilder,
    compilation_constraints_block,
    constrained_patch_builder_prompt,
)
import two_stage_driver  # noqa: E402  (N2U driver)
from two_stage_driver import run_patch_stages  # noqa: E402

BLOCKED = "mid"
PID = "p"
STATEMENT = "Lemma M implies theorem T."
RUN02_ERROR = "premise_fact_ids are not declared problem premises"


# --- fixtures -------------------------------------------------------------------


def _context():
    node = lambda nid, goal, deps=(): SimpleNamespace(  # noqa: E731
        node_id=nid, goal=goal, depends_on=tuple(deps), premise_fact_ids=()
    )
    return SimpleNamespace(
        original_problem="Prove T.",
        blocked_obligation=SimpleNamespace(goal="Lemma M implies theorem T.", premises=()),
        blocked_node=node(BLOCKED, STATEMENT),
        local_nodes=[node("target", STATEMENT, (BLOCKED,))],
        verified_boundary=[
            SimpleNamespace(fact_id="fdeadbeef", statement="A run-derived verified Fact.")
        ],
        attempts=[],
        previous_refinement_summary="",
        downstream_intent="",
    )


def _sketch(operator="INSERT_CUT_SET"):
    return SimpleNamespace(
        obstruction="Obs.",
        evidence=("e1",),
        mathematical_idea="Use an entropy decrement.",
        why_this_reduces_difficulty="Isolates analytic content.",
        operator=operator,
        why_current_route_is_exhausted="Route exhausted.",
        decline_reason="",
        candidate_claims=("Claim one.", "Claim two."),
        raw="fixture",
    )


class _FakeCodex:
    """Records the invocation; returns a fixed schema-shaped response."""

    def __init__(self, payload) -> None:
        self.payload = payload
        self.calls = []

    def invoke(self, *, prompt, schema, label):
        self.calls.append({"prompt": prompt, "schema": schema, "label": label})
        return self.payload


def _patch_payload(nodes):
    return {"compilation_decline": False, "decline_reason": "", "new_nodes": nodes}


def _two_nodes():
    return [
        {"node_id": "h1", "goal": "Helper lemma one.",
         "depends_on": [], "premise_fact_ids": []},
        {"node_id": "h2", "goal": "Helper lemma two.",
         "depends_on": ["h1"], "premise_fact_ids": []},
    ]


# --- constraints block content (§22.1/2/5) ---------------------------------------


def test_constraints_block_matches_validator_premise_environment() -> None:
    """§22.1/§4: the block enumerates exactly the IDs the validator will
    enforce; the driver lineage passes the validator's default (())."""
    block = compilation_constraints_block(("abc123", "def456"))
    assert "abc123" in block and "def456" in block
    empty = compilation_constraints_block(())
    assert "abc123" not in empty
    assert "empty" in empty  # explicit emptiness disclosure
    # The validator-side environment in this lineage is the run_local_rede-
    # composition default; the runner wires the builder with the same value.
    signature = inspect.signature(run_local_redecomposition)
    assert signature.parameters["problem_premise_fact_ids"].default == ()


def test_run_derived_facts_not_listed_as_legal_premises() -> None:
    """§22.2: verified run-derived Facts visible in the context are NOT
    presented as legal premises when the declared set is empty."""
    prompt = constrained_patch_builder_prompt(_context(), _sketch(), ())
    boundary_line = "fdeadbeef"  # present as context (verified boundary)...
    assert boundary_line in prompt
    block = prompt[prompt.index("MECHANICAL COMPILATION CONSTRAINTS"):]
    assert "fdeadbeef" not in block  # ...but not as a legal premise
    assert "NOT a\n  declared problem premise" in block or "not a declared" in block.lower()


def test_treatment_never_sees_previous_mechanical_failure() -> None:
    """§22.5/§5/§8: the treatment prompt contains no trace of the run_02
    failure — no diagnostics, no failed node IDs, no repair advice."""
    prompt = constrained_patch_builder_prompt(_context(), _sketch(), ())
    assert RUN02_ERROR not in prompt
    assert "separated_one_edge_entropy_decrement" not in prompt
    assert "4d1b3650" not in prompt
    assert "sibling dependencies instead" not in prompt  # N2W hint banned (§6)
    assert "diagnostics" not in prompt.lower()


# --- prompt / schema identity (§22.3/4/6/10) --------------------------------------


def test_treatment_is_n2t_prompt_plus_constraints_block() -> None:
    """§22.4/§3: the base N2T prompt is preserved byte-identical; the only
    change is the inserted constraints block before the return instruction."""
    context, sketch = _context(), _sketch()
    base = patch_builder_prompt(context, sketch)
    treated = constrained_patch_builder_prompt(context, sketch, ())
    marker = "\nReturn ONLY the JSON object:"
    head, _, tail = base.partition(marker)
    assert treated == (
        head + "\n" + compilation_constraints_block(()) + marker + tail
    )
    # Strategy sections survive verbatim.
    assert sketch.mathematical_idea in treated
    assert "Claim one." in treated


def test_builder_cannot_change_operator_and_validator_untouched() -> None:
    """§22.3/6/10: frozen PATCH_SCHEMA carries no operator field; the frozen
    src validator is used, not reimplemented; exactly three operators."""
    assert "operator" not in PATCH_SCHEMA["properties"]
    assert not hasattr(n2x, "validate_cut_set_proposal")
    assert n2x.parse_patch_build_output is parse_patch_build_output
    assert two_stage_driver.run_local_redecomposition is run_local_redecomposition
    assert set(two_stage_driver._OPERATION) == {
        "SPLIT", "INSERT_CUT_SET", "ADD_ALTERNATIVE_ROUTE",
    }
    assert validate_cut_set_proposal.__module__ == "research.local_refinement"


def test_constraint_aware_builder_invocation() -> None:
    """The builder wraps the frozen N2T contract: same schema, same parse,
    constraints block present in the prompt actually sent."""
    codex = _FakeCodex(_patch_payload(_two_nodes()))
    builder = ConstraintAwarePatchBuilder(codex, problem_premise_fact_ids=())
    result = builder.compile(_context(), _sketch())
    assert isinstance(result, PatchBuildResult)
    assert not result.compilation_decline
    call = codex.calls[0]
    assert call["schema"] is PATCH_SCHEMA
    assert "MECHANICAL COMPILATION CONSTRAINTS" in call["prompt"]
    assert builder.last_prompt == call["prompt"]


# --- pipeline behavior with the seam (§22.7/8/9) -----------------------------------


class _ScriptedGate:
    def audit(self, packet):
        return {"strategy_class": "PLAUSIBLE_STRATEGY", "reasons": ["fixture"]}


class _ScriptedFidelity:
    def audit(self, sketch, patch_nodes, operator):
        return {"strategy_fidelity": "FAITHFUL", "operator_check": "OPERATOR_PRESERVED",
                "claim_fidelity": [], "reasons": ["fixture"]}


class _PassAuditor:
    def __init__(self):
        self.calls = 0

    def audit(self, context, proposal, *, effort=None, timeout=None):
        self.calls += 1
        return AuditorResult(verdict="PASS", reasons=("fixture",))


def _workspace(root: Path) -> Path:
    problem_dir = root / "workspace" / PID
    problem_dir.mkdir(parents=True)
    ProofScaffold.create(
        problem_dir / "scaffold.json",
        problem=ProblemSpec(PID, STATEMENT),
        target_node_id="target",
        nodes=(
            ScaffoldNode(BLOCKED, STATEMENT),
            ScaffoldNode("target", STATEMENT, depends_on=(BLOCKED,)),
        ),
    )
    ObligationRegistry(problem_dir / "obligations.json")
    return problem_dir


def _run_stages(root, builder):
    return run_patch_stages(
        root,
        problem_id=PID,
        frontier=BLOCKED,
        context=_context(),
        sketch=_sketch(),
        gate=_ScriptedGate(),
        fidelity=_ScriptedFidelity(),
        patch_builder=builder,
        reviser=None,
        auditor_for=lambda operation: _PassAuditor(),
        # N2X: repair disabled (§2/§15) — mechanical_repair stays None.
    )


def test_mechanical_fail_stops_without_repair() -> None:
    """§22.7/§15: under N2X the N2W repair seam is disabled — a Mechanical
    FAIL is immediately terminal."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        bad = _FakeCodex(_patch_payload([
            {"node_id": "h1", "goal": "Helper lemma one.",
             "depends_on": [], "premise_fact_ids": []},
            {"node_id": "h2", "goal": "Helper lemma two.",
             "depends_on": ["h1"], "premise_fact_ids": ["run-derived-fact"]},
        ]))
        episode, evidence, counts = _run_stages(
            root, ConstraintAwarePatchBuilder(bad)
        )
        assert episode["outcome"] == "MECHANICAL_FAIL"
        assert "mechanical_repair" not in episode
        assert counts["repair"] == 0
        assert any(RUN02_ERROR in e for e in episode["mechanical_errors"])
        assert [n.node_id for n in ProofScaffold(root / "scaffold.json").list_nodes()] == [
            BLOCKED, "target",
        ]


def test_treatment_pipeline_writes_no_facts_and_calls_no_solver() -> None:
    """§22.8/9/§16: a successful constraint-aware compile applies the patch
    but admits no Facts; run_patch_stages has no solver surface at all."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        codex = _FakeCodex(_patch_payload(_two_nodes()))
        episode, evidence, counts = _run_stages(
            root, ConstraintAwarePatchBuilder(codex)
        )
        assert episode["outcome"] == "PATCH_APPLIED"
        assert episode["facts_admitted_by_refinement"] == 0
        assert FactGraph(root).list_facts() == []
    signature = inspect.signature(run_patch_stages)
    assert "worker" not in signature.parameters
    assert "verifier" not in signature.parameters
