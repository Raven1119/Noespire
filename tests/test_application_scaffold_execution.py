"""N1.14P — product wiring of the static multi-node scaffold proof path.

Fresh problems (no root obligation, no scaffold.json) execute through
``run_static_scaffold_once`` (Architect once → materialize → multi-node
execution); a workspace with a persisted scaffold resumes through
``solve_scaffold`` (zero Architect calls, zero resolved-node re-execution);
legacy root-obligation workspaces keep the ``solve_problem_once`` path.
All execution is real research-core code over scripted doubles injected
through ExecutionService factories, never by patching the core.
"""

import json
from pathlib import Path
import threading
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from application.execution import ExecutionService
from application.http import create_app
from application.workspace_read_model import build_read_model

from research.graph import FactGraph
from research.obligation import ObligationRegistry, ObligationStatus, ProofObligation
from research.pipeline import VerificationResult
from research.problem import ProblemSpec
from research.scaffold import ProofScaffold, ScaffoldNode
from research.scaffold_architect import ScaffoldProposal, ScaffoldProposalNode

from application_fixtures import (
    BlockingGoalWorker,
    GoalEchoWorker,
    RejectingVerifier,
    StubArchitect,
    WorkspaceBuilder,
    add_fact,
    append_log,
    registry_for,
    wait_for,
    write_residual_running_attempt,
)


def read_log(problem_dir: Path) -> list:
    log = problem_dir / "_execution_log.jsonl"
    if not log.is_file():
        return []
    return [
        json.loads(line)
        for line in log.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def linear_proposal(statement: str) -> ScaffoldProposal:
    """lemma1 -> lemma2 -> target, target goal == the problem statement."""
    return ScaffoldProposal(
        nodes=(
            ScaffoldProposalNode("lemma1", "Lemma one.", (), ()),
            ScaffoldProposalNode("lemma2", "Lemma two.", ("lemma1",), ()),
            ScaffoldProposalNode("target", statement, ("lemma2",), ()),
        ),
        target_node_id="target",
    )


class ScaffoldExecutionTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.builder = WorkspaceBuilder(Path(self.temporary.name))

    def _service(self, worker, verifier, architect) -> ExecutionService:
        return ExecutionService(
            self.builder.root,
            worker_factory=lambda: worker,
            verifier_factory=lambda: verifier,
            architect_factory=lambda: architect,
        )

    def _client(self, service: ExecutionService) -> TestClient:
        return TestClient(create_app(self.builder.root, execution_service=service))

    def _run_to_idle(self, service: ExecutionService, client: TestClient, problem_id: str) -> None:
        response = client.post(f"/api/problems/{problem_id}/attempts")
        self.assertEqual(response.status_code, 202, response.json())
        self.assertTrue(wait_for(lambda: not service.is_running(problem_id)))


class FreshProblemScaffoldExecutionTests(ScaffoldExecutionTestBase):
    """A. Fresh problem: Architect once, scaffold persisted, multi-node SOLVED."""

    def test_fresh_problem_runs_architect_once_and_solves_three_nodes(self) -> None:
        problem_dir = self.builder.add_problem("p-a", "Target theorem A.")
        architect = StubArchitect([linear_proposal("Target theorem A.")])
        worker = GoalEchoWorker()
        verifier = RejectingVerifier()
        service = self._service(worker, verifier, architect)
        client = self._client(service)

        self._run_to_idle(service, client, "p-a")

        self.assertEqual(architect.calls, 1)
        self.assertTrue((problem_dir / "scaffold.json").is_file())
        self.assertEqual(worker.goals, ["Lemma one.", "Lemma two.", "Target theorem A."])
        self.assertEqual(verifier.calls, 3)

        model = client.get("/api/problems/p-a").json()
        self.assertEqual(model["status"], "SOLVED")
        self.assertEqual(model["execution_mode"], "STATIC_SCAFFOLD")
        self.assertEqual(model["target_fact"]["statement"], "Target theorem A.")
        self.assertEqual(len(model["supporting_closure"]), 3)

    def test_execution_id_correlates_many_attempt_ids(self) -> None:
        """One execution -> N attempts: per-attempt invocation and finish
        records all carry the same execution_id and the correct attempt_id."""
        problem_dir = self.builder.add_problem("p-corr", "Target theorem C.")
        service = self._service(
            GoalEchoWorker(), RejectingVerifier(),
            StubArchitect([linear_proposal("Target theorem C.")]),
        )
        self._run_to_idle(service, self._client(service), "p-corr")

        events = read_log(problem_dir)
        architect_events = [e for e in events if e["kind"] == "ARCHITECT_INVOKED"]
        self.assertEqual(len(architect_events), 1)
        execution_id = architect_events[0]["execution_id"]

        attempt_ids = ["attempt-000001", "attempt-000002", "attempt-000003"]
        workers = [e for e in events if e["kind"] == "WORKER_INVOKED"]
        verifiers = [e for e in events if e["kind"] == "VERIFIER_INVOKED"]
        self.assertEqual([e["attempt_id"] for e in workers], attempt_ids)
        self.assertEqual([e["attempt_id"] for e in verifiers], attempt_ids)
        for event in workers + verifiers:
            self.assertEqual(event["execution_id"], execution_id)

        finishes = [e for e in events if e["kind"] == "ATTEMPT_FINISHED"]
        self.assertEqual(len(finishes), 3)
        self.assertEqual([e["attempt_id"] for e in finishes], attempt_ids)
        for event in finishes:
            self.assertEqual(event["execution_id"], execution_id)
            self.assertEqual(event["outcome_stage"], "PASS")
            self.assertTrue(event["verifier_called"])
            self.assertIsNotNone(event["started_at"])
            self.assertIsNotNone(event["finished_at"])


class SolvedScaffoldReadModelTests(ScaffoldExecutionTestBase):
    """B. A solved multi-node workspace reads back SOLVED with a multi-fact closure."""

    def test_solved_multi_node_workspace_reads_solved_with_closure(self) -> None:
        self.builder.add_problem("p-b", "Target theorem B.")
        service = self._service(
            GoalEchoWorker(), RejectingVerifier(),
            StubArchitect([linear_proposal("Target theorem B.")]),
        )
        client = self._client(service)
        self._run_to_idle(service, client, "p-b")

        model = client.get("/api/problems/p-b").json()

        self.assertEqual(model["status"], "SOLVED")
        self.assertEqual(model["display_status"], "SOLVED")
        self.assertIsNotNone(model["target_fact"])
        self.assertEqual(model["target_fact"]["statement"], "Target theorem B.")
        self.assertGreater(len(model["supporting_closure"]), 1)
        self.assertEqual(
            [fact["statement"] for fact in model["supporting_closure"]],
            ["Lemma one.", "Lemma two.", "Target theorem B."],
        )
        self.assertIsNone(model["obligation"])
        self.assertEqual(len(model["attempts"]), 3)


class BlockedScaffoldTests(ScaffoldExecutionTestBase):
    """C/D. A verifier rejection blocks the run; a manual retry resumes only
    the failed node — no Architect call, no resolved-node re-execution.

    The product default is ``max_attempts_per_obligation=3`` (N1.15 bounded
    repair), so the blocked workspace shows lemma2 attempted three times
    (rounds 2-3 with repair context) before the run blocks. Legacy
    single-attempt-on-FAIL is pinned at the research layer instead
    (``execute_obligation`` and ``solver_config=None`` scaffold tests).
    """

    def _blocked_workspace(self):
        problem_dir = self.builder.add_problem("p-block", "Target theorem X.")
        architect = StubArchitect([linear_proposal("Target theorem X.")])
        worker = GoalEchoWorker()
        verifier = RejectingVerifier({"Lemma two."})
        service = self._service(worker, verifier, architect)
        client = self._client(service)
        self._run_to_idle(service, client, "p-block")
        return problem_dir, architect, worker, verifier, service, client

    def test_verifier_rejection_blocks_run_and_keeps_lemma_fact(self) -> None:
        problem_dir, architect, worker, verifier, service, client = self._blocked_workspace()

        self.assertEqual(architect.calls, 1)
        self.assertEqual(
            worker.goals, ["Lemma one.", "Lemma two.", "Lemma two.", "Lemma two."]
        )
        self.assertEqual(verifier.calls, 4)
        # The lemma1 Fact was admitted and retained; the target never ran.
        self.assertEqual(
            [fact.statement for fact in FactGraph(problem_dir).list_facts()],
            ["Lemma one."],
        )
        scaffold = ProofScaffold(problem_dir / "scaffold.json")
        self.assertIsNotNone(scaffold.get("lemma1").resolved_by_fact_id)
        self.assertIsNone(scaffold.get("lemma2").resolved_by_fact_id)
        self.assertIsNone(scaffold.get("target").resolved_by_fact_id)

        model = client.get("/api/problems/p-block").json()
        self.assertEqual(model["status"], "OPEN")
        attempts = {a["scaffold_node_id"]: a for a in model["attempts"]}
        self.assertEqual(attempts["lemma2"]["verdict"], "FAIL")
        self.assertEqual(attempts["lemma2"]["failure_class"], "rejection")
        self.assertEqual(
            attempts["lemma2"]["obligation_id"], "scaffold:p-block:lemma2"
        )
        self.assertIsNone(model["last_execution_failure"])

        finishes = [e for e in read_log(problem_dir) if e["kind"] == "ATTEMPT_FINISHED"]
        self.assertEqual(
            [(e["attempt_id"], e["outcome_stage"]) for e in finishes],
            [
                ("attempt-000001", "PASS"),
                ("attempt-000002", "FRESH_VERIFIER_REJECT"),
                ("attempt-000003", "FRESH_VERIFIER_REJECT"),
                ("attempt-000004", "FRESH_VERIFIER_REJECT"),
            ],
        )

    def test_manual_retry_resumes_without_architect_or_resolved_rerun(self) -> None:
        """Retry coherence after a BLOCKED run WITH repair evidence: the resume
        re-plans nothing, re-proves nothing resolved, and starts each node at
        repair round 1 (repair context never crosses executions)."""
        problem_dir, architect, worker, verifier, service, client = self._blocked_workspace()
        # The blocked run's repair rounds saw the verifier reason in context.
        self.assertEqual(
            [ctx is None for ctx in worker.repair_contexts],
            [True, True, False, False],
        )
        for round_number, ctx in zip((2, 3), worker.repair_contexts[2:]):
            self.assertEqual(ctx.attempt_number, round_number)
            self.assertEqual(ctx.max_attempts, 3)
            self.assertEqual(ctx.previous_statement, "Lemma two.")
            self.assertTrue(ctx.verifier_reason)
        verifier.rejected.clear()

        self._run_to_idle(service, client, "p-block")

        self.assertEqual(architect.calls, 1)  # resume never re-plans
        self.assertEqual(
            worker.goals,
            [
                "Lemma one.",
                "Lemma two.",
                "Lemma two.",
                "Lemma two.",
                "Lemma two.",
                "Target theorem X.",
            ],
        )
        # The retried lemma2 and the target are fresh solver runs: round 1.
        self.assertIsNone(worker.repair_contexts[4])
        self.assertIsNone(worker.repair_contexts[5])
        model = client.get("/api/problems/p-block").json()
        self.assertEqual(model["status"], "SOLVED")
        self.assertEqual(len(model["supporting_closure"]), 3)


class FailOnceVerifier:
    """Rejects each listed statement exactly once, then accepts it."""

    def __init__(self, reject_once) -> None:
        self.reject_once = set(reject_once)
        self.failed = set()
        self.calls = 0

    def verify(self, problem, candidate, predecessors):
        self.calls += 1
        if candidate.statement in self.reject_once and candidate.statement not in self.failed:
            self.failed.add(candidate.statement)
            return VerificationResult(False, "scripted first-round rejection")
        return VerificationResult(True, "scripted acceptance")


class AttributedGoalWorker(GoalEchoWorker):
    """Snapshots the service's current_attempt_id inside every propose call."""

    def __init__(self) -> None:
        super().__init__()
        self.service = None
        self.problem_id = None
        self.attempt_snapshots = []

    def propose(self, *, problem, existing_facts, subgoal, repair_context=None):
        self.attempt_snapshots.append(self.service.current_attempt_id(self.problem_id))
        return super().propose(
            problem=problem,
            existing_facts=existing_facts,
            subgoal=subgoal,
            repair_context=repair_context,
        )


class ProductRepairAttributionTests(ScaffoldExecutionTestBase):
    """N1.15: a FAIL-then-repair-PASS product execution produces one
    ATTEMPT_FINISHED per attempt with correct per-attempt attribution, and
    repair rounds are strictly sequential (exactly one RUNNING-verdict
    attempt in flight at any moment)."""

    def test_fail_then_repair_pass_attributes_every_attempt(self) -> None:
        problem_dir = self.builder.add_problem("p-rep", "Target theorem REP.")
        worker = AttributedGoalWorker()
        verifier = FailOnceVerifier({"Lemma two."})
        service = ExecutionService(
            self.builder.root,
            worker_factory=lambda: worker,
            verifier_factory=lambda: verifier,
            architect_factory=lambda: StubArchitect(
                [linear_proposal("Target theorem REP.")]
            ),
            max_attempts_per_obligation=2,
        )
        worker.service = service
        worker.problem_id = "p-rep"
        client = self._client(service)

        self._run_to_idle(service, client, "p-rep")

        self.assertEqual(
            worker.goals,
            ["Lemma one.", "Lemma two.", "Lemma two.", "Target theorem REP."],
        )
        # Round 1 of every node is the legacy call shape; lemma2 round 2
        # carries the rejection feedback.
        self.assertEqual(
            [ctx is None for ctx in worker.repair_contexts], [True, True, False, True]
        )
        repair = worker.repair_contexts[2]
        self.assertEqual(repair.verifier_reason, "scripted first-round rejection")
        self.assertEqual(repair.attempt_number, 2)
        self.assertEqual(repair.max_attempts, 2)
        # Live attribution: each worker invocation saw exactly its own
        # in-flight attempt — never two RUNNING attempts at once.
        self.assertEqual(
            worker.attempt_snapshots,
            ["attempt-000001", "attempt-000002", "attempt-000003", "attempt-000004"],
        )

        events = read_log(problem_dir)
        attempt_ids = [f"attempt-{n:06d}" for n in range(1, 5)]
        self.assertEqual(
            [e["attempt_id"] for e in events if e["kind"] == "WORKER_INVOKED"],
            attempt_ids,
        )
        self.assertEqual(
            [e["attempt_id"] for e in events if e["kind"] == "VERIFIER_INVOKED"],
            attempt_ids,
        )
        finishes = [e for e in events if e["kind"] == "ATTEMPT_FINISHED"]
        self.assertEqual(
            [(e["attempt_id"], e["outcome_stage"]) for e in finishes],
            [
                ("attempt-000001", "PASS"),
                ("attempt-000002", "FRESH_VERIFIER_REJECT"),
                ("attempt-000003", "PASS"),
                ("attempt-000004", "PASS"),
            ],
        )

        model = client.get("/api/problems/p-rep").json()
        self.assertEqual(model["status"], "SOLVED")
        self.assertEqual(len(model["attempts"]), 4)
        # Exactly one verified Fact per node — repair never double-admits.
        self.assertEqual(
            sorted(fact.statement for fact in FactGraph(problem_dir).list_facts()),
            ["Lemma one.", "Lemma two.", "Target theorem REP."],
        )


class ArchitectFailureTests(ScaffoldExecutionTestBase):
    """E/F. An invalid proposal fails closed: nothing executes, nothing
    persists; the next manual retry invokes a fresh Architect."""

    def _invalid_proposal(self, statement: str) -> ScaffoldProposal:
        return ScaffoldProposal(
            nodes=(ScaffoldProposalNode("target", "A different theorem entirely.", (), ()),),
            target_node_id="target",
        )

    def test_invalid_proposal_runs_nothing_and_records_architect_invalid(self) -> None:
        problem_dir = self.builder.add_problem("p-inv", "Target theorem I.")
        architect = StubArchitect([self._invalid_proposal("Target theorem I.")])
        worker = GoalEchoWorker()
        verifier = RejectingVerifier()
        service = self._service(worker, verifier, architect)
        client = self._client(service)

        self._run_to_idle(service, client, "p-inv")

        self.assertEqual(architect.calls, 1)
        self.assertEqual(worker.calls, 0)
        self.assertEqual(verifier.calls, 0)
        self.assertFalse((problem_dir / "scaffold.json").exists())
        self.assertEqual(FactGraph(problem_dir).list_facts(), [])

        model = client.get("/api/problems/p-inv").json()
        self.assertEqual(model["status"], "OPEN")
        self.assertEqual(model["attempts"], [])
        failure = model["last_execution_failure"]
        self.assertIsNotNone(failure)
        self.assertEqual(failure["outcome_stage"], "ARCHITECT_INVALID")
        self.assertIsNotNone(failure["error"])

        events = read_log(problem_dir)
        self.assertEqual(len([e for e in events if e["kind"] == "WORKER_INVOKED"]), 0)
        (finish,) = [e for e in events if e["kind"] == "ATTEMPT_FINISHED"]
        self.assertIsNone(finish["attempt_id"])
        self.assertEqual(finish["outcome_stage"], "ARCHITECT_INVALID")
        self.assertIsNotNone(finish["error"])
        self.assertIsNotNone(finish["started_at"])
        self.assertIsNotNone(finish["finished_at"])

    def test_retry_after_architect_invalid_invokes_a_fresh_architect(self) -> None:
        self.builder.add_problem("p-retry", "Target theorem R.")
        architect = StubArchitect(
            [self._invalid_proposal("Target theorem R."), linear_proposal("Target theorem R.")]
        )
        worker = GoalEchoWorker()
        service = self._service(worker, RejectingVerifier(), architect)
        client = self._client(service)

        self._run_to_idle(service, client, "p-retry")
        self.assertEqual(architect.calls, 1)
        self.assertEqual(client.get("/api/problems/p-retry").json()["status"], "OPEN")

        self._run_to_idle(service, client, "p-retry")

        self.assertEqual(architect.calls, 2)
        self.assertEqual(client.get("/api/problems/p-retry").json()["status"], "SOLVED")


class LegacyWorkspaceUnchangedTests(ScaffoldExecutionTestBase):
    """G. A legacy root-obligation workspace keeps the solve_problem_once path:
    the Architect factory is never even constructed."""

    def test_legacy_open_workspace_uses_direct_path_and_never_builds_architect(self) -> None:
        problem_dir = self.builder.add_problem("p-leg", "Legacy theorem.")
        registry_for(problem_dir).add(
            ProofObligation("root:p-leg", (), "Legacy theorem.", "root")
        )
        worker = GoalEchoWorker()
        verifier = RejectingVerifier()

        def exploding_architect_factory():
            raise AssertionError("architect factory must never be called")

        service = ExecutionService(
            self.builder.root,
            worker_factory=lambda: worker,
            verifier_factory=lambda: verifier,
            architect_factory=exploding_architect_factory,
        )
        client = self._client(service)

        self._run_to_idle(service, client, "p-leg")

        self.assertEqual(worker.goals, ["Legacy theorem."])
        self.assertEqual(
            registry_for(problem_dir).get("root:p-leg").status,
            ObligationStatus.DISCHARGED,
        )
        self.assertFalse((problem_dir / "scaffold.json").exists())
        model = client.get("/api/problems/p-leg").json()
        self.assertEqual(model["status"], "SOLVED")
        self.assertEqual(model["execution_mode"], "LEGACY_DIRECT")
        self.assertIsNone(model["proof_structure"])
        self.assertEqual(model["obligation"]["obligation_id"], "root:p-leg")


class AlreadySolvedClaimTests(ScaffoldExecutionTestBase):
    """H. SOLVED is a 409 in both modes."""

    def test_solved_scaffold_workspace_returns_409_already_solved(self) -> None:
        self.builder.add_problem("p-done", "Target theorem D.")
        service = self._service(
            GoalEchoWorker(), RejectingVerifier(),
            StubArchitect([linear_proposal("Target theorem D.")]),
        )
        client = self._client(service)
        self._run_to_idle(service, client, "p-done")
        self.assertEqual(client.get("/api/problems/p-done").json()["status"], "SOLVED")

        response = client.post("/api/problems/p-done/attempts")

        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json(), {"error": "already_solved"})


class ConcurrentStartTests(ScaffoldExecutionTestBase):
    """I. Concurrent double start on a fresh (scaffold-mode) problem."""

    def test_concurrent_double_start_exactly_one_accepted(self) -> None:
        self.builder.add_problem("p-race", "Target theorem Race.")
        started, release = threading.Event(), threading.Event()
        worker = BlockingGoalWorker(started, release)
        service = self._service(
            worker, RejectingVerifier(),
            StubArchitect([linear_proposal("Target theorem Race.")]),
        )
        client = self._client(service)
        barrier = threading.Barrier(2)
        responses = []

        def do_post() -> None:
            barrier.wait()
            responses.append(client.post("/api/problems/p-race/attempts"))

        threads = [threading.Thread(target=do_post) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(sorted(r.status_code for r in responses), [202, 409])
        conflict = next(r for r in responses if r.status_code == 409)
        self.assertEqual(conflict.json(), {"error": "already_running"})
        self.assertTrue(started.wait(timeout=5))
        release.set()
        self.assertTrue(wait_for(lambda: not service.is_running("p-race")))
        self.assertEqual(client.get("/api/problems/p-race").json()["status"], "SOLVED")


class ScaffoldRecoveryTests(ScaffoldExecutionTestBase):
    """J. Startup recovery over scaffold workspaces."""

    def _service_recovery(self) -> ExecutionService:
        # Recovery never invokes worker/verifier/architect factories.
        return ExecutionService(self.builder.root)

    def test_running_scaffold_obligation_recovers_interrupted_and_is_idempotent(self) -> None:
        problem_dir = self.builder.add_problem("p-j1", "Target J1.")
        ProofScaffold.create(
            problem_dir / "scaffold.json",
            problem=ProblemSpec("p-j1", "Target J1."),
            target_node_id="target",
            nodes=(
                ScaffoldNode("lemma1", "Lemma J1."),
                ScaffoldNode("target", "Target J1.", depends_on=("lemma1",)),
            ),
        )
        registry = registry_for(problem_dir)
        registry.add(ProofObligation("scaffold:p-j1:lemma1", (), "Lemma J1.", "scaffold:lemma1"))
        registry.transition("scaffold:p-j1:lemma1", ObligationStatus.RUNNING)
        attempt_id = write_residual_running_attempt(
            problem_dir, "p-j1", obligation_id="scaffold:p-j1:lemma1"
        )

        self._service_recovery().recover_stale_running()

        self.assertEqual(
            registry_for(problem_dir).get("scaffold:p-j1:lemma1").status,
            ObligationStatus.OPEN,
        )
        (event,) = read_log(problem_dir)
        self.assertEqual(event["kind"], "RECOVERED_INTERRUPTED")
        self.assertEqual(event["attempt_id"], attempt_id)
        self.assertFalse(event["verifier_called"])
        model = build_read_model(self.builder.root, "p-j1")
        self.assertEqual(model["status"], "OPEN")

        first = read_log(problem_dir)
        self._service_recovery().recover_stale_running()
        self.assertEqual(read_log(problem_dir), first)

    def test_orphan_architect_invoked_gets_interrupted_finish_idempotent(self) -> None:
        problem_dir = self.builder.add_problem("p-j2", "Target J2.")
        append_log(
            problem_dir,
            {"kind": "ARCHITECT_INVOKED", "execution_id": "exec-orphan",
             "problem_id": "p-j2", "ts": "t1"},
        )

        self._service_recovery().recover_stale_running()

        (finish,) = [e for e in read_log(problem_dir) if e["kind"] == "ATTEMPT_FINISHED"]
        self.assertEqual(finish["execution_id"], "exec-orphan")
        self.assertIsNone(finish["attempt_id"])
        self.assertEqual(finish["outcome_stage"], "INTERRUPTED")
        self.assertTrue(finish["recovered"])
        self.assertIsNone(finish["started_at"])
        self.assertIsNone(finish["finished_at"])

        model = build_read_model(self.builder.root, "p-j2")
        self.assertIsNotNone(model["last_execution_failure"])
        self.assertEqual(model["last_execution_failure"]["outcome_stage"], "INTERRUPTED")

        first = read_log(problem_dir)
        self._service_recovery().recover_stale_running()
        self.assertEqual(read_log(problem_dir), first)

    def test_discharged_crash_window_reconciles_without_worker_or_verifier(self) -> None:
        """Crash between obligation DISCHARGED and scaffold.resolve: the next
        execution reconciles through solve_scaffold's DISCHARGED short-circuit
        (N1.12 semantics) — zero worker/verifier calls, zero Architect calls."""
        problem_dir = self.builder.add_problem("p-j3", "Target J3.")
        scaffold = ProofScaffold.create(
            problem_dir / "scaffold.json",
            problem=ProblemSpec("p-j3", "Target J3."),
            target_node_id="target",
            nodes=(ScaffoldNode("target", "Target J3."),),
        )
        registry = registry_for(problem_dir)
        registry.add(ProofObligation("scaffold:p-j3:target", (), "Target J3.", "scaffold:target"))
        registry.transition("scaffold:p-j3:target", ObligationStatus.RUNNING)
        fact = add_fact(problem_dir, "p-j3", "Target J3.", "Previously accepted proof.")
        registry.resolve("scaffold:p-j3:target", fact.fact_id, FactGraph(problem_dir))
        # The crash took the scaffold.resolve write: the node is unresolved.
        self.assertIsNone(scaffold.get("target").resolved_by_fact_id)

        worker = GoalEchoWorker()
        verifier = RejectingVerifier()

        def exploding_architect_factory():
            raise AssertionError("resume must never build an architect")

        service = ExecutionService(
            self.builder.root,
            worker_factory=lambda: worker,
            verifier_factory=lambda: verifier,
            architect_factory=exploding_architect_factory,
        )
        client = self._client(service)

        self._run_to_idle(service, client, "p-j3")

        self.assertEqual(worker.calls, 0)
        self.assertEqual(verifier.calls, 0)
        self.assertEqual(
            ProofScaffold(problem_dir / "scaffold.json").get("target").resolved_by_fact_id,
            fact.fact_id,
        )
        model = client.get("/api/problems/p-j3").json()
        self.assertEqual(model["status"], "SOLVED")
        self.assertEqual(model["target_fact"]["fact_id"], fact.fact_id)


if __name__ == "__main__":
    unittest.main()
