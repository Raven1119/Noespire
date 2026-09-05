"""N2N failure provenance handoff — deterministic contract tests (§29).

Seams under test (pre-agreed by the task card):
- provenance.py: partial codex JSONL stream -> bounded FailureProvenance
  packet (capture, extraction, bounds, grounding, status).
- provenance_handoff.py: make_provenance_handoff — LOCAL_HORIZON_EXHAUSTED capture
  bound to obligation x attempt; everything else untouched (SYSTEM_ERROR).
- inject.py: ProvenanceInjectingInvoker — builder prompts for the
  handed-off obligation receive the bounded UNVERIFIED provenance section;
  all other labels/obligations pass through byte-identical.
- driver escalation with provenance wired is the frozen N2M behavior (§18).

All tests are model-free: fake workers/verifiers/builders/auditors only.
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
sys.path.insert(0, str(REPO_ROOT / "experiments" / "n2n_failure_provenance"))

from research.graph import FactGraph  # noqa: E402
from research.obligation import ObligationRegistry  # noqa: E402
from research.problem import ProblemSpec  # noqa: E402
from research.scaffold import ProofScaffold, ScaffoldNode  # noqa: E402

from provenance import (  # noqa: E402
    MAX_TOTAL_CHARS,
    NON_SUBSTANTIVE,
    SUBSTANTIVE,
    UNAVAILABLE,
    build_provenance_packet,
    parse_partial_events,
)

CLAIM = "It would suffice to prove H: every prefix of the sequence has bounded partial sums."
OBSTRUCTION = "The argument stalls because the compactness step needs the full theorem."
NOISE = "I will think carefully about this problem."


def _jsonl(items) -> str:
    """A partial codex --json stream carrying the given completed items."""
    lines = [
        json.dumps({"type": "thread.started", "thread_id": "t"}),
        json.dumps({"type": "turn.started"}),
    ]
    for item_type, text in items:
        lines.append(
            json.dumps(
                {"type": "item.completed", "item": {"type": item_type, "text": text}}
            )
        )
    return "\n".join(lines) + "\n"


def _packet(raw: str, **overrides):
    fields = dict(
        raw_stdout=raw,
        obligation_id="scaffold:p:mid",
        attempt_id="attempt-000001",
        node_id="mid",
        timeout_seconds=600,
    )
    fields.update(overrides)
    return build_provenance_packet(**fields)


# --- §29.4/5/6/7 + §27 grounding: extraction -------------------------------------


def test_visible_intermediate_claim_extracted() -> None:
    """§29.4: an explicit 'it suffices to prove H' survives the timeout."""
    packet = _packet(_jsonl([("reasoning", CLAIM)]))
    assert packet.status == SUBSTANTIVE
    assert any(CLAIM in item for item in packet.visible_items)


def test_visible_obstruction_extracted() -> None:
    """§29.5: an explicit obstruction statement survives the timeout."""
    packet = _packet(_jsonl([("reasoning", OBSTRUCTION)]))
    assert packet.status == SUBSTANTIVE
    assert any(OBSTRUCTION in item for item in packet.visible_items)


def test_noise_only_is_non_substantive() -> None:
    """§29.6: filler text carries no mathematical frontier."""
    packet = _packet(_jsonl([("reasoning", NOISE)]))
    assert packet.status == NON_SUBSTANTIVE


def test_empty_stream_is_unavailable() -> None:
    """§29.6/§11: no visible items -> NO_PROVENANCE_AVAILABLE territory."""
    assert _packet("").status == UNAVAILABLE
    assert _packet(_jsonl([])).status == UNAVAILABLE  # thread/turn events only


def test_provenance_bound_enforced() -> None:
    """§29.7/§12: hard total cap; the latest items (the frontier) win."""
    items = [("reasoning", f"approach {i}: " + "x" * 800) for i in range(20)]
    packet = _packet(_jsonl(items))
    assert packet.byte_size <= MAX_TOTAL_CHARS
    assert packet.visible_items  # not emptied by the cap
    assert "approach 19" in packet.visible_items[-1]
    assert not any("approach 0" in item for item in packet.visible_items)


def test_items_are_grounded_in_raw_artifact() -> None:
    """§27: every extracted item is a verbatim substring of the raw stream
    (mechanical extraction cannot hallucinate a claim)."""
    raw = _jsonl([("reasoning", CLAIM), ("agent_message", OBSTRUCTION)])
    packet = _packet(raw)
    for item in packet.visible_items:
        assert item in raw


def test_truncated_tail_line_tolerated() -> None:
    """A stream cut mid-line still yields its complete items."""
    raw = _jsonl([("reasoning", CLAIM)])
    raw += '{"type": "item.completed", "item": {"type": "reasoning", "te'
    packet = _packet(raw)
    assert packet.status == SUBSTANTIVE
    assert any(CLAIM in item for item in packet.visible_items)


def test_command_execution_contributes_command_text() -> None:
    """Observable tool use (toy-example computations) is explicit output."""
    raw = "\n".join(
        [
            json.dumps({"type": "thread.started", "thread_id": "t"}),
            json.dumps(
                {
                    "type": "item.completed",
                    "item": {
                        "type": "command_execution",
                        "command": CLAIM,  # stand-in text, grounding-safe
                        "aggregated_output": "ok",
                        "exit_code": 0,
                    },
                }
            ),
        ]
    )
    packet = _packet(raw)
    assert any(CLAIM in item for item in packet.visible_items)


# --- §29.1/2/3/8/9: handoff capture and binding ------------------------------------

from provenance_handoff import make_provenance_handoff  # noqa: E402

PROBLEM_ID = "n2n-test-problem"
STATEMENT = "Lemma M implies theorem T."


def _workspace(root: Path, verdict: str = "ERROR") -> Path:
    """Degenerate 2-node scaffold plus one recorded attempt on ``mid``."""
    problem_dir = root / "workspace" / PROBLEM_ID
    problem_dir.mkdir(parents=True)
    ProofScaffold.create(
        problem_dir / "scaffold.json",
        problem=ProblemSpec(PROBLEM_ID, STATEMENT),
        target_node_id="target",
        nodes=(
            ScaffoldNode("mid", STATEMENT),
            ScaffoldNode("target", STATEMENT, depends_on=("mid",)),
        ),
    )
    ObligationRegistry(problem_dir / "obligations.json")
    (problem_dir / "attempts").mkdir()
    (problem_dir / "attempts" / "attempt-000003.json").write_text(
        json.dumps(
            {
                "attempt_id": "attempt-000003",
                "problem_id": PROBLEM_ID,
                "obligation_id": f"scaffold:{PROBLEM_ID}:mid",
                "candidate_artifact": None,
                "verifier_artifact": None,
                "verdict": verdict,
                "error": "TimeoutExpired: ..." if verdict == "ERROR" else None,
            }
        ),
        encoding="utf-8",
    )
    return problem_dir


def _timeout(stream: str) -> subprocess.TimeoutExpired:
    return subprocess.TimeoutExpired(
        cmd=["docker", "run"], timeout=600, output=stream
    )


def test_timeout_partial_artifact_captured() -> None:
    """§29.1: the partial stream riding on TimeoutExpired becomes a bounded
    packet at handoff time."""
    with TemporaryDirectory() as tmp:
        problem_dir = _workspace(Path(tmp))
        handoff = make_provenance_handoff(PROBLEM_ID)
        frontier = handoff(_timeout(_jsonl([("reasoning", CLAIM)])), problem_dir)
        assert frontier == "mid"
        packets = list((problem_dir / "provenance").glob("*.json"))
        assert len(packets) == 1
        payload = json.loads(packets[0].read_text(encoding="utf-8"))
        assert payload["status"] == SUBSTANTIVE
        assert any(CLAIM in item for item in payload["visible_items"])
        assert payload["raw_artifact"]


def test_non_error_latest_attempt_no_capture() -> None:
    """§29.2: a mathematical FAIL verdict is not a horizon; nothing captured."""
    with TemporaryDirectory() as tmp:
        problem_dir = _workspace(Path(tmp), verdict="FAIL")
        handoff = make_provenance_handoff(PROBLEM_ID)
        assert handoff(_timeout(_jsonl([("reasoning", CLAIM)])), problem_dir) is None
        assert not (problem_dir / "provenance").exists()


def test_system_error_no_capture() -> None:
    """§29.3: infrastructure errors never masquerade as provenance."""
    with TemporaryDirectory() as tmp:
        problem_dir = _workspace(Path(tmp))
        handoff = make_provenance_handoff(PROBLEM_ID)
        assert handoff(RuntimeError("docker daemon unavailable"), problem_dir) is None
        assert not (problem_dir / "provenance").exists()


def test_provenance_tied_to_obligation_and_attempt() -> None:
    """§29.8: the packet is bound to exactly one obligation x attempt."""
    with TemporaryDirectory() as tmp:
        problem_dir = _workspace(Path(tmp))
        handoff = make_provenance_handoff(PROBLEM_ID)
        handoff(_timeout(_jsonl([("reasoning", CLAIM)])), problem_dir)
        (payload,) = [
            json.loads(p.read_text(encoding="utf-8"))
            for p in (problem_dir / "provenance").glob("*.json")
        ]
        assert payload["attempt_id"] == "attempt-000003"
        assert payload["obligation_id"] == f"scaffold:{PROBLEM_ID}:mid"
        assert payload["node_id"] == "mid"
        assert payload["termination"] == "LOCAL_HORIZON_EXHAUSTED"
        assert payload["timeout_seconds"] == 600


def test_provenance_never_enters_factgraph() -> None:
    """§29.9/§15: packets live outside every frozen truth structure."""
    with TemporaryDirectory() as tmp:
        problem_dir = _workspace(Path(tmp))
        handoff = make_provenance_handoff(PROBLEM_ID)
        handoff(_timeout(_jsonl([("reasoning", CLAIM)])), problem_dir)
        assert FactGraph(problem_dir).list_facts() == []


# --- §29.10/11/13/14/15: builder-prompt injection locality ---------------------------

from inject import ProvenanceInjectingInvoker  # noqa: E402
from provenance import write_packet  # noqa: E402

BUILDER_PROMPT = (
    "You are the Codex Local Graph Builder for a blocked natural-language proof scaffold.\n"
    "Blocked obligation:\n"
    "goal: Lemma M implies theorem T.\n"
    "premises: []\n"
    "Local graph (nodes, goals, dependencies):\n"
    '- "mid" goal: Lemma M implies theorem T. depends_on: [] [BLOCKED]\n'
    '- "target" goal: Lemma M implies theorem T. depends_on: [\'mid\']\n'
    "\nReturn ONLY the JSON object:\n{...}\n"
)


class RecordingInvoker:
    def __init__(self) -> None:
        self.prompts = []

    def invoke(self, *, prompt, schema, label):
        self.prompts.append((label, prompt))
        return {"outcome": "NO_USEFUL_SPLIT"}


def _injector(root: Path, inner, packet_node="mid", status_items=("reasoning", CLAIM)):
    problem_dir = _workspace(root)
    raw = _jsonl([status_items]) if status_items else ""
    packet = build_provenance_packet(
        raw_stdout=raw,
        obligation_id=f"scaffold:{PROBLEM_ID}:{packet_node}",
        attempt_id="attempt-000003",
        node_id=packet_node,
        timeout_seconds=600,
    )
    write_packet(problem_dir, packet, raw)
    return ProvenanceInjectingInvoker(inner, provenance_dir=problem_dir / "provenance")


def test_builder_receives_relevant_provenance() -> None:
    """§29.10: a SUBSTANTIVE packet for the blocked node is injected, labeled
    UNVERIFIED, before the return-marker."""
    with TemporaryDirectory() as tmp:
        inner = RecordingInvoker()
        invoker = _injector(Path(tmp), inner)
        invoker.invoke(prompt=BUILDER_PROMPT, schema={}, label="local_graph_builder")
        (_, prompt) = inner.prompts[0]
        assert CLAIM in prompt
        assert "UNVERIFIED" in prompt
        assert prompt.index(CLAIM) < prompt.index("Return ONLY the JSON object")


def test_unrelated_branch_provenance_excluded() -> None:
    """§29.11/§14: a packet bound to another node is never injected."""
    with TemporaryDirectory() as tmp:
        inner = RecordingInvoker()
        invoker = _injector(Path(tmp), inner, packet_node="other_node")
        invoker.invoke(prompt=BUILDER_PROMPT, schema={}, label="local_graph_builder")
        assert inner.prompts[0][1] == BUILDER_PROMPT


def test_non_substantive_provenance_not_injected() -> None:
    """§25B: noise-only partial output must not reach the builder."""
    with TemporaryDirectory() as tmp:
        inner = RecordingInvoker()
        invoker = _injector(Path(tmp), inner, status_items=("reasoning", NOISE))
        invoker.invoke(prompt=BUILDER_PROMPT, schema={}, label="local_graph_builder")
        assert inner.prompts[0][1] == BUILDER_PROMPT


def test_non_builder_labels_pass_through_byte_identical() -> None:
    """§29.13/14/15: worker, verifier, and auditor prompts are untouched even
    when a substantive packet exists (frozen NodeSolver / closed-book
    verifier / operators receive zero semantic change)."""
    with TemporaryDirectory() as tmp:
        inner = RecordingInvoker()
        invoker = _injector(Path(tmp), inner)
        for label in ("research_worker", "closed_book_verifier", "structural_auditor"):
            invoker.invoke(prompt=BUILDER_PROMPT, schema={}, label=label)
        for (_, prompt) in inner.prompts:
            assert prompt == BUILDER_PROMPT


def test_missing_blocked_marker_passthrough() -> None:
    """Fail-safe: a prompt without a parseable [BLOCKED] node is unchanged."""
    with TemporaryDirectory() as tmp:
        inner = RecordingInvoker()
        invoker = _injector(Path(tmp), inner)
        invoker.invoke(prompt="no marker here", schema={}, label="local_graph_builder")
        assert inner.prompts[0][1] == "no marker here"


# --- §29.12: fixed escalation unchanged with provenance wired -----------------------

from driver import run_long_horizon  # noqa: E402
from research.fact import CandidateFact  # noqa: E402
from research.local_refinement import BuilderResult, parse_cut_set_output  # noqa: E402
from research.pipeline import VerificationResult  # noqa: E402


class TimeoutOnceWithTraceWorker:
    """Times out once on ``blocked_goal`` carrying a partial JSONL stream."""

    def __init__(self, blocked_goal: str, stream: str) -> None:
        self.blocked_goal = blocked_goal
        self.stream = stream
        self.timed_out = False

    def propose(self, *, problem, existing_facts, subgoal, repair_context=None):
        goal = subgoal.split("Goal:\n", 1)[1]
        if goal == self.blocked_goal and not self.timed_out:
            self.timed_out = True
            raise subprocess.TimeoutExpired(
                cmd=["docker", "run"], timeout=600, output=self.stream
            )
        return CandidateFact(
            goal,
            f"A candidate proof of {goal}",
            tuple(fact.fact_id for fact in existing_facts),
        )


class _AcceptingVerifier:
    def verify(self, problem, candidate, predecessors):
        return VerificationResult(True, "scripted accept")


class _PassingAuditor:
    def audit(self, context, proposal, *, effort=None, timeout=None):
        from research.local_refinement import AuditorResult

        return AuditorResult(verdict="PASS", reasons=("scripted pass",))


def test_fixed_escalation_unchanged_with_provenance() -> None:
    """§29.12/§18: timeout -> capture -> SPLIT declines -> CUT applies ->
    solved; escalation order and N2M behavior are untouched, and the packet
    exists before the first builder call."""
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        ProofScaffold.create(
            root / "scaffold.json",
            problem=ProblemSpec(PROBLEM_ID, STATEMENT),
            target_node_id="target",
            nodes=(
                ScaffoldNode("mid", STATEMENT),
                ScaffoldNode("target", STATEMENT, depends_on=("mid",)),
            ),
        )
        cut = parse_cut_set_output(
            json.dumps(
                {
                    "outcome": "INSERT_CUT_SET",
                    "obstruction": "The direct route stalled at the local horizon.",
                    "expected_effect": "Two helper obligations split the gap.",
                    "new_nodes": [
                        {"node_id": "h1", "goal": "Helper lemma one.",
                         "depends_on": [], "premise_fact_ids": []},
                        {"node_id": "h2", "goal": "Helper lemma two.",
                         "depends_on": ["h1"], "premise_fact_ids": []},
                    ],
                    "missing_context": "",
                }
            ),
            blocked_node_id="mid",
        )
        requested = []

        def builder_for(operation: str):
            requested.append(operation)

            class _Stub:
                def propose(self, context, *, effort=None, timeout=None):
                    if operation == "insert_cut_set":
                        # The provenance packet must already exist when the
                        # first builder runs (capture precedes escalation).
                        assert (root / "provenance").is_dir()
                        return cut
                    return BuilderResult(outcome="NO_USEFUL_SPLIT")

            return _Stub()

        result = run_long_horizon(
            root,
            problem=ProblemSpec(PROBLEM_ID, STATEMENT),
            worker=TimeoutOnceWithTraceWorker(STATEMENT, _jsonl([("reasoning", CLAIM)])),
            verifier=_AcceptingVerifier(),
            builder_for=builder_for,
            auditor_for=lambda operation: _PassingAuditor(),
            author="n2n-test",
            solve_error_handoff=make_provenance_handoff(PROBLEM_ID),
        )
        assert result.stop_reason == "TARGET_SOLVED"
        assert result.horizon_handoffs == 1
        assert requested == ["split", "insert_cut_set"]
        (packet_path,) = (root / "provenance").glob("attempt-*.json")
        payload = json.loads(packet_path.read_text(encoding="utf-8"))
        assert payload["status"] == SUBSTANTIVE
        assert payload["node_id"] == "mid"
