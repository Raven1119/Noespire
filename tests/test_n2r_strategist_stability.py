"""N2R strategist stability audit — deterministic contract tests (task card §35).

Seams under test:
- sampler.prepare_snapshot: strips prior Strategist/Auditor/revision artifacts
  (strategist/, revisions/, local_refinements/, treatment_journal.jsonl) while
  preserving the mathematical decision state byte-for-byte.
- sampler.run_samples: K fixed up front; every sample receives a byte-identical
  rendered prompt (hash-proven); fresh sessions; DECLINE/REJECT never revise;
  REVISE triggers exactly one N2Q-protocol revision; proposals may apply only
  to the sample's own workspace copy — the canonical snapshot is hash-checked
  unchanged; timeouts are recorded outcomes, never crashes or retries.

All tests are model-free: scripted strategists/revisers/auditors only.
"""

from __future__ import annotations

import hashlib
import inspect
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
sys.path.insert(0, str(REPO_ROOT / "experiments" / "n2q_auditor_guided_revision"))
sys.path.insert(0, str(REPO_ROOT / "experiments" / "n2r_strategist_stability"))

from research.local_refinement import (  # noqa: E402
    AuditorResult,
    _build_context,
)
from research.graph import FactGraph  # noqa: E402
from research.obligation import ObligationRegistry  # noqa: E402
from research.problem import ProblemSpec  # noqa: E402
from research.scaffold import ProofScaffold, ScaffoldNode  # noqa: E402

import strategist as n2p_strategist  # noqa: E402
import treatment_driver as n2p_driver  # noqa: E402
from strategist import parse_strategist_output, strategist_prompt  # noqa: E402
from reviser import (  # noqa: E402
    MathematicalReviser,
    OperatorDriftError,
    parse_revision_output,
    revision_prompt,
)

import sampler  # noqa: E402  (module under test)
from sampler import SAMPLE_OUTCOMES, prepare_snapshot, run_samples, tree_hash  # noqa: E402

BLOCKED = "mid"
STATEMENT = "Lemma M implies theorem T."
REVISE_REASON = "The second cut does not fix the quantifier domain of m."
PID = "p"


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


def _decision(operator="INSERT_CUT_SET", **overrides):
    return parse_strategist_output(
        _strategist_json(operator, **overrides), blocked_node_id=BLOCKED
    )


def _revision(operator="INSERT_CUT_SET", repairable=True, **overrides):
    payload = json.loads(_strategist_json(operator, **overrides))
    payload["repairable"] = repairable
    return parse_revision_output(
        json.dumps(payload), blocked_node_id=BLOCKED, expected_operator=operator
    )


def _workspace(root: Path, *, with_prior_decision_artifacts: bool = False) -> Path:
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
    if with_prior_decision_artifacts:
        (problem_dir / "strategist").mkdir()
        (problem_dir / "strategist" / f"strategist-001-{BLOCKED}.json").write_text(
            json.dumps({"blocked_node_id": BLOCKED, "raw": _strategist_json("SPLIT")}),
            encoding="utf-8",
        )
        (problem_dir / "revisions").mkdir()
        (problem_dir / "revisions" / f"revision-001-{BLOCKED}.json").write_text(
            json.dumps({"blocked_node_id": BLOCKED, "raw": "{}"}), encoding="utf-8"
        )
        (problem_dir / "local_refinements").mkdir()
        (problem_dir / "local_refinements" / "cut-deadbeef.json").write_text(
            json.dumps({
                "problem_id": PID,
                "blocked_node_id": BLOCKED,
                "outcome": "AUDITOR_REVISE",
                "proposal": {"obstruction": "prior cut proposal"},
            }),
            encoding="utf-8",
        )
        (problem_dir / "treatment_journal.jsonl").write_text(
            json.dumps({"event": "horizon_handoff"}) + "\n", encoding="utf-8"
        )
    return problem_dir


class _ScriptedStrategist:
    def __init__(self, results) -> None:
        self.results = list(results)
        self.calls = 0
        self.last_prompt = None

    def strategize(self, context):
        self.calls += 1
        self.last_prompt = strategist_prompt(context)
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
    """One fresh auditor instance per factory call (session freshness)."""

    def __init__(self, verdicts) -> None:
        self.verdicts = list(verdicts)
        self.instances = []

    def __call__(self, operation):
        instance = _FreshAuditor(self.verdicts)
        self.instances.append(instance)
        return instance


def _run(snapshot_source: Path, runs_dir: Path, *, k=3, strategist, reviser, factory):
    snapshot = prepare_snapshot(snapshot_source, runs_dir / "snapshot")
    return run_samples(
        snapshot,
        runs_dir=runs_dir,
        k=k,
        problem_id=PID,
        frontier=BLOCKED,
        strategist=strategist,
        reviser=reviser,
        auditor_for=factory,
    )


# --- snapshot preparation (§35.2/§35.3) ----------------------------------------


def test_prepare_snapshot_strips_prior_decision_artifacts() -> None:
    """§5/§35.2-3: prior Strategist/Auditor/revision artifacts are stripped;
    the mathematical state files survive byte-for-byte."""
    with TemporaryDirectory() as tmp:
        source = _workspace(Path(tmp) / "src", with_prior_decision_artifacts=True)
        before = tree_hash(source.parent.parent)  # includes artifacts
        dest = prepare_snapshot(source, Path(tmp) / "snap")
        assert tree_hash(dest) != before
        for name in ("strategist", "revisions", "local_refinements",
                     "treatment_journal.jsonl"):
            assert not (dest / name).exists()
        # (obligations.json is lazily created by ObligationRegistry.add; the
        # scaffold + attempts carry the mathematical state here.)
        assert (dest / "scaffold.json").read_bytes() == (source / "scaffold.json").read_bytes()
        assert (dest / "attempts" / "attempt-000001.json").read_bytes() == (
            source / "attempts" / "attempt-000001.json"
        ).read_bytes()


def test_stripped_context_has_no_prior_refinement_summary() -> None:
    """§35.2/3: the stripped snapshot's context carries no anchoring summary
    even though the source workspace had a same-node REVISE record."""
    with TemporaryDirectory() as tmp:
        source = _workspace(Path(tmp) / "src", with_prior_decision_artifacts=True)
        dest = prepare_snapshot(source, Path(tmp) / "snap")
        context = _build_context(
            scaffold=ProofScaffold(dest / "scaffold.json"),
            graph=FactGraph(dest),
            registry=ObligationRegistry(dest / "obligations.json"),
            problem_id=PID,
            blocked_node_id=BLOCKED,
        )
        assert context.previous_refinement_summary is None


# --- outcome vocabulary + frozen-surface reuse (§35.12/13/14/16) ----------------


def test_sample_outcome_vocabulary() -> None:
    """§11 mechanical classes plus honest runtime sentinels."""
    assert {
        "DECLINE",
        "MECHANICALLY_INVALID",
        "AUDITOR_PASS",
        "AUDITOR_REVISE_PASS",
        "AUDITOR_REVISE_FAIL",
        "AUDITOR_REJECT",
        "STRATEGIST_TIMEOUT",
        "REVISER_TIMEOUT",
    } <= set(SAMPLE_OUTCOMES)


def test_sampler_reuses_frozen_strategist_prompt_and_operators() -> None:
    """§35.12/14: N2R introduces no prompt or operator of its own."""
    assert sampler.strategist_prompt is n2p_strategist.strategist_prompt
    assert sampler._OPERATION is n2p_driver._OPERATION
    assert set(sampler._OPERATION) == {"SPLIT", "INSERT_CUT_SET", "ADD_ALTERNATIVE_ROUTE"}


def test_sampler_has_no_solver_or_worker_parameter() -> None:
    """§35.10/§3: measurement only — no NodeSolver can be reached."""
    params = set(inspect.signature(run_samples).parameters)
    assert not ({"worker", "verifier", "solver_config", "solver"} & params)


# --- sampling identity + isolation (§35.1/4/5/6/11/17) --------------------------


def test_all_samples_receive_byte_identical_prompt() -> None:
    """§35.1/§4: the rendered strategist prompt hash is identical across K."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = _workspace(root / "src", with_prior_decision_artifacts=True)
        strategist = _ScriptedStrategist([_decision(), _decision(), _decision()])
        result = _run(
            source, root / "runs", k=3,
            strategist=strategist,
            reviser=_ScriptedReviser([]),
            factory=_AuditorFactory(["PASS", "PASS", "PASS"]),
        )
        hashes = {record.prompt_sha256 for record in result.records}
        assert len(hashes) == 1
        # And it equals the prompt rendered directly from the stripped snapshot.
        snapshot_context = _build_context(
            scaffold=ProofScaffold(root / "runs" / "snapshot" / "scaffold.json"),
            graph=FactGraph(root / "runs" / "snapshot"),
            registry=ObligationRegistry(root / "runs" / "snapshot" / "obligations.json"),
            problem_id=PID,
            blocked_node_id=BLOCKED,
        )
        expected = hashlib.sha256(
            strategist_prompt(snapshot_context).encode("utf-8")
        ).hexdigest()
        assert hashes == {expected}


def test_k_fixed_and_one_fresh_strategist_call_per_sample() -> None:
    """§35.4/17: exactly K records, exactly K strategist sessions."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = _workspace(root / "src")
        strategist = _ScriptedStrategist([_decision() for _ in range(8)])
        result = _run(
            source, root / "runs", k=8,
            strategist=strategist,
            reviser=_ScriptedReviser([]),
            factory=_AuditorFactory(["PASS"] * 8),
        )
        assert len(result.records) == 8
        assert strategist.calls == 8
        assert all(r.outcome == "AUDITOR_PASS" for r in result.records)


def test_pass_applies_to_sample_copy_only_snapshot_untouched() -> None:
    """§35.5/6/11: an auditor PASS applies inside the sample's own copy; the
    canonical snapshot (including facts/) is hash-identical afterwards."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = _workspace(root / "src")
        result = _run(
            source, root / "runs", k=1,
            strategist=_ScriptedStrategist([_decision()]),
            reviser=_ScriptedReviser([]),
            factory=_AuditorFactory(["PASS"]),
        )
        assert result.snapshot_unchanged
        snapshot = root / "runs" / "snapshot"
        assert tree_hash(snapshot) == result.snapshot_hash
        assert [n.node_id for n in ProofScaffold(snapshot / "scaffold.json").list_nodes()] == [
            BLOCKED, "target",
        ]
        # The sample copy DID take the patch.
        sample_scaffold = (
            root / "runs" / "sample_01" / "workspace" / PID / "scaffold.json"
        )
        sample_nodes = [n.node_id for n in ProofScaffold(sample_scaffold).list_nodes()]
        assert "h1" in sample_nodes and "h2" in sample_nodes


# --- N2Q revision protocol inside a sample (§35.7/8/9) --------------------------


def test_decline_triggers_no_revision() -> None:
    """§35.8: DECLINE is terminal — zero reviser calls, zero auditor calls."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = _workspace(root / "src")
        reviser = _ScriptedReviser([])
        factory = _AuditorFactory([])
        result = _run(
            source, root / "runs", k=1,
            strategist=_ScriptedStrategist([
                _decision("DECLINE", new_nodes=[],
                          decline_reason="No meaningful reduction available.")
            ]),
            reviser=reviser,
            factory=factory,
        )
        assert result.records[0].outcome == "DECLINE"
        assert "No meaningful reduction" in result.records[0].decline_reason
        assert reviser.calls == 0
        assert all(i.calls == 0 for i in factory.instances)


def test_reject_triggers_no_revision() -> None:
    """§35.9: REJECT is terminal — zero reviser calls."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = _workspace(root / "src")
        reviser = _ScriptedReviser([])
        result = _run(
            source, root / "runs", k=1,
            strategist=_ScriptedStrategist([_decision()]),
            reviser=reviser,
            factory=_AuditorFactory(["REJECT"]),
        )
        assert result.records[0].outcome == "AUDITOR_REJECT"
        assert reviser.calls == 0


def test_revise_runs_exactly_one_revision_then_pass() -> None:
    """§35.7: REVISE -> exactly one N2Q revision -> v2 PASS -> AUDITOR_REVISE_PASS."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = _workspace(root / "src")
        reviser = _ScriptedReviser([_revision()])
        factory = _AuditorFactory(["REVISE", "PASS"])
        result = _run(
            source, root / "runs", k=1,
            strategist=_ScriptedStrategist([_decision()]),
            reviser=reviser,
            factory=factory,
        )
        record = result.records[0]
        assert record.outcome == "AUDITOR_REVISE_PASS"
        assert reviser.calls == 1
        assert len(factory.instances) == 2  # v1 auditor + fresh v2 auditor
        assert record.revision["outcome"] == "REVISION_PASS"
        # The v2 patch applied to the sample copy only.
        assert result.snapshot_unchanged


def test_second_revise_is_terminal() -> None:
    """§35.7: a second REVISE stops the sample — no v3, no extra sessions."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = _workspace(root / "src")
        reviser = _ScriptedReviser([_revision()])
        result = _run(
            source, root / "runs", k=1,
            strategist=_ScriptedStrategist([_decision()]),
            reviser=reviser,
            factory=_AuditorFactory(["REVISE", "REVISE"]),
        )
        record = result.records[0]
        assert record.outcome == "AUDITOR_REVISE_FAIL"
        assert record.revision["outcome"] == "REVISION_STILL_REVISE"
        assert reviser.calls == 1


def test_revision_not_local_is_terminal_without_second_auditor() -> None:
    """§35.7 + N2Q §4: unrepairable feedback never re-enters the pipeline."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = _workspace(root / "src")
        reviser = _ScriptedReviser([
            _revision(repairable=False, new_nodes=[],
                      decline_reason="The objection is to the route itself.")
        ])
        factory = _AuditorFactory(["REVISE"])
        result = _run(
            source, root / "runs", k=1,
            strategist=_ScriptedStrategist([_decision()]),
            reviser=reviser,
            factory=factory,
        )
        record = result.records[0]
        assert record.outcome == "AUDITOR_REVISE_FAIL"
        assert record.revision["outcome"] == "REVISION_NOT_LOCAL"
        assert len(factory.instances) == 1  # no v2 auditor session


def test_operator_drift_is_revision_invalid() -> None:
    """N2Q §4 enforced inside a sample: operator drift -> REVISION_INVALID."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = _workspace(root / "src")
        reviser = _ScriptedReviser([OperatorDriftError("operator drift")])
        result = _run(
            source, root / "runs", k=1,
            strategist=_ScriptedStrategist([_decision()]),
            reviser=reviser,
            factory=_AuditorFactory(["REVISE"]),
        )
        record = result.records[0]
        assert record.outcome == "AUDITOR_REVISE_FAIL"
        assert record.revision["outcome"] == "REVISION_INVALID"


def test_mechanical_reject_is_mechanically_invalid() -> None:
    """§11: frozen mechanical validation gates before any auditor session."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = _workspace(root / "src")
        factory = _AuditorFactory([])
        result = _run(
            source, root / "runs", k=1,
            strategist=_ScriptedStrategist([
                _decision(new_nodes=[
                    {"node_id": "h1", "goal": "Helper lemma one.",
                     "depends_on": ["nonexistent-sibling"], "premise_fact_ids": []},
                ])
            ]),
            reviser=_ScriptedReviser([]),
            factory=factory,
        )
        record = result.records[0]
        assert record.outcome == "MECHANICALLY_INVALID"
        assert record.mechanical_errors
        assert all(i.calls == 0 for i in factory.instances)


# --- timeout sentinels (§32 runtime honesty; horizon stays 600s) ----------------


def test_strategist_timeout_recorded_run_continues() -> None:
    """A 600s strategist timeout is an outcome, never a crash or a retry."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = _workspace(root / "src")
        timeout = subprocess.TimeoutExpired(cmd="codex", timeout=600)
        strategist = _ScriptedStrategist([timeout, _decision()])
        result = _run(
            source, root / "runs", k=2,
            strategist=strategist,
            reviser=_ScriptedReviser([]),
            factory=_AuditorFactory(["PASS"]),
        )
        assert [r.outcome for r in result.records] == ["STRATEGIST_TIMEOUT", "AUDITOR_PASS"]
        assert strategist.calls == 2  # no retry of the timed-out sample


def test_reviser_timeout_recorded() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = _workspace(root / "src")
        timeout = subprocess.TimeoutExpired(cmd="codex", timeout=600)
        result = _run(
            source, root / "runs", k=1,
            strategist=_ScriptedStrategist([_decision()]),
            reviser=_ScriptedReviser([timeout]),
            factory=_AuditorFactory(["REVISE"]),
        )
        assert result.records[0].outcome == "REVISER_TIMEOUT"


# --- per-sample persistence (§35.17 adjacent; §34) ------------------------------


def test_each_sample_persists_its_evidence() -> None:
    """§34: every sample dir carries the strategist packet and the record;
    revised samples also carry the revision packet."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = _workspace(root / "src")
        result = _run(
            source, root / "runs", k=2,
            strategist=_ScriptedStrategist([
                _decision(),
                _decision("DECLINE", new_nodes=[], decline_reason="nothing useful"),
            ]),
            reviser=_ScriptedReviser([_revision()]),
            factory=_AuditorFactory(["REVISE", "PASS"]),
        )
        s1 = root / "runs" / "sample_01"
        s2 = root / "runs" / "sample_02"
        assert (s1 / "strategist_packet.json").is_file()
        assert (s1 / "revision_packet.json").is_file()
        assert (s1 / "mechanical_result.json").is_file()
        assert (s2 / "strategist_packet.json").is_file()
        assert not (s2 / "revision_packet.json").exists()
        record = json.loads((s1 / "mechanical_result.json").read_text(encoding="utf-8"))
        assert record["outcome"] == "AUDITOR_REVISE_PASS"
        assert record["prompt_sha256"] == result.records[0].prompt_sha256
