"""N2L — closed-book long-horizon evaluation: deterministic contract tests.

No Codex, no Docker, no network: invokers/builders/auditors/workers/verifiers
are stubs. Covers the §32 contract:

- closed-book surface: retrieval options, network-attempt detection;
- ClosedBookVerifier: gate logic (valid AND no external authority), schema,
  prompt overlay, reason classification;
- long-horizon driver: fixed SPLIT -> CUT -> ALT escalation, per-(node,
  operator) exactly-once, budgets, stop conditions, context locality;
- metrics: counts, closed-book rejection accounting, verified reasoning depth;
- fact audit: deterministic INVALID gate over model checks;
- fixtures: erdos67 prep starts clean (no N2C facts, no copied history).
"""

from pathlib import Path
from tempfile import TemporaryDirectory

import json
import sys

import pytest

from research.fact import CandidateFact, Fact
from research.graph import FactGraph
from research.local_refinement import (
    AuditorResult,
    BuilderResult,
    parse_builder_output,
)
from research.obligation import ObligationRegistry
from research.pipeline import VerificationResult
from research.problem import ProblemSpec
from research.scaffold import ProofScaffold, ScaffoldNode, solve_scaffold

REPO_ROOT = Path(__file__).resolve().parents[1]
N2L_DIR = REPO_ROOT / "experiments" / "n2l_closed_book_long_horizon"
sys.path.insert(0, str(N2L_DIR))

PROBLEM_STATEMENT = "Target theorem T."
BLOCKED_GOAL = "Intermediate lemma M."
SIDE_GOAL = "Unrelated sibling lemma S."
SIDE_PROOF = "Unrelated sibling proof text."


class GoalEchoWorker:
    """Echoes the subgoal's ``Goal:\\n<text>`` tail back as the candidate."""

    def __init__(self) -> None:
        self.calls = 0

    def propose(self, *, problem, existing_facts, subgoal, repair_context=None):
        self.calls += 1
        goal = subgoal.split("Goal:\n", 1)[1]
        return CandidateFact(
            goal,
            f"A candidate proof of {goal}",
            tuple(fact.fact_id for fact in existing_facts),
        )


class RaisingWorker:
    def propose(self, *, problem, existing_facts, subgoal, repair_context=None):
        raise RuntimeError("scripted worker crash")


class RejectingVerifier:
    def __init__(self, rejected=()) -> None:
        self.rejected = set(rejected)
        self.calls = 0

    def verify(self, problem, candidate, predecessors):
        self.calls += 1
        return VerificationResult(
            candidate.statement not in self.rejected, "scripted verdict"
        )


class StubBuilder:
    def __init__(self, result: BuilderResult) -> None:
        self.result = result
        self.contexts = []

    def propose(self, context, *, effort=None, timeout=None):
        self.contexts.append(context)
        return self.result


class StubAuditor:
    def __init__(self, result: AuditorResult) -> None:
        self.result = result
        self.calls = []

    def audit(self, context, proposal, *, effort=None, timeout=None):
        self.calls.append((context, proposal))
        return self.result


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


SPLIT_CHILDREN = (
    {"node_id": "mid-a", "goal": "Part one of M.", "depends_on": [], "premise_fact_ids": []},
    {
        "node_id": "mid-b",
        "goal": "Part two of M.",
        "depends_on": ["mid-a"],
        "premise_fact_ids": [],
    },
)


def split_apply_result(blocked_node_id="mid") -> BuilderResult:
    raw = json.dumps(
        {
            "outcome": "SPLIT",
            "obstruction": "Both halves failed jointly.",
            "expected_effect": "Each half is provable alone.",
            "new_nodes": list(SPLIT_CHILDREN),
            "missing_context": "",
        }
    )
    return parse_builder_output(raw, blocked_node_id=blocked_node_id)


DECLINE_OUTCOME = {
    "split": "NO_USEFUL_SPLIT",
    "insert_cut_set": "NO_USEFUL_CUT",
    "add_alternative_route": "NO_USEFUL_ROUTE",
}


class Factory:
    """builder_for/auditor_for test double: records requested operations and
    serves queued builder results (declines by default), PASS auditors."""

    def __init__(self, builder_results=(), auditor=None) -> None:
        self.builder_results = list(builder_results)
        self.auditor = auditor or StubAuditor(
            AuditorResult(verdict="PASS", reasons=("looks sound",))
        )
        self.requested = []
        self.builders = []

    def builder_for(self, operation: str):
        self.requested.append(operation)
        result = (
            self.builder_results.pop(0)
            if self.builder_results
            else BuilderResult(outcome=DECLINE_OUTCOME[operation])
        )
        builder = StubBuilder(result)
        self.builders.append(builder)
        return builder

    def auditor_for(self, operation: str):
        return self.auditor


def make_workspace(root: Path) -> ProofScaffold:
    """mid -> target; mid runs once and is rejected (FAIL evidence)."""
    problem = ProblemSpec("p", PROBLEM_STATEMENT)
    scaffold = ProofScaffold.create(
        root / "scaffold.json",
        problem=problem,
        target_node_id="target",
        nodes=(
            ScaffoldNode("mid", BLOCKED_GOAL),
            ScaffoldNode("target", PROBLEM_STATEMENT, depends_on=("mid",)),
        ),
    )
    result = solve_scaffold(
        scaffold=scaffold,
        problem=problem,
        registry=ObligationRegistry(root / "obligations.json"),
        graph=FactGraph(root),
        author="worker",
        worker=GoalEchoWorker(),
        verifier=RejectingVerifier({BLOCKED_GOAL}),
    )
    assert result.status == "BLOCKED"
    return ProofScaffold(root / "scaffold.json")


def make_workspace_with_sibling(root: Path) -> ProofScaffold:
    """Adds a resolved sibling branch unrelated to the blocked region."""
    problem = ProblemSpec("p", PROBLEM_STATEMENT)
    scaffold = ProofScaffold.create(
        root / "scaffold.json",
        problem=problem,
        target_node_id="target",
        nodes=(
            ScaffoldNode("mid", BLOCKED_GOAL),
            ScaffoldNode("side", SIDE_GOAL),
            ScaffoldNode("target", PROBLEM_STATEMENT, depends_on=("mid", "side")),
        ),
    )
    graph = FactGraph(root)
    side_fact = graph.add_fact(
        Fact.create(problem_id="p", author="worker", statement=SIDE_GOAL, proof=SIDE_PROOF)
    )
    scaffold.resolve("side", side_fact.fact_id, graph)
    result = solve_scaffold(
        scaffold=scaffold,
        problem=problem,
        registry=ObligationRegistry(root / "obligations.json"),
        graph=graph,
        author="worker",
        worker=GoalEchoWorker(),
        verifier=RejectingVerifier({BLOCKED_GOAL}),
    )
    assert result.status == "BLOCKED"
    return ProofScaffold(root / "scaffold.json")


# --- closed-book surface (§32.1) ----------------------------------------------

from closed_book import (  # noqa: E402
    ClosedBookCodexInvoker,
    ClosedBookVerifier,
    closed_book_options,
    detect_network_attempts,
)


def test_closed_book_options_disable_retrieval_but_keep_model_config() -> None:
    options = closed_book_options()
    joined = " ".join(options)
    assert 'web_search="disabled"' in joined
    assert "tools.web_search=false" in joined
    assert "features.network_proxy=true" in joined
    assert "network.domains" in joined
    # Model/effort come from the mounted user config.toml: ignoring it would
    # silently change the frozen experiment condition.
    assert "--ignore-user-config" not in options
    # Already in the base isolated argv.
    assert "--skip-git-repo-check" not in options


def test_closed_book_invoker_argv_appends_options_to_isolated_base() -> None:
    invoker = ClosedBookCodexInvoker.__new__(ClosedBookCodexInvoker)
    invoker.image = "img"
    invoker.docker_executable = "docker"
    invoker.auth_dir = Path("/auth")
    invoker.timeout_seconds = 600
    invoker.audit_dir = None
    argv = invoker._run_argv("name", Path("/work"))
    joined = " ".join(argv)
    # codex's own sandbox + permission profile replace danger-full-access so
    # the network/tool policy is actually enforced (probe evidence: N2L probe).
    assert "--sandbox read-only" in joined
    assert "danger-full-access" not in joined
    assert "--security-opt seccomp=unconfined" in joined
    assert 'web_search="disabled"' in joined
    assert argv[:2] == ["docker", "run"]


def test_detect_network_attempts_flags_curl_and_web_search() -> None:
    events = [
        {"type": "item.completed", "item": {"type": "command_execution",
                                            "command": "curl -sS https://arxiv.org/abs/1509.05363"}},
        {"type": "item.completed", "item": {"type": "agent_message", "text": "{}"}},
    ]
    attempts = detect_network_attempts(events)
    assert attempts and "arxiv.org" in attempts[0]
    assert detect_network_attempts([events[1]]) == []
    assert detect_network_attempts([]) == []


# --- ClosedBookVerifier gate (§32.2–§32.5) -------------------------------------


class RecordingCodex:
    def __init__(self, response: dict) -> None:
        self.response = response
        self.calls = []

    def invoke(self, *, prompt, schema, label):
        self.calls.append((prompt, schema, label))
        return self.response


def _candidate() -> CandidateFact:
    return CandidateFact("Lemma L.", "Proof text of L.", ())


def _verify_response(accepted, dependency, violation="NONE", reason="r") -> dict:
    return {
        "accepted": accepted,
        "external_authority_dependency": dependency,
        "violation_type": violation,
        "reason": reason,
    }


def test_closed_book_verifier_accepts_self_contained_proof() -> None:
    codex = RecordingCodex(_verify_response(True, False, reason="valid"))
    result = ClosedBookVerifier(codex).verify("P", _candidate(), [])
    assert result.accepted is True
    assert result.reason == "valid"


def test_closed_book_verifier_accepts_predecessor_grounded_proof() -> None:
    codex = RecordingCodex(_verify_response(True, False))
    predecessor = Fact.create(
        problem_id="p", author="w", statement="Base lemma.", proof="Base proof."
    )
    candidate = CandidateFact("Lemma L.", "Proof using the base lemma.", (predecessor.fact_id,))
    result = ClosedBookVerifier(codex).verify("P", candidate, [predecessor])
    assert result.accepted is True
    prompt, _, _ = codex.calls[0]
    assert predecessor.fact_id in prompt and "Base lemma." in prompt


def test_closed_book_verifier_rejects_external_theorem_authority() -> None:
    codex = RecordingCodex(
        _verify_response(True, True, "EXTERNAL_THEOREM_AUTHORITY", "cites Hodge theory")
    )
    result = ClosedBookVerifier(codex).verify("P", _candidate(), [])
    assert result.accepted is False
    assert result.reason.startswith("[CLOSED_BOOK:EXTERNAL_THEOREM_AUTHORITY]")
    assert "cites Hodge theory" in result.reason


def test_closed_book_verifier_rejects_target_circularity() -> None:
    codex = RecordingCodex(
        _verify_response(True, True, "TARGET_CIRCULARITY", "invokes the target theorem")
    )
    result = ClosedBookVerifier(codex).verify("P", _candidate(), [])
    assert result.accepted is False
    assert result.reason.startswith("[CLOSED_BOOK:TARGET_CIRCULARITY]")


def test_closed_book_verifier_dependency_with_none_violation_fails_closed() -> None:
    """accepted+dependency+NONE is a model inconsistency: reject anyway."""
    codex = RecordingCodex(_verify_response(True, True, "NONE", "muddled"))
    result = ClosedBookVerifier(codex).verify("P", _candidate(), [])
    assert result.accepted is False
    assert result.reason.startswith("[CLOSED_BOOK:UNDECLARED_EXTERNAL_RESULT]")


def test_closed_book_verifier_violation_without_dependency_fails_closed() -> None:
    """Gate asymmetry (review finding): a flagged violation_type with the
    dependency boolean left false must still forbid admission."""
    codex = RecordingCodex(
        _verify_response(True, False, "TARGET_CIRCULARITY", "invokes the target")
    )
    result = ClosedBookVerifier(codex).verify("P", _candidate(), [])
    assert result.accepted is False
    assert result.reason.startswith("[CLOSED_BOOK:TARGET_CIRCULARITY]")


def test_closed_book_verifier_mathematical_fail_is_not_prefixed() -> None:
    codex = RecordingCodex(_verify_response(False, False, reason="gap in step 2"))
    result = ClosedBookVerifier(codex).verify("P", _candidate(), [])
    assert result.accepted is False
    assert result.reason == "gap in step 2"
    assert not result.reason.startswith("[CLOSED_BOOK:")


def test_closed_book_verifier_prompt_is_base_prompt_plus_policy() -> None:
    codex = RecordingCodex(_verify_response(True, False))
    verifier = ClosedBookVerifier(codex)
    verifier.verify("The problem.", _candidate(), [])
    prompt, schema, label = codex.calls[0]
    assert label == "closed_book_verifier"
    # Base verifier semantics carried verbatim.
    assert "Judge whether the supplied proof establishes exactly the candidate" in prompt
    assert "Accepted predecessor facts:" in prompt
    # Closed-book overlay.
    assert "closed-book" in prompt
    assert "EXTERNAL_THEOREM_AUTHORITY" in prompt
    assert "TARGET_CIRCULARITY" in prompt
    # Strict schema; the deterministic gate fields are required.
    assert schema["additionalProperties"] is False
    assert sorted(schema["required"]) == sorted(
        ["accepted", "external_authority_dependency", "violation_type", "reason"]
    )
    assert schema["properties"]["violation_type"]["enum"] == [
        "NONE",
        "EXTERNAL_THEOREM_AUTHORITY",
        "TARGET_CIRCULARITY",
        "UNDECLARED_EXTERNAL_RESULT",
    ]
    # No target-specific string rules anywhere (§9).
    assert "Tao" not in prompt and "discrepancy" not in prompt
    # Evidence: exact prompt retained on the adapter.
    assert verifier.last_prompt == prompt


# --- driver escalation and stop conditions (§32.6–§32.15) ----------------------

from driver import (  # noqa: E402
    LongHorizonBudget,
    run_long_horizon,
)


def _run(root, factory, **kwargs):
    return run_long_horizon(
        root,
        problem=ProblemSpec("p", PROBLEM_STATEMENT),
        worker=kwargs.pop("worker", GoalEchoWorker()),
        verifier=kwargs.pop("verifier", RejectingVerifier({BLOCKED_GOAL})),
        builder_for=factory.builder_for,
        auditor_for=factory.auditor_for,
        **kwargs,
    )


def test_blocked_frontier_escalates_split_then_cut_then_alt() -> None:
    """§13/§32.6-8: fixed order, declines advance the escalation."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        factory = Factory()  # all builders decline
        result = _run(root, factory)
        assert factory.requested == ["split", "insert_cut_set", "add_alternative_route"]
        assert result.stop_reason == "OPERATORS_EXHAUSTED"
        assert result.solve_status == "BLOCKED"
        # Declines never reach the auditor.
        assert factory.auditor.calls == []
        journal = [
            json.loads(line)
            for line in (root / "long_horizon_journal.jsonl").read_text(
                encoding="utf-8"
            ).splitlines()
        ]
        assert [entry["operation"] for entry in journal] == [
            "split",
            "insert_cut_set",
            "add_alternative_route",
        ]
        assert all(entry["blocked_node_id"] == "mid" for entry in journal)
        # Declines advance the escalation directly: exactly one solve (3
        # attempts), never a re-solve of the unchanged exhausted frontier.
        assert result.solver_attempts == 3


def test_applied_split_executes_children_and_solves_target() -> None:
    """§32.9: APPLIED mutation hands back to the frozen solver."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        factory = Factory(builder_results=[split_apply_result()])
        result = _run(root, factory)
        assert result.stop_reason == "TARGET_SOLVED"
        assert result.solve_status == "SOLVED"
        assert factory.requested == ["split"]
        assert len(factory.auditor.calls) == 1
        facts = FactGraph(root).list_facts()
        assert {fact.statement for fact in facts} == {
            "Part one of M.",
            "Part two of M.",
            PROBLEM_STATEMENT,
        }


def test_new_blocked_node_restarts_escalation_at_split() -> None:
    """§13/§32.10: a new node identity is a new obligation."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        # split(mid) applies; mid-a solves; mid-b blocks and all its
        # operators decline.
        factory = Factory(builder_results=[split_apply_result()])
        result = _run(
            root,
            factory,
            verifier=RejectingVerifier({BLOCKED_GOAL, "Part two of M."}),
        )
        assert result.stop_reason == "OPERATORS_EXHAUSTED"
        assert factory.requested == [
            "split",  # on mid
            "split",  # restarted on mid-b
            "insert_cut_set",
            "add_alternative_route",
        ]
        journal = [
            json.loads(line)
            for line in (root / "long_horizon_journal.jsonl").read_text(
                encoding="utf-8"
            ).splitlines()
        ]
        assert [entry["blocked_node_id"] for entry in journal] == [
            "mid",
            "mid-b",
            "mid-b",
            "mid-b",
        ]


def test_same_obligation_operator_pair_is_never_repeated() -> None:
    """§15/§32.11: escalation state is scanned from evidence, not memory."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        factory = Factory(builder_results=[split_apply_result()])
        _run(root, factory, verifier=RejectingVerifier({BLOCKED_GOAL, "Part two of M."}))
        pairs = [
            (entry["blocked_node_id"], entry["operation"])
            for entry in (
                json.loads(line)
                for line in (root / "long_horizon_journal.jsonl")
                .read_text(encoding="utf-8")
                .splitlines()
            )
        ]
        assert len(pairs) == len(set(pairs))
        # And a second run over the same workspace tries nothing new.
        factory2 = Factory()
        result2 = _run(root, factory2, verifier=RejectingVerifier({BLOCKED_GOAL, "Part two of M."}))
        assert factory2.requested == []
        assert result2.stop_reason == "OPERATORS_EXHAUSTED"


def test_mutation_budget_stops_the_run() -> None:
    """§16/§32.12."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        factory = Factory(builder_results=[split_apply_result()])
        result = _run(
            root,
            factory,
            verifier=RejectingVerifier({BLOCKED_GOAL, "Part two of M."}),
            budget=LongHorizonBudget(max_mutation_episodes=1),
        )
        assert result.stop_reason == "BUDGET_EXHAUSTED"
        assert result.mutation_episodes == 1
        # No further operator was attempted on mid-b.
        assert factory.requested == ["split"]


def test_solver_attempt_budget_stops_the_run() -> None:
    """§16/§32.13: attempts are the attempt-*.json artifacts created mid-run."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        factory = Factory()
        result = _run(
            root,
            factory,
            budget=LongHorizonBudget(max_solver_attempts=2),
        )
        # The first solve burns 3 attempts (product budget) on mid.
        assert result.stop_reason == "BUDGET_EXHAUSTED"
        assert result.solver_attempts >= 3
        assert factory.requested == []


def test_target_solved_stops_without_calling_builders() -> None:
    """§17/§32.14."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        problem = ProblemSpec("p", PROBLEM_STATEMENT)
        ProofScaffold.create(
            root / "scaffold.json",
            problem=problem,
            target_node_id="target",
            nodes=(ScaffoldNode("target", PROBLEM_STATEMENT),),
        )
        factory = Factory()
        result = _run(root, factory, verifier=RejectingVerifier())
        assert result.stop_reason == "TARGET_SOLVED"
        assert factory.requested == []


def test_system_error_stops_the_run() -> None:
    """§17/§32.15."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        factory = Factory()
        result = _run(root, factory, worker=RaisingWorker())
        assert result.stop_reason == "SYSTEM_ERROR"
        assert "scripted worker crash" in result.error


# --- driver locality / truth boundary (§32.16–§32.20) --------------------------


def _context_text(context) -> str:
    return "\n".join(
        [
            context.original_problem,
            context.blocked_node.goal,
            context.blocked_obligation.goal,
            "\n".join(node.goal for node in context.local_nodes),
            "\n".join(fact.statement + fact.proof for fact in context.verified_boundary),
            context.downstream_intent,
            context.previous_refinement_summary or "",
        ]
    )


def test_builder_context_stays_local_across_episodes() -> None:
    """§18/§19/§32.16-17: no transcript growth, no sibling leakage — even after
    several episodes."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace_with_sibling(root)
        factory = Factory(builder_results=[split_apply_result()])
        _run(
            root,
            factory,
            verifier=RejectingVerifier({BLOCKED_GOAL, "Part two of M."}),
        )
        assert len(factory.builders) == 4  # split(mid) + 3 declines on mid-b
        for builder in factory.builders:
            for context in builder.contexts:
                text = _context_text(context)
                assert SIDE_GOAL not in text
                assert SIDE_PROOF not in text
        # No transcript memory: later contexts carry only the one-line-per-
        # episode refinement digest for this obligation, not prior prompts.
        last = factory.builders[-1].contexts[0]
        assert "looks sound" not in (last.previous_refinement_summary or "")


def test_fact_truth_gate_unchanged_no_facts_on_rejection() -> None:
    """§32.18."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        make_workspace(root)
        factory = Factory()
        _run(root, factory)
        assert FactGraph(root).list_facts() == []


def test_driver_does_not_touch_the_frozen_legacy_path() -> None:
    """§32.20: importing/using the driver leaves legacy one-shot semantics
    byte-compatible (no scheduler, no solver config)."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        problem = ProblemSpec("p", PROBLEM_STATEMENT)
        scaffold = ProofScaffold.create(
            root / "scaffold.json",
            problem=problem,
            target_node_id="target",
            nodes=(ScaffoldNode("target", PROBLEM_STATEMENT),),
        )
        result = solve_scaffold(
            scaffold=scaffold,
            problem=problem,
            registry=ObligationRegistry(root / "obligations.json"),
            graph=FactGraph(root),
            author="worker",
            worker=GoalEchoWorker(),
            verifier=RejectingVerifier(),
        )
        assert result.status == "SOLVED"


# --- metrics (§26/§27) ----------------------------------------------------------

from metrics import compute_metrics  # noqa: E402


def test_compute_metrics_counts_and_depth() -> None:
    with TemporaryDirectory() as directory:
        root = Path(directory)
        graph = FactGraph(root)
        base = graph.add_fact(
            Fact.create(problem_id="p", author="w", statement="Base.", proof="pb")
        )
        middle = graph.add_fact(
            Fact.create(
                problem_id="p",
                author="w",
                statement="Middle.",
                proof="pm",
                predecessors=(base.fact_id,),
            )
        )
        top = graph.add_fact(
            Fact.create(
                problem_id="p",
                author="w",
                statement="Top.",
                proof="pt",
                predecessors=(middle.fact_id,),
            )
        )
        for index, (verdict, reason) in enumerate(
            [
                ("PASS", "ok"),
                ("FAIL", "gap in step 2"),
                ("FAIL", "[CLOSED_BOOK:EXTERNAL_THEOREM_AUTHORITY] cites X"),
                ("ERROR", None),
            ],
            start=1,
        ):
            _write_json(
                root / "attempts" / f"attempt-{index:06d}.json",
                {
                    "attempt_id": f"attempt-{index:06d}",
                    "problem_id": "p",
                    "obligation_id": "scaffold:p:mid",
                    "candidate_artifact": None,
                    "verifier_artifact": (
                        {"accepted": verdict == "PASS", "reason": reason}
                        if reason
                        else None
                    ),
                    "verdict": verdict,
                    "error": None,
                },
            )
        _write_json(
            root / "local_refinements" / "split-deadbeefcafe.json",
            {
                "blocked_node_id": "mid",
                "outcome": "APPLIED",
                "proposal": {"obstruction": "o"},
                "auditor": {"verdict": "PASS"},
            },
        )
        _write_json(
            root / "local_refinements" / "no-cut-20260902T000000000000.json",
            {"blocked_node_id": "mid", "outcome": "NO_USEFUL_CUT"},
        )
        _write_json(
            root / "local_refinements" / "alt-001122334455.json",
            {
                "blocked_node_id": "mid",
                "outcome": "AUDITOR_REJECT",
                "auditor": {"verdict": "REJECT"},
            },
        )

        metrics = compute_metrics(root, initial_attempt_count=0)
        assert metrics["fact_count"] == 3
        assert metrics["verified_reasoning_depth"] == 3
        assert metrics["solver_attempts"] == 4
        assert metrics["verifier_rejections"] == 2
        assert metrics["external_authority_rejections"] == 1
        assert metrics["system_errors"] == 1
        assert metrics["operators"]["split"] == {"proposed": 1, "applied": 1}
        assert metrics["operators"]["insert_cut_set"] == {"proposed": 1, "applied": 0}
        assert metrics["operators"]["add_alternative_route"] == {"proposed": 1, "applied": 0}
        assert metrics["builder_declines"] == 1
        assert metrics["auditor_rejects"] == 1
        assert top.statement == "Top."


# --- fact audit (§30) -----------------------------------------------------------

from fact_audit import FactAuditor  # noqa: E402


def _audit_response(**overrides) -> dict:
    response = {
        "mathematically_correct": True,
        "predecessor_sufficient": True,
        "closed_book_clean": True,
        "no_target_circularity": True,
        "classification": "SUBSTANTIVE",
        "reasons": ["self-contained induction"],
    }
    response.update(overrides)
    return response


def test_fact_audit_passes_substantive_fact() -> None:
    codex = RecordingCodex(_audit_response())
    fact = Fact.create(problem_id="p", author="w", statement="S.", proof="P.")
    result = FactAuditor(codex).audit(
        problem="P", fact=fact, predecessors=[], target_statement="T."
    )
    assert result["classification"] == "SUBSTANTIVE"
    prompt, schema, label = codex.calls[0]
    assert label == "closed_book_fact_audit"
    assert "S." in prompt and "P." in prompt
    assert schema["additionalProperties"] is False


@pytest.mark.parametrize(
    "check",
    [
        "mathematically_correct",
        "predecessor_sufficient",
        "closed_book_clean",
        "no_target_circularity",
    ],
)
def test_fact_audit_any_failed_check_forces_invalid(check: str) -> None:
    """Deterministic gate: the model's classification cannot override a
    failed boolean check."""
    codex = RecordingCodex(_audit_response(**{check: False}))
    fact = Fact.create(problem_id="p", author="w", statement="S.", proof="P.")
    result = FactAuditor(codex).audit(
        problem="P", fact=fact, predecessors=[], target_statement="T."
    )
    assert result["classification"] == "INVALID"


def test_fact_audit_trivial_classification_is_kept() -> None:
    codex = RecordingCodex(_audit_response(classification="TRIVIAL"))
    fact = Fact.create(problem_id="p", author="w", statement="S.", proof="P.")
    result = FactAuditor(codex).audit(
        problem="P", fact=fact, predecessors=[], target_statement="T."
    )
    assert result["classification"] == "TRIVIAL"


# --- INVALID cascade (§30) ------------------------------------------------------

from fact_audit import cascade_invalid  # noqa: E402


def _chain_facts():
    """a (root, INVALID) <- b <- c; d unrelated."""
    a = Fact.create(problem_id="p", author="w", statement="A.", proof="PA.")
    b = Fact.create(
        problem_id="p", author="w", statement="B.", proof="PB.",
        predecessors=(a.fact_id,),
    )
    c = Fact.create(
        problem_id="p", author="w", statement="C.", proof="PC.",
        predecessors=(b.fact_id,),
    )
    d = Fact.create(problem_id="p", author="w", statement="D.", proof="PD.")
    return a, b, c, d


def test_cascade_invalid_marks_all_downstream() -> None:
    a, b, c, d = _chain_facts()
    audits = [
        {"fact_id": a.fact_id, "classification": "INVALID"},
        {"fact_id": b.fact_id, "classification": "SUBSTANTIVE"},
        {"fact_id": c.fact_id, "classification": "TRIVIAL"},
        {"fact_id": d.fact_id, "classification": "SUBSTANTIVE"},
    ]
    result = {item["fact_id"]: item for item in cascade_invalid([a, b, c, d], audits)}
    assert result[a.fact_id]["classification"] == "INVALID"
    assert result[b.fact_id]["classification"] == "INVALID"
    assert "cascade" in result[b.fact_id]
    assert result[c.fact_id]["classification"] == "INVALID"
    assert result[d.fact_id]["classification"] == "SUBSTANTIVE"


def test_cascade_invalid_ignores_audit_errors() -> None:
    """AUDIT_ERROR records an unauditable fact; it is not treated as refuted
    and does not cascade."""
    a, b, c, d = _chain_facts()
    audits = [
        {"fact_id": a.fact_id, "classification": "AUDIT_ERROR"},
        {"fact_id": b.fact_id, "classification": "SUBSTANTIVE"},
    ]
    result = {item["fact_id"]: item for item in cascade_invalid([a, b], audits)}
    assert result[a.fact_id]["classification"] == "AUDIT_ERROR"
    assert result[b.fact_id]["classification"] == "SUBSTANTIVE"


def test_cascade_invalid_no_invalid_facts_is_identity() -> None:
    a, b, c, d = _chain_facts()
    audits = [
        {"fact_id": fact.fact_id, "classification": "SUBSTANTIVE"}
        for fact in (a, b, c, d)
    ]
    assert cascade_invalid([a, b, c, d], audits) == audits


# --- fixture cleanliness (§22/§32.19) -------------------------------------------

from run_experiment import prepare_erdos67  # noqa: E402


def test_erdos67_prep_starts_from_clean_baseline_only() -> None:
    """§22: no N2C facts, no N2A/B/C refinement history, nothing beyond the
    byte-identical baseline copy."""
    with TemporaryDirectory() as directory:
        root = Path(directory)
        baseline = root / "baseline"
        (baseline / "attempts").mkdir(parents=True)
        (baseline / "facts").mkdir()
        _write_json(baseline / "scaffold.json", {"nodes": []})
        _write_json(baseline / "obligations.json", {"obligations": []})
        _write_json(
            baseline / "attempts" / "attempt-000001.json",
            {"attempt_id": "attempt-000001", "verdict": "FAIL"},
        )
        case_root = root / "case"

        problem_dir, problem = prepare_erdos67(case_root, baseline_dir=baseline)

        assert problem.statement  # real #67 statement constant
        assert (problem_dir / "scaffold.json").is_file()
        assert not (problem_dir / "local_refinements").exists()
        assert list((problem_dir / "facts").glob("*")) == []
        # Exactly the baseline files, nothing more.
        copied = sorted(
            str(path.relative_to(problem_dir)) for path in problem_dir.rglob("*")
        )
        expected = sorted(
            str(path.relative_to(baseline)) for path in baseline.rglob("*")
        )
        assert copied == expected


# --- resume CLI contract (frozen manual-Retry semantics) ------------------------

from run_experiment import run_case  # noqa: E402


def test_resume_rejects_probe_and_packets() -> None:
    for case in ("probe", "packets"):
        with pytest.raises(SystemExit):
            run_case(case, force=False, resume=True)


def test_resume_and_force_are_mutually_exclusive(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("run_experiment.HERE", tmp_path)
    (tmp_path / "runs" / "control_a").mkdir(parents=True)
    with pytest.raises(SystemExit):
        run_case("control_a", force=True, resume=True)


def test_resume_requires_existing_case_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("run_experiment.HERE", tmp_path)
    with pytest.raises(SystemExit):
        run_case("control_a", force=False, resume=True)


def test_resume_archives_previous_leg_evidence(tmp_path, monkeypatch) -> None:
    """The prior leg's evidence/ is moved aside, never overwritten."""
    monkeypatch.setattr("run_experiment.HERE", tmp_path)
    case_root = tmp_path / "runs" / "control_a"
    evidence = case_root / "evidence"
    evidence.mkdir(parents=True)
    (evidence / "summary.json").write_text("{}", encoding="utf-8")

    calls = {}

    def fake_long_horizon(case, root, solver_attempts=3, resume=False):
        calls.update(case=case, root=root, resume=resume)
        return {"case": case}

    monkeypatch.setattr("run_experiment.run_long_horizon_case", fake_long_horizon)
    run_case("control_a", force=False, resume=True)

    assert calls == {"case": "control_a", "root": case_root, "resume": True}
    assert (case_root / "evidence_leg1" / "summary.json").is_file()
    assert not evidence.exists()


# --- runtime violation aggregation (§31) -----------------------------------------

from run_experiment import _network_attempt_total  # noqa: E402


def test_network_attempt_total_aggregates_across_legs(tmp_path) -> None:
    case_root = tmp_path / "case"
    for evidence_dir, attempts in (
        (case_root / "evidence_leg1" / "invocations", ["curl arxiv"]),
        (case_root / "evidence" / "invocations", []),
    ):
        evidence_dir.mkdir(parents=True)
        (evidence_dir / "001_research_worker.json").write_text(
            json.dumps({"network_attempts": attempts}), encoding="utf-8"
        )
    assert _network_attempt_total(case_root) == 1
    assert _network_attempt_total(tmp_path / "empty") == 0
