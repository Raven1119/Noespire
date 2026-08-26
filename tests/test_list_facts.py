from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from research.fact import Fact
from research.graph import FactGraph


class ListFactsTests(unittest.TestCase):
    def test_list_facts_returns_all_persisted_facts_in_stable_order(self) -> None:
        with TemporaryDirectory() as directory:
            graph = FactGraph(Path(directory))
            facts = [
                Fact.create(problem_id="p", author="w", statement=name, proof=f"Proof {name}.")
                for name in ("B", "A")
            ]
            for fact in facts:
                graph.add_fact(fact)

            self.assertEqual(
                [fact.fact_id for fact in graph.list_facts()],
                sorted(fact.fact_id for fact in facts),
            )


if __name__ == "__main__":
    unittest.main()
