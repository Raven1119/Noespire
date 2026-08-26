import unittest

from research.fact import Fact


class FactTests(unittest.TestCase):
    def test_equivalent_content_has_a_stable_fact_id(self) -> None:
        first = Fact.create(
            problem_id="odd-sum",
            author="worker-a",
            statement="The first two odd numbers sum to four.",
            proof="1 + 3 = 4.",
            predecessors=("fact-b", "fact-a"),
        )
        second = Fact.create(
            problem_id="odd-sum",
            author="worker-b",
            statement="  The first two odd numbers\n sum to four. ",
            proof="1 + 3  = 4.\n",
            predecessors=("fact-a", "fact-b"),
        )

        self.assertEqual(first.fact_id, "7bdf963a57fe0373")
        self.assertEqual(first.fact_id, second.fact_id)


if __name__ == "__main__":
    unittest.main()
