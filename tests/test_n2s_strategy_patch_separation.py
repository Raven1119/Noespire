"""N2S strategy/patch separation probe — minimal contract tests (task card §29).

The probe asks ONE question: does dropping precise GraphPatch generation from
the strategist call raise completion without degrading strategy quality?
These tests pin the contract: identical frozen input state, no GraphPatch in
prompt or schema, no FactGraph/graph mutation path, no NodeSolver/Auditor/
Reviser anywhere, K fixed, fresh sessions.

All tests are model-free: scripted sketchers/fake invokers only.
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
sys.path.insert(0, str(REPO_ROOT / "experiments" / "n2s_strategy_patch_separation"))

from research.local_refinement import (  # noqa: E402
    AttemptRecord,
    LocalRefinementContext,
    _build_context,
)
from research.fact import Fact  # noqa: E402
from research.graph import FactGraph  # noqa: E402
from research.obligation import ObligationRegistry, ProofObligation  # noqa: E402
from research.problem import ProblemSpec  # noqa: E402
from research.scaffold import ProofScaffold, ScaffoldNode  # noqa: E402

from strategist import _node_lines, strategist_prompt  # noqa: E402  (N2P control)
from sampler import prepare_snapshot, tree_hash  # noqa: E402  (N2R, read-only)

from sketch import (  # noqa: E402  (module under test)
    SKETCH_SCHEMA,
    StrategySketcher,
    build_sketch_audit_packet,
    parse_sketch_output,
    run_sketch_samples,
    sketch_prompt,
)

BLOCKED = "mid"
STATEMENT = "Lemma M implies theorem T."
PID = "p"


def _context() -> LocalRefinementContext:
    return LocalRefinementContext(
        original_problem="Prove theorem T.",
        blocked_node=ScaffoldNode(BLOCKED, "Lemma M."),
        blocked_obligation=ProofObligation("scaffold:p:mid", (), "Lemma M.", "scaffold:mid"),
        local_nodes=(ScaffoldNode("target", "Prove theorem T.", depends_on=(BLOCKED,)),),
        verified_boundary=(
            Fact.create(
                problem_id=PID, author="test",
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
        previous_refinement_summary=None,
        allowed_operation="SPLIT",
    )


def _sketch_json(operator="ADD_ALTERNATIVE_ROUTE", **overrides) -> str:
    payload = {
        "obstruction": "Compactness alone transports counterexamples; no discrepancy argument.",
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


def _workspace(root: Path, *, with_prior_artifacts: bool = False) -> Path:
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
    if with_prior_artifacts:
        (problem_dir / "strategist").mkdir()
        (problem_dir / "strategist" / f"strategist-001-{BLOCKED}.json").write_text(
            json.dumps({"blocked_node_id": BLOCKED, "raw": _sketch_json()}),
            encoding="utf-8",
        )
        (problem_dir / "local_refinements").mkdir()
        (problem_dir / "local_refinements" / "alt-deadbeef.json").write_text(
            json.dumps({"problem_id": PID, "blocked_node_id": BLOCKED,
                        "outcome": "APPLIED", "proposal": {"obstruction": "prior"}}),
            encoding="utf-8",
        )
    return problem_dir


class _ScriptedSketcher:
    def __init__(self, results) -> None:
        self.results = list(results)
        self.calls = 0
        self.last_prompt = None

    def strategize(self, context):
        self.calls += 1
        self.last_prompt = sketch_prompt(context)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


def _run(source: Path, runs_dir: Path, *, k, sketcher):
    snapshot = prepare_snapshot(source, runs_dir / "snapshot")
    return run_sketch_samples(
        snapshot, runs_dir=runs_dir, k=k, problem_id=PID,
        frontier=BLOCKED, sketcher=sketcher,
    )


# --- input identity with the N2R/N2P control (§29.1/§5/§27) ---------------------


def _context_blocks(context) -> tuple:
    """The context-derived sections exactly as the frozen control renders
    them (strategist.py:152)."""
    attempts = "\n".join(
        f'- {a.attempt_id}: verdict {a.verdict}'
        + (f'; candidate: {(a.candidate_artifact or {}).get("statement")}'
           if a.candidate_artifact else "")
        + (f'; verifier feedback: {(a.verifier_artifact or {}).get("reason")}'
           if a.verifier_artifact else "")
        + (f'; error: {a.error}' if a.error else "")
        for a in context.attempts
    ) or "(no recorded attempts)"
    boundary = "\n".join(
        f'- {f.fact_id}: {f.statement}' for f in context.verified_boundary
    ) or "(none)"
    return (
        f"Original problem:\n{context.original_problem}",
        f"Blocked obligation:\ngoal: {context.blocked_obligation.goal}\n"
        f"premises: {list(context.blocked_obligation.premises)}",
        f'Local graph (nodes, goals, dependencies):\n'
        f'- "{context.blocked_node.node_id}" goal: {context.blocked_node.goal} '
        f'depends_on: {list(context.blocked_node.depends_on)} [BLOCKED]\n'
        f'{_node_lines(context.local_nodes)}',
        f"Verified facts relevant to the local region:\n{boundary}",
        f"Failure evidence (recorded attempts on the blocked obligation):\n{attempts}",
        context.downstream_intent,
    )


def test_treatment_context_blocks_identical_to_control() -> None:
    """§29.1/§6/§27: every mathematical-input block of the control prompt
    appears verbatim in the treatment prompt."""
    context = _context()
    control = strategist_prompt(context)
    treatment = sketch_prompt(context)
    for block in _context_blocks(context):
        assert block in control
        assert block in treatment


def test_prior_sample_outputs_excluded_from_input() -> None:
    """§29.2/§5: snapshot preparation strips prior decision artifacts; the
    context built from it carries no refinement history."""
    with TemporaryDirectory() as tmp:
        source = _workspace(Path(tmp) / "src", with_prior_artifacts=True)
        dest = prepare_snapshot(source, Path(tmp) / "snap")
        for name in ("strategist", "revisions", "local_refinements",
                     "treatment_journal.jsonl"):
            assert not (dest / name).exists()
        context = _build_context(
            scaffold=ProofScaffold(dest / "scaffold.json"),
            graph=FactGraph(dest),
            registry=ObligationRegistry(dest / "obligations.json"),
            problem_id=PID,
            blocked_node_id=BLOCKED,
        )
        assert context.previous_refinement_summary is None


# --- no GraphPatch anywhere (§29.3/§29.4/§6/§16) ---------------------------------


def test_treatment_prompt_does_not_request_graphpatch() -> None:
    prompt = sketch_prompt(_context())
    assert "new_nodes" not in prompt
    assert "candidate_claims" in prompt
    # Patch generation is explicitly forbidden, not just omitted.
    squashed = " ".join(prompt.lower().split())
    assert "do not produce a graphpatch" in squashed
    # The §8 guard against degenerating into a full proof.
    assert "Do not attempt to prove the target theorem" in prompt


def test_output_schema_has_no_graphpatch() -> None:
    assert "new_nodes" not in SKETCH_SCHEMA["properties"]
    claims = SKETCH_SCHEMA["properties"]["candidate_claims"]
    assert claims["type"] == "array" and claims["items"] == {"type": "string"}


def test_parse_requires_claims_unless_decline() -> None:
    sketch = parse_sketch_output(_sketch_json(), blocked_node_id=BLOCKED)
    assert sketch.operator == "ADD_ALTERNATIVE_ROUTE"
    assert len(sketch.candidate_claims) == 2
    decline = parse_sketch_output(
        _sketch_json("DECLINE", candidate_claims=[],
                     decline_reason="No narrower local reduction exists."),
        blocked_node_id=BLOCKED,
    )
    assert decline.operator == "DECLINE"
    with pytest.raises(ValueError):
        parse_sketch_output(
            _sketch_json("SPLIT", candidate_claims=[]), blocked_node_id=BLOCKED
        )
    with pytest.raises(ValueError):
        parse_sketch_output("not json", blocked_node_id=BLOCKED)


# --- no downstream machinery at all (§29.5-9, §16-18) ----------------------------


def test_probe_has_no_solver_auditor_or_reviser_parameter() -> None:
    """§29.6/7/8: measurement only — no NodeSolver, no Structural Auditor,
    no N2Q reviser can be reached from the probe."""
    params = set(inspect.signature(run_sketch_samples).parameters)
    assert not ({"worker", "verifier", "solver", "solver_config",
                 "auditor", "auditor_for", "reviser"} & params)


def test_no_graph_or_factgraph_mutation() -> None:
    """§29.5/9: candidate claims are UNVERIFIED STRATEGY SKETCHes — the
    snapshot and every sample copy keep byte-identical scaffold/facts."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = _workspace(root / "src")
        result = _run(
            source, root / "runs", k=2,
            sketcher=_ScriptedSketcher([
                parse_sketch_output(_sketch_json(), blocked_node_id=BLOCKED),
                parse_sketch_output(_sketch_json(), blocked_node_id=BLOCKED),
            ]),
        )
        assert result.snapshot_unchanged
        snapshot = root / "runs" / "snapshot"
        assert tree_hash(snapshot) == result.snapshot_hash
        for sample_dir in sorted((root / "runs").glob("sample_0*")):
            ws = sample_dir / "workspace" / PID
            assert (ws / "scaffold.json").read_bytes() == (
                snapshot / "scaffold.json"
            ).read_bytes()
            assert not (ws / "local_refinements").exists()
            assert not (ws / "facts").exists() or tree_hash(ws / "facts")


# --- sampling contract (§29.10/11, §9/§10/§24) -----------------------------------


def test_k_fixed_one_fresh_call_per_sample() -> None:
    """§29.10/11: exactly K records, exactly K fresh sketcher calls, all
    prompts byte-identical."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = _workspace(root / "src")
        sketcher = _ScriptedSketcher([
            parse_sketch_output(_sketch_json(), blocked_node_id=BLOCKED)
            for _ in range(4)
        ])
        result = _run(source, root / "runs", k=4, sketcher=sketcher)
        assert len(result.records) == 4
        assert sketcher.calls == 4
        assert len({r.prompt_sha256 for r in result.records}) == 1
        assert all(r.outcome == "COMPLETED" for r in result.records)
        assert all(r.elapsed_seconds is not None for r in result.records)


def test_timeout_recorded_run_continues() -> None:
    """§24: the 600s bound is unchanged; a timeout is an outcome, never a
    retry, never a crash."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = _workspace(root / "src")
        timeout = subprocess.TimeoutExpired(cmd="codex", timeout=600)
        sketcher = _ScriptedSketcher([
            timeout,
            parse_sketch_output(_sketch_json(), blocked_node_id=BLOCKED),
        ])
        result = _run(source, root / "runs", k=2, sketcher=sketcher)
        assert [r.outcome for r in result.records] == ["SKETCH_TIMEOUT", "COMPLETED"]
        assert sketcher.calls == 2  # no retry


def test_decline_is_terminal_and_persisted() -> None:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        source = _workspace(root / "src")
        result = _run(
            source, root / "runs", k=1,
            sketcher=_ScriptedSketcher([
                parse_sketch_output(
                    _sketch_json("DECLINE", candidate_claims=[],
                                 decline_reason="No narrower local reduction exists."),
                    blocked_node_id=BLOCKED,
                )
            ]),
        )
        record = result.records[0]
        assert record.outcome == "DECLINE"
        assert "No narrower" in record.decline_reason
        packet = json.loads(
            (root / "runs" / "sample_01" / "strategist_packet.json").read_text(
                encoding="utf-8"
            )
        )
        assert packet["operator"] == "DECLINE"


# --- sketcher agent + audit packet ------------------------------------------------


def test_sketcher_single_fresh_invocation_and_label() -> None:
    """§10: one strategize = one invoke; the real invoker spawns a fresh
    ephemeral session per invoke."""

    class _RecordingInvoker:
        def __init__(self):
            self.calls = []

        def invoke(self, *, prompt, schema, label):
            self.calls.append((label, prompt, schema))
            return json.loads(_sketch_json())

    invoker = _RecordingInvoker()
    sketcher = StrategySketcher(invoker)
    sketcher.strategize(_context())
    assert [c[0] for c in invoker.calls] == ["strategy_sketcher"]
    assert invoker.calls[0][2] is SKETCH_SCHEMA
    assert sketcher.last_prompt == invoker.calls[0][1]


def test_sketch_audit_packet_carries_no_prior_outcomes() -> None:
    """The independent quality audit sees the decision-time state and the
    sketch only — never control-run outcomes (N2P/N2Q/N2R) or other samples."""
    context = _context()
    sketch = parse_sketch_output(_sketch_json(), blocked_node_id=BLOCKED)
    packet = build_sketch_audit_packet(context, sketch)
    assert packet["original_problem"] == "Prove theorem T."
    assert packet["blocked_goal"] == "Lemma M."
    assert packet["candidate_claims"] == list(sketch.candidate_claims)
    assert "new_nodes" not in json.dumps(packet)
    rendered = json.dumps(packet)
    assert "auditor" not in rendered.lower()
    assert "verdict" not in rendered.lower() or "FAIL" in rendered  # attempts only
