"""N2Q bounded auditor-guided proposal revision — deterministic contract
tests (task card §31).

Seams under test (pre-agreed by the task card):
- reviser.py: bounded revision contract — repairable flag, operator locked
  to v1 (OperatorDriftError), revision prompt carries the same local context
  + v1 + verbatim auditor reasons and nothing more; independent locality
  audit classes.
- revision_driver.py: PASS/REJECT/DECLINE never trigger a revision; REVISE
  triggers exactly one; v2 outcomes are terminal (STILL_REVISE / REJECTED /
  INVALID) or APPLIED (continue); Facts still only come from
  worker -> verifier; K=1 on the initial strategist unchanged.

All tests are model-free: fake invokers/workers/verifiers/auditors only.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))
sys.path.insert(0, str(REPO_ROOT / "experiments" / "n2l_closed_book_long_horizon"))
sys.path.insert(0, str(REPO_ROOT / "experiments" / "n2m_horizon_handoff"))
sys.path.insert(0, str(REPO_ROOT / "experiments" / "n2p_mathematical_strategist"))
sys.path.insert(0, str(REPO_ROOT / "experiments" / "n2q_auditor_guided_revision"))

from research.fact import CandidateFact, Fact  # noqa: E402
from research.local_refinement import (  # noqa: E402
    AttemptRecord,
    AuditorResult,
    LocalRefinementContext,
)
from research.node_solver import NodeSolverConfig  # noqa: E402
from research.obligation import ProofObligation  # noqa: E402
from research.pipeline import VerificationResult  # noqa: E402
from research.problem import ProblemSpec  # noqa: E402
from research.scaffold import ProofScaffold, ScaffoldNode  # noqa: E402

from strategist import parse_strategist_output, strategist_prompt  # noqa: E402  (N2P)
from reviser import (  # noqa: E402
    LOCALITY_CLASSES,
    REVISION_OUTCOMES,
    MathematicalReviser,
    OperatorDriftError,
    RevisionResult,
    parse_revision_output,
    revision_prompt,
)
from revision_driver import run_treatment_with_revision  # noqa: E402

BLOCKED = "mid"
STATEMENT = "Lemma M implies theorem T."
REVISE_REASON = "The fourth cut does not fix the quantifier domain of m."


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


def _revision_json(operator: str, repairable=True, **overrides) -> str:
    payload = json.loads(_strategist_json(operator, **overrides))
    payload["repairable"] = repairable
    return json.dumps(payload)


def _decision(operator="INSERT_CUT_SET", **overrides):
    return parse_strategist_output(_strategist_json(operator, **overrides), blocked_node_id=BLOCKED)


# --- revision parse contract (§4/§12/§16) -------------------------------------


def test_revision_outcome_vocabulary() -> None:
    assert set(REVISION_OUTCOMES) == {
        "REVISION_PASS",
        "REVISION_STILL_REVISE",
        "REVISION_REJECTED",
        "REVISION_INVALID",
        "REVISION_NOT_LOCAL",
    }
    assert set(LOCALITY_CLASSES) == {
        "LOCAL_REPAIR",
        "PARTIAL_STRATEGY_CHANGE",
        "NEW_STRATEGY",
    }


def test_repairable_revision_parses_into_v2() -> None:
    result = parse_revision_output(
        _revision_json("INSERT_CUT_SET"), blocked_node_id=BLOCKED,
        expected_operator="INSERT_CUT_SET",
    )
    assert result.repairable
    assert result.decision.operator == "INSERT_CUT_SET"
    assert [n["node_id"] for n in result.decision.new_nodes] == ["h1", "h2"]


def test_unrepairable_revision_is_not_local() -> None:
    """§4/§16: feedback that requires a new strategy must surface as
    REVISION_NOT_LOCAL material, never a silent re-plan."""
    result = parse_revision_output(
        _revision_json(
            "INSERT_CUT_SET", repairable=False, new_nodes=[],
            decline_reason="The objection is to the route itself, not its wording.",
        ),
        blocked_node_id=BLOCKED, expected_operator="INSERT_CUT_SET",
    )
    assert not result.repairable
    assert result.decision is None
    assert "route itself" in result.not_local_reason


def test_operator_drift_is_invalid() -> None:
    """§31.8/§4: revision may not change the operator."""
    with pytest.raises(OperatorDriftError):
        parse_revision_output(
            _revision_json("SPLIT"), blocked_node_id=BLOCKED,
            expected_operator="INSERT_CUT_SET",
        )


def test_repairable_flag_required() -> None:
    with pytest.raises(ValueError):
        parse_revision_output(
            _strategist_json("INSERT_CUT_SET"), blocked_node_id=BLOCKED,
            expected_operator="INSERT_CUT_SET",
        )


def test_malformed_revision_raises() -> None:
    with pytest.raises(ValueError):
        parse_revision_output(
            "not json", blocked_node_id=BLOCKED, expected_operator="SPLIT"
        )


# --- prompt contracts (§6/§7/§22) ----------------------------------------------


def _context() -> LocalRefinementContext:
    return LocalRefinementContext(
        original_problem="Prove theorem T.",
        blocked_node=ScaffoldNode("mid", "Lemma M."),
        blocked_obligation=ProofObligation("scaffold:p:mid", (), "Lemma M.", "scaffold:mid"),
        local_nodes=(ScaffoldNode("target", "Prove theorem T.", depends_on=("mid",)),),
        verified_boundary=(
            Fact.create(
                problem_id="p", author="test",
                statement="Base fact F0.", proof="Direct computation.",
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


def test_revision_prompt_carries_context_v1_and_reasons_only() -> None:
    """§31.10/§7: revision input = decision-time local state + v1 + auditor
    feedback. No graph widening, no transcript, no new material."""
    v1 = _decision()
    prompt = revision_prompt(_context(), v1, (REVISE_REASON,))
    assert "Prove theorem T." in prompt  # original problem
    assert "Lemma M." in prompt  # blocked goal
    assert "Base fact F0." in prompt  # verified boundary
    assert "the final step invokes theorem T" in prompt  # failure evidence
    assert "Helper lemma one." in prompt  # v1 patch
    assert REVISE_REASON in prompt  # verbatim auditor feedback
    assert '"operator": "INSERT_CUT_SET"' in prompt  # v1 operator shown
    # The revision prompt must NOT re-offer the strategist's operator menu —
    # the operator is locked to v1's (§4).
    assert '"SPLIT": the blocked goal unfolds' not in prompt
    # No unrelated content: the verified-facts section carries exactly the
    # context's boundary facts.
    section = prompt.split("Verified facts relevant to the local region:")[1].split(
        "Failure evidence"
    )[0]
    bullets = [line for line in section.splitlines() if line.startswith("- ")]
    assert len(bullets) == 1


def test_revision_prompt_locks_operator_in_output_contract() -> None:
    """§4: the prompt's output template fixes the operator to v1's."""
    prompt = revision_prompt(_context(), _decision(), (REVISE_REASON,))
    assert '"operator": "INSERT_CUT_SET"' in prompt


def test_initial_strategist_prompt_unchanged() -> None:
    """§31.12/§22: N2Q adds a revision contract only; the N2P strategist
    prompt is the same object with the same content."""
    import strategist as n2p_strategist

    assert strategist_prompt is n2p_strategist.strategist_prompt
    prompt = strategist_prompt(_context())
    assert "work in this exact order" in prompt
    assert "You are performing" not in prompt
    # The revision prompt is a separate contract.
    assert "REVISE" in revision_prompt(_context(), _decision(), (REVISE_REASON,))


class _RecordingInvoker:
    def __init__(self, response):
        self.response = response
        self.calls = []

    def invoke(self, *, prompt, schema, label):
        self.calls.append((label, prompt, schema))
        return self.response


def test_reviser_single_fresh_call_and_label() -> None:
    """§6: one revise = one fresh invocation with its own label."""
    response = json.loads(_revision_json("INSERT_CUT_SET"))
    invoker = _RecordingInvoker(response)
    reviser = MathematicalReviser(invoker)
    result = reviser.revise(_context(), _decision(), (REVISE_REASON,))
    assert result.repairable
    assert invoker.calls[0][0] == "mathematical_reviser"
    assert len(invoker.calls) == 1
    assert reviser.last_prompt == invoker.calls[0][1]


# --- driver contract (§31.1-9, 11, 13, 14) --------------------------------------


class _EchoWorker:
    def propose(self, *, problem, existing_facts, subgoal, repair_context=None):
        goal = subgoal.split("Goal:\n", 1)[1]
        return CandidateFact(
            goal, f"A candidate proof of {goal}",
            tuple(fact.fact_id for fact in existing_facts),
        )


class _RejectFirstVerifier:
    """Rejects the very first verification (forcing a frontier), accepts
    everything after — including the re-routed node with the same statement."""

    def __init__(self) -> None:
        self.calls = 0

    def verify(self, problem, candidate, predecessors):
        self.calls += 1
        return VerificationResult(self.calls > 1, "scripted verdict")


class _ScriptedStrategist:
    def __init__(self, results) -> None:
        self.results = list(results)
        self.calls = 0
        self.last_prompt = None

    def strategize(self, context):
        self.calls += 1
        self.last_prompt = strategist_prompt(context)
        return self.results.pop(0)


class _ScriptedReviser:
    def __init__(self, results) -> None:
        self.results = list(results)
        self.calls = 0
        self.last_prompt = None
        self.seen_reasons = None

    def revise(self, context, v1, auditor_reasons):
        self.calls += 1
        self.seen_reasons = tuple(auditor_reasons)
        self.last_prompt = revision_prompt(context, v1, auditor_reasons)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class _FreshAuditor:
    """One auditor instance per session; verdicts drawn from a shared script."""

    def __init__(self, verdicts) -> None:
        self.verdicts = verdicts
        self.calls = 0

    def audit(self, context, proposal, *, effort=None, timeout=None):
        self.calls += 1
        verdict = self.verdicts.pop(0)
        reasons = (REVISE_REASON,) if verdict == "REVISE" else ("scripted",)
        return AuditorResult(verdict=verdict, reasons=reasons)


class _AuditorFactory:
    def __init__(self, verdicts) -> None:
        self.verdicts = list(verdicts)
        self.instances = []

    def __call__(self, operation):
        instance = _FreshAuditor(self.verdicts)
        self.instances.append(instance)
        return instance


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


def _run(root, strategist, reviser, auditor_factory, verifier=None):
    return run_treatment_with_revision(
        root,
        problem=ProblemSpec("p", STATEMENT),
        worker=_EchoWorker(),
        verifier=verifier or _RejectFirstVerifier(),
        strategist=strategist,
        reviser=reviser,
        auditor_for=auditor_factory,
        solver_config=NodeSolverConfig(max_attempts_per_obligation=1),
        author="n2q-test",
    )


def _scripted(operator="INSERT_CUT_SET"):
    return _ScriptedStrategist([_decision(operator)])


def _repairable_revision(operator="INSERT_CUT_SET"):
    return parse_revision_output(
        _revision_json(operator), blocked_node_id=BLOCKED, expected_operator=operator
    )


def _scaffold_nodes(root: Path):
    return [n.node_id for n in ProofScaffold(root / "scaffold.json").list_nodes()]


def test_pass_triggers_no_revision() -> None:
    """§31.1/§19: auditor PASS on v1 applies; zero revision calls."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        reviser = _ScriptedReviser([])
        result = _run(root, _scripted(), reviser, _AuditorFactory(["PASS"]))
        assert result.stop_reason == "TARGET_SOLVED"
        assert reviser.calls == 0
        assert result.revision_calls == 0


def test_reject_triggers_no_revision() -> None:
    """§31.2/§15: REJECT is terminal; zero revision calls."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        reviser = _ScriptedReviser([])
        result = _run(root, _scripted(), reviser, _AuditorFactory(["REJECT"]))
        assert result.stop_reason == "STRATEGY_AUDIT_REJECTED"
        assert reviser.calls == 0
        assert _scaffold_nodes(root) == ["mid", "target"]


def test_decline_triggers_no_revision() -> None:
    """§31.3/§17: DECLINE is terminal; zero revision calls, no mutation."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        reviser = _ScriptedReviser([])
        strategist = _ScriptedStrategist(
            [_decision("DECLINE", new_nodes=[], decline_reason="no honest restructuring")]
        )
        result = _run(root, strategist, reviser, _AuditorFactory([]))
        assert result.stop_reason == "STRATEGIST_DECLINED"
        assert reviser.calls == 0
        assert _scaffold_nodes(root) == ["mid", "target"]


def test_revise_then_v2_pass_applies() -> None:
    """§31.4/§31.7/§2: REVISE -> exactly one revision -> v2 PASS -> apply."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        reviser = _ScriptedReviser([_repairable_revision()])
        auditors = _AuditorFactory(["REVISE", "PASS"])
        result = _run(root, _scripted(), reviser, auditors)
        assert result.stop_reason == "TARGET_SOLVED"
        assert reviser.calls == 1
        assert result.revision_calls == 1
        assert len(auditors.instances) == 2  # fresh auditor per round (§19)
        assert auditors.instances[0] is not auditors.instances[1]
        episode = result.episodes[0]
        assert episode["outcome"] == "AUDITOR_REVISE"
        assert episode["revision"]["outcome"] == "REVISION_PASS"
        assert reviser.seen_reasons == (REVISE_REASON,)
        assert result.mutation_episodes == 1


def test_v2_revise_stops() -> None:
    """§31.5/§20: v2 REVISE is terminal — never a v3."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        reviser = _ScriptedReviser([_repairable_revision()])
        result = _run(root, _scripted(), reviser, _AuditorFactory(["REVISE", "REVISE"]))
        assert result.stop_reason == "REVISION_STILL_REVISE"
        assert reviser.calls == 1
        assert _scaffold_nodes(root) == ["mid", "target"]


def test_v2_reject_stops() -> None:
    """§31.6: v2 REJECT is terminal."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        reviser = _ScriptedReviser([_repairable_revision()])
        result = _run(root, _scripted(), reviser, _AuditorFactory(["REVISE", "REJECT"]))
        assert result.stop_reason == "REVISION_REJECTED"
        assert reviser.calls == 1
        assert _scaffold_nodes(root) == ["mid", "target"]


def test_operator_drift_is_revision_invalid() -> None:
    """§31.8/§4: a revision that changes the operator is REVISION_INVALID;
    no mutation, no second auditor call."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        reviser = _ScriptedReviser(
            [OperatorDriftError("operator drift: 'SPLIT' != v1 'INSERT_CUT_SET'")]
        )
        auditors = _AuditorFactory(["REVISE"])
        result = _run(root, _scripted(), reviser, auditors)
        assert result.stop_reason == "REVISION_INVALID"
        assert reviser.calls == 1
        assert len(auditors.instances) == 1  # v2 never reached an auditor
        assert _scaffold_nodes(root) == ["mid", "target"]


def test_unrepairable_feedback_is_not_local() -> None:
    """§31.9/§16 (Control C): feedback requiring a new strategy yields
    REVISION_NOT_LOCAL; no mutation, no second auditor."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        reviser = _ScriptedReviser([
            RevisionResult(
                repairable=False, decision=None,
                not_local_reason="The objection is to the route itself.", raw="{}",
            )
        ])
        auditors = _AuditorFactory(["REVISE"])
        result = _run(root, _scripted(), reviser, auditors)
        assert result.stop_reason == "REVISION_NOT_LOCAL"
        assert len(auditors.instances) == 1
        assert _scaffold_nodes(root) == ["mid", "target"]


def test_facts_only_from_worker_verifier_after_revision() -> None:
    """§31.11/§9: an applied v2 admits no Facts by itself; the worker ->
    verifier path does."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        reviser = _ScriptedReviser([_repairable_revision()])
        result = _run(
            root, _scripted(), reviser, _AuditorFactory(["REVISE", "PASS"])
        )
        assert result.stop_reason == "TARGET_SOLVED"
        from research.graph import FactGraph

        facts = FactGraph(root).list_facts()
        assert facts
        assert {f.statement for f in facts} >= {"Helper lemma one.", "Helper lemma two."}


def test_k1_initial_strategist_unchanged() -> None:
    """§31.14/§3: exactly one initial strategist call per frontier, even
    when a revision follows."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        strategist = _scripted()
        reviser = _ScriptedReviser([_repairable_revision()])
        result = _run(root, strategist, reviser, _AuditorFactory(["REVISE", "PASS"]))
        assert result.stop_reason == "TARGET_SOLVED"
        assert strategist.calls == 1
        assert result.strategist_calls == 1


def test_revision_packet_and_audit_packet_persisted() -> None:
    """§30: revision input/output and the decision-time audit packet are
    persisted as evidence."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        reviser = _ScriptedReviser([_repairable_revision()])
        _run(root, _scripted(), reviser, _AuditorFactory(["REVISE", "PASS"]))
        packets = list((root / "revisions").glob("*.json"))
        assert len(packets) == 1
        payload = json.loads(packets[0].read_text(encoding="utf-8"))
        assert payload["repairable"] is True
        assert payload["v2"]["operator"] == "INSERT_CUT_SET"
        assert REVISE_REASON in payload["prompt"]
        revision = json.loads(
            (root / "treatment_journal.jsonl").read_text(encoding="utf-8")
            .strip().splitlines()[-1]
        )["revision"]
        assert "mechanical_errors" not in revision["audit_packet"]
        assert "structural_auditor_verdict" not in revision["audit_packet"]
