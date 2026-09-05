"""N2W mechanical-validator-guided patch repair — contract tests (§36).

Additive seam on the frozen N2U two-stage driver: on MECHANICAL_REJECT, ONE
fresh diagnostic-guided repair of the compiler output (v1 patch), gated by a
deterministic v1->v2 diff check and a fresh independent locality audit, then
the SAME deterministic validator and the frozen Structural Auditor / N2Q
one-round revision. Strategy and operator are immutable; no resampling, no
new operator, no repair on auditor REJECT, no Facts outside the Verifier.

All tests are model-free: scripted components + fake worker/verifier.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

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
):
    sys.path.insert(0, str(REPO_ROOT / rel))

from research.fact import CandidateFact  # noqa: E402
from research.graph import FactGraph  # noqa: E402
from research.local_refinement import AuditorResult  # noqa: E402
from research.node_solver import NodeSolverConfig  # noqa: E402
from research.obligation import ObligationRegistry  # noqa: E402
from research.pipeline import VerificationResult  # noqa: E402
from research.problem import ProblemSpec  # noqa: E402
from research.scaffold import ProofScaffold, ScaffoldNode  # noqa: E402

from sketch import parse_sketch_output  # noqa: E402  (N2S)
from patch_builder import parse_patch_build_output  # noqa: E402  (N2T)
from reviser import parse_revision_output  # noqa: E402  (N2Q)

import repair as n2w_repair  # noqa: E402  (module under test)
from repair import repair_diff_check  # noqa: E402

import two_stage_driver  # noqa: E402  (module under test)
from two_stage_driver import EPISODE_OUTCOMES, run_two_stage  # noqa: E402

BLOCKED = "mid"
STATEMENT = "Lemma M implies theorem T."
PID = "p"
BAD_FACT_ID = "not-a-declared-premise"
REVISE_REASON = "The second claim does not fix the quantifier domain of m."


# --- fixtures -------------------------------------------------------------------


def _sketch_json(operator="INSERT_CUT_SET", **overrides) -> str:
    payload = {
        "obstruction": "Compactness alone transports counterexamples.",
        "evidence": ["attempt-1 verifier: final step invokes T"],
        "mathematical_idea": "Entropy decrement over a dilation-invariant measure.",
        "why_this_reduces_difficulty": "Isolates the analytic content on a narrower class.",
        "operator": operator,
        "why_current_route_is_exhausted": "Compactness cannot supply the estimate.",
        "decline_reason": "",
        "candidate_claims": [
            "A dilation-invariant probability measure exists on the limit system.",
            "An entropy decrement inequality bounds the mutual information.",
        ],
    }
    payload.update(overrides)
    return json.dumps(payload)


def _sketch(operator="INSERT_CUT_SET", **overrides):
    return parse_sketch_output(_sketch_json(operator, **overrides), blocked_node_id=BLOCKED)


def _nodes(*, premise_fact_ids=()):
    return [
        {"node_id": "h1", "goal": "Helper lemma one.",
         "depends_on": [], "premise_fact_ids": []},
        {"node_id": "h2", "goal": "Helper lemma two.",
         "depends_on": ["h1"], "premise_fact_ids": list(premise_fact_ids)},
    ]


def _patch_json(**overrides) -> str:
    payload = {
        "compilation_decline": False,
        "decline_reason": "",
        "new_nodes": _nodes(),
    }
    payload.update(overrides)
    return json.dumps(payload)


def _patch(**overrides):
    return parse_patch_build_output(_patch_json(**overrides))


def _bad_patch():
    """The run_02 defect shape: an illegal premise_fact_ids reference."""
    return _patch(new_nodes=_nodes(premise_fact_ids=[BAD_FACT_ID]))


def _repaired_patch():
    """v1 with ONLY the illegal reference removed (same node ids/goals)."""
    return _patch()


def _revision(operator="INSERT_CUT_SET", repairable=True):
    payload = json.loads(_sketch_json(operator))
    payload["new_nodes"] = _nodes()
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


class _ScriptedRepairer:
    def __init__(self, results) -> None:
        self.results = list(results)
        self.calls = 0
        self.last_prompt = None

    def repair(self, context, sketch, v1_nodes, mechanical_errors):
        self.calls += 1
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class _ScriptedRepairLocality:
    def __init__(self, locality="LOCAL_MECHANICAL_REPAIR") -> None:
        self.locality = locality
        self.calls = 0

    def audit(self, sketch, v1_nodes, v2_nodes, mechanical_errors):
        self.calls += 1
        return {"locality": self.locality, "reasons": ["scripted"]}


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


def _run(root, *, sketcher=None, gate=None, fidelity=None, builder, reviser=None,
         factory, repairer=None, repair_locality=None):
    return run_two_stage(
        root,
        problem=ProblemSpec(PID, STATEMENT),
        worker=_EchoWorker(),
        verifier=_RejectFirstVerifier(),
        sketcher=sketcher or _ScriptedSketcher([_sketch()]),
        gate=gate or _ScriptedGate(["PLAUSIBLE_STRATEGY"]),
        fidelity=fidelity or _ScriptedFidelity(),
        patch_builder=builder,
        reviser=reviser or _ScriptedReviser([]),
        auditor_for=factory,
        mechanical_repair=repairer,
        repair_locality=repair_locality,
        solver_config=NodeSolverConfig(max_attempts_per_obligation=1),
        author="n2w-test",
    )


def _node_ids(root: Path):
    return [n.node_id for n in ProofScaffold(root / "scaffold.json").list_nodes()]


# --- vocabulary + frozen-component identity (§36.13/15) ---------------------------


def test_episode_outcome_vocabulary_extended() -> None:
    """§28-style attribution: the N2W repair classes join the frozen set."""
    assert {
        "MECHANICAL_REPAIR_NOT_LOCAL", "MECHANICAL_REPAIR_INVALID",
        "MECHANICAL_REPAIR_TIMEOUT", "MECHANICAL_REPAIR_FAILED",
        "MECHANICAL_FAIL", "PATCH_APPLIED",
    } <= set(EPISODE_OUTCOMES)


def test_no_new_operator_and_frozen_validator_reused() -> None:
    """§36.13/6/§6: exactly the three frozen operators; the repair stage has
    no operator vocabulary of its own and no operator field in its schema."""
    assert set(two_stage_driver._OPERATION) == {
        "SPLIT", "INSERT_CUT_SET", "ADD_ALTERNATIVE_ROUTE",
    }
    assert "operator" not in n2w_repair.REPAIR_SCHEMA["properties"]
    assert n2w_repair.REPAIR_LOCALITY_CLASSES == (
        "LOCAL_MECHANICAL_REPAIR", "PARTIAL_STRUCTURAL_CHANGE",
        "STRATEGY_DRIFT", "OPERATOR_DRIFT",
    )


def test_diff_check_requires_identical_node_id_set() -> None:
    """§8/§13 deterministic gate: no added/dropped obligations in a repair."""
    v1 = _nodes(premise_fact_ids=[BAD_FACT_ID])
    assert repair_diff_check(v1, _nodes()) == ()
    renamed = [dict(n, node_id="other") for n in _nodes()]
    assert repair_diff_check(v1, renamed)
    dropped = _nodes()[:1]
    assert repair_diff_check(v1, dropped)


# --- repair triggering (§36.1/2) ---------------------------------------------------


def test_mechanical_pass_never_repairs() -> None:
    """§36.1/§2: a mechanically valid patch goes straight to the auditor;
    repair_calls = 0 (Control B shape)."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        repairer = _ScriptedRepairer([])
        locality = _ScriptedRepairLocality()
        result = _run(
            root, builder=_ScriptedBuilder([_patch()]),
            factory=_AuditorFactory(["PASS"]),
            repairer=repairer, repair_locality=locality,
        )
        assert result.stop_reason == "TARGET_SOLVED"
        assert result.episodes[0]["outcome"] == "PATCH_APPLIED"
        assert repairer.calls == 0
        assert locality.calls == 0
        assert result.repair_calls == 0


def test_mechanical_fail_exactly_one_repair_then_applied() -> None:
    """§36.2/§2: MECHANICAL_REJECT -> exactly one repair -> same validator ->
    fresh auditor PASS -> apply (frozen-replay success shape)."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        repairer = _ScriptedRepairer([_repaired_patch()])
        locality = _ScriptedRepairLocality()
        builder = _ScriptedBuilder([_bad_patch()])
        sketcher = _ScriptedSketcher([_sketch()])
        result = _run(
            root, sketcher=sketcher, builder=builder,
            factory=_AuditorFactory(["PASS"]),
            repairer=repairer, repair_locality=locality,
        )
        assert result.stop_reason == "TARGET_SOLVED"
        episode = result.episodes[0]
        assert episode["outcome"] == "PATCH_APPLIED"
        record = episode["mechanical_repair"]
        assert record["outcome"] == "MECHANICAL_REPAIR_PASS"
        assert record["mechanical_errors_v1"]
        assert record["mechanical_errors_v2"] == []
        assert record["locality"]["locality"] == "LOCAL_MECHANICAL_REPAIR"
        assert record["fields_changed"] == {"h2": ["premise_fact_ids"]}
        # §36.11/12: no resampling anywhere upstream of the repair.
        assert sketcher.calls == 1
        assert builder.calls == 1
        assert repairer.calls == 1
        assert result.repair_calls == 1


# --- repair termination (§36.3/6) --------------------------------------------------


def test_second_mechanical_fail_stops_no_v3() -> None:
    """§36.3/§2: a still-invalid v2 is terminal — no v3, no auditor, no
    graph mutation. The v2 error text comes from the SAME deterministic
    validator (§36.9/§22)."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        # v2 keeps the illegal reference AND adds a goal restating the
        # blocked goal: the real validator must flag both.
        still_bad = _patch(new_nodes=[
            {"node_id": "h1", "goal": STATEMENT,
             "depends_on": [], "premise_fact_ids": []},
            {"node_id": "h2", "goal": "Helper lemma two.",
             "depends_on": ["h1"], "premise_fact_ids": [BAD_FACT_ID]},
        ])
        factory = _AuditorFactory([])
        result = _run(
            root, builder=_ScriptedBuilder([_bad_patch()]),
            factory=factory,
            repairer=_ScriptedRepairer([still_bad]),
            repair_locality=_ScriptedRepairLocality(),
        )
        assert result.stop_reason == "MECHANICAL_REPAIR_FAILED"
        record = result.episodes[0]["mechanical_repair"]
        assert record["outcome"] == "MECHANICAL_REPAIR_FAILED"
        assert any("premise_fact_ids" in e for e in record["mechanical_errors_v2"])
        assert any("restates the goal" in e for e in record["mechanical_errors_v2"])
        assert all(i.calls == 0 for i in factory.instances)  # no auditor ran
        assert _node_ids(root) == [BLOCKED, "target"]


def test_non_local_repair_stops_without_audit() -> None:
    """§36.6/§9: the repairer may report the defect demands a new strategy —
    MECHANICAL_REPAIR_NOT_LOCAL, terminal, no silent re-plan (Control C)."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        decline = parse_patch_build_output(json.dumps({
            "compilation_decline": True,
            "decline_reason": "Fixing this needs a different operator.",
            "new_nodes": [],
        }))
        locality = _ScriptedRepairLocality()
        result = _run(
            root, builder=_ScriptedBuilder([_bad_patch()]),
            factory=_AuditorFactory([]),
            repairer=_ScriptedRepairer([decline]),
            repair_locality=locality,
        )
        assert result.stop_reason == "MECHANICAL_REPAIR_NOT_LOCAL"
        record = result.episodes[0]["mechanical_repair"]
        assert record["outcome"] == "MECHANICAL_REPAIR_NOT_LOCAL"
        assert "operator" in record["not_local_reason"]
        assert locality.calls == 0  # nothing to audit — no v2 exists
        assert _node_ids(root) == [BLOCKED, "target"]


# --- drift gates (§36.4/5) ----------------------------------------------------------


def test_diff_gate_rejects_node_set_change_before_locality_audit() -> None:
    """§36.4-partial/§13: an added/dropped/renamed obligation is deterministi-
    cally invalid; the locality auditor never runs."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        replanned = _patch(new_nodes=_nodes() + [
            {"node_id": "h3", "goal": "Helper lemma three.",
             "depends_on": ["h2"], "premise_fact_ids": []},
        ])
        locality = _ScriptedRepairLocality()
        result = _run(
            root, builder=_ScriptedBuilder([_bad_patch()]),
            factory=_AuditorFactory([]),
            repairer=_ScriptedRepairer([replanned]),
            repair_locality=locality,
        )
        assert result.stop_reason == "MECHANICAL_REPAIR_INVALID"
        record = result.episodes[0]["mechanical_repair"]
        assert record["diff_errors"]
        assert locality.calls == 0
        assert _node_ids(root) == [BLOCKED, "target"]


def test_strategy_drift_locality_invalid() -> None:
    """§36.5/§13: only LOCAL_MECHANICAL_REPAIR may enter the second
    validation; STRATEGY_DRIFT is terminal, nothing applied."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        factory = _AuditorFactory([])
        result = _run(
            root, builder=_ScriptedBuilder([_bad_patch()]),
            factory=factory,
            repairer=_ScriptedRepairer([_repaired_patch()]),
            repair_locality=_ScriptedRepairLocality("STRATEGY_DRIFT"),
        )
        assert result.stop_reason == "MECHANICAL_REPAIR_INVALID"
        assert result.episodes[0]["mechanical_repair"]["locality"]["locality"] == "STRATEGY_DRIFT"
        assert all(i.calls == 0 for i in factory.instances)
        assert _node_ids(root) == [BLOCKED, "target"]


def test_operator_drift_locality_invalid() -> None:
    """§36.4: operator drift is impossible by construction (the repair schema
    has no operator field — the driver locks the sketch's operator); an
    auditor claiming OPERATOR_DRIFT is still terminal, never applied."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        result = _run(
            root, builder=_ScriptedBuilder([_bad_patch()]),
            factory=_AuditorFactory([]),
            repairer=_ScriptedRepairer([_repaired_patch()]),
            repair_locality=_ScriptedRepairLocality("OPERATOR_DRIFT"),
        )
        assert result.stop_reason == "MECHANICAL_REPAIR_INVALID"
        assert result.episodes[0]["operator"] == "INSERT_CUT_SET"
        assert _node_ids(root) == [BLOCKED, "target"]


# --- frozen downstream behavior (§36.7/10) ------------------------------------------


def test_auditor_reject_never_triggers_mechanical_repair() -> None:
    """§36.7/§19: REJECT after a mechanical PASS is terminal for the frozen
    auditor path; the mechanical repairer must not intervene."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        repairer = _ScriptedRepairer([])
        result = _run(
            root, builder=_ScriptedBuilder([_patch()]),
            factory=_AuditorFactory(["REJECT"]),
            repairer=repairer, repair_locality=_ScriptedRepairLocality(),
        )
        assert result.stop_reason == "STRUCTURAL_AUDITOR_REJECT"
        assert repairer.calls == 0


def test_revise_after_repair_reuses_exactly_one_n2q_round() -> None:
    """§36.10/§15: AUDITOR_REVISE on the repaired patch still gets exactly
    one N2Q revision; a second REVISE is terminal."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        reviser = _ScriptedReviser([_revision()])
        result = _run(
            root, builder=_ScriptedBuilder([_bad_patch()]),
            reviser=reviser, factory=_AuditorFactory(["REVISE", "PASS"]),
            repairer=_ScriptedRepairer([_repaired_patch()]),
            repair_locality=_ScriptedRepairLocality(),
        )
        assert reviser.calls == 1
        assert result.episodes[0]["outcome"] == "PATCH_APPLIED"
        assert result.episodes[0]["revision"]["outcome"] == "REVISION_PASS"
        assert result.stop_reason == "TARGET_SOLVED"
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        reviser = _ScriptedReviser([_revision()])
        result = _run(
            root, builder=_ScriptedBuilder([_bad_patch()]),
            reviser=reviser, factory=_AuditorFactory(["REVISE", "REVISE"]),
            repairer=_ScriptedRepairer([_repaired_patch()]),
            repair_locality=_ScriptedRepairLocality(),
        )
        assert reviser.calls == 1
        assert result.stop_reason == "REVISION_FAILED"
        assert result.episodes[0]["revision"]["outcome"] == "REVISION_STILL_REVISE"


# --- truth boundary + regression default (§36.8/14) ---------------------------------


def test_repair_path_never_writes_facts() -> None:
    """§36.8/§23: a mechanical repair admits no Facts; only the
    worker->verifier path does."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        result = _run(
            root, builder=_ScriptedBuilder([_bad_patch()]),
            factory=_AuditorFactory(["PASS"]),
            repairer=_ScriptedRepairer([_repaired_patch()]),
            repair_locality=_ScriptedRepairLocality(),
        )
        assert result.stop_reason == "TARGET_SOLVED"
        episode = result.episodes[0]
        assert episode["outcome"] == "PATCH_APPLIED"
        assert episode["mechanical_repair"]["outcome"] == "MECHANICAL_REPAIR_PASS"
        assert episode["facts_admitted_by_refinement"] == 0
        assert all(f.author == "n2w-test" for f in FactGraph(root).list_facts())


def test_default_none_is_frozen_n2u_behavior() -> None:
    """§36.14-partial/§25: with mechanical_repair=None the seam is inert —
    a Mechanical FAIL is terminal exactly as in frozen N2U/N2V."""
    with TemporaryDirectory() as tmp:
        root = _workspace(Path(tmp))
        factory = _AuditorFactory([])
        result = _run(
            root, builder=_ScriptedBuilder([_bad_patch()]),
            factory=factory,
        )
        assert result.stop_reason == "MECHANICAL_FAIL"
        assert "mechanical_repair" not in result.episodes[0]
        assert all(i.calls == 0 for i in factory.instances)
        assert _node_ids(root) == [BLOCKED, "target"]
