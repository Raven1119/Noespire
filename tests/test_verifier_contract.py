import unittest

from research.agents import ResearchVerifier
from research.fact import CandidateFact, Fact
from research.pipeline import VerificationResult


class StaticCodex:
    def __init__(self) -> None:
        self.prompt = ""

    def invoke(self, *, prompt, schema, label):
        self.prompt = prompt
        return {"accepted": True, "reason": "The derivation is correct."}


class VerifierContractTests(unittest.TestCase):
    def test_verifier_returns_structured_independent_verdict(self) -> None:
        runner = StaticCodex()
        verifier = ResearchVerifier(runner)
        predecessor = Fact(
            fact_id="prior-id",
            problem_id="odd-sum",
            author="worker",
            statement="1 + 3 = 4.",
            proof="Direct addition.",
            predecessors=(),
        )
        candidate = CandidateFact(
            statement="1 + 3 + 5 = 9.",
            proof="Add 5 to the predecessor equality.",
            predecessors=("prior-id",),
        )

        result = verifier.verify("Prove the odd sum.", candidate, [predecessor])

        self.assertEqual(result, VerificationResult(True, "The derivation is correct."))
        self.assertIn("independent fresh Codex verifier", runner.prompt)
        self.assertIn("prior-id", runner.prompt)


if __name__ == "__main__":
    unittest.main()
