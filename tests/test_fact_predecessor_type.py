import unittest

from research.fact import Fact


class FactPredecessorTypeTests(unittest.TestCase):
    def test_fact_predecessors_are_canonical_tuple(self) -> None:
        fact = Fact.create(
            problem_id="p",
            author="worker",
            statement="C",
            proof="A and B imply C.",
            predecessors=("bbbbbbbbbbbbbbbb", "aaaaaaaaaaaaaaaa", "aaaaaaaaaaaaaaaa"),
        )

        self.assertEqual(fact.predecessors, ("aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"))
        self.assertIsInstance(fact.predecessors, tuple)


if __name__ == "__main__":
    unittest.main()
