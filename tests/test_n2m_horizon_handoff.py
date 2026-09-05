"""N2M horizon handoff — deterministic contract tests (task card §22-§24).

Seams under test (pre-agreed by the task card):
- classify_solve_error: typed solve-path exception -> LOCAL_HORIZON_EXHAUSTED
  | SYSTEM_ERROR (§22 T1-T5).
- run_long_horizon(solve_error_handoff=...): timeout handoff keeps the
  obligation OPEN, writes no Fact, and makes the frozen escalation eligible
  (§23 H1-H7, §24 long-horizon contract).

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

from research.fact import CandidateFact  # noqa: E402
from research.graph import FactGraph  # noqa: E402
from research.local_refinement import (  # noqa: E402
    parse_alternative_route_output,
    parse_builder_output,
    parse_cut_set_output,
)
from research.obligation import ObligationRegistry, ObligationStatus  # noqa: E402
from research.pipeline import VerificationResult  # noqa: E402
from research.problem import ProblemSpec  # noqa: E402
from research.scaffold import ProofScaffold, ScaffoldNode  # noqa: E402

PROBLEM_STATEMENT = "Target theorem T."
BLOCKED_GOAL = "Intermediate lemma M."


# --- §22: classification ---------------------------------------------------------

from classification import (  # noqa: E402
    LOCAL_HORIZON_EXHAUSTED,
    SYSTEM_ERROR,
    classify_solve_error,
)


def test_worker_timeout_is_local_horizon_exhausted() -> None:
    """T1: the frozen 600s invocation timeout is a typed TimeoutExpired."""
    error = subprocess.TimeoutExpired(cmd=["docker", "run"], timeout=600)
    assert classify_solve_error(error) == LOCAL_HORIZON_EXHAUSTED


def test_docker_daemon_unavailable_is_system_error() -> None:
    """T2: container/CLI launch failure is infrastructure, not horizon."""
    assert classify_solve_error(FileNotFoundError("docker")) == SYSTEM_ERROR
    assert classify_solve_error(RuntimeError("daemon not running")) == SYSTEM_ERROR


def test_model_api_failure_is_system_error() -> None:
    """T3: non-zero exit from the model call surfaces as RuntimeError."""
    assert classify_solve_error(RuntimeError("Codex invocation failed")) == SYSTEM_ERROR


def test_schema_parse_failure_is_system_error() -> None:
    """T4: invalid structured output is a JSONDecodeError, not a horizon."""
    error = json.JSONDecodeError("expecting value", doc="x", pos=0)
    assert classify_solve_error(error) == SYSTEM_ERROR


def test_unexpected_exception_is_system_error() -> None:
    assert classify_solve_error(ValueError("boom")) == SYSTEM_ERROR
    assert classify_solve_error(OSError("disk")) == SYSTEM_ERROR


# --- fakes ------------------------------------------------------------------------

from driver import run_long_horizon  # noqa: E402
from handoff import (  # noqa: E402
    frontier_from_latest_error_attempt,
    make_solve_error_handoff,
)


class ScriptedWorker:
    """Goal-keyed script: each goal maps to a queue of behaviors.

    "timeout" -> raise the typed 600s TimeoutExpired; otherwise echo the
    goal as the candidate (the verifier decides PASS/FAIL).
    """

    def __init__(self, script: dict) -> None:
        self.script = {goal: list(behaviors) for goal, behaviors in script.items()}
        self.calls = 0

    def propose(self, *, problem, existing_facts, subgoal, repair_context=None):
        self.calls += 1
        goal = subgoal.split("Goal:\n", 1)[1]
        behaviors = self.script.get(goal) or []
        if behaviors and behaviors[0] == "timeout":
            behaviors.pop(0)
            raise subprocess.TimeoutExpired(cmd=["docker", "run"], timeout=600)
        return CandidateFact(
            goal,
            f"A candidate proof of {goal}",
            tuple(fact.fact_id for fact in existing_facts),
        )


class RejectingVerifier:
    def __init__(self, rejected=()) -> None:
        self.rejected = set(rejected)

    def verify(self, problem, candidate, predecessors):
        return VerificationResult(
            candidate.statement not in self.rejected, "scripted verdict"
        )


class RaisingWorker:
    def propose(self, *, problem, existing_facts, subgoal, repair_context=None):
        raise RuntimeError("scripted infrastructure crash")


class StubBuilder:
    def __init__(self, result) -> None:
        self.result = result
        self.contexts = []

    def propose(self, context, *, effort=None, timeout=None):
        self.contexts.append(context)
        return self.result


class StubAuditor:
    def __init__(self) -> None:
        self.calls = []

    def audit(self, context, proposal, *, effort=None, timeout=None):
        from research.local_refinement import AuditorResult

        self.calls.append((context, proposal))
        return AuditorResult(verdict="PASS", reasons=("looks sound",))


DECLINE_OUTCOME = {
    "split": "NO_USEFUL_SPLIT",
    "insert_cut_set": "NO_USEFUL_CUT",
    "add_alternative_route": "NO_USEFUL_ROUTE",
}


class Factory:
    def __init__(self, builder_results=()) -> None:
        self.builder_results = list(builder_results)
        self.auditor = StubAuditor()
        self.requested = []

    def builder_for(self, operation: str):
        from research.local_refinement import BuilderResult

        self.requested.append(operation)
        result = (
            self.builder_results.pop(0)
            if self.builder_results
            else BuilderResult(outcome=DECLINE_OUTCOME[operation])
        )
        return StubBuilder(result)

    def auditor_for(self, operation: str):
        return self.auditor


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _scaffold(root: Path, nodes) -> None:
    ProofScaffold.create(
        root / "scaffold.json",
        problem=ProblemSpec("p", PROBLEM_STATEMENT),
        target_node_id="target",
        nodes=nodes,
    )


def make_timeout_workspace(root: Path) -> None:
    """mid -> target; no pre-run: the timeout itself is the evidence."""
    _scaffold(
        root,
        (
            ScaffoldNode("mid", BLOCKED_GOAL),
            ScaffoldNode("target", PROBLEM_STATEMENT, depends_on=("mid",)),
        ),
    )


def _run(root, factory, worker, verifier, **kwargs):
    return run_long_horizon(
        root,
        problem=ProblemSpec("p", PROBLEM_STATEMENT),
        worker=worker,
        verifier=verifier,
        builder_for=factory.builder_for,
        auditor_for=factory.auditor_for,
        solve_error_handoff=make_solve_error_handoff("p"),
        **kwargs,
    )


def _attempts(root: Path):
    attempts_dir = root / "attempts"
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(attempts_dir.glob("attempt-*.json"))
    ]


def _journal(root: Path):
    path = root / "long_horizon_journal.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def _cut_result(blocked_node_id: str, children):
    raw = json.dumps(
        {
            "outcome": "INSERT_CUT_SET",
            "obstruction": "The direct route stalls.",
            "expected_effect": "The cuts split the gap.",
            "new_nodes": list(children),
            "missing_context": "",
        }
    )
    return parse_cut_set_output(raw, blocked_node_id=blocked_node_id)


def _alt_result(blocked_node_id: str, children):
    raw = json.dumps(
        {
            "outcome": "ADD_ALTERNATIVE_ROUTE",
            "obstruction": "The direct route stalls.",
            "why_current_route_is_exhausted": "R1 has no further honest step.",
            "expected_effect": "R2 reaches the goal by a different mechanism.",
            "new_nodes": list(children),
            "missing_context": "",
        }
    )
    return parse_alternative_route_output(raw, blocked_node_id=blocked_node_id)


# --- §23: handoff -----------------------------------------------------------------


def test_timeout_hands_off_to_full_escalation() -> None:
    """H1/H2/H3/H4/H5: timeout -> obligation OPEN, no Fact, then the fixed
    SPLIT -> CUT -> ALT escalation fires on the handed-off frontier."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_timeout_workspace(root)
        factory = Factory()  # all builders decline
        result = _run(
            root,
            factory,
            worker=ScriptedWorker({BLOCKED_GOAL: ["timeout"]}),
            verifier=RejectingVerifier(),
        )
        assert result.horizon_handoffs == 1
        assert result.stop_reason == "OPERATORS_EXHAUSTED"
        assert factory.requested == ["split", "insert_cut_set", "add_alternative_route"]

        # H1: the obligation stays OPEN (never REJECTED/DISCHARGED).
        registry = ObligationRegistry(root / "obligations.json")
        obligation = registry.get("scaffold:p:mid")
        assert obligation.status is ObligationStatus.OPEN

        # H2: no Fact was written; the timeout attempt has no candidate
        # and no verifier artifact (§11/§13).
        assert FactGraph(root).list_facts() == []
        (attempt,) = _attempts(root)
        assert attempt["verdict"] == "ERROR"
        assert attempt["candidate_artifact"] is None
        assert attempt["verifier_artifact"] is None
        assert "timed out after 600 seconds" in attempt["error"]

        # The handoff itself is journaled as execution evidence.
        handoffs = [e for e in _journal(root) if e.get("event") == "horizon_handoff"]
        assert len(handoffs) == 1
        assert handoffs[0]["blocked_node_id"] == "mid"
        assert handoffs[0]["error_type"] == "TimeoutExpired"
        assert handoffs[0]["timeout_seconds"] == 600


def test_timeout_handoff_then_applied_cut_makes_progress() -> None:
    """§25 Control A machinery: first node times out, graph operator takes
    over, children solve, the blocked goal resolves, target SOLVED."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_timeout_workspace(root)
        from research.local_refinement import BuilderResult

        factory = Factory(
            builder_results=[
                BuilderResult(outcome="NO_USEFUL_SPLIT"),
                _cut_result(
                    "mid",
                    (
                        {"node_id": "h1", "goal": "Helper one.", "depends_on": [],
                         "premise_fact_ids": []},
                        {"node_id": "h2", "goal": "Helper two.", "depends_on": ["h1"],
                         "premise_fact_ids": []},
                    ),
                ),
            ]
        )
        result = _run(
            root,
            factory,
            worker=ScriptedWorker({BLOCKED_GOAL: ["timeout"]}),  # times out once
            verifier=RejectingVerifier(),  # accepts everything
        )
        assert result.stop_reason == "TARGET_SOLVED"
        assert result.horizon_handoffs == 1
        assert result.mutation_episodes == 1
        assert factory.requested == ["split", "insert_cut_set"]
        statements = {fact.statement for fact in FactGraph(root).list_facts()}
        assert {"Helper one.", "Helper two.", BLOCKED_GOAL, PROBLEM_STATEMENT} <= statements


def test_system_error_never_hands_off() -> None:
    """H6: infrastructure failure stops the run; no graph operator fires."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_timeout_workspace(root)
        factory = Factory()
        result = _run(root, factory, worker=RaisingWorker(), verifier=RejectingVerifier())
        assert result.stop_reason == "SYSTEM_ERROR"
        assert result.horizon_handoffs == 0
        assert factory.requested == []
        assert factory.auditor.calls == []


def test_pass_never_hands_off() -> None:
    """H7: an ordinary PASS needs no escalation at all."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_timeout_workspace(root)
        factory = Factory()
        result = _run(
            root, factory, worker=ScriptedWorker({}), verifier=RejectingVerifier()
        )
        assert result.stop_reason == "TARGET_SOLVED"
        assert result.horizon_handoffs == 0
        assert factory.requested == []


def test_verifier_fail_is_mathematical_path_not_handoff() -> None:
    """T5: ordinary verifier FAIL -> BLOCKED -> escalation, zero handoffs."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_timeout_workspace(root)
        factory = Factory()
        result = _run(
            root,
            factory,
            worker=ScriptedWorker({}),
            verifier=RejectingVerifier({BLOCKED_GOAL}),
        )
        assert result.solve_status == "BLOCKED"
        assert result.horizon_handoffs == 0
        assert result.stop_reason == "OPERATORS_EXHAUSTED"
        assert factory.requested == ["split", "insert_cut_set", "add_alternative_route"]
        assert all(a["verdict"] == "FAIL" for a in _attempts(root))


# --- §24: long-horizon contract -----------------------------------------------------


def test_multi_node_mixed_horizon_and_blocked_sequence() -> None:
    """§24: A timeout->split, B PASS, C timeout->cut, D PASS,
    E BLOCKED->alt. The driver must continue through the whole sequence
    with correct budgets and preserved Facts."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        _scaffold(
            root,
            (
                ScaffoldNode("a", "Goal A."),
                ScaffoldNode("b", "Goal B."),
                ScaffoldNode("c", "Goal C."),
                ScaffoldNode("d", "Goal D."),
                ScaffoldNode("e", "Goal E."),
                ScaffoldNode(
                    "target",
                    PROBLEM_STATEMENT,
                    depends_on=("a", "b", "c", "d", "e"),
                ),
            ),
        )
        from research.local_refinement import BuilderResult

        factory = Factory(
            builder_results=[
                # A: timeout handed off; SPLIT applies.
                parse_builder_output(
                    json.dumps(
                        {
                            "outcome": "SPLIT",
                            "obstruction": "A stalls jointly.",
                            "expected_effect": "Halves are provable.",
                            "new_nodes": [
                                {"node_id": "a1", "goal": "Part one of A.",
                                 "depends_on": [], "premise_fact_ids": []},
                                {"node_id": "a2", "goal": "Part two of A.",
                                 "depends_on": ["a1"], "premise_fact_ids": []},
                            ],
                            "missing_context": "",
                        }
                    ),
                    blocked_node_id="a",
                ),
                # C: timeout handed off; SPLIT declines, CUT applies.
                BuilderResult(outcome="NO_USEFUL_SPLIT"),
                _cut_result(
                    "c",
                    (
                        {"node_id": "c1", "goal": "Cut lemma one for C.",
                         "depends_on": [], "premise_fact_ids": []},
                        {"node_id": "c2", "goal": "Cut lemma two for C.",
                         "depends_on": ["c1"], "premise_fact_ids": []},
                    ),
                ),
                # E: verifier BLOCKED; SPLIT and CUT decline, ALT applies.
                BuilderResult(outcome="NO_USEFUL_SPLIT"),
                BuilderResult(outcome="NO_USEFUL_CUT"),
                _alt_result(
                    "e",
                    (
                        {"node_id": "e1", "goal": "Alternative lemma one for E.",
                         "depends_on": [], "premise_fact_ids": []},
                        {"node_id": "e2", "goal": "Alternative lemma two for E.",
                         "depends_on": ["e1"], "premise_fact_ids": []},
                    ),
                ),
            ]
        )
        worker = ScriptedWorker(
            {
                "Goal A.": ["timeout"],
                "Goal C.": ["timeout"],
            }
        )
        result = _run(root, factory, worker=worker, verifier=RejectingVerifier({"Goal E."}))

        # Driver survived both timeouts and ran all three operators.
        assert result.horizon_handoffs == 2
        assert result.mutation_episodes == 3
        assert factory.requested == [
            "split",  # on a
            "split",  # on c
            "insert_cut_set",  # on c
            "split",  # on e
            "insert_cut_set",  # on e
            "add_alternative_route",  # on e
            # N2C semantics: alt parks e and re-routes the verbatim goal
            # onto the NEW node e__alt — a new obligation identity, so the
            # escalation restarts there (and declines out).
            "split",  # on e__alt
            "insert_cut_set",  # on e__alt
            "add_alternative_route",  # on e__alt
        ]
        # E never resolves (verifier rejects it under every route), so the
        # run ends with the re-routed frontier's operators exhausted rather
        # than TARGET_SOLVED.
        assert result.stop_reason == "OPERATORS_EXHAUSTED"
        assert [
            entry["blocked_node_id"]
            for entry in _journal(root)
            if entry.get("operation")
        ][-3:] == ["e__alt", "e__alt", "e__alt"]
        # All verified mathematics is preserved. Note: split SUPERSEDES a
        # (N2A semantics — a's own goal is never admitted; the target
        # consumes the children), while cut keeps c's goal alive through
        # the new route (N2B semantics).
        statements = {fact.statement for fact in FactGraph(root).list_facts()}
        assert {
            "Part one of A.", "Part two of A.",
            "Goal B.", "Goal D.",
            "Cut lemma one for C.", "Cut lemma two for C.", "Goal C.",
            "Alternative lemma one for E.", "Alternative lemma two for E.",
        } <= statements
        assert "Goal A." not in statements
        assert "Goal E." not in statements
        # Timeout attempts carry no candidate; FAIL attempts are ordinary.
        timeout_attempts = [
            a for a in _attempts(root) if a["verdict"] == "ERROR"
        ]
        assert len(timeout_attempts) == 2
        assert all(a["candidate_artifact"] is None for a in timeout_attempts)
