import unittest

from research.agents import ResearchVerifier
from research.fact import CandidateFact, Fact
from research.pipeline import VerificationResult


class StaticCodex:
    def __init__(self, response=None) -> None:
        self.prompt = ""
        self.response = response or {
            "accepted": True,
            "reason": "The derivation is correct.",
        }

    def invoke(self, *, prompt, schema, label):
        self.prompt = prompt
        return self.response


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

    def test_correct_intermediate_is_the_verification_target(self) -> None:
        runner = StaticCodex()
        verifier = ResearchVerifier(runner)
        candidate = CandidateFact(
            statement="For every integer n, n^3 - n is divisible by 2.",
            proof="The product n(n-1)(n+1) contains an even factor.",
            predecessors=(),
        )

        result = verifier.verify(
            "Prove that n^3 - n is divisible by 6 for every integer n.",
            candidate,
            [],
        )

        self.assertTrue(result.accepted)
        self.assertIn("The complete Problem is background context only", runner.prompt)
        self.assertIn("The candidate may be an intermediate lemma", runner.prompt)
        self.assertIn(
            "establishes exactly the candidate statement",
            runner.prompt,
        )
        self.assertIn(
            "Do not require the candidate to prove the complete Problem",
            runner.prompt,
        )

    def test_root_theorem_verdict_is_preserved(self) -> None:
        candidate = CandidateFact(
            statement="The sum of the first n odd integers is n^2.",
            proof="Induct on n.",
            predecessors=(),
        )
        for accepted in (True, False):
            with self.subTest(accepted=accepted):
                runner = StaticCodex(
                    {"accepted": accepted, "reason": "frozen root verdict"}
                )
                result = ResearchVerifier(runner).verify(
                    candidate.statement,
                    candidate,
                    [],
                )
                self.assertEqual(result, VerificationResult(accepted, "frozen root verdict"))
                normalized_prompt = " ".join(runner.prompt.split())
                self.assertIn(
                    "unless the candidate statement itself is the complete Problem",
                    normalized_prompt,
                )
                self.assertEqual(runner.prompt.count(candidate.statement), 2)

    def test_false_intermediate_verdict_remains_rejected(self) -> None:
        runner = StaticCodex({"accepted": False, "reason": "counterexample n=1"})
        candidate = CandidateFact(
            statement="Every integer is even.",
            proof="This is claimed without justification.",
            predecessors=(),
        )

        result = ResearchVerifier(runner).verify("Prove a different theorem.", candidate, [])

        self.assertFalse(result.accepted)
        self.assertIn("mathematically correct", runner.prompt)

    def test_insufficient_proof_verdict_remains_rejected(self) -> None:
        runner = StaticCodex({"accepted": False, "reason": "proof is insufficient"})
        candidate = CandidateFact(
            statement="There are infinitely many primes.",
            proof="This is a classical theorem.",
            predecessors=(),
        )

        result = ResearchVerifier(runner).verify("Prove a larger result.", candidate, [])

        self.assertFalse(result.accepted)
        self.assertIn("proof establishes exactly the candidate statement", runner.prompt)

    def test_missing_assumption_verdict_remains_rejected(self) -> None:
        runner = StaticCodex({"accepted": False, "reason": "x may be negative"})
        candidate = CandidateFact(
            statement="For every real x, sqrt(x)^2 = x.",
            proof="Apply the real square-root identity, assuming x is nonnegative.",
            predecessors=(),
        )

        result = ResearchVerifier(runner).verify("Prove a larger result.", candidate, [])

        self.assertFalse(result.accepted)
        self.assertIn("missing assumptions", runner.prompt)

    def test_predecessor_misuse_verdict_remains_rejected(self) -> None:
        runner = StaticCodex(
            {"accepted": False, "reason": "the predecessor does not imply the claim"}
        )
        predecessor = Fact(
            fact_id="unrelated-id",
            problem_id="p",
            author="worker",
            statement="2 is even.",
            proof="2 = 2 * 1.",
            predecessors=(),
        )
        candidate = CandidateFact(
            statement="3 is even.",
            proof="This follows from the predecessor.",
            predecessors=("unrelated-id",),
        )

        result = ResearchVerifier(runner).verify("Prove a larger result.", candidate, [predecessor])

        self.assertFalse(result.accepted)
        self.assertIn("predecessors are collectively sufficient", runner.prompt)
        self.assertIn("genuinely used", runner.prompt)
        self.assertIn("unsupported inference", runner.prompt)


if __name__ == "__main__":
    unittest.main()
