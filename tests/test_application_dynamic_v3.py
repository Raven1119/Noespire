"""Proof Core v3 product wiring: execution, read model, HTTP, recovery.

Fresh problems (no root obligation, no scaffold.json, no proof_graph.json)
execute through the v3 dynamic core (``start_run`` once, ``resume_run``
afterwards); legacy and scaffold workspaces keep their paths. All execution
is real research-core code with a scripted Codex invoker injected through
``ExecutionService(dynamic_invoker_factory=...)`` — the core is never
patched.
"""

import json
from pathlib import Path
import threading
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from application.execution import ExecutionService
from application.http import create_app
from application.workspace_read_model import build_problem_list, build_read_model

from application_fixtures import WorkspaceBuilder, add_open_obligation, wait_for


STATEMENT = "For every integer n, n(n+1) is even."
LEMMA = "For every integer n, either n or n+1 is even."
EVEN_PRODUCT = "For any even integer a and integer b, ab is even."


class ScriptedV3:
    """Scripted closed-book Codex for the v3 seam (mirrors the core test).

    ``reject_direct``: the worker submits a flawed proof while no
    predecessor Facts exist (the verifier rejects it), driving route
    exhaustion. ``strategy``: "DECLINE" or "SPLIT" (the parity two-lemma
    decomposition). ``counterexample``: the worker answers the target with
    a counterexample candidate instead of a proof.
    """

    def __init__(self, *, reject_direct=False, strategy="DECLINE", counterexample=False):
        self.calls = []
        self.reject_direct = reject_direct
        self.strategy = strategy
        self.counterexample = counterexample

    def invoke(self, *, prompt, schema, label):
        self.calls.append(label)
        if label == "research_worker":
            packet = json.loads(prompt.split("Local packet:\n", 1)[1])
            goal = packet["obligation"]["statement"]
            facts = packet["predecessor_facts"]
            if self.counterexample:
                return {
                    "kind": "COUNTEREXAMPLE_CANDIDATE",
                    "statement": goal,
                    "proof": "",
                    "counterexample": "n = 0.5 falsifies the integrality reading.",
                    "reason": "",
                    "predecessors": [],
                }
            flawed = self.reject_direct and goal == STATEMENT and not facts
            return {
                "kind": "PROOF_CANDIDATE",
                "statement": goal,
                "proof": "missing argument"
                if flawed
                else "By parity of consecutive integers, an even factor makes the product even.",
                "counterexample": "",
                "reason": "",
                "predecessors": [f["fact_id"] for f in facts],
            }
        if label == "closed_book_verifier":
            return {
                "accepted": "missing argument" not in prompt,
                "external_authority_dependency": False,
                "violation_type": "NONE",
                "reason": "Elementary parity argument.",
            }
        if label == "refutation_verifier":
            return {
                "accepted": True,
                "assumptions_satisfied": True,
                "conclusion_falsified": True,
                "closed_book_clean": True,
                "reason": "The counterexample satisfies the context and falsifies the goal.",
            }
        if label == "strategy_sketcher":
            if self.strategy == "DECLINE":
                return {
                    "obstruction": "No viable decomposition.",
                    "evidence": ["Three rejected direct proofs."],
                    "mathematical_idea": "",
                    "why_this_reduces_difficulty": "",
                    "operator": "DECLINE",
                    "why_current_route_is_exhausted": "Repeated rejection.",
                    "decline_reason": "No useful local strategy.",
                    "candidate_claims": [],
                }
            return {
                "obstruction": "The consecutive-factor parity argument is missing.",
                "evidence": ["Rejected elementary proof."],
                "mathematical_idea": "Prove consecutive parity first.",
                "why_this_reduces_difficulty": "The child isolates a two-case parity statement.",
                "operator": "SPLIT",
                "why_current_route_is_exhausted": "Missing argument.",
                "decline_reason": "",
                "candidate_claims": [LEMMA, EVEN_PRODUCT],
            }
        if label == "n2s_sketch_audit":
            return {
                "strategy_class": "USEFUL_STRATEGY",
                "difficulty_reduction": "REAL_REDUCTION",
                "strategy_family": "parity",
                "reasons": ["Elementary local cases."],
            }
        if label == "boundary_aware_patch_builder":
            return {
                "compilation_decline": False,
                "decline_reason": "",
                "support_fact_ids": [],
                "new_nodes": [
                    {"node_id": "parity_cases", "goal": LEMMA, "depends_on": [], "premise_fact_ids": []},
                    {"node_id": "even_product", "goal": EVEN_PRODUCT, "depends_on": [], "premise_fact_ids": []},
                ],
            }
        if label == "n2t_fidelity_audit":
            return {
                "strategy_fidelity": "FAITHFUL",
                "operator_check": "OPERATOR_PRESERVED",
                "claim_fidelity": [{"claim": LEMMA, "status": "PRESERVED_AND_REFINED"}],
                "reasons": ["Same parity claim."],
            }
        if label == "structural_auditor":
            return {
                "verdict": "PASS",
                "reasons": ["The lemma supplies the missing argument."],
                "checks": {key: True for key in schema["properties"]["checks"]["properties"]},
            }
        if label == "closed_book_fact_audit":
            return {
                "mathematically_correct": True,
                "predecessor_sufficient": True,
                "closed_book_clean": True,
                "no_target_circularity": True,
                "classification": "SUBSTANTIVE",
                "reasons": ["Parity proof."],
            }
        raise AssertionError(label)


class BlockingV3(ScriptedV3):
    """Blocks inside the first worker call (concurrency seam)."""

    def __init__(self, started, release):
        super().__init__()
        self.started = started
        self.release = release
        self.entered = False

    def invoke(self, *, prompt, schema, label):
        if label == "research_worker" and not self.entered:
            self.entered = True
            self.started.set()
            if not self.release.wait(timeout=10):
                raise RuntimeError("test release timeout")
        return super().invoke(prompt=prompt, schema=schema, label=label)


class ProcessCrash(BaseException):
    pass


class CrashingV3(ScriptedV3):
    """Raises a BaseException inside the first worker call: a hard process
    crash mid-call, leaving a dangling write-ahead request."""

    def invoke(self, *, prompt, schema, label):
        if label == "research_worker":
            raise ProcessCrash()
        return super().invoke(prompt=prompt, schema=schema, label=label)


class DynamicV3WiringTests(unittest.TestCase):
    def setUp(self):
        self._tmp = TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.builder = WorkspaceBuilder(Path(self._tmp.name))

    def service(self, invoker, **kwargs):
        return ExecutionService(
            self.builder.root,
            dynamic_invoker_factory=lambda: invoker,
            **kwargs,
        )

    def client(self, service):
        return TestClient(create_app(self.builder.root, execution_service=service))

    def create_problem(self, client, statement=STATEMENT) -> str:
        response = client.post("/api/problems", json={"statement": statement})
        self.assertEqual(response.status_code, 201)
        return response.json()["problem_id"]

    def run_to_completion(self, client, service, problem_id):
        response = client.post(f"/api/problems/{problem_id}/attempts")
        self.assertEqual(response.status_code, 202)
        self.assertTrue(wait_for(lambda: not service.is_running(problem_id)))

    # -- fresh problem default + direct solve -------------------------------

    def test_fresh_problem_defaults_to_v3_and_solves(self):
        invoker = ScriptedV3()
        service = self.service(invoker)
        client = self.client(service)
        problem_id = self.create_problem(client)

        before = client.get(f"/api/problems/{problem_id}").json()
        self.assertEqual(before["execution_mode"], "DYNAMIC_PROOF_V3")
        self.assertEqual(before["status"], "OPEN")
        self.assertIsNone(before["dynamic"])
        self.assertIsNone(before["proof_graph"])
        self.assertEqual(before["attempts"], [])

        self.run_to_completion(client, service, problem_id)

        model = client.get(f"/api/problems/{problem_id}").json()
        self.assertEqual(model["status"], "SOLVED")
        self.assertEqual(model["execution_mode"], "DYNAMIC_PROOF_V3")
        self.assertEqual(model["dynamic"]["stop_reason"], "TARGET_SOLVED")
        self.assertEqual(model["dynamic"]["phase"], "STOPPED")
        self.assertIsNotNone(model["target_fact"])
        self.assertEqual(model["target_fact"]["statement"], STATEMENT)
        self.assertGreaterEqual(len(model["supporting_closure"]), 1)
        graph = model["proof_graph"]
        target = next(
            o for o in graph["obligations"] if o["obligation_id"] == graph["target_obligation_id"]
        )
        self.assertEqual(target["truth_state"], "DISCHARGED")
        self.assertEqual(target["resolved_fact_id"], model["target_fact"]["fact_id"])
        self.assertEqual(len(graph["routes"]), 1)
        self.assertEqual(graph["routes"][0]["kind"], "DIRECT")
        self.assertEqual(graph["frontiers"], [])
        self.assertEqual(len(model["attempts"]), 1)
        attempt = model["attempts"][0]
        self.assertEqual(attempt["outcome"], "FACT_ADMITTED")
        self.assertEqual(attempt["verdict"], "PASS")
        self.assertEqual(attempt["obligation_goal"], STATEMENT)
        self.assertEqual(attempt["fact_id"], model["target_fact"]["fact_id"])
        # Legacy-only keys stay null in v3 mode.
        self.assertIsNone(model["obligation"])
        self.assertIsNone(model["proof_structure"])
        # Solved runs reject further executions.
        retry = client.post(f"/api/problems/{problem_id}/attempts")
        self.assertEqual(retry.status_code, 409)
        self.assertEqual(retry.json()["error"], "already_solved")

    # -- route exhaustion + strategist decline → terminal stop ---------------

    def test_rejected_proofs_exhaust_route_then_decline_stops(self):
        invoker = ScriptedV3(reject_direct=True)
        service = self.service(invoker)
        client = self.client(service)
        problem_id = self.create_problem(client)
        self.run_to_completion(client, service, problem_id)

        model = client.get(f"/api/problems/{problem_id}").json()
        self.assertEqual(model["status"], "OPEN")
        self.assertEqual(model["dynamic"]["stop_reason"], "STRATEGIST_DECLINE")
        route = model["proof_graph"]["routes"][0]
        self.assertEqual(route["derived_state"], "EXHAUSTED")
        self.assertEqual(route["lifecycle"], "EXHAUSTED")
        self.assertTrue(route["exhaustion_reason"])
        self.assertEqual(len(model["attempts"]), 3)
        self.assertTrue(
            all(a["outcome"] == "PROOF_REJECTED" for a in model["attempts"])
        )
        self.assertTrue(
            all(a["failure_class"] == "rejection" for a in model["attempts"])
        )
        # A terminally stopped run cannot be retried (core contract).
        retry = client.post(f"/api/problems/{problem_id}/attempts")
        self.assertEqual(retry.status_code, 409)
        self.assertEqual(retry.json()["error"], "run_stopped")
        self.assertEqual(retry.json()["stop_reason"], "STRATEGIST_DECLINE")

    # -- SPLIT patch → multi-node solve --------------------------------------

    def test_split_patch_produces_multi_node_proof(self):
        invoker = ScriptedV3(reject_direct=True, strategy="SPLIT")
        service = self.service(invoker)
        client = self.client(service)
        problem_id = self.create_problem(client)
        self.run_to_completion(client, service, problem_id)

        model = client.get(f"/api/problems/{problem_id}").json()
        self.assertEqual(model["status"], "SOLVED")
        self.assertEqual(len(model["supporting_closure"]), 3)
        graph = model["proof_graph"]
        self.assertEqual(len(graph["obligations"]), 3)
        kinds = sorted(route["kind"] for route in graph["routes"])
        self.assertIn("SPLIT", kinds)
        self.assertIn("DIRECT", kinds)
        discharged = [
            o for o in graph["obligations"] if o["truth_state"] == "DISCHARGED"
        ]
        self.assertEqual(len(discharged), 3)
        # Refinement history: one applied SPLIT patch with its child goals.
        self.assertEqual(len(model["patches"]), 1)
        patch = model["patches"][0]
        self.assertEqual(patch["operator"], "SPLIT")
        self.assertEqual(
            patch["target_obligation_id"], graph["target_obligation_id"]
        )
        self.assertEqual(sorted(patch["obligation_goals"]), sorted([LEMMA, EVEN_PRODUCT]))
        self.assertEqual(patch["step"], 1)
        # Per-node attempts: 3 rejected direct + 2 lemmas + 1 target.
        outcomes = sorted(a["outcome"] for a in model["attempts"])
        self.assertEqual(outcomes.count("PROOF_REJECTED"), 3)
        self.assertEqual(outcomes.count("FACT_ADMITTED"), 3)
        for route in graph["routes"]:
            self.assertIn(
                route["derived_state"], ("READY", "WAITING", "IMPOSSIBLE", "EXHAUSTED")
            )

    # -- counterexample refutation -------------------------------------------

    def test_counterexample_refutes_target(self):
        invoker = ScriptedV3(counterexample=True)
        service = self.service(invoker)
        client = self.client(service)
        problem_id = self.create_problem(client)
        self.run_to_completion(client, service, problem_id)

        model = client.get(f"/api/problems/{problem_id}").json()
        self.assertEqual(model["status"], "OPEN")  # refuted is not solved
        self.assertEqual(model["dynamic"]["stop_reason"], "TARGET_REFUTED")
        target = next(
            o
            for o in model["proof_graph"]["obligations"]
            if o["obligation_id"] == model["proof_graph"]["target_obligation_id"]
        )
        self.assertEqual(target["truth_state"], "REFUTED")
        self.assertEqual(len(model["refutations"]), 1)
        refutation = model["refutations"][0]
        self.assertEqual(refutation["refutation_id"], target["refutation_id"])
        self.assertTrue(refutation["counterexample"])
        self.assertEqual(model["attempts"][0]["outcome"], "REFUTATION_ADMITTED")
        retry = client.post(f"/api/problems/{problem_id}/attempts")
        self.assertEqual(retry.status_code, 409)
        self.assertEqual(retry.json()["error"], "run_stopped")

    # -- concurrency ----------------------------------------------------------

    def test_concurrent_double_start_exactly_one_execution(self):
        started = threading.Event()
        release = threading.Event()
        self.addCleanup(release.set)
        invoker = BlockingV3(started, release)
        service = self.service(invoker)
        client = self.client(service)
        problem_id = self.create_problem(client)

        first = client.post(f"/api/problems/{problem_id}/attempts")
        self.assertEqual(first.status_code, 202)
        self.assertTrue(started.wait(timeout=10))
        second = client.post(f"/api/problems/{problem_id}/attempts")
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["error"], "already_running")
        # While blocked: the run is live and the current attempt is visible.
        model = client.get(f"/api/problems/{problem_id}").json()
        self.assertEqual(model["status"], "RUNNING")
        self.assertEqual(model["dynamic"]["phase"], "SOLVE")
        self.assertIsNotNone(model["live"]["current_attempt_id"])
        release.set()
        self.assertTrue(wait_for(lambda: not service.is_running(problem_id)))
        self.assertEqual(
            client.get(f"/api/problems/{problem_id}").json()["status"], "SOLVED"
        )

    # -- crash → restart → resume (conservative interruption) -----------------

    def test_crash_restart_resume_preserves_state_without_duplicate_calls(self):
        service = self.service(CrashingV3())
        client = self.client(service)
        problem_id = self.create_problem(client)
        response = client.post(f"/api/problems/{problem_id}/attempts")
        self.assertEqual(response.status_code, 202)
        self.assertTrue(wait_for(lambda: not service.is_running(problem_id)))

        # The crashed run persists mid-phase; nothing was rewritten.
        model = client.get(f"/api/problems/{problem_id}").json()
        self.assertEqual(model["status"], "OPEN")  # not live, not solved
        self.assertEqual(model["dynamic"]["phase"], "SOLVE")
        self.assertIsNone(model["dynamic"]["stop_reason"])
        self.assertEqual(model["attempts"][0]["outcome"], "RUNNING")

        # Process restart: a fresh service over the same workspaces. Startup
        # recovery must skip v3 workspaces without touching core evidence.
        before_attempt = (
            self.builder.root / problem_id / "attempts" / "attempt-000001.json"
        ).read_text(encoding="utf-8")
        invoker2 = ScriptedV3()
        service2 = self.service(invoker2)
        service2.recover_stale_running()
        after_attempt = (
            self.builder.root / problem_id / "attempts" / "attempt-000001.json"
        ).read_text(encoding="utf-8")
        self.assertEqual(before_attempt, after_attempt)

        # Resume: the dangling request is conservatively interrupted by the
        # core; no model call is duplicated.
        client2 = self.client(service2)
        response = client2.post(f"/api/problems/{problem_id}/attempts")
        self.assertEqual(response.status_code, 202)
        self.assertTrue(wait_for(lambda: not service2.is_running(problem_id)))
        self.assertEqual(invoker2.calls, [])
        model = client2.get(f"/api/problems/{problem_id}").json()
        self.assertEqual(model["dynamic"]["stop_reason"], "INTERRUPTED")
        self.assertEqual(model["attempts"][0]["outcome"], "INTERRUPTED")
        self.assertEqual(model["attempts"][0]["failure_class"], "interrupted")

        # The run is now terminally stopped.
        retry = client2.post(f"/api/problems/{problem_id}/attempts")
        self.assertEqual(retry.status_code, 409)
        self.assertEqual(retry.json()["error"], "run_stopped")

    # -- old modes unaffected --------------------------------------------------

    def test_legacy_root_workspace_still_legacy(self):
        problem_dir = self.builder.add_problem("legacy-1", "Legacy statement.")
        add_open_obligation(problem_dir, "legacy-1", "Legacy statement.")
        model = build_read_model(self.builder.root, "legacy-1")
        self.assertEqual(model["execution_mode"], "LEGACY_DIRECT")
        self.assertIsNone(model["dynamic"])
        self.assertIsNone(model["proof_graph"])
        summaries = build_problem_list(self.builder.root)
        self.assertEqual(summaries[0]["status"], "OPEN")


if __name__ == "__main__":
    unittest.main()
