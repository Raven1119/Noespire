"""N2U live two-stage failure-driven refinement — contract tests (§34).

Composition-only integration: N2S StrategySketcher -> N2S SketchAuditor gate
-> N2T StrategyBoundPatchBuilder (+ N2T FidelityAuditor pre-apply check, §12)
-> frozen mechanical validator + Structural Auditor -> N2Q one-round revision
-> apply -> NodeSolver/Verifier. K=1 per frontier; no resampling, no fixed
escalation, no new operator, no memory.

All tests are model-free: scripted components + fake worker/verifier.
"""

from __future__ import annotations

import inspect
import json
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

import pytest

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
):
    sys.path.insert(0, str(REPO_ROOT / rel))

from research.fact import CandidateFact  # noqa: E402
from research.graph import FactGraph  # noqa: E402
from research.local_refinement import AuditorResult, run_local_redecomposition  # noqa: E402
from research.node_solver import NodeSolverConfig  # noqa: E402
from research.obligation import ObligationRegistry  # noqa: E402
from research.pipeline import VerificationResult  # noqa: E402
from research.problem import ProblemSpec  # noqa: E402
from research.scaffold import ProofScaffold, ScaffoldNode, solve_scaffold  # noqa: E402

import strategist as n2p_strategist  # noqa: E402
from sketch import parse_sketch_output  # noqa: E402  (N2S)
from patch_builder import parse_patch_build_output  # noqa: E402  (N2T)
from reviser import parse_revision_output  # noqa: E402  (N2Q)

import two_stage_driver  # noqa: E402  (module under test)
from two_stage_driver import (  # noqa: E402
    EPISODE_OUTCOMES,
    GATE_PASS_CLASSES,
    run_two_stage,
)

BLOCKED = "mid"
STATEMENT = "Lemma M implies theorem T."
PID = "p"
REVISE_REASON = "The second claim does not fix the quantifier domain of m."


# --- fixtures -------------------------------------------------------------------


def _sketch(operator="ADD_ALTERNATIVE_ROUTE", **overrides) -> str:
    payload = {
        "obstruction": "Compactness alone transports counterexamples.",
        "evidence": ["attempt-1 verifier: final step invokes T"],
        "mathematical_idea": "Dilation-invariant measure on multiplicative characters.",
        "why_this_reduces_difficulty": "Isolates the analytic content on a narrower class.",
        "operator": operator,
        "why_current_route_is_exhausted": "Compactness cannot supply the estimate.",
        "decline_reason": "",
        "candidate_claims": [
            "Finite counterexamples yield an infinite bounded-discrepancy sequence.",
            "Its dilates average to a dilation-invariant probability measure.",
        ],
    }
    payload.update(overrides)
    return json.dumps(payload)


def _sketch_result(operator="ADD_ALTERNATIVE_ROUTE", **overrides):
    return parse_sketch_output(_sketch(operator, **overrides), blocked_node_id=BLOCKED)


def _patch_json(**overrides) -> str:
    payload = {
        "compilation_decline": False,
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


def _patch():
    return parse_patch_build_output(_patch_json())


def _revision(operator="ADD_ALTERNATIVE_ROUTE", repairable=True):
    payload = json.loads(_sketch(operator))
    payload["new_nodes"] = json.loads(_patch_json())["new_nodes"]
    payload["repairable"] = repairable
    return parse_revision_output(
        json.dumps(payload), blocked_node_id=BLOCKED, expected_operator=operator
    )


class _EchoWorker:
    def propose(self, *, problem, existing_facts, subgoal, repair_context=None):
        goal = subgoal.split("Goal:\n", 1)[1]
        return CandidateFact(
            goal, f"A candidate proof of {goal}",
            tuple(fact.fact_id for fact in existing_facts),
        )


class _RejectFirstVerifier:
    """Rejects the first verification (forcing a frontier), accepts after."""

    def __init__(self) -> None:
        self.calls = 0

    def verify(self, problem, candidate, predecessors):
        self.calls += 1
        return VerificationResult(self.calls > 1, "scripted verdict")


class _ScriptedSketcher:
    def __init__(self, results) -> None:
        self.results = list(results)
        self.calls = 0
        self.last_prompt = None

    def strategize(self, context):
        self.calls += 1
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class _ScriptedGate:
    def __init__(self, classes) -> None:
        self.classes = list(classes)
        self.calls = 0

    def audit(self, packet):
        self.calls += 1
        return {
            "strategy_class": self.classes.pop(0),
            "difficulty_reduction": "UNCLEAR",
            "strategy_family": "test",
            "reasons": ["scripted"],
        }


class _ScriptedFidelity:
    def __init__(self, fidelity="FAITHFUL", operator_check="OPERATOR_PRESERVED") -> None:
        self.fidelity = fidelity
        self.operator_check = operator_check
        self.calls = 0

    def audit(self, sketch, patch_nodes, operator):
        self.calls += 1
        return {
            "strategy_fidelity": self.fidelity,
            "operator_check": self.operator_check,
            "claim_fidelity": [],
            "reasons": ["scripted"],
        }


class _ScriptedBuilder:
    def __init__(self, results) -> None:
        self.results = list(results)
        self.calls = 0
        self.last_prompt = None

    def compile(self, context, sketch):
        self.calls += 1
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class _ScriptedReviser:
    def __init__(self, results) -> None:
        self.results = list(results)
        self.calls = 0
        self.last_prompt = None

    def revise(self, context, v1, auditor_reasons):
        self.calls += 1
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class _FreshAuditor:
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


def _run(root, *, sketcher, gate=None, fidelity=None, builder, reviser, factory):
    return run_two_stage(
        root,
        problem=ProblemSpec(PID, STATEMENT),
        worker=_EchoWorker(),
        verifier=_RejectFirstVerifier(),
        sketcher=sketcher,
        gate=gate or _ScriptedGate(["PLAUSIBLE_STRATEGY"]),
        fidelity=fidelity or _ScriptedFidelity(),
        patch_builder=builder,
        reviser=reviser,
        auditor_for=factory,
        solver_config=NodeSolverConfig(max_attempts_per_obligation=1),
        author="n2u-test",
    )


def _ok_sketcher():
    return _ScriptedSketcher([_sketch_result()])


# --- vocabulary + frozen-component identity (§34.5/6/15) -------------------------


def test_episode_outcome_vocabulary() -> None:
    """§28 stage failure attribution classes."""
    assert {
        "STRATEGIST_TIMEOUT", "STRATEGIST_DECLINE", "STRATEGY_GATE_REJECT",
        "PATCH_BUILDER_TIMEOUT", "PATCH_COMPILATION_INVALID", "MECHANICAL_FAIL",
        "STRUCTURAL_AUDITOR_REJECT", "REVISION_FAILED", "PATCH_APPLIED",
        "SYSTEM_ERROR",
    } <= set(EPISODE_OUTCOMES)


def test_frozen_components_reused_not_reimplemented() -> None:
    """§2/§34.5/6/15: driver composes the frozen seams; no new operator."""
    assert two_stage_driver.solve_scaffold is solve_scaffold
    assert two_stage_driver.run_local_redecomposition is run_local_redecomposition
    assert two_stage_driver.compile_to_builder_result is n2p_strategist.compile_to_builder_result
    assert set(two_stage_driver._OPERATION) == {
        "SPLIT", "INSERT_CUT_SET", "ADD_ALTERNATIVE_ROUTE",
    }
    assert GATE_PASS_CLASSES == ("USEFUL_STRATEGY", "PLAUSIBLE_STRATEGY")


# --- gate contract (§34.1/2/8, §6-§10) -------------------------------------------


def test_gate_reject_never_calls_patch_builder() -> None:
    """§34.1/§8/§10: INVALID strategy stops at the gate; no builder, no
    auditor, no revision, no fallback."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        builder = _ScriptedBuilder([])
        factory = _AuditorFactory([])
        reviser = _ScriptedReviser([])
        result = _run(
            root, sketcher=_ok_sketcher(),
            gate=_ScriptedGate(["INVALID"]),
            builder=builder, reviser=reviser, factory=factory,
        )
        assert result.stop_reason == "STRATEGY_GATE_REJECT"
        assert builder.calls == 0
        assert reviser.calls == 0
        assert all(i.calls == 0 for i in factory.instances)


def test_gate_pass_calls_patch_builder_once() -> None:
    """§34.2: a passing gate leads to exactly one compilation."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        builder = _ScriptedBuilder([_patch()])
        result = _run(
            root, sketcher=_ok_sketcher(),
            gate=_ScriptedGate(["USEFUL_STRATEGY"]),
            builder=builder, reviser=_ScriptedReviser([]),
            factory=_AuditorFactory(["PASS"]),
        )
        assert builder.calls == 1
        assert result.mutation_episodes == 1
        assert result.stop_reason == "TARGET_SOLVED"


def test_decline_reaches_no_downstream_stage() -> None:
    """§34.8/§9: DECLINE skips gate, builder, auditor, reviser."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        gate = _ScriptedGate([])
        builder = _ScriptedBuilder([])
        result = _run(
            root,
            sketcher=_ScriptedSketcher([
                _sketch_result("DECLINE", candidate_claims=[],
                               decline_reason="No meaningful reduction.")
            ]),
            gate=gate, builder=builder, reviser=_ScriptedReviser([]),
            factory=_AuditorFactory([]),
        )
        assert result.stop_reason == "STRATEGIST_DECLINE"
        assert gate.calls == 0 and builder.calls == 0


# --- immutability + drift (§34.3/4, §8/§12) ---------------------------------------


def test_operator_and_strategy_immutable_through_pipeline() -> None:
    """§34.3/4: the applied patch carries the sketch's operator and strategy;
    a drifted fidelity verdict stops before apply."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        result = _run(
            root,
            sketcher=_ScriptedSketcher([_sketch_result("INSERT_CUT_SET")]),
            builder=_ScriptedBuilder([_patch()]), reviser=_ScriptedReviser([]),
            factory=_AuditorFactory(["PASS"]),
        )
        assert result.stop_reason == "TARGET_SOLVED"
        episode = result.episodes[0]
        assert episode["operator"] == "INSERT_CUT_SET"
        assert episode["outcome"] == "PATCH_APPLIED"
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        factory = _AuditorFactory([])
        result = _run(
            root, sketcher=_ok_sketcher(),
            fidelity=_ScriptedFidelity(fidelity="STRATEGY_DRIFT"),
            builder=_ScriptedBuilder([_patch()]), reviser=_ScriptedReviser([]),
            factory=factory,
        )
        assert result.stop_reason == "PATCH_COMPILATION_INVALID"
        assert all(i.calls == 0 for i in factory.instances)  # never audited
        assert [n.node_id for n in ProofScaffold(root / "scaffold.json").list_nodes()] == [
            BLOCKED, "target",
        ]


# --- frozen validation/auditor/revision behavior (§34.5-7, §13-§15) --------------


def test_mechanical_fail_stops_before_auditor() -> None:
    """§34.5/§13: frozen mechanical validation gates; no retry of builder."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        bad = parse_patch_build_output(_patch_json(new_nodes=[
            {"node_id": "h1", "goal": "Helper lemma one.",
             "depends_on": ["nonexistent"], "premise_fact_ids": []},
        ]))
        builder = _ScriptedBuilder([bad])
        factory = _AuditorFactory([])
        result = _run(
            root, sketcher=_ok_sketcher(), builder=builder,
            reviser=_ScriptedReviser([]), factory=factory,
        )
        assert result.stop_reason == "MECHANICAL_FAIL"
        assert builder.calls == 1  # no retry
        assert all(i.calls == 0 for i in factory.instances)


def test_auditor_reject_terminal_no_revision() -> None:
    """§34.9-adjacent/§14: REJECT stops; zero revision calls."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        reviser = _ScriptedReviser([])
        result = _run(
            root, sketcher=_ok_sketcher(), builder=_ScriptedBuilder([_patch()]),
            reviser=reviser, factory=_AuditorFactory(["REJECT"]),
        )
        assert result.stop_reason == "STRUCTURAL_AUDITOR_REJECT"
        assert reviser.calls == 0


def test_revise_exactly_one_n2q_round() -> None:
    """§34.7/§15: REVISE -> one N2Q revision -> v2 PASS applies; a second
    REVISE is terminal."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        reviser = _ScriptedReviser([_revision()])
        result = _run(
            root, sketcher=_ok_sketcher(), builder=_ScriptedBuilder([_patch()]),
            reviser=reviser, factory=_AuditorFactory(["REVISE", "PASS"]),
        )
        assert reviser.calls == 1
        assert result.episodes[0]["outcome"] == "PATCH_APPLIED"
        assert result.stop_reason == "TARGET_SOLVED"
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        reviser = _ScriptedReviser([_revision()])
        result = _run(
            root, sketcher=_ok_sketcher(), builder=_ScriptedBuilder([_patch()]),
            reviser=reviser, factory=_AuditorFactory(["REVISE", "REVISE"]),
        )
        assert reviser.calls == 1
        assert result.stop_reason == "REVISION_FAILED"
        assert result.episodes[0]["revision"]["outcome"] == "REVISION_STILL_REVISE"


# --- no resampling / no fallback (§34.9/13/14, §4/§18/§24) ------------------------


def test_strategist_timeout_no_retry_no_fallback() -> None:
    """§34.9/14/§24: one sketcher call; timeout stops the frontier; no
    fixed SPLIT->CUT->ALT fallback (§18)."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        timeout = subprocess.TimeoutExpired(cmd="codex", timeout=600)
        sketcher = _ScriptedSketcher([timeout])
        gate = _ScriptedGate([])
        builder = _ScriptedBuilder([])
        result = _run(
            root, sketcher=sketcher, gate=gate, builder=builder,
            reviser=_ScriptedReviser([]), factory=_AuditorFactory([]),
        )
        assert result.stop_reason == "STRATEGIST_TIMEOUT"
        assert sketcher.calls == 1
        assert gate.calls == 0 and builder.calls == 0


# --- truth boundary (§34.10-12, §16) ----------------------------------------------


def test_refinement_stages_never_write_facts() -> None:
    """§34.10/11/12/§16: gate PASS and auditor PASS admit nothing; Facts
    appear only through solve_scaffold's worker->verifier path."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        verifier = _RejectFirstVerifier()

        def run():
            return run_two_stage(
                root,
                problem=ProblemSpec(PID, STATEMENT),
                worker=_EchoWorker(),
                verifier=verifier,
                sketcher=_ok_sketcher(),
                gate=_ScriptedGate(["PLAUSIBLE_STRATEGY"]),
                fidelity=_ScriptedFidelity(),
                patch_builder=_ScriptedBuilder([_patch()]),
                reviser=_ScriptedReviser([]),
                auditor_for=_AuditorFactory(["PASS"]),
                solver_config=NodeSolverConfig(max_attempts_per_obligation=1),
                author="n2u-test",
            )

        # Drive the refinement stage via the handoff path after the first
        # block: facts before vs after the episode must be unchanged by it.
        result = run()
        assert result.stop_reason == "TARGET_SOLVED"
        graph = FactGraph(root)
        facts = graph.list_facts()
        # Every admitted Fact is a verifier-accepted worker candidate.
        assert len(facts) == verifier.calls - 1  # first verdict was a reject
        assert all(f.author == "n2u-test" for f in facts)
        # The refinement episode itself persisted evidence but no Fact.
        episode = result.episodes[0]
        assert episode["outcome"] == "PATCH_APPLIED"
        assert episode["facts_admitted_by_refinement"] == 0


# --- evidence persistence (§35) ----------------------------------------------------


def test_episode_evidence_persisted() -> None:
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        result = _run(
            root, sketcher=_ok_sketcher(), builder=_ScriptedBuilder([_patch()]),
            reviser=_ScriptedReviser([]), factory=_AuditorFactory(["PASS"]),
        )
        episodes_dir = root / "two_stage"
        packets = sorted(episodes_dir.glob("episode-*.json"))
        assert len(packets) == 1
        packet = json.loads(packets[0].read_text(encoding="utf-8"))
        assert packet["outcome"] == "PATCH_APPLIED"
        assert packet["sketch"]["operator"] == "ADD_ALTERNATIVE_ROUTE"
        assert packet["gate"]["strategy_class"] == "PLAUSIBLE_STRATEGY"
        assert packet["fidelity"]["strategy_fidelity"] == "FAITHFUL"
        assert packet["patch"]["new_nodes"]
