"""N2P mathematical local strategist — deterministic contract tests (§37).

Seams under test (pre-agreed by the task card):
- strategist.py: unified diagnose -> strategy -> operator -> patch contract;
  parses/compiles into the three existing operator proposals or DECLINE;
  operator is never preselected; output enum is exactly the three frozen
  operators + DECLINE.
- treatment_driver.py: one strategist call per frontier (K=1), no fallback
  escalation, DECLINE / auditor REJECT stop the frontier without mutation;
  Facts still only come from worker -> verifier.

All tests are model-free: fake invokers/workers/verifiers/auditors only.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "experiments" / "n2l_closed_book_long_horizon"))
sys.path.insert(0, str(REPO_ROOT / "experiments" / "n2m_horizon_handoff"))
sys.path.insert(0, str(REPO_ROOT / "experiments" / "n2p_mathematical_strategist"))

from research.local_refinement import (  # noqa: E402
    AlternativeRouteProposal,
    CutSetProposal,
    SplitProposal,
)

from strategist import (  # noqa: E402
    OPERATORS,
    compile_to_builder_result,
    parse_strategist_output,
)

BLOCKED = "mid"


def _strategist_json(operator: str, **overrides) -> str:
    payload = {
        "obstruction": "The direct route stalls at the local horizon.",
        "evidence": ["attempt-1 verifier: gap too wide"],
        "mathematical_idea": "Introduce two helper lemmas that split the gap.",
        "why_this_reduces_difficulty": "Each helper is strictly weaker than the goal.",
        "operator": operator,
        "why_current_route_is_exhausted": "",
        "decline_reason": "",
        "new_nodes": [
            {"node_id": "h1", "goal": "Helper lemma one.",
             "depends_on": [], "premise_fact_ids": []},
            {"node_id": "h2", "goal": "Helper lemma two.",
             "depends_on": ["h1"], "premise_fact_ids": []},
        ],
    }
    payload.update(overrides)
    return json.dumps(payload)


# --- §37.3/15 + compile (§37.4/5/6) ----------------------------------------------


def test_output_enum_is_three_operators_plus_decline() -> None:
    """§37.3/§37.15/§4: exactly SPLIT | CUT | ALT_ROUTE | DECLINE."""
    assert set(OPERATORS) == {
        "SPLIT",
        "INSERT_CUT_SET",
        "ADD_ALTERNATIVE_ROUTE",
        "DECLINE",
    }
    with pytest.raises(ValueError):
        parse_strategist_output(_strategist_json("REWIRE"), blocked_node_id=BLOCKED)


def test_split_proposal_compiles_into_split_patch() -> None:
    """§37.4: a SPLIT decision compiles into the frozen SPLIT proposal."""
    result = parse_strategist_output(_strategist_json("SPLIT"), blocked_node_id=BLOCKED)
    built = compile_to_builder_result(result, blocked_node_id=BLOCKED)
    assert built.outcome == "SPLIT"
    assert type(built.proposal) is SplitProposal
    assert [c.node_id for c in built.proposal.children] == ["h1", "h2"]


def test_cut_proposal_compiles_into_cut_patch() -> None:
    """§37.5: INSERT_CUT_SET compiles into the frozen CUT proposal."""
    result = parse_strategist_output(
        _strategist_json("INSERT_CUT_SET"), blocked_node_id=BLOCKED
    )
    built = compile_to_builder_result(result, blocked_node_id=BLOCKED)
    assert built.outcome == "INSERT_CUT_SET"
    assert type(built.proposal) is CutSetProposal


def test_alt_route_proposal_compiles_into_alt_patch() -> None:
    """§37.6: ADD_ALTERNATIVE_ROUTE compiles with the N2C fields carried."""
    result = parse_strategist_output(
        _strategist_json(
            "ADD_ALTERNATIVE_ROUTE",
            why_current_route_is_exhausted="R1 terminates in the target theorem.",
        ),
        blocked_node_id=BLOCKED,
    )
    built = compile_to_builder_result(result, blocked_node_id=BLOCKED)
    assert built.outcome == "ADD_ALTERNATIVE_ROUTE"
    assert type(built.proposal) is AlternativeRouteProposal
    assert built.proposal.failed_route_summary == "R1 terminates in the target theorem."


def test_decline_carries_reason_and_no_patch() -> None:
    """§37.7 (parse level)/§13: DECLINE keeps its reason and builds no patch."""
    result = parse_strategist_output(
        _strategist_json(
            "DECLINE",
            new_nodes=[],
            decline_reason="Evidence shows the goal is theorem-strength; no honest split.",
        ),
        blocked_node_id=BLOCKED,
    )
    assert result.operator == "DECLINE"
    assert "theorem-strength" in result.decline_reason


def test_non_decline_requires_new_nodes() -> None:
    with pytest.raises(ValueError):
        parse_strategist_output(
            _strategist_json("SPLIT", new_nodes=[]), blocked_node_id=BLOCKED
        )


def test_malformed_output_raises() -> None:
    with pytest.raises(ValueError):
        parse_strategist_output("not json", blocked_node_id=BLOCKED)


# --- §37.1/2/13: prompt contract ----------------------------------------------------

from research.fact import Fact  # noqa: E402
from research.local_refinement import (  # noqa: E402
    AttemptRecord,
    LocalRefinementContext,
)
from research.obligation import ProofObligation  # noqa: E402
from research.problem import ProblemSpec  # noqa: E402
from research.scaffold import ScaffoldNode  # noqa: E402

from strategist import MathematicalStrategist, strategist_prompt  # noqa: E402


def _context() -> LocalRefinementContext:
    return LocalRefinementContext(
        original_problem="Prove theorem T.",
        blocked_node=ScaffoldNode("mid", "Lemma M."),
        blocked_obligation=ProofObligation("scaffold:p:mid", (), "Lemma M.", "scaffold:mid"),
        local_nodes=(ScaffoldNode("target", "Prove theorem T.", depends_on=("mid",)),),
        verified_boundary=(
            Fact.create(
                problem_id="p",
                author="test",
                statement="Base fact F0.",
                proof="Direct computation.",
            ),
        ),
        attempts=(
            AttemptRecord(
                attempt_id="attempt-000001",
                obligation_id="scaffold:p:mid",
                verdict="FAIL",
                error=None,
                candidate_artifact={"statement": "Lemma M."},
                verifier_artifact={"reason": "the final step invokes theorem T"},
            ),
        ),
        downstream_intent='Downstream intent for blocked node mid:\n- "target" consumes mid',
        previous_refinement_summary="",
        allowed_operation="SPLIT",
    )


def test_strategist_receives_same_local_context() -> None:
    """§37.1/§6: the prompt carries exactly the frozen context fields."""
    prompt = strategist_prompt(_context())
    assert "Prove theorem T." in prompt  # original problem
    assert "Lemma M." in prompt  # blocked goal
    assert "the final step invokes theorem T" in prompt  # verifier feedback
    assert "Base fact F0." in prompt  # verified boundary
    assert "consumes mid" in prompt  # downstream intent
    assert "attempt-000001" in prompt  # attempt evidence


def test_operator_is_not_preselected() -> None:
    """§37.2/§7: all four options appear as a menu; no operator is given as
    the assignment."""
    prompt = strategist_prompt(_context())
    for token in ("SPLIT", "INSERT_CUT_SET", "ADD_ALTERNATIVE_ROUTE", "DECLINE"):
        assert token in prompt
    assert "You are performing" not in prompt
    assert "Return ONLY the JSON object" in prompt


def test_context_radius_unchanged() -> None:
    """§37.13/§6: the prompt is a pure rendering of the given context — no
    whole-graph or transcript material is added."""
    context = _context()
    prompt = strategist_prompt(context)
    assert "unrelated" not in prompt
    # The verified-facts section carries exactly the context's boundary
    # facts — one bullet each, nothing beyond.
    section = prompt.split("Verified facts relevant to the local region:")[1].split(
        "Failure evidence"
    )[0]
    bullets = [line for line in section.splitlines() if line.startswith("- ")]
    assert len(bullets) == len(context.verified_boundary)
    for fact, bullet in zip(context.verified_boundary, bullets):
        assert fact.statement in bullet


class _RecordingInvoker:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def invoke(self, *, prompt, schema, label):
        self.calls.append((label, prompt, schema))
        return self.response


def test_strategist_single_fresh_call_and_label() -> None:
    """§37.16 (agent level): one strategize = one invocation, distinct label."""
    response = json.loads(_strategist_json("DECLINE", new_nodes=[], decline_reason="x"))
    invoker = _RecordingInvoker(response)
    strategist = MathematicalStrategist(invoker)
    result = strategist.strategize(_context())
    assert result.operator == "DECLINE"
    assert len(invoker.calls) == 1
    assert invoker.calls[0][0] == "mathematical_strategist"
    assert strategist.last_prompt == invoker.calls[0][1]


# --- §37.7/8/9/10/16/17: treatment driver ------------------------------------------

from research.fact import CandidateFact  # noqa: E402
from research.node_solver import NodeSolverConfig  # noqa: E402
from research.pipeline import VerificationResult  # noqa: E402
from research.scaffold import ProofScaffold  # noqa: E402

from treatment_driver import run_treatment  # noqa: E402

STATEMENT = "Lemma M implies theorem T."


class _EchoWorker:
    def propose(self, *, problem, existing_facts, subgoal, repair_context=None):
        goal = subgoal.split("Goal:\n", 1)[1]
        return CandidateFact(
            goal, f"A candidate proof of {goal}",
            tuple(fact.fact_id for fact in existing_facts),
        )


class _RejectingVerifier:
    def __init__(self, rejected=()) -> None:
        self.rejected = set(rejected)

    def verify(self, problem, candidate, predecessors):
        return VerificationResult(
            candidate.statement not in self.rejected, "scripted verdict"
        )


class _RejectFirstVerifier:
    """Rejects the very first verification (the initial attempt on the
    blocked node, forcing a frontier), accepts everything after — including
    the re-routed node carrying the same statement."""

    def __init__(self) -> None:
        self.calls = 0

    def verify(self, problem, candidate, predecessors):
        self.calls += 1
        return VerificationResult(self.calls > 1, "scripted verdict")


class _ScriptedStrategist:
    """One scripted StrategistResult per call; counts calls (K=1 check)."""

    def __init__(self, results) -> None:
        self.results = list(results)
        self.calls = 0
        self.last_prompt = None

    def strategize(self, context):
        self.calls += 1
        self.last_prompt = strategist_prompt(context)
        return self.results.pop(0)


class _ScriptedAuditor:
    def __init__(self, verdict="PASS") -> None:
        self.verdict = verdict
        self.calls = 0

    def audit(self, context, proposal, *, effort=None, timeout=None):
        from research.local_refinement import AuditorResult

        self.calls += 1
        return AuditorResult(verdict=self.verdict, reasons=("scripted",))


def _workspace(root: Path) -> Path:
    from research.obligation import ObligationRegistry

    problem_dir = root / "workspace" / "p"
    problem_dir.mkdir(parents=True)
    ProofScaffold.create(
        problem_dir / "scaffold.json",
        problem=ProblemSpec("p", STATEMENT),
        target_node_id="target",
        nodes=(
            ScaffoldNode("mid", STATEMENT),
            ScaffoldNode("target", STATEMENT, depends_on=("mid",)),
        ),
    )
    ObligationRegistry(problem_dir / "obligations.json")
    return problem_dir


def _run(root, strategist, auditor=None, rejected=(STATEMENT,), verifier=None):
    return run_treatment(
        root,
        problem=ProblemSpec("p", STATEMENT),
        worker=_EchoWorker(),
        verifier=verifier or _RejectingVerifier(rejected),
        strategist=strategist,
        auditor_for=lambda operation: auditor or _ScriptedAuditor(),
        solver_config=NodeSolverConfig(max_attempts_per_obligation=1),
        author="n2p-test",
    )


def _scaffold_nodes(root: Path):
    return [n.node_id for n in ProofScaffold(root / "scaffold.json").list_nodes()]


def test_decline_makes_no_mutation() -> None:
    """§37.7/§23: DECLINE stops the frontier; graph untouched; no auditor."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        strategist = _ScriptedStrategist(
            [parse_strategist_output(
                _strategist_json("DECLINE", new_nodes=[], decline_reason="no honest restructuring"),
                blocked_node_id="mid",
            )]
        )
        auditor = _ScriptedAuditor()
        result = _run(root, strategist, auditor)
        assert result.stop_reason == "STRATEGIST_DECLINED"
        assert _scaffold_nodes(root) == ["mid", "target"]
        assert auditor.calls == 0


def test_auditor_reject_makes_no_mutation() -> None:
    """§37.8/§24: auditor REJECT stops the frontier; no resample, no mutation."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        strategist = _ScriptedStrategist(
            [parse_strategist_output(_strategist_json("INSERT_CUT_SET"), blocked_node_id="mid")]
        )
        result = _run(root, strategist, _ScriptedAuditor(verdict="REJECT"))
        assert result.stop_reason == "STRATEGY_AUDIT_REJECTED"
        assert _scaffold_nodes(root) == ["mid", "target"]
        assert strategist.calls == 1


def test_no_automatic_fallback_escalation() -> None:
    """§37.9/§23: after DECLINE no SPLIT/CUT/ALT attempt follows."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        strategist = _ScriptedStrategist(
            [parse_strategist_output(
                _strategist_json("DECLINE", new_nodes=[], decline_reason="x"),
                blocked_node_id="mid",
            )]
        )
        result = _run(root, strategist)
        assert result.stop_reason == "STRATEGIST_DECLINED"
        assert strategist.calls == 1
        assert not (root / "local_refinements").exists() or not list(
            (root / "local_refinements").glob("*.json")
        )


def test_applied_cut_then_facts_come_from_worker_verifier() -> None:
    """§37.10: the strategist never creates Facts; after an APPLIED patch the
    frozen worker->verifier path admits them."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        strategist = _ScriptedStrategist(
            [parse_strategist_output(_strategist_json("INSERT_CUT_SET"), blocked_node_id="mid")]
        )
        result = _run(root, strategist, verifier=_RejectFirstVerifier())
        assert result.stop_reason == "TARGET_SOLVED"
        assert result.mutation_episodes == 1
        from research.graph import FactGraph

        facts = FactGraph(root).list_facts()
        assert facts  # admitted only via worker -> verifier after the patch
        statements = {fact.statement for fact in facts}
        assert "Helper lemma one." in statements


def test_k1_one_strategist_call_per_frontier() -> None:
    """§37.16/§5: exactly one strategist call per frontier identity."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        strategist = _ScriptedStrategist(
            [parse_strategist_output(_strategist_json("INSERT_CUT_SET"), blocked_node_id="mid")]
        )
        result = _run(root, strategist, verifier=_RejectFirstVerifier())
        assert result.stop_reason == "TARGET_SOLVED"
        assert strategist.calls == 1  # one frontier, one decision


def test_strategist_packet_persisted() -> None:
    """§37.17/§38: diagnosis, strategy, operator, raw output, and the exact
    prompt are persisted as evidence."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        strategist = _ScriptedStrategist(
            [parse_strategist_output(_strategist_json("INSERT_CUT_SET"), blocked_node_id="mid")]
        )
        _run(root, strategist, verifier=_RejectFirstVerifier())
        packets = list((root / "strategist").glob("*.json"))
        assert len(packets) == 1
        payload = json.loads(packets[0].read_text(encoding="utf-8"))
        assert payload["operator"] == "INSERT_CUT_SET"
        assert payload["obstruction"]
        assert payload["mathematical_idea"]
        assert payload["why_this_reduces_difficulty"]
        assert payload["raw"]
        assert "Mathematical Local Strategist" in payload["prompt"]


def test_episode_carries_decision_time_audit_packet() -> None:
    """The post-hoc independent audit consumes a decision-time snapshot with
    no frozen-pipeline verdicts inside (no anchoring; code-review fix)."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        strategist = _ScriptedStrategist(
            [parse_strategist_output(_strategist_json("INSERT_CUT_SET"), blocked_node_id="mid")]
        )
        result = _run(root, strategist, verifier=_RejectFirstVerifier())
        packet = result.episodes[0]["audit_packet"]
        assert packet["blocked_goal"] == STATEMENT
        assert packet["operator"] == "INSERT_CUT_SET"
        assert packet["patch"]
        assert "mechanical_errors" not in packet
        assert "structural_auditor_verdict" not in packet
        assert isinstance(packet["failure_evidence"], list)
        assert isinstance(packet["verified_boundary"], list)


def test_strategist_schema_error_is_system_error() -> None:
    """Malformed strategist output is a schema failure, not a decline."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))

        class _BadStrategist:
            last_prompt = None

            def strategize(self, context):
                raise ValueError("unknown operator: 'REWIRE'")

        result = _run(root, _BadStrategist())
        assert result.stop_reason == "SYSTEM_ERROR"
        assert _scaffold_nodes(root) == ["mid", "target"]
