from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research.fact import CandidateFact
from research.graph import FactGraph
from research.pipeline import VerificationResult, submit_candidate


class RejectingVerifier:
    def verify(self, problem, candidate, predecessors):
        return VerificationResult(accepted=False, reason="The arithmetic is false.")


class RejectedSubmissionTests(unittest.TestCase):
    def test_rejected_candidate_does_not_enter_fact_graph(self) -> None:
        with TemporaryDirectory() as directory:
            graph = FactGraph(Path(directory))
            candidate = CandidateFact(statement="1 + 1 = 3", proof="Incorrect.", predecessors=())

            result = submit_candidate(
                graph=graph,
                problem_id="arithmetic",
                problem="Check elementary arithmetic.",
                author="codex-worker",
                candidate=candidate,
                verifier=RejectingVerifier(),
            )

            self.assertFalse(result.verification.accepted)
            self.assertIsNone(result.fact)
            self.assertEqual(graph.list_facts(), [])


if __name__ == "__main__":
    unittest.main()
