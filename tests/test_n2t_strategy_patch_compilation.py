"""N2T strategy-to-GraphPatch compilation probe — contract tests (§29).

The probe asks: can a fresh, strategy-bound Patch Builder compile a frozen
N2S Strategy Sketch into the existing typed GraphPatch, through the frozen
mechanical validator + structural auditor (+ at most one N2Q revision)?

Pinned contracts: operator immutable by construction, frozen schemas/parsers/
validators reused, no canonical-graph mutation, no NodeSolver, REVISE uses
exactly the N2Q one-round protocol, REJECT/DECLINE terminal, K=1 per sketch,
no sketch-audit anchoring.

All tests are model-free: scripted builders/revisers/auditors only.
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
):
    sys.path.insert(0, str(REPO_ROOT / rel))

from research.local_refinement import AuditorResult, run_local_redecomposition  # noqa: E402
from research.obligation import ObligationRegistry  # noqa: E402
from research.problem import ProblemSpec  # noqa: E402
from research.scaffold import ProofScaffold, ScaffoldNode  # noqa: E402

import strategist as n2p_strategist  # noqa: E402
from sampler import prepare_snapshot, tree_hash  # noqa: E402  (N2R, read-only)
from sketch import parse_sketch_output  # noqa: E402  (N2S, read-only)
from reviser import OperatorDriftError, parse_revision_output  # noqa: E402  (N2Q)

from patch_builder import (  # noqa: E402  (module under test)
    CLAIM_FIDELITY,
    COMPILATION_OUTCOMES,
    FIDELITY_CLASSES,
    PATCH_SCHEMA,
    StrategyBoundPatchBuilder,
    _assemble_decision,
    parse_patch_build_output,
    patch_builder_prompt,
    run_compilations,
)

BLOCKED = "mid"
STATEMENT = "Lemma M implies theorem T."
PID = "p"
REVISE_REASON = "The second claim does not fix the quantifier domain of m."


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
    (problem_dir / "attempts").mkdir()
    (problem_dir / "attempts" / "attempt-000001.json").write_text(
        json.dumps({
            "attempt_id": "attempt-000001",
            "obligation_id": f"scaffold:{PID}:{BLOCKED}",
            "verdict": "FAIL",
            "error": None,
            "candidate_artifact": {"statement": STATEMENT},
            "verifier_artifact": {"reason": "the final step invokes theorem T"},
        }),
        encoding="utf-8",
    )
    return problem_dir


class _ScriptedBuilder:
    def __init__(self, results) -> None:
        self.results = list(results)
        self.calls = 0
        self.last_prompt = None

    def compile(self, context, sketch):
        self.calls += 1
        self.last_prompt = patch_builder_prompt(context, sketch)
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
        from reviser import revision_prompt
        self.calls += 1
        self.last_prompt = revision_prompt(context, v1, auditor_reasons)
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


def _run(source: Path, runs_dir: Path, *, sketches, builder, reviser, factory):
    snapshot = prepare_snapshot(source, runs_dir / "snapshot")
    return run_compilations(
        snapshot,
        runs_dir=runs_dir,
        sketches=sketches,
        problem_id=PID,
        frontier=BLOCKED,
        builder=builder,
        reviser=reviser,
        auditor_for=factory,
    )


def _patch(operator="ADD_ALTERNATIVE_ROUTE"):
    return parse_patch_build_output(_patch_json())


def _revision(operator="ADD_ALTERNATIVE_ROUTE", repairable=True):
    payload = json.loads(_sketch(operator))
    payload["new_nodes"] = json.loads(_patch_json())["new_nodes"]
    payload["repairable"] = repairable
    return parse_revision_output(
        json.dumps(payload), blocked_node_id=BLOCKED, expected_operator=operator
    )


# --- operator immutability + frozen reuse (§29.1-4, §8/§9) ----------------------


def test_patch_schema_cannot_express_operator() -> None:
    """§8/§29.1-2: the builder output has no operator field — operator drift
    is impossible by construction, not by instruction."""
    assert "operator" not in PATCH_SCHEMA["properties"]
    assert set(PATCH_SCHEMA["properties"]) == {
        "compilation_decline", "decline_reason", "new_nodes",
    }


def test_assembled_decision_operator_always_equals_sketch() -> None:
    """§8: the driver copies the operator from the frozen sketch."""
    decision = _assemble_decision(
        _sketch_result("INSERT_CUT_SET"),
        parse_patch_build_output(_patch_json()),
        blocked_node_id=BLOCKED,
    )
    assert decision.operator == "INSERT_CUT_SET"
    assert decision.mathematical_idea.endswith("multiplicative characters.")
    assert [n["node_id"] for n in decision.new_nodes] == ["h1", "h2"]


def test_frozen_schemas_parsers_and_validator_reused() -> None:
    """§29.3/4 + §9: no operator semantics re-implemented in the probe."""
    import patch_builder

    assert patch_builder.compile_to_builder_result is n2p_strategist.compile_to_builder_result
    assert patch_builder.parse_strategist_output is n2p_strategist.parse_strategist_output
    assert patch_builder.run_local_redecomposition is run_local_redecomposition
    # The patch item shape is copied verbatim from the frozen schemas.
    from research.agents import _CUT_SCHEMA
    assert (
        PATCH_SCHEMA["properties"]["new_nodes"]["items"]
        == _CUT_SCHEMA["properties"]["new_nodes"]["items"]
    )


def test_mechanical_reject_via_frozen_validator() -> None:
    """§29.4/§14: frozen mechanical validation gates before any auditor."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        factory = _AuditorFactory([])
        bad = parse_patch_build_output(_patch_json(new_nodes=[
            {"node_id": "h1", "goal": "Helper lemma one.",
             "depends_on": ["nonexistent"], "premise_fact_ids": []},
        ]))
        result = _run(
            _workspace(root / "src"), root / "runs",
            sketches=(("s1", _sketch_result()),),
            builder=_ScriptedBuilder([bad]),
            reviser=_ScriptedReviser([]),
            factory=factory,
        )
        record = result.records[0]
        assert record.outcome == "MECHANICAL_FAIL"
        assert record.mechanical_errors
        assert all(i.calls == 0 for i in factory.instances)


# --- isolation + no downstream machinery (§29.5-7, §23/§24) ---------------------


def test_patch_never_enters_canonical_graph() -> None:
    """§29.5/7 + §24: an auditor PASS applies inside the sketch's own temp
    copy only; the snapshot (incl. facts) is hash-identical afterwards."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        result = _run(
            _workspace(root / "src"), root / "runs",
            sketches=(("s1", _sketch_result()),),
            builder=_ScriptedBuilder([_patch()]),
            reviser=_ScriptedReviser([]),
            factory=_AuditorFactory(["PASS"]),
        )
        assert result.records[0].outcome == "AUDITOR_PASS"
        assert result.snapshot_unchanged
        snapshot = root / "runs" / "snapshot"
        assert tree_hash(snapshot) == result.snapshot_hash
        assert [n.node_id for n in ProofScaffold(snapshot / "scaffold.json").list_nodes()] == [
            BLOCKED, "target",
        ]
        applied = (
            root / "runs" / "sketch_s1" / "workspace" / PID / "scaffold.json"
        )
        assert "h1" in [n.node_id for n in ProofScaffold(applied).list_nodes()]


def test_probe_has_no_solver_parameter() -> None:
    """§29.6/§23: no NodeSolver, no verifier — 0 new Facts by construction."""
    params = set(inspect.signature(run_compilations).parameters)
    assert not ({"worker", "verifier", "solver", "solver_config"} & params)


# --- N2Q revision protocol + terminal outcomes (§29.8/9, §15/§16) ---------------


def test_revise_reuses_n2q_one_round_protocol() -> None:
    """§15/§29.8: REVISE -> exactly one N2Q revision -> v2 PASS."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        reviser = _ScriptedReviser([_revision()])
        factory = _AuditorFactory(["REVISE", "PASS"])
        result = _run(
            _workspace(root / "src"), root / "runs",
            sketches=(("s1", _sketch_result()),),
            builder=_ScriptedBuilder([_patch()]),
            reviser=reviser,
            factory=factory,
        )
        record = result.records[0]
        assert record.outcome == "AUDITOR_REVISE_PASS"
        assert reviser.calls == 1
        assert len(factory.instances) == 2
        assert record.revision["outcome"] == "REVISION_PASS"


def test_second_revise_and_reject_are_terminal() -> None:
    """§29.8/9: v2 REVISE stops; REJECT triggers zero revision calls."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        reviser = _ScriptedReviser([_revision()])
        result = _run(
            _workspace(root / "src"), root / "runs",
            sketches=(("s1", _sketch_result()),),
            builder=_ScriptedBuilder([_patch()]),
            reviser=reviser,
            factory=_AuditorFactory(["REVISE", "REVISE"]),
        )
        assert result.records[0].outcome == "AUDITOR_REVISE_FAIL"
        assert result.records[0].revision["outcome"] == "REVISION_STILL_REVISE"
        assert reviser.calls == 1
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        reviser = _ScriptedReviser([])
        result = _run(
            _workspace(root / "src"), root / "runs",
            sketches=(("s1", _sketch_result()),),
            builder=_ScriptedBuilder([_patch()]),
            reviser=reviser,
            factory=_AuditorFactory(["REJECT"]),
        )
        assert result.records[0].outcome == "AUDITOR_REJECT"
        assert reviser.calls == 0


# --- sampling policy + anchoring (§29.10/11, §3/§10/§12) ------------------------


def test_one_builder_call_per_sketch_k_fixed() -> None:
    """§12/§29.10: K=1 per sketch; the number of sketches fixes the run size."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        builder = _ScriptedBuilder([_patch(), _patch(), _patch(), _patch()])
        result = _run(
            _workspace(root / "src"), root / "runs",
            sketches=tuple((f"s{i}", _sketch_result()) for i in range(4)),
            builder=builder,
            reviser=_ScriptedReviser([]),
            factory=_AuditorFactory(["PASS"] * 4),
        )
        assert len(result.records) == 4
        assert builder.calls == 4
        assert all(r.outcome == "AUDITOR_PASS" for r in result.records)


def test_prompt_carries_sketch_but_no_audit_verdict() -> None:
    """§3/§10/§29.11: the builder sees the sketch's stated fields, never the
    N2S SketchAuditor verdict or any historical patch."""
    sketch = _sketch_result()
    from research.local_refinement import _build_context
    from research.graph import FactGraph
    with TemporaryDirectory() as tmp:
        ws = _workspace(Path(tmp))
        context = _build_context(
            scaffold=ProofScaffold(ws / "scaffold.json"),
            graph=FactGraph(ws),
            registry=ObligationRegistry(ws / "obligations.json"),
            problem_id=PID,
            blocked_node_id=BLOCKED,
        )
        prompt = patch_builder_prompt(context, sketch)
    assert sketch.mathematical_idea in prompt
    assert sketch.candidate_claims[0] in prompt
    assert 'operator ("ADD_ALTERNATIVE_ROUTE")' in prompt
    for banned in ("PLAUSIBLE", "strategy_class", "quality_audit",
                   "USEFUL_STRATEGY", "SketchAuditor"):
        assert banned not in prompt


# --- decline / timeout / vocabulary (§7/§13/§17/§19) ----------------------------


def test_compilation_decline_is_terminal() -> None:
    """§7: the builder may decline an uncompilable sketch; no auditor runs."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        factory = _AuditorFactory([])
        decline = parse_patch_build_output(_patch_json(
            compilation_decline=True, new_nodes=[],
            decline_reason="The sketch does not determine the cuts.",
        ))
        result = _run(
            _workspace(root / "src"), root / "runs",
            sketches=(("s1", _sketch_result("INSERT_CUT_SET")),),
            builder=_ScriptedBuilder([decline]),
            reviser=_ScriptedReviser([]),
            factory=factory,
        )
        record = result.records[0]
        assert record.outcome == "COMPILATION_DECLINE"
        assert "does not determine" in record.decline_reason
        assert all(i.calls == 0 for i in factory.instances)


def test_patch_timeout_is_recorded_not_retried() -> None:
    """§13: 600s bound unchanged; a builder timeout is an honest outcome."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        timeout = subprocess.TimeoutExpired(cmd="codex", timeout=600)
        builder = _ScriptedBuilder([timeout, _patch()])
        result = _run(
            _workspace(root / "src"), root / "runs",
            sketches=(("s1", _sketch_result()), ("s2", _sketch_result())),
            builder=builder,
            reviser=_ScriptedReviser([]),
            factory=_AuditorFactory(["PASS"]),
        )
        assert [r.outcome for r in result.records] == ["PATCH_TIMEOUT", "AUDITOR_PASS"]
        assert builder.calls == 2  # no retry
        assert result.records[0].elapsed_seconds is not None


def test_outcome_and_fidelity_vocabularies() -> None:
    assert {
        "COMPILATION_DECLINE", "MECHANICAL_FAIL", "AUDITOR_PASS",
        "AUDITOR_REJECT", "AUDITOR_REVISE_PASS", "AUDITOR_REVISE_FAIL",
        "PATCH_TIMEOUT", "SAMPLE_ERROR",
    } <= set(COMPILATION_OUTCOMES)
    assert set(FIDELITY_CLASSES) == {
        "FAITHFUL", "PARTIALLY_FAITHFUL", "STRATEGY_DRIFT",
    }
    assert set(CLAIM_FIDELITY) == {
        "PRESERVED_AND_REFINED", "DROPPED", "MATERIALLY_REPLACED",
        "UNRELATED_NEW_CLAIM",
    }


def test_parse_rejects_malformed_and_bad_item() -> None:
    with pytest.raises(ValueError):
        parse_patch_build_output("not json")
    with pytest.raises(ValueError):
        parse_patch_build_output(_patch_json(compilation_decline="yes"))
    with pytest.raises(ValueError):
        parse_patch_build_output(_patch_json(new_nodes=[{"node_id": "h1"}]))
