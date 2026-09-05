"""N1.14P — workspace read model projection for scaffold-mode workspaces.

Additive fields only: ``execution_mode``, ``proof_structure``,
``last_execution_failure``, and per-attempt ``obligation_id`` /
``scaffold_node_id``. Legacy workspaces keep every previously existing key
and semantic unchanged; a corrupt scaffold.json fails closed (raises) rather
than silently falling back to the legacy projection.
"""

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from application.execution import ExecutionService
from application.workspace_read_model import build_problem_list, build_read_model

from research.obligation import ObligationStatus
from research.problem import ProblemSpec
from research.scaffold import ProofScaffold, ScaffoldNode
from research.scaffold_architect import ScaffoldProposal, ScaffoldProposalNode

from application_fixtures import (
    GoalEchoWorker,
    RejectingVerifier,
    StubArchitect,
    WorkspaceBuilder,
    append_log,
    registry_for,
    run_attempt,
    wait_for,
)


def linear_proposal(statement: str) -> ScaffoldProposal:
    return ScaffoldProposal(
        nodes=(
            ScaffoldProposalNode("lemma1", "Lemma one.", (), ()),
            ScaffoldProposalNode("lemma2", "Lemma two.", ("lemma1",), ()),
            ScaffoldProposalNode("target", statement, ("lemma2",), ()),
        ),
        target_node_id="target",
    )


def materialize_linear_scaffold(problem_dir: Path, problem_id: str, statement: str) -> ProofScaffold:
    return ProofScaffold.create(
        problem_dir / "scaffold.json",
        problem=ProblemSpec(problem_id, statement),
        target_node_id="target",
        nodes=(
            ScaffoldNode("lemma1", "Lemma one."),
            ScaffoldNode("lemma2", "Lemma two.", depends_on=("lemma1",)),
            ScaffoldNode("target", statement, depends_on=("lemma2",)),
        ),
    )


class ScaffoldReadModelTestBase(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.builder = WorkspaceBuilder(Path(self.temporary.name))

    def _run(self, problem_id: str, verifier: RejectingVerifier) -> None:
        service = ExecutionService(
            self.builder.root,
            worker_factory=lambda: GoalEchoWorker(),
            verifier_factory=lambda: verifier,
            architect_factory=lambda: StubArchitect(
                [linear_proposal(self.statement)]
            ),
        )
        service.start_attempt(problem_id)
        assert wait_for(lambda: not service.is_running(problem_id))


class PlannedScaffoldTests(ScaffoldReadModelTestBase):
    def test_materialized_scaffold_with_no_runs_projects_planned_structure(self) -> None:
        problem_dir = self.builder.add_problem("p-plan", "Target theorem P.")
        materialize_linear_scaffold(problem_dir, "p-plan", "Target theorem P.")

        model = build_read_model(self.builder.root, "p-plan")

        self.assertEqual(model["execution_mode"], "STATIC_SCAFFOLD")
        self.assertEqual(model["status"], "OPEN")
        self.assertEqual(model["display_status"], "OPEN")
        self.assertIsNone(model["obligation"])
        self.assertEqual(model["attempts"], [])
        self.assertIsNone(model["target_fact"])
        self.assertEqual(model["supporting_closure"], [])
        self.assertIsNone(model["last_execution_failure"])

        structure = model["proof_structure"]
        self.assertEqual(structure["target_node_id"], "target")
        nodes = {node["node_id"]: node for node in structure["nodes"]}
        self.assertEqual(set(nodes), {"lemma1", "lemma2", "target"})
        self.assertEqual(nodes["lemma1"]["statement"], "Lemma one.")
        self.assertEqual(nodes["lemma1"]["dependency_node_ids"], [])
        self.assertEqual(nodes["lemma2"]["dependency_node_ids"], ["lemma1"])
        self.assertEqual(nodes["target"]["dependency_node_ids"], ["lemma2"])
        for node in nodes.values():
            self.assertIsNone(node["resolved_fact_id"])
            self.assertIsNone(node["latest_attempt_id"])
        # lemma1 has no dependencies -> READY; the rest wait on theirs.
        self.assertEqual(nodes["lemma1"]["state"], "READY")
        self.assertEqual(nodes["lemma2"]["state"], "PLANNED")
        self.assertEqual(nodes["target"]["state"], "PLANNED")

    def test_scaffold_without_obligations_does_not_crash(self) -> None:
        problem_dir = self.builder.add_problem("p-empty", "Target theorem E.")
        materialize_linear_scaffold(problem_dir, "p-empty", "Target theorem E.")

        model = build_read_model(self.builder.root, "p-empty")

        self.assertEqual(model["status"], "OPEN")
        self.assertEqual(model["attempts"], [])
        summary = next(
            item for item in build_problem_list(self.builder.root)
            if item["problem_id"] == "p-empty"
        )
        self.assertEqual(summary["status"], "OPEN")
        self.assertEqual(summary["attempt_count"], 0)


class PartiallyVerifiedScaffoldTests(ScaffoldReadModelTestBase):
    statement = "Target theorem V."

    def test_blocked_run_projects_verified_blocked_planned_and_attribution(self) -> None:
        self.builder.add_problem("p-part", self.statement)
        self._run("p-part", RejectingVerifier({"Lemma two."}))

        model = build_read_model(self.builder.root, "p-part")

        self.assertEqual(model["status"], "OPEN")
        nodes = {node["node_id"]: node for node in model["proof_structure"]["nodes"]}
        self.assertEqual(nodes["lemma1"]["state"], "VERIFIED")
        self.assertIsNotNone(nodes["lemma1"]["resolved_fact_id"])
        self.assertEqual(nodes["lemma1"]["latest_attempt_id"], "attempt-000001")
        self.assertEqual(nodes["lemma2"]["state"], "BLOCKED")
        self.assertIsNone(nodes["lemma2"]["resolved_fact_id"])
        # Product default max_attempts_per_obligation=3: lemma2's latest
        # attempt is its third repair round.
        self.assertEqual(nodes["lemma2"]["latest_attempt_id"], "attempt-000004")
        self.assertEqual(nodes["target"]["state"], "PLANNED")
        self.assertIsNone(nodes["target"]["latest_attempt_id"])

        attempts = {a["scaffold_node_id"]: a for a in model["attempts"]}
        self.assertEqual(set(attempts), {"lemma1", "lemma2"})
        self.assertEqual(attempts["lemma1"]["verdict"], "PASS")
        self.assertEqual(attempts["lemma1"]["failure_class"], None)
        self.assertEqual(attempts["lemma1"]["obligation_id"], "scaffold:p-part:lemma1")
        self.assertEqual(attempts["lemma2"]["verdict"], "FAIL")
        self.assertEqual(attempts["lemma2"]["failure_class"], "rejection")
        self.assertEqual(attempts["lemma2"]["obligation_id"], "scaffold:p-part:lemma2")

        summary = next(
            item for item in build_problem_list(self.builder.root)
            if item["problem_id"] == "p-part"
        )
        self.assertEqual(summary["status"], "OPEN")
        self.assertEqual(summary["attempt_count"], 4)


class SolvedScaffoldTests(ScaffoldReadModelTestBase):
    statement = "Target theorem S."

    def test_solved_scaffold_projects_all_verified_and_multi_fact_closure(self) -> None:
        self.builder.add_problem("p-sol", self.statement)
        self._run("p-sol", RejectingVerifier())

        model = build_read_model(self.builder.root, "p-sol")

        self.assertEqual(model["status"], "SOLVED")
        self.assertEqual(model["display_status"], "SOLVED")
        self.assertEqual(model["target_fact"]["statement"], self.statement)
        self.assertEqual(len(model["supporting_closure"]), 3)
        nodes = {node["node_id"]: node for node in model["proof_structure"]["nodes"]}
        for node_id in ("lemma1", "lemma2", "target"):
            self.assertEqual(nodes[node_id]["state"], "VERIFIED")
            self.assertIsNotNone(nodes[node_id]["resolved_fact_id"])
        self.assertEqual(
            nodes["target"]["resolved_fact_id"], model["target_fact"]["fact_id"]
        )
        summary = next(
            item for item in build_problem_list(self.builder.root)
            if item["problem_id"] == "p-sol"
        )
        self.assertEqual(summary["status"], "SOLVED")


class LegacyCompatibilityTests(ScaffoldReadModelTestBase):
    """Legacy workspaces: every previously existing key/semantic unchanged;
    the additive fields take their legacy values."""

    def test_legacy_solved_workspace_payload_is_unchanged_plus_additive_fields(self) -> None:
        problem_dir = self.builder.add_problem("p-leg", "Legacy theorem L.")
        result = run_attempt(problem_dir, "p-leg", "Legacy theorem L.", accepted=True)

        model = build_read_model(self.builder.root, "p-leg")

        self.assertEqual(model["execution_mode"], "LEGACY_DIRECT")
        self.assertIsNone(model["proof_structure"])
        self.assertIsNone(model["last_execution_failure"])
        self.assertEqual(model["status"], "SOLVED")
        self.assertEqual(model["obligation"]["obligation_id"], "root:p-leg")
        self.assertEqual(model["obligation"]["status"], "DISCHARGED")
        self.assertEqual(model["obligation"]["resolved_by_fact_id"], result.target_fact_id)
        self.assertEqual(model["target_fact"]["fact_id"], result.target_fact_id)
        (attempt,) = model["attempts"]
        self.assertEqual(attempt["obligation_id"], "root:p-leg")
        self.assertIsNone(attempt["scaffold_node_id"])
        self.assertEqual(attempt["verdict"], "PASS")

    def test_legacy_pre_attempt_runtime_failure_is_surfaced(self) -> None:
        """Today-invisible pre-attempt failures (attempt_id null) surface via
        last_execution_failure — additive honesty improvement."""
        problem_dir = self.builder.add_problem("p-pre", "Legacy theorem P.")
        run_attempt(problem_dir, "p-pre", "Legacy theorem P.", accepted=False)
        append_log(
            problem_dir,
            {"kind": "ATTEMPT_FINISHED", "execution_id": "exec-x", "problem_id": "p-pre",
             "attempt_id": None, "started_at": "t0", "finished_at": "t1",
             "outcome_stage": "RUNTIME_ERROR", "verifier_called": False,
             "error": "IsolationUnavailableError: docker daemon is unavailable"},
        )

        model = build_read_model(self.builder.root, "p-pre")

        failure = model["last_execution_failure"]
        self.assertEqual(failure["outcome_stage"], "RUNTIME_ERROR")
        self.assertEqual(
            failure["error"], "IsolationUnavailableError: docker daemon is unavailable"
        )
        self.assertEqual(failure["finished_at"], "t1")

    def test_per_attempt_finish_does_not_surface_as_execution_failure(self) -> None:
        problem_dir = self.builder.add_problem("p-per", "Legacy theorem Q.")
        result = run_attempt(problem_dir, "p-per", "Legacy theorem Q.", accepted=False)
        append_log(
            problem_dir,
            {"kind": "ATTEMPT_FINISHED", "execution_id": "exec-y", "problem_id": "p-per",
             "attempt_id": result.attempt_id, "started_at": "t0", "finished_at": "t1",
             "outcome_stage": "FRESH_VERIFIER_REJECT", "verifier_called": True},
        )

        model = build_read_model(self.builder.root, "p-per")

        self.assertIsNone(model["last_execution_failure"])


class CorruptScaffoldTests(ScaffoldReadModelTestBase):
    def test_corrupt_scaffold_json_fails_closed(self) -> None:
        problem_dir = self.builder.add_problem("p-corrupt", "Target theorem Z.")
        (problem_dir / "scaffold.json").write_text("{ not json", encoding="utf-8")

        with self.assertRaises(Exception):
            build_read_model(self.builder.root, "p-corrupt")

    def test_scaffold_resolution_missing_fact_is_corruption(self) -> None:
        problem_dir = self.builder.add_problem("p-dangle", "Target theorem D.")
        scaffold = materialize_linear_scaffold(problem_dir, "p-dangle", "Target theorem D.")
        # Hand-tamper: claim a resolved target whose Fact does not exist.
        payload = json.loads((problem_dir / "scaffold.json").read_text(encoding="utf-8"))
        for node in payload["nodes"]:
            if node["node_id"] == "target":
                node["resolved_by_fact_id"] = "missing-fact"
        (problem_dir / "scaffold.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
        self.assertIsNone(scaffold.get("target").resolved_by_fact_id)  # pre-tamper load

        with self.assertRaises(Exception):
            build_read_model(self.builder.root, "p-dangle")


if __name__ == "__main__":
    unittest.main()
