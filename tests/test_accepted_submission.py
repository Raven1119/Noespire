from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research.fact import CandidateFact
from research.graph import FactGraph
from research.pipeline import VerificationResult, submit_candidate


class AcceptingVerifier:
    def verify(self, problem, candidate, predecessors):
        return VerificationResult(accepted=True, reason="The arithmetic and proof are correct.")


class AcceptedSubmissionTests(unittest.TestCase):
    def test_accepted_candidate_enters_fact_graph(self) -> None:
        with TemporaryDirectory() as directory:
            graph = FactGraph(Path(directory))
            candidate = CandidateFact(statement="1 + 1 = 2", proof="Direct addition.", predecessors=())

            result = submit_candidate(
                graph=graph,
                problem_id="arithmetic",
                problem="Check elementary arithmetic.",
                author="codex-worker",
                candidate=candidate,
                verifier=AcceptingVerifier(),
            )

            self.assertTrue(result.verification.accepted)
            self.assertIsNotNone(result.fact)
            self.assertEqual(graph.get_fact(result.fact.fact_id), result.fact)


if __name__ == "__main__":
    unittest.main()
