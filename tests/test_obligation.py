from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research.fact import CandidateFact, Fact
from research.graph import FactGraph
from research.obligation import ObligationRegistry, ObligationStatus, ProofObligation, Route
from research.obligation_execution import execute_obligation
from research.pipeline import VerificationResult


class ScriptedWorker:
    def __init__(self, candidate: CandidateFact) -> None:
        self.candidate = candidate
        self.received_facts = []
        self.received_goal = ""
        self.calls = 0

    def propose(self, *, problem, existing_facts, subgoal):
        self.calls += 1
        self.received_facts = list(existing_facts)
        self.received_goal = subgoal
        return self.candidate


class ObservingVerifier:
    def __init__(self, graph: FactGraph, accepted: bool) -> None:
        self.graph = graph
        self.accepted = accepted
        self.fact_ids_during_verification = []
        self.calls = 0

    def verify(self, problem, candidate, predecessors):
        self.calls += 1
        self.fact_ids_during_verification = [fact.fact_id for fact in self.graph.list_facts()]
        return VerificationResult(self.accepted, "scripted verdict")


class ProofObligationTests(unittest.TestCase):
    def _execute_verifier_failure(self, root: Path):
        graph = FactGraph(root / "truth")
        premise = graph.add_fact(
            Fact.create(problem_id="p", author="worker", statement="F1", proof="Proof F1.")
        )
        before = graph.list_facts()
        registry = ObligationRegistry(root / "obligations.json")
        registry.add(ProofObligation("o-target", (premise.fact_id,), "Target T", "route-a"))
        result = execute_obligation(
            registry=registry,
            obligation_id="o-target",
            graph=graph,
            problem_id="p",
            problem="Prove Target T.",
            author="worker",
            worker=ScriptedWorker(
                CandidateFact("Target T", "An invalid proof.", (premise.fact_id,))
            ),
            verifier=ObservingVerifier(graph, accepted=False),
        )
        return graph, registry, before, result

    def test_open_obligation_is_not_fact(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            graph = FactGraph(root / "truth")
            registry = ObligationRegistry(root / "obligations.json")

            obligation = ProofObligation(
                obligation_id="o-target",
                premises=(),
                goal="Target T",
                route_id="route-a",
            )
            registry.add(obligation)

            self.assertEqual(registry.get("o-target"), obligation)
            self.assertEqual(graph.list_facts(), [])

    def test_or_routes_remain_distinct_alternatives(self) -> None:
        with TemporaryDirectory() as directory:
            registry = ObligationRegistry(Path(directory) / "obligations.json")
            first = ProofObligation("o-a", ("fact-1",), "Target T", "route-a")
            second = ProofObligation("o-b", ("fact-2",), "Target T", "route-b")
            route_a = Route("route-a", (first.obligation_id,))
            route_b = Route("route-b", (second.obligation_id,))

            registry.add(first)
            registry.add(second)

            self.assertEqual(route_a.obligation_ids, ("o-a",))
            self.assertEqual(route_b.obligation_ids, ("o-b",))
            self.assertEqual(
                [(item.premises, item.route_id) for item in registry.list()],
                [(("fact-1",), "route-a"), (("fact-2",), "route-b")],
            )

    def test_obligation_registry_round_trip(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "obligations.json"
            graph = FactGraph(root / "truth")
            admitted = graph.add_fact(
                Fact.create(
                    problem_id="p",
                    author="verified-worker",
                    statement="Target T",
                    proof="A complete proof of T.",
                )
            )
            registry = ObligationRegistry(path)
            registry.add(ProofObligation("o-target", (), "Target T", "route-a"))
            registry.transition("o-target", ObligationStatus.RUNNING)
            registry.resolve("o-target", admitted.fact_id, graph)

            reloaded = ObligationRegistry(path)
            obligation = reloaded.get("o-target")

            self.assertEqual(obligation.status, ObligationStatus.DISCHARGED)
            self.assertEqual(obligation.resolved_by_fact_id, admitted.fact_id)
            self.assertEqual(obligation.route_id, "route-a")

    def test_candidate_before_verification_is_not_fact(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            graph = FactGraph(root / "truth")
            premise = graph.add_fact(
                Fact.create(problem_id="p", author="worker", statement="F1", proof="Proof F1.")
            )
            registry = ObligationRegistry(root / "obligations.json")
            registry.add(ProofObligation("o-target", (premise.fact_id,), "Target T", "route-a"))
            worker = ScriptedWorker(
                CandidateFact("Target T", "F1 proves Target T.", (premise.fact_id,))
            )
            verifier = ObservingVerifier(graph, accepted=True)

            execute_obligation(
                registry=registry,
                obligation_id="o-target",
                graph=graph,
                problem_id="p",
                problem="Prove Target T.",
                author="worker",
                worker=worker,
                verifier=verifier,
            )

            self.assertEqual(verifier.fact_ids_during_verification, [premise.fact_id])

    def test_verifier_failure_does_not_mutate_fact_graph(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            graph, registry, before, result = self._execute_verifier_failure(root)

            self.assertFalse(result.verification.accepted)
            self.assertIsNone(result.fact)
            self.assertEqual(graph.list_facts(), before)
            self.assertEqual(registry.get("o-target").status, ObligationStatus.OPEN)

    def test_verifier_failure_returns_obligation_to_open(self) -> None:
        with TemporaryDirectory() as directory:
            _, registry, _, result = self._execute_verifier_failure(Path(directory))

            self.assertEqual(result.obligation.status, ObligationStatus.OPEN)
            self.assertEqual(registry.get("o-target").status, ObligationStatus.OPEN)

    def test_verifier_failure_keeps_resolved_fact_id_null(self) -> None:
        with TemporaryDirectory() as directory:
            _, registry, _, result = self._execute_verifier_failure(Path(directory))

            self.assertIsNone(result.obligation.resolved_by_fact_id)
            self.assertIsNone(registry.get("o-target").resolved_by_fact_id)

    def test_failed_attempt_can_be_retried_and_discharged(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            graph = FactGraph(root / "truth")
            registry = ObligationRegistry(root / "obligations.json")
            registry.add(ProofObligation("o-target", (), "Target T", "route-a"))

            first = execute_obligation(
                registry=registry,
                obligation_id="o-target",
                graph=graph,
                problem_id="p",
                problem="Prove Target T.",
                author="worker",
                worker=ScriptedWorker(CandidateFact("Target T", "Candidate A.", ())),
                verifier=ObservingVerifier(graph, accepted=False),
            )

            self.assertEqual(first.obligation.status, ObligationStatus.OPEN)
            self.assertIsNone(first.obligation.resolved_by_fact_id)
            self.assertEqual(graph.list_facts(), [])

            second = execute_obligation(
                registry=registry,
                obligation_id="o-target",
                graph=graph,
                problem_id="p",
                problem="Prove Target T.",
                author="worker",
                worker=ScriptedWorker(CandidateFact("Target T", "Candidate B.", ())),
                verifier=ObservingVerifier(graph, accepted=True),
            )

            self.assertEqual(second.obligation.status, ObligationStatus.DISCHARGED)
            self.assertIsNotNone(second.fact)
            self.assertEqual(second.obligation.resolved_by_fact_id, second.fact.fact_id)
            self.assertEqual(graph.list_facts(), [second.fact])

    def test_verifier_pass_materializes_fact(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            graph = FactGraph(root / "truth")
            registry = ObligationRegistry(root / "obligations.json")
            registry.add(ProofObligation("o-target", (), "Target T", "route-a"))

            result = execute_obligation(
                registry=registry,
                obligation_id="o-target",
                graph=graph,
                problem_id="p",
                problem="Prove Target T.",
                author="worker",
                worker=ScriptedWorker(CandidateFact("Target T", "A complete proof.", ())),
                verifier=ObservingVerifier(graph, accepted=True),
            )

            self.assertIsNotNone(result.fact)
            self.assertEqual(graph.list_facts(), [result.fact])

    def test_pass_discharges_obligation(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            graph = FactGraph(root / "truth")
            registry = ObligationRegistry(root / "obligations.json")
            registry.add(ProofObligation("o-target", (), "Target T", "route-a"))

            execute_obligation(
                registry=registry,
                obligation_id="o-target",
                graph=graph,
                problem_id="p",
                problem="Prove Target T.",
                author="worker",
                worker=ScriptedWorker(CandidateFact("Target T", "A complete proof.", ())),
                verifier=ObservingVerifier(graph, accepted=True),
            )

            self.assertEqual(registry.get("o-target").status, ObligationStatus.DISCHARGED)

    def test_resolved_fact_id_matches_admitted_fact(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            graph = FactGraph(root / "truth")
            registry = ObligationRegistry(root / "obligations.json")
            registry.add(ProofObligation("o-target", (), "Target T", "route-a"))

            result = execute_obligation(
                registry=registry,
                obligation_id="o-target",
                graph=graph,
                problem_id="p",
                problem="Prove Target T.",
                author="worker",
                worker=ScriptedWorker(CandidateFact("Target T", "A complete proof.", ())),
                verifier=ObservingVerifier(graph, accepted=True),
            )

            self.assertEqual(
                registry.get("o-target").resolved_by_fact_id,
                result.fact.fact_id,
            )

    def test_retry_does_not_duplicate_content_addressed_fact(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            graph = FactGraph(root / "truth")
            registry = ObligationRegistry(root / "obligations.json")
            registry.add(ProofObligation("o-target", (), "Target T", "route-a"))
            worker = ScriptedWorker(CandidateFact("Target T", "A complete proof.", ()))
            verifier = ObservingVerifier(graph, accepted=True)
            arguments = {
                "registry": registry,
                "obligation_id": "o-target",
                "graph": graph,
                "problem_id": "p",
                "problem": "Prove Target T.",
                "author": "worker",
                "worker": worker,
                "verifier": verifier,
            }

            first = execute_obligation(**arguments)
            second = execute_obligation(**arguments)

            self.assertEqual(second.fact, first.fact)
            self.assertFalse(second.executed)
            self.assertEqual(worker.calls, 1)
            self.assertEqual(verifier.calls, 1)
            self.assertEqual(graph.list_facts(), [first.fact])

    def test_and_obligation_preserves_all_premises(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            graph = FactGraph(root / "truth")
            premises = tuple(
                graph.add_fact(
                    Fact.create(
                        problem_id="p",
                        author="worker",
                        statement=name,
                        proof=f"Proof {name}.",
                    )
                ).fact_id
                for name in ("F1", "F2", "F3")
            )
            obligation = ProofObligation("o-target", premises, "Target T", "route-a")
            registry = ObligationRegistry(root / "obligations.json")
            registry.add(obligation)
            worker = ScriptedWorker(
                CandidateFact(
                    "Target T",
                    "The conjunction of F1, F2, and F3 proves T.",
                    obligation.premises,
                )
            )

            result = execute_obligation(
                registry=registry,
                obligation_id="o-target",
                graph=graph,
                problem_id="p",
                problem="Prove Target T.",
                author="worker",
                worker=worker,
                verifier=ObservingVerifier(graph, accepted=True),
            )

            self.assertEqual(
                tuple(fact.fact_id for fact in worker.received_facts),
                obligation.premises,
            )
            self.assertIn("Use every provided accepted Fact", worker.received_goal)
            self.assertIn("Target T", worker.received_goal)
            self.assertEqual(result.fact.predecessors, obligation.premises)

    def test_deterministic_two_premise_pass_control(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            graph = FactGraph(root / "truth")
            accepted = [
                graph.add_fact(
                    Fact.create(problem_id="p", author="worker", statement=name, proof=f"Proof {name}.")
                )
                for name in ("F1", "F2")
            ]
            obligation = ProofObligation(
                "o-target",
                tuple(fact.fact_id for fact in accepted),
                "Target T",
                "route-a",
            )
            registry = ObligationRegistry(root / "obligations.json")
            registry.add(obligation)

            result = execute_obligation(
                registry=registry,
                obligation_id="o-target",
                graph=graph,
                problem_id="p",
                problem="Prove Target T.",
                author="worker",
                worker=ScriptedWorker(
                    CandidateFact("Target T", "F1 and F2 jointly prove T.", obligation.premises)
                ),
                verifier=ObservingVerifier(graph, accepted=True),
            )

            self.assertTrue(result.verification.accepted)
            self.assertEqual(result.fact.predecessors, obligation.premises)
            self.assertEqual(result.obligation.status, ObligationStatus.DISCHARGED)

    def test_deterministic_two_premise_fail_control(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            graph = FactGraph(root / "truth")
            accepted = [
                graph.add_fact(
                    Fact.create(problem_id="p", author="worker", statement=name, proof=f"Proof {name}.")
                )
                for name in ("F1", "F2")
            ]
            before = graph.list_facts()
            obligation = ProofObligation(
                "o-target",
                tuple(fact.fact_id for fact in accepted),
                "Target T",
                "route-a",
            )
            registry = ObligationRegistry(root / "obligations.json")
            registry.add(obligation)

            result = execute_obligation(
                registry=registry,
                obligation_id="o-target",
                graph=graph,
                problem_id="p",
                problem="Prove Target T.",
                author="worker",
                worker=ScriptedWorker(
                    CandidateFact("Target T", "An invalid proof.", obligation.premises)
                ),
                verifier=ObservingVerifier(graph, accepted=False),
            )

            self.assertFalse(result.verification.accepted)
            self.assertEqual(graph.list_facts(), before)
            self.assertEqual(result.obligation.status, ObligationStatus.OPEN)


if __name__ == "__main__":
    unittest.main()
