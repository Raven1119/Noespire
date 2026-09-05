import unittest

from research.agents import ResearchWorker
from research.fact import CandidateFact, Fact
from research.pipeline import RepairContext


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

    def test_base_prompt_carries_the_danus_reasoning_policy(self) -> None:
        runner = StaticCodex()
        worker = ResearchWorker(runner)

        worker.propose(problem="Prove T.", existing_facts=[], subgoal="Goal:\nT.")

        self.assertIn("Reasoning policy", runner.prompt)
        self.assertIn("toy examples", runner.prompt)
        self.assertIn("counterexamples", runner.prompt)
        self.assertIn("internal subgoals are proof steps", runner.prompt)
        self.assertNotIn("Repair round", runner.prompt)

    def test_repair_context_adds_verifier_feedback_and_attempt_budget(self) -> None:
        runner = StaticCodex()
        worker = ResearchWorker(runner)
        repair = RepairContext(
            previous_statement="Every integer is even.",
            previous_proof="Claimed without justification.",
            verifier_reason="counterexample n=1",
            attempt_number=2,
            max_attempts=3,
        )

        worker.propose(
            problem="Prove T.",
            existing_facts=[],
            subgoal="Goal:\nT.",
            repair_context=repair,
        )

        self.assertIn("Repair round 2 of 3", runner.prompt)
        self.assertIn("Every integer is even.", runner.prompt)
        self.assertIn("Claimed without justification.", runner.prompt)
        self.assertIn("counterexample n=1", runner.prompt)
        self.assertIn("key failure", runner.prompt)
        self.assertIn("root cause", runner.prompt)
        self.assertIn("materially identical proof", runner.prompt)


if __name__ == "__main__":
    unittest.main()
