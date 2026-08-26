import unittest

from research.agents import ResearchWorker
from research.fact import CandidateFact, Fact


class StaticCodex:
    def __init__(self) -> None:
        self.prompt = ""

    def invoke(self, *, prompt, schema, label):
        self.prompt = prompt
        return {
            "statement": "1 + 3 + 5 = 9.",
            "proof": "From the accepted fact 1 + 3 = 4, add 5 to get 9.",
            "predecessors": ["prior-id"],
        }


class WorkerContractTests(unittest.TestCase):
    def test_worker_consumes_problem_facts_and_subgoal_and_returns_candidate(self) -> None:
        runner = StaticCodex()
        worker = ResearchWorker(runner)
        prior = Fact(
            fact_id="prior-id",
            problem_id="odd-sum",
            author="worker",
            statement="1 + 3 = 4.",
            proof="Direct addition.",
            predecessors=(),
        )

        candidate = worker.propose(
            problem="Prove that the first four positive odd integers sum to 16.",
            existing_facts=[prior],
            subgoal="Extend the accepted sum by adding 5.",
        )

        self.assertEqual(
            candidate,
            CandidateFact(
                statement="1 + 3 + 5 = 9.",
                proof="From the accepted fact 1 + 3 = 4, add 5 to get 9.",
                predecessors=("prior-id",),
            ),
        )
        self.assertIn("first four positive odd integers", runner.prompt)
        self.assertIn("prior-id", runner.prompt)
        self.assertIn("adding 5", runner.prompt)


if __name__ == "__main__":
    unittest.main()
